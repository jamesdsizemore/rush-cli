"""Tests for Phase 27: Authenticated In-Memory Web Dashboard.

Verifies:
- Control 5: Ephemeral token authorization (X-Rush-Auth or query param)
- Control 5: DNS Rebinding prevention (Host header whitelist)
- Control 5: CSRF / Origin header verification
- Brooks-Sweep Recommendation 2: Sub-millisecond in-memory asset serving
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import HTTPServer
from pathlib import Path

from rush.dashboard import (
    AuthenticatedDashboardHandler,
    init_in_memory_assets,
)
from rush.dashboard.server import (
    bootstrap_launch_url,
    create_dashboard_server,
    reconnect_dashboard,
)
from rush.tools.base import ToolResult

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "dashboard"


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


def test_dashboard_findings_serializes_canonical_result() -> None:
    result = ToolResult(
        tool="lint",
        status="fail",
        duration_ms=12,
        summary="One lint error",
        findings=[{"path": "app.py", "severity": "error", "message": "Unused import"}],
    )
    server, port = _start_test_server([result], "findings-token")
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/findings",
            headers={"X-Rush-Auth": "findings-token"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            assert response.status == 200
            assert json.load(response) == [
                {
                    "tool": "lint",
                    "status": "fail",
                    "summary": "One lint error",
                    "findings_count": 1,
                }
            ]
    finally:
        server.shutdown()
        server.server_close()


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


# --- P66-01: canonical authenticated per-server API (real loopback HTTP) ----


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


def _serve(server) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def _get(url: str, headers: dict | None = None):
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        return urllib.request.urlopen(req, timeout=5)
    except urllib.error.HTTPError as exc:
        return exc


def _post(url: str, headers: dict | None = None, body: bytes = b""):
    req = urllib.request.Request(url, data=body, headers=headers or {}, method="POST")
    try:
        return urllib.request.urlopen(req, timeout=5)
    except urllib.error.HTTPError as exc:
        return exc


def _bootstrap_session(base_url: str, token: str) -> tuple[str, str]:
    """Exchange a bootstrap token; return (cookie_header_value, csrf_token)."""
    resp = _post(
        f"{base_url}/api/session", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status == 200
    payload = json.loads(resp.read())
    set_cookie = resp.headers.get("Set-Cookie")
    assert set_cookie is not None
    cookie_value = set_cookie.split(";")[0]
    return cookie_value, payload["csrf_token"]


def test_browser_snapshot_contract() -> None:
    project_a = _load_fixture("project_a.json")
    project_b = _load_fixture("project_b.json")
    server, ctx, token = create_dashboard_server(
        {"project-a": project_a, "project-b": project_b}
    )
    _serve(server)
    try:
        base_url = ctx.launch_origin
        cookie, _csrf = _bootstrap_session(base_url, token)

        resp_a = _get(
            f"{base_url}/api/projects/project-a/snapshot", headers={"Cookie": cookie}
        )
        assert resp_a.status == 200
        body_a = json.loads(resp_a.read())
        assert body_a["schema_version"] == 1
        assert body_a["project_id"] == "project-a"
        assert body_a["sequence"] == 1
        finding_ids = {f["id"] for f in body_a["data"]["findings"]}
        assert finding_ids == {"f1", "f2", "f3"}
        assert {m["id"] for m in body_a["data"]["memories"]} == {"m1", "m2"}
        assert body_a["data"]["agents"][0]["id"] == "ag1"

        resp_b = _get(
            f"{base_url}/api/projects/project-b/snapshot", headers={"Cookie": cookie}
        )
        body_b = json.loads(resp_b.read())
        assert body_b["project_id"] == "project-b"
        assert {f["id"] for f in body_b["data"]["findings"]} == {"f1-b", "f2-b", "f3-b"}

        missing = _get(
            f"{base_url}/api/projects/nope/snapshot", headers={"Cookie": cookie}
        )
        assert missing.status == 404
    finally:
        server.shutdown()
        server.server_close()


def test_two_servers_keep_auth_and_state_isolated() -> None:
    project_a = _load_fixture("project_a.json")
    server1, ctx1, token1 = create_dashboard_server({"project-a": project_a})
    server2, ctx2, token2 = create_dashboard_server({"project-a": project_a})
    _serve(server1)
    _serve(server2)
    try:
        assert ctx1.auth.control_capability != ctx2.auth.control_capability
        assert token1 != token2

        # Server 2's bootstrap token must not work against server 1.
        rejected = _post(
            f"{ctx1.launch_origin}/api/session",
            headers={"Authorization": f"Bearer {token2}"},
        )
        assert rejected.status == 401

        cookie1, _ = _bootstrap_session(ctx1.launch_origin, token1)
        cookie2, _ = _bootstrap_session(ctx2.launch_origin, token2)
        assert (
            cookie1.split("=")[0] != cookie2.split("=")[0]
        )  # distinct per-server cookie names

        # Server 1's session cookie must not authenticate against server 2.
        cross = _get(
            f"{ctx2.launch_origin}/api/projects/project-a/snapshot",
            headers={"Cookie": cookie1},
        )
        assert cross.status == 401

        # Server 1's control capability must not satisfy server 2's control endpoint.
        cross_control = _get(
            f"{ctx2.launch_origin}/api/control/health",
            headers={"X-Rush-Control": ctx1.auth.control_capability},
        )
        assert cross_control.status == 401
    finally:
        server1.shutdown()
        server1.server_close()
        server2.shutdown()
        server2.server_close()


def test_host_and_origin_exact_authority() -> None:
    project_a = _load_fixture("project_a.json")
    server, ctx, token = create_dashboard_server({"project-a": project_a})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        cookie, csrf = _bootstrap_session(base_url, token)

        wrong_host = _get(
            f"http://127.0.0.1:{ctx.bound_port}/api/health",
            headers={"Host": f"127.0.0.1:{ctx.bound_port + 1}"},
        )
        assert wrong_host.status == 403

        wrong_origin = _get(
            f"{base_url}/api/projects/project-a/snapshot",
            headers={"Cookie": cookie, "Origin": "http://127.0.0.1.evil.example:1"},
        )
        assert wrong_origin.status == 403

        mutation_no_origin = _post(
            f"{base_url}/api/projects/project-a/actions",
            headers={
                "Cookie": cookie,
                "X-Rush-CSRF": csrf,
                "Content-Type": "application/json",
            },
            body=json.dumps(
                {"operation": "noop", "request_id": "req-authority-1"}
            ).encode(),
        )
        assert mutation_no_origin.status == 403

        mutation_exact_origin = _post(
            f"{base_url}/api/projects/project-a/actions",
            headers={
                "Cookie": cookie,
                "X-Rush-CSRF": csrf,
                "Content-Type": "application/json",
                "Origin": base_url,
            },
            body=json.dumps(
                {"operation": "noop", "request_id": "req-authority-2"}
            ).encode(),
        )
        assert mutation_exact_origin.status == 202

        # Raw socket: duplicate Host headers must be rejected outright.
        import socket

        sock = socket.create_connection(("127.0.0.1", ctx.bound_port), timeout=5)
        try:
            request_text = (
                f"GET /api/health HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{ctx.bound_port}\r\n"
                f"Host: 127.0.0.1:{ctx.bound_port}\r\n"
                f"Connection: close\r\n\r\n"
            )
            sock.sendall(request_text.encode("ascii"))
            raw_response = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                raw_response += chunk
            assert b"403" in raw_response.split(b"\r\n", 1)[0]
        finally:
            sock.close()
    finally:
        server.shutdown()
        server.server_close()


def test_serialization_failure_returns_error_before_headers() -> None:
    unserializable_project = {
        "project_id": "broken",
        "source_identity": "broken",
        "sink": object(),
    }
    server, ctx, token = create_dashboard_server({"broken": unserializable_project})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        cookie, _csrf = _bootstrap_session(base_url, token)
        resp = _get(
            f"{base_url}/api/projects/broken/snapshot", headers={"Cookie": cookie}
        )
        assert resp.status == 500
        body = json.loads(resp.read())
        assert body["error"]["code"] == "serialization_error"
        assert "Traceback" not in json.dumps(body)
    finally:
        server.shutdown()
        server.server_close()


def test_reload_restores_cookie_session_without_bearer_storage() -> None:
    project_a = _load_fixture("project_a.json")
    server, ctx, token = create_dashboard_server({"project-a": project_a})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        cookie, csrf = _bootstrap_session(base_url, token)

        # Reload: GET /api/session with only the cookie, no Authorization header.
        restore = _get(f"{base_url}/api/session", headers={"Cookie": cookie})
        assert restore.status == 200
        restored = json.loads(restore.read())
        assert restored["csrf_token"] == csrf

        # The consumed bootstrap token cannot be exchanged again (never stored
        # for reuse; reload never depends on a stashed Bearer token).
        replay = _post(
            f"{base_url}/api/session", headers={"Authorization": f"Bearer {token}"}
        )
        assert replay.status == 401

        no_cookie = _get(f"{base_url}/api/session")
        assert no_cookie.status == 401
    finally:
        server.shutdown()
        server.server_close()


def test_restart_or_expiry_requires_reauthorization() -> None:
    project_a = _load_fixture("project_a.json")
    server, ctx, token = create_dashboard_server({"project-a": project_a})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        cookie, _csrf = _bootstrap_session(base_url, token)
        cookie_value = cookie.split("=", 1)[1]

        # Simulate expiry by forcing this session's expiry into the past.
        session = ctx.auth.get_session(cookie_value)
        assert session is not None
        session.expires_at = 0.0

        expired = _get(
            f"{base_url}/api/projects/project-a/snapshot", headers={"Cookie": cookie}
        )
        assert expired.status == 401

        cannot_mutate = _post(
            f"{base_url}/api/projects/project-a/actions",
            headers={
                "Cookie": cookie,
                "Origin": base_url,
                "Content-Type": "application/json",
            },
            body=json.dumps(
                {"operation": "noop", "request_id": "req-expired"}
            ).encode(),
        )
        assert cannot_mutate.status == 401

        # A brand-new server instance (simulated restart) never honors the old
        # server's bootstrap token or session cookie.
        server2, ctx2, _token2 = create_dashboard_server({"project-a": project_a})
        _serve(server2)
        try:
            restarted = _get(
                f"{ctx2.launch_origin}/api/projects/project-a/snapshot",
                headers={"Cookie": cookie},
            )
            assert restarted.status == 401
        finally:
            server2.shutdown()
            server2.server_close()

        # Reconnect via the private control capability restores access without
        # losing project scope/state, without ever using cookie/Bearer.
        new_token = reconnect_dashboard(base_url, ctx.auth.control_capability)
        launch_url = bootstrap_launch_url(ctx, new_token)
        assert launch_url.endswith(f"#token={new_token}")
        new_cookie, _new_csrf = _bootstrap_session(base_url, new_token)
        reauthorized = _get(
            f"{base_url}/api/projects/project-a/snapshot",
            headers={"Cookie": new_cookie},
        )
        assert reauthorized.status == 200
    finally:
        server.shutdown()
        server.server_close()
