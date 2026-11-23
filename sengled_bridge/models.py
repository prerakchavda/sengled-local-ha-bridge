"""
Comprehensive Sengled Device, Model & FCC ID Catalog and Fingerprinting Engine.

Covers all known Sengled Wi-Fi (ESP8266, MXCHIP, W867, SLM-B01) and Bluetooth
(Telink TLSR825x, Phyplus PHY6222QC BLE SIG Mesh & BLE Audio) bulbs, strips,
and plugs, as well as out-of-scope Zigbee / Z-Wave models for accurate warning
and identification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple


class RadioProtocol(str, Enum):
    """Underlying radio and control protocol used by a Sengled device."""

    WIFI_MQTT_UDP = "wifi_mqtt_udp"
    WIFI_MATTER = "wifi_matter"
    BLE_SIG_MESH = "ble_sig_mesh"
    BLE_GATT_AUDIO = "ble_gatt_audio"
    ZIGBEE = "zigbee_out_of_scope"
    ZWAVE = "zwave_out_of_scope"


class ColorCapability(str, Enum):
    """Lighting capability tier of a bulb or fixture."""

    ON_OFF = "onoff"
    DIMMABLE_WHITE = "brightness"
    TUNABLE_WHITE = "color_temp"
    RGBW = "rgbw"


@dataclass(frozen=True)
class SengledModuleSpec:
    """Radio module specification from FCC / IC certification filings (Grantee 2AGN8)."""

    module_id: str
    fcc_id: str
    ic_id: Optional[str]
    chipset: str
    protocol: RadioProtocol
    supports_custom_firmware: bool
    custom_firmware_notes: str
    cert_year: int


@dataclass(frozen=True)
class SengledModelSpec:
    """Product model specification mapping model codes to FCC IDs and capabilities."""

    model: str
    name: str
    fcc_ids: Tuple[str, ...]
    module_id: str
    chipset: str
    protocol: RadioProtocol
    capability: ColorCapability
    form_factor: str
    min_kelvin: int = 2700
    max_kelvin: int = 6500
    lumens: Optional[int] = 800
    supports_power_monitoring: bool = False
    supports_effects: bool = False
    supports_ota_tasmota_esphome: bool = False
    aliases: Tuple[str, ...] = field(default_factory=tuple)
    notes: str = ""


# ---------------------------------------------------------------------------
# Sengled Radio Modules (FCC Grantee Code: 2AGN8 / IC: 20888)
# ---------------------------------------------------------------------------
RADIO_MODULES: Dict[str, SengledModuleSpec] = {
    "WF861": SengledModuleSpec(
        module_id="WF861",
        fcc_id="2AGN8-WF861",
        ic_id="20888-WF861",
        chipset="MXCHIP EMW3080 / EMW3091 (Cortex-M4F)",
        protocol=RadioProtocol.WIFI_MQTT_UDP,
        supports_custom_firmware=False,
        custom_firmware_notes="MXCHIP architecture; use stock firmware local TLS MQTT (8883) & UDP (9080) bridge.",
        cert_year=2020,
    ),
    "WF862": SengledModuleSpec(
        module_id="WF862",
        fcc_id="2AGN8-WF862",
        ic_id="20888-WF862",
        chipset="MXCHIP EMW3080 / EMW3091",
        protocol=RadioProtocol.WIFI_MQTT_UDP,
        supports_custom_firmware=False,
        custom_firmware_notes="Use stock firmware local TLS MQTT (8883) & UDP (9080) bridge.",
        cert_year=2021,
    ),
    "WF863": SengledModuleSpec(
        module_id="WF863",
        fcc_id="2AGN8-WF863",
        ic_id="20888-WF863",
        chipset="Espressif ESP8266EX (2MB Flash)",
        protocol=RadioProtocol.WIFI_MQTT_UDP,
        supports_custom_firmware=True,
        custom_firmware_notes=(
            "ESP8266-based! Supports both stock-firmware local TLS MQTT/UDP bridging "
            "AND direct OTA/serial flashing to ESPHome or Tasmota via shim firmware."
        ),
        cert_year=2021,
    ),
    "WF864": SengledModuleSpec(
        module_id="WF864",
        fcc_id="2AGN8-WF864",
        ic_id="20888-WF864",
        chipset="MXCHIP EMW3091",
        protocol=RadioProtocol.WIFI_MQTT_UDP,
        supports_custom_firmware=False,
        custom_firmware_notes="MXCHIP module; use stock firmware local TLS MQTT (8883) & UDP (9080) bridge.",
        cert_year=2021,
    ),
    "WF866": SengledModuleSpec(
        module_id="WF866",
        fcc_id="2AGN8-WF866",
        ic_id="20888-WF866",
        chipset="Sengled Wi-Fi SoC (Beken / Realtek / MXCHIP)",
        protocol=RadioProtocol.WIFI_MQTT_UDP,
        supports_custom_firmware=False,
        custom_firmware_notes="Use stock firmware local TLS MQTT (8883) & UDP (9080) bridge.",
        cert_year=2022,
    ),
    "WF867": SengledModuleSpec(
        module_id="WF867",
        fcc_id="2AGN8-WF867",
        ic_id="20888-WF867",
        chipset="W867 Wi-Fi Module",
        protocol=RadioProtocol.WIFI_MQTT_UDP,
        supports_custom_firmware=False,
        custom_firmware_notes="Use stock firmware local TLS MQTT (8883) & UDP (9080) bridge.",
        cert_year=2022,
    ),
    "SLMB01": SengledModuleSpec(
        module_id="SLMB01",
        fcc_id="2AGN8-SLMB01",
        ic_id="20888-SLMB01",
        chipset="SLM-B01 Wi-Fi + BLE Combo Module",
        protocol=RadioProtocol.WIFI_MQTT_UDP,
        supports_custom_firmware=False,
        custom_firmware_notes="G2 Wi-Fi+BLE combo module; supports local TLS MQTT (8883) & UDP (9080) bridge.",
        cert_year=2024,
    ),
    "BT001": SengledModuleSpec(
        module_id="BT001",
        fcc_id="2AGN8-BT001",
        ic_id="20888-BT001",
        chipset="Telink TLSR825X (BLE 5.0 Mesh)",
        protocol=RadioProtocol.BLE_SIG_MESH,
        supports_custom_firmware=False,
        custom_firmware_notes="Standard Bluetooth SIG Mesh node (PB-GATT 0x1827 / Proxy 0x1828, Manufacturer ID 0x08B4).",
        cert_year=2020,
    ),
    "BT002": SengledModuleSpec(
        module_id="BT002",
        fcc_id="2AGN8-BT002",
        ic_id="20888-BT002",
        chipset="Telink TLSR8253F512AT32 (BLE 5.0 Mesh, 512KB Flash, 6ch PWM)",
        protocol=RadioProtocol.BLE_SIG_MESH,
        supports_custom_firmware=False,
        custom_firmware_notes="Standard Bluetooth SIG Mesh node (PB-GATT 0x1827 / Proxy 0x1828, Manufacturer ID 0x08B4).",
        cert_year=2021,
    ),
    "BT003": SengledModuleSpec(
        module_id="BT003",
        fcc_id="2AGN8-BT003",
        ic_id="20888-BT003",
        chipset="Telink TLSR825X BLE 5.0 Mesh",
        protocol=RadioProtocol.BLE_SIG_MESH,
        supports_custom_firmware=False,
        custom_firmware_notes="Standard Bluetooth SIG Mesh node (PB-GATT 0x1827 / Proxy 0x1828).",
        cert_year=2021,
    ),
    "BT004": SengledModuleSpec(
        module_id="BT004",
        fcc_id="2AGN8-BT004",
        ic_id="20888-BT004",
        chipset="Telink TLSR825X BLE 5.0 Mesh",
        protocol=RadioProtocol.BLE_SIG_MESH,
        supports_custom_firmware=False,
        custom_firmware_notes="Standard Bluetooth SIG Mesh node (PB-GATT 0x1827 / Proxy 0x1828).",
        cert_year=2022,
    ),
    "BT006": SengledModuleSpec(
        module_id="BT006",
        fcc_id="2AGN8-BT006",
        ic_id="20888-BT006",
        chipset="Phyplus PHY6222QC (BLE 5.0 Mesh, 64KB SRAM, 512KB Flash)",
        protocol=RadioProtocol.BLE_SIG_MESH,
        supports_custom_firmware=False,
        custom_firmware_notes="Bluetooth SIG Mesh / Broadcast mesh lighting module.",
        cert_year=2025,
    ),
}


# ---------------------------------------------------------------------------
# Exhaustive Sengled Bulb / Device Catalog (Wi-Fi, BLE, and Out-of-Scope Refs)
# ---------------------------------------------------------------------------
MODEL_CATALOG: Tuple[SengledModelSpec, ...] = (
    # --- Wi-Fi W31 Series (ESP8266 / 2AGN8-WF863) ---
    SengledModelSpec(
        model="W31-N11",
        name="Sengled Smart Wi-Fi LED Soft White A19 (2700K)",
        fcc_ids=("2AGN8-WF863",),
        module_id="WF863",
        chipset="ESP8266",
        protocol=RadioProtocol.WIFI_MQTT_UDP,
        capability=ColorCapability.DIMMABLE_WHITE,
        form_factor="A19",
        min_kelvin=2700,
        max_kelvin=2700,
        lumens=800,
        supports_power_monitoring=True,
        supports_ota_tasmota_esphome=True,
        aliases=("W31-N11W", "W31-N11_2P", "W31-N11_3P", "W31-N11_4P"),
        notes="Confirmed ESP8266 (WF863). Works with local TLS MQTT/UDP bridge OR OTA Tasmota/ESPHome flash.",
    ),
    SengledModelSpec(
        model="W31-N15",
        name="Sengled Smart Wi-Fi LED Daylight / Multicolor A19",
        fcc_ids=("2AGN8-WF863",),
        module_id="WF863",
        chipset="ESP8266",
        protocol=RadioProtocol.WIFI_MQTT_UDP,
        capability=ColorCapability.RGBW,
        form_factor="A19",
        min_kelvin=2000,
        max_kelvin=6500,
        lumens=800,
        supports_power_monitoring=True,
        supports_ota_tasmota_esphome=True,
        aliases=("W31-N15W", "W31-N15_2P", "W31-N15_4P"),
        notes="Confirmed ESP8266 (WF863). Works with local TLS MQTT/UDP bridge OR OTA Tasmota/ESPHome flash.",
    ),
    SengledModelSpec(
        model="W31-N13H",
        name="Sengled Smart Wi-Fi LED Extra Bright Multicolor A19 (1500lm)",
        fcc_ids=("2AGN8-WF863",),
        module_id="WF863",
        chipset="ESP8266",
        protocol=RadioProtocol.WIFI_MQTT_UDP,
        capability=ColorCapability.RGBW,
        form_factor="A19/A21",
        min_kelvin=2000,
        max_kelvin=6500,
        lumens=1500,
        supports_power_monitoring=True,
        supports_ota_tasmota_esphome=True,
        aliases=("W31-N13", "W31-N13HW"),
        notes="IC: 20888-WF863 / FCC ID: 2AGN8-WF863. Extra bright 100W-equivalent RGBW ESP8266 bulb.",
    ),
    # --- Wi-Fi W11 / W12 / W13 / W17 / W1E / W21 Series (MXCHIP WF861 / WF862 / WF864 / EMW3091) ---
    SengledModelSpec(
        model="W11-N11",
        name="Sengled Smart Wi-Fi LED Soft White A19 (2700K)",
        fcc_ids=("2AGN8-WF861", "2AGN8-W11N11"),
        module_id="WF861",
        chipset="MXCHIP EMW3080/EMW3091",
        protocol=RadioProtocol.WIFI_MQTT_UDP,
        capability=ColorCapability.DIMMABLE_WHITE,
        form_factor="A19",
        min_kelvin=2700,
        max_kelvin=2700,
        lumens=800,
        supports_power_monitoring=True,
        aliases=("W11-N11W", "W11-N11W_2P", "W11-N1150W", "W11-U21", "W11-U31"),
        notes="Stock firmware local takeover via TLS MQTT (8883) and UDP (9080).",
    ),
    SengledModelSpec(
        model="W11-N13",
        name="Sengled Smart Wi-Fi LED Multicolor A19",
        fcc_ids=("2AGN8-WF861", "2AGN8-WF864"),
        module_id="WF861",
        chipset="MXCHIP EMW3080/EMW3091",
        protocol=RadioProtocol.WIFI_MQTT_UDP,
        capability=ColorCapability.RGBW,
        form_factor="A19",
        min_kelvin=2000,
        max_kelvin=6500,
        lumens=800,
        supports_power_monitoring=True,
        aliases=("W11-N13W",),
        notes="Stock firmware local takeover via TLS MQTT (8883) and UDP (9080).",
    ),
    SengledModelSpec(
        model="W11-N15",
        name="Sengled Smart Wi-Fi LED Daylight A19 (5000K)",
        fcc_ids=("2AGN8-WF861", "2AGN8-WF864"),
        module_id="WF861",
        chipset="MXCHIP EMW3080/EMW3091",
        protocol=RadioProtocol.WIFI_MQTT_UDP,
        capability=ColorCapability.DIMMABLE_WHITE,
        form_factor="A19",
        min_kelvin=5000,
        max_kelvin=5000,
        lumens=800,
        supports_power_monitoring=True,
        aliases=("W11-N15W",),
        notes="Stock firmware local takeover via TLS MQTT (8883) and UDP (9080).",
    ),
    SengledModelSpec(
        model="W21-N11",
        name="Sengled Smart Wi-Fi LED Soft White A19",
        fcc_ids=("2AGN8-WF861", "2AGN8-WF864"),
        module_id="WF864",
        chipset="MXCHIP EMW3091",
        protocol=RadioProtocol.WIFI_MQTT_UDP,
        capability=ColorCapability.DIMMABLE_WHITE,
        form_factor="A19",
        min_kelvin=2700,
        max_kelvin=2700,
        lumens=800,
        supports_power_monitoring=True,
        aliases=("W21-N11W",),
        notes="MXCHIP-based Wi-Fi bulb; local control via TLS MQTT (8883) & UDP (9080).",
    ),
    SengledModelSpec(
        model="W21-N13",
        name="Sengled Smart Wi-Fi LED Multicolor A19 (RGBW)",
        fcc_ids=("2AGN8-WF861", "2AGN8-WF864"),
        module_id="WF864",
        chipset="MXCHIP EMW3091",
        protocol=RadioProtocol.WIFI_MQTT_UDP,
        capability=ColorCapability.RGBW,
        form_factor="A19",
        min_kelvin=2700,
        max_kelvin=6500,
        lumens=800,
        supports_power_monitoring=True,
        aliases=("W21-N13W", "W21-N13W_2P"),
        notes="Firmware RDSW2019004A0530_W21-N13_SYSTEM; local control via TLS MQTT (8883) & UDP (9080).",
    ),
    SengledModelSpec(
        model="W21-N15",
        name="Sengled Smart Wi-Fi LED Daylight A19",
        fcc_ids=("2AGN8-WF861", "2AGN8-WF864"),
        module_id="WF864",
        chipset="MXCHIP EMW3091",
        protocol=RadioProtocol.WIFI_MQTT_UDP,
        capability=ColorCapability.DIMMABLE_WHITE,
        form_factor="A19",
        min_kelvin=5000,
        max_kelvin=5000,
        lumens=800,
        supports_power_monitoring=True,
        aliases=("W21-N15W",),
        notes="MXCHIP-based Wi-Fi bulb; local control via TLS MQTT (8883) & UDP (9080).",
    ),
    SengledModelSpec(
        model="W12-N15",
        name="Sengled Smart Wi-Fi BR30 Floodlight Bulb",
        fcc_ids=("2AGN8-WF861", "2AGN8-WF864"),
        module_id="WF864",
        chipset="MXCHIP EMW3091",
        protocol=RadioProtocol.WIFI_MQTT_UDP,
        capability=ColorCapability.RGBW,
        form_factor="BR30",
        min_kelvin=2700,
        max_kelvin=6500,
        lumens=650,
        aliases=("W12-N15WFFS2P", "W12-N11"),
        notes="Wi-Fi BR30 floodlight; local control via TLS MQTT (8883) & UDP (9080).",
    ),
    SengledModelSpec(
        model="W13-NC5",
        name="Sengled Smart Wi-Fi E12 Candelabra Bulb (40W Equiv)",
        fcc_ids=("2AGN8-WF861", "2AGN8-WF864"),
        module_id="WF864",
        chipset="MXCHIP EMW3091",
        protocol=RadioProtocol.WIFI_MQTT_UDP,
        capability=ColorCapability.RGBW,
        form_factor="B11/E12",
        min_kelvin=2700,
        max_kelvin=6500,
        lumens=450,
        aliases=("W13-NC5WFFS2P",),
        notes="Wi-Fi E12 candle bulb; local control via TLS MQTT (8883) & UDP (9080).",
    ),
    SengledModelSpec(
        model="W17-N11",
        name="Sengled Smart Wi-Fi Edison Filament ST19 Bulb (2100K)",
        fcc_ids=("2AGN8-W17N11", "2AGN8-WF864"),
        module_id="WF864",
        chipset="MXCHIP EMW3091",
        protocol=RadioProtocol.WIFI_MQTT_UDP,
        capability=ColorCapability.DIMMABLE_WHITE,
        form_factor="ST19",
        min_kelvin=2100,
        max_kelvin=2100,
        lumens=600,
        aliases=("W17-N11W2P", "W17N11"),
        notes="FCC ID: 2AGN8-W17N11. Vintage Edison filament Wi-Fi bulb.",
    ),
    SengledModelSpec(
        model="W1E-NC1",
        name="Sengled Smart Wi-Fi Vintage Candle Filament Bulb (40W Equiv)",
        fcc_ids=("2AGN8-W1ENC1", "2AGN8-WF864"),
        module_id="WF864",
        chipset="MXCHIP EMW3091",
        protocol=RadioProtocol.WIFI_MQTT_UDP,
        capability=ColorCapability.DIMMABLE_WHITE,
        form_factor="B11/E12",
        min_kelvin=2100,
        max_kelvin=2100,
        lumens=400,
        aliases=("W1E-NC1W2P", "W1E-N1F", "W1ENC1"),
        notes="FCC ID: 2AGN8-W1ENC1. Vintage candle Wi-Fi bulb.",
    ),
    SengledModelSpec(
        model="W1G-N84",
        name="Sengled Smart Wi-Fi LED TV Lightstrip / Audio Sync Bar",
        fcc_ids=("2AGN8-WF861", "2AGN8-WF864", "2AGN8-WF867"),
        module_id="WF864",
        chipset="MXCHIP / W867",
        protocol=RadioProtocol.WIFI_MQTT_UDP,
        capability=ColorCapability.RGBW,
        form_factor="Lightstrip/Bar",
        min_kelvin=2700,
        max_kelvin=6500,
        supports_effects=True,
        aliases=("W1G-N84DB", "W1H-N84FB"),
        notes="Supports effectStatus (0=off, 7=audioSync) over wifielement/{MAC}/update.",
    ),
    SengledModelSpec(
        model="W2G-N84",
        name="Sengled Smart Wi-Fi TV Light Strip with Video Sync",
        fcc_ids=("2AGN8-W2GN84", "2AGN8-WF867"),
        module_id="WF867",
        chipset="W867",
        protocol=RadioProtocol.WIFI_MQTT_UDP,
        capability=ColorCapability.RGBW,
        form_factor="TV Lightstrip",
        min_kelvin=2700,
        max_kelvin=6500,
        supports_effects=True,
        aliases=("W2GN84",),
        notes="FCC ID: 2AGN8-W2GN84. Supports effectStatus 0/7/100/101 (audio/video/game sync).",
    ),
    SengledModelSpec(
        model="W71-N15",
        name="Sengled G2 Smart Wi-Fi + BLE Multicolor A19 Bulb",
        fcc_ids=("2AGN8-W71N15", "2AGN8-SLMB01", "2AGN8-WF866"),
        module_id="SLMB01",
        chipset="SLM-B01",
        protocol=RadioProtocol.WIFI_MQTT_UDP,
        capability=ColorCapability.RGBW,
        form_factor="A19",
        min_kelvin=2000,
        max_kelvin=6500,
        lumens=800,
        aliases=("W71N15", "W71-N11", "W71-N11DL"),
        notes="FCC ID: 2AGN8-W71N15 (2024 G2 Wi-Fi + Bluetooth onboarding bulb).",
    ),
    SengledModelSpec(
        model="W41-N15AW",
        name="Sengled Smart Wi-Fi Matter Multicolor A19 Bulb",
        fcc_ids=("2AGN8-WF866", "2AGN8-WF867"),
        module_id="WF866",
        chipset="Matter Wi-Fi SoC",
        protocol=RadioProtocol.WIFI_MATTER,
        capability=ColorCapability.RGBW,
        form_factor="A19",
        min_kelvin=2000,
        max_kelvin=6500,
        lumens=800,
        aliases=("W41-U13A", "W41-U33A"),
        notes="Supports native local Matter commissioning in Home Assistant.",
    ),
    # --- Bluetooth (BLE SIG Mesh) B11 / B12 / B16 / B1F / B1G / B1K / B21 Series ---
    SengledModelSpec(
        model="B11-N11",
        name="Sengled Smart Bluetooth Mesh LED Soft White A19 (2700K)",
        fcc_ids=("2AGN8-BT001", "2AGN8-BT002"),
        module_id="BT001",
        chipset="Telink TLSR825X",
        protocol=RadioProtocol.BLE_SIG_MESH,
        capability=ColorCapability.DIMMABLE_WHITE,
        form_factor="A19",
        min_kelvin=2700,
        max_kelvin=2700,
        lumens=800,
        aliases=("B11-N11W", "B11-N11W_2P", "B11-N11W_4P", "B11-N11W_6P", "B11-U21", "B11-U21W", "B11-U31"),
        notes="Bluetooth SIG Mesh (0x1827 PB-GATT No-OOB / 0x1828 Proxy, GenericOnOff + LightLightness).",
    ),
    SengledModelSpec(
        model="B11-N12",
        name="Sengled Smart Bluetooth Mesh LED Daylight A19 (5000K)",
        fcc_ids=("2AGN8-BT001", "2AGN8-BT002"),
        module_id="BT002",
        chipset="Telink TLSR8253F512AT32",
        protocol=RadioProtocol.BLE_SIG_MESH,
        capability=ColorCapability.DIMMABLE_WHITE,
        form_factor="A19",
        min_kelvin=5000,
        max_kelvin=5000,
        lumens=800,
        aliases=("B11-N12W", "B11-N12W2P", "B11-N12W4P", "B11-N12WCA3P-US"),
        notes="Bluetooth SIG Mesh Daylight 5000K dimmable bulb.",
    ),
    SengledModelSpec(
        model="B11-N13",
        name="Sengled Smart Bluetooth Mesh LED 100W Equiv Soft White A19 (1500lm)",
        fcc_ids=("2AGN8-BT002", "2AGN8-BT003"),
        module_id="BT002",
        chipset="Telink TLSR8253F512AT32",
        protocol=RadioProtocol.BLE_SIG_MESH,
        capability=ColorCapability.DIMMABLE_WHITE,
        form_factor="A19",
        min_kelvin=2700,
        max_kelvin=2700,
        lumens=1500,
        aliases=("B11-N13W",),
        notes="Bluetooth SIG Mesh 100W-equivalent dimmable soft white bulb.",
    ),
    SengledModelSpec(
        model="B11-N14",
        name="Sengled Smart Bluetooth Mesh LED 100W Equiv Daylight A19 (1500lm)",
        fcc_ids=("2AGN8-BT002", "2AGN8-BT003"),
        module_id="BT002",
        chipset="Telink TLSR8253F512AT32",
        protocol=RadioProtocol.BLE_SIG_MESH,
        capability=ColorCapability.DIMMABLE_WHITE,
        form_factor="A19",
        min_kelvin=5000,
        max_kelvin=5000,
        lumens=1500,
        aliases=("B11-N14W", "B11-N15", "B11-N16"),
        notes="Bluetooth SIG Mesh 100W-equivalent dimmable daylight bulb.",
    ),
    SengledModelSpec(
        model="B11-N1E",
        name="Sengled Smart Bluetooth Mesh LED Multicolor A19 (RGBW)",
        fcc_ids=("2AGN8-BT002", "2AGN8-BT003"),
        module_id="BT002",
        chipset="Telink TLSR8253F512AT32",
        protocol=RadioProtocol.BLE_SIG_MESH,
        capability=ColorCapability.RGBW,
        form_factor="A19",
        min_kelvin=2000,
        max_kelvin=6500,
        lumens=800,
        aliases=("B11-N1EW", "B11-N1EW2P", "B11-N1EW4P", "B11-N1EW_6P", "B11-N1E1", "B11-U2E", "B11-U3E"),
        notes="FCC ID: 2AGN8-BT002. Telink BLE SIG Mesh (GenericOnOff, LightLightness, LightCTL, LightHSL).",
    ),
    SengledModelSpec(
        model="B12-N11",
        name="Sengled Smart Bluetooth Mesh BR30 Soft White Floodlight",
        fcc_ids=("2AGN8-BT002", "2AGN8-BT003"),
        module_id="BT002",
        chipset="Telink TLSR8253F512AT32",
        protocol=RadioProtocol.BLE_SIG_MESH,
        capability=ColorCapability.DIMMABLE_WHITE,
        form_factor="BR30",
        min_kelvin=2700,
        max_kelvin=2700,
        lumens=650,
        notes="Bluetooth SIG Mesh BR30 floodlight.",
    ),
    SengledModelSpec(
        model="B12-N1E",
        name="Sengled Smart Bluetooth Mesh BR30 Multicolor Floodlight",
        fcc_ids=("2AGN8-BT002", "2AGN8-BT003"),
        module_id="BT002",
        chipset="Telink TLSR8253F512AT32",
        protocol=RadioProtocol.BLE_SIG_MESH,
        capability=ColorCapability.RGBW,
        form_factor="BR30",
        min_kelvin=2000,
        max_kelvin=6500,
        lumens=650,
        notes="Bluetooth SIG Mesh BR30 RGBW floodlight.",
    ),
    SengledModelSpec(
        model="B16-N11",
        name="Sengled Smart Bluetooth Mesh 5/6-inch Recessed Downlight",
        fcc_ids=("2AGN8-BT002", "2AGN8-BT003"),
        module_id="BT003",
        chipset="Telink TLSR825X",
        protocol=RadioProtocol.BLE_SIG_MESH,
        capability=ColorCapability.TUNABLE_WHITE,
        form_factor="Recessed Downlight",
        min_kelvin=2700,
        max_kelvin=5000,
        lumens=750,
        notes="Bluetooth SIG Mesh recessed downlight.",
    ),
    SengledModelSpec(
        model="B1F-N5E",
        name="Sengled Smart Bluetooth Mesh Filament Candle B11 Bulb",
        fcc_ids=("2AGN8-B1FN5E", "2AGN8-B1FN5G", "2AGN8-BT002"),
        module_id="BT002",
        chipset="Telink TLSR8253F512AT32",
        protocol=RadioProtocol.BLE_SIG_MESH,
        capability=ColorCapability.DIMMABLE_WHITE,
        form_factor="B11 Candle",
        min_kelvin=2100,
        max_kelvin=2700,
        lumens=400,
        aliases=("B1FN5E", "B1F-N5G", "B1FN5G"),
        notes="FCC ID: 2AGN8-B1FN5E / 2AGN8-B1FN5G. BLE Mesh filament candle bulb.",
    ),
    SengledModelSpec(
        model="B1K-N1G",
        name="Sengled Smart Bluetooth Mesh Filament Edison ST19 Bulb",
        fcc_ids=("2AGN8-B1KN1G", "2AGN8-BT002"),
        module_id="BT002",
        chipset="Telink TLSR8253F512AT32",
        protocol=RadioProtocol.BLE_SIG_MESH,
        capability=ColorCapability.DIMMABLE_WHITE,
        form_factor="ST19 Edison",
        min_kelvin=2100,
        max_kelvin=2100,
        lumens=600,
        aliases=("B1KN1G",),
        notes="FCC ID: 2AGN8-B1KN1G. BLE Mesh vintage Edison bulb.",
    ),
    SengledModelSpec(
        model="B1G-G8EXW",
        name="Sengled Smart Bluetooth Mesh LED Lightstrip (5M)",
        fcc_ids=("2AGN8-BT002", "2AGN8-BT003"),
        module_id="BT003",
        chipset="Telink TLSR825X",
        protocol=RadioProtocol.BLE_SIG_MESH,
        capability=ColorCapability.RGBW,
        form_factor="Lightstrip",
        min_kelvin=2000,
        max_kelvin=6500,
        notes="Bluetooth SIG Mesh RGBIC/RGBW LED strip.",
    ),
    SengledModelSpec(
        model="B1C-NB7",
        name="Sengled Smart Bluetooth Mesh Plug",
        fcc_ids=("2AGN8-B1CNB7", "2AGN8-BT003"),
        module_id="BT003",
        chipset="Telink TLSR825X",
        protocol=RadioProtocol.BLE_SIG_MESH,
        capability=ColorCapability.ON_OFF,
        form_factor="Smart Plug",
        lumens=None,
        aliases=("B1CNB7",),
        notes="FCC ID: 2AGN8-B1CNB7. Bluetooth SIG Mesh GenericOnOff smart plug.",
    ),
    SengledModelSpec(
        model="B21-N1E",
        name="Sengled Simply Smart BLE Mesh Multicolor A19 Bulb",
        fcc_ids=("2AGN8-B21N1E", "2AGN8-BT006", "2AGN8-BT004"),
        module_id="BT006",
        chipset="Phyplus PHY6222QC / Telink",
        protocol=RadioProtocol.BLE_SIG_MESH,
        capability=ColorCapability.RGBW,
        form_factor="A19",
        min_kelvin=2000,
        max_kelvin=6500,
        lumens=800,
        aliases=("B21N1E", "B21-N1EW6PK", "B21-N13"),
        notes="FCC ID: 2AGN8-B21N1E / 2AGN8-BT006 (2024-2025 BLE Mesh bulb, often bundled with B2EG7F remote).",
    ),
    SengledModelSpec(
        model="S21-N11",
        name="Sengled Pulse / Solo Bluetooth Speaker LED Lamp",
        fcc_ids=("2AGN8-S21N11", "2AGN8-P22N12", "2AGN8-P22N13", "2AGN8-P22N14"),
        module_id="BT001",
        chipset="CSR / Dual-Mode Bluetooth Audio + BLE GATT",
        protocol=RadioProtocol.BLE_GATT_AUDIO,
        capability=ColorCapability.DIMMABLE_WHITE,
        form_factor="BR30 Speaker Bulb",
        min_kelvin=2700,
        max_kelvin=2700,
        lumens=650,
        aliases=("S21N11", "P22-N12", "P22-N13", "P22-N14", "C01-BR30"),
        notes="Bluetooth speaker + dimmable LED bulb controlled over BLE GATT.",
    ),
    # --- Out-of-Scope Zigbee Reference Entries (For accurate identification & user warnings) ---
    SengledModelSpec(
        model="E11-G13",
        name="Sengled Element Classic Zigbee Soft White A19",
        fcc_ids=("2AGN8-E11G13", "2AGN8-ZM001", "2AGN8-ZM002"),
        module_id="ZM001",
        chipset="Silabs EFR32 / Zigbee HA 1.2",
        protocol=RadioProtocol.ZIGBEE,
        capability=ColorCapability.DIMMABLE_WHITE,
        form_factor="A19",
        aliases=("E11-G13W", "E11-G14WA", "E11-N13W", "E11-N14W", "E21-N11"),
        notes="OUT OF SCOPE: Zigbee radio hardware required (ZHA / Zigbee2MQTT).",
    ),
    SengledModelSpec(
        model="E11-N1EA",
        name="Sengled Element Color Plus Zigbee Multicolor A19",
        fcc_ids=("2AGN8-E11N1EA", "2AGN8-E21N1EA", "2AGN8-E12N1E", "2AGN8-ZM004", "2AGN8-ZM005", "2AGN8-ZM006"),
        module_id="ZM004",
        chipset="Silabs EFR32 / Zigbee 3.0",
        protocol=RadioProtocol.ZIGBEE,
        capability=ColorCapability.RGBW,
        form_factor="A19",
        aliases=("E11-N1EAW", "E21-N1EA", "E12-N1E", "E1G-G8E", "E1F-N9G"),
        notes="OUT OF SCOPE: Zigbee radio hardware required (ZHA / Zigbee2MQTT).",
    ),
)


# Known Sengled IEEE OUI (MAC Address Prefixes)
SENGLED_MAC_OUIS: Dict[str, str] = {
    "B0:CE:18": "Sengled Co., Ltd.",
    "B0:F8:93": "Sengled / Espressif Systems",
    "40:43:18": "Sengled / Espressif Systems (WF863)",
    "E8:DB:84": "Sengled / Espressif Systems (WF863)",
    "80:A0:36": "Sengled Co., Ltd. (MXCHIP WF861/WF864)",
    "F4:CF:A2": "Sengled / Espressif Systems",
    "EC:21:E5": "Sengled / Telink BLE Mesh",
    "A4:C1:38": "Telink Semiconductor (Sengled BLE Mesh BT001/BT002)",
}

# Telink Semiconductor Bluetooth SIG Company Identifier (advertised in Manufacturer Specific Data)
TELINK_MANUFACTURER_ID = 0x08B4

# Bluetooth SIG Mesh Service & Characteristic UUIDs
BLE_MESH_PROVISIONING_SERVICE_UUID = "00001827-0000-1000-8000-00805f9b34fb"
BLE_MESH_PROVISIONING_DATA_IN_UUID = "00002adb-0000-1000-8000-00805f9b34fb"
BLE_MESH_PROVISIONING_DATA_OUT_UUID = "00002adc-0000-1000-8000-00805f9b34fb"

BLE_MESH_PROXY_SERVICE_UUID = "00001828-0000-1000-8000-00805f9b34fb"
BLE_MESH_PROXY_DATA_IN_UUID = "00002add-0000-1000-8000-00805f9b34fb"
BLE_MESH_PROXY_DATA_OUT_UUID = "00002ade-0000-1000-8000-00805f9b34fb"

# Telink Legacy Proprietary Mesh UUIDs (fallback on older B11 / S21 firmware)
TELINK_PROPRIETARY_SERVICE_UUID = "00010203-0405-0607-0809-0a0b0c0d1910"
TELINK_PROPRIETARY_NOTIFY_UUID = "00010203-0405-0607-0809-0a0b0c0d1911"
TELINK_PROPRIETARY_COMMAND_UUID = "00010203-0405-0607-0809-0a0b0c0d1912"


def _normalize_token(value: str) -> str:
    """Normalize a model number or FCC ID for case-insensitive lookup."""
    return value.strip().upper().replace("_", "-").replace(" ", "")


def identify_device_by_model_or_fcc(query: str) -> List[SengledModelSpec]:
    """
    Look up matching SengledModelSpec entries by model code, alias, module ID, or FCC ID.

    Examples:
        identify_device_by_model_or_fcc("W31-N11")
        identify_device_by_model_or_fcc("2AGN8-WF863")
        identify_device_by_model_or_fcc("B11-N1E")
        identify_device_by_model_or_fcc("2AGN8-BT002")
    """
    norm = _normalize_token(query)
    if not norm:
        return []

    norm_alnum = norm.replace("-", "")
    matches: List[SengledModelSpec] = []

    for spec in MODEL_CATALOG:
        candidates = [spec.model, spec.module_id, *spec.aliases, *spec.fcc_ids]
        for cand in candidates:
            c_norm = _normalize_token(cand)
            c_alnum = c_norm.replace("-", "")
            if norm == c_norm or norm_alnum == c_alnum or norm_alnum in c_alnum:
                matches.append(spec)
                break

    return matches


def identify_from_status_attributes(attributes: Dict[str, str]) -> Dict[str, object]:
    """
    Fingerprint a Sengled Wi-Fi bulb from its MQTT `wifielement/{MAC}/status` attributes.

    Example status attributes sent by bulb:
        {"typeCode": "W31-N11", "identifyNO": "ESP8266", "supportAttributes": "brightness", ...}
    """
    type_code = str(attributes.get("typeCode", "") or "").strip()
    identify_no = str(attributes.get("identifyNO", "") or "").strip()
    support_attrs = str(attributes.get("supportAttributes", "") or "").strip()
    version = str(attributes.get("version", "") or "").strip()

    matched_specs = identify_device_by_model_or_fcc(type_code) if type_code else []
    spec = matched_specs[0] if matched_specs else None

    is_esp8266 = (
        "ESP8266" in identify_no.upper()
        or (spec is not None and spec.supports_ota_tasmota_esphome)
    )

    # Determine color capability dynamically from supportAttributes + model spec
    supported_tokens = {tok.strip().lower() for tok in support_attrs.split(",") if tok.strip()}
    if "color" in supported_tokens or (spec and spec.capability == ColorCapability.RGBW):
        capability = ColorCapability.RGBW
    elif (
        "colortemperature" in supported_tokens
        or "white" in supported_tokens
        or (spec and spec.capability == ColorCapability.TUNABLE_WHITE)
    ):
        capability = ColorCapability.TUNABLE_WHITE
    elif "brightness" in supported_tokens or (spec and spec.capability == ColorCapability.DIMMABLE_WHITE):
        capability = ColorCapability.DIMMABLE_WHITE
    else:
        capability = spec.capability if spec else ColorCapability.DIMMABLE_WHITE

    return {
        "model": type_code or (spec.model if spec else "Unknown Wi-Fi Bulb"),
        "name": spec.name if spec else f"Sengled Wi-Fi Bulb ({type_code or 'Generic'})",
        "module_id": spec.module_id if spec else ("WF863" if is_esp8266 else "WF861/WF864"),
        "chipset": identify_no or (spec.chipset if spec else "MXCHIP/ESP8266"),
        "protocol": RadioProtocol.WIFI_MQTT_UDP,
        "capability": capability,
        "firmware_version": version,
        "is_esp8266": is_esp8266,
        "flashing_evaluation": evaluate_esphome_tasmota_vs_stock(type_code, identify_no),
    }


def identify_from_ble_advertisement(
    local_name: Optional[str],
    service_uuids: Sequence[str],
    manufacturer_data: Optional[Dict[int, bytes]] = None,
    mac_address: Optional[str] = None,
) -> Dict[str, object]:
    """
    Fingerprint a BLE peripheral from its GATT scan advertisement data.
    Distinguishes unprovisioned SIG Mesh (0x1827), provisioned SIG Mesh Proxy (0x1828),
    Telink legacy mesh (1910), and non-Sengled BLE devices.
    """
    uuids_lower = {u.lower() for u in service_uuids}
    mfr_ids = set(manufacturer_data.keys()) if manufacturer_data else set()
    name_str = (local_name or "").strip()

    has_prov_1827 = any("1827" in u for u in uuids_lower)
    has_proxy_1828 = any("1828" in u for u in uuids_lower)
    has_telink_1910 = any("00010203-0405-0607-0809-0a0b0c0d1910" in u or "1910" in u for u in uuids_lower)
    is_telink_mfr = TELINK_MANUFACTURER_ID in mfr_ids

    mac_prefix = (mac_address or "").upper()[:8]
    known_oui = SENGLED_MAC_OUIS.get(mac_prefix)

    if has_prov_1827:
        mesh_state = "unprovisioned_pb_gatt_0x1827"
        protocol = RadioProtocol.BLE_SIG_MESH
    elif has_proxy_1828:
        mesh_state = "provisioned_proxy_0x1828"
        protocol = RadioProtocol.BLE_SIG_MESH
    elif has_telink_1910:
        mesh_state = "telink_proprietary_gatt_0x1910"
        protocol = RadioProtocol.BLE_SIG_MESH
    else:
        mesh_state = "generic_gatt"
        protocol = RadioProtocol.BLE_GATT_AUDIO

    is_sengled_ble = (
        has_prov_1827
        or has_proxy_1828
        or has_telink_1910
        or is_telink_mfr
        or known_oui is not None
        or any(tok in name_str.upper() for tok in ("SENGLED", "B11", "B12", "B1F", "B21", "PULSE"))
    )

    return {
        "is_sengled_ble": is_sengled_ble,
        "local_name": name_str or "Sengled BLE Mesh Node",
        "protocol": protocol,
        "mesh_state": mesh_state,
        "is_telink_chip": is_telink_mfr or has_prov_1827 or has_proxy_1828 or has_telink_1910,
        "manufacturer_id_hex": f"0x{TELINK_MANUFACTURER_ID:04X}" if is_telink_mfr else None,
        "oui_vendor": known_oui,
        "encryption_type": (
            "Encrypted Bluetooth SIG Mesh (5-layer stack: Access/Upper/Lower/Network/Proxy PDU 0x2ADD/0x2ADE; No-OOB PB-GATT)"
            if (has_prov_1827 or has_proxy_1828)
            else "GATT Characteristic Write"
        ),
    }


def evaluate_esphome_tasmota_vs_stock(type_code: str, identify_no: str = "") -> Dict[str, object]:
    """
    Evaluate whether ESPHome/Tasmota flashing is cleaner than stock-firmware bridging
    for a given bulb model / radio module.
    """
    specs = identify_device_by_model_or_fcc(type_code) if type_code else []
    spec = specs[0] if specs else None
    is_esp8266 = (
        "ESP8266" in identify_no.upper()
        or (spec is not None and spec.supports_ota_tasmota_esphome)
        or _normalize_token(type_code) in {"W31-N11", "W31-N15", "W31-N13H", "WF863", "2AGN8-WF863"}
    )

    if is_esp8266:
        return {
            "can_flash_esphome_tasmota": True,
            "module": "2AGN8-WF863 (Espressif ESP8266)",
            "recommendation": "dual_option",
            "summary": (
                "WF863 uses an ESP8266 with PWM channels on GPIO4/GPIO12/GPIO13/GPIO14. "
                "Both paths work cleanly: (1) Stock-firmware TLS MQTT + UDP bridge requires zero "
                "flashing risk and preserves native gradient transitions, while (2) OTA flashing "
                "to ESPHome/Tasmota via the `update` MQTT command (`type: update`) removes the TLS "
                "8883 broker requirement permanently. An ESPHome configuration is provided in "
                "`esphome/sengled-wf863-esp8266.yaml`."
            ),
        }

    return {
        "can_flash_esphome_tasmota": False,
        "module": spec.module_id if spec else "MXCHIP / Non-ESP (WF861/WF864/WF866/WF867/SLMB01)",
        "recommendation": "stock_firmware_bridge",
        "summary": (
            "Non-ESP8266 module (e.g., MXCHIP EMW3080/EMW3091 or W867). Custom firmware OTA shim "
            "flashing is NOT supported; stock-firmware local takeover via our HTTP discovery + "
            "TLS 8883 MQTT & UDP 9080 bridge is the required and safest 100% local path."
        ),
    }
