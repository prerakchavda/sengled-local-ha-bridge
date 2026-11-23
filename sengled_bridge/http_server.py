"""
Local HTTP Config & Discovery Server + Lightweight Web Provisioning UI.

Serves the cloud discovery endpoints required by Sengled Wi-Fi bulbs on boot:
  - `GET/POST/PUT /life2/device/accessCloud.json` (and `/accessCloud.json`)
  - `GET/POST/PUT /jbalancer/new/bimqtt` (and `/bimqtt`)
as well as `/health`, `/status`, `/api/models`, `/api/provision`, and the Web UI (`/`).
"""

from __future__ import annotations

import json
import socketserver
import threading
import time
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from sengled_bridge.models import (
    MODEL_CATALOG,
    RADIO_MODULES,
    evaluate_esphome_tasmota_vs_stock,
    identify_device_by_model_or_fcc,
)
from sengled_bridge.provisioning import discover_lan_bulbs_udp, provision_wifi_bulb


def build_access_cloud_response() -> Dict[str, Any]:
    """Standard Sengled `/life2/device/accessCloud.json` response."""
    return {
        "messageCode": "200",
        "info": "OK",
        "description": "正常",
        "success": True,
    }


def build_bimqtt_response(mqtt_host: str, mqtt_tls_port: int = 8883) -> Dict[str, Any]:
    """
    Standard Sengled `/jbalancer/new/bimqtt` response.
    NOTE: `"protocal"` is an intentional spelling required by Sengled bulb firmware.
    """
    return {
        "protocal": "mqtt",
        "host": mqtt_host,
        "port": int(mqtt_tls_port),
    }


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Sengled Local Home Assistant Bridge</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    :root {
      --bg: #0f172a;
      --card: #1e293b;
      --border: #334155;
      --text: #f8fafc;
      --muted: #94a3b8;
      --accent: #38bdf8;
      --ok: #22c55e;
    }
    body {
      font-family: system-ui, -apple-system, sans-serif;
      background: var(--bg);
      color: var(--text);
      margin: 0;
      padding: 24px;
      line-height: 1.5;
    }
    .container { max-width: 960px; margin: 0 auto; }
    h1 { margin-top: 0; font-size: 1.6rem; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; margin-bottom: 20px; }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 18px;
    }
    .card h2 { margin-top: 0; font-size: 1.15rem; color: var(--accent); }
    label { display: block; font-size: 0.85rem; color: var(--muted); margin-top: 10px; }
    input {
      width: 100%;
      box-sizing: border-box;
      padding: 8px 10px;
      margin-top: 4px;
      border-radius: 6px;
      border: 1px solid var(--border);
      background: #0b1120;
      color: var(--text);
    }
    button {
      margin-top: 14px;
      padding: 9px 16px;
      border: none;
      border-radius: 6px;
      background: var(--accent);
      color: #0f172a;
      font-weight: 600;
      cursor: pointer;
    }
    pre {
      background: #0b1120;
      padding: 12px;
      border-radius: 6px;
      overflow-x: auto;
      font-size: 0.82rem;
      border: 1px solid var(--border);
    }
    .badge {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 0.78rem;
      background: rgba(34, 197, 94, 0.15);
      color: var(--ok);
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>Sengled Local Home Assistant Bridge <span class="badge">100% Local / Cloud-Free</span></h1>
    <div class="grid">
      <div class="card">
        <h2>1. Fingerprint Model # / FCC ID</h2>
        <label>Model or FCC ID (e.g. W31-N11, 2AGN8-WF863, W21-N13, B11-N1E, 2AGN8-BT002)</label>
        <input id="modelQuery" placeholder="W31-N11 or 2AGN8-WF863" />
        <button onclick="lookupModel()">Lookup Model / FCC ID</button>
        <pre id="modelOut">Enter a model or FCC ID above to inspect chipset & protocol.</pre>
      </div>
      <div class="card">
        <h2>2. Wi-Fi Bulb AP Provisioning (192.168.8.1:9080)</h2>
        <label>2.4 GHz Wi-Fi SSID</label>
        <input id="ssid" placeholder="MyHome24GHz" />
        <label>Wi-Fi Password</label>
        <input id="password" type="password" placeholder="Wi-Fi Password" />
        <label>Local Bridge IP</label>
        <input id="serverIp" placeholder="192.168.1.100" />
        <button onclick="provisionBulb()">Provision Connected AP Bulb</button>
        <pre id="provOut">Connect to Sengled_Wi-Fi Bulb_XXXX AP first, then click Provision.</pre>
      </div>
    </div>
    <div class="card">
      <h2>3. Bridge & Discovery Endpoint Status</h2>
      <button onclick="refreshStatus()">Refresh Status</button>
      <button onclick="scanLanUdp()">Scan LAN via UDP (Port 9080)</button>
      <pre id="statusOut">Loading status...</pre>
    </div>
  </div>
  <script>
    async function lookupModel() {
      const q = document.getElementById('modelQuery').value.trim();
      const res = await fetch('/api/models?q=' + encodeURIComponent(q));
      const data = await res.json();
      document.getElementById('modelOut').textContent = JSON.stringify(data, null, 2);
    }
    async function provisionBulb() {
      const payload = {
        ssid: document.getElementById('ssid').value,
        password: document.getElementById('password').value,
        server_ip: document.getElementById('serverIp').value
      };
      const res = await fetch('/api/provision', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      document.getElementById('provOut').textContent = JSON.stringify(data, null, 2);
    }
    async function refreshStatus() {
      const res = await fetch('/status');
      const data = await res.json();
      document.getElementById('statusOut').textContent = JSON.stringify(data, null, 2);
      if (data.mqtt_host && !document.getElementById('serverIp').value) {
        document.getElementById('serverIp').value = data.mqtt_host;
      }
    }
    async function scanLanUdp() {
      const res = await fetch('/api/udp-discover', {method: 'POST'});
      const data = await res.json();
      document.getElementById('statusOut').textContent = JSON.stringify(data, null, 2);
    }
    refreshStatus();
  </script>
</body>
</html>
"""


class FastHTTPServer(HTTPServer):
    """HTTPServer subclass that skips blocking reverse-DNS getfqdn() calls on bind."""

    allow_reuse_address = True

    def server_bind(self) -> None:
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = str(host)
        self.server_port = int(port)


class SengledDiscoveryHTTPServer:
    """
    Embedded HTTP server handling Sengled Wi-Fi bulb cloud simulation endpoints
    and the local web dashboard.
    """

    def __init__(
        self,
        mqtt_host: str,
        mqtt_tls_port: int = 8883,
        http_port: int = 8080,
        bind_address: str = "0.0.0.0",
        status_provider: Optional[Callable[[], Dict[str, Any]]] = None,
    ):
        self.mqtt_host = mqtt_host
        self.mqtt_tls_port = int(mqtt_tls_port)
        self.http_port = int(http_port)
        self.bind_address = bind_address
        self.status_provider = status_provider

        self.access_cloud_hits: int = 0
        self.bimqtt_hits: int = 0
        self.client_ips: List[str] = []
        self.started_at: float = time.time()

        self._server: Optional[FastHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def _record_client(self, ip: str) -> None:
        if ip and ip not in self.client_ips:
            self.client_ips.append(ip)

    def get_status_dict(self) -> Dict[str, Any]:
        extra = self.status_provider() if self.status_provider else {}
        return {
            "service": "sengled-local-ha-bridge",
            "uptime_seconds": round(time.time() - self.started_at, 1),
            "http_port": self.http_port,
            "mqtt_host": self.mqtt_host,
            "mqtt_tls_port": self.mqtt_tls_port,
            "access_cloud_hits": self.access_cloud_hits,
            "bimqtt_hits": self.bimqtt_hits,
            "recent_bulb_ips": self.client_ips,
            **extra,
        }

    def _create_handler(self):
        outer = self

        class RequestHandler(BaseHTTPRequestHandler):
            def _send_json(self, data: Any, status_code: int = 200) -> None:
                body = json.dumps(data).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_html(self, html: str, status_code: int = 200) -> None:
                body = html.encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _read_body_bytes(self) -> bytes:
                length = int(self.headers.get("Content-Length", 0) or 0)
                return self.rfile.read(length) if length > 0 else b""

            def _handle_sengled_discovery(self, path: str) -> bool:
                client_ip = str(self.client_address[0])
                if path in ("/life2/device/accessCloud.json", "/accessCloud.json"):
                    outer.access_cloud_hits += 1
                    outer._record_client(client_ip)
                    self._send_json(build_access_cloud_response())
                    return True

                if path in ("/jbalancer/new/bimqtt", "/bimqtt"):
                    outer.bimqtt_hits += 1
                    outer._record_client(client_ip)
                    self._send_json(
                        build_bimqtt_response(outer.mqtt_host, outer.mqtt_tls_port)
                    )
                    return True

                return False

            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                path = parsed.path

                if self._handle_sengled_discovery(path):
                    return

                if path == "/health":
                    self._send_json({"status": "ok", "mqtt_host": outer.mqtt_host})
                    return

                if path == "/status":
                    self._send_json(outer.get_status_dict())
                    return

                if path == "/api/models":
                    qs = parse_qs(parsed.query)
                    query = (qs.get("q", [""])[0] or "").strip()
                    if query:
                        matches = [asdict(m) for m in identify_device_by_model_or_fcc(query)]
                        eval_info = evaluate_esphome_tasmota_vs_stock(query)
                        self._send_json(
                            {
                                "query": query,
                                "count": len(matches),
                                "matches": matches,
                                "flashing_evaluation": eval_info,
                            }
                        )
                    else:
                        self._send_json(
                            {
                                "modules": {k: asdict(v) for k, v in RADIO_MODULES.items()},
                                "models": [asdict(m) for m in MODEL_CATALOG],
                            }
                        )
                    return

                if path == "/":
                    self._send_html(DASHBOARD_HTML)
                    return

                self._send_json({"error": "Not Found", "path": path}, status_code=404)

            def do_POST(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                path = parsed.path
                raw_body = self._read_body_bytes()

                if self._handle_sengled_discovery(path):
                    return

                if path == "/api/provision":
                    try:
                        req = json.loads(raw_body.decode("utf-8") or "{}")
                        ssid = str(req.get("ssid", "")).strip()
                        password = str(req.get("password", "")).strip()
                        server_ip = str(req.get("server_ip", "") or outer.mqtt_host).strip()
                        bulb_ip = str(req.get("bulb_ip", "192.168.8.1")).strip()
                        if not ssid or not password:
                            self._send_json(
                                {"success": False, "error": "ssid and password are required"},
                                status_code=400,
                            )
                            return
                        res = provision_wifi_bulb(
                            ssid=ssid,
                            password=password,
                            server_ip=server_ip,
                            http_port=outer.http_port,
                            bulb_ip=bulb_ip,
                        )
                        self._send_json(asdict(res))
                    except Exception as exc:
                        self._send_json(
                            {"success": False, "error": str(exc)}, status_code=500
                        )
                    return

                if path == "/api/udp-discover":
                    bulbs = discover_lan_bulbs_udp(listen_seconds=1.5)
                    self._send_json({"discovered_count": len(bulbs), "bulbs": bulbs})
                    return

                self._send_json({"error": "Not Found", "path": path}, status_code=404)

            def do_PUT(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                _ = self._read_body_bytes()
                if self._handle_sengled_discovery(parsed.path):
                    return
                self._send_json({"error": "Not Found"}, status_code=404)

            def log_message(self, format_str: str, *args: Any) -> None:
                return

        return RequestHandler

    def start(self) -> int:
        """Start the HTTP server in a background daemon thread and return the bound port."""
        self._server = FastHTTPServer(
            (self.bind_address, self.http_port), self._create_handler()
        )
        self.http_port = int(self._server.server_port)
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="sengled-http", daemon=True
        )
        self._thread.start()
        return self.http_port

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
