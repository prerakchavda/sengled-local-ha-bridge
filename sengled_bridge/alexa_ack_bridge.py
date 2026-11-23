"""
Amazon "Works with Alexa Only" (Alexa Connect Kit / ACK & Echo-Paired BLE)
Multi-Path Bridge & Local Echo / Hue V1 Emulator for `sengled-local-ha-bridge`.

Provides 4 complementary ways to integrate "Works with Alexa Only" lights
(such as Amazon Basics `13aSB-A800ST-Q1T`, `13aSB-A806ST-Q1R_NA`, `13aSB-A806ST-Q1T_EU`,
`13aSB-A806ST-Q1T_JP`, `B0C332SMK8`, `B0C3349GNR`, `B0CG5VDC8P`, `B0CYPQM746`,
`WS30-01`, `WP52-2`, and Echo-paired Sengled `B11-N11`/`B11-N1E` BLE Mesh bulbs)
directly into `sengled-local-ha-bridge` as native Home Assistant MQTT Discovery `light` entities:

1. Direct Alexa Smart Home GraphQL & Behaviors API Bridge (Zero Hardware Mod):
   - Queries `POST https://<alexa_domain>/nexus/v1/graphql` (`Endpoints` & `getPowerBrightnessColorColorTempStates`)
     to auto-discover "Works with Alexa Only" ACK & Echo-connected lights and poll live state.
   - Dispatches `setEndpointFeatures` GraphQL mutations (`turnOn`, `turnOff`, `setBrightness`,
     `setColorTemperature`) and `Alexa.SmartHome.Batch` / `/api/phoenix/state` (`setColor` mapped across
     all official Alexa Smart Home color names) when Home Assistant sends commands to
     `sengled_bridge/light/{slug}/set`.
2. Built-in 100% Local LAN Echo / Philips Hue V1 Emulator (`LocalHueEchoEmulator`):
   - Serves UPnP `/description.xml`, SSDP (`239.255.255.250:1900`), and Philips Hue V1 REST endpoints
     (`/api/<username>/lights`, `PUT /api/<username>/lights/<id>/state`) on the bridge HTTP server so
     local Amazon Echo devices and Alexa Routines can sync state bidirectionally over the local LAN
     without requiring cloud cookies.
3. Home Assistant `alexa_media` / `alexa_devices` MQTT Command Relay:
   - Translates every Home Assistant light command on `sengled_bridge/light/{slug}/set` into a
     structured MQTT event on `sengled_bridge/alexa_ack/{slug}/command` containing natural-language
     Alexa command phrases and ready-to-call Home Assistant `media_player.play_media` service payloads.
4. Sengled `wifielement/{MAC}/...` Protocol Compatibility for Serial-Flashed ACK ESP32 Bulbs:
   - Allows `ESP32-PICO-V3-ZERO` (`2AC7Z-ESP32PICOV30`) Amazon Basics bulbs flashed with
     `esphome/amazon-basics-ack-esp32.yaml` (supporting PWM LEDC, `BP5758D`, and `SM2135E`/`SM2235EGH`
     LED drivers) to work natively with `sengled-local-ha-bridge` or ESPHome.
"""

from __future__ import annotations

import colorsys
import hashlib
import json
import logging
import re
import socket
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from sengled_bridge.wifi_protocol import (
    kelvin_to_mireds,
    mac_to_slug,
    mireds_to_kelvin,
    normalize_mac,
)

logger = logging.getLogger("sengled_bridge.alexa_ack")

# Official Amazon Technologies Inc. IEEE OUI prefix used for deterministic MAC derivation
# when an ACK device is registered by DSN, Barcode, or Alexa Endpoint ID.
AMAZON_OUI_PREFIX = "F0:F0:A4"

# Regional Amazon Marketplace -> Alexa Web API Host Mapping
ALEXA_DOMAIN_MAP: Dict[str, str] = {
    "amazon.com": "alexa.amazon.com",
    "alexa.amazon.com": "alexa.amazon.com",
    "pitangui.amazon.com": "alexa.amazon.com",
    "amazon.co.uk": "alexa.amazon.co.uk",
    "alexa.amazon.co.uk": "alexa.amazon.co.uk",
    "layla.amazon.com": "alexa.amazon.co.uk",
    "amazon.ca": "alexa.amazon.ca",
    "alexa.amazon.ca": "alexa.amazon.ca",
    "amazon.de": "alexa.amazon.de",
    "alexa.amazon.de": "alexa.amazon.de",
    "amazon.co.jp": "alexa.amazon.co.jp",
    "alexa.amazon.co.jp": "alexa.amazon.co.jp",
    "amazon.es": "alexa.amazon.es",
    "alexa.amazon.es": "alexa.amazon.es",
    "amazon.fr": "alexa.amazon.fr",
    "alexa.amazon.fr": "alexa.amazon.fr",
    "amazon.it": "alexa.amazon.it",
    "alexa.amazon.it": "alexa.amazon.it",
    "amazon.com.au": "alexa.amazon.com.au",
    "alexa.amazon.com.au": "alexa.amazon.com.au",
    "amazon.com.br": "alexa.amazon.com.br",
    "alexa.amazon.com.br": "alexa.amazon.com.br",
    "amazon.com.mx": "alexa.amazon.com.mx",
    "alexa.amazon.com.mx": "alexa.amazon.com.mx",
}

# Official Alexa.ColorTemperatureController named color temperature presets
ALEXA_COLOR_TEMP_PRESETS: Dict[str, int] = {
    "warm_white": 2200,
    "soft_white": 2700,
    "white": 4000,
    "daylight_white": 5500,
    "cool_white": 7000,
}

# Official Alexa.ColorController named color palette mapped to RGB (0..255)
ALEXA_COLOR_PALETTE: Dict[str, Tuple[int, int, int]] = {
    "red": (255, 0, 0),
    "crimson": (255, 37, 69),
    "firebrick": (255, 47, 47),
    "dark_red": (220, 0, 0),
    "indian_red": (255, 114, 114),
    "light_coral": (255, 136, 136),
    "salmon": (255, 160, 122),
    "dark_salmon": (255, 164, 134),
    "light_salmon": (255, 160, 122),
    "tomato": (255, 99, 71),
    "orange_red": (255, 68, 0),
    "coral": (255, 126, 79),
    "dark_orange": (255, 138, 37),
    "orange": (255, 166, 0),
    "gold": (255, 212, 0),
    "goldenrod": (255, 194, 39),
    "dark_goldenrod": (255, 187, 14),
    "yellow": (255, 255, 0),
    "light_yellow": (255, 255, 224),
    "lemon_chiffon": (255, 249, 204),
    "khaki": (255, 244, 149),
    "dark_khaki": (255, 248, 145),
    "peach_puff": (255, 216, 186),
    "moccasin": (255, 225, 181),
    "papaya_whip": (255, 239, 214),
    "wheat": (255, 231, 186),
    "tan": (255, 221, 171),
    "burlywood": (255, 210, 156),
    "sandy_brown": (255, 170, 100),
    "peru": (255, 164, 79),
    "chocolate": (255, 128, 37),
    "saddle_brown": (255, 124, 31),
    "sienna": (255, 130, 72),
    "brown": (255, 61, 62),
    "green_yellow": (175, 255, 45),
    "chartreuse": (127, 255, 0),
    "lawn_green": (121, 255, 65),
    "lime": (199, 255, 30),
    "lime_green": (64, 255, 64),
    "yellow_green": (191, 255, 70),
    "olive_drab": (191, 255, 63),
    "olive": (255, 252, 75),
    "dark_olive_green": (161, 255, 110),
    "pale_green": (157, 255, 157),
    "light_green": (153, 255, 153),
    "medium_spring_green": (26, 255, 157),
    "spring_green": (0, 255, 127),
    "medium_sea_green": (87, 255, 160),
    "sea_green": (82, 255, 157),
    "forest_green": (60, 255, 60),
    "green": (0, 255, 0),
    "web_green": (0, 255, 61),
    "dark_green": (0, 200, 0),
    "dark_sea_green": (193, 255, 193),
    "medium_aquamarine": (127, 255, 213),
    "aquamarine": (127, 255, 210),
    "turquoise": (72, 255, 237),
    "medium_turquoise": (87, 255, 249),
    "dark_turquoise": (1, 251, 255),
    "light_sea_green": (47, 255, 245),
    "cadet_blue": (150, 251, 255),
    "dark_cyan": (0, 255, 255),
    "teal": (52, 254, 255),
    "cyan": (0, 255, 255),
    "aqua": (52, 254, 255),
    "light_cyan": (224, 255, 255),
    "pale_turquoise": (188, 255, 255),
    "powder_blue": (195, 249, 255),
    "light_blue": (193, 240, 255),
    "sky_blue": (147, 224, 255),
    "light_sky_blue": (138, 210, 255),
    "deep_sky_blue": (56, 189, 255),
    "dodger_blue": (30, 143, 255),
    "cornflower": (107, 158, 255),
    "steel_blue": (96, 183, 255),
    "royal_blue": (72, 118, 255),
    "blue": (0, 0, 255),
    "medium_blue": (0, 0, 230),
    "dark_blue": (0, 0, 180),
    "navy_blue": (0, 0, 150),
    "midnight_blue": (57, 57, 255),
    "lavender": (159, 127, 255),
    "thistle": (255, 226, 255),
    "plum": (255, 185, 255),
    "violet": (255, 139, 255),
    "orchid": (255, 132, 253),
    "fuchsia": (255, 0, 255),
    "magenta": (255, 0, 255),
    "medium_orchid": (224, 102, 255),
    "medium_purple": (172, 130, 255),
    "rebecca_purple": (170, 85, 255),
    "blue_violet": (155, 48, 255),
    "dark_violet": (179, 0, 255),
    "dark_orchid": (191, 64, 255),
    "dark_magenta": (230, 0, 230),
    "purple": (171, 36, 255),
    "web_purple": (200, 0, 200),
    "indigo": (144, 0, 255),
    "slate_blue": (133, 111, 255),
    "dark_slate_blue": (130, 111, 255),
    "medium_slate_blue": (131, 112, 255),
    "pink": (255, 191, 204),
    "light_pink": (255, 181, 193),
    "hot_pink": (255, 104, 182),
    "deep_pink": (255, 20, 145),
    "medium_violet_red": (255, 26, 171),
    "pale_violet_red": (255, 130, 172),
    "maroon": (255, 70, 141),
    "white": (255, 255, 255),
    "snow": (255, 249, 249),
    "honeydew": (239, 255, 239),
    "mint_cream": (244, 255, 249),
    "azure": (239, 255, 255),
    "alice_blue": (239, 247, 255),
    "ghost_white": (247, 247, 255),
    "seashell": (255, 244, 237),
    "beige": (255, 255, 229),
    "old_lace": (255, 247, 232),
    "floral_white": (255, 249, 239),
    "ivory": (255, 255, 239),
    "antique_white": (255, 240, 219),
    "linen": (255, 245, 235),
    "lavender_blush": (255, 239, 244),
    "misty_rose": (255, 226, 224),
}


def dsn_or_endpoint_to_mac(identifier: str) -> str:
    """
    Convert a MAC address, Amazon Device Serial Number (DSN), or Alexa `endpointId`
    into a normalized 17-character uppercase MAC address (`XX:XX:XX:XX:XX:XX`).

    If `identifier` is already a valid 12-hex-digit MAC address, normalizes it directly.
    Otherwise derives a deterministic MAC under the official Amazon Technologies Inc.
    OUI (`F0:F0:A4:XX:YY:ZZ`).
    """
    clean = identifier.strip()
    hex_only = "".join(ch for ch in clean if ch in "0123456789abcdefABCDEF")
    if len(hex_only) == 12 and all(ch in "0123456789abcdefABCDEF:-_. " for ch in clean):
        return normalize_mac(hex_only)

    digest = hashlib.sha256(clean.upper().encode("utf-8")).digest()
    return f"{AMAZON_OUI_PREFIX}:{digest[0]:02X}:{digest[1]:02X}:{digest[2]:02X}"


def rgb_to_nearest_alexa_color_name(r: int, g: int, b: int) -> str:
    """
    Map an 8-bit `(r, g, b)` color from Home Assistant to the closest official
    Alexa Smart Home `colorName` (`Alexa.ColorController`) using perceptual
    redmean-weighted Euclidean distance.
    """
    rc = max(0, min(255, int(r)))
    gc = max(0, min(255, int(g)))
    bc = max(0, min(255, int(b)))

    best_name = "white"
    best_dist = float("inf")
    for name, (pr, pg, pb) in ALEXA_COLOR_PALETTE.items():
        rmean = (rc + pr) / 2.0
        dr = rc - pr
        dg = gc - pg
        db = bc - pb
        dist = (2.0 + rmean / 256.0) * (dr * dr) + 4.0 * (dg * dg) + (2.0 + (255.0 - rmean) / 256.0) * (db * db)
        if dist < best_dist:
            best_dist = dist
            best_name = name
    return best_name


def alexa_color_name_to_rgb(color_name: str) -> Tuple[int, int, int]:
    """Return the `(r, g, b)` tuple for an Alexa `colorName`."""
    key = color_name.strip().lower().replace(" ", "_").replace("-", "_")
    return ALEXA_COLOR_PALETTE.get(key, (255, 255, 255))


def alexa_hsv_to_rgb(
    hue_deg: float, saturation_0_1: float, brightness_0_1: float = 1.0
) -> Tuple[int, int, int]:
    """
    Convert Alexa GraphQL `colorStateValue { hue (0..360), saturation (0..1), brightness (0..1) }`
    into an 8-bit `(r, g, b)` tuple.
    """
    h = (float(hue_deg) % 360.0) / 360.0
    s = max(0.0, min(1.0, float(saturation_0_1)))
    v = max(0.0, min(1.0, float(brightness_0_1)))
    if s > 1.0:
        s = min(1.0, s / 100.0)
    if v > 1.0:
        v = min(1.0, v / 100.0)
    rf, gf, bf = colorsys.hsv_to_rgb(h, s, v if v > 0 else 1.0)
    return (round(rf * 255), round(gf * 255), round(bf * 255))


def kelvin_to_alexa_color_temp_name(kelvin: int) -> str:
    """
    Map a color temperature in Kelvin (`2000..7000K`) to the nearest official
    Alexa `colorTemperatureName` (`warm_white`, `soft_white`, `white`, `daylight_white`, `cool_white`).
    """
    k = max(1800, min(10000, int(kelvin)))
    best_name = "soft_white"
    best_diff = float("inf")
    for name, preset_k in ALEXA_COLOR_TEMP_PRESETS.items():
        diff = abs(k - preset_k)
        if diff < best_diff:
            best_diff = diff
            best_name = name
    return best_name


def parse_amazon_ack_ffs_barcode(raw_barcode: str) -> Dict[str, Any]:
    """
    Parse an Amazon Basics or Sengled "Works with Alexa Only" Frustration-Free Setup (FFS)
    2D DataMatrix / QR barcode, Device Serial Number (DSN), ASIN, or model string.

    Supports:
    - JSON FFS payloads: `{"dsn": "G091...", "apid": "...", "mac": "..."}`
    - Key-value FFS strings: `DSN:G091...;MAC:F0F0A4112233;MODEL:13aSB-A800ST-Q1T`
    - Amazon setup URLs: `https://www.amazon.com/dp/B0C332SMK8?dsn=G091...`
    - Direct Model / ASIN / DSN strings: `13aSB-A800ST-Q1T`, `13aSB-A806ST-Q1R_NA`,
      `13aSB-A806ST-Q1T_EU`, `13aSB-A806ST-Q1T_JP`, `B0C332SMK8`, `B0CG5VDC8P`,
      `WS30-01`, `WP52-2`, `B11-N11`, `B11-N1E`.
    """
    text = raw_barcode.strip()
    upper = text.upper()

    dsn: Optional[str] = None
    explicit_mac: Optional[str] = None
    model = "13ASB-A800ST-Q1T"
    pin: Optional[str] = None

    # 1. Check if JSON formatted FFS barcode
    if text.startswith("{") and text.endswith("}"):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                dsn = str(obj.get("dsn") or obj.get("DSN") or obj.get("serialNumber") or "").strip() or None
                explicit_mac = str(obj.get("mac") or obj.get("MAC") or "").strip() or None
                pin = str(obj.get("pin") or obj.get("PIN") or obj.get(" setupPin") or "").strip() or None
                if obj.get("model") or obj.get("apid"):
                    model = str(obj.get("model") or obj.get("apid")).strip().upper()
        except json.JSONDecodeError:
            pass

    # 2. Check key-value pairs (e.g. DSN:G09...;MAC:...;PIN:...)
    if ";" in text or ("DSN:" in upper or "MAC:" in upper):
        for part in re.split(r"[;&,\s]+", text):
            if ":" in part or "=" in part:
                k, v = re.split(r"[:=]", part, maxsplit=1)
                ku = k.strip().upper()
                vv = v.strip()
                if ku in ("DSN", "SN", "SERIAL"):
                    dsn = vv
                elif ku == "MAC":
                    explicit_mac = vv
                elif ku in ("MODEL", "SKU", "ASIN"):
                    model = vv.upper()
                elif ku == "PIN":
                    pin = vv

    # 3. Check known model / ASIN substrings
    if any(tok in upper for tok in ("A806ST-Q1R", "B0C3349GNR")):
        model = "13ASB-A806ST-Q1R"
    elif any(tok in upper for tok in ("A806ST-Q1T", "A800ST-Q1T", "B0C332SMK8", "B0CG5VDC8P", "B0CYPQM746", "B0C333MTB5")):
        model = "13ASB-A800ST-Q1T"
    elif any(tok in upper for tok in ("WS30-01", "WP52-2", "B0CW5D561J", "B0CPY295K7", "B0CRKTC31J", "B0CMXR538P", "B0CMXRGBNH")):
        model = "WP52-2"
    elif any(tok in upper for tok in ("B11-N11", "B11-N1E", "B12-N11", "B12-N1E", "B21-N1E")):
        for candidate in ("B11-N11", "B11-N1E", "B12-N11", "B12-N1E", "B21-N1E"):
            if candidate in upper:
                model = candidate
                break

    # 4. Extract 16-char Amazon DSN (`G0...` / `G8...`) if present
    if not dsn:
        dsn_match = re.search(r"\b(G[0-9A-Z]{15})\b", upper)
        if dsn_match:
            dsn = dsn_match.group(1)

    derived_mac = dsn_or_endpoint_to_mac(explicit_mac or dsn or text)
    slug = mac_to_slug(derived_mac)

    return {
        "raw_barcode": text,
        "model": model,
        "dsn": dsn or f"ACK-{slug.upper()}",
        "mac": derived_mac,
        "slug": slug,
        "setup_pin": pin,
        "chipset": "Espressif ESP32-PICO-V3-ZERO (FCC ID: 2AC7Z-ESP32PICOV30)",
        "bridge_registration_cli": f'sengled-bridge serve --ack-light "{derived_mac},{model},Amazon Alexa Light"',
        "bridge_api_register_payload": {
            "identifier": explicit_mac or dsn or derived_mac,
            "model": model,
            "name": f"Amazon Basics ({model}) {derived_mac[-5:]}",
        },
    }


# ---------------------------------------------------------------------------
# Amazon Alexa Smart Home GraphQL (`/nexus/v1/graphql`) Queries & Mutations
# ---------------------------------------------------------------------------
GRAPHQL_ENDPOINTS_QUERY = """query Endpoints {
  endpoints {
    items {
      id
      friendlyName
      displayCategories {
        primary {
          value
        }
      }
      serialNumber {
        value {
          text
        }
      }
      enablement
      model {
        value {
          text
        }
      }
      manufacturer {
        value {
          text
        }
      }
      features {
        name
        instance
        operations {
          name
        }
        properties {
          name
          ... on Power {
            powerStateValue
          }
          ... on Brightness {
            brightnessStateValue
          }
          ... on Color {
            colorStateValue {
              hue
              saturation
              brightness
            }
          }
          ... on ColorTemperature {
            colorTemperatureInKelvinStateValue
          }
          ... on ToggleState {
            toggleStateValue
          }
        }
      }
    }
  }
}"""

GRAPHQL_LIGHT_STATE_QUERY = """query getPowerBrightnessColorColorTempStates($endpointId: String!) {
  endpoint(id: $endpointId) {
    features {
      name
      properties {
        name
        ... on Power {
          powerStateValue
        }
        ... on Brightness {
          brightnessStateValue
        }
        ... on Color {
          colorStateValue {
            hue
            saturation
            brightness
          }
        }
        ... on ColorTemperature {
          colorTemperatureInKelvinStateValue
        }
      }
    }
  }
}"""

GRAPHQL_SET_ENDPOINT_FEATURES_MUTATION = """mutation updatePowerFeatureForEndpoints($featureControlRequests: [FeatureControlRequest!]!) {
  setEndpointFeatures(
    setEndpointFeaturesInput: {
      featureControlRequests: $featureControlRequests
    }
  ) {
    featureControlResponses {
      endpointId
      featureOperationName
      __typename
    }
    errors {
      endpointId
      code
      __typename
    }
    __typename
  }
}"""


def extract_features_state(features: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Extract normalized light state (`is_on`, `ha_brightness`, `color_temp_kelvin`,
    `rgb`, `color_mode`, `supported_operations`) from an Alexa GraphQL `features` array.
    """
    out: Dict[str, Any] = {
        "supported_features": [],
        "supported_operations": [],
    }
    for feat in features or []:
        if not isinstance(feat, dict):
            continue
        fname = str(feat.get("name", "") or "").strip()
        if fname and fname not in out["supported_features"]:
            out["supported_features"].append(fname)

        for op in feat.get("operations") or []:
            if isinstance(op, dict) and op.get("name"):
                op_name = str(op["name"])
                if op_name not in out["supported_operations"]:
                    out["supported_operations"].append(op_name)

        for prop in feat.get("properties") or []:
            if not isinstance(prop, dict):
                continue
            if fname == "power" and prop.get("powerStateValue") in ("ON", "OFF"):
                out["is_on"] = prop["powerStateValue"] == "ON"
            elif fname == "toggle" and "is_on" not in out and prop.get("toggleStateValue") in ("ON", "OFF"):
                out["is_on"] = prop["toggleStateValue"] == "ON"
            elif fname == "brightness" and prop.get("brightnessStateValue") is not None:
                bri_pct = max(0, min(100, int(prop["brightnessStateValue"])))
                out["brightness_pct"] = bri_pct
                out["ha_brightness"] = round((bri_pct / 100.0) * 255)
            elif fname == "colorTemperature" and prop.get("colorTemperatureInKelvinStateValue") is not None:
                kelvin = int(prop["colorTemperatureInKelvinStateValue"])
                if kelvin > 0:
                    out["color_temp_kelvin"] = max(2000, min(7000, kelvin))
                    out.setdefault("color_mode", "color_temp")
            elif fname == "color" and isinstance(prop.get("colorStateValue"), dict):
                cval = prop["colorStateValue"]
                if cval.get("hue") is not None and cval.get("saturation") is not None:
                    out["rgb"] = alexa_hsv_to_rgb(
                        float(cval["hue"]),
                        float(cval["saturation"]),
                        float(cval.get("brightness", 1.0)),
                    )
                    out["color_mode"] = "rgb"

    return out


def parse_graphql_endpoints_response(resp_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Parse the JSON response from `POST /nexus/v1/graphql` (`EndpointsQuery`) and
    return all discovered lighting / switch / plug endpoints.
    """
    items = (
        resp_json.get("data", {})
        .get("endpoints", {})
        .get("items", [])
        if isinstance(resp_json, dict)
        else []
    )
    results: List[Dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        endpoint_id = str(item.get("id", "") or "").strip()
        if not endpoint_id:
            continue
        friendly_name = str(item.get("friendlyName", "") or "").strip() or "Alexa Smart Light"
        category = (
            str((item.get("displayCategories") or {}).get("primary", {}).get("value", "LIGHT"))
            .strip()
            .upper()
        )
        serial = str(((item.get("serialNumber") or {}).get("value") or {}).get("text", "") or "").strip()
        model_text = str(((item.get("model") or {}).get("value") or {}).get("text", "") or "").strip()
        mfr_text = str(((item.get("manufacturer") or {}).get("value") or {}).get("text", "") or "").strip()
        enablement = str(item.get("enablement", "ENABLED") or "ENABLED").upper()

        feat_state = extract_features_state(item.get("features") or [])
        has_power = "power" in feat_state["supported_features"] or "turnOn" in feat_state["supported_operations"]
        if category not in ("LIGHT", "SMARTPLUG", "SWITCH") and not has_power:
            continue

        # Determine canonical model code in our catalog
        upper_meta = f"{model_text} {mfr_text} {friendly_name}".upper()
        if "A806ST-Q1R" in upper_meta:
            catalog_model = "13ASB-A806ST-Q1R"
        elif any(tok in upper_meta for tok in ("13ASB", "A800ST", "A806ST", "AMAZON BASICS", "AMAZON")):
            if category in ("SMARTPLUG", "SWITCH") or "color" not in feat_state["supported_features"]:
                catalog_model = (
                    "WP52-2"
                    if "brightness" not in feat_state["supported_features"]
                    else "13ASB-A806ST-Q1R"
                )
            else:
                catalog_model = "13ASB-A800ST-Q1T"
        elif "SENGLED" in upper_meta:
            catalog_model = model_text or ("B11-N1E" if "color" in feat_state["supported_features"] else "B11-N11")
        else:
            catalog_model = model_text or (
                "13ASB-A800ST-Q1T" if "color" in feat_state["supported_features"] else "13ASB-A806ST-Q1R"
            )

        derived_mac = dsn_or_endpoint_to_mac(serial or endpoint_id)
        results.append(
            {
                "endpoint_id": endpoint_id,
                "friendly_name": friendly_name,
                "display_category": category,
                "dsn": serial or endpoint_id,
                "mac": derived_mac,
                "model": catalog_model,
                "raw_model": model_text,
                "manufacturer": mfr_text or "Amazon Basics",
                "enabled": enablement == "ENABLED",
                **feat_state,
            }
        )
    return results


def parse_graphql_light_state_response(resp_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse the JSON response from `POST /nexus/v1/graphql` (`GRAPHQL_LIGHT_STATE_QUERY`)
    into a normalized state dictionary.
    """
    if isinstance(resp_json, list) and resp_json:
        resp_json = resp_json[0]
    features = (
        resp_json.get("data", {})
        .get("endpoint", {})
        .get("features", [])
        if isinstance(resp_json, dict)
        else []
    )
    return extract_features_state(features)


def build_graphql_feature_control_requests(
    endpoint_id: str, ha_cmd: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Build the `featureControlRequests` array for `GRAPHQL_SET_ENDPOINT_FEATURES_MUTATION`
    from a Home Assistant JSON light command (`state`, `brightness`, `color_temp_kelvin` / `color_temp`).
    """
    state_str = str(ha_cmd.get("state", "ON")).upper()
    if state_str == "OFF":
        return [
            {
                "endpointId": endpoint_id,
                "featureName": "power",
                "featureOperationName": "turnOff",
            }
        ]

    reqs: List[Dict[str, Any]] = [
        {
            "endpointId": endpoint_id,
            "featureName": "power",
            "featureOperationName": "turnOn",
        }
    ]

    if "brightness" in ha_cmd and ha_cmd["brightness"] is not None:
        bri_pct = max(1, min(100, round((int(ha_cmd["brightness"]) / 255.0) * 100)))
        reqs.append(
            {
                "endpointId": endpoint_id,
                "featureName": "brightness",
                "featureOperationName": "setBrightness",
                "payload": {"brightness": bri_pct},
            }
        )

    if "color_temp_kelvin" in ha_cmd or "color_temp" in ha_cmd:
        kelvin = (
            int(ha_cmd["color_temp_kelvin"])
            if "color_temp_kelvin" in ha_cmd
            else mireds_to_kelvin(float(ha_cmd["color_temp"]))
        )
        clamped_k = max(2000, min(7000, kelvin))
        reqs.append(
            {
                "endpointId": endpoint_id,
                "featureName": "colorTemperature",
                "featureOperationName": "setColorTemperature",
                "payload": {"colorTemperatureInKelvin": clamped_k},
            }
        )

    return reqs


def build_phoenix_state_put_payload(
    entity_id: str, ha_cmd: Dict[str, Any], entity_type: str = "APPLIANCE"
) -> Dict[str, Any]:
    """
    Build the `PUT /api/phoenix/state` (`controlRequests`) payload used by Alexa
    for `setColor` (`colorName`), `setColorTemperature`, `setBrightness`, and `turnOn`/`turnOff`.
    """
    state_str = str(ha_cmd.get("state", "ON")).upper()
    if state_str == "OFF":
        return {
            "controlRequests": [
                {
                    "entityId": entity_id,
                    "entityType": entity_type,
                    "parameters": {"action": "turnOff"},
                }
            ]
        }

    requests: List[Dict[str, Any]] = [
        {
            "entityId": entity_id,
            "entityType": entity_type,
            "parameters": {"action": "turnOn"},
        }
    ]

    if "color" in ha_cmd and isinstance(ha_cmd["color"], dict):
        c = ha_cmd["color"]
        color_name = rgb_to_nearest_alexa_color_name(
            int(c.get("r", 255)), int(c.get("g", 255)), int(c.get("b", 255))
        )
        requests.append(
            {
                "entityId": entity_id,
                "entityType": entity_type,
                "parameters": {"action": "setColor", "colorName": color_name},
            }
        )
    elif "color_temp_kelvin" in ha_cmd or "color_temp" in ha_cmd:
        kelvin = (
            int(ha_cmd["color_temp_kelvin"])
            if "color_temp_kelvin" in ha_cmd
            else mireds_to_kelvin(float(ha_cmd["color_temp"]))
        )
        ct_name = kelvin_to_alexa_color_temp_name(kelvin)
        requests.append(
            {
                "entityId": entity_id,
                "entityType": entity_type,
                "parameters": {
                    "action": "setColorTemperature",
                    "colorTemperatureName": ct_name,
                },
            }
        )

    if "brightness" in ha_cmd and ha_cmd["brightness"] is not None:
        bri_pct = max(1, min(100, round((int(ha_cmd["brightness"]) / 255.0) * 100)))
        requests.append(
            {
                "entityId": entity_id,
                "entityType": entity_type,
                "parameters": {"action": "setBrightness", "brightness": str(bri_pct)},
            }
        )

    return {"controlRequests": requests}


def build_behaviors_smarthome_batch_payload(
    target_entity_id: str,
    ha_cmd: Dict[str, Any],
    customer_id: str = "local_bridge",
) -> Dict[str, Any]:
    """
    Build the `POST /api/behaviors/preview` (`Alexa.SmartHome.Batch`, skillId
    `amzn1.ask.1p.smarthome`) payload that executes batched power, brightness,
    colorTemperature, and `setColor` (`colorName`) operations on an Alexa-only bulb.
    """
    state_str = str(ha_cmd.get("state", "ON")).upper()
    operations: List[Dict[str, Any]] = []

    if state_str == "OFF":
        operations.append({"type": "turnOff"})
    else:
        operations.append({"type": "turnOn"})
        if "brightness" in ha_cmd and ha_cmd["brightness"] is not None:
            bri_pct = max(1, min(100, round((int(ha_cmd["brightness"]) / 255.0) * 100)))
            operations.append({"type": "setBrightness", "brightness": bri_pct})

        if "color" in ha_cmd and isinstance(ha_cmd["color"], dict):
            c = ha_cmd["color"]
            color_name = rgb_to_nearest_alexa_color_name(
                int(c.get("r", 255)), int(c.get("g", 255)), int(c.get("b", 255))
            )
            operations.append({"type": "setColor", "colorName": color_name})
        elif "color_temp_kelvin" in ha_cmd or "color_temp" in ha_cmd:
            kelvin = (
                int(ha_cmd["color_temp_kelvin"])
                if "color_temp_kelvin" in ha_cmd
                else mireds_to_kelvin(float(ha_cmd["color_temp"]))
            )
            ct_name = kelvin_to_alexa_color_temp_name(kelvin)
            operations.append(
                {"type": "setColorTemperature", "colorTemperatureName": ct_name}
            )

    sequence_node = {
        "@type": "com.amazon.alexa.behaviors.model.Sequence",
        "startNode": {
            "@type": "com.amazon.alexa.behaviors.model.SerialNode",
            "name": None,
            "nodesToExecute": [
                {
                    "@type": "com.amazon.alexa.behaviors.model.OpaquePayloadOperationNode",
                    "type": "Alexa.SmartHome.Batch",
                    "skillId": "amzn1.ask.1p.smarthome",
                    "operationPayload": {
                        "target": target_entity_id,
                        "customerId": customer_id,
                        "operations": operations,
                    },
                    "tag": None,
                    "name": None,
                }
            ],
        },
    }
    return {
        "behaviorId": "PREVIEW",
        "sequenceJson": json.dumps(sequence_node, separators=(",", ":")),
        "status": "ENABLED",
    }


def build_alexa_voice_command_and_ha_service_payload(
    friendly_name: str,
    ha_cmd: Dict[str, Any],
    echo_entity_id: str = "media_player.echo_dot",
) -> Dict[str, Any]:
    """
    Translate a Home Assistant light command into natural-language Alexa voice commands
    and a ready-to-execute Home Assistant `media_player.play_media` service call
    (for users bridging via Home Assistant's `alexa_media` or `alexa_devices`).
    """
    name = friendly_name.strip() or "Smart Light"
    state_str = str(ha_cmd.get("state", "ON")).upper()
    phrases: List[str] = []

    if state_str == "OFF":
        phrases.append(f"turn off {name}")
    else:
        if "color" in ha_cmd and isinstance(ha_cmd["color"], dict):
            c = ha_cmd["color"]
            color_name = rgb_to_nearest_alexa_color_name(
                int(c.get("r", 255)), int(c.get("g", 255)), int(c.get("b", 255))
            ).replace("_", " ")
            phrases.append(f"set {name} to {color_name}")
        elif "color_temp_kelvin" in ha_cmd or "color_temp" in ha_cmd:
            kelvin = (
                int(ha_cmd["color_temp_kelvin"])
                if "color_temp_kelvin" in ha_cmd
                else mireds_to_kelvin(float(ha_cmd["color_temp"]))
            )
            ct_spoken = kelvin_to_alexa_color_temp_name(kelvin).replace("_", " ")
            phrases.append(f"set {name} to {ct_spoken}")

        if "brightness" in ha_cmd and ha_cmd["brightness"] is not None:
            bri_pct = max(1, min(100, round((int(ha_cmd["brightness"]) / 255.0) * 100)))
            phrases.append(f"set {name} brightness to {bri_pct} percent")

        if not phrases:
            phrases.append(f"turn on {name}")

    combined_phrase = " and ".join(phrases)
    return {
        "friendly_name": name,
        "voice_phrases": phrases,
        "combined_voice_command": combined_phrase,
        "ha_alexa_media_service_call": {
            "domain": "media_player",
            "service": "play_media",
            "target": {"entity_id": echo_entity_id},
            "service_data": {
                "media_content_id": combined_phrase,
                "media_content_type": "custom",
            },
        },
    }


# ---------------------------------------------------------------------------
# State Model & Controller for "Works with Alexa Only" (ACK) Lights
# ---------------------------------------------------------------------------
@dataclass
class AlexaACKLightState:
    """
    In-memory state representation of an Amazon "Works with Alexa Only" (ACK or
    Echo-paired) light bridged into Home Assistant via `sengled-local-ha-bridge`.
    """

    mac: str
    endpoint_id: str = ""
    dsn: str = ""
    model: str = "13ASB-A800ST-Q1T"
    name: str = "Amazon Basics Smart Bulb"
    manufacturer: str = "Amazon Basics"
    hue_light_id: int = 1
    is_on: bool = False
    ha_brightness: int = 255
    color_temp_kelvin: int = 2700
    rgb: Tuple[int, int, int] = (255, 255, 255)
    color_mode: str = "color_temp"
    last_alexa_color_name: str = "white"
    last_seen_epoch: float = field(default_factory=time.time)

    def apply_ha_command(self, cmd_dict: Dict[str, Any]) -> None:
        """Apply a Home Assistant JSON command dictionary to this light's state."""
        self.last_seen_epoch = time.time()
        state_str = str(cmd_dict.get("state", "ON")).upper()
        if state_str == "OFF":
            self.is_on = False
            return

        self.is_on = True
        if "brightness" in cmd_dict and cmd_dict["brightness"] is not None:
            self.ha_brightness = max(1, min(255, int(cmd_dict["brightness"])))

        if "color" in cmd_dict and isinstance(cmd_dict["color"], dict):
            c = cmd_dict["color"]
            r = max(0, min(255, int(c.get("r", 255))))
            g = max(0, min(255, int(c.get("g", 255))))
            b = max(0, min(255, int(c.get("b", 255))))
            self.rgb = (r, g, b)
            self.color_mode = "rgb"
            self.last_alexa_color_name = rgb_to_nearest_alexa_color_name(r, g, b)
        elif "color_temp_kelvin" in cmd_dict or "color_temp" in cmd_dict:
            kelvin = (
                int(cmd_dict["color_temp_kelvin"])
                if "color_temp_kelvin" in cmd_dict
                else mireds_to_kelvin(float(cmd_dict["color_temp"]))
            )
            self.color_temp_kelvin = max(2000, min(7000, kelvin))
            self.color_mode = "color_temp"

    def apply_graphql_state(self, state_info: Dict[str, Any]) -> bool:
        """Apply state fields parsed from an Alexa GraphQL response."""
        if not state_info:
            return False
        self.last_seen_epoch = time.time()
        if "is_on" in state_info:
            self.is_on = bool(state_info["is_on"])
        if "ha_brightness" in state_info and int(state_info["ha_brightness"]) > 0:
            self.ha_brightness = max(1, min(255, int(state_info["ha_brightness"])))
        if "color_temp_kelvin" in state_info:
            self.color_temp_kelvin = int(state_info["color_temp_kelvin"])
            if state_info.get("color_mode") == "color_temp":
                self.color_mode = "color_temp"
        if "rgb" in state_info:
            self.rgb = tuple(state_info["rgb"])  # type: ignore[assignment]
            self.color_mode = "rgb"
            self.last_alexa_color_name = rgb_to_nearest_alexa_color_name(*self.rgb)
        return True


# ---------------------------------------------------------------------------
# 100% Local LAN Echo / Philips Hue V1 Emulator for Bidirectional State Sync
# ---------------------------------------------------------------------------
def build_hue_upnp_description_xml(
    advertise_ip: str,
    http_port: int = 8080,
    bridge_id: str = "F0F0A4FFFE000001",
) -> str:
    """
    Build the UPnP `/description.xml` document served to local Amazon Echo devices
    for local Philips Hue V1 bridge discovery.
    """
    serial = bridge_id.lower()
    return f"""<?xml version="1.0" encoding="UTF-8" ?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
  <specVersion>
    <major>1</major>
    <minor>0</minor>
  </specVersion>
  <URLBase>http://{advertise_ip}:{http_port}/</URLBase>
  <device>
    <deviceType>urn:schemas-upnp-org:device:basic:1</deviceType>
    <friendlyName>Sengled &amp; Amazon ACK Local Bridge ({advertise_ip})</friendlyName>
    <manufacturer>Royal Philips Electronics</manufacturer>
    <manufacturerURL>http://www.philips.com</manufacturerURL>
    <modelDescription>Philips hue Personal Wireless Lighting</modelDescription>
    <modelName>Philips hue bridge 2015</modelName>
    <modelNumber>BSB002</modelNumber>
    <modelURL>http://www.meethue.com</modelURL>
    <serialNumber>{serial}</serialNumber>
    <UDN>uuid:2f402f80-da50-11e1-9b23-{serial[-12:]}</UDN>
  </device>
</root>"""


def build_ssdp_search_response(
    advertise_ip: str,
    http_port: int = 8080,
    bridge_id: str = "F0F0A4FFFE000001",
) -> str:
    """Build a UPnP / Hue SSDP `M-SEARCH` HTTP 200 OK UDP response packet."""
    serial = bridge_id.lower()
    uuid_str = f"uuid:2f402f80-da50-11e1-9b23-{serial[-12:]}"
    lines = [
        "HTTP/1.1 200 OK",
        "HOST: 239.255.255.250:1900",
        "EXT:",
        "CACHE-CONTROL: max-age=100",
        f"LOCATION: http://{advertise_ip}:{http_port}/description.xml",
        "SERVER: Linux/3.14.0 UPnP/1.0 IpBridge/1.24.0",
        f"hue-bridgeid: {bridge_id.upper()}",
        "ST: urn:schemas-upnp-org:device:basic:1",
        f"USN: {uuid_str}::urn:schemas-upnp-org:device:basic:1",
        "",
        "",
    ]
    return "\r\n".join(lines)


def build_hue_v1_light_entry(bulb: AlexaACKLightState) -> Dict[str, Any]:
    """
    Build a Philips Hue V1 `/api/<user>/lights/<id>` JSON representation of an
    `AlexaACKLightState` so an Amazon Echo on the local LAN can discover and sync it.
    """
    r, g, b = bulb.rgb
    h_0_1, s_0_1, _ = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    hue_u16 = round(h_0_1 * 65535) % 65536
    sat_u8 = max(0, min(254, round(s_0_1 * 254)))
    bri_u8 = max(1, min(254, bulb.ha_brightness))
    ct_mireds = max(153, min(500, kelvin_to_mireds(bulb.color_temp_kelvin)))
    colormode = "hs" if bulb.color_mode == "rgb" else "ct"

    return {
        "state": {
            "on": bool(bulb.is_on),
            "bri": bri_u8,
            "hue": hue_u16,
            "sat": sat_u8,
            "ct": ct_mireds,
            "xy": [0.3127, 0.3290],
            "alert": "none",
            "effect": "none",
            "colormode": colormode,
            "reachable": True,
        },
        "type": "Extended color light",
        "name": bulb.name,
        "modelid": "LCT015",
        "manufacturername": "Philips",
        "productname": "Hue color lamp",
        "uniqueid": f"{bulb.mac.lower()}-0b",
        "swversion": "1.104.2",
    }


def apply_hue_v1_state_put(
    bulb: AlexaACKLightState, hue_put: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Apply a local Echo `PUT /api/<user>/lights/<id>/state` payload to `bulb`
    and return the standard Hue V1 `[{"success": {"/lights/<id>/state/...": val}}]` array.
    """
    lid = bulb.hue_light_id
    ack_list: List[Dict[str, Any]] = []
    bulb.last_seen_epoch = time.time()

    if "on" in hue_put:
        bulb.is_on = bool(hue_put["on"])
        ack_list.append({"success": {f"/lights/{lid}/state/on": bulb.is_on}})

    if "bri" in hue_put:
        bri_val = max(1, min(254, int(hue_put["bri"])))
        bulb.ha_brightness = max(1, min(255, round((bri_val / 254.0) * 255)))
        bulb.is_on = True
        ack_list.append({"success": {f"/lights/{lid}/state/bri": bri_val}})

    if "ct" in hue_put:
        ct_val = max(153, min(500, int(hue_put["ct"])))
        bulb.color_temp_kelvin = mireds_to_kelvin(ct_val)
        bulb.color_mode = "color_temp"
        bulb.is_on = True
        ack_list.append({"success": {f"/lights/{lid}/state/ct": ct_val}})

    if "hue" in hue_put or "sat" in hue_put:
        r0, g0, b0 = bulb.rgb
        h0, s0, _ = colorsys.rgb_to_hsv(r0 / 255.0, g0 / 255.0, b0 / 255.0)
        hue_u16 = int(hue_put.get("hue", round(h0 * 65535))) % 65536
        sat_u8 = max(0, min(254, int(hue_put.get("sat", round(s0 * 254)))))
        rf, gf, bf = colorsys.hsv_to_rgb(hue_u16 / 65535.0, sat_u8 / 254.0, 1.0)
        bulb.rgb = (round(rf * 255), round(gf * 255), round(bf * 255))
        bulb.color_mode = "rgb"
        bulb.last_alexa_color_name = rgb_to_nearest_alexa_color_name(*bulb.rgb)
        bulb.is_on = True
        if "hue" in hue_put:
            ack_list.append({"success": {f"/lights/{lid}/state/hue": hue_u16}})
        if "sat" in hue_put:
            ack_list.append({"success": {f"/lights/{lid}/state/sat": sat_u8}})

    return ack_list


# ---------------------------------------------------------------------------
# Unified Controller for "Works with Alexa Only" Lights in Sengled Bridge
# ---------------------------------------------------------------------------
class AlexaACKController:
    """
    Controller for Amazon "Works with Alexa Only" (ACK & Echo-Paired) lights.

    Supports:
    - Registering lights by MAC, DSN, FFS 2D Barcode, or Alexa `endpointId`
    - Auto-discovering "Works with Alexa Only" lights via Amazon's `/nexus/v1/graphql`
    - Executing On/Off, Brightness, Color Temperature, and RGB Color commands via:
      1. Direct Alexa GraphQL (`/nexus/v1/graphql`) + Behaviors (`/api/behaviors/preview`) / Phoenix (`/api/phoenix/state`)
      2. Home Assistant `alexa_media` / `alexa_devices` MQTT Command Relay
      3. Local LAN Echo / Philips Hue V1 Emulation (`/description.xml` & `/api/<user>/lights/<id>`)
    """

    def __init__(
        self,
        alexa_cookie: str = "",
        alexa_domain: str = "amazon.com",
        alexa_csrf: str = "",
        echo_entity_id: str = "media_player.echo_dot",
        on_state_change: Optional[Callable[[AlexaACKLightState], None]] = None,
        http_transport: Optional[
            Callable[[str, str, Dict[str, str], Optional[bytes]], Dict[str, Any]]
        ] = None,
    ):
        self.alexa_cookie = alexa_cookie.strip()
        self.alexa_domain = ALEXA_DOMAIN_MAP.get(
            alexa_domain.strip().lower(), alexa_domain.strip().lower() or "alexa.amazon.com"
        )
        if not self.alexa_domain.startswith("alexa."):
            self.alexa_domain = f"alexa.{self.alexa_domain}"
        self.alexa_csrf = alexa_csrf.strip() or self._extract_csrf_from_cookie(self.alexa_cookie)
        self.echo_entity_id = echo_entity_id
        self.on_state_change = on_state_change
        self._http_transport = http_transport or self._default_http_transport

        self.bulbs: Dict[str, AlexaACKLightState] = {}
        self.hue_id_to_mac: Dict[int, str] = {}
        self.endpoint_id_to_mac: Dict[str, str] = {}
        self._next_hue_id: int = 1

        self._ssdp_sock: Optional[socket.socket] = None
        self._ssdp_thread: Optional[threading.Thread] = None
        self._ssdp_stop = False

    @staticmethod
    def _extract_csrf_from_cookie(cookie_str: str) -> str:
        match = re.search(r"(?:^|;\s*)csrf=([^;\s]+)", cookie_str)
        return match.group(1) if match else ""

    def configure_alexa_credentials(
        self,
        alexa_cookie: str,
        alexa_domain: str = "amazon.com",
        alexa_csrf: str = "",
    ) -> None:
        """Update the Amazon Alexa session cookie and regional domain at runtime."""
        self.alexa_cookie = alexa_cookie.strip()
        clean_dom = alexa_domain.strip().lower()
        self.alexa_domain = ALEXA_DOMAIN_MAP.get(clean_dom, clean_dom or "alexa.amazon.com")
        if not self.alexa_domain.startswith("alexa."):
            self.alexa_domain = f"alexa.{self.alexa_domain}"
        self.alexa_csrf = alexa_csrf.strip() or self._extract_csrf_from_cookie(self.alexa_cookie)

    def _build_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {
            "Accept": "application/json; charset=utf-8",
            "Content-Type": "application/json; charset=utf-8",
            "Origin": f"https://{self.alexa_domain}",
            "Referer": f"https://{self.alexa_domain}/spa/index.html",
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 PitanguiBridge/2.2.595606.0"
            ),
        }
        if self.alexa_cookie:
            headers["Cookie"] = self.alexa_cookie
        if self.alexa_csrf:
            headers["csrf"] = self.alexa_csrf
        return headers

    @staticmethod
    def _default_http_transport(
        method: str,
        url: str,
        headers: Dict[str, str],
        body: Optional[bytes] = None,
    ) -> Dict[str, Any]:
        req = urllib.request.Request(url=url, data=body, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw.strip() else {}

    def register_bulb(
        self,
        identifier: str,
        model: str = "13ASB-A800ST-Q1T",
        name: Optional[str] = None,
        endpoint_id: str = "",
        dsn: str = "",
        manufacturer: str = "Amazon Basics",
    ) -> AlexaACKLightState:
        """
        Register an Amazon "Works with Alexa Only" light by MAC, DSN, FFS barcode,
        or Alexa `endpointId`.
        """
        norm_mac = dsn_or_endpoint_to_mac(identifier)
        if norm_mac not in self.bulbs:
            hue_id = self._next_hue_id
            self._next_hue_id += 1
            bulb = AlexaACKLightState(
                mac=norm_mac,
                endpoint_id=endpoint_id or (identifier if identifier.startswith("amzn1.") else ""),
                dsn=dsn or identifier,
                model=model.strip().upper() or "13ASB-A800ST-Q1T",
                name=name or f"Amazon Alexa Light ({model}) {norm_mac[-5:]}",
                manufacturer=manufacturer,
                hue_light_id=hue_id,
            )
            self.bulbs[norm_mac] = bulb
            self.hue_id_to_mac[hue_id] = norm_mac
        else:
            bulb = self.bulbs[norm_mac]
            if endpoint_id:
                bulb.endpoint_id = endpoint_id
            if dsn:
                bulb.dsn = dsn
            if name:
                bulb.name = name
            if model:
                bulb.model = model.strip().upper()

        if bulb.endpoint_id:
            self.endpoint_id_to_mac[bulb.endpoint_id] = norm_mac
        return bulb

    def get_bulb_by_hue_id(self, hue_id: int) -> Optional[AlexaACKLightState]:
        mac = self.hue_id_to_mac.get(int(hue_id))
        return self.bulbs.get(mac) if mac else None

    def discover_from_alexa_graphql(self) -> List[AlexaACKLightState]:
        """
        Query `POST https://<alexa_domain>/nexus/v1/graphql` using the configured
        Amazon session cookie and register all discovered Alexa Smart Home lights.
        """
        if not self.alexa_cookie:
            raise ValueError("alexa_cookie is required to query /nexus/v1/graphql.")

        url = f"https://{self.alexa_domain}/nexus/v1/graphql"
        body = json.dumps({"query": GRAPHQL_ENDPOINTS_QUERY, "variables": {}}).encode("utf-8")
        resp_json = self._http_transport("POST", url, self._build_headers(), body)
        parsed_endpoints = parse_graphql_endpoints_response(resp_json)

        discovered_bulbs: List[AlexaACKLightState] = []
        for ep in parsed_endpoints:
            bulb = self.register_bulb(
                identifier=ep["mac"],
                model=ep["model"],
                name=ep["friendly_name"],
                endpoint_id=ep["endpoint_id"],
                dsn=ep["dsn"],
                manufacturer=ep["manufacturer"],
            )
            bulb.apply_graphql_state(ep)
            if self.on_state_change:
                self.on_state_change(bulb)
            discovered_bulbs.append(bulb)
        return discovered_bulbs

    def poll_bulb_state_graphql(self, mac: str) -> Optional[Dict[str, Any]]:
        """
        Poll the live state of a registered Alexa-only light via
        `POST https://<alexa_domain>/nexus/v1/graphql` (`GRAPHQL_LIGHT_STATE_QUERY`).
        """
        norm_mac = dsn_or_endpoint_to_mac(mac)
        bulb = self.bulbs.get(norm_mac)
        if not bulb or not bulb.endpoint_id or not self.alexa_cookie:
            return None

        url = f"https://{self.alexa_domain}/nexus/v1/graphql"
        body = json.dumps(
            {
                "query": GRAPHQL_LIGHT_STATE_QUERY,
                "variables": {"endpointId": bulb.endpoint_id},
            }
        ).encode("utf-8")
        resp_json = self._http_transport("POST", url, self._build_headers(), body)
        state_info = parse_graphql_light_state_response(resp_json)
        if state_info:
            bulb.apply_graphql_state(state_info)
            if self.on_state_change:
                self.on_state_change(bulb)
        return state_info

    def dispatch_ha_command(self, mac: str, cmd_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a Home Assistant light command (`state`, `brightness`,
        `color_temp_kelvin`/`color_temp`, `color`) for an Amazon "Works with Alexa Only"
        light across all active control paths:
          1. Update internal + Emulated Hue V1 state and fire `on_state_change`
          2. Build GraphQL `setEndpointFeatures`, Behaviors `Alexa.SmartHome.Batch`,
             Phoenix `/api/phoenix/state`, and Home Assistant `alexa_media` voice payloads
          3. If `alexa_cookie` and `endpoint_id` are configured, dispatch live HTTP
             GraphQL / Behaviors requests to Amazon Alexa.
        """
        norm_mac = dsn_or_endpoint_to_mac(mac)
        bulb = self.bulbs.get(norm_mac) or self.register_bulb(norm_mac)
        bulb.apply_ha_command(cmd_dict)

        target_id = bulb.endpoint_id or bulb.dsn or bulb.mac
        graphql_requests = build_graphql_feature_control_requests(target_id, cmd_dict)
        behaviors_batch = build_behaviors_smarthome_batch_payload(target_id, cmd_dict)
        phoenix_payload = build_phoenix_state_put_payload(target_id, cmd_dict)
        voice_relay = build_alexa_voice_command_and_ha_service_payload(
            bulb.name, cmd_dict, echo_entity_id=self.echo_entity_id
        )

        cloud_dispatched = False
        cloud_responses: List[Any] = []
        cloud_error: Optional[str] = None

        if self.alexa_cookie and bulb.endpoint_id:
            try:
                has_rgb = "color" in cmd_dict and isinstance(cmd_dict["color"], dict)
                if graphql_requests:
                    gql_url = f"https://{self.alexa_domain}/nexus/v1/graphql"
                    gql_body = json.dumps(
                        {
                            "operationName": "updatePowerFeatureForEndpoints",
                            "query": GRAPHQL_SET_ENDPOINT_FEATURES_MUTATION,
                            "variables": {"featureControlRequests": graphql_requests},
                        }
                    ).encode("utf-8")
                    gql_resp = self._http_transport("POST", gql_url, self._build_headers(), gql_body)
                    cloud_responses.append({"endpoint": "/nexus/v1/graphql", "response": gql_resp})
                    cloud_dispatched = True

                if has_rgb:
                    beh_url = f"https://{self.alexa_domain}/api/behaviors/preview"
                    beh_body = json.dumps(behaviors_batch).encode("utf-8")
                    beh_resp = self._http_transport("POST", beh_url, self._build_headers(), beh_body)
                    cloud_responses.append({"endpoint": "/api/behaviors/preview", "response": beh_resp})
                    cloud_dispatched = True
            except Exception as exc:
                cloud_error = str(exc)
                logger.warning("Direct Alexa API dispatch for %s failed: %s", bulb.name, exc)

        if self.on_state_change:
            self.on_state_change(bulb)

        return {
            "transport": "amazon_alexa_ack",
            "mac": bulb.mac,
            "endpoint_id": target_id,
            "name": bulb.name,
            "model": bulb.model,
            "hue_light_id": bulb.hue_light_id,
            "alexa_color_name": bulb.last_alexa_color_name,
            "cloud_dispatched": cloud_dispatched,
            "cloud_responses": cloud_responses,
            "cloud_error": cloud_error,
            "graphql_requests": graphql_requests,
            "behaviors_batch_payload": behaviors_batch,
            "phoenix_state_payload": phoenix_payload,
            "voice_command_relay": voice_relay,
        }

    def handle_local_hue_state_put(self, hue_id: int, hue_put: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """
        Process an incoming local LAN `PUT /api/<user>/lights/<id>/state` from an
        Amazon Echo device and sync the updated state to Home Assistant MQTT.
        """
        bulb = self.get_bulb_by_hue_id(hue_id)
        if not bulb:
            return None
        ack = apply_hue_v1_state_put(bulb, hue_put)
        if self.on_state_change:
            self.on_state_change(bulb)
        return ack

    def start_ssdp_responder(self, advertise_ip: str, http_port: int = 8080) -> bool:
        """
        Start a background UDP multicast listener on `239.255.255.250:1900` that responds
        to `M-SEARCH` queries from local Amazon Echo devices for Philips Hue bridge discovery.
        """
        if self._ssdp_thread and self._ssdp_thread.is_alive():
            return True
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", 1900))
            mreq = socket.inet_aton("239.255.255.250") + socket.inet_aton("0.0.0.0")
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            sock.settimeout(1.0)
        except OSError as exc:
            logger.debug("SSDP port 1900 not available (%s); HTTP /description.xml remains active.", exc)
            return False

        self._ssdp_sock = sock
        self._ssdp_stop = False
        resp_bytes = build_ssdp_search_response(advertise_ip, http_port).encode("utf-8")

        def _loop() -> None:
            while not self._ssdp_stop and self._ssdp_sock:
                try:
                    data, addr = self._ssdp_sock.recvfrom(2048)
                    text = data.decode("utf-8", errors="ignore")
                    if "M-SEARCH" in text and ("ssdp:all" in text or "device:basic:1" in text or "upnp:rootdevice" in text):
                        self._ssdp_sock.sendto(resp_bytes, addr)
                except socket.timeout:
                    continue
                except OSError:
                    break

        self._ssdp_thread = threading.Thread(target=_loop, name="sengled-hue-ssdp", daemon=True)
        self._ssdp_thread.start()
        return True

    def stop_ssdp_responder(self) -> None:
        self._ssdp_stop = True
        if self._ssdp_sock:
            try:
                self._ssdp_sock.close()
            except OSError:
                pass
            self._ssdp_sock = None
