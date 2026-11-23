"""
Home Assistant MQTT Discovery & State Translation Layer.

Automatically exposes Sengled Wi-Fi and Bluetooth (BLE) bulbs to Home Assistant
as native `light` entities (plus optional `sensor` entities for Wi-Fi RSSI and
power consumption) using the Home Assistant MQTT JSON Light schema.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple, Union

from sengled_bridge.alexa_ack_bridge import AlexaACKLightState
from sengled_bridge.ble_controller import SengledBLEBulbState
from sengled_bridge.models import (
    ColorCapability,
    RadioProtocol,
    SengledModelSpec,
    identify_device_by_model_or_fcc,
    identify_from_status_attributes,
)
from sengled_bridge.wifi_protocol import (
    SengledWiFiBulbState,
    build_command_item,
    format_sengled_color,
    ha_brightness_to_sengled,
    kelvin_to_mireds,
    kelvin_to_sengled_cct_pct,
    mac_to_slug,
    mireds_to_kelvin,
    normalize_mac,
)

EFFECT_NAME_TO_CODE: Dict[str, int] = {
    "normal": 0,
    "audio_sync": 7,
    "video_sync": 100,
    "game_sync": 101,
}
EFFECT_CODE_TO_NAME: Dict[int, str] = {v: k for k, v in EFFECT_NAME_TO_CODE.items()}


def get_ha_topics(
    mac: str,
    discovery_prefix: str = "homeassistant",
    bridge_prefix: str = "sengled_bridge",
) -> Dict[str, str]:
    """Return all Home Assistant MQTT discovery, state, command, and availability topics for a bulb."""
    slug = mac_to_slug(mac)
    object_id = f"sengled_{slug}"
    return {
        "discovery_topic": f"{discovery_prefix}/light/{object_id}/config",
        "rssi_discovery_topic": f"{discovery_prefix}/sensor/{object_id}_rssi/config",
        "power_discovery_topic": f"{discovery_prefix}/sensor/{object_id}_power/config",
        "state_topic": f"{bridge_prefix}/light/{slug}/state",
        "command_topic": f"{bridge_prefix}/light/{slug}/set",
        "availability_topic": f"{bridge_prefix}/light/{slug}/availability",
        "bridge_availability_topic": f"{bridge_prefix}/bridge/status",
        "alexa_ack_command_topic": f"{bridge_prefix}/alexa_ack/{slug}/command",
    }


def resolve_supported_color_modes(
    model_code: str = "",
    support_attributes: str = "",
    default_capability: ColorCapability = ColorCapability.RGBW,
) -> Tuple[List[str], int, int, bool]:
    """
    Determine Home Assistant `supported_color_modes`, `(min_kelvin, max_kelvin)`,
    and `supports_effects` for a bulb model.
    """
    specs: List[SengledModelSpec] = (
        identify_device_by_model_or_fcc(model_code) if model_code else []
    )
    spec = specs[0] if specs else None

    tokens = {
        t.strip().lower() for t in (support_attributes or "").split(",") if t.strip()
    }

    if "color" in tokens:
        cap = ColorCapability.RGBW
    elif "colortemperature" in tokens or "white" in tokens:
        cap = ColorCapability.TUNABLE_WHITE
    elif "brightness" in tokens and not spec:
        cap = ColorCapability.DIMMABLE_WHITE
    elif spec:
        cap = spec.capability
    else:
        cap = default_capability

    min_k = spec.min_kelvin if spec else 2700
    max_k = spec.max_kelvin if spec else 6500
    supports_effects = bool(spec.supports_effects) if spec else ("effectstatus" in tokens)

    if cap == ColorCapability.ON_OFF:
        modes = ["onoff"]
    elif cap == ColorCapability.DIMMABLE_WHITE:
        modes = ["brightness"]
    elif cap == ColorCapability.TUNABLE_WHITE:
        modes = ["color_temp"]
    else:
        modes = ["color_temp", "rgb"]

    return modes, min_k, max_k, supports_effects


def build_ha_light_discovery_payload(
    mac: str,
    model_code: str = "",
    support_attributes: str = "",
    firmware_version: str = "",
    chipset: str = "",
    friendly_name: Optional[str] = None,
    transport: str = "Wi-Fi",
    manufacturer: Optional[str] = None,
    discovery_prefix: str = "homeassistant",
    bridge_prefix: str = "sengled_bridge",
) -> Dict[str, Any]:
    """
    Build a Home Assistant MQTT Discovery configuration dictionary for a Sengled or
    Amazon Basics 'Works with Alexa Only' (ACK) bulb (`homeassistant/light/sengled_{mac_slug}/config`).
    """
    norm_mac = normalize_mac(mac)
    slug = mac_to_slug(norm_mac)
    topics = get_ha_topics(norm_mac, discovery_prefix=discovery_prefix, bridge_prefix=bridge_prefix)

    specs = identify_device_by_model_or_fcc(model_code) if model_code else []
    spec = specs[0] if specs else None

    modes, min_k, max_k, supports_effects = resolve_supported_color_modes(
        model_code=model_code,
        support_attributes=support_attributes,
    )

    is_ack = (spec is not None and spec.protocol == RadioProtocol.WIFI_ALEXA_ACK) or (
        "ACK" in transport.upper()
    )
    resolved_mfr = manufacturer or ("Amazon Basics" if is_ack else "Sengled")
    display_model = model_code or (spec.model if spec else f"{resolved_mfr} {transport} Bulb")
    name = friendly_name or (
        f"{spec.name} ({norm_mac[-5:]})" if spec else f"{resolved_mfr} {display_model} {norm_mac[-5:]}"
    )

    payload: Dict[str, Any] = {
        "name": name,
        "unique_id": f"sengled_{slug}_light",
        "object_id": f"sengled_{slug}",
        "schema": "json",
        "state_topic": topics["state_topic"],
        "command_topic": topics["command_topic"],
        "availability": [
            {"topic": topics["bridge_availability_topic"], "payload_available": "online", "payload_not_available": "offline"},
            {"topic": topics["availability_topic"], "payload_available": "online", "payload_not_available": "offline"},
        ],
        "availability_mode": "all",
        "supported_color_modes": modes,
        "optimistic": False,
        "device": {
            "identifiers": [f"sengled_{slug}"],
            "connections": [["mac", norm_mac]],
            "manufacturer": resolved_mfr,
            "model": f"{display_model} ({spec.module_id})" if spec else display_model,
            "name": name,
            "sw_version": firmware_version or ("ACK Bridge" if is_ack else "Stock Local"),
            "hw_version": chipset or (spec.chipset if spec else transport),
        },
    }

    if "brightness" in modes or "color_temp" in modes or "rgb" in modes:
        payload["brightness"] = True
        payload["brightness_scale"] = 255

    if "color_temp" in modes:
        eff_max_k = max(max_k, min_k + 100) if max_k <= min_k else max_k
        payload["min_mireds"] = kelvin_to_mireds(eff_max_k)
        payload["max_mireds"] = kelvin_to_mireds(min_k)
        payload["color_temp_kelvin"] = True

    if supports_effects:
        payload["effect"] = True
        payload["effect_list"] = list(EFFECT_NAME_TO_CODE.keys())

    return payload


def build_ha_light_state_payload(
    bulb: Union[SengledWiFiBulbState, SengledBLEBulbState, AlexaACKLightState]
) -> Dict[str, Any]:
    """
    Build the Home Assistant MQTT JSON Light state dictionary from a Wi-Fi, BLE,
    or Amazon 'Works with Alexa Only' (ACK) bulb state object.
    """
    if isinstance(bulb, SengledWiFiBulbState):
        model_code = bulb.type_code
        support_attrs = bulb.support_attributes
        ha_bri = bulb.ha_brightness
        effect_name = EFFECT_CODE_TO_NAME.get(bulb.effect_status, "normal")
    else:
        model_code = bulb.model
        support_attrs = ""
        ha_bri = bulb.ha_brightness
        effect_name = "normal"

    modes, _, _, supports_effects = resolve_supported_color_modes(
        model_code=model_code,
        support_attributes=support_attrs,
    )

    state_dict: Dict[str, Any] = {
        "state": "ON" if bulb.is_on else "OFF",
    }

    if modes == ["onoff"]:
        state_dict["color_mode"] = "onoff"
        return state_dict

    state_dict["brightness"] = ha_bri

    if modes == ["brightness"]:
        state_dict["color_mode"] = "brightness"
        return state_dict

    active_mode = bulb.color_mode if bulb.color_mode in modes else modes[0]
    state_dict["color_mode"] = active_mode

    if "color_temp" in modes:
        state_dict["color_temp_kelvin"] = bulb.color_temp_kelvin
        state_dict["color_temp"] = kelvin_to_mireds(bulb.color_temp_kelvin)

    if "rgb" in modes:
        r, g, b = bulb.rgb
        state_dict["color"] = {"r": r, "g": g, "b": b}

    if supports_effects:
        state_dict["effect"] = effect_name

    return state_dict


def translate_ha_command_to_wifi_mqtt(
    mac: str,
    ha_cmd_payload: Union[str, bytes, Dict[str, Any]],
    timestamp_ms: Optional[int] = None,
    min_kelvin: int = 2700,
    max_kelvin: int = 6500,
) -> Tuple[str, str]:
    """
    Translate a Home Assistant JSON light command from `sengled_bridge/light/{slug}/set`
    into a `(topic, payload_json)` pair for `wifielement/{MAC}/update`.

    Handles:
    - `state`: `"ON"` / `"OFF"`
    - `brightness`: `0`..`255` -> Sengled `0`..`100`
    - `color`: `{"r": R, "g": G, "b": B}` -> Sengled `"R:G:B"`
    - `color_temp_kelvin` or `color_temp` (mireds) -> Sengled `0`..`100` + mandatory `switch: "1"`
    - `effect`: `"normal"` / `"audio_sync"` / `"video_sync"` / `"game_sync"`
    - `transition`: seconds -> Sengled `gradientTime` (milliseconds)
    """
    norm_mac = normalize_mac(mac)
    topic = f"wifielement/{norm_mac}/update"

    if isinstance(ha_cmd_payload, (str, bytes)):
        cmd_dict = json.loads(
            ha_cmd_payload.decode("utf-8")
            if isinstance(ha_cmd_payload, bytes)
            else ha_cmd_payload
        )
    else:
        cmd_dict = dict(ha_cmd_payload)

    transition_s = cmd_dict.get("transition")
    gradient_ms: Optional[int] = (
        round(float(transition_s) * 1000) if transition_s is not None else None
    )

    items: List[Dict[str, Any]] = []
    state_str = str(cmd_dict.get("state", "ON")).upper()

    if state_str == "OFF":
        items.append(
            build_command_item(
                norm_mac,
                "switch",
                "0",
                timestamp_ms=timestamp_ms,
                gradient_time_ms=gradient_ms,
            )
        )
        return topic, json.dumps(items, separators=(",", ":"))

    # Light is turning ON or adjusting parameters while ON
    has_cct = "color_temp_kelvin" in cmd_dict or "color_temp" in cmd_dict
    has_rgb = "color" in cmd_dict and isinstance(cmd_dict["color"], dict)
    has_bri = "brightness" in cmd_dict
    has_effect = "effect" in cmd_dict

    if has_cct:
        if "color_temp_kelvin" in cmd_dict:
            kelvin = int(cmd_dict["color_temp_kelvin"])
        else:
            kelvin = mireds_to_kelvin(float(cmd_dict["color_temp"]))
        cct_pct = kelvin_to_sengled_cct_pct(kelvin, min_kelvin=min_kelvin, max_kelvin=max_kelvin)
        items.append(
            build_command_item(
                norm_mac,
                "colorTemperature",
                str(cct_pct),
                timestamp_ms=timestamp_ms,
                gradient_time_ms=gradient_ms,
            )
        )
        # Mandatory switch: "1" required by Sengled firmware when changing colorTemperature
        items.append(
            build_command_item(
                norm_mac,
                "switch",
                "1",
                timestamp_ms=timestamp_ms,
                gradient_time_ms=gradient_ms,
            )
        )

    if has_rgb:
        c = cmd_dict["color"]
        r = int(c.get("r", 255))
        g = int(c.get("g", 255))
        b = int(c.get("b", 255))
        items.append(
            build_command_item(
                norm_mac,
                "color",
                format_sengled_color(r, g, b, use_hex=False),
                timestamp_ms=timestamp_ms,
            )
        )

    if has_bri:
        bri_pct = ha_brightness_to_sengled(int(cmd_dict["brightness"]))
        items.append(
            build_command_item(
                norm_mac,
                "brightness",
                str(bri_pct),
                timestamp_ms=timestamp_ms,
                gradient_time_ms=gradient_ms,
            )
        )

    if has_effect:
        eff_name = str(cmd_dict["effect"]).strip().lower()
        eff_code = EFFECT_NAME_TO_CODE.get(eff_name, 0)
        items.append(
            build_command_item(
                norm_mac,
                "effectStatus",
                str(eff_code),
                timestamp_ms=timestamp_ms,
            )
        )

    # Always ensure switch="1" is included if not already added by has_cct
    if not has_cct:
        items.append(
            build_command_item(
                norm_mac,
                "switch",
                "1",
                timestamp_ms=timestamp_ms,
                gradient_time_ms=gradient_ms,
            )
        )

    return topic, json.dumps(items, separators=(",", ":"))
