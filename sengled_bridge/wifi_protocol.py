"""
Sengled Wi-Fi MQTT (Port 8883 TLS) and Direct UDP (Port 9080) Protocol Codec.

Handles:
- Topic routing:
  * `wifielement/{MAC}/status`
  * `wifielement/{MAC}/update`
  * `wifielement/{MAC}/consumption`
  * `wifielement/{MAC}/consumptionTime`
  * `wifielement/c/status`
- Status payload decoding (supports plain JSON array `[...]` and legacy `Os$[...]`).
- Command payload encoding for power (`switch`), dimming (`brightness` 0-100),
  color temperature (`colorTemperature` 0-100 / Kelvin + mandatory `switch: "1"`),
  RGB color (`R:G:B` and `RRGGBB`), effects (`effectStatus`), group commands,
  and OTA firmware updates (`update`).
- Direct local UDP (port 9080) JSON payload generation (`search_devices`,
  `set_device_switch`, `set_device_brightness`, `set_device_color`,
  `set_device_colortemp`, `set_device_pwm`).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union


def normalize_mac(mac: str) -> str:
    """Normalize a MAC address to uppercase colon-separated format `AA:BB:CC:DD:EE:FF`."""
    cleaned = mac.strip().upper().replace("-", ":").replace("_", ":").replace(".", "")
    if ":" not in cleaned and len(cleaned) == 12:
        cleaned = ":".join(cleaned[i : i + 2] for i in range(0, 12, 2))
    return cleaned


def mac_to_slug(mac: str) -> str:
    """Convert a MAC address to a lowercase hex slug `aabbccddeeff` for HA entity IDs."""
    return normalize_mac(mac).replace(":", "").lower()


def ha_brightness_to_sengled(ha_brightness: int) -> int:
    """Convert Home Assistant brightness (0..255) to Sengled percentage (0..100)."""
    clamped = max(0, min(255, int(ha_brightness)))
    if clamped == 0:
        return 0
    return max(1, round((clamped / 255.0) * 100))


def sengled_brightness_to_ha(sengled_brightness: Union[int, float, str]) -> int:
    """Convert Sengled brightness percentage (0..100) to Home Assistant (0..255)."""
    try:
        pct = float(sengled_brightness)
    except (TypeError, ValueError):
        pct = 0.0
    clamped = max(0.0, min(100.0, pct))
    return round((clamped / 100.0) * 255)


def kelvin_to_sengled_cct_pct(
    kelvin: int, min_kelvin: int = 2700, max_kelvin: int = 6500
) -> int:
    """
    Convert a Kelvin color temperature (2700K..6500K) to Sengled's 0..100 scale
    (0 = warmest 2700K, 100 = coolest 6500K).
    """
    if max_kelvin <= min_kelvin:
        return 0
    clamped = max(min_kelvin, min(max_kelvin, int(kelvin)))
    return round(((clamped - min_kelvin) / float(max_kelvin - min_kelvin)) * 100)


def sengled_cct_to_kelvin(
    val: Union[int, float, str], min_kelvin: int = 2700, max_kelvin: int = 6500
) -> int:
    """
    Convert Sengled `colorTemperature` (reported either as 0..100 percent or
    direct Kelvin like 2700..6500) into Kelvin.
    """
    try:
        num = float(val)
    except (TypeError, ValueError):
        return min_kelvin

    if num > 100.0:
        return max(min_kelvin, min(max_kelvin, round(num)))

    clamped_pct = max(0.0, min(100.0, num))
    return round(min_kelvin + (clamped_pct / 100.0) * (max_kelvin - min_kelvin))


def mireds_to_kelvin(mireds: Union[int, float]) -> int:
    """Convert Home Assistant mireds (153..500) to Kelvin."""
    m = max(1, float(mireds))
    return round(1_000_000.0 / m)


def kelvin_to_mireds(kelvin: Union[int, float]) -> int:
    """Convert Kelvin to Home Assistant mireds."""
    k = max(1000.0, float(kelvin))
    return round(1_000_000.0 / k)


def parse_sengled_color(value: str) -> Optional[Tuple[int, int, int]]:
    """
    Parse a Sengled `color` string into an `(r, g, b)` tuple (0..255 each).
    Supports both colon-separated `"255:0:128"` and hex `"FF0080"` formats.
    """
    raw = (value or "").strip()
    if not raw:
        return None

    if ":" in raw:
        parts = raw.split(":")
        if len(parts) == 3:
            try:
                r, g, b = (max(0, min(255, int(p))) for p in parts)
                return (r, g, b)
            except ValueError:
                return None

    hex_str = raw.lstrip("#")
    if len(hex_str) == 6:
        try:
            r = int(hex_str[0:2], 16)
            g = int(hex_str[2:4], 16)
            b = int(hex_str[4:6], 16)
            return (r, g, b)
        except ValueError:
            return None

    return None


def format_sengled_color(r: int, g: int, b: int, use_hex: bool = False) -> str:
    """
    Format RGB values (0..255) for Sengled's `color` attribute.
    Default is colon-separated `"R:G:B"` (universally accepted across WF861/WF863/WF864);
    optional hex `"RRGGBB"`.
    """
    rc = max(0, min(255, int(r)))
    gc = max(0, min(255, int(g)))
    bc = max(0, min(255, int(b)))
    if use_hex:
        return f"{rc:02X}{gc:02X}{bc:02X}"
    return f"{rc:d}:{gc:d}:{bc:d}"


@dataclass
class SengledWiFiBulbState:
    """In-memory state representation of a Sengled Wi-Fi bulb."""

    mac: str
    is_on: bool = False
    brightness_pct: int = 100
    color_temp_kelvin: int = 2700
    rgb: Tuple[int, int, int] = (255, 255, 255)
    color_mode: str = "color_temp"  # "color_temp", "rgb", or "brightness"
    effect_status: int = 0
    type_code: str = ""
    identify_no: str = ""
    product_code: str = "wifielement"
    support_attributes: str = "brightness"
    firmware_version: str = ""
    ip_address: str = ""
    rssi: Optional[int] = None
    power_consumption_mw: Optional[int] = None
    consumption_time_s: Optional[int] = None
    last_seen_epoch: float = field(default_factory=time.time)
    raw_attributes: Dict[str, str] = field(default_factory=dict)

    @property
    def ha_brightness(self) -> int:
        return sengled_brightness_to_ha(self.brightness_pct)

    def apply_status_records(self, records: Sequence[Dict[str, Any]]) -> bool:
        """
        Update bulb state from a list of Sengled MQTT status objects:
            [{"dn": "40:43:18:2F:74:C9", "type": "switch", "value": "1", "time": "50"}, ...]
        Returns True if any state or metadata attribute was updated.
        """
        changed = False
        self.last_seen_epoch = time.time()

        for item in records:
            if not isinstance(item, dict):
                continue
            attr_type = str(item.get("type", "") or "").strip()
            attr_val = item.get("value")
            if not attr_type or attr_val is None:
                continue

            val_str = str(attr_val).strip()
            self.raw_attributes[attr_type] = val_str

            if attr_type == "switch":
                self.is_on = val_str == "1"
                changed = True
            elif attr_type == "brightness":
                try:
                    self.brightness_pct = max(0, min(100, int(float(val_str))))
                    changed = True
                except ValueError:
                    pass
            elif attr_type in ("colorTemperature", "white"):
                self.color_temp_kelvin = sengled_cct_to_kelvin(val_str)
                self.color_mode = "color_temp"
                changed = True
            elif attr_type == "color":
                parsed_rgb = parse_sengled_color(val_str)
                if parsed_rgb:
                    self.rgb = parsed_rgb
                    self.color_mode = "rgb"
                    changed = True
            elif attr_type == "colorMode":
                # 1 = RGB engine active, 2 = White/CCT engine active (read-only reported attr)
                if val_str == "1":
                    self.color_mode = "rgb"
                elif val_str == "2":
                    self.color_mode = "color_temp"
                changed = True
            elif attr_type == "effectStatus":
                try:
                    self.effect_status = int(val_str)
                    changed = True
                except ValueError:
                    pass
            elif attr_type == "typeCode":
                self.type_code = val_str
                changed = True
            elif attr_type == "identifyNO":
                self.identify_no = val_str
                changed = True
            elif attr_type == "productCode":
                self.product_code = val_str
                changed = True
            elif attr_type == "supportAttributes":
                self.support_attributes = val_str
                changed = True
            elif attr_type == "version":
                self.firmware_version = val_str
                changed = True
            elif attr_type == "ip":
                self.ip_address = val_str
                changed = True
            elif attr_type == "deviceRssi":
                try:
                    self.rssi = int(val_str)
                    changed = True
                except ValueError:
                    pass
            elif attr_type == "consumption":
                try:
                    self.power_consumption_mw = int(val_str)
                    changed = True
                except ValueError:
                    pass
            elif attr_type == "consumptionTime":
                try:
                    self.consumption_time_s = int(val_str)
                    changed = True
                except ValueError:
                    pass

        return changed


# ---------------------------------------------------------------------------
# MQTT Topic & Payload Decoding / Encoding
# ---------------------------------------------------------------------------
def parse_mqtt_topic(topic: str) -> Optional[Tuple[str, str]]:
    """
    Parse a `wifielement/{MAC}/{subtopic}` MQTT topic into `(mac, subtopic)`.
    Returns None if the topic is not a valid Sengled `wifielement` topic.
    """
    parts = topic.strip().split("/")
    if len(parts) != 3 or parts[0] != "wifielement":
        return None
    mac_or_c = parts[1]
    subtopic = parts[2]
    if mac_or_c.lower() == "c":
        return ("c", subtopic)
    return (normalize_mac(mac_or_c), subtopic)


def decode_sengled_mqtt_payload(payload: Union[str, bytes]) -> List[Dict[str, Any]]:
    """
    Decode a Sengled MQTT payload from `wifielement/{MAC}/status` or `/update`.
    Transparently strips the legacy `Os$` prefix if present.
    """
    if isinstance(payload, bytes):
        text = payload.decode("utf-8", errors="ignore").strip()
    else:
        text = str(payload).strip()

    if text.startswith("Os$"):
        text = text[3:].strip()

    if not text:
        return []

    parsed = json.loads(text)
    if isinstance(parsed, dict):
        return [parsed]
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    return []


def _epoch_ms(timestamp_ms: Optional[int] = None) -> int:
    return int(timestamp_ms if timestamp_ms is not None else time.time() * 1000)


def build_command_item(
    mac: str,
    cmd_type: str,
    value: Any,
    timestamp_ms: Optional[int] = None,
    gradient_time_ms: Optional[int] = None,
) -> Dict[str, Any]:
    """Build a single command object for `wifielement/{MAC}/update`."""
    item: Dict[str, Any] = {
        "dn": normalize_mac(mac),
        "type": cmd_type,
        "value": value,
        "time": _epoch_ms(timestamp_ms),
    }
    if gradient_time_ms is not None:
        item["gradientTime"] = int(gradient_time_ms)
    return item


def encode_switch_command(
    mac: str,
    on: bool,
    timestamp_ms: Optional[int] = None,
    gradient_time_ms: Optional[int] = None,
    os_prefix: bool = False,
) -> str:
    """Encode an MQTT power ON (`"1"`) or OFF (`"0"`) command for `wifielement/{MAC}/update`."""
    cmds = [
        build_command_item(
            mac,
            "switch",
            "1" if on else "0",
            timestamp_ms=timestamp_ms,
            gradient_time_ms=gradient_time_ms,
        )
    ]
    raw = json.dumps(cmds, separators=(",", ":"))
    return f"Os${raw}" if os_prefix else raw


def encode_brightness_command(
    mac: str,
    brightness_pct: int,
    timestamp_ms: Optional[int] = None,
    gradient_time_ms: Optional[int] = None,
    os_prefix: bool = False,
) -> str:
    """Encode an MQTT brightness command (`0`..`100`) for `wifielement/{MAC}/update`."""
    clamped = max(0, min(100, int(brightness_pct)))
    cmds = [
        build_command_item(
            mac,
            "brightness",
            str(clamped),
            timestamp_ms=timestamp_ms,
            gradient_time_ms=gradient_time_ms,
        )
    ]
    raw = json.dumps(cmds, separators=(",", ":"))
    return f"Os${raw}" if os_prefix else raw


def encode_color_command(
    mac: str,
    r: int,
    g: int,
    b: int,
    use_hex: bool = False,
    timestamp_ms: Optional[int] = None,
    os_prefix: bool = False,
) -> str:
    """Encode an MQTT RGB color command (`"R:G:B"` or `"RRGGBB"`) for `wifielement/{MAC}/update`."""
    color_val = format_sengled_color(r, g, b, use_hex=use_hex)
    cmds = [
        build_command_item(
            mac,
            "color",
            color_val,
            timestamp_ms=timestamp_ms,
        )
    ]
    raw = json.dumps(cmds, separators=(",", ":"))
    return f"Os${raw}" if os_prefix else raw


def encode_color_temp_command(
    mac: str,
    color_temp_pct_or_kelvin: int,
    use_percentage: bool = True,
    timestamp_ms: Optional[int] = None,
    os_prefix: bool = False,
) -> str:
    """
    Encode an MQTT color temperature command for `wifielement/{MAC}/update`.

    CRITICAL FIRMWARE REQUIREMENT:
    Sengled Wi-Fi bulbs require `{"type": "switch", "value": "1"}` to be bundled
    in the same JSON array as `{"type": "colorTemperature", ...}`.
    """
    ts = _epoch_ms(timestamp_ms)
    val = int(color_temp_pct_or_kelvin)
    if use_percentage and val > 100:
        val = kelvin_to_sengled_cct_pct(val)
    elif use_percentage:
        val = max(0, min(100, val))

    cmds = [
        build_command_item(mac, "colorTemperature", str(val), timestamp_ms=ts),
        build_command_item(mac, "switch", "1", timestamp_ms=ts),
    ]
    raw = json.dumps(cmds, separators=(",", ":"))
    return f"Os${raw}" if os_prefix else raw


def encode_effect_command(
    mac: str,
    effect_status: int,
    timestamp_ms: Optional[int] = None,
) -> str:
    """Encode an MQTT effectStatus command (`0`=normal, `7`=audio, `100`=video, `101`=game)."""
    cmds = [build_command_item(mac, "effectStatus", str(int(effect_status)), timestamp_ms=timestamp_ms)]
    return json.dumps(cmds, separators=(",", ":"))


def encode_reset_command(mac: str, timestamp_ms: Optional[int] = None) -> str:
    """Encode an MQTT factory reset command (`type: "reset", value: "1"`)."""
    cmds = [build_command_item(mac, "reset", "1", timestamp_ms=timestamp_ms)]
    return json.dumps(cmds, separators=(",", ":"))


def encode_ota_update_command(
    mac: str, firmware_url: str, timestamp_ms: Optional[int] = None
) -> str:
    """Encode an MQTT OTA firmware update command (`type: "update", value: "<url>"`)."""
    cmds = [build_command_item(mac, "update", firmware_url, timestamp_ms=timestamp_ms)]
    return json.dumps(cmds, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Direct Local UDP Control Payloads (Port 9080)
# ---------------------------------------------------------------------------
def build_udp_search_devices() -> bytes:
    """Build UDP broadcast discovery payload `{"func":"search_devices","param":{}}`."""
    return json.dumps({"func": "search_devices", "param": {}}, separators=(",", ":")).encode("utf-8")


def build_udp_switch(on: bool) -> bytes:
    """Build UDP power switch payload (`switch`: 1 or 0)."""
    return json.dumps(
        {"func": "set_device_switch", "param": {"switch": 1 if on else 0}},
        separators=(",", ":"),
    ).encode("utf-8")


def build_udp_brightness(brightness_pct: int) -> bytes:
    """Build UDP brightness payload (`brightness`: 0..100)."""
    clamped = max(0, min(100, int(brightness_pct)))
    return json.dumps(
        {"func": "set_device_brightness", "param": {"brightness": clamped}},
        separators=(",", ":"),
    ).encode("utf-8")


def build_udp_color(r: int, g: int, b: int) -> bytes:
    """Build UDP persistent RGB color payload (`red`, `green`, `blue`: 0..255)."""
    return json.dumps(
        {
            "func": "set_device_color",
            "param": {
                "red": max(0, min(255, int(r))),
                "green": max(0, min(255, int(g))),
                "blue": max(0, min(255, int(b))),
            },
        },
        separators=(",", ":"),
    ).encode("utf-8")


def build_udp_colortemp(color_temp_pct: int) -> bytes:
    """Build UDP persistent color temperature payload (`colorTemperature`: 0..100)."""
    clamped = max(0, min(100, int(color_temp_pct)))
    return json.dumps(
        {"func": "set_device_colortemp", "param": {"colorTemperature": clamped}},
        separators=(",", ":"),
    ).encode("utf-8")
