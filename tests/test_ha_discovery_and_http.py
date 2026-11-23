"""Unit tests for Home Assistant MQTT Discovery, Bridge routing, and HTTP Discovery server."""

import json
import urllib.request
from pathlib import Path

from sengled_bridge.bridge import SengledHomeAssistantBridge
from sengled_bridge.ha_discovery import (
    build_ha_light_discovery_payload,
    translate_ha_command_to_wifi_mqtt,
)
from sengled_bridge.http_server import SengledDiscoveryHTTPServer


def test_ha_discovery_payload_for_w31_and_w21():
    # W31-N11 is dimmable soft white
    w31_disc = build_ha_light_discovery_payload(
        mac="40:43:18:2F:74:C9",
        model_code="W31-N11",
        support_attributes="brightness",
        firmware_version="V1.0.0.4",
        chipset="ESP8266",
    )
    assert w31_disc["unique_id"] == "sengled_4043182f74c9_light"
    assert w31_disc["supported_color_modes"] == ["brightness"]
    assert w31_disc["device"]["manufacturer"] == "Sengled"
    assert "WF863" in w31_disc["device"]["model"]

    # W21-N13 is RGBW multicolor
    w21_disc = build_ha_light_discovery_payload(
        mac="80:A0:36:E1:8E:B8",
        model_code="W21-N13",
        support_attributes="brightness,color,colorTemperature",
    )
    assert set(w21_disc["supported_color_modes"]) == {"color_temp", "rgb"}
    assert "min_mireds" in w21_disc and "max_mireds" in w21_disc


def test_translate_ha_command_to_wifi_mqtt():
    mac = "80:A0:36:E1:8E:B8"

    # Turn ON with color temperature + brightness
    topic, payload_str = translate_ha_command_to_wifi_mqtt(
        mac,
        {"state": "ON", "color_temp_kelvin": 4600, "brightness": 128, "transition": 1.5},
        timestamp_ms=1700000000000,
    )
    assert topic == f"wifielement/{mac}/update"
    cmds = json.loads(payload_str)
    types = [c["type"] for c in cmds]
    # Must include colorTemperature, switch="1", and brightness
    assert "colorTemperature" in types
    assert "switch" in types
    assert "brightness" in types
    for c in cmds:
        assert c.get("gradientTime") == 1500


def test_bridge_end_to_end_wifi_and_ble_routing(tmp_path: Path):
    ha_messages = []
    bulb_messages = []

    bridge = SengledHomeAssistantBridge(
        publish_ha_callback=lambda t, p, r: ha_messages.append((t, json.loads(p) if p.startswith("{") else p, r)),
        publish_bulb_callback=lambda t, p, r: bulb_messages.append((t, json.loads(p), r)),
        seq_storage_path=tmp_path / "ble_seq.json",
    )

    # 1. Simulate incoming Wi-Fi bulb status message
    status_payload = json.dumps(
        [
            {"dn": "40:43:18:2F:74:C9", "type": "typeCode", "value": "W31-N15", "time": "49"},
            {"dn": "40:43:18:2F:74:C9", "type": "identifyNO", "value": "ESP8266", "time": "49"},
            {"dn": "40:43:18:2F:74:C9", "type": "switch", "value": "1", "time": "49"},
            {"dn": "40:43:18:2F:74:C9", "type": "brightness", "value": "80", "time": "49"},
        ]
    )
    bridge.handle_wifielement_message("wifielement/40:43:18:2F:74:C9/status", status_payload)

    published_topics = [m[0] for m in ha_messages]
    assert "homeassistant/light/sengled_4043182f74c9/config" in published_topics
    assert "sengled_bridge/light/4043182f74c9/availability" in published_topics
    assert "sengled_bridge/light/4043182f74c9/state" in published_topics

    # 2. Simulate HA sending an RGB command back to the Wi-Fi bulb
    res = bridge.handle_ha_command_message(
        "sengled_bridge/light/4043182f74c9/set",
        json.dumps({"state": "ON", "color": {"r": 0, "g": 255, "b": 128}}),
    )
    assert res is not None
    assert res["transport"] == "wifi"
    assert bulb_messages[-1][0] == "wifielement/40:43:18:2F:74:C9/update"
    assert any(item["type"] == "color" and item["value"] == "0:255:128" for item in bulb_messages[-1][1])

    # 3. Register a BLE Mesh bulb and send a command from HA
    bridge.register_ble_bulb_in_ha("EC:21:E5:AA:BB:CC", model="B11-N1E")
    ble_res = bridge.handle_ha_command_message(
        "sengled_bridge/light/ec21e5aabbcc/set",
        json.dumps({"state": "ON", "brightness": 200}),
    )
    assert ble_res is not None
    assert ble_res["transport"] == "ble_sig_mesh"
    assert len(ble_res["proxy_pdus_hex"]) == 1


def test_http_discovery_server_endpoints():
    server = SengledDiscoveryHTTPServer(
        mqtt_host="192.168.1.250",
        mqtt_tls_port=8883,
        http_port=0,  # Ephemeral free port
    )
    port = server.start()
    try:
        base_url = f"http://127.0.0.1:{port}"

        # 1. POST /life2/device/accessCloud.json
        req1 = urllib.request.Request(
            f"{base_url}/life2/device/accessCloud.json",
            data=b"{}",
            method="POST",
        )
        with urllib.request.urlopen(req1, timeout=3) as resp1:
            data1 = json.loads(resp1.read().decode("utf-8"))
            assert data1["success"] is True
            assert data1["messageCode"] == "200"

        # 2. POST /jbalancer/new/bimqtt (must preserve Sengled's "protocal" typo!)
        req2 = urllib.request.Request(
            f"{base_url}/jbalancer/new/bimqtt",
            data=b"{}",
            method="POST",
        )
        with urllib.request.urlopen(req2, timeout=3) as resp2:
            data2 = json.loads(resp2.read().decode("utf-8"))
            assert data2 == {
                "protocal": "mqtt",
                "host": "192.168.1.250",
                "port": 8883,
            }

        # 3. GET /api/models?q=2AGN8-WF863
        with urllib.request.urlopen(f"{base_url}/api/models?q=2AGN8-WF863", timeout=3) as resp3:
            data3 = json.loads(resp3.read().decode("utf-8"))
            assert data3["count"] >= 3
            assert data3["flashing_evaluation"]["can_flash_esphome_tasmota"] is True

        # 4. GET /status
        with urllib.request.urlopen(f"{base_url}/status", timeout=3) as resp4:
            data4 = json.loads(resp4.read().decode("utf-8"))
            assert data4["access_cloud_hits"] == 1
            assert data4["bimqtt_hits"] == 1
    finally:
        server.stop()
