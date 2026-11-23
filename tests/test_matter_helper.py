"""Unit tests for Matter QR / manual pairing code decoder and Amazon Basics ACK classifier."""

from sengled_bridge.matter_helper import (
    classify_and_decode_smart_bulb_code,
    decode_matter_manual_code,
    decode_matter_qr_code,
    encode_matter_qr_code,
    generate_manual_pairing_code_11,
    verify_verhoeff_checksum,
)
from sengled_bridge.models import RadioProtocol, identify_device_by_model_or_fcc


def test_encode_and_decode_matter_qr_roundtrip():
    qr = encode_matter_qr_code(
        discriminator=2976,
        passcode=20202021,
        vendor_id=0x131B,  # Amazon Basics
        product_id=0x0042,
        discovery_mask=0b010,  # BLE
    )
    assert qr.startswith("MT:")

    decoded = decode_matter_qr_code(qr)
    assert decoded.vendor_id == 0x131B
    assert decoded.vendor_name == "Amazon / Amazon Basics"
    assert decoded.product_id == 0x0042
    assert decoded.discriminator == 2976
    assert decoded.passcode == 20202021
    assert "BLE" in decoded.discovery_capabilities
    assert decoded.valid_checksum is True

    # Verify the generated 11-digit manual code passes Verhoeff check and decodes to the same passcode
    digits_only = decoded.manual_pairing_code_11.replace("-", "")
    assert len(digits_only) == 11
    assert verify_verhoeff_checksum(digits_only) is True

    manual_decoded = decode_matter_manual_code(decoded.manual_pairing_code_11)
    assert manual_decoded.passcode == 20202021
    assert manual_decoded.short_discriminator == (2976 >> 8)
    assert manual_decoded.valid_checksum is True


def test_classify_matter_vs_amazon_ack():
    qr = encode_matter_qr_code(discriminator=3840, passcode=34567890, vendor_id=0x1344)
    matter_res = classify_and_decode_smart_bulb_code(qr)
    assert matter_res["is_matter"] is True
    assert matter_res["classification"] == "matter_native_local"
    assert matter_res["ha_service_call"]["command"] == "commission_with_code"

    manual_11 = generate_manual_pairing_code_11(3840, 34567890)
    manual_res = classify_and_decode_smart_bulb_code(manual_11)
    assert manual_res["is_matter"] is True
    assert manual_res["payload"]["passcode"] == 34567890

    ack_res = classify_and_decode_smart_bulb_code("13aSB-A800ST-Q1T")
    assert ack_res["is_matter"] is False
    assert ack_res["classification"] == "amazon_ack_alexa_only"


def test_amazon_basics_models_in_catalog():
    ab_matter = identify_device_by_model_or_fcc("AB-MATTER-A19")
    assert len(ab_matter) == 1
    assert ab_matter[0].protocol == RadioProtocol.WIFI_MATTER

    ab_ack = identify_device_by_model_or_fcc("B0C332SMK8")
    assert len(ab_ack) == 1
    assert ab_ack[0].protocol == RadioProtocol.WIFI_ALEXA_ACK
    assert ab_ack[0].model == "13ASB-A800ST-Q1T"

    w41 = identify_device_by_model_or_fcc("W41-N15")
    assert len(w41) == 1
    assert w41[0].protocol == RadioProtocol.WIFI_MATTER
