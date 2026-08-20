"""Authenticated In-Memory Web Dashboard Server.

Architecture §8, Phase 27.
Enforces Control 5: CSRF, DNS Rebinding & Ephemeral Token Auth Gating.
Implements Brooks-Sweep Rec 2: Atomic In-Memory Asset Compilation.
"""

from __future__ import annotations

import json
import secrets
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, ClassVar

from rush.logging import get_logger, log_subsystem
from rush.tools.base import ToolResult

logger = get_logger("dashboard")

DASHBOARD_HTML_BUFFER: str = ""


def init_in_memory_assets() -> None:
    """Pre-compile all web dashboard assets into immutable in-memory buffers."""
    global DASHBOARD_HTML_BUFFER
    template_path = Path(__file__).parent / "templates" / "dashboard.html"
    if template_path.is_file():
        DASHBOARD_HTML_BUFFER = template_path.read_text(encoding="utf-8")
    else:
        DASHBOARD_HTML_BUFFER = (
            "<!DOCTYPE html><html><body><h1>Rush Quality Dashboard</h1></body></html>"
        )
    log_subsystem("dashboard", "INFO", "In-memory web assets compiled successfully")


class AuthenticatedDashboardHandler(BaseHTTPRequestHandler):
    """Zero-dependency HTTP handler enforcing host header whitelist, origin checks, and token auth."""

    auth_token: str = ""
    cached_results: ClassVar[list[ToolResult]] = []

    def _validate_host_and_origin(self) -> bool:
        """Protect against DNS Rebinding and CSRF attacks."""
        host_header = self.headers.get("Host", "").split(":")[0].strip()
        if host_header not in {"127.0.0.1", "localhost"}:
            log_subsystem(
                "dashboard",
                "SECURITY_ALERT",
                f"Rejected request with untrusted Host header: {host_header}",
            )
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"Forbidden: Invalid Host header")
            return False

        origin_header = self.headers.get("Origin")
        if origin_header:
            parsed = urllib.parse.urlparse(origin_header)
            if parsed.hostname not in {"127.0.0.1", "localhost"}:
                log_subsystem(
                    "dashboard",
                    "SECURITY_ALERT",
                    f"Rejected cross-origin request from: {origin_header}",
                )
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b"Forbidden: Invalid Origin")
                return False

        return True

    def _validate_auth_token(self) -> bool:
        """Validate ephemeral token from X-Rush-Auth header or query parameter."""
        token_header = self.headers.get("X-Rush-Auth")
        if token_header and secrets.compare_digest(token_header, self.auth_token):
            return True

        # Query param check
        parsed_url = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed_url.query)
        token_param = qs.get("token", [None])[0]
        if token_param and secrets.compare_digest(token_param, self.auth_token):
            return True

        log_subsystem(
            "dashboard",
            "SECURITY_ALERT",
            "Rejected unauthorized request missing valid auth token",
        )
        self.send_response(401)
        self.end_headers()
        self.wfile.write(b"Unauthorized: Missing or invalid authentication token")
        return False

    def do_GET(self) -> None:
        if not self._validate_host_and_origin():
            return
        if not self._validate_auth_token():
            return

        parsed_url = urllib.parse.urlparse(self.path)

        if parsed_url.path == "/api/findings":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            data = json.dumps(self.cached_results, default=str)
            self.wfile.write(data.encode("utf-8"))
            return

        # Default serve in-memory HTML
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy", "default-src 'self' 'unsafe-inline';"
        )
        self.end_headers()
        self.wfile.write(DASHBOARD_HTML_BUFFER.encode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:
        # Route server diagnostics to rush subsystem logger
        log_subsystem("dashboard", "DEBUG", format % args)


def launch_dashboard(
    results: list[ToolResult], port: int = 0, host: str = "127.0.0.1"
) -> tuple[HTTPServer, str]:
    """Initialize assets, generate ephemeral token, and start HTTP server bound to IPv4 loopback."""
    init_in_memory_assets()
    token = secrets.token_urlsafe(32)

    handler = AuthenticatedDashboardHandler
    handler.auth_token = token
    handler.cached_results = results

    server = HTTPServer((host, port), handler)
    actual_port = server.server_address[1]
    url = f"http://{host}:{actual_port}/?token={token}"

    log_subsystem("dashboard", "INFO", f"Dashboard live at {url}")
    return server, url
