"""Unit tests for Sengled Wi-Fi TLS MQTT and UDP protocol encoding/decoding."""

import json

from sengled_bridge.wifi_protocol import (
    SengledWiFiBulbState,
    build_udp_brightness,
    build_udp_color,
    build_udp_colortemp,
    build_udp_search_devices,
    build_udp_switch,
    decode_sengled_mqtt_payload,
    encode_brightness_command,
    encode_color_command,
    encode_color_temp_command,
    encode_switch_command,
    ha_brightness_to_sengled,
    kelvin_to_sengled_cct_pct,
    parse_mqtt_topic,
    parse_sengled_color,
    sengled_brightness_to_ha,
    sengled_cct_to_kelvin,
)


def test_parse_mqtt_topic():
    assert parse_mqtt_topic("wifielement/40:43:18:2f:74:c9/status") == (
        "40:43:18:2F:74:C9",
        "status",
    )
    assert parse_mqtt_topic("wifielement/c/status") == ("c", "status")
    assert parse_mqtt_topic("homeassistant/light/foo/config") is None


def test_decode_mqtt_payload_plain_and_os_prefix():
    raw_plain = '[{"dn":"40:43:18:2F:74:C9","type":"switch","value":"1","time":"50"}]'
    records = decode_sengled_mqtt_payload(raw_plain)
    assert len(records) == 1
    assert records[0]["type"] == "switch"
    assert records[0]["value"] == "1"

    raw_os = 'Os$[{"dn":"80:A0:36:E1:8E:B8","type":"brightness","value":"75","time":1662036404644}]'
    records_os = decode_sengled_mqtt_payload(raw_os)
    assert len(records_os) == 1
    assert records_os[0]["type"] == "brightness"
    assert records_os[0]["value"] == "75"


def test_bulb_state_apply_status_records():
    bulb = SengledWiFiBulbState(mac="40:43:18:2F:74:C9")
    status_batch = [
        {"dn": "40:43:18:2F:74:C9", "type": "brightness", "value": "50", "time": "49"},
        {"dn": "40:43:18:2F:74:C9", "type": "version", "value": "V1.0.0.4", "time": "49"},
        {"dn": "40:43:18:2F:74:C9", "type": "switch", "value": "1", "time": "49"},
        {"dn": "40:43:18:2F:74:C9", "type": "typeCode", "value": "W31-N11", "time": "49"},
        {"dn": "40:43:18:2F:74:C9", "type": "identifyNO", "value": "ESP8266", "time": "49"},
        {"dn": "40:43:18:2F:74:C9", "type": "ip", "value": "192.168.0.24", "time": "49"},
        {"dn": "40:43:18:2F:74:C9", "type": "deviceRssi", "value": "-55", "time": "49"},
        {"dn": "40:43:18:2F:74:C9", "type": "color", "value": "255:128:0", "time": "50"},
    ]
    assert bulb.apply_status_records(status_batch) is True
    assert bulb.is_on is True
    assert bulb.brightness_pct == 50
    assert bulb.ha_brightness == 128
    assert bulb.type_code == "W31-N11"
    assert bulb.identify_no == "ESP8266"
    assert bulb.ip_address == "192.168.0.24"
    assert bulb.rssi == -55
    assert bulb.rgb == (255, 128, 0)
    assert bulb.color_mode == "rgb"


def test_encode_commands():
    mac = "80:A0:36:E1:8E:B8"

    sw_cmd = json.loads(encode_switch_command(mac, True, timestamp_ms=1700000000000))
    assert sw_cmd == [{"dn": mac, "type": "switch", "value": "1", "time": 1700000000000}]

    bri_cmd = json.loads(encode_brightness_command(mac, 75, timestamp_ms=1700000000000))
    assert bri_cmd == [{"dn": mac, "type": "brightness", "value": "75", "time": 1700000000000}]

    col_cmd = json.loads(encode_color_command(mac, 255, 0, 128, timestamp_ms=1700000000000))
    assert col_cmd == [{"dn": mac, "type": "color", "value": "255:0:128", "time": 1700000000000}]

    col_hex = json.loads(encode_color_command(mac, 255, 0, 128, use_hex=True, timestamp_ms=1700000000000))
    assert col_hex[0]["value"] == "FF0080"

    # CRITICAL: colorTemperature MUST include switch="1" in the same command list
    cct_cmd = json.loads(encode_color_temp_command(mac, 4600, timestamp_ms=1700000000000))
    assert len(cct_cmd) == 2
    assert cct_cmd[0] == {"dn": mac, "type": "colorTemperature", "value": "50", "time": 1700000000000}
    assert cct_cmd[1] == {"dn": mac, "type": "switch", "value": "1", "time": 1700000000000}


def test_scale_and_color_conversions():
    assert ha_brightness_to_sengled(0) == 0
    assert ha_brightness_to_sengled(255) == 100
    assert sengled_brightness_to_ha(100) == 255

    assert kelvin_to_sengled_cct_pct(2700) == 0
    assert kelvin_to_sengled_cct_pct(6500) == 100
    assert sengled_cct_to_kelvin(0) == 2700
    assert sengled_cct_to_kelvin(100) == 6500
    assert sengled_cct_to_kelvin(4000) == 4000

    assert parse_sengled_color("255:0:64") == (255, 0, 64)
    assert parse_sengled_color("FF0040") == (255, 0, 64)


def test_udp_payload_builders():
    assert json.loads(build_udp_search_devices()) == {"func": "search_devices", "param": {}}
    assert json.loads(build_udp_switch(True)) == {"func": "set_device_switch", "param": {"switch": 1}}
    assert json.loads(build_udp_brightness(42)) == {"func": "set_device_brightness", "param": {"brightness": 42}}
    assert json.loads(build_udp_color(10, 20, 30)) == {
        "func": "set_device_color",
        "param": {"red": 10, "green": 20, "blue": 30},
    }
    assert json.loads(build_udp_colortemp(80)) == {
        "func": "set_device_colortemp",
        "param": {"colorTemperature": 80},
    }
