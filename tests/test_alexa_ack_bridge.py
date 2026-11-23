"""Tests for Amazon 'Works with Alexa Only' (ACK & Echo-Paired) Multi-Path Bridge."""

from __future__ import annotations

import json
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from sengled_bridge.alexa_ack_bridge import (
    AlexaACKController,
    alexa_color_name_to_rgb,
    alexa_hsv_to_rgb,
    build_alexa_voice_command_and_ha_service_payload,
    build_behaviors_smarthome_batch_payload,
    build_graphql_feature_control_requests,
    build_phoenix_state_put_payload,
    dsn_or_endpoint_to_mac,
    kelvin_to_alexa_color_temp_name,
    parse_amazon_ack_ffs_barcode,
    rgb_to_nearest_alexa_color_name,
)
from sengled_bridge.bridge import SengledHomeAssistantBridge
from sengled_bridge.http_server import SengledDiscoveryHTTPServer


def test_dsn_or_endpoint_to_mac() -> None:
    # Explicit MAC is preserved and normalized
    assert dsn_or_endpoint_to_mac("f0f0a4112233") == "F0:F0:A4:11:22:33"
    assert dsn_or_endpoint_to_mac("F0:F0:A4:AA:BB:CC") == "F0:F0:A4:AA:BB:CC"

    # Amazon DSN or Alexa endpointId produces deterministic F0:F0:A4:XX:YY:ZZ MAC
    mac1 = dsn_or_endpoint_to_mac("G09123456789ABCD")
    mac2 = dsn_or_endpoint_to_mac("g09123456789abcd")
    assert mac1 == mac2
    assert mac1.startswith("F0:F0:A4:")
    assert len(mac1) == 17


def test_alexa_color_and_kelvin_mapping() -> None:
    assert rgb_to_nearest_alexa_color_name(255, 0, 0) == "red"
    assert rgb_to_nearest_alexa_color_name(0, 255, 0) == "green"
    assert rgb_to_nearest_alexa_color_name(0, 0, 255) == "blue"
    assert rgb_to_nearest_alexa_color_name(255, 20, 145) == "deep_pink"
    assert rgb_to_nearest_alexa_color_name(30, 143, 255) == "dodger_blue"
    assert alexa_color_name_to_rgb("deep_pink") == (255, 20, 145)

    r, g, b = alexa_hsv_to_rgb(0.0, 1.0, 1.0)
    assert (r, g, b) == (255, 0, 0)

    assert kelvin_to_alexa_color_temp_name(2200) == "warm_white"
    assert kelvin_to_alexa_color_temp_name(2700) == "soft_white"
    assert kelvin_to_alexa_color_temp_name(4000) == "white"
    assert kelvin_to_alexa_color_temp_name(5500) == "daylight_white"
    assert kelvin_to_alexa_color_temp_name(6500) == "cool_white"


def test_parse_amazon_ack_ffs_barcodes() -> None:
    # 1. JSON FFS barcode
    json_info = parse_amazon_ack_ffs_barcode(
        '{"dsn":"G091112223334445","model":"13aSB-A800ST-Q1T","pin":"987654"}'
    )
    assert json_info["dsn"] == "G091112223334445"
    assert json_info["model"] == "13ASB-A800ST-Q1T"
    assert json_info["setup_pin"] == "987654"
    assert json_info["mac"].startswith("F0:F0:A4:")

    # 2. Key-value FFS barcode with Soft White model
    kv_info = parse_amazon_ack_ffs_barcode(
        "DSN:G099998887776665;MAC:F0F0A4123456;MODEL:13aSB-A806ST-Q1R_NA"
    )
    assert kv_info["dsn"] == "G099998887776665"
    assert kv_info["mac"] == "F0:F0:A4:12:34:56"
    assert kv_info["model"] == "13ASB-A806ST-Q1R"

    # 3. Switch / dimmer model
    sw_info = parse_amazon_ack_ffs_barcode("WS30-01")
    assert sw_info["model"] == "WP52-2"


def test_graphql_behaviors_phoenix_and_voice_payload_builders() -> None:
    endpoint_id = "amzn1.alexa.endpoint.abcd-1234"
    ha_cmd = {
        "state": "ON",
        "brightness": 128,
        "color": {"r": 255, "g": 20, "b": 145},
    }

    gql_reqs = build_graphql_feature_control_requests(endpoint_id, ha_cmd)
    assert gql_reqs[0]["featureOperationName"] == "turnOn"
    assert gql_reqs[1]["featureOperationName"] == "setBrightness"
    assert gql_reqs[1]["payload"]["brightness"] == 50

    batch = build_behaviors_smarthome_batch_payload(endpoint_id, ha_cmd)
    seq = json.loads(batch["sequenceJson"])
    ops = seq["startNode"]["nodesToExecute"][0]["operationPayload"]["operations"]
    assert {"type": "turnOn"} in ops
    assert {"type": "setBrightness", "brightness": 50} in ops
    assert {"type": "setColor", "colorName": "deep_pink"} in ops

    phoenix = build_phoenix_state_put_payload(endpoint_id, ha_cmd)
    actions = [r["parameters"] for r in phoenix["controlRequests"]]
    assert {"action": "setColor", "colorName": "deep_pink"} in actions

    voice = build_alexa_voice_command_and_ha_service_payload("Desk Light", ha_cmd)
    assert "set Desk Light to deep pink" in voice["combined_voice_command"]
    assert "set Desk Light brightness to 50 percent" in voice["combined_voice_command"]
    assert (
        voice["ha_alexa_media_service_call"]["service_data"]["media_content_type"]
        == "custom"
    )


def test_alexa_graphql_auto_discovery_and_live_dispatch() -> None:
    recorded_http: List[Tuple[str, str, Dict[str, Any]]] = []

    def mock_http_transport(
        method: str,
        url: str,
        headers: Dict[str, str],
        body: Optional[bytes] = None,
    ) -> Dict[str, Any]:
        req_json = json.loads(body.decode("utf-8")) if body else {}
        recorded_http.append((method, url, req_json))

        if "query Endpoints" in str(req_json.get("query", "")):
            return {
                "data": {
                    "endpoints": {
                        "items": [
                            {
                                "id": "amzn1.alexa.endpoint.basics-rgb-1",
                                "friendlyName": "Amazon Basics Bedroom Light",
                                "displayCategories": {"primary": {"value": "LIGHT"}},
                                "serialNumber": {"value": {"text": "G09123456789ABCD"}},
                                "enablement": "ENABLED",
                                "model": {"value": {"text": "13aSB-A800ST-Q1T"}},
                                "manufacturer": {"value": {"text": "Amazon Basics"}},
                                "features": [
                                    {
                                        "name": "power",
                                        "operations": [{"name": "turnOn"}, {"name": "turnOff"}],
                                        "properties": [{"name": "powerState", "powerStateValue": "ON"}],
                                    },
                                    {
                                        "name": "brightness",
                                        "operations": [{"name": "setBrightness"}],
                                        "properties": [{"name": "brightness", "brightnessStateValue": 80}],
                                    },
                                    {
                                        "name": "color",
                                        "operations": [{"name": "setColor"}],
                                        "properties": [
                                            {
                                                "name": "color",
                                                "colorStateValue": {
                                                    "hue": 240.0,
                                                    "saturation": 1.0,
                                                    "brightness": 1.0,
                                                },
                                            }
                                        ],
                                    },
                                    {
                                        "name": "colorTemperature",
                                        "operations": [{"name": "setColorTemperature"}],
                                        "properties": [
                                            {
                                                "name": "colorTemperatureInKelvin",
                                                "colorTemperatureInKelvinStateValue": 2700,
                                            }
                                        ],
                                    },
                                ],
                            }
                        ]
                    }
                }
            }
        return {
            "data": {
                "setEndpointFeatures": {
                    "featureControlResponses": [
                        {"endpointId": "amzn1.alexa.endpoint.basics-rgb-1", "featureOperationName": "turnOn"}
                    ],
                    "errors": [],
                }
            }
        }

    ctrl = AlexaACKController(
        alexa_cookie="session-id=123; at-main=abc; csrf=999888",
        alexa_domain="amazon.com",
        http_transport=mock_http_transport,
    )
    assert ctrl.alexa_csrf == "999888"

    discovered = ctrl.discover_from_alexa_graphql()
    assert len(discovered) == 1
    bulb = discovered[0]
    assert bulb.name == "Amazon Basics Bedroom Light"
    assert bulb.model == "13ASB-A800ST-Q1T"
    assert bulb.is_on is True
    assert bulb.ha_brightness == 204
    assert bulb.rgb == (0, 0, 255)

    # Dispatch an RGB + Brightness command and verify both GraphQL and Behaviors Batch were called
    recorded_http.clear()
    dispatch_res = ctrl.dispatch_ha_command(
        bulb.mac,
        {"state": "ON", "brightness": 255, "color": {"r": 255, "g": 212, "b": 0}},
    )
    assert dispatch_res["cloud_dispatched"] is True
    assert dispatch_res["alexa_color_name"] == "gold"
    assert len(recorded_http) == 2
    assert recorded_http[0][1].endswith("/nexus/v1/graphql")
    assert recorded_http[1][1].endswith("/api/behaviors/preview")


def test_bridge_and_http_hue_v1_emulator_end_to_end() -> None:
    ha_messages: List[Tuple[str, str, bool]] = []

    bridge = SengledHomeAssistantBridge(
        publish_ha_callback=lambda t, p, r: ha_messages.append((t, p, r)),
    )

    # 1. Register an Amazon Basics "Works with Alexa Only" bulb in the bridge
    bulb = bridge.register_ack_light_in_ha(
        identifier="G09123456789ABCD",
        model="13ASB-A800ST-Q1T",
        friendly_name="Kitchen Alexa Bulb",
    )
    disc_msgs = [m for m in ha_messages if m[0].endswith("/config")]
    assert len(disc_msgs) == 1
    disc_json = json.loads(disc_msgs[0][1])
    assert disc_json["device"]["manufacturer"] == "Amazon Basics"
    assert set(disc_json["supported_color_modes"]) == {"color_temp", "rgb"}

    # 2. Send a Home Assistant command to `sengled_bridge/light/{slug}/set`
    ha_messages.clear()
    slug = bulb.mac.lower().replace(":", "")
    res = bridge.handle_ha_command_message(
        f"sengled_bridge/light/{slug}/set",
        json.dumps({"state": "ON", "brightness": 191, "color_temp_kelvin": 2200}),
    )
    assert res is not None
    assert res["transport"] == "amazon_alexa_ack"
    # Verify both HA state topic and MQTT voice relay topic were emitted
    emitted_topics = {m[0] for m in ha_messages}
    assert f"sengled_bridge/light/{slug}/state" in emitted_topics
    assert f"sengled_bridge/alexa_ack/{slug}/command" in emitted_topics

    # 3. Verify HTTP server Local Philips Hue V1 Echo Emulator & ACK API endpoints
    server = SengledDiscoveryHTTPServer(
        mqtt_host="192.168.1.100",
        mqtt_tls_port=8883,
        http_port=0,
        bridge=bridge,
    )
    port = server.start()
    try:
        # GET /description.xml
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/description.xml") as r:
            xml_text = r.read().decode("utf-8")
            assert "Philips hue bridge" in xml_text
            assert "192.168.1.100" in xml_text

        # POST /api (Echo pairing)
        req_pair = urllib.request.Request(
            f"http://127.0.0.1:{port}/api",
            data=b'{"devicetype":"echo#local"}',
            method="POST",
        )
        with urllib.request.urlopen(req_pair) as r:
            pair_data = json.loads(r.read().decode("utf-8"))
            assert pair_data[0]["success"]["username"] == "sengledlocalhabridge"

        # GET /api/sengledlocalhabridge/lights
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/sengledlocalhabridge/lights"
        ) as r:
            lights_data = json.loads(r.read().decode("utf-8"))
            assert "1" in lights_data
            assert lights_data["1"]["name"] == "Kitchen Alexa Bulb"

        # PUT /api/sengledlocalhabridge/lights/1/state (Echo local state sync -> HA MQTT)
        ha_messages.clear()
        req_put = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/sengledlocalhabridge/lights/1/state",
            data=json.dumps({"on": True, "bri": 254, "hue": 0, "sat": 254}).encode("utf-8"),
            method="PUT",
        )
        with urllib.request.urlopen(req_put) as r:
            put_resp = json.loads(r.read().decode("utf-8"))
            assert any("/lights/1/state/on" in item.get("success", {}) for item in put_resp)

        assert bulb.rgb == (255, 0, 0)
        assert any(m[0] == f"sengled_bridge/light/{slug}/state" for m in ha_messages)
    finally:
        server.stop()
