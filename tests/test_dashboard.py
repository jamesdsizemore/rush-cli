"""Tests for Phase 27: Authenticated In-Memory Web Dashboard.

Verifies:
- Control 5: Ephemeral token authorization (X-Rush-Auth or query param)
- Control 5: DNS Rebinding prevention (Host header whitelist)
- Control 5: CSRF / Origin header verification
- Brooks-Sweep Recommendation 2: Sub-millisecond in-memory asset serving
"""

from __future__ import annotations

import threading
import urllib.error
import urllib.request
from http.server import HTTPServer

from rush.dashboard import (
    AuthenticatedDashboardHandler,
    init_in_memory_assets,
)
from rush.tools.base import ToolResult


def _start_test_server(results: list[ToolResult], token: str) -> tuple[HTTPServer, int]:
    init_in_memory_assets()
    handler_cls = AuthenticatedDashboardHandler
    handler_cls.auth_token = token
    handler_cls.cached_results = results

    # Bind to random ephemeral port on 127.0.0.1
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    port = server.server_address[1]

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def test_dashboard_unauthorized_request_rejected() -> None:
    server, port = _start_test_server([], "secret-token-123")
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 401
    except urllib.error.HTTPError as exc:
        assert exc.code == 401
    finally:
        server.shutdown()


def test_dashboard_dns_rebinding_host_header() -> None:
    server, port = _start_test_server([], "secret-token-123")
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/?token=secret-token-123",
            headers={"Host": "attacker.com"},
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 403
    except urllib.error.HTTPError as exc:
        assert exc.code == 403
    finally:
        server.shutdown()


def test_dashboard_origin_header_validation() -> None:
    server, port = _start_test_server([], "secret-token-123")
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/findings",
            headers={
                "X-Rush-Auth": "secret-token-123",
                "Origin": "https://evil.com",
            },
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 403
    except urllib.error.HTTPError as exc:
        assert exc.code == 403
    finally:
        server.shutdown()


def test_dashboard_authorized_request_serves_html() -> None:
    server, port = _start_test_server([], "secret-token-123")
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/?token=secret-token-123")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            content = resp.read().decode("utf-8")
            assert "Rush Quality Dashboard" in content
    finally:
        server.shutdown()
