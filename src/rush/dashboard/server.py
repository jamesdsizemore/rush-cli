"""Authenticated in-memory ephemeral dashboard HTTP server."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from typing import ClassVar
from urllib.parse import parse_qs, urlparse

from rush.dashboard.static_assets import DASHBOARD_HTML_TEMPLATE
from rush.tools.base import ToolResult

_IN_MEMORY_ASSETS: dict[str, bytes] = {}


def init_in_memory_assets() -> dict[str, bytes]:
    """Initialize in-memory cached assets."""
    _IN_MEMORY_ASSETS["index.html"] = DASHBOARD_HTML_TEMPLATE.encode("utf-8")
    return _IN_MEMORY_ASSETS


class AuthenticatedDashboardHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for ephemeral authenticated dashboard."""

    auth_token: ClassVar[str] = ""
    cached_results: ClassVar[list[ToolResult]] = []

    def log_message(self, format: str, *args) -> None:
        """Suppress default stderr logging."""

    def do_GET(self) -> None:
        # 1. DNS Rebinding check
        host = self.headers.get("Host", "")
        if not (host.startswith(("127.0.0.1", "localhost"))):
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"Forbidden: Invalid Host header")
            return

        # 2. Origin / CSRF check
        origin = self.headers.get("Origin")
        if origin and not (origin.startswith(("http://127.0.0.1", "http://localhost"))):
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"Forbidden: Invalid Origin")
            return

        # 3. Auth Token check
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        token_in_query = query.get("token", [None])[0]
        token_in_header = self.headers.get("X-Rush-Auth")

        token = token_in_header or token_in_query
        if not token or token != self.auth_token:
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"Unauthorized: Missing or invalid token")
            return

        # 4. Routing
        if parsed.path == "/" or parsed.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML_TEMPLATE.encode("utf-8"))
        elif parsed.path == "/api/findings":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            data = [
                {
                    "tool": r.tool,
                    "status": r.status,
                    "summary": r.summary,
                    "findings_count": len(r.findings),
                }
                for r in self.cached_results
            ]
            self.wfile.write(json.dumps(data).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()
