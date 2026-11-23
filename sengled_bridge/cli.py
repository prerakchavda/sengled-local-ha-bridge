"""
Command-Line Interface for Sengled Local Home Assistant Bridge.

Subcommands:
  - `models`     : List all known Sengled Wi-Fi & BLE models / FCC IDs or fingerprint a specific model
  - `certs`      : Generate self-signed TLS CA & Server certificates for local port 8883 Mosquitto
  - `provision`  : Pair a factory-reset Sengled Wi-Fi bulb (192.168.8.1:9080) to 2.4 GHz Wi-Fi & local bridge
  - `udp`        : Discover or control Sengled Wi-Fi bulbs directly on LAN UDP port 9080
  - `ble-scan`   : Scan & fingerprint Sengled BLE SIG Mesh / GATT bulbs via `bleak`
  - `serve`      : Start the Local HTTP Discovery Server + Web UI + Home Assistant MQTT Discovery Bridge
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, List, Optional

from sengled_bridge.bridge import SengledHomeAssistantBridge
from sengled_bridge.crypto import generate_self_signed_certs
from sengled_bridge.http_server import SengledDiscoveryHTTPServer
from sengled_bridge.models import (
    MODEL_CATALOG,
    RADIO_MODULES,
    evaluate_esphome_tasmota_vs_stock,
    identify_device_by_model_or_fcc,
)
from sengled_bridge.provisioning import (
    discover_lan_bulbs_udp,
    provision_wifi_bulb,
    udp_set_brightness,
    udp_set_color,
    udp_set_colortemp,
    udp_set_switch,
)


def _cmd_models(args: argparse.Namespace) -> int:
    if args.query:
        matches = identify_device_by_model_or_fcc(args.query)
        evaluation = evaluate_esphome_tasmota_vs_stock(args.query)
        output = {
            "query": args.query,
            "matches": [asdict(m) for m in matches],
            "flashing_evaluation": evaluation,
        }
        print(json.dumps(output, indent=2))
        return 0 if matches else 1

    print(f"=== Sengled Radio Modules ({len(RADIO_MODULES)} FCC Certified Modules) ===")
    for mod in RADIO_MODULES.values():
        print(
            f"  {mod.module_id:<8} | FCC: {mod.fcc_id:<14} | {mod.protocol.value:<18} | {mod.chipset}"
        )

    print(f"\n=== Sengled Smart Bulb & Device Models ({len(MODEL_CATALOG)} Families) ===")
    for spec in MODEL_CATALOG:
        fcc_str = ", ".join(spec.fcc_ids)
        print(
            f"  {spec.model:<10} | {spec.protocol.value:<18} | {spec.capability.value:<10} | "
            f"Module: {spec.module_id:<6} | FCC: {fcc_str:<26} | {spec.name}"
        )
    return 0


def _cmd_certs(args: argparse.Namespace) -> int:
    paths = generate_self_signed_certs(
        cert_dir=args.dir,
        common_name=args.cn,
        server_ip=args.ip,
        overwrite=args.overwrite,
    )
    print(
        json.dumps(
            {k: str(v) for k, v in paths.items()},
            indent=2,
        )
    )
    return 0


def _cmd_provision(args: argparse.Namespace) -> int:
    result = provision_wifi_bulb(
        ssid=args.ssid,
        password=args.password,
        server_ip=args.server_ip,
        http_port=args.http_port,
        bulb_ip=args.bulb_ip,
        bulb_port=args.bulb_port,
        bssid=args.bssid,
    )
    print(json.dumps(asdict(result), indent=2))
    return 0 if result.success else 1


def _cmd_udp(args: argparse.Namespace) -> int:
    if args.discover:
        bulbs = discover_lan_bulbs_udp(listen_seconds=args.timeout)
        print(json.dumps({"discovered": len(bulbs), "bulbs": bulbs}, indent=2))
        return 0

    if not args.ip:
        print("Error: --ip <BULB_IP> is required unless --discover is set.", file=sys.stderr)
        return 2

    resp: Any = None
    if args.on:
        resp = udp_set_switch(args.ip, True)
    elif args.off:
        resp = udp_set_switch(args.ip, False)
    elif args.brightness is not None:
        resp = udp_set_brightness(args.ip, args.brightness)
    elif args.color is not None:
        r, g, b = args.color
        resp = udp_set_color(args.ip, r, g, b)
    elif args.colortemp is not None:
        resp = udp_set_colortemp(args.ip, args.colortemp)
    else:
        print("Specify one of --discover, --on, --off, --brightness, --color, or --colortemp.", file=sys.stderr)
        return 2

    print(json.dumps({"ip": args.ip, "response": resp}, indent=2))
    return 0


def _cmd_ble_scan(args: argparse.Namespace) -> int:
    from sengled_bridge.ble_controller import SengledBLEController

    ctrl = SengledBLEController()
    devices = asyncio.run(ctrl.scan_sengled_ble_devices(timeout_s=args.timeout))
    print(json.dumps({"discovered_ble": len(devices), "devices": devices}, indent=2))
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    import paho.mqtt.client as mqtt

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    log = logging.getLogger("sengled_bridge.serve")

    if args.auto_certs:
        certs = generate_self_signed_certs(
            cert_dir=args.cert_dir,
            server_ip=args.advertise_ip,
        )
        log.info("Verified self-signed TLS certificates in %s", certs["server_cert"].parent)

    bridge = SengledHomeAssistantBridge(
        discovery_prefix=args.discovery_prefix,
        bridge_prefix=args.bridge_prefix,
        seq_storage_path=Path(args.data_dir) / "ble_mesh_seq.json",
    )

    # Set up MQTT client connected to the HA / unified Mosquitto broker
    try:
        mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="sengled-local-ha-bridge")
    except AttributeError:
        mqtt_client = mqtt.Client(client_id="sengled-local-ha-bridge")

    if args.mqtt_username:
        mqtt_client.username_pw_set(args.mqtt_username, args.mqtt_password or "")

    mqtt_client.will_set(
        f"{args.bridge_prefix}/bridge/status", payload="offline", qos=1, retain=True
    )

    def _publish(topic: str, payload: str, retain: bool = False) -> None:
        mqtt_client.publish(topic, payload=payload, qos=1, retain=retain)

    bridge.set_publish_callbacks(publish_ha=_publish, publish_bulb=_publish)

    def _on_connect(client: Any, userdata: Any, flags: Any, rc: Any, *extra: Any) -> None:
        log.info("Connected to MQTT broker %s:%s (rc=%s)", args.mqtt_host, args.mqtt_port, rc)
        client.subscribe("wifielement/+/status", qos=1)
        client.subscribe("wifielement/c/status", qos=1)
        client.subscribe("wifielement/+/consumption", qos=1)
        client.subscribe("wifielement/+/consumptionTime", qos=1)
        client.subscribe(f"{args.bridge_prefix}/light/+/set", qos=1)
        bridge.publish_bridge_online(True)

        # Register any pre-configured BLE bulbs
        for ble_spec in args.ble_bulb or []:
            parts = ble_spec.split(",")
            mac = parts[0].strip()
            model = parts[1].strip() if len(parts) > 1 else "B11-N1E"
            bridge.register_ble_bulb_in_ha(mac=mac, model=model)
            log.info("Registered BLE bulb %s (%s) in Home Assistant", mac, model)

    def _on_message(client: Any, userdata: Any, msg: Any) -> None:
        topic = str(msg.topic)
        if topic.startswith("wifielement/"):
            bridge.handle_wifielement_message(topic, msg.payload)
        elif topic.startswith(f"{args.bridge_prefix}/light/") and topic.endswith("/set"):
            bridge.handle_ha_command_message(topic, msg.payload)

    mqtt_client.on_connect = _on_connect
    mqtt_client.on_message = _on_message

    http_server = SengledDiscoveryHTTPServer(
        mqtt_host=args.advertise_ip,
        mqtt_tls_port=args.bulb_tls_port,
        http_port=args.http_port,
        status_provider=bridge.get_summary_status,
    )
    bound_port = http_server.start()
    log.info(
        "HTTP Discovery & Web UI listening on http://0.0.0.0:%d (advertising MQTT TLS %s:%d)",
        bound_port,
        args.advertise_ip,
        args.bulb_tls_port,
    )

    try:
        mqtt_client.connect(args.mqtt_host, args.mqtt_port, keepalive=60)
        mqtt_client.loop_start()
    except Exception as exc:
        log.warning("Initial MQTT connect to %s:%s failed (%s); HTTP server remains active.", args.mqtt_host, args.mqtt_port, exc)

    stop_event = False

    def _handle_sig(signum: int, frame: Any) -> None:
        nonlocal stop_event
        stop_event = True

    signal.signal(signal.SIGINT, _handle_sig)
    signal.signal(signal.SIGTERM, _handle_sig)

    try:
        while not stop_event:
            time.sleep(0.5)
    finally:
        bridge.publish_bridge_online(False)
        mqtt_client.loop_stop()
        http_server.stop()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sengled-bridge",
        description="100% Local Home Assistant Bridge for Sengled Wi-Fi & BLE Smart Bulbs",
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    # 1. models
    p_models = sub.add_parser("models", help="List or fingerprint Sengled models and FCC IDs")
    p_models.add_argument("-q", "--query", help="Model number or FCC ID (e.g. W31-N11, 2AGN8-WF863, B11-N1E)")
    p_models.set_defaults(func=_cmd_models)

    # 2. certs
    p_certs = sub.add_parser("certs", help="Generate self-signed TLS certs for port 8883 Mosquitto")
    p_certs.add_argument("--dir", default="./certs", help="Output certificate directory")
    p_certs.add_argument("--cn", default="sengled.local", help="Certificate Common Name")
    p_certs.add_argument("--ip", default="127.0.0.1", help="Local Bridge IP for SAN")
    p_certs.add_argument("--overwrite", action="store_true", help="Overwrite existing certificates")
    p_certs.set_defaults(func=_cmd_certs)

    # 3. provision
    p_prov = sub.add_parser("provision", help="Provision a reset Sengled Wi-Fi bulb in AP mode (192.168.8.1:9080)")
    p_prov.add_argument("--ssid", required=True, help="2.4 GHz Wi-Fi SSID")
    p_prov.add_argument("--password", required=True, help="Wi-Fi Password")
    p_prov.add_argument("--server-ip", required=True, help="Local bridge IP that serves /accessCloud.json and /bimqtt")
    p_prov.add_argument("--http-port", type=int, default=8080, help="Local HTTP discovery server port (default: 8080)")
    p_prov.add_argument("--bulb-ip", default="192.168.8.1", help="Bulb AP IP (default: 192.168.8.1)")
    p_prov.add_argument("--bulb-port", type=int, default=9080, help="Bulb UDP port (default: 9080)")
    p_prov.add_argument("--bssid", help="Router BSSID (required only for non-ASCII SSIDs)")
    p_prov.set_defaults(func=_cmd_provision)

    # 4. udp
    p_udp = sub.add_parser("udp", help="Direct local UDP discovery & control on port 9080")
    p_udp.add_argument("--discover", action="store_true", help="Broadcast search_devices on UDP 9080")
    p_udp.add_argument("--timeout", type=float, default=2.0, help="Discovery listen timeout (seconds)")
    p_udp.add_argument("--ip", help="Target bulb LAN IP")
    p_udp.add_argument("--on", action="store_true", help="Turn bulb ON via UDP")
    p_udp.add_argument("--off", action="store_true", help="Turn bulb OFF via UDP")
    p_udp.add_argument("--brightness", type=int, help="Set brightness 0..100 via UDP")
    p_udp.add_argument("--color", nargs=3, type=int, metavar=("R", "G", "B"), help="Set RGB color 0..255 via UDP")
    p_udp.add_argument("--colortemp", type=int, help="Set color temperature 0..100 via UDP")
    p_udp.set_defaults(func=_cmd_udp)

    # 5. ble-scan
    p_ble = sub.add_parser("ble-scan", help="Scan and fingerprint Sengled BLE SIG Mesh / GATT bulbs")
    p_ble.add_argument("--timeout", type=float, default=8.0, help="Scan duration in seconds")
    p_ble.set_defaults(func=_cmd_ble_scan)

    # 6. matter
    p_matter = sub.add_parser(
        "matter",
        help="Decode Matter QR (MT:...) or 11/21-digit codes & classify Amazon Basics / Sengled Matter vs ACK devices",
    )
    p_matter.add_argument(
        "--code",
        required=True,
        help="Matter QR string (MT:...), 11/21-digit pairing code, or Amazon Basics barcode/model",
    )
    p_matter.set_defaults(func=_cmd_matter)

    # 7. serve
    p_serve = sub.add_parser("serve", help="Run the local HTTP config server + HA MQTT Discovery bridge")
    p_serve.add_argument("--advertise-ip", default="127.0.0.1", help="LAN IP returned to bulbs in /bimqtt")
    p_serve.add_argument("--http-port", type=int, default=8080, help="HTTP discovery & Web UI port (default: 8080)")
    p_serve.add_argument("--bulb-tls-port", type=int, default=8883, help="TLS MQTT port returned in /bimqtt (default: 8883)")
    p_serve.add_argument("--mqtt-host", default="127.0.0.1", help="Home Assistant / local MQTT broker host")
    p_serve.add_argument("--mqtt-port", type=int, default=1883, help="Home Assistant / local MQTT broker port")
    p_serve.add_argument("--mqtt-username", default="", help="Optional MQTT username")
    p_serve.add_argument("--mqtt-password", default="", help="Optional MQTT password")
    p_serve.add_argument("--discovery-prefix", default="homeassistant", help="HA MQTT discovery prefix")
    p_serve.add_argument("--bridge-prefix", default="sengled_bridge", help="Bridge state/command topic prefix")
    p_serve.add_argument("--cert-dir", default="./certs", help="Directory for self-signed TLS certificates")
    p_serve.add_argument("--data-dir", default="./data", help="Directory for persistent state & BLE mesh seq floor")
    p_serve.add_argument("--auto-certs", action="store_true", default=True, help="Auto-generate TLS certs on startup")
    p_serve.add_argument("--ble-bulb", action="append", help="Register BLE bulb as MAC,MODEL (e.g. EC:21:E5:11:22:33,B11-N1E)")
    p_serve.add_argument("--log-level", default="info", help="Logging level (debug, info, warning, error)")
    p_serve.set_defaults(func=_cmd_serve)

    return parser


def _cmd_matter(args: argparse.Namespace) -> int:
    from sengled_bridge.matter_helper import classify_and_decode_smart_bulb_code

    info = classify_and_decode_smart_bulb_code(args.code)
    print(json.dumps(info, indent=2))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
