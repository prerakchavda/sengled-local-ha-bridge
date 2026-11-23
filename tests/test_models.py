"""Unit tests for Sengled model & FCC ID catalog and fingerprinting."""

from sengled_bridge.models import (
    BLE_MESH_PROVISIONING_SERVICE_UUID,
    BLE_MESH_PROXY_SERVICE_UUID,
    ColorCapability,
    MODEL_CATALOG,
    RADIO_MODULES,
    RadioProtocol,
    TELINK_MANUFACTURER_ID,
    evaluate_esphome_tasmota_vs_stock,
    identify_device_by_model_or_fcc,
    identify_from_ble_advertisement,
    identify_from_status_attributes,
)


def test_catalog_contains_all_major_fcc_modules():
    expected_modules = {
        "WF861",
        "WF862",
        "WF863",
        "WF864",
        "WF866",
        "WF867",
        "SLMB01",
        "BT001",
        "BT002",
        "BT003",
        "BT004",
        "BT006",
    }
    assert expected_modules.issubset(set(RADIO_MODULES.keys()))
    assert len(MODEL_CATALOG) >= 25


def test_lookup_by_model_and_fcc_id():
    wf863_matches = identify_device_by_model_or_fcc("2AGN8-WF863")
    wf863_models = {m.model for m in wf863_matches}
    assert {"W31-N11", "W31-N15", "W31-N13H"}.issubset(wf863_models)

    w21 = identify_device_by_model_or_fcc("W21-N13")
    assert len(w21) == 1
    assert w21[0].protocol == RadioProtocol.WIFI_MQTT_UDP
    assert w21[0].capability == ColorCapability.RGBW

    b11 = identify_device_by_model_or_fcc("B11-N1E")
    assert len(b11) == 1
    assert b11[0].protocol == RadioProtocol.BLE_SIG_MESH
    assert "2AGN8-BT002" in b11[0].fcc_ids

    b1f = identify_device_by_model_or_fcc("2AGN8-B1FN5E")
    assert len(b1f) == 1
    assert b1f[0].model == "B1F-N5E"


def test_fingerprint_from_mqtt_status_attributes():
    attrs = {
        "typeCode": "W31-N11",
        "identifyNO": "ESP8266",
        "supportAttributes": "brightness",
        "version": "V1.0.0.4",
    }
    fp = identify_from_status_attributes(attrs)
    assert fp["model"] == "W31-N11"
    assert fp["is_esp8266"] is True
    assert fp["capability"] == ColorCapability.DIMMABLE_WHITE
    assert fp["flashing_evaluation"]["can_flash_esphome_tasmota"] is True


def test_evaluate_esphome_vs_stock():
    esp_eval = evaluate_esphome_tasmota_vs_stock("W31-N15", "ESP8266")
    assert esp_eval["can_flash_esphome_tasmota"] is True

    mx_eval = evaluate_esphome_tasmota_vs_stock("W21-N13", "EMW3091")
    assert mx_eval["can_flash_esphome_tasmota"] is False
    assert mx_eval["recommendation"] == "stock_firmware_bridge"


def test_fingerprint_ble_advertisement():
    unprov = identify_from_ble_advertisement(
        local_name="Sengled",
        service_uuids=[BLE_MESH_PROVISIONING_SERVICE_UUID],
        manufacturer_data={TELINK_MANUFACTURER_ID: b"\x01\x02"},
        mac_address="EC:21:E5:AA:BB:CC",
    )
    assert unprov["is_sengled_ble"] is True
    assert unprov["mesh_state"] == "unprovisioned_pb_gatt_0x1827"
    assert unprov["is_telink_chip"] is True

    prov = identify_from_ble_advertisement(
        local_name=None,
        service_uuids=[BLE_MESH_PROXY_SERVICE_UUID],
        manufacturer_data={TELINK_MANUFACTURER_ID: b"\x00"},
        mac_address="A4:C1:38:11:22:33",
    )
    assert prov["is_sengled_ble"] is True
    assert prov["mesh_state"] == "provisioned_proxy_0x1828"
