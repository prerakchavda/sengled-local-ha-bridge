# Sengled Local Home Assistant Bridge (No Cloud / No Zigbee)

A 100% local, cloud-free software bridge and provisioning toolkit that integrates **Sengled Wi-Fi** and **Sengled Bluetooth (BLE SIG Mesh)** smart bulbs into **Home Assistant** as native `light` entities via MQTT Discovery.

---

## Highlights

- **Comprehensive Model & FCC ID Catalog (`2AGN8-*`)**: Built-in fingerprinting and capability database covering **12 FCC-certified Sengled radio modules** (`WF861`, `WF862`, `WF863` ESP8266, `WF864` MXCHIP, `WF866`, `WF867`, `SLMB01`, `BT001`–`BT006` Telink/Phyplus) and **30+ bulb/strip model families** (`W11`, `W12`, `W13`, `W17`, `W1E`, `W1G`, `W21`, `W2G`, `W31`, `W41`, `W71`, `B11`, `B12`, `B16`, `B1C`, `B1F`, `B1G`, `B1K`, `B21`, `S21`).
- **Sengled Wi-Fi Local Takeover (Stock Firmware)**:
  - **Provisioning CLI & Web UI**: Pairs reset Wi-Fi bulbs (`192.168.8.1:9080` UDP, RC4 `KEY_STR` encryption) onto your 2.4 GHz LAN and overrides `appServerDomain` (`/life2/device/accessCloud.json`) and `jbalancerDomain` (`/jbalancer/new/bimqtt`) to point to your local server.
  - **Local Control Server**: Embedded HTTP config responder (preserving Sengled's firmware typo `"protocal": "mqtt"`) + auto-generated self-signed TLS certificates for port `8883` Mosquitto + direct LAN UDP (`9080`) discovery/control.
  - **ESP8266 (`2AGN8-WF863`) Dual-Path Support**: Works out of the box with stock firmware or direct ESPHome/Tasmota flashing (template included at [`esphome/sengled-wf863-esp8266.yaml`](esphome/sengled-wf863-esp8266.yaml)).
- **Sengled Bluetooth (BLE SIG Mesh) Controller**:
  - Supports Telink (`0x08B4`) & Phyplus Bluetooth SIG Mesh bulbs (`0x1827` PB-GATT / `0x1828` Mesh Proxy `0x2ADD`/`0x2ADE`).
  - Solves the two notorious Sengled BLE Mesh pitfalls: automatic `ProxyConfigSetFilterType(EXCLUSION_LIST_FILTER)` initialization and disk-persisted `mesh_seq_floor` sequence tracking (`SeqAuth` anti-replay protection).
  - Includes an ESPHome Bluetooth Proxy template ([`esphome/sengled-ble-proxy.yaml`](esphome/sengled-ble-proxy.yaml)).
- **Amazon "Works with Alexa Only" (ACK & Echo-Paired) Multi-Path Bridge**:
  - Integrates **Amazon Basics "Works with Alexa Only"** bulbs/switches (`13aSB-A800ST-Q1T`, `13aSB-A806ST-Q1R`, `B0C332SMK8`, `B0CG5VDC8P`, `WS30-01`, `WP52-2` on `2AC7Z-ESP32PICOV30` / `ESP32-PICO-V3-ZERO`) and **Echo-paired Sengled BLE bulbs** directly into Home Assistant via 4 built-in paths:
    1. **Direct Alexa Smart Home GraphQL (`/nexus/v1/graphql`) & Behaviors (`/api/behaviors/preview`) Bridge**: Auto-discovers and controls On/Off, Brightness, Color Temperature (`2000K`–`7000K`), and RGB Color (mapped across 125+ official `Alexa.ColorController` color names).
    2. **Built-in 100% Local LAN Echo / Philips Hue V1 Emulator**: Serves UPnP `/description.xml`, SSDP (`239.255.255.250:1900`), and `/api/<user>/lights/<id>` so local Amazon Echo devices sync state over your LAN without cloud cookies.
    3. **Home Assistant `alexa_media` / `alexa_devices` Voice Command MQTT Relay**: Emits natural-language voice commands and ready-to-call `media_player.play_media` payloads on `sengled_bridge/alexa_ack/{slug}/command`.
    4. **Sengled-Protocol & Native ESPHome Firmware Templates**: Includes [`esphome/amazon-basics-sengled-compat.yaml`](esphome/amazon-basics-sengled-compat.yaml) (speaks native `wifielement/{MAC}/status` & `update`!) and [`esphome/amazon-basics-ack-esp32.yaml`](esphome/amazon-basics-ack-esp32.yaml) (`LEDC PWM`, `BP5758D`, and `SM2235EGH` LED drivers).
- **Native Home Assistant MQTT Discovery**: Automatically publishes `homeassistant/light/sengled_{mac}/config` with full On/Off, Brightness (`0`–`255`), Color Temperature (`2000K`–`6500K`), RGB color, transition (`gradientTime`), effects (`audio_sync`, `video_sync`, `game_sync`), and availability tracking.

---

## Architecture

```mermaid
flowchart LR
    subgraph Bulbs["Sengled & Amazon Smart Bulbs"]
        W["Sengled Wi-Fi Bulbs (W11/W21/W31/W71)\nWF861/WF863/WF864/WF867"]
        B["Sengled BLE Mesh Bulbs (B11/B12/B1F/B21)\nBT001-BT006 (Telink 0x08B4)"]
        A["Amazon 'Works with Alexa Only' Lights\n13aSB-A800ST-Q1T / A806ST-Q1R (ACK ESP32)"]
    end

    subgraph LocalBridge["Sengled Local Home Assistant Bridge"]
        HTTP["HTTP Discovery, Hue V1 Emulator & Web UI (:8080)\n/accessCloud.json, /bimqtt, /description.xml"]
        TLS["Mosquitto TLS Broker (:8883)\nwifielement/{MAC}/status & update"]
        UDP["Direct LAN UDP (:9080)\nsearch_devices & set_device_*"]
        BLE["BLE SIG Mesh Controller\n0x1828 Proxy PDU & SeqAuth Tracker"]
        ACK["Alexa ACK Multi-Path Controller\nGraphQL / Local Hue V1 / MQTT Voice Relay"]
        CORE["Python HA Discovery Bridge\nsengled_bridge"]
    end

    HA["Home Assistant\nMQTT Integration (Light Entities)"]

    W -->|"1. Boot HTTP Check"| HTTP
    W <-->|"2. TLSv1.2 MQTT"| TLS
    W <-->|"Optional LAN UDP"| UDP
    B <-->|"GATT 0x2ADD / 0x2ADE"| BLE
    A <-->|"GraphQL / Local Echo Hue V1 / Sengled Shim"| ACK
    TLS <--> CORE
    UDP <--> CORE
    BLE <--> CORE
    ACK <--> CORE
    CORE <-->|"homeassistant/light/...\nsengled_bridge/light/..."| HA
```

---

## Quick Start

### Option 1: Docker Compose

1. Set your host's LAN IP in `.env` or environment and launch the stack:
   ```bash
   ADVERTISE_IP=192.168.1.100 docker compose up -d --build
   ```
2. Open the Web UI at `http://192.168.1.100:8080/` to look up models/FCC IDs, monitor endpoint hits, provision reset Wi-Fi bulbs, or register Amazon "Works with Alexa Only" (ACK) lights.

### Option 2: Home Assistant Add-on

1. In Home Assistant, navigate to **Settings -> Add-ons -> Add-on Store -> Repositories (⋮)** and add:
   `https://github.com/prerakchavda/sengled-local-ha-bridge`
2. Install **Sengled Local Home Assistant Bridge**, set `advertise_ip` to your Home Assistant LAN IP, and click **Start**.

### Option 3: Python CLI

```bash
pip install -e .

# 1. Fingerprint any Sengled or Amazon Basics model or FCC ID (or list all 35+ models)
sengled-bridge models
sengled-bridge models -q 2AGN8-WF863
sengled-bridge models -q B11-N1E
sengled-bridge models -q 13aSB-A800ST-Q1T

# 2. Generate self-signed TLS certificates for port 8883 Mosquitto
sengled-bridge certs --dir ./certs --ip 192.168.1.100

# 3. Provision a factory-reset Wi-Fi bulb (connected to Sengled_Wi-Fi Bulb_XXXX AP)
sengled-bridge provision \
  --ssid "MyHome24GHz" \
  --password "MyWiFiPassword" \
  --server-ip 192.168.1.100 \
  --http-port 8080

# 4. Discover or control Wi-Fi bulbs directly over LAN UDP port 9080
sengled-bridge udp --discover
sengled-bridge udp --ip 192.168.1.145 --on
sengled-bridge udp --ip 192.168.1.145 --color 255 64 0

# 5. Scan and fingerprint nearby Sengled BLE bulbs
sengled-bridge ble-scan --timeout 8

# 6. Decode a Matter QR code (MT:...) or classify an Amazon Basics Matter vs. Alexa-Only (ACK) device
sengled-bridge matter --code "MT:Y.K9042C00KA0648G00"
sengled-bridge matter --code "13aSB-A800ST-Q1T"

# 7. Parse an Amazon "Works with Alexa Only" FFS barcode or generate/dispatch multi-path control commands
sengled-bridge alexa-ack --barcode "DSN:G09123456789ABCD;MODEL:13aSB-A800ST-Q1T"
sengled-bridge alexa-ack --id "G09123456789ABCD" --name "Living Room Lamp" --color 255 20 145 --brightness 200

# 8. Run the bridge daemon (including optional BLE and Amazon 'Works with Alexa Only' lights)
sengled-bridge serve \
  --advertise-ip 192.168.1.100 \
  --http-port 8080 \
  --mqtt-host 127.0.0.1 \
  --ack-light "G09123456789ABCD,13ASB-A800ST-Q1T,Living Room Lamp"
```

---

## Documentation

- [**Supported Models & FCC ID Catalog (`2AGN8-*` & `2AC7Z-*`)**](docs/MODELS_AND_FCC_IDS.md)
- [**Wi-Fi & BLE Protocol Reverse Engineering Reference**](docs/PROTOCOL_REVERSE_ENGINEERING.md)
- [**Bulb Reset, Onboarding & Pi-hole/AdGuard DNS Hijack Guide**](docs/ONBOARDING_AND_DNS.md)
- [**Amazon Basics & Sengled "Works with Alexa Only" (ACK / BLE) & Matter Integration Guide**](docs/AMAZON_BASICS_AND_MATTER.md)

---

## Running Tests

```bash
pytest -v
```
