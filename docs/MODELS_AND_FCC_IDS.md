# Sengled Smart Bulb Models & FCC ID Reference (`2AGN8-*`)

This catalog maps every known Sengled Wi-Fi and Bluetooth (BLE) radio module (`2AGN8-*`) and retail bulb model number to its chipset, local protocol, and firmware options.

---

## 1. Certified Sengled Radio Modules (FCC Grantee: `2AGN8` / IC: `20888`)

| Module ID | FCC ID | IC ID | Chipset / SoC | Protocol | Custom Firmware (ESPHome/Tasmota)? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **WF861** | `2AGN8-WF861` | `20888-WF861` | MXCHIP EMW3080 / EMW3091 (Cortex-M4F) | Wi-Fi TLS MQTT (`8883`) + UDP (`9080`) | No — use stock-firmware local bridge |
| **WF862** | `2AGN8-WF862` | `20888-WF862` | MXCHIP EMW3080 / EMW3091 | Wi-Fi TLS MQTT (`8883`) + UDP (`9080`) | No — use stock-firmware local bridge |
| **WF863** | `2AGN8-WF863` | `20888-WF863` | **Espressif ESP8266EX (2MB Flash)** | Wi-Fi TLS MQTT (`8883`) + UDP (`9080`) | **Yes** — supports both stock bridge & OTA/serial ESPHome/Tasmota |
| **WF864** | `2AGN8-WF864` | `20888-WF864` | MXCHIP EMW3091 | Wi-Fi TLS MQTT (`8883`) + UDP (`9080`) | No — use stock-firmware local bridge |
| **WF866** | `2AGN8-WF866` | `20888-WF866` | Sengled Wi-Fi SoC | Wi-Fi TLS MQTT (`8883`) + UDP (`9080`) | No — use stock-firmware local bridge |
| **WF867** | `2AGN8-WF867` | `20888-WF867` | W867 Wi-Fi Module | Wi-Fi TLS MQTT (`8883`) + UDP (`9080`) | No — use stock-firmware local bridge |
| **SLMB01** | `2AGN8-SLMB01` | `20888-SLMB01` | SLM-B01 Wi-Fi + BLE Combo Module | Wi-Fi TLS MQTT (`8883`) + UDP (`9080`) | No — use stock-firmware local bridge |
| **BT001** | `2AGN8-BT001` | `20888-BT001` | **Telink TLSR825X** (BLE 5.0 Mesh) | Bluetooth SIG Mesh (`0x1827` / `0x1828`) | N/A — controlled via BLE SIG Mesh Proxy |
| **BT002** | `2AGN8-BT002` | `20888-BT002` | **Telink TLSR8253F512AT32** (512KB Flash, 6ch PWM) | Bluetooth SIG Mesh (`0x1827` / `0x1828`) | N/A — controlled via BLE SIG Mesh Proxy |
| **BT003** | `2AGN8-BT003` | `20888-BT003` | Telink TLSR825X BLE 5.0 Mesh | Bluetooth SIG Mesh (`0x1827` / `0x1828`) | N/A — controlled via BLE SIG Mesh Proxy |
| **BT004** | `2AGN8-BT004` | `20888-BT004` | Telink TLSR825X BLE 5.0 Mesh | Bluetooth SIG Mesh (`0x1827` / `0x1828`) | N/A — controlled via BLE SIG Mesh Proxy |
| **BT006** | `2AGN8-BT006` | `20888-BT006` | **Phyplus PHY6222QC** (64KB SRAM, 512KB Flash) | Bluetooth SIG Mesh (`0x1827` / `0x1828`) | N/A — controlled via BLE SIG Mesh Proxy |

---

## 2. Sengled Wi-Fi Bulbs, Strips & Bars (`W11` / `W12` / `W13` / `W17` / `W1E` / `W21` / `W31` / `W71`)

| Model Code | Aliases | FCC ID(s) | Module / SoC | Form Factor & Capabilities | Local Control Method |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **W31-N11** | `W31-N11W`, `W31-N11_4P` | `2AGN8-WF863` | `WF863` (ESP8266) | A19 2700K Soft White Dimmable (800lm) | Local TLS MQTT (`8883`) + UDP (`9080`) **or** ESPHome/Tasmota |
| **W31-N15** | `W31-N15W`, `W31-N15_4P` | `2AGN8-WF863` | `WF863` (ESP8266) | A19 Multicolor RGBW / Daylight (800lm) | Local TLS MQTT (`8883`) + UDP (`9080`) **or** ESPHome/Tasmota |
| **W31-N13H** | `W31-N13`, `W31-N13HW` | `2AGN8-WF863` | `WF863` (ESP8266) | A19/A21 Extra Bright 1500lm RGBW | Local TLS MQTT (`8883`) + UDP (`9080`) **or** ESPHome/Tasmota |
| **W11-N11** | `W11-N11W`, `W11-N1150W`, `W11-U21`, `W11-U31` | `2AGN8-WF861`, `2AGN8-W11N11` | `WF861` (MXCHIP) | A19 2700K Soft White Dimmable (800lm) | Stock Firmware TLS MQTT (`8883`) + UDP (`9080`) |
| **W11-N13** | `W11-N13W` | `2AGN8-WF861`, `2AGN8-WF864` | `WF861` (MXCHIP) | A19 Multicolor RGBW (800lm) | Stock Firmware TLS MQTT (`8883`) + UDP (`9080`) |
| **W11-N15** | `W11-N15W` | `2AGN8-WF861`, `2AGN8-WF864` | `WF861` (MXCHIP) | A19 5000K Daylight Dimmable (800lm) | Stock Firmware TLS MQTT (`8883`) + UDP (`9080`) |
| **W21-N11** | `W21-N11W` | `2AGN8-WF861`, `2AGN8-WF864` | `WF864` (MXCHIP EMW3091) | A19 2700K Soft White Dimmable (800lm) | Stock Firmware TLS MQTT (`8883`) + UDP (`9080`) |
| **W21-N13** | `W21-N13W`, `W21-N13W_2P` | `2AGN8-WF861`, `2AGN8-WF864` | `WF864` (MXCHIP EMW3091) | A19 Multicolor RGBW (2700K–6500K, 800lm) | Stock Firmware TLS MQTT (`8883`) + UDP (`9080`) |
| **W21-N15** | `W21-N15W` | `2AGN8-WF861`, `2AGN8-WF864` | `WF864` (MXCHIP EMW3091) | A19 5000K Daylight Dimmable (800lm) | Stock Firmware TLS MQTT (`8883`) + UDP (`9080`) |
| **W12-N15** | `W12-N15WFFS2P`, `W12-N11` | `2AGN8-WF861`, `2AGN8-WF864` | `WF864` (MXCHIP EMW3091) | BR30 Floodlight Multicolor RGBW (650lm) | Stock Firmware TLS MQTT (`8883`) + UDP (`9080`) |
| **W13-NC5** | `W13-NC5WFFS2P` | `2AGN8-WF861`, `2AGN8-WF864` | `WF864` (MXCHIP EMW3091) | B11/E12 Candelabra Multicolor RGBW (450lm) | Stock Firmware TLS MQTT (`8883`) + UDP (`9080`) |
| **W17-N11** | `W17-N11W2P`, `W17N11` | `2AGN8-W17N11`, `2AGN8-WF864` | `WF864` (MXCHIP EMW3091) | ST19 Vintage Edison Filament 2100K (600lm) | Stock Firmware TLS MQTT (`8883`) + UDP (`9080`) |
| **W1E-NC1** | `W1E-NC1W2P`, `W1E-N1F` | `2AGN8-W1ENC1`, `2AGN8-WF864` | `WF864` (MXCHIP EMW3091) | B11/E12 Vintage Candle Filament 2100K | Stock Firmware TLS MQTT (`8883`) + UDP (`9080`) |
| **W1G-N84** | `W1G-N84DB`, `W1H-N84FB` | `2AGN8-WF864`, `2AGN8-WF867` | `WF864` / `WF867` | Wi-Fi LED Lightstrip / Audio Sync Light Bar | Stock Firmware TLS MQTT (`8883`, `effectStatus`) |
| **W2G-N84** | `W2GN84` | `2AGN8-W2GN84`, `2AGN8-WF867` | `WF867` | Wi-Fi TV Light Strip with Video Sync | Stock Firmware TLS MQTT (`8883`, `effectStatus`) |
| **W71-N15** | `W71-N11`, `W71-N11DL` | `2AGN8-W71N15`, `2AGN8-SLMB01` | `SLMB01` (G2 Wi-Fi+BLE) | A19 G2 Multicolor RGBW / Soft White | Stock Firmware TLS MQTT (`8883`) + UDP (`9080`) |
| **W41-N15AW** | `W41-U13A`, `W41-U33A` | `2AGN8-WF866`, `2AGN8-WF867` | `WF866` | A19/A60 Matter Wi-Fi RGBW | Native Home Assistant Matter |

---

## 3. Sengled Bluetooth (BLE SIG Mesh & BLE GATT) Bulbs (`B11` / `B12` / `B16` / `B1F` / `B1G` / `B1K` / `B21` / `S21`)

| Model Code | Aliases | FCC ID(s) | Module / SoC | Form Factor & Capabilities | Local Control Method |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **B11-N11** | `B11-N11W`, `B11-U21`, `B11-U31` | `2AGN8-BT001`, `2AGN8-BT002` | `BT001` / `BT002` (Telink TLSR825x) | A19 2700K Soft White Dimmable (800lm) | Bluetooth SIG Mesh (`0x1827`/`0x1828`) |
| **B11-N12** | `B11-N12W`, `B11-N12W4P` | `2AGN8-BT001`, `2AGN8-BT002` | `BT002` (Telink TLSR8253) | A19 5000K Daylight Dimmable (800lm) | Bluetooth SIG Mesh (`0x1827`/`0x1828`) |
| **B11-N13** | `B11-N13W` | `2AGN8-BT002`, `2AGN8-BT003` | `BT002` (Telink TLSR8253) | A19 100W Equiv (1500lm) 2700K Dimmable | Bluetooth SIG Mesh (`0x1827`/`0x1828`) |
| **B11-N14** | `B11-N14W`, `B11-N15`, `B11-N16` | `2AGN8-BT002`, `2AGN8-BT003` | `BT002` (Telink TLSR8253) | A19 100W Equiv (1500lm) 5000K Dimmable | Bluetooth SIG Mesh (`0x1827`/`0x1828`) |
| **B11-N1E** | `B11-N1EW`, `B11-N1E1`, `B11-U2E`, `B11-U3E` | `2AGN8-BT002`, `2AGN8-BT003` | `BT002` (Telink TLSR8253) | A19 Multicolor RGBW (2000K–6500K, 800lm) | Bluetooth SIG Mesh (`GenericOnOff`, `LightCTL`, `LightHSL`) |
| **B12-N11** | `B12-N11W` | `2AGN8-BT002`, `2AGN8-BT003` | `BT002` (Telink TLSR8253) | BR30 Floodlight 2700K Soft White (650lm) | Bluetooth SIG Mesh (`0x1827`/`0x1828`) |
| **B12-N1E** | `B12-N1EW` | `2AGN8-BT002`, `2AGN8-BT003` | `BT002` (Telink TLSR8253) | BR30 Floodlight Multicolor RGBW (650lm) | Bluetooth SIG Mesh (`0x1827`/`0x1828`) |
| **B16-N11** | `B16-N11W` | `2AGN8-BT002`, `2AGN8-BT003` | `BT003` (Telink TLSR825x) | 5/6-inch Recessed Downlight CCT (750lm) | Bluetooth SIG Mesh (`0x1827`/`0x1828`) |
| **B1F-N5E** | `B1F-N5G`, `B1FN5E`, `B1FN5G` | `2AGN8-B1FN5E`, `2AGN8-B1FN5G` | `BT002` (Telink TLSR8253) | B11 Filament Candle 2100K/2700K (400lm) | Bluetooth SIG Mesh (`0x1827`/`0x1828`) |
| **B1K-N1G** | `B1KN1G` | `2AGN8-B1KN1G`, `2AGN8-BT002` | `BT002` (Telink TLSR8253) | ST19 Filament Edison 2100K (600lm) | Bluetooth SIG Mesh (`0x1827`/`0x1828`) |
| **B1G-G8EXW**| `B1G-G8E` | `2AGN8-BT002`, `2AGN8-BT003` | `BT003` (Telink TLSR825x) | 5M BLE Mesh Multicolor LED Lightstrip | Bluetooth SIG Mesh (`0x1827`/`0x1828`) |
| **B1C-NB7** | `B1CNB7` | `2AGN8-B1CNB7`, `2AGN8-BT003` | `BT003` (Telink TLSR825x) | BLE Mesh Smart Plug | Bluetooth SIG Mesh (`GenericOnOff`) |
| **B21-N1E** | `B21-N13`, `B21-N1EW6PK` | `2AGN8-B21N1E`, `2AGN8-BT006` | `BT006` (Phyplus PHY6222QC) | A19 Simply Smart BLE Mesh RGBW | Bluetooth SIG Mesh (`0x1827`/`0x1828`) |
| **S21-N11** | `P22-N12`, `P22-N13`, `P22-N14` | `2AGN8-S21N11`, `2AGN8-P22N13` | Dual-Mode BT Audio + BLE | BR30 Speaker + Dimmable LED Lamp | BLE GATT Characteristic Control |

---

## 4. ESPHome / Tasmota vs. Stock-Firmware Bridging for `2AGN8-WF863` (ESP8266)

If your bulb has FCC ID **`2AGN8-WF863`** (models `W31-N11`, `W31-N15`, `W31-N13H`), its internal radio module is an **Espressif ESP8266EX** (`identifyNO: "ESP8266"`). You can choose between two 100% local approaches:

| Criterion | Option 1: Stock-Firmware Local Bridge (Default) | Option 2: Direct ESPHome / Tasmota Flash |
| :--- | :--- | :--- |
| **Compatibility** | Works on **all** Sengled Wi-Fi bulbs (`WF861`, `WF862`, `WF863`, `WF864`, `WF866`, `WF867`, `SLMB01`) | **Only** works on `2AGN8-WF863` (ESP8266); bricks MXCHIP (`WF861`/`WF864`) |
| **Risk Level** | Zero bricking risk; reversible at any time via 5x power-cycle reset | Small OTA shim risk if power is lost mid-flash |
| **Infrastructure** | Requires local port `8883` TLS Mosquitto + bridge daemon | Connects directly to Home Assistant Native ESPHome API (no TLS broker needed) |
| **Hardware Transitions** | Uses Sengled's native `gradientTime` hardware fade engine and `consumption` telemetry | Uses ESPHome software PWM (`GPIO4`=R, `GPIO12`=G, `GPIO14`=B, `GPIO13`=WW) |

An ready-to-compile ESPHome configuration for `2AGN8-WF863` bulbs is included at [`esphome/sengled-wf863-esp8266.yaml`](../esphome/sengled-wf863-esp8266.yaml).
