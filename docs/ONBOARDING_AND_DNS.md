# Bulb Reset, Onboarding & DNS Hijack Guide

This guide walks through resetting and adopting Sengled Wi-Fi and Bluetooth (BLE) bulbs into your local Home Assistant bridge, including a zero-reset **DNS Override** option for Wi-Fi bulbs that are already connected to your Wi-Fi network.

---

## 1. Factory Resetting a Sengled Bulb

Use the physical wall switch or lamp switch:

1. Start with the bulb powered **ON**.
2. Rapidly toggle the power **OFF and ON 5 times** (about 0.5–1 second per toggle; some older BLE firmware revisions require **10 rapid toggles**).
3. End in the **ON** position.
4. **Confirmation**: The bulb will blink/flash **3 to 5 times** (and multicolor bulbs will cycle Red -> Green -> Blue -> Warm White).

---

## 2. Adopting Sengled Wi-Fi Bulbs (`W11`, `W12`, `W13`, `W17`, `W1E`, `W21`, `W31`, `W71`)

### Method A: AP Mode Provisioning (Recommended for New or Reset Bulbs)

1. Ensure the Sengled Local Bridge is running on your LAN (e.g., `192.168.1.100`, HTTP port `8080`, TLS MQTT port `8883`).
2. Reset the bulb so its open setup Wi-Fi network appears: `Sengled_Wi-Fi Bulb_XXXX`.
3. Connect your laptop or Wi-Fi interface to `Sengled_Wi-Fi Bulb_XXXX` (the bulb's gateway IP is `192.168.8.1`).
4. Run the provisioning CLI (or use the Web UI at `http://<BRIDGE_IP>:8080/`):
   ```bash
   sengled-bridge provision \
     --ssid "Your24GHzWiFi" \
     --password "YourWiFiPassword" \
     --server-ip 192.168.1.100 \
     --http-port 8080
   ```
5. The bulb will join your 2.4 GHz Wi-Fi, query `http://192.168.1.100:8080/life2/device/accessCloud.json` and `/jbalancer/new/bimqtt`, connect to your local TLS MQTT broker on port `8883`, and automatically appear in Home Assistant under **Settings -> Devices & Services -> MQTT**!

---

### Method B: Zero-Reset DNS Override (Pi-hole / AdGuard Home / Router `dnsmasq`)

If your Sengled Wi-Fi bulbs are **already connected to your 2.4 GHz Wi-Fi** from before Sengled's cloud outage, you do **not** even need to reset or re-pair them!

By default, stock bulbs resolve Sengled's cloud discovery domains on port `80`/`443` and MQTT on port `8883`. Point these domains to your local bridge IP (`192.168.1.100`) in your local DNS server and run the bridge HTTP server on port `80`:

#### Domains to Override -> `<YOUR_BRIDGE_IP>`
- `element.cloud.sengled.com`
- `life2.cloud.sengled.com`
- `jbalancer.cloud.sengled.com`
- `us-mqtt.cloud.sengled.com`
- `mqtt.cloud.sengled.com`
- `cloud.sengled.com`

#### AdGuard Home (Custom Filtering Rules)
```text
||cloud.sengled.com^$dnsrewrite=192.168.1.100
```

#### Pi-hole / `dnsmasq` (`/etc/dnsmasq.d/99-sengled-local.conf`)
```ini
address=/cloud.sengled.com/192.168.1.100
```
After adding the DNS rule, power-cycle the bulb once so it re-queries `/jbalancer/new/bimqtt` and connects to your local port `8883` TLS broker.

---

## 3. Adopting Sengled Bluetooth (BLE SIG Mesh) Bulbs (`B11`, `B12`, `B16`, `B1F`, `B1G`, `B1K`, `B21`)

1. Reset the BLE bulb (5x rapid power toggle).
2. Verify the bulb is advertising Bluetooth SIG Mesh Provisioning Service `0x1827` (and Telink Manufacturer ID `0x08B4`):
   ```bash
   sengled-bridge ble-scan --timeout 8
   ```
3. Provision the bulb into your local Bluetooth SIG Mesh network (using nRF Mesh with **No-OOB** authentication, assigning NetKey + AppKey 0 bound to GenericOnOff `0x1000`, LightLightness `0x1300`, LightCTL `0x1303`, LightHSL `0x1307`).
4. Pass `--ble-bulb <MAC>,<MODEL>` to `sengled-bridge serve` (or list it under `ble_bulbs` in the Home Assistant Add-on configuration).
5. If your Home Assistant server is far from the bulb, flash an ESP32 with [`esphome/sengled-ble-proxy.yaml`](../esphome/sengled-ble-proxy.yaml) to act as an active BLE GATT Proxy (`0x1828`).
