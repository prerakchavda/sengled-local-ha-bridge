"""Unit tests for Sengled Bluetooth SIG Mesh & BLE controller."""

from pathlib import Path
import struct

from sengled_bridge.ble_controller import (
    MeshSequenceTracker,
    OPCODE_GENERIC_ONOFF_STATUS,
    OPCODE_LIGHT_CTL_STATUS,
    OPCODE_LIGHT_HSL_STATUS,
    OPCODE_LIGHT_LIGHTNESS_STATUS,
    PROXY_FILTER_BLACKLIST,
    PROXY_PDU_NETWORK,
    SengledBLEController,
    build_generic_onoff_set,
    build_light_ctl_set,
    build_light_hsl_set,
    build_light_lightness_set,
    build_proxy_filter_exclusion_list_message,
    decode_proxy_pdu,
    encode_access_opcode,
    encode_proxy_pdu,
    mesh_hsl_to_rgb,
    parse_mesh_access_status,
    rgb_to_mesh_hsl,
)


def test_proxy_pdu_and_exclusion_filter():
    filter_msg = build_proxy_filter_exclusion_list_message()
    assert filter_msg == bytes([0x00, PROXY_FILTER_BLACKLIST])

    pdu = encode_proxy_pdu(PROXY_PDU_NETWORK, b"\x82\x02\x01\x07")
    sar, pdu_type, body = decode_proxy_pdu(pdu)
    assert sar == 0
    assert pdu_type == PROXY_PDU_NETWORK
    assert body == b"\x82\x02\x01\x07"


def test_mesh_sequence_tracker_persists_floor_across_restarts(tmp_path: Path):
    seq_file = tmp_path / "mesh_seq.json"
    tracker1 = MeshSequenceTracker(storage_path=seq_file, initial_seq=1, stride=16)
    seq1, tid1 = tracker1.next_seq_and_tid()
    assert seq1 == 1
    assert tid1 == 0

    # Simulate restart: tracker2 must resume ABOVE tracker1's reserved floor
    tracker2 = MeshSequenceTracker(storage_path=seq_file, initial_seq=1, stride=16)
    seq2, _ = tracker2.next_seq_and_tid()
    assert seq2 > seq1 + 10


def test_mesh_lighting_opcodes_and_status_parsing():
    on_set = build_generic_onoff_set(True, tid=5)
    assert on_set == b"\x82\x02\x01\x05"

    lightness_set = build_light_lightness_set(32768, tid=6)
    assert lightness_set[:2] == b"\x82\x4c"

    ctl_set = build_light_ctl_set(65535, 4000, delta_uv=0, tid=7)
    assert ctl_set[:2] == b"\x82\x5e"

    hsl_set = build_light_hsl_set(32768, 21845, 65535, tid=8)
    assert hsl_set[:2] == b"\x82\x76"

    # Decode status packets
    on_status = parse_mesh_access_status(
        encode_access_opcode(OPCODE_GENERIC_ONOFF_STATUS) + b"\x01\x01"
    )
    assert on_status is not None
    assert on_status["is_on"] is True

    light_status = parse_mesh_access_status(
        encode_access_opcode(OPCODE_LIGHT_LIGHTNESS_STATUS) + struct.pack("<H", 65535)
    )
    assert light_status is not None
    assert light_status["ha_brightness"] == 255

    ctl_status = parse_mesh_access_status(
        encode_access_opcode(OPCODE_LIGHT_CTL_STATUS) + struct.pack("<HH", 32768, 3500)
    )
    assert ctl_status is not None
    assert ctl_status["color_temp_kelvin"] == 3500

    l_u16, h_u16, s_u16 = rgb_to_mesh_hsl(255, 0, 0)
    hsl_status = parse_mesh_access_status(
        encode_access_opcode(OPCODE_LIGHT_HSL_STATUS)
        + struct.pack("<HHH", l_u16, h_u16, s_u16)
    )
    assert hsl_status is not None
    r, g, b = hsl_status["rgb"]
    assert r > 240 and g < 15 and b < 15


def test_ble_controller_state_and_notifications(tmp_path: Path):
    events = []
    ctrl = SengledBLEController(
        seq_storage_path=tmp_path / "seq.json",
        on_state_change=lambda b: events.append((b.mac, b.is_on, b.ha_brightness)),
    )
    mac = "EC:21:E5:11:22:33"
    pdu = ctrl.build_turn_on_off_pdu(mac, True)
    assert len(pdu) == 5
    assert ctrl.bulbs[mac].is_on is True
    assert events[-1] == (mac, True, 255)

    # Incoming notification turning bulb OFF
    notif_pdu = encode_proxy_pdu(
        PROXY_PDU_NETWORK,
        encode_access_opcode(OPCODE_GENERIC_ONOFF_STATUS) + b"\x00",
    )
    ctrl.handle_incoming_proxy_notification(mac, notif_pdu)
    assert ctrl.bulbs[mac].is_on is False
