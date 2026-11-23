"""
Unified Local Home Assistant Bridge Service for Sengled Wi-Fi & BLE Smart Bulbs.

Orchestrates:
- Local HTTP Discovery Server (`/life2/device/accessCloud.json`, `/jbalancer/new/bimqtt`, Web UI)
- MQTT Bridge translating between Sengled `wifielement/{MAC}/...` topics and Home Assistant
  MQTT Discovery (`homeassistant/light/sengled_{slug}/config` & `sengled_bridge/light/{slug}/...`)
- Local Bluetooth (BLE SIG Mesh) bulb state & command routing
"""

from __future__ import annotations

import json
import logging
import ssl
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from sengled_bridge.alexa_ack_bridge import (
    AlexaACKController,
    AlexaACKLightState,
    dsn_or_endpoint_to_mac,
)
from sengled_bridge.ble_controller import SengledBLEBulbState, SengledBLEController
from sengled_bridge.ha_discovery import (
    build_ha_light_discovery_payload,
    build_ha_light_state_payload,
    get_ha_topics,
    translate_ha_command_to_wifi_mqtt,
)
from sengled_bridge.http_server import SengledDiscoveryHTTPServer
from sengled_bridge.wifi_protocol import (
    SengledWiFiBulbState,
    decode_sengled_mqtt_payload,
    mac_to_slug,
    normalize_mac,
    parse_mqtt_topic,
)

logger = logging.getLogger("sengled_bridge")


class SengledHomeAssistantBridge:
    """
    Core message processor and router bridging Sengled Wi-Fi (MQTT/UDP), BLE
    (SIG Mesh), and Amazon 'Works with Alexa Only' (ACK & Echo-paired) bulbs
    into Home Assistant via MQTT Discovery.
    """

    def __init__(
        self,
        discovery_prefix: str = "homeassistant",
        bridge_prefix: str = "sengled_bridge",
        publish_ha_callback: Optional[Callable[[str, str, bool], None]] = None,
        publish_bulb_callback: Optional[Callable[[str, str, bool], None]] = None,
        seq_storage_path: Optional[Union[str, Path]] = None,
        alexa_cookie: str = "",
        alexa_domain: str = "amazon.com",
        echo_entity_id: str = "media_player.echo_dot",
    ):
        self.discovery_prefix = discovery_prefix
        self.bridge_prefix = bridge_prefix
        self._publish_ha = publish_ha_callback
        self._publish_bulb = publish_bulb_callback

        self.wifi_bulbs: Dict[str, SengledWiFiBulbState] = {}
        self.slug_to_mac: Dict[str, str] = {}
        self.published_discovery_signatures: Dict[str, str] = {}

        self.ble_controller = SengledBLEController(
            seq_storage_path=seq_storage_path,
            on_state_change=self._on_ble_bulb_state_change,
        )

        self.ack_controller = AlexaACKController(
            alexa_cookie=alexa_cookie,
            alexa_domain=alexa_domain,
            echo_entity_id=echo_entity_id,
            on_state_change=self._on_ack_bulb_state_change,
        )

    def set_publish_callbacks(
        self,
        publish_ha: Callable[[str, str, bool], None],
        publish_bulb: Optional[Callable[[str, str, bool], None]] = None,
    ) -> None:
        self._publish_ha = publish_ha
        self._publish_bulb = publish_bulb or publish_ha

    def _emit_ha(self, topic: str, payload: Union[str, Dict[str, Any]], retain: bool = True) -> None:
        if not self._publish_ha:
            return
        body = json.dumps(payload, separators=(",", ":")) if isinstance(payload, dict) else str(payload)
        self._publish_ha(topic, body, retain)

    def _emit_bulb(self, topic: str, payload: Union[str, Dict[str, Any]], retain: bool = False) -> None:
        cb = self._publish_bulb or self._publish_ha
        if not cb:
            return
        body = json.dumps(payload, separators=(",", ":")) if isinstance(payload, dict) else str(payload)
        cb(topic, body, retain)

    def publish_bridge_online(self, online: bool = True) -> None:
        topic = f"{self.bridge_prefix}/bridge/status"
        self._emit_ha(topic, "online" if online else "offline", retain=True)

    # -----------------------------------------------------------------------
    # Wi-Fi, BLE & Amazon "Works with Alexa Only" (ACK) Registration
    # -----------------------------------------------------------------------
    def get_or_create_wifi_bulb(self, mac: str) -> SengledWiFiBulbState:
        norm_mac = normalize_mac(mac)
        slug = mac_to_slug(norm_mac)
        self.slug_to_mac[slug] = norm_mac
        if norm_mac not in self.wifi_bulbs:
            self.wifi_bulbs[norm_mac] = SengledWiFiBulbState(mac=norm_mac)
        return self.wifi_bulbs[norm_mac]

    def register_ble_bulb_in_ha(
        self,
        mac: str,
        model: str = "B11-N1E",
        friendly_name: Optional[str] = None,
        unicast_addr: int = 0x0002,
    ) -> SengledBLEBulbState:
        """Register a Sengled BLE Mesh bulb and publish its HA MQTT Discovery config."""
        norm_mac = normalize_mac(mac)
        slug = mac_to_slug(norm_mac)
        self.slug_to_mac[slug] = norm_mac
        bulb = self.ble_controller.register_bulb(
            norm_mac, model=model, name=friendly_name, unicast_addr=unicast_addr
        )
        topics = get_ha_topics(norm_mac, self.discovery_prefix, self.bridge_prefix)
        disc_payload = build_ha_light_discovery_payload(
            mac=norm_mac,
            model_code=bulb.model,
            friendly_name=bulb.name,
            transport="BLE SIG Mesh",
            discovery_prefix=self.discovery_prefix,
            bridge_prefix=self.bridge_prefix,
        )
        self._emit_ha(topics["discovery_topic"], disc_payload, retain=True)
        self._emit_ha(topics["availability_topic"], "online", retain=True)
        self._emit_ha(topics["state_topic"], build_ha_light_state_payload(bulb), retain=True)
        return bulb

    def register_ack_light_in_ha(
        self,
        identifier: str,
        model: str = "13ASB-A800ST-Q1T",
        friendly_name: Optional[str] = None,
        endpoint_id: str = "",
        dsn: str = "",
        manufacturer: str = "Amazon Basics",
    ) -> AlexaACKLightState:
        """
        Register an Amazon 'Works with Alexa Only' (ACK or Echo-paired) light by MAC,
        DSN, FFS barcode, or Alexa `endpointId`, and publish its HA MQTT Discovery config.
        """
        norm_mac = dsn_or_endpoint_to_mac(identifier)
        slug = mac_to_slug(norm_mac)
        self.slug_to_mac[slug] = norm_mac
        bulb = self.ack_controller.register_bulb(
            identifier=identifier,
            model=model,
            name=friendly_name,
            endpoint_id=endpoint_id,
            dsn=dsn,
            manufacturer=manufacturer,
        )
        topics = get_ha_topics(norm_mac, self.discovery_prefix, self.bridge_prefix)
        disc_payload = build_ha_light_discovery_payload(
            mac=norm_mac,
            model_code=bulb.model,
            friendly_name=bulb.name,
            transport="Amazon Alexa ACK",
            manufacturer=bulb.manufacturer,
            discovery_prefix=self.discovery_prefix,
            bridge_prefix=self.bridge_prefix,
        )
        self._emit_ha(topics["discovery_topic"], disc_payload, retain=True)
        self._emit_ha(topics["availability_topic"], "online", retain=True)
        self._emit_ha(topics["state_topic"], build_ha_light_state_payload(bulb), retain=True)
        return bulb

    def discover_and_register_alexa_lights(self) -> List[AlexaACKLightState]:
        """
        Query Amazon's `/nexus/v1/graphql` endpoint using the configured `alexa_cookie`
        and automatically register all discovered 'Works with Alexa Only' lights in HA.
        """
        bulbs = self.ack_controller.discover_from_alexa_graphql()
        for bulb in bulbs:
            slug = mac_to_slug(bulb.mac)
            self.slug_to_mac[slug] = bulb.mac
            topics = get_ha_topics(bulb.mac, self.discovery_prefix, self.bridge_prefix)
            disc_payload = build_ha_light_discovery_payload(
                mac=bulb.mac,
                model_code=bulb.model,
                friendly_name=bulb.name,
                transport="Amazon Alexa ACK",
                manufacturer=bulb.manufacturer,
                discovery_prefix=self.discovery_prefix,
                bridge_prefix=self.bridge_prefix,
            )
            self._emit_ha(topics["discovery_topic"], disc_payload, retain=True)
            self._emit_ha(topics["availability_topic"], "online", retain=True)
            self._emit_ha(topics["state_topic"], build_ha_light_state_payload(bulb), retain=True)
        return bulbs

    def _on_ble_bulb_state_change(self, bulb: SengledBLEBulbState) -> None:
        topics = get_ha_topics(bulb.mac, self.discovery_prefix, self.bridge_prefix)
        self._emit_ha(topics["availability_topic"], "online", retain=True)
        self._emit_ha(topics["state_topic"], build_ha_light_state_payload(bulb), retain=True)

    def _on_ack_bulb_state_change(self, bulb: AlexaACKLightState) -> None:
        topics = get_ha_topics(bulb.mac, self.discovery_prefix, self.bridge_prefix)
        self._emit_ha(topics["availability_topic"], "online", retain=True)
        self._emit_ha(topics["state_topic"], build_ha_light_state_payload(bulb), retain=True)

    def _ensure_wifi_discovery_published(self, bulb: SengledWiFiBulbState) -> None:
        sig = f"{bulb.type_code}|{bulb.support_attributes}|{bulb.firmware_version}|{bulb.identify_no}"
        if self.published_discovery_signatures.get(bulb.mac) == sig:
            return
        self.published_discovery_signatures[bulb.mac] = sig

        topics = get_ha_topics(bulb.mac, self.discovery_prefix, self.bridge_prefix)
        disc_payload = build_ha_light_discovery_payload(
            mac=bulb.mac,
            model_code=bulb.type_code,
            support_attributes=bulb.support_attributes,
            firmware_version=bulb.firmware_version,
            chipset=bulb.identify_no,
            transport="Wi-Fi",
            discovery_prefix=self.discovery_prefix,
            bridge_prefix=self.bridge_prefix,
        )
        self._emit_ha(topics["discovery_topic"], disc_payload, retain=True)

    def handle_wifielement_message(self, topic: str, payload: Union[str, bytes]) -> Optional[SengledWiFiBulbState]:
        """
        Process an incoming MQTT message on `wifielement/{MAC}/status`,
        `wifielement/c/status`, `wifielement/{MAC}/consumption`, or
        `wifielement/{MAC}/consumptionTime`.
        """
        parsed_topic = parse_mqtt_topic(topic)
        if not parsed_topic:
            return None

        topic_mac, subtopic = parsed_topic
        if subtopic not in ("status", "consumption", "consumptionTime"):
            return None

        try:
            records = decode_sengled_mqtt_payload(payload)
        except json.JSONDecodeError:
            logger.warning("Ignoring malformed JSON on %s", topic)
            return None

        if not records:
            return None

        # When topic is `wifielement/c/status`, extract the bulb MAC from `dn` inside the record
        target_mac = topic_mac
        if target_mac == "c":
            dn_val = str(records[0].get("dn", "") or "").strip()
            if not dn_val:
                return None
            target_mac = normalize_mac(dn_val)

        bulb = self.get_or_create_wifi_bulb(target_mac)
        bulb.apply_status_records(records)

        self._ensure_wifi_discovery_published(bulb)
        topics = get_ha_topics(bulb.mac, self.discovery_prefix, self.bridge_prefix)
        self._emit_ha(topics["availability_topic"], "online", retain=True)
        self._emit_ha(topics["state_topic"], build_ha_light_state_payload(bulb), retain=True)
        return bulb

    # -----------------------------------------------------------------------
    # Home Assistant Command Routing (`sengled_bridge/light/{slug}/set`)
    # -----------------------------------------------------------------------
    def handle_ha_command_message(
        self, topic: str, payload: Union[str, bytes]
    ) -> Optional[Dict[str, Any]]:
        """
        Handle an incoming Home Assistant command on `sengled_bridge/light/{slug}/set`.
        Routes to:
          - `AlexaACKController` (for Amazon 'Works with Alexa Only' ACK / Echo-paired lights)
          - `SengledBLEController` (for BLE SIG Mesh bulbs)
          - `wifielement/{MAC}/update` (for Sengled Wi-Fi bulbs)
        """
        prefix = f"{self.bridge_prefix}/light/"
        if not topic.startswith(prefix) or not topic.endswith("/set"):
            return None

        slug = topic[len(prefix) : -len("/set")].strip().lower()
        mac = self.slug_to_mac.get(slug) or normalize_mac(slug)

        if isinstance(payload, bytes):
            cmd_text = payload.decode("utf-8", errors="ignore").strip()
        else:
            cmd_text = str(payload).strip()

        # Support plain "ON"/"OFF" as well as JSON schema payloads
        if cmd_text.upper() in ("ON", "OFF"):
            cmd_dict: Dict[str, Any] = {"state": cmd_text.upper()}
        else:
            cmd_dict = json.loads(cmd_text)

        # 1. Check if this MAC belongs to a registered Amazon "Works with Alexa Only" (ACK) light
        if mac in self.ack_controller.bulbs:
            return self._dispatch_ack_command(mac, cmd_dict)

        # 2. Check if this MAC belongs to a registered BLE bulb
        if mac in self.ble_controller.bulbs:
            return self._dispatch_ble_command(mac, cmd_dict)

        # 3. Otherwise route to Wi-Fi bulb via `wifielement/{MAC}/update`
        bulb = self.get_or_create_wifi_bulb(mac)
        bulb_topic, bulb_payload = translate_ha_command_to_wifi_mqtt(mac, cmd_dict)
        self._emit_bulb(bulb_topic, bulb_payload, retain=False)

        # Optimistically update state so HA UI responds immediately
        records = decode_sengled_mqtt_payload(bulb_payload)
        bulb.apply_status_records(records)
        self._ensure_wifi_discovery_published(bulb)
        topics = get_ha_topics(bulb.mac, self.discovery_prefix, self.bridge_prefix)
        self._emit_ha(topics["state_topic"], build_ha_light_state_payload(bulb), retain=True)

        return {
            "transport": "wifi",
            "mac": mac,
            "topic": bulb_topic,
            "payload": json.loads(bulb_payload),
        }

    def _dispatch_ack_command(self, mac: str, cmd_dict: Dict[str, Any]) -> Dict[str, Any]:
        result = self.ack_controller.dispatch_ha_command(mac, cmd_dict)
        topics = get_ha_topics(mac, self.discovery_prefix, self.bridge_prefix)
        # Emit voice command & HA service call relay payload on MQTT for zero-cookie HA automations
        self._emit_ha(
            topics["alexa_ack_command_topic"],
            result["voice_command_relay"],
            retain=False,
        )
        return result

    def _dispatch_ble_command(self, mac: str, cmd_dict: Dict[str, Any]) -> Dict[str, Any]:
        state_str = str(cmd_dict.get("state", "ON")).upper()
        pdus: List[bytes] = []

        if state_str == "OFF":
            pdus.append(self.ble_controller.build_turn_on_off_pdu(mac, False))
        else:
            if "color" in cmd_dict and isinstance(cmd_dict["color"], dict):
                c = cmd_dict["color"]
                pdus.append(
                    self.ble_controller.build_rgb_pdu(
                        mac,
                        int(c.get("r", 255)),
                        int(c.get("g", 255)),
                        int(c.get("b", 255)),
                        ha_brightness=cmd_dict.get("brightness"),
                    )
                )
            elif "color_temp_kelvin" in cmd_dict or "color_temp" in cmd_dict:
                from sengled_bridge.wifi_protocol import mireds_to_kelvin

                kelvin = (
                    int(cmd_dict["color_temp_kelvin"])
                    if "color_temp_kelvin" in cmd_dict
                    else mireds_to_kelvin(float(cmd_dict["color_temp"]))
                )
                pdus.append(
                    self.ble_controller.build_color_temp_pdu(
                        mac, kelvin, ha_brightness=cmd_dict.get("brightness")
                    )
                )
            elif "brightness" in cmd_dict:
                pdus.append(
                    self.ble_controller.build_brightness_pdu(mac, int(cmd_dict["brightness"]))
                )
            else:
                pdus.append(self.ble_controller.build_turn_on_off_pdu(mac, True))

        return {
            "transport": "ble_sig_mesh",
            "mac": mac,
            "proxy_pdus_hex": [p.hex() for p in pdus],
        }

    def get_summary_status(self) -> Dict[str, Any]:
        return {
            "wifi_bulbs_count": len(self.wifi_bulbs),
            "ble_bulbs_count": len(self.ble_controller.bulbs),
            "ack_lights_count": len(self.ack_controller.bulbs),
            "wifi_bulbs": {
                mac: {
                    "is_on": b.is_on,
                    "brightness_pct": b.brightness_pct,
                    "color_mode": b.color_mode,
                    "color_temp_kelvin": b.color_temp_kelvin,
                    "rgb": b.rgb,
                    "type_code": b.type_code,
                    "identify_no": b.identify_no,
                    "firmware_version": b.firmware_version,
                    "ip_address": b.ip_address,
                    "rssi": b.rssi,
                }
                for mac, b in self.wifi_bulbs.items()
            },
            "ble_bulbs": {
                mac: {
                    "is_on": b.is_on,
                    "ha_brightness": b.ha_brightness,
                    "color_mode": b.color_mode,
                    "color_temp_kelvin": b.color_temp_kelvin,
                    "rgb": b.rgb,
                    "model": b.model,
                    "unicast_addr": f"0x{b.unicast_addr:04X}",
                }
                for mac, b in self.ble_controller.bulbs.items()
            },
            "ack_lights": {
                mac: {
                    "is_on": b.is_on,
                    "ha_brightness": b.ha_brightness,
                    "color_mode": b.color_mode,
                    "color_temp_kelvin": b.color_temp_kelvin,
                    "rgb": b.rgb,
                    "alexa_color_name": b.last_alexa_color_name,
                    "model": b.model,
                    "name": b.name,
                    "endpoint_id": b.endpoint_id,
                    "dsn": b.dsn,
                    "hue_light_id": b.hue_light_id,
                }
                for mac, b in self.ack_controller.bulbs.items()
            },
        }

