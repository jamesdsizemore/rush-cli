"""Tests for Phase 27: Authenticated In-Memory Web Dashboard.

Verifies:
- Control 5: Ephemeral token authorization (X-Rush-Auth or query param)
- Control 5: DNS Rebinding prevention (Host header whitelist)
- Control 5: CSRF / Origin header verification
- Brooks-Sweep Recommendation 2: Sub-millisecond in-memory asset serving
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from http.server import HTTPServer
from pathlib import Path

import pytest

from rush.dashboard import (
    AuthenticatedDashboardHandler,
    init_in_memory_assets,
)
from rush.dashboard.server import (
    _classify_mutating,
    bootstrap_launch_url,
    create_dashboard_server,
    reconnect_dashboard,
)
from rush.dashboard.state import MutationLedger, ProjectRegistry
from rush.memory.handoff import prepare_handoff
from rush.memory.store import MemoryArtifact, TypedArtifactStore
from rush.tools.base import ToolResult

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "dashboard"


@pytest.fixture(autouse=True)
def _isolated_dashboard_data_root(tmp_path, monkeypatch):
    """P69-01.2d: `MutationLedger` now persists durably (previously pure
    in-memory), so every test in this module gets an isolated data root by
    default -- otherwise a test that never monkeypatches `default_data_root`
    itself would read/write this OS user's real Rush data directory, leaking
    state across test runs. A test that explicitly monkeypatches its own
    `default_data_root` afterward still wins (it runs after this fixture)."""
    isolated_root = tmp_path / "rush-data-default"
    monkeypatch.setattr("rush.setup.provision.default_data_root", lambda: isolated_root)
    monkeypatch.setattr(
        "rush.workflows.projects.default_data_root", lambda: isolated_root
    )


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


def test_unrecognized_section_query_value_returns_400_not_full_snapshot() -> None:
    """P69-03.3 CONNECT: the section dispatch's real fallback branch used to
    serve the full `record.snapshot` for *any* unmatched `section` value --
    including a typo or a stale client's old section name -- instead of
    rejecting it. A missing `section` (the default, bare `/snapshot` full
    dict) must keep working unchanged; only a genuinely unrecognized,
    non-empty value is rejected."""
    project_a = _load_fixture("project_a.json")
    server, ctx, token = create_dashboard_server({"project-a": project_a})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        cookie, _csrf = _bootstrap_session(base_url, token)

        bad = _get(
            f"{base_url}/api/projects/project-a/snapshot?section=bogus",
            headers={"Cookie": cookie},
        )
        assert bad.status == 400
        body = json.loads(bad.read())
        assert body["error"]["code"] == "invalid_section"

        # The bare, section-less request still returns the full snapshot.
        still_works = _get(
            f"{base_url}/api/projects/project-a/snapshot", headers={"Cookie": cookie}
        )
        assert still_works.status == 200
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
                {
                    "operation": "noop",
                    "request_id": "req-authority-2",
                    "schema_version": 1,
                }
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


# --- P69-01.2 d-g: durable MutationLedger, reservation contract, per-operation-kind
# recovery receipts, _prepare_write() atomicity -----------------------------------


def _artifact(**overrides) -> MemoryArtifact:
    defaults = {
        "id": "artifact-default",
        "family": "memory",
        "subject": "domain_knowledge",
        "trust_tier": "DERIVED",
        "content": {"note": "default"},
        "source": "test",
        "created_at": time.time(),
    }
    defaults.update(overrides)
    return MemoryArtifact(**defaults)


def test_mutation_ledger_scoped_by_project_not_just_request_id(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr("rush.setup.provision.default_data_root", lambda: tmp_path)
    ledger = MutationLedger()
    calls: list[str] = []

    def _builder_a(op_id: str) -> tuple[int, bytes]:
        calls.append("a")
        return 200, b"response-a"

    def _builder_b(op_id: str) -> tuple[int, bytes]:
        calls.append("b")
        return 200, b"response-b"

    (_status_a, body_a), conflict_a = ledger.commit(
        "project-a", "req-1", "same-hash", _builder_a
    )
    (_status_b, body_b), conflict_b = ledger.commit(
        "project-b", "req-1", "same-hash", _builder_b
    )

    assert not conflict_a
    assert not conflict_b
    assert body_a == b"response-a"
    assert body_b == b"response-b"
    assert calls == ["a", "b"]


def test_two_processes_reserving_the_same_request_id_only_one_succeeds(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr("rush.setup.provision.default_data_root", lambda: tmp_path)
    # Two independent MutationLedger instances pointed at the same durable db
    # simulate two separate server processes racing the same request_id --
    # exclusivity must come from the storage layer, not a shared in-process lock.
    ledger_1 = MutationLedger()
    ledger_2 = MutationLedger()

    build_count = {"n": 0}
    count_lock = threading.Lock()
    start_barrier = threading.Barrier(2)

    def _slow_builder(op_id: str) -> tuple[int, bytes]:
        with count_lock:
            build_count["n"] += 1
        time.sleep(0.2)
        return 200, f"result-{op_id}".encode()

    results: list[tuple[tuple[int, bytes], bool]] = []
    results_lock = threading.Lock()

    def _run(ledger: MutationLedger) -> None:
        start_barrier.wait()
        outcome = ledger.commit("project-a", "req-race", "hash-race", _slow_builder)
        with results_lock:
            results.append(outcome)

    t1 = threading.Thread(target=_run, args=(ledger_1,))
    t2 = threading.Thread(target=_run, args=(ledger_2,))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert build_count["n"] == 1
    assert len(results) == 2
    (response_1, conflict_1), (response_2, conflict_2) = results
    assert not conflict_1
    assert not conflict_2
    assert response_1 == response_2


def test_mutation_ledger_survives_restart_and_prunes_expired_entries(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr("rush.setup.provision.default_data_root", lambda: tmp_path)
    ledger = MutationLedger()
    calls = {"n": 0}

    def _builder(op_id: str) -> tuple[int, bytes]:
        calls["n"] += 1
        return 200, b"terminal-response"

    ledger.commit("project-a", "req-restart", "hash-1", _builder)
    assert calls["n"] == 1

    # "Restart": a brand-new MutationLedger instance, same durable db path.
    restarted = MutationLedger()
    (_status, body), conflict = restarted.commit(
        "project-a", "req-restart", "hash-1", _builder
    )
    assert not conflict
    assert body == b"terminal-response"
    assert calls["n"] == 1  # replayed from disk, builder never re-invoked

    removed = restarted.prune_expired(ttl_seconds=0)
    assert removed == 1

    # Genuinely gone now: an identical retry reserves a brand-new entry.
    restarted.commit("project-a", "req-restart", "hash-1", _builder)
    assert calls["n"] == 2


def test_202_accepted_row_is_not_pruned_before_operation_reaches_terminal_state(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr("rush.setup.provision.default_data_root", lambda: tmp_path)
    ledger = MutationLedger()
    captured: dict[str, str] = {}

    def _builder(op_id: str) -> tuple[int, bytes]:
        captured["id"] = op_id
        return 202, b'{"accepted": true}'

    (status, body), conflict = ledger.commit(
        "project-a", "req-async", "hash-async", _builder
    )
    assert status == 202
    assert not conflict

    assert ledger.prune_expired(ttl_seconds=0) == 0  # still pending, never pruned

    # Identical retry still replays the 202 -- a valid ledger entry even
    # though it is not yet this operation's terminal outcome.
    (status2, body2), _conflict2 = ledger.commit(
        "project-a", "req-async", "hash-async", _builder
    )
    assert status2 == 202
    assert body2 == body

    ledger.record_status_transition(captured["id"], "terminal", {"final_status": 200})
    assert ledger.prune_expired(ttl_seconds=0) == 1


def test_crash_between_effect_and_ledger_persist_is_recoverable_from_preallocated_id(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr("rush.setup.provision.default_data_root", lambda: tmp_path)
    ledger = MutationLedger()
    store = TypedArtifactStore(tmp_path / "project")

    def _crashing_builder(op_id: str) -> tuple[int, bytes]:
        # The effect commits durably (its own transaction) before the
        # process "crashes" -- commit() never reaches finalize().
        store.write(_artifact(id="artifact-crash"), receipt_operation_id=op_id)
        raise RuntimeError("simulated crash after effect committed")

    with pytest.raises(RuntimeError):
        ledger.commit("project-a", "req-crash", "hash-crash", _crashing_builder)

    with sqlite3.connect(str(tmp_path / "dashboard" / "mutation_ledger.db")) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT operation_id, status FROM mutation_ledger "
            "WHERE project_id = ? AND request_id = ?",
            ("project-a", "req-crash"),
        ).fetchone()
    assert row["status"] == "pending"
    receipt = store.get_receipt(row["operation_id"])
    assert receipt is not None
    assert receipt["kind"] == "create"
    assert receipt["artifact_id"] == "artifact-crash"


def test_insertion_failure_after_conflict_delete_rolls_back_the_delete_too_p69_01(
    tmp_path,
) -> None:
    store = TypedArtifactStore(tmp_path / "project")
    # Directly seed a STATED row (mirrors test_phase61_trust.py's
    # `_insert_stated_row` pattern) rather than going through promote(),
    # which would additionally require a real, resolvable symbol_ref.
    with sqlite3.connect(str(store.db_path)) as conn:
        conn.execute(
            "INSERT INTO memory_artifacts "
            "(id, family, subject, trust_tier, content, source, created_at, symbol_ref) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                "artifact-existing",
                "memory",
                "domain_knowledge",
                "STATED",
                json.dumps({"flag": True}),
                "test",
                time.time(),
                "sym-conflict",
            ),
        )
        conn.commit()
    assert store.get_current("artifact-existing").trust_tier == "STATED"

    # Pre-seed a colliding (id, version=1) row so _insert_row's second INSERT
    # fails mid-transaction, inside the same transaction as the conflict-delete
    # evaluate_conflict() will trigger below.
    with sqlite3.connect(str(store.db_path)) as conn:
        conn.execute(
            "INSERT INTO memory_artifact_versions "
            "(artifact_id, artifact_version, content, source, trust_tier, created_at, deleted) "
            "VALUES (?,1,?,?,?,?,0)",
            ("artifact-colliding", "{}", "test", "DERIVED", time.time()),
        )
        conn.commit()

    candidate = _artifact(
        id="artifact-colliding", content={"flag": False}, symbol_ref="sym-conflict"
    )
    with pytest.raises(sqlite3.IntegrityError):
        store.write(candidate)

    # The conflict-delete rolled back along with the failed insert.
    assert store.get_current("artifact-existing") is not None


def test_recovery_receipt_distinguishes_promotion_created_from_promotion_completed(
    tmp_path,
) -> None:
    store = TypedArtifactStore(tmp_path / "project")

    stored = store.write(
        _artifact(id="artifact-promoted", content={"note": "will be promoted"}),
        receipt_operation_id="op-create-1",
    )
    assert store.get_receipt("op-create-1")["kind"] == "create"

    stored, decision = store.promote(
        stored.id, user_stated=True, receipt_operation_id="op-promote-1"
    )
    assert decision.promoted is True
    assert store.get_receipt("op-promote-1")["kind"] == "promote"

    # A denied promotion gets a create receipt, never a promote receipt.
    stored2 = store.write(
        _artifact(id="artifact-denied", content={"note": "will not be promoted"}),
        receipt_operation_id="op-create-2",
    )
    assert store.get_receipt("op-create-2") is not None
    stored2, decision2 = store.promote(
        stored2.id,
        user_stated=False,
        candidate_sources=["only_one"],
        receipt_operation_id="op-promote-2",
    )
    assert decision2.promoted is False
    assert store.get_receipt("op-promote-2") is None


def test_recovery_receipt_correctly_attributes_edit_despite_intervening_unrelated_write(
    tmp_path,
) -> None:
    store = TypedArtifactStore(tmp_path / "project")
    store.write(_artifact(id="artifact-edit-target", content={"note": "v1"}))

    result_a = store.edit(
        "artifact-edit-target",
        {"note": "v2 by op-a"},
        expected_version=1,
        scope="domain_knowledge",
        apply=True,
        receipt_operation_id="op-a",
    )
    assert result_a["revision"] == 2

    result_b = store.edit(
        "artifact-edit-target",
        {"note": "v3 by op-b"},
        expected_version=2,
        scope="domain_knowledge",
        apply=True,
        receipt_operation_id="op-b",
    )
    assert result_b["revision"] == 3

    assert store.get_receipt("op-a")["revision"] == 2
    assert store.get_receipt("op-b")["revision"] == 3


def test_recovery_receipt_for_delete_exists_only_after_real_commit_not_before(
    tmp_path,
) -> None:
    store = TypedArtifactStore(tmp_path / "project")
    store.write(_artifact(id="artifact-to-delete", content={"note": "delete me"}))

    store.delete_batch(
        ["artifact-to-delete"],
        expected_revisions={"artifact-to-delete": 1},
        scope="domain_knowledge",
        apply=False,
        receipt_operation_id="op-delete-1",
    )
    assert store.get_receipt("op-delete-1") is None

    store.delete_batch(
        ["artifact-to-delete"],
        expected_revisions={"artifact-to-delete": 1},
        scope="domain_knowledge",
        apply=True,
        receipt_operation_id="op-delete-1",
    )
    receipt = store.get_receipt("op-delete-1")
    assert receipt is not None
    assert receipt["kind"] == "delete"


def test_crash_recovery_for_delete_uses_tombstone_not_object_lookup(tmp_path) -> None:
    store = TypedArtifactStore(tmp_path / "project")
    store.write(_artifact(id="artifact-deleted", content={"note": "gone soon"}))
    store.delete_batch(
        ["artifact-deleted"],
        expected_revisions={"artifact-deleted": 1},
        scope="domain_knowledge",
        apply=True,
    )

    def _delete_completed(artifact_id: str) -> bool:
        with sqlite3.connect(str(store.db_path)) as conn:
            row = conn.execute(
                "SELECT 1 FROM memory_changes WHERE artifact_id = ? AND tombstone = 1",
                (artifact_id,),
            ).fetchone()
        return row is not None

    assert _delete_completed("artifact-deleted") is True
    assert store.get_current("artifact-deleted") is None

    # An id that never existed is *also* absent from memory_artifacts, but has
    # no tombstone -- mere absence can't distinguish "deleted" from "never
    # existed"; the tombstone can.
    assert store.get_current("artifact-never-existed") is None
    assert _delete_completed("artifact-never-existed") is False


def test_crash_recovery_for_edit_distinguishes_applied_from_not_applied_via_version_receipt(
    tmp_path,
) -> None:
    store = TypedArtifactStore(tmp_path / "project")
    store.write(_artifact(id="artifact-edit-recovery", content={"note": "v1"}))

    applied = store.edit(
        "artifact-edit-recovery",
        {"note": "v2"},
        expected_version=1,
        scope="domain_knowledge",
        apply=True,
        receipt_operation_id="op-applied",
    )
    applied_receipt = store.get_receipt("op-applied")
    assert applied_receipt is not None
    assert applied_receipt["revision"] == applied["revision"]

    not_applied = store.edit(
        "artifact-edit-recovery",
        {"note": "preview only"},
        expected_version=2,
        scope="domain_knowledge",
        apply=False,
        receipt_operation_id="op-not-applied",
    )
    assert not_applied["applied"] is False
    assert store.get_receipt("op-not-applied") is None


def test_crash_recovery_for_handoff_reconciles_each_persisted_effect_independently(
    tmp_path,
) -> None:
    store = TypedArtifactStore(tmp_path / "project")
    session_a, _cap_a, _delta_a = prepare_handoff(
        store,
        root=tmp_path,
        audience="agent-a",
        granted_ids=["seed"],
        session_allowlist=["test"],
        receipt_operation_id="op-handoff-a",
    )
    session_b, _cap_b, _delta_b = prepare_handoff(
        store,
        root=tmp_path,
        audience="agent-b",
        granted_ids=["seed"],
        session_allowlist=["test"],
        receipt_operation_id="op-handoff-b",
    )

    receipt_a = store.get_receipt("op-handoff-a")
    receipt_b = store.get_receipt("op-handoff-b")
    assert receipt_a is not None
    assert receipt_b is not None
    assert receipt_a["artifact_id"] == session_a.session_id
    assert receipt_b["artifact_id"] == session_b.session_id
    assert receipt_a["artifact_id"] != receipt_b["artifact_id"]


def test_snapshot_memories_reads_inventory_and_generation_in_one_atomic_transaction(
    tmp_path,
) -> None:
    store = TypedArtifactStore(tmp_path / "project")
    errors: list[tuple[int, int]] = []

    def _writer() -> None:
        for i in range(60):
            store.write(_artifact(id=f"artifact-{i}", content={"note": f"n{i}"}))

    writer = threading.Thread(target=_writer)
    writer.start()

    for _ in range(60):
        memories, generation = store.snapshot_memories()
        if generation != len(memories):
            errors.append((generation, len(memories)))
        time.sleep(0.001)
    writer.join(timeout=10)

    assert errors == []


def test_current_generation_accepts_an_existing_connection_and_does_not_open_a_second_one(
    tmp_path,
) -> None:
    store = TypedArtifactStore(tmp_path / "project")
    connect_calls = {"n": 0}
    original_connect = store._connect

    def _counting_connect() -> sqlite3.Connection:
        connect_calls["n"] += 1
        return original_connect()

    store._connect = _counting_connect

    with store._connect() as conn:
        pass
    connect_calls["n"] = 0
    store.current_generation(conn)
    assert connect_calls["n"] == 0

    store.current_generation()
    assert connect_calls["n"] == 1


def test_refresh_memories_rejects_a_stale_generation_pair_from_snapshot_memories() -> (
    None
):
    registry = ProjectRegistry({"project-a": {"source_identity": "src-a"}})
    assert registry.refresh_memories("project-a", [{"id": "m1"}], 5) is True
    assert registry.get("project-a").snapshot["memories"] == [{"id": "m1"}]
    assert registry.get("project-a").memory_generation == 5

    assert registry.refresh_memories("project-a", [{"id": "stale"}], 3) is False
    assert registry.get("project-a").snapshot["memories"] == [{"id": "m1"}]

    assert registry.refresh_memories("project-a", [{"id": "same-gen"}], 5) is False
    assert registry.get("project-a").snapshot["memories"] == [{"id": "m1"}]

    assert registry.refresh_memories("project-a", [{"id": "m2"}], 6) is True
    assert registry.get("project-a").snapshot["memories"] == [{"id": "m2"}]


def test_preview_and_read_only_actions_write_no_durable_ledger_entry(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr("rush.setup.provision.default_data_root", lambda: tmp_path)
    ledger = MutationLedger()
    calls = {"n": 0}

    def _builder(op_id: str) -> tuple[int, bytes]:
        calls["n"] += 1
        assert op_id == ""  # a non-mutating call never gets a real reservation id
        return 200, b"read-only-response"

    for operation, arguments in (
        ("provision_plan", {}),
        ("data_export", {}),
        ("memory_edit", {"apply": False}),
    ):
        mutating = _classify_mutating(operation, arguments)
        assert mutating is False
        ledger.commit(
            "project-a",
            f"req-{operation}",
            "hash",
            _builder,
            operation_type=operation,
            mutating=mutating,
        )

    with sqlite3.connect(str(tmp_path / "dashboard" / "mutation_ledger.db")) as conn:
        count = conn.execute("SELECT COUNT(*) FROM mutation_ledger").fetchone()[0]
    assert count == 0
    assert calls["n"] == 3


def test_handoff_preview_classified_mutating_in_p69_01_matching_its_still_real_writes() -> (
    None
):
    assert _classify_mutating("handoff_preview", {}) is True
