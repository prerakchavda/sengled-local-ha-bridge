"""
Sengled Bluetooth (BLE) & Bluetooth SIG Mesh Controller (`B11-*`, `B12-*`, `B1F-*`, `B21-*`).

Architecture Overview:
Sengled Bluetooth bulbs (`2AGN8-BT001`..`BT006`, Telink TLSR825x / Phyplus PHY6222QC,
Manufacturer ID `0x08B4`) are Bluetooth SIG Mesh nodes:
  - Unprovisioned state advertises Service `0x1827` (Mesh Provisioning: Data In `0x2ADB`,
    Data Out `0x2ADC`) using PB-GATT No-OOB ECDH provisioning.
  - Provisioned state advertises Service `0x1828` (Mesh Proxy: Data In `0x2ADD`,
    Data Out `0x2ADE`).
  - CRITICAL PROXY FILTER RULE: Upon connecting to `0x1828` and enabling notifications on
    `0x2ADE`, the controller MUST send `ProxyConfigSetFilterType(EXCLUSION_LIST_FILTER = 0x01)`
    to destination `0x0000` so the proxy forwards status responses back to the controller.
  - CRITICAL REPLAY PROTECTION RULE: Mesh nodes reject packets with `seq <= last_seq`.
    `MeshSequenceTracker` persists `mesh_seq_floor` to disk and increments safely across restarts.

Also supports legacy Telink proprietary GATT (`00010203-0405-0607-0809-0a0b0c0d1912`)
for older speaker/BLE bulbs (`S21-N11`, `P22-*`).
"""

from __future__ import annotations

import colorsys
import json
import struct
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from sengled_bridge.models import (
    BLE_MESH_PROVISIONING_SERVICE_UUID,
    BLE_MESH_PROXY_DATA_IN_UUID,
    BLE_MESH_PROXY_DATA_OUT_UUID,
    BLE_MESH_PROXY_SERVICE_UUID,
    TELINK_PROPRIETARY_COMMAND_UUID,
    identify_from_ble_advertisement,
)
from sengled_bridge.wifi_protocol import normalize_mac

# ---------------------------------------------------------------------------
# Bluetooth SIG Mesh Proxy PDU Types & Filter Constants
# ---------------------------------------------------------------------------
PROXY_SAR_COMPLETE = 0b00
PROXY_SAR_FIRST = 0b01
PROXY_SAR_CONTINUATION = 0b10
PROXY_SAR_LAST = 0b11

PROXY_PDU_NETWORK = 0x00
PROXY_PDU_MESH_BEACON = 0x01
PROXY_PDU_PROXY_CONFIG = 0x02
PROXY_PDU_PROVISIONING = 0x03

# Proxy Configuration Opcodes (sent with CTL=1, TTL=0, DST=0x0000)
PROXY_CONFIG_OPCODE_SET_FILTER_TYPE = 0x00
PROXY_CONFIG_OPCODE_ADD_ADDRESSES = 0x01
PROXY_CONFIG_OPCODE_REMOVE_ADDRESSES = 0x02
PROXY_CONFIG_OPCODE_FILTER_STATUS = 0x03

PROXY_FILTER_WHITELIST = 0x00  # Inclusion List (default on connect - drops everything!)
PROXY_FILTER_BLACKLIST = 0x01  # Exclusion List (opens proxy gate for all status responses)

# ---------------------------------------------------------------------------
# Bluetooth SIG Mesh Lighting Access Layer Opcodes
# ---------------------------------------------------------------------------
OPCODE_GENERIC_ONOFF_GET = 0x8201
OPCODE_GENERIC_ONOFF_SET = 0x8202
OPCODE_GENERIC_ONOFF_SET_UNACK = 0x8203
OPCODE_GENERIC_ONOFF_STATUS = 0x8204

OPCODE_LIGHT_LIGHTNESS_GET = 0x824B
OPCODE_LIGHT_LIGHTNESS_SET = 0x824C
OPCODE_LIGHT_LIGHTNESS_SET_UNACK = 0x824D
OPCODE_LIGHT_LIGHTNESS_STATUS = 0x824E

OPCODE_LIGHT_CTL_GET = 0x825D
OPCODE_LIGHT_CTL_SET = 0x825E
OPCODE_LIGHT_CTL_SET_UNACK = 0x825F
OPCODE_LIGHT_CTL_STATUS = 0x8260

OPCODE_LIGHT_HSL_GET = 0x826D
OPCODE_LIGHT_HSL_SET = 0x8276
OPCODE_LIGHT_HSL_SET_UNACK = 0x8277
OPCODE_LIGHT_HSL_STATUS = 0x8278


# ---------------------------------------------------------------------------
# Sequence Number & Replay Counter Persistence (`SeqAuth`)
# ---------------------------------------------------------------------------
class MeshSequenceTracker:
    """
    Persists Bluetooth SIG Mesh 24-bit sequence numbers (`seq`) and 8-bit
    transaction IDs (`tid`) to disk to prevent anti-replay packet drops after
    process restarts.
    """

    def __init__(
        self,
        storage_path: Optional[Union[str, Path]] = None,
        initial_seq: int = 1,
        stride: int = 32,
    ):
        self.storage_path = Path(storage_path) if storage_path else None
        self.stride = max(1, int(stride))
        self._seq: int = max(1, int(initial_seq))
        self._tid: int = 0
        self._reserved_floor: int = self._seq
        self._load()

    def _load(self) -> None:
        if not self.storage_path or not self.storage_path.exists():
            return
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
            saved_floor = int(data.get("mesh_seq_floor", 1))
            saved_tid = int(data.get("last_tid", 0))
            # Advance past the previously persisted floor so restarts never reuse seq
            self._seq = saved_floor + self.stride
            self._reserved_floor = self._seq + self.stride
            self._tid = saved_tid % 256
            self._save()
        except (OSError, ValueError, json.JSONDecodeError):
            pass

    def _save(self) -> None:
        if not self.storage_path:
            return
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            self.storage_path.write_text(
                json.dumps(
                    {
                        "mesh_seq_floor": self._reserved_floor,
                        "current_seq": self._seq,
                        "last_tid": self._tid,
                        "updated_at": int(time.time()),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass

    def next_seq_and_tid(self) -> Tuple[int, int]:
        """Allocate the next 24-bit sequence number and 8-bit transaction ID."""
        seq = self._seq
        tid = self._tid
        self._seq = (self._seq + 1) & 0xFFFFFF
        self._tid = (self._tid + 1) & 0xFF
        if self._seq >= self._reserved_floor:
            self._reserved_floor = self._seq + self.stride
            self._save()
        return seq, tid

    @property
    def current_seq(self) -> int:
        return self._seq


# ---------------------------------------------------------------------------
# Color & Scale Conversions for Bluetooth SIG Mesh Models
# ---------------------------------------------------------------------------
def ha_brightness_to_mesh_lightness(ha_brightness: int) -> int:
    """Convert Home Assistant brightness (0..255) to 16-bit Mesh Lightness (0..65535)."""
    clamped = max(0, min(255, int(ha_brightness)))
    if clamped == 0:
        return 0
    return max(1, round((clamped / 255.0) * 65535))


def mesh_lightness_to_ha_brightness(lightness_u16: int) -> int:
    """Convert 16-bit Mesh Lightness (0..65535) to Home Assistant brightness (0..255)."""
    clamped = max(0, min(65535, int(lightness_u16)))
    return round((clamped / 65535.0) * 255)


def rgb_to_mesh_hsl(r: int, g: int, b: int) -> Tuple[int, int, int]:
    """
    Convert RGB (0..255 each) to 16-bit Bluetooth SIG Mesh `(lightness, hue, saturation)`
    where each component is in `0..65535`.
    """
    rf = max(0.0, min(1.0, r / 255.0))
    gf = max(0.0, min(1.0, g / 255.0))
    bf = max(0.0, min(1.0, b / 255.0))
    h, l, s = colorsys.rgb_to_hls(rf, gf, bf)
    lightness_u16 = round(l * 65535)
    hue_u16 = round(h * 65535) % 65536
    sat_u16 = round(s * 65535)
    return (lightness_u16, hue_u16, sat_u16)


def mesh_hsl_to_rgb(lightness_u16: int, hue_u16: int, sat_u16: int) -> Tuple[int, int, int]:
    """
    Convert 16-bit Bluetooth SIG Mesh `(lightness, hue, saturation)` back to
    8-bit RGB `(r, g, b)` (0..255).
    """
    l = max(0.0, min(1.0, lightness_u16 / 65535.0))
    h = max(0.0, min(1.0, hue_u16 / 65535.0))
    s = max(0.0, min(1.0, sat_u16 / 65535.0))
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return (round(r * 255), round(g * 255), round(b * 255))


# ---------------------------------------------------------------------------
# Bluetooth SIG Mesh Access Layer & Proxy PDU Builders / Parsers
# ---------------------------------------------------------------------------
def encode_proxy_pdu(pdu_type: int, payload: bytes, sar: int = PROXY_SAR_COMPLETE) -> bytes:
    """
    Encapsulate a payload into a Bluetooth SIG Mesh Proxy PDU for GATT `0x2ADD` / `0x2ADB`.
    Header byte: `(SAR << 6) | (PDU_Type & 0x3F)`.
    """
    header = ((sar & 0x03) << 6) | (pdu_type & 0x3F)
    return bytes([header]) + payload


def decode_proxy_pdu(pdu: bytes) -> Tuple[int, int, bytes]:
    """
    Decode a Bluetooth SIG Mesh Proxy PDU from GATT `0x2ADE` / `0x2ADC` into
    `(sar, pdu_type, payload)`.
    """
    if not pdu:
        raise ValueError("Empty Mesh Proxy PDU")
    header = pdu[0]
    sar = (header >> 6) & 0x03
    pdu_type = header & 0x3F
    return (sar, pdu_type, pdu[1:])


def build_proxy_filter_exclusion_list_message() -> bytes:
    """
    Build the Proxy Config `SetFilterType(EXCLUSION_LIST_FILTER = 0x01)` Access/Config
    payload `[0x00, 0x01]` that opens the Mesh Proxy to forward bulb responses.
    """
    return bytes([PROXY_CONFIG_OPCODE_SET_FILTER_TYPE, PROXY_FILTER_BLACKLIST])


def encode_access_opcode(opcode: int) -> bytes:
    """Encode a 1-byte, 2-byte (`0x80xx`..`0xBFxx`), or 3-byte Mesh Access opcode."""
    if opcode <= 0x7F:
        return bytes([opcode])
    if opcode <= 0xFFFF:
        return struct.pack(">H", opcode)
    return struct.pack(">I", opcode)[1:]


def build_generic_onoff_get() -> bytes:
    """Build `GenericOnOffGet` (`0x8201`) Access Layer payload."""
    return encode_access_opcode(OPCODE_GENERIC_ONOFF_GET)


def build_generic_onoff_set(
    on: bool,
    tid: int = 0,
    transition_steps: Optional[int] = None,
    delay_5ms: int = 0,
    acknowledged: bool = True,
) -> bytes:
    """
    Build `GenericOnOffSet` (`0x8202`) or `GenericOnOffSetUnacknowledged` (`0x8203`)
    Access Layer payload:
        Opcode (2B) | OnOff (1B: 0x00 or 0x01) | TID (1B) | [TransitionTime (1B) | Delay (1B)]
    """
    opcode = OPCODE_GENERIC_ONOFF_SET if acknowledged else OPCODE_GENERIC_ONOFF_SET_UNACK
    body = bytearray(encode_access_opcode(opcode))
    body.append(0x01 if on else 0x00)
    body.append(tid & 0xFF)
    if transition_steps is not None:
        body.append(transition_steps & 0xFF)
        body.append(delay_5ms & 0xFF)
    return bytes(body)


def build_light_lightness_set(
    lightness_u16: int,
    tid: int = 0,
    transition_steps: Optional[int] = None,
    delay_5ms: int = 0,
    acknowledged: bool = True,
) -> bytes:
    """
    Build `LightLightnessSet` (`0x824C`) or Unacknowledged (`0x824D`) Access payload:
        Opcode (2B) | Lightness (2B little-endian) | TID (1B) | [TransitionTime (1B) | Delay (1B)]
    """
    opcode = OPCODE_LIGHT_LIGHTNESS_SET if acknowledged else OPCODE_LIGHT_LIGHTNESS_SET_UNACK
    clamped = max(0, min(65535, int(lightness_u16)))
    body = bytearray(encode_access_opcode(opcode))
    body.extend(struct.pack("<H", clamped))
    body.append(tid & 0xFF)
    if transition_steps is not None:
        body.append(transition_steps & 0xFF)
        body.append(delay_5ms & 0xFF)
    return bytes(body)


def build_light_ctl_set(
    lightness_u16: int,
    temperature_kelvin: int,
    delta_uv: int = 0,
    tid: int = 0,
    transition_steps: Optional[int] = None,
    delay_5ms: int = 0,
    acknowledged: bool = True,
) -> bytes:
    """
    Build `LightCTLSet` (`0x825E`) or Unacknowledged (`0x825F`) Access payload:
        Opcode (2B) | Lightness (2B LE) | Temperature (2B LE, 800..20000K) |
        Delta UV (2B signed LE) | TID (1B) | [TransitionTime (1B) | Delay (1B)]
    """
    opcode = OPCODE_LIGHT_CTL_SET if acknowledged else OPCODE_LIGHT_CTL_SET_UNACK
    l_clamped = max(0, min(65535, int(lightness_u16)))
    t_clamped = max(800, min(20000, int(temperature_kelvin)))
    duv_clamped = max(-32768, min(32767, int(delta_uv)))
    body = bytearray(encode_access_opcode(opcode))
    body.extend(struct.pack("<HHh", l_clamped, t_clamped, duv_clamped))
    body.append(tid & 0xFF)
    if transition_steps is not None:
        body.append(transition_steps & 0xFF)
        body.append(delay_5ms & 0xFF)
    return bytes(body)


def build_light_hsl_set(
    lightness_u16: int,
    hue_u16: int,
    saturation_u16: int,
    tid: int = 0,
    transition_steps: Optional[int] = None,
    delay_5ms: int = 0,
    acknowledged: bool = True,
) -> bytes:
    """
    Build `LightHSLSet` (`0x8276`) or Unacknowledged (`0x8277`) Access payload:
        Opcode (2B) | Lightness (2B LE) | Hue (2B LE) | Saturation (2B LE) |
        TID (1B) | [TransitionTime (1B) | Delay (1B)]
    """
    opcode = OPCODE_LIGHT_HSL_SET if acknowledged else OPCODE_LIGHT_HSL_SET_UNACK
    l_clamped = max(0, min(65535, int(lightness_u16)))
    h_clamped = max(0, min(65535, int(hue_u16)))
    s_clamped = max(0, min(65535, int(saturation_u16)))
    body = bytearray(encode_access_opcode(opcode))
    body.extend(struct.pack("<HHH", l_clamped, h_clamped, s_clamped))
    body.append(tid & 0xFF)
    if transition_steps is not None:
        body.append(transition_steps & 0xFF)
        body.append(delay_5ms & 0xFF)
    return bytes(body)


def parse_mesh_access_status(access_pdu: bytes) -> Optional[Dict[str, Any]]:
    """
    Decode incoming Bluetooth SIG Mesh Access Layer status notifications
    (`GenericOnOffStatus`, `LightLightnessStatus`, `LightCTLStatus`, `LightHSLStatus`).
    """
    if len(access_pdu) < 3:
        return None

    opcode = struct.unpack(">H", access_pdu[:2])[0]
    params = access_pdu[2:]

    if opcode == OPCODE_GENERIC_ONOFF_STATUS and len(params) >= 1:
        present_on = params[0] != 0
        target_on = (params[1] != 0) if len(params) >= 2 else present_on
        return {
            "type": "GenericOnOffStatus",
            "opcode": opcode,
            "is_on": present_on,
            "target_on": target_on,
        }

    if opcode == OPCODE_LIGHT_LIGHTNESS_STATUS and len(params) >= 2:
        present_lightness = struct.unpack("<H", params[:2])[0]
        target_lightness = (
            struct.unpack("<H", params[2:4])[0] if len(params) >= 4 else present_lightness
        )
        return {
            "type": "LightLightnessStatus",
            "opcode": opcode,
            "lightness_u16": present_lightness,
            "target_lightness_u16": target_lightness,
            "ha_brightness": mesh_lightness_to_ha_brightness(present_lightness),
            "is_on": present_lightness > 0,
        }

    if opcode == OPCODE_LIGHT_CTL_STATUS and len(params) >= 4:
        lightness, temp_k = struct.unpack("<HH", params[:4])
        return {
            "type": "LightCTLStatus",
            "opcode": opcode,
            "lightness_u16": lightness,
            "ha_brightness": mesh_lightness_to_ha_brightness(lightness),
            "color_temp_kelvin": temp_k,
            "color_mode": "color_temp",
            "is_on": lightness > 0,
        }

    if opcode == OPCODE_LIGHT_HSL_STATUS and len(params) >= 6:
        lightness, hue, sat = struct.unpack("<HHH", params[:6])
        rgb = mesh_hsl_to_rgb(lightness, hue, sat)
        return {
            "type": "LightHSLStatus",
            "opcode": opcode,
            "lightness_u16": lightness,
            "hue_u16": hue,
            "saturation_u16": sat,
            "ha_brightness": mesh_lightness_to_ha_brightness(lightness),
            "rgb": rgb,
            "color_mode": "rgb",
            "is_on": lightness > 0,
        }

    return None


# ---------------------------------------------------------------------------
# In-Memory State & Controller for Sengled BLE Bulbs
# ---------------------------------------------------------------------------
@dataclass
class SengledBLEBulbState:
    """State tracking for a Sengled Bluetooth (BLE SIG Mesh / GATT) bulb."""

    mac: str
    unicast_addr: int = 0x0002
    model: str = "B11-N1E"
    name: str = "Sengled BLE Mesh Bulb"
    is_on: bool = False
    ha_brightness: int = 255
    color_temp_kelvin: int = 2700
    rgb: Tuple[int, int, int] = (255, 255, 255)
    color_mode: str = "color_temp"
    connected: bool = False
    last_seen_epoch: float = field(default_factory=time.time)

    def apply_mesh_status(self, status: Dict[str, Any]) -> bool:
        """Apply a decoded SIG Mesh status dictionary to this bulb state."""
        if not status:
            return False
        self.last_seen_epoch = time.time()
        if "is_on" in status:
            self.is_on = bool(status["is_on"])
        if "ha_brightness" in status and int(status["ha_brightness"]) > 0:
            self.ha_brightness = int(status["ha_brightness"])
        if "color_temp_kelvin" in status:
            self.color_temp_kelvin = int(status["color_temp_kelvin"])
            self.color_mode = "color_temp"
        if "rgb" in status:
            self.rgb = tuple(status["rgb"])  # type: ignore[assignment]
            self.color_mode = "rgb"
        return True


class SengledBLEController:
    """
    Local Bluetooth (BLE) & SIG Mesh controller for Sengled BLE bulbs.

    Supports:
    - Live BLE scanning & fingerprinting via `bleak`
    - Eager GATT Proxy connection to `0x1828` (`0x2ADD`/`0x2ADE`) with automatic
      `EXCLUSION_LIST_FILTER` configuration and `GenericOnOffGet` passive state sync
    - Persistent `MeshSequenceTracker` (`mesh_seq_floor`) so restarts never trigger
      Mesh replay-attack drops
    - Optimistic state callbacks for instant Home Assistant UI feedback
    """

    def __init__(
        self,
        seq_storage_path: Optional[Union[str, Path]] = None,
        on_state_change: Optional[Callable[[SengledBLEBulbState], None]] = None,
    ):
        self.seq_tracker = MeshSequenceTracker(storage_path=seq_storage_path)
        self.on_state_change = on_state_change
        self.bulbs: Dict[str, SengledBLEBulbState] = {}

    def register_bulb(
        self,
        mac: str,
        model: str = "B11-N1E",
        name: Optional[str] = None,
        unicast_addr: int = 0x0002,
    ) -> SengledBLEBulbState:
        norm_mac = normalize_mac(mac)
        if norm_mac not in self.bulbs:
            self.bulbs[norm_mac] = SengledBLEBulbState(
                mac=norm_mac,
                unicast_addr=unicast_addr,
                model=model,
                name=name or f"Sengled BLE ({model}) {norm_mac[-5:]}",
            )
        return self.bulbs[norm_mac]

    def build_turn_on_off_pdu(self, mac: str, on: bool) -> bytes:
        """
        Build a Proxy PDU for turning a Sengled BLE bulb ON or OFF and update
        optimistic state.
        """
        bulb = self.register_bulb(mac)
        _, tid = self.seq_tracker.next_seq_and_tid()
        access_payload = build_generic_onoff_set(on=on, tid=tid, acknowledged=True)
        bulb.is_on = on
        bulb.last_seen_epoch = time.time()
        if self.on_state_change:
            self.on_state_change(bulb)
        return encode_proxy_pdu(PROXY_PDU_NETWORK, access_payload)

    def build_brightness_pdu(self, mac: str, ha_brightness: int) -> bytes:
        """
        Build a Proxy PDU for setting a Sengled BLE bulb's brightness (`0..255`).
        """
        bulb = self.register_bulb(mac)
        _, tid = self.seq_tracker.next_seq_and_tid()
        lightness = ha_brightness_to_mesh_lightness(ha_brightness)
        access_payload = build_light_lightness_set(lightness, tid=tid, acknowledged=True)
        bulb.ha_brightness = max(0, min(255, int(ha_brightness)))
        bulb.is_on = bulb.ha_brightness > 0
        bulb.last_seen_epoch = time.time()
        if self.on_state_change:
            self.on_state_change(bulb)
        return encode_proxy_pdu(PROXY_PDU_NETWORK, access_payload)

    def build_color_temp_pdu(self, mac: str, kelvin: int, ha_brightness: Optional[int] = None) -> bytes:
        """
        Build a Proxy PDU for setting a Sengled BLE bulb's color temperature (`2000..6500K`).
        """
        bulb = self.register_bulb(mac)
        if ha_brightness is not None:
            bulb.ha_brightness = max(1, min(255, int(ha_brightness)))
        _, tid = self.seq_tracker.next_seq_and_tid()
        lightness = ha_brightness_to_mesh_lightness(bulb.ha_brightness or 255)
        access_payload = build_light_ctl_set(
            lightness_u16=lightness,
            temperature_kelvin=kelvin,
            tid=tid,
            acknowledged=True,
        )
        bulb.color_temp_kelvin = max(2000, min(6500, int(kelvin)))
        bulb.color_mode = "color_temp"
        bulb.is_on = True
        bulb.last_seen_epoch = time.time()
        if self.on_state_change:
            self.on_state_change(bulb)
        return encode_proxy_pdu(PROXY_PDU_NETWORK, access_payload)

    def build_rgb_pdu(
        self, mac: str, r: int, g: int, b: int, ha_brightness: Optional[int] = None
    ) -> bytes:
        """
        Build a Proxy PDU for setting a Sengled BLE bulb's RGB color (`0..255`).
        """
        bulb = self.register_bulb(mac)
        if ha_brightness is not None:
            bulb.ha_brightness = max(1, min(255, int(ha_brightness)))
        _, tid = self.seq_tracker.next_seq_and_tid()
        lightness, hue, sat = rgb_to_mesh_hsl(r, g, b)
        access_payload = build_light_hsl_set(
            lightness_u16=lightness,
            hue_u16=hue,
            saturation_u16=sat,
            tid=tid,
            acknowledged=True,
        )
        bulb.rgb = (max(0, min(255, int(r))), max(0, min(255, int(g))), max(0, min(255, int(b))))
        bulb.color_mode = "rgb"
        bulb.is_on = True
        bulb.last_seen_epoch = time.time()
        if self.on_state_change:
            self.on_state_change(bulb)
        return encode_proxy_pdu(PROXY_PDU_NETWORK, access_payload)

    def handle_incoming_proxy_notification(self, mac: str, raw_pdu: bytes) -> Optional[Dict[str, Any]]:
        """
        Process an incoming GATT notification from `0x2ADE` (Mesh Proxy Data Out),
        update the bulb state, and fire `on_state_change`.
        """
        bulb = self.register_bulb(mac)
        _, pdu_type, payload = decode_proxy_pdu(raw_pdu)
        if pdu_type not in (PROXY_PDU_NETWORK, PROXY_PDU_PROXY_CONFIG):
            return None

        status = parse_mesh_access_status(payload)
        if status:
            bulb.apply_mesh_status(status)
            if self.on_state_change:
                self.on_state_change(bulb)
        return status

    async def scan_sengled_ble_devices(self, timeout_s: float = 8.0) -> List[Dict[str, Any]]:
        """
        Run a live BLE scan using `bleak` (if installed and a Bluetooth adapter
        is available) and fingerprint all discovered Sengled BLE devices.
        """
        try:
            from bleak import BleakScanner
        except ImportError as exc:
            raise RuntimeError("bleak is not installed; install with `pip install bleak`.") from exc

        discovered = await BleakScanner.discover(timeout=timeout_s, return_adv=True)
        results: List[Dict[str, Any]] = []
        for address, (device, adv) in discovered.items():
            fp = identify_from_ble_advertisement(
                local_name=adv.local_name or device.name,
                service_uuids=adv.service_uuids or [],
                manufacturer_data=adv.manufacturer_data or {},
                mac_address=address,
            )
            if fp["is_sengled_ble"]:
                results.append(
                    {
                        "mac": normalize_mac(address),
                        "rssi": adv.rssi,
                        "service_uuids": list(adv.service_uuids or []),
                        **fp,
                    }
                )
        return results
