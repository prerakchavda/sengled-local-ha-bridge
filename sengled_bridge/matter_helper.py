"""
Matter (CHIP) QR Code / Manual Pairing Code Decoder & Amazon Basics / Sengled
Matter Commissioning Helper for Home Assistant.

Supports:
1. Decoding Matter `MT:...` Base38 QR code strings into:
   - Version, Vendor ID (VID), Product ID (PID), Custom Flow,
     Discovery Capabilities (SoftAP, BLE, OnNetwork),
     12-bit Discriminator, and 27-bit Setup Passcode (PIN).
2. Generating the 11-digit Matter Manual Pairing Code (with Verhoeff checksum)
   from a decoded `MT:...` QR code so users can type it directly into Home Assistant
   even if the camera scan fails.
3. Decoding and validating 11-digit or 21-digit Matter Manual Pairing Codes
   (verifying the Verhoeff check digit, extracting the 4-bit short discriminator
   and 27-bit setup passcode).
4. Classifying Amazon Basics & Sengled barcodes to distinguish:
   - Native Matter-over-Wi-Fi devices (`MT:...` or 11/21-digit pairing code)
   - Legacy "Works with Alexa Only" ACK (Alexa Connect Kit) Frustration-Free Setup
     2D barcodes (`13aSB-A800ST-Q1T`, `B0C332SMK8`, `WP52-2`, etc.).
5. Building Home Assistant `python-matter-server` WebSocket (`ws://<host>:5580/ws`)
   `commission_with_code` payloads.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# Matter Base38 alphabet (CSA Matter Specification Section 5.1.3)
BASE38_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-."
BASE38_MAP = {ch: idx for idx, ch in enumerate(BASE38_CHARS)}

# Verhoeff Checksum Tables (CSA Matter Specification Section 5.1.4.1)
_VERHOEFF_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_VERHOEFF_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)
_VERHOEFF_INV = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)

# Known CSA Matter Vendor IDs
KNOWN_MATTER_VENDORS: Dict[int, str] = {
    0x117C: "IKEA",
    0x100B: "Philips Hue (Signify)",
    0x131B: "Amazon / Amazon Basics",
    0x1217: "Amazon / Alexa Connect Kit (ACK)",
    0x1344: "Sengled Co., Ltd.",
    0x115F: "Leedarson (Amazon Basics OEM)",
    0xFFF1: "CSA Test Vendor (0xFFF1)",
}


def compute_verhoeff_check_digit(digits_str: str) -> str:
    """Compute the Verhoeff check digit for a numeric string."""
    c = 0
    for idx, ch in enumerate(reversed(digits_str)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[(idx + 1) % 8][int(ch)]]
    return str(_VERHOEFF_INV[c])


def verify_verhoeff_checksum(digits_with_check: str) -> bool:
    """Verify a numeric string ending with a Verhoeff check digit."""
    if not digits_with_check.isdigit() or len(digits_with_check) < 2:
        return False
    c = 0
    for idx, ch in enumerate(reversed(digits_with_check)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[idx % 8][int(ch)]]
    return c == 0


def base38_decode(encoded: str) -> bytes:
    """
    Decode a Matter Base38 string (without the `MT:` prefix) into raw bytes.
    Chunks of 5 characters -> 3 bytes; 4 characters -> 2 bytes; 2 characters -> 1 byte.
    """
    clean = encoded.strip().upper()
    if clean.startswith("MT:") or clean.startswith("MT-"):
        clean = clean[3:]

    out = bytearray()
    i = 0
    n = len(clean)
    while i < n:
        rem = n - i
        if rem >= 5:
            chunk = clean[i : i + 5]
            num_bytes = 3
            i += 5
        elif rem == 4:
            chunk = clean[i : i + 4]
            num_bytes = 2
            i += 4
        elif rem == 2:
            chunk = clean[i : i + 2]
            num_bytes = 1
            i += 2
        else:
            raise ValueError(f"Invalid Base38 chunk length ({rem}) in Matter QR code.")

        val = 0
        for ch in reversed(chunk):
            if ch not in BASE38_MAP:
                raise ValueError(f"Invalid Base38 character: {ch!r}")
            val = val * 38 + BASE38_MAP[ch]

        for b_idx in range(num_bytes):
            out.append((val >> (8 * b_idx)) & 0xFF)

    return bytes(out)


def base38_encode(raw: bytes) -> str:
    """Encode raw bytes into a Matter Base38 string (without `MT:` prefix)."""
    chars: List[str] = []
    i = 0
    n = len(raw)
    while i < n:
        rem = n - i
        if rem >= 3:
            val = raw[i] | (raw[i + 1] << 8) | (raw[i + 2] << 16)
            num_chars = 5
            i += 3
        elif rem == 2:
            val = raw[i] | (raw[i + 1] << 8)
            num_chars = 4
            i += 2
        else:
            val = raw[i]
            num_chars = 2
            i += 1

        for _ in range(num_chars):
            chars.append(BASE38_CHARS[val % 38])
            val //= 38

    return "".join(chars)


@dataclass
class MatterOnboardingPayload:
    """Decoded Matter onboarding payload from a QR code or Manual Pairing Code."""

    source_type: str  # "qr_code" or "manual_code"
    raw_code: str
    version: int
    vendor_id: Optional[int]
    vendor_name: Optional[str]
    product_id: Optional[int]
    custom_flow: int
    discovery_capabilities: List[str]
    discriminator: int
    short_discriminator: int
    passcode: int
    manual_pairing_code_11: str
    valid_checksum: bool


def generate_manual_pairing_code_11(discriminator_12bit: int, passcode_27bit: int) -> str:
    """
    Generate the standard 11-digit Matter Manual Pairing Code (`XXXX-XXX-XXXX`)
    from a 12-bit discriminator and 27-bit setup passcode.
    """
    short_disc = (discriminator_12bit >> 8) & 0x0F
    chunk1 = ((short_disc >> 2) & 0x03)  # 1 digit (0..3 for standard flow)
    chunk2 = ((short_disc & 0x03) << 14) | (passcode_27bit & 0x3FFF)  # 5 digits
    chunk3 = (passcode_27bit >> 14) & 0x1FFF  # 4 digits

    ten_digits = f"{chunk1:01d}{chunk2:05d}{chunk3:04d}"
    check = compute_verhoeff_check_digit(ten_digits)
    full = ten_digits + check
    return f"{full[:4]}-{full[4:7]}-{full[7:]}"


def encode_matter_qr_code(
    discriminator: int,
    passcode: int,
    vendor_id: int = 0x131B,
    product_id: int = 0x0001,
    discovery_mask: int = 0b010,  # BLE
    custom_flow: int = 0,
    version: int = 0,
) -> str:
    """
    Pack a Matter 88-bit onboarding payload into an `MT:...` QR code string.
    Bit layout (CSA Matter Spec Table 35):
      - bits 0..2   (3 bits)  : version (0)
      - bits 3..18  (16 bits) : vendor_id
      - bits 19..34 (16 bits) : product_id
      - bits 35..36 (2 bits)  : custom_flow
      - bits 37..44 (8 bits)  : discovery_capabilities bitmask (bit0=SoftAP, bit1=BLE, bit2=OnNetwork)
      - bits 45..56 (12 bits) : discriminator
      - bits 57..83 (27 bits) : passcode
      - bits 84..87 (4 bits)  : padding (0)
    """
    bits = (
        (version & 0x07)
        | ((vendor_id & 0xFFFF) << 3)
        | ((product_id & 0xFFFF) << 19)
        | ((custom_flow & 0x03) << 35)
        | ((discovery_mask & 0xFF) << 37)
        | ((discriminator & 0xFFF) << 45)
        | ((passcode & 0x7FFFFFF) << 57)
    )
    raw_11_bytes = bits.to_bytes(11, byteorder="little")
    return "MT:" + base38_encode(raw_11_bytes)


def decode_matter_qr_code(qr_str: str) -> MatterOnboardingPayload:
    """Decode an `MT:...` Matter QR code string into a `MatterOnboardingPayload`."""
    raw = base38_decode(qr_str)
    if len(raw) < 11:
        raise ValueError(f"Matter QR payload too short ({len(raw)} bytes; expected >= 11).")

    bits = int.from_bytes(raw[:11], byteorder="little")
    version = bits & 0x07
    vendor_id = (bits >> 3) & 0xFFFF
    product_id = (bits >> 19) & 0xFFFF
    custom_flow = (bits >> 35) & 0x03
    disc_mask = (bits >> 37) & 0xFF
    discriminator = (bits >> 45) & 0xFFF
    passcode = (bits >> 57) & 0x7FFFFFF

    caps: List[str] = []
    if disc_mask & 0x01:
        caps.append("SoftAP")
    if disc_mask & 0x02:
        caps.append("BLE")
    if disc_mask & 0x04:
        caps.append("OnNetwork (IP/mDNS)")

    manual_11 = generate_manual_pairing_code_11(discriminator, passcode)
    return MatterOnboardingPayload(
        source_type="qr_code",
        raw_code=qr_str.strip(),
        version=version,
        vendor_id=vendor_id,
        vendor_name=KNOWN_MATTER_VENDORS.get(vendor_id, f"Vendor 0x{vendor_id:04X}"),
        product_id=product_id,
        custom_flow=custom_flow,
        discovery_capabilities=caps or ["BLE", "OnNetwork"],
        discriminator=discriminator,
        short_discriminator=(discriminator >> 8) & 0x0F,
        passcode=passcode,
        manual_pairing_code_11=manual_11,
        valid_checksum=True,
    )


def decode_matter_manual_code(code_str: str) -> MatterOnboardingPayload:
    """
    Decode an 11-digit (`XXXX-XXX-XXXX`) or 21-digit Matter Manual Pairing Code.
    """
    digits = "".join(ch for ch in code_str if ch.isdigit())
    if len(digits) not in (11, 21):
        raise ValueError("Matter manual pairing code must be 11 or 21 digits.")

    checksum_ok = verify_verhoeff_checksum(digits)
    chunk1 = int(digits[0])
    chunk2 = int(digits[1:6])
    chunk3 = int(digits[6:10])

    custom_flow = 1 if chunk1 >= 4 else 0
    short_disc = ((chunk1 & 0x03) << 2) | ((chunk2 >> 14) & 0x03)
    passcode = (chunk2 & 0x3FFF) | (chunk3 << 14)

    vendor_id: Optional[int] = None
    product_id: Optional[int] = None
    if len(digits) == 21:
        vendor_id = int(digits[10:15])
        product_id = int(digits[15:20])

    formatted_11 = f"{digits[:4]}-{digits[4:7]}-{digits[7:11]}"
    return MatterOnboardingPayload(
        source_type="manual_code",
        raw_code=code_str.strip(),
        version=0,
        vendor_id=vendor_id,
        vendor_name=KNOWN_MATTER_VENDORS.get(vendor_id) if vendor_id else None,
        product_id=product_id,
        custom_flow=custom_flow,
        discovery_capabilities=["BLE", "OnNetwork (IP/mDNS)"],
        discriminator=short_disc << 8,
        short_discriminator=short_disc,
        passcode=passcode,
        manual_pairing_code_11=formatted_11,
        valid_checksum=checksum_ok,
    )


def classify_and_decode_smart_bulb_code(code_or_barcode: str) -> Dict[str, Any]:
    """
    Inspect a scanned QR code, pairing code, or model/barcode from an Amazon Basics
    or Sengled bulb and classify whether it is:
      1. A native Matter device (`MT:...` or 11/21-digit code)
      2. A legacy "Works with Alexa Only" ACK device (e.g., `13aSB-A800ST-Q1T`, FFS 2D barcode)
    """
    raw = code_or_barcode.strip()
    upper = raw.upper()

    # Case 1: Matter QR code (`MT:...`)
    if upper.startswith("MT:") or upper.startswith("MT-"):
        decoded = decode_matter_qr_code(raw)
        return {
            "classification": "matter_native_local",
            "is_matter": True,
            "summary": "Native Matter-over-Wi-Fi Device (100% local in Home Assistant; no cloud or bridge required).",
            "payload": decoded.__dict__,
            "ha_service_call": build_ha_matter_commission_request(raw),
        }

    # Case 2: 11-digit or 21-digit numeric Matter pairing code
    only_digits = "".join(ch for ch in raw if ch.isdigit())
    if len(only_digits) in (11, 21) and all(ch.isdigit() or ch in "- " for ch in raw):
        decoded = decode_matter_manual_code(raw)
        return {
            "classification": "matter_native_local",
            "is_matter": True,
            "summary": "Native Matter Manual Pairing Code (100% local in Home Assistant).",
            "payload": decoded.__dict__,
            "ha_service_call": build_ha_matter_commission_request(only_digits),
        }

    # Case 3: Amazon Basics "Works with Alexa Only" (ACK) barcode or model string
    return {
        "classification": "amazon_ack_alexa_only",
        "is_matter": False,
        "raw_input": raw,
        "summary": (
            "Non-Matter Amazon Alexa Connect Kit (ACK / Frustration-Free Setup) device. "
            "Uses mTLS to AWS IoT on an ESP32-PICO-V3-ZERO or BK7231N module."
        ),
        "recommended_paths": [
            "No-Hardware-Mod: Pair in Alexa App and expose to Home Assistant via Alexa Media Player (HACS).",
            "100% Local Hardware Mod: Flash ESPHome or Tasmota (with local Matter) via 3.3V UART serial pads (see esphome/amazon-basics-ack-esp32.yaml).",
        ],
    }


def build_ha_matter_commission_request(
    code: str, network_only: bool = False, message_id: str = "sengled-matter-1"
) -> Dict[str, Any]:
    """
    Build the JSON WebSocket command for Home Assistant's `python-matter-server`
    (`ws://<ha_host>:5580/ws`) to commission a Matter bulb locally.
    """
    return {
        "message_id": message_id,
        "command": "commission_with_code",
        "args": {
            "code": code.strip(),
            "network_only": bool(network_only),
        },
    }
