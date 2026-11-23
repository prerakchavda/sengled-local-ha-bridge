"""Unit tests for Sengled RC4 Wi-Fi onboarding encryption, TLS certs, and AP provisioning."""

import json
from pathlib import Path
import pytest

from sengled_bridge.crypto import (
    KEY_STR,
    decrypt_wifi_payload,
    encrypt_wifi_payload,
    generate_self_signed_certs,
)
from sengled_bridge.provisioning import (
    build_end_config_request,
    build_set_params_request,
    build_start_config_request,
    parse_set_params_response,
)


def test_rc4_encrypt_decrypt_roundtrip():
    sample = {
        "name": "setParamsRequest",
        "totalStep": 1,
        "curStep": 1,
        "payload": {
            "userID": "618",
            "appServerDomain": "http://192.168.1.50:8080/life2/device/accessCloud.json",
            "jbalancerDomain": "http://192.168.1.50:8080/jbalancer/new/bimqtt",
            "timeZone": "UTC",
            "routerInfo": {"ssid": "MyHome24GHz", "password": "secretpassword"},
        },
    }
    encrypted_b64 = encrypt_wifi_payload(sample)
    assert isinstance(encrypted_b64, str)
    assert "MyHome24GHz" not in encrypted_b64

    decrypted = decrypt_wifi_payload(encrypted_b64)
    assert decrypted == sample


def test_build_set_params_request_ascii_and_non_ascii():
    params, encrypted = build_set_params_request(
        ssid="HomeNetwork",
        password="pass123",
        server_ip="10.0.1.31",
        http_port=54448,
    )
    assert params["payload"]["appServerDomain"] == "http://10.0.1.31:54448/life2/device/accessCloud.json"
    assert params["payload"]["jbalancerDomain"] == "http://10.0.1.31:54448/jbalancer/new/bimqtt"
    assert params["payload"]["routerInfo"] == {"ssid": "HomeNetwork", "password": "pass123"}
    assert decrypt_wifi_payload(encrypted) == params

    # Non-ASCII SSID requires BSSID
    with pytest.raises(ValueError):
        build_set_params_request("CaféWiFi", "pass123", "10.0.1.31")

    non_ascii_params, _ = build_set_params_request(
        ssid="CaféWiFi",
        password="pass123",
        server_ip="10.0.1.31",
        bssid="aa:bb:cc:11:22:33",
    )
    assert non_ascii_params["payload"]["routerInfo"] == {
        "ssid": "",
        "bssid": "AA:BB:CC:11:22:33",
        "password": "pass123",
    }


def test_parse_set_params_response_plaintext_and_encrypted():
    ack = {"name": "setParamsResponse", "payload": {"result": True}}
    assert parse_set_params_response(json.dumps(ack)) == ack

    enc_ack = encrypt_wifi_payload(ack)
    assert parse_set_params_response(enc_ack) == ack


def test_handshake_request_schemas():
    start = build_start_config_request()
    assert start["name"] == "startConfigRequest"
    assert start["payload"] == {"protocol": 1}

    end = build_end_config_request()
    assert end["name"] == "endConfigRequest"


def test_generate_self_signed_certs(tmp_path: Path):
    certs = generate_self_signed_certs(
        cert_dir=tmp_path,
        common_name="sengled.local",
        server_ip="192.168.1.100",
    )
    for key in ("ca_key", "ca_cert", "server_key", "server_cert"):
        assert certs[key].exists()
        assert certs[key].stat().st_size > 200
    assert b"BEGIN CERTIFICATE" in certs["server_cert"].read_bytes()
