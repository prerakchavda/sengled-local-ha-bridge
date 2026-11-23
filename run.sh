#!/usr/bin/env bash
set -euo pipefail

OPTIONS_JSON="/data/options.json"
CERT_DIR="${CERT_DIR:-/data/certs}"
DATA_DIR="${DATA_DIR:-/data/state}"

mkdir -p "$CERT_DIR" "$DATA_DIR"

if [ -f "$OPTIONS_JSON" ]; then
  ADVERTISE_IP="$(jq -r '.advertise_ip // "127.0.0.1"' "$OPTIONS_JSON")"
  HTTP_PORT="$(jq -r '.http_port // 8080' "$OPTIONS_JSON")"
  BULB_TLS_PORT="$(jq -r '.bulb_tls_port // 8883' "$OPTIONS_JSON")"
  MQTT_HOST="$(jq -r '.mqtt_host // "core-mosquitto"' "$OPTIONS_JSON")"
  MQTT_PORT="$(jq -r '.mqtt_port // 1883' "$OPTIONS_JSON")"
  MQTT_USERNAME="$(jq -r '.mqtt_username // ""' "$OPTIONS_JSON")"
  MQTT_PASSWORD="$(jq -r '.mqtt_password // ""' "$OPTIONS_JSON")"
  DISCOVERY_PREFIX="$(jq -r '.discovery_prefix // "homeassistant"' "$OPTIONS_JSON")"
  BRIDGE_PREFIX="$(jq -r '.bridge_prefix // "sengled_bridge"' "$OPTIONS_JSON")"
  LOG_LEVEL="$(jq -r '.log_level // "info"' "$OPTIONS_JSON")"
  ALEXA_COOKIE="$(jq -r '.alexa_cookie // ""' "$OPTIONS_JSON")"
  ALEXA_DOMAIN="$(jq -r '.alexa_domain // "amazon.com"' "$OPTIONS_JSON")"
  ECHO_ENTITY="$(jq -r '.echo_entity // "media_player.echo_dot"' "$OPTIONS_JSON")"
else
  ADVERTISE_IP="${ADVERTISE_IP:-127.0.0.1}"
  HTTP_PORT="${HTTP_PORT:-8080}"
  BULB_TLS_PORT="${BULB_TLS_PORT:-8883}"
  MQTT_HOST="${MQTT_HOST:-127.0.0.1}"
  MQTT_PORT="${MQTT_PORT:-1883}"
  MQTT_USERNAME="${MQTT_USERNAME:-}"
  MQTT_PASSWORD="${MQTT_PASSWORD:-}"
  DISCOVERY_PREFIX="${DISCOVERY_PREFIX:-homeassistant}"
  BRIDGE_PREFIX="${BRIDGE_PREFIX:-sengled_bridge}"
  LOG_LEVEL="${LOG_LEVEL:-info}"
  ALEXA_COOKIE="${ALEXA_COOKIE:-}"
  ALEXA_DOMAIN="${ALEXA_DOMAIN:-amazon.com}"
  ECHO_ENTITY="${ECHO_ENTITY:-media_player.echo_dot}"
fi

EXTRA_ARGS=()
if [ -f "$OPTIONS_JSON" ]; then
  while IFS= read -r ble; do
    [ -n "$ble" ] && EXTRA_ARGS+=(--ble-bulb "$ble")
  done < <(jq -r '.ble_bulbs[]? // empty' "$OPTIONS_JSON")
  while IFS= read -r ack; do
    [ -n "$ack" ] && EXTRA_ARGS+=(--ack-light "$ack")
  done < <(jq -r '.ack_lights[]? // empty' "$OPTIONS_JSON")
fi

echo "[sengled-bridge] Generating/verifying self-signed TLS certificates in ${CERT_DIR}..."
sengled-bridge certs --dir "$CERT_DIR" --ip "$ADVERTISE_IP"

echo "[sengled-bridge] Starting Sengled Local Home Assistant Bridge..."
exec sengled-bridge serve \
  --advertise-ip "$ADVERTISE_IP" \
  --http-port "$HTTP_PORT" \
  --bulb-tls-port "$BULB_TLS_PORT" \
  --mqtt-host "$MQTT_HOST" \
  --mqtt-port "$MQTT_PORT" \
  --mqtt-username "$MQTT_USERNAME" \
  --mqtt-password "$MQTT_PASSWORD" \
  --discovery-prefix "$DISCOVERY_PREFIX" \
  --bridge-prefix "$BRIDGE_PREFIX" \
  --cert-dir "$CERT_DIR" \
  --data-dir "$DATA_DIR" \
  --alexa-cookie "$ALEXA_COOKIE" \
  --alexa-domain "$ALEXA_DOMAIN" \
  --echo-entity "$ECHO_ENTITY" \
  --log-level "$LOG_LEVEL" \
  "${EXTRA_ARGS[@]}"

