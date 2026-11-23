"""
Sengled Wi-Fi AP Mode Provisioning & Local UDP LAN Discovery / Control (Port 9080).

Implements the reverse-engineered UDP onboarding sequence against a factory-reset
Sengled Wi-Fi bulb (default AP IP `192.168.8.1`, UDP port `9080`):
  1. `startConfigRequest` -> extracts bulb MAC address
  2. Optional `scanWifiRequest` + `getAPListRequest` -> lists nearby 2.4 GHz APs
  3. Second `startConfigRequest` (prep)
  4. `setParamsRequest` (RC4 + Base64 encrypted with `KEY_STR`) -> programs Wi-Fi
     credentials and overrides `appServerDomain` (`/life2/device/accessCloud.json`)
     and `jbalancerDomain` (`/jbalancer/new/bimqtt`) to point to the local bridge.
  5. `endConfigRequest` -> triggers bulb reboot onto the home LAN.
"""

from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from sengled_bridge.crypto import decrypt_wifi_payload, encrypt_wifi_payload
from sengled_bridge.wifi_protocol import (
    build_udp_brightness,
    build_udp_color,
    build_udp_colortemp,
    build_udp_search_devices,
    build_udp_switch,
    normalize_mac,
)

DEFAULT_BULB_AP_IP = "192.168.8.1"
DEFAULT_BULB_UDP_PORT = 9080


@dataclass
class ProvisioningResult:
    """Result of a Sengled Wi-Fi AP provisioning attempt."""

    success: bool
    bulb_mac: Optional[str]
    app_server_url: str
    jbalancer_url: str
    message: str
    raw_response: Optional[Dict[str, Any]] = None


def build_start_config_request() -> Dict[str, Any]:
    return {
        "name": "startConfigRequest",
        "totalStep": 1,
        "curStep": 1,
        "payload": {"protocol": 1},
    }


def build_scan_wifi_request() -> Dict[str, Any]:
    return {
        "name": "scanWifiRequest",
        "totalStep": 1,
        "curStep": 1,
        "payload": {},
    }


def build_get_ap_list_request() -> Dict[str, Any]:
    return {
        "name": "getAPListRequest",
        "totalStep": 1,
        "curStep": 1,
        "payload": {},
    }


def build_end_config_request() -> Dict[str, Any]:
    return {
        "name": "endConfigRequest",
        "totalStep": 1,
        "curStep": 1,
        "payload": {},
    }


def build_set_params_request(
    ssid: str,
    password: str,
    server_ip: str,
    http_port: int = 8080,
    bssid: Optional[str] = None,
    user_id: str = "618",
    timezone: str = "UTC",
) -> Tuple[Dict[str, Any], str]:
    """
    Construct the plaintext `setParamsRequest` dictionary and its RC4+Base64
    encrypted wire string.

    Note: Sengled firmware requires `bssid` and an empty `ssid` if the Wi-Fi
    SSID contains non-ASCII characters.
    """
    is_ascii = all(ord(c) < 128 for c in ssid)
    if is_ascii:
        router_info: Dict[str, str] = {"ssid": ssid, "password": password}
    else:
        if not bssid:
            raise ValueError(
                "Non-ASCII Wi-Fi SSID requires a BSSID (MAC address of router AP)."
            )
        router_info = {"ssid": "", "bssid": bssid.upper(), "password": password}

    app_url = f"http://{server_ip}:{http_port}/life2/device/accessCloud.json"
    jbalancer_url = f"http://{server_ip}:{http_port}/jbalancer/new/bimqtt"

    params_dict: Dict[str, Any] = {
        "name": "setParamsRequest",
        "totalStep": 1,
        "curStep": 1,
        "payload": {
            "userID": str(user_id),
            "appServerDomain": app_url,
            "jbalancerDomain": jbalancer_url,
            "timeZone": timezone,
            "routerInfo": router_info,
        },
    }
    encrypted = encrypt_wifi_payload(params_dict)
    return params_dict, encrypted


def parse_set_params_response(raw_text: str) -> Dict[str, Any]:
    """
    Parse the bulb's response to `setParamsRequest`, which may be either
    plaintext JSON or RC4+Base64 encrypted JSON depending on firmware version.
    """
    text = raw_text.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    decrypted = decrypt_wifi_payload(text)
    if isinstance(decrypted, dict):
        return decrypted
    raise ValueError("Unable to decode setParamsRequest response as JSON or RC4.")


def provision_wifi_bulb(
    ssid: str,
    password: str,
    server_ip: str,
    http_port: int = 8080,
    bulb_ip: str = DEFAULT_BULB_AP_IP,
    bulb_port: int = DEFAULT_BULB_UDP_PORT,
    bssid: Optional[str] = None,
    timezone: str = "UTC",
    timeout_s: float = 5.0,
) -> ProvisioningResult:
    """
    Execute the complete Wi-Fi AP onboarding flow against a reset Sengled bulb
    at `192.168.8.1:9080`.
    """
    params_dict, encrypted_params = build_set_params_request(
        ssid=ssid,
        password=password,
        server_ip=server_ip,
        http_port=http_port,
        bssid=bssid,
        timezone=timezone,
    )
    app_url = params_dict["payload"]["appServerDomain"]
    jbalancer_url = params_dict["payload"]["jbalancerDomain"]

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout_s)

        # Step 1: Initial startConfigRequest handshake
        start_msg = json.dumps(build_start_config_request()).encode("utf-8")
        sock.sendto(start_msg, (bulb_ip, bulb_port))
        data, _ = sock.recvfrom(4096)
        handshake = json.loads(data.decode("utf-8", errors="ignore"))
        raw_mac = handshake.get("payload", {}).get("mac")
        bulb_mac = normalize_mac(raw_mac) if raw_mac else None

        # Step 2: Re-handshake prep before sending parameters
        sock.sendto(start_msg, (bulb_ip, bulb_port))
        data2, _ = sock.recvfrom(4096)
        prep_resp = json.loads(data2.decode("utf-8", errors="ignore"))
        if not prep_resp.get("payload", {}).get("result", True):
            return ProvisioningResult(
                success=False,
                bulb_mac=bulb_mac,
                app_server_url=app_url,
                jbalancer_url=jbalancer_url,
                message="Bulb rejected startConfigRequest preparation step.",
                raw_response=prep_resp,
            )

        # Step 3: Send RC4+Base64 encrypted setParamsRequest
        sock.sendto(encrypted_params.encode("utf-8"), (bulb_ip, bulb_port))
        parsed_resp: Optional[Dict[str, Any]] = None
        try:
            resp_bytes, _ = sock.recvfrom(4096)
            parsed_resp = parse_set_params_response(
                resp_bytes.decode("utf-8", errors="ignore")
            )
            if parsed_resp.get("payload", {}).get("result") is False:
                return ProvisioningResult(
                    success=False,
                    bulb_mac=bulb_mac,
                    app_server_url=app_url,
                    jbalancer_url=jbalancer_url,
                    message="Bulb rejected setParamsRequest credentials.",
                    raw_response=parsed_resp,
                )
        except socket.timeout:
            # Some firmware versions reboot immediately or omit ack before endConfigRequest
            pass

        # Step 4: Send endConfigRequest
        end_msg = json.dumps(build_end_config_request()).encode("utf-8")
        sock.sendto(end_msg, (bulb_ip, bulb_port))
        try:
            sock.recvfrom(4096)
        except (socket.timeout, OSError):
            pass

        return ProvisioningResult(
            success=True,
            bulb_mac=bulb_mac,
            app_server_url=app_url,
            jbalancer_url=jbalancer_url,
            message=f"Provisioned bulb {bulb_mac or bulb_ip} to SSID '{ssid}' -> {server_ip}:{http_port}",
            raw_response=parsed_resp,
        )


def discover_lan_bulbs_udp(
    broadcast_ip: str = "255.255.255.255",
    port: int = DEFAULT_BULB_UDP_PORT,
    listen_seconds: float = 2.0,
) -> List[Dict[str, Any]]:
    """
    Broadcast `{"func":"search_devices","param":{}}` over UDP port 9080 to
    discover all Sengled Wi-Fi bulbs on the local subnet.
    """
    payload = build_udp_search_devices()
    discovered: Dict[str, Dict[str, Any]] = {}

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(0.3)
        sock.sendto(payload, (broadcast_ip, port))

        deadline = time.time() + listen_seconds
        while time.time() < deadline:
            try:
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break

            try:
                msg = json.loads(data.decode("utf-8", errors="ignore"))
            except json.JSONDecodeError:
                continue

            result = msg.get("result", msg) if isinstance(msg, dict) else {}
            mac = normalize_mac(str(result.get("mac", "") or addr[0]))
            discovered[mac] = {
                "ip": addr[0],
                "mac": mac,
                "version": result.get("version", ""),
                "mqtt_state": result.get("mqtt_state"),
                "config_state": result.get("config_state"),
                "R": result.get("R"),
                "G": result.get("G"),
                "B": result.get("B"),
                "W": result.get("W"),
                "raw": msg,
            }

    return list(discovered.values())


def send_udp_command(
    bulb_ip: str,
    payload: bytes,
    port: int = DEFAULT_BULB_UDP_PORT,
    timeout_s: float = 2.5,
) -> Optional[Dict[str, Any]]:
    """Send a raw UDP JSON command packet to a Sengled Wi-Fi bulb on port 9080."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout_s)
        sock.sendto(payload, (bulb_ip, port))
        try:
            data, _ = sock.recvfrom(4096)
            return json.loads(data.decode("utf-8", errors="ignore"))
        except (socket.timeout, json.JSONDecodeError):
            return None


def udp_set_switch(bulb_ip: str, on: bool, port: int = DEFAULT_BULB_UDP_PORT) -> Optional[Dict[str, Any]]:
    return send_udp_command(bulb_ip, build_udp_switch(on), port=port)


def udp_set_brightness(bulb_ip: str, brightness_pct: int, port: int = DEFAULT_BULB_UDP_PORT) -> Optional[Dict[str, Any]]:
    return send_udp_command(bulb_ip, build_udp_brightness(brightness_pct), port=port)


def udp_set_color(bulb_ip: str, r: int, g: int, b: int, port: int = DEFAULT_BULB_UDP_PORT) -> Optional[Dict[str, Any]]:
    return send_udp_command(bulb_ip, build_udp_color(r, g, b), port=port)


def udp_set_colortemp(bulb_ip: str, color_temp_pct: int, port: int = DEFAULT_BULB_UDP_PORT) -> Optional[Dict[str, Any]]:
    return send_udp_command(bulb_ip, build_udp_colortemp(color_temp_pct), port=port)
