"""Real loopback HTTP contract tests for the P66-01 canonical dashboard API.

Covers §3.6-3.7 body/header limits, cookie+CSRF+origin mutation gating, the
private reconnect-control boundary, and public vs. private health redaction.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

from rush.dashboard.server import create_dashboard_server

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "dashboard"


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
    resp = _post(
        f"{base_url}/api/session", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status == 200
    payload = json.loads(resp.read())
    cookie_value = resp.headers.get("Set-Cookie").split(";")[0]
    return cookie_value, payload["csrf_token"]


def test_body_and_header_limits() -> None:
    project_a = _load_fixture("project_a.json")
    server, ctx, token = create_dashboard_server({"project-a": project_a})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        cookie, csrf = _bootstrap_session(base_url, token)
        headers = {
            "Cookie": cookie,
            "X-Rush-CSRF": csrf,
            "Origin": base_url,
            "Content-Type": "application/json",
        }

        oversized_body = json.dumps(
            {
                "operation": "noop",
                "request_id": "req-big",
                "padding": "x" * (257 * 1024),
            }
        ).encode()
        too_big = _post(
            f"{base_url}/api/projects/project-a/actions",
            headers=headers,
            body=oversized_body,
        )
        assert too_big.status == 413

        many_headers = dict(headers)
        for i in range(80):
            many_headers[f"X-Extra-{i}"] = "1"
        too_many_headers = _post(
            f"{base_url}/api/projects/project-a/actions",
            headers=many_headers,
            body=json.dumps(
                {"operation": "noop", "request_id": "req-headers"}
            ).encode(),
        )
        assert too_many_headers.status == 400

        chunked = _post(
            f"{base_url}/api/projects/project-a/actions",
            headers={**headers, "Transfer-Encoding": "chunked"},
            body=json.dumps(
                {"operation": "noop", "request_id": "req-chunked"}
            ).encode(),
        )
        assert chunked.status == 400

        wrong_content_type = _post(
            f"{base_url}/api/projects/project-a/actions",
            headers={**headers, "Content-Type": "text/plain"},
            body=json.dumps({"operation": "noop", "request_id": "req-ct"}).encode(),
        )
        assert wrong_content_type.status == 400

        within_limits = _post(
            f"{base_url}/api/projects/project-a/actions",
            headers=headers,
            body=json.dumps({"operation": "noop", "request_id": "req-ok"}).encode(),
        )
        assert within_limits.status == 202
    finally:
        server.shutdown()
        server.server_close()


def test_cookie_csrf_and_origin_required() -> None:
    project_a = _load_fixture("project_a.json")
    server, ctx, token = create_dashboard_server({"project-a": project_a})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        cookie, csrf = _bootstrap_session(base_url, token)
        action_url = f"{base_url}/api/projects/project-a/actions"

        no_cookie = _post(
            action_url,
            headers={
                "Origin": base_url,
                "X-Rush-CSRF": csrf,
                "Content-Type": "application/json",
            },
            body=json.dumps({"operation": "noop", "request_id": "req-a"}).encode(),
        )
        assert no_cookie.status == 401

        no_csrf = _post(
            action_url,
            headers={
                "Origin": base_url,
                "Cookie": cookie,
                "Content-Type": "application/json",
            },
            body=json.dumps({"operation": "noop", "request_id": "req-b"}).encode(),
        )
        assert no_csrf.status == 403

        wrong_csrf = _post(
            action_url,
            headers={
                "Origin": base_url,
                "Cookie": cookie,
                "X-Rush-CSRF": "not-the-real-token",
                "Content-Type": "application/json",
            },
            body=json.dumps({"operation": "noop", "request_id": "req-c"}).encode(),
        )
        assert wrong_csrf.status == 403

        cross_origin = _post(
            action_url,
            headers={
                "Origin": "http://127.0.0.1:1",
                "Cookie": cookie,
                "X-Rush-CSRF": csrf,
                "Content-Type": "application/json",
            },
            body=json.dumps({"operation": "noop", "request_id": "req-d"}).encode(),
        )
        assert cross_origin.status == 403

        every_check_passes = _post(
            action_url,
            headers={
                "Origin": base_url,
                "Cookie": cookie,
                "X-Rush-CSRF": csrf,
                "Content-Type": "application/json",
            },
            body=json.dumps({"operation": "noop", "request_id": "req-e"}).encode(),
        )
        assert every_check_passes.status == 202
    finally:
        server.shutdown()
        server.server_close()


def test_reconnect_control_cannot_be_used_by_browser() -> None:
    project_a = _load_fixture("project_a.json")
    server, ctx, token = create_dashboard_server({"project-a": project_a})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        cookie, _csrf = _bootstrap_session(base_url, token)
        control_token = ctx.auth.control_capability

        # A browser-shaped request (Origin present) is rejected even with the
        # correct control capability.
        browser_like = _post(
            f"{base_url}/api/session/bootstrap",
            headers={
                "Origin": base_url,
                "X-Rush-Control": control_token,
                "Content-Length": "0",
            },
        )
        assert browser_like.status == 401

        # A request carrying the browser's own authenticated cookie is
        # rejected even with the correct control capability -- this endpoint
        # accepts no cookie at all.
        cookie_present = _post(
            f"{base_url}/api/session/bootstrap",
            headers={
                "Cookie": cookie,
                "X-Rush-Control": control_token,
                "Content-Length": "0",
            },
        )
        assert cookie_present.status == 401

        # The browser never possesses the control capability in the first
        # place: no cookie, no Origin, no control header still fails.
        no_control = _post(
            f"{base_url}/api/session/bootstrap", headers={"Content-Length": "0"}
        )
        assert no_control.status == 401

        # A genuine CLI-shaped request (no cookie, no Origin, valid control)
        # succeeds.
        genuine = _post(
            f"{base_url}/api/session/bootstrap",
            headers={"X-Rush-Control": control_token, "Content-Length": "0"},
        )
        assert genuine.status == 200
        payload = json.loads(genuine.read())
        assert "bootstrap_token" in payload
    finally:
        server.shutdown()
        server.server_close()


def test_private_health_matches_descriptor_and_public_health_is_redacted() -> None:
    project_a = _load_fixture("project_a.json")
    server, ctx, token = create_dashboard_server({"project-a": project_a})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        cookie, _csrf = _bootstrap_session(base_url, token)

        public = _get(f"{base_url}/api/health")
        assert public.status == 200
        public_body = json.loads(public.read())
        assert public_body == {"ready": True, "schema_version": 1}
        assert "server_id" not in public_body
        assert "pid" not in public_body
        assert "start_nonce" not in public_body

        private = _get(
            f"{base_url}/api/control/health",
            headers={"X-Rush-Control": ctx.auth.control_capability},
        )
        assert private.status == 200
        private_body = json.loads(private.read())
        assert private_body == {
            "schema_version": 1,
            "server_id": ctx.server_id,
            "pid": ctx.pid,
            "start_nonce": ctx.start_nonce,
        }

        cookie_only = _get(f"{base_url}/api/control/health", headers={"Cookie": cookie})
        assert cookie_only.status == 401

        bearer_only = _get(
            f"{base_url}/api/control/health",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert bearer_only.status == 401

        with_origin = _get(
            f"{base_url}/api/control/health",
            headers={"X-Rush-Control": ctx.auth.control_capability, "Origin": base_url},
        )
        assert with_origin.status == 403
    finally:
        server.shutdown()
        server.server_close()


def test_duplicate_mutation_id_returns_original_run() -> None:
    project_a = _load_fixture("project_a.json")
    server, ctx, token = create_dashboard_server({"project-a": project_a})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        cookie, csrf = _bootstrap_session(base_url, token)
        headers = {
            "Cookie": cookie,
            "X-Rush-CSRF": csrf,
            "Origin": base_url,
            "Content-Type": "application/json",
        }
        body = json.dumps(
            {"operation": "noop", "request_id": "same-mutation-id"}
        ).encode()

        first = _post(
            f"{base_url}/api/projects/project-a/actions", headers=headers, body=body
        )
        assert first.status == 202
        first_payload = json.loads(first.read())

        second = _post(
            f"{base_url}/api/projects/project-a/actions", headers=headers, body=body
        )
        assert second.status == 202
        second_payload = json.loads(second.read())

        assert first_payload["data"]["run_id"] == second_payload["data"]["run_id"]
        assert ctx.mutations._run_counter == 1

        different_body = json.dumps(
            {"operation": "scan_start", "request_id": "same-mutation-id"}
        ).encode()
        conflict = _post(
            f"{base_url}/api/projects/project-a/actions",
            headers=headers,
            body=different_body,
        )
        assert conflict.status == 409
    finally:
        server.shutdown()
        server.server_close()
