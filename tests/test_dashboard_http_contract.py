"""Real loopback HTTP contract tests for the P66-01 canonical dashboard API.

Covers §3.6-3.7 body/header limits, cookie+CSRF+origin mutation gating, the
private reconnect-control boundary, and public vs. private health redaction.
"""

from __future__ import annotations

import json
import os
import secrets
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from contextlib import contextmanager, suppress
from pathlib import Path
from unittest.mock import patch

import pytest
from _process_children import spawn_child

from rush.dashboard import state as dashboard_state
from rush.dashboard.server import (
    DashboardContext,
    _ActionDenied,
    _admit_and_launch,
    _run_supervised,
    create_dashboard_server,
    stop_all_dashboard_contexts,
)
from rush.dashboard.state import (
    MutationLedger,
    OwnerLock,
    PendingOutcomeQueue,
    ScanConflictError,
    claim_dead_owner,
    cross_process_project_lock,
    probe_owner_alive,
    reconcile_admissions,
)
from rush.memory.store import MemoryArtifact, OwnerScope, TypedArtifactStore
from rush.tools.project import ProjectTool
from rush.workflows.project_run import ScanBusyError, _run_lock
from rush.workflows.projects import register_project

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
    yield
    # T027: stop every DashboardContext's recovery/outcome-retry threads
    # created by this test before the isolated data root above is reverted
    # -- otherwise a leaked thread keeps firing for the rest of this pytest
    # process's life against a now-stale (or, once reverted, real shared)
    # data root, which is exactly how the T027 full-suite hang accumulated.
    stop_all_dashboard_contexts()


class _RecordingConnection:
    """Wraps a real sqlite3 connection so a test can see the exact statement
    sequence a `MutationLedger` transaction issues, and can make a chosen
    statement fail (P69-02.2g/i transaction-boundary tests)."""

    def __init__(self, conn, statements: list[str], failures: list[dict]) -> None:
        self._conn = conn
        self._statements = statements
        self._failures = failures

    def execute(self, sql: str, *args):
        normalized = " ".join(sql.split())
        self._statements.append(normalized)
        for rule in self._failures:
            if rule["times"] > 0 and normalized.startswith(rule["sql"]):
                rule["times"] -= 1
                raise sqlite3.OperationalError(rule["message"])
        return self._conn.execute(sql, *args)

    def executescript(self, sql: str):
        return self._conn.executescript(sql)

    def commit(self) -> None:
        self._statements.append("COMMIT")
        self._conn.commit()

    def rollback(self) -> None:
        self._statements.append("ROLLBACK")
        self._conn.rollback()

    def __enter__(self):
        self._conn.__enter__()
        return self

    def __exit__(self, *exc_info):
        return self._conn.__exit__(*exc_info)


def _instrument(ledger: MutationLedger) -> dict:
    state = getattr(ledger, "_test_instrumentation", None)
    if state is None:
        statements: list[str] = []
        failures: list[dict] = []
        original = ledger._connect

        def _connect():
            return _RecordingConnection(original(), statements, failures)

        ledger._connect = _connect
        state = {"statements": statements, "failures": failures}
        ledger._test_instrumentation = state
    return state


def _record_sql(ledger: MutationLedger) -> list[str]:
    return _instrument(ledger)["statements"]


def _fail_on(
    ledger: MutationLedger,
    sql: str,
    *,
    times: int = 10_000_000,
    message: str = "disk I/O error",
) -> None:
    _instrument(ledger)["failures"].append(
        {"sql": sql, "times": times, "message": message}
    )


def _clear_failures(ledger: MutationLedger) -> None:
    _instrument(ledger)["failures"].clear()


def _admission_ctx(
    tmp_path: Path, *, recovery_interval: float = 3600.0
) -> DashboardContext:
    """A DashboardContext with no bound socket -- enough for the admission,
    worker-supervision and recovery unit tests. Its durable ledger and owner
    locks land under the autouse-isolated data root, not this OS user's real
    Rush directory."""
    assert tmp_path.is_dir()
    return DashboardContext(
        {},
        bound_host="127.0.0.1",
        bound_port=0,
        recovery_interval=recovery_interval,
    )


def _seed_operation(
    ledger: MutationLedger, operation_id: str, *, project_id: str = "project-a"
) -> None:
    """Insert one durable reservation row carrying a *known* operation_id.
    `reserve()` mints a random one, which these tests need to pin so they can
    assert against the exact admission slot they created."""
    with sqlite3.connect(str(ledger._db_path)) as conn:
        conn.execute(
            "INSERT INTO mutation_ledger (project_id, request_id, operation_id, "
            "operation_type, body_hash, status, created_at) VALUES (?,?,?,?,?,?,?)",
            (
                project_id,
                f"req-{operation_id}",
                operation_id,
                "scan_start",
                "hash-1",
                "pending",
                time.time(),
            ),
        )
        conn.commit()


def _chained_attachments(tmp_path: Path, *, terminal: bool = True) -> MutationLedger:
    """`op-a -> op-b -> op-c`, where `op-c` is the executing operation and the
    only one that ever reaches terminal: an attached id never receives its own
    status transition, so its terminality is purely derived (P69-02.2i)."""
    db_path = tmp_path / "prune.db"
    ledger = MutationLedger(db_path=db_path)
    now = time.time()
    with sqlite3.connect(str(db_path)) as conn:
        for operation_id in ("op-a", "op-b", "op-c"):
            is_target = terminal and operation_id == "op-c"
            conn.execute(
                "INSERT INTO mutation_ledger (project_id, request_id, operation_id, "
                "operation_type, body_hash, status, created_at, terminal_at, "
                "transition_status, transition_payload) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    "project-a",
                    f"req-{operation_id}",
                    operation_id,
                    "scan_start",
                    "hash-1",
                    "terminal" if is_target else "pending",
                    now - 10,
                    now - 10 if is_target else None,
                    "terminal" if is_target else None,
                    json.dumps({"status": "success"}) if is_target else None,
                ),
            )
        for attached, executing in (("op-a", "op-b"), ("op-b", "op-c")):
            conn.execute(
                "INSERT INTO operation_attachments (operation_id, "
                "executing_operation_id, created_at) VALUES (?,?,?)",
                (attached, executing, now),
            )
        conn.commit()
    return ledger


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


def _serve(server) -> threading.Thread:
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    )
    thread.start()
    return thread


def _child_hold_owner_lock(owner_id: str, data_root: str, hold_seconds: float) -> None:
    """Child-process target (P69-01 subsection h): acquire a real
    owner-liveness lock and sleep, so the parent can SIGKILL this process
    to simulate a genuine crash (the lock's own `finally`/context-manager
    release never runs -- only the kernel's on-exit release does)."""
    from rush.dashboard.state import OwnerLock

    OwnerLock(owner_id, data_root=Path(data_root))
    time.sleep(hold_seconds)


def _child_hold_scan_lock(project_root: str, hold_seconds: float) -> None:
    """Child-process target: hold the real scan-exclusion lock and sleep, so
    the parent can SIGKILL this process to prove the lock releases on real
    process death, not on any staleness timer."""
    with _run_lock(Path(project_root), timeout=10):
        time.sleep(hold_seconds)


def _fork_and_run(target, *args) -> int:
    """Run `target(*args)` in a real child process; return its pid.
    Callers use `_kill_and_reap` for an unclean (SIGKILL) death, which is
    the real crash scenario P69-01 subsection h's lock semantics defend
    against -- no reliance on the child's own cleanup code ever running."""
    json_args = [str(a) if isinstance(a, Path) else a for a in args]
    proc = spawn_child(target.__module__, target.__name__, json_args)
    return proc.pid


def _kill_and_reap(pid: int) -> None:
    with suppress(ProcessLookupError):
        os.kill(pid, signal.SIGKILL)
    with suppress(ChildProcessError):
        os.waitpid(pid, 0)


def test_two_servers_on_the_same_project_each_hold_their_own_distinct_owner_lock_not_one_shared_project_lock() -> (
    None
):
    project_a = _load_fixture("project_a.json")
    server1, ctx1, _token1 = create_dashboard_server({"project-a": project_a})
    server2, ctx2, _token2 = create_dashboard_server({"project-a": project_a})
    try:
        assert ctx1.owner_instance_id != ctx2.owner_instance_id
        assert ctx1._owner_lock.path != ctx2._owner_lock.path
        # Both servers' owner locks are simultaneously live -- neither
        # blocked the other, proving this is not one shared per-project
        # lock (a single per-project lock would contradict
        # `create_dashboard_server`'s own supported-concurrency guarantee).
        assert probe_owner_alive(ctx1.owner_instance_id) is True
        assert probe_owner_alive(ctx2.owner_instance_id) is True
    finally:
        server1.server_close()
        server2.server_close()


def test_recovery_probes_the_specific_recorded_owners_lock_not_a_project_wide_one(
    tmp_path,
) -> None:
    from rush.dashboard.state import OwnerLock

    live_id = "server:live-owner"
    dead_id = "server:dead-owner"
    OwnerLock(live_id, data_root=tmp_path)
    # `dead_id` never acquired a lock at all. Both "belong" to the same
    # project in spirit, but recovery must probe each row's own exact
    # recorded owner identity, never fall back to project-wide state.
    assert probe_owner_alive(live_id, data_root=tmp_path) is True
    assert probe_owner_alive(dead_id, data_root=tmp_path) is False


def test_second_server_can_acquire_lock_only_after_first_servers_real_process_exit(
    tmp_path,
) -> None:
    project_root = tmp_path / "proj"
    project_root.mkdir()
    pid = _fork_and_run(_child_hold_scan_lock, project_root, 30.0)
    try:
        time.sleep(1.5)  # real subprocess startup + import is slower than a fork
        with pytest.raises(ScanBusyError), _run_lock(project_root, timeout=0.3):
            pass
    finally:
        _kill_and_reap(pid)
    # The child was SIGKILLed -- its own cleanup code never ran. The kernel
    # released the lock the instant the process died; immediately
    # acquirable now, with no staleness wait.
    with _run_lock(project_root, timeout=1.0):
        pass


def test_slow_but_alive_owner_holding_the_lock_blocks_recovery_claim(tmp_path) -> None:
    owner_id = "server:slow-owner"
    pid = _fork_and_run(_child_hold_owner_lock, owner_id, tmp_path, 2.0)
    try:
        time.sleep(1.5)  # real subprocess startup + import is slower than a fork
        with claim_dead_owner(owner_id, data_root=tmp_path) as claimed:
            assert claimed is False
    finally:
        _kill_and_reap(pid)
    with claim_dead_owner(owner_id, data_root=tmp_path) as claimed:
        assert claimed is True


def test_lock_based_recovery_has_no_pid_reuse_failure_mode(tmp_path) -> None:
    owner_id = "server:never-started"
    # This owner never acquired its lock -- it's provably gone. Simulate
    # the exact pid-reuse hazard a naive `os.kill(pid, 0)`-based liveness
    # check would fall for: a real, currently-alive, unrelated process
    # happens to occupy a pid a dead owner might once have used -- this
    # test's own pid, which is definitely alive.
    os.kill(os.getpid(), 0)  # sanity: does not raise -- this process lives
    assert probe_owner_alive(owner_id, data_root=tmp_path) is False


def test_scan_lock_remains_exclusive_past_the_old_30s_staleness_threshold_while_scan_is_still_running(
    tmp_path,
) -> None:
    project_root = tmp_path / "proj"
    project_root.mkdir()
    with _run_lock(project_root, timeout=1.0):
        lock_path = project_root / ".rush" / "runs" / ".scan.lock"
        old = time.time() - 60.0  # 60s old -- well past the old 30s cutoff
        os.utime(lock_path, (old, old))
        with pytest.raises(ScanBusyError), _run_lock(project_root, timeout=0.3):
            pass


def test_scan_lock_becomes_acquirable_immediately_after_the_scan_itself_finishes_not_tied_to_process_exit(
    tmp_path,
) -> None:
    project_root = tmp_path / "proj"
    project_root.mkdir()
    with _run_lock(project_root, timeout=1.0):
        pass  # scan finishes; lock released -- same process, no exit
    with _run_lock(project_root, timeout=0.1):
        pass  # immediately re-acquirable, no wait


def test_concurrent_recovery_claims_on_the_same_pending_row_only_one_succeeds(
    tmp_path,
) -> None:
    owner_id = "server:dead-owner-raced"
    results: list[bool] = []
    results_lock = threading.Lock()

    def _try_claim() -> None:
        with claim_dead_owner(owner_id, data_root=tmp_path) as claimed:
            with results_lock:
                results.append(claimed)
            if claimed:
                time.sleep(0.2)  # hold the claim while "reconciling"

    threads = [threading.Thread(target=_try_claim) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    assert results.count(True) == 1


def test_second_server_starting_does_not_interrupt_first_servers_live_operation(
    tmp_path,
) -> None:
    project_a = _load_fixture("project_a.json")
    server1, ctx1, _token1 = create_dashboard_server({"project-a": project_a})
    try:
        project_root = tmp_path / "proj"
        project_root.mkdir()
        started = threading.Event()
        release = threading.Event()

        def _run_scan() -> None:
            with _run_lock(project_root, timeout=5.0):
                started.set()
                release.wait(timeout=5)

        worker = threading.Thread(target=_run_scan)
        worker.start()
        assert started.wait(timeout=2)

        # A second server starts up against the same project while the
        # first is mid-scan -- its construction must succeed and must not
        # disturb the first server's own live operation.
        server2, ctx2, _token2 = create_dashboard_server({"project-a": project_a})
        try:
            assert ctx1.owner_instance_id != ctx2.owner_instance_id
            # The first server's scan lock is still exclusively held -- the
            # second server's mere startup did not release it.
            with pytest.raises(ScanBusyError), _run_lock(project_root, timeout=0.2):
                pass
        finally:
            server2.server_close()
        release.set()
        worker.join(timeout=5)
    finally:
        server1.server_close()


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
            body=json.dumps(
                {"schema_version": 1, "operation": "noop", "request_id": "req-ok"}
            ).encode(),
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
            body=json.dumps(
                {"schema_version": 1, "operation": "noop", "request_id": "req-e"}
            ).encode(),
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
            {
                "schema_version": 1,
                "operation": "noop",
                "request_id": "same-mutation-id",
            }
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
            {
                "schema_version": 1,
                "operation": "scan_start",
                "request_id": "same-mutation-id",
            }
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


def test_csp_and_security_headers_present() -> None:
    project_a = _load_fixture("project_a.json")
    server, ctx, _token = create_dashboard_server({"project-a": project_a})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        resp = _get(f"{base_url}/")
        assert resp.status == 200
        assert resp.headers.get("Content-Security-Policy") == (
            "default-src 'none'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; font-src 'self'; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
            "form-action 'self'"
        )
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("Referrer-Policy") == "no-referrer"
        assert resp.headers.get("Cache-Control") == "no-store"

        health = _get(f"{base_url}/api/health")
        assert health.headers.get("Content-Security-Policy") is not None
        assert health.headers.get("X-Content-Type-Options") == "nosniff"
    finally:
        server.shutdown()
        server.server_close()


def test_get_requests_enforce_header_limits() -> None:
    project_a = _load_fixture("project_a.json")
    server, ctx, _token = create_dashboard_server({"project-a": project_a})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        many_headers = {f"X-Extra-{i}": "1" for i in range(80)}
        resp = _get(f"{base_url}/api/health", headers=many_headers)
        assert resp.status == 400
    finally:
        server.shutdown()
        server.server_close()


def test_missing_content_length_rejected_not_zeroed() -> None:
    project_a = _load_fixture("project_a.json")
    server, ctx, _token = create_dashboard_server({"project-a": project_a})
    _serve(server)
    try:
        host, port = ctx.bound_host, ctx.bound_port
        sock = socket.create_connection((host, port), timeout=5)
        try:
            request = (
                f"POST /api/session/bootstrap HTTP/1.1\r\n"
                f"Host: {host}:{port}\r\n"
                f"X-Rush-Control: {ctx.auth.control_capability}\r\n"
                f"\r\n"
            )
            sock.sendall(request.encode())
            response_bytes = sock.recv(4096)
        finally:
            sock.close()
        status_line = response_bytes.split(b"\r\n", 1)[0].decode()
        assert " 400 " in status_line
    finally:
        server.shutdown()
        server.server_close()


def test_concurrent_requests_beyond_bound_return_503() -> None:
    project_a = _load_fixture("project_a.json")
    server, ctx, _token = create_dashboard_server({"project-a": project_a})
    _serve(server)
    slow_sockets: list[socket.socket] = []
    try:
        host, port = ctx.bound_host, ctx.bound_port
        base_url = ctx.launch_origin
        for _ in range(8):
            sock = socket.create_connection((host, port), timeout=5)
            with suppress(OSError):
                sock.sendall(
                    f"GET /api/health HTTP/1.1\r\nHost: {host}:{port}\r\nX-Hold: ".encode()
                )
            slow_sockets.append(sock)
        time.sleep(0.3)
        resp = _get(f"{base_url}/api/health")
        assert resp.status == 503
        assert resp.headers.get("Retry-After") == "1"
    finally:
        for sock in slow_sockets:
            with suppress(OSError):
                sock.close()
        server.shutdown()
        server.server_close()


def test_worker_thread_count_stays_bounded_under_slow_incomplete_requests() -> None:
    project_a = _load_fixture("project_a.json")
    server, ctx, _token = create_dashboard_server({"project-a": project_a})
    _serve(server)
    baseline = threading.active_count()
    slow_sockets: list[socket.socket] = []
    try:
        host, port = ctx.bound_host, ctx.bound_port
        for _ in range(20):
            sock = socket.create_connection((host, port), timeout=5)
            with suppress(OSError):
                sock.sendall(
                    f"GET /api/health HTTP/1.1\r\nHost: {host}:{port}\r\nX-Hold: ".encode()
                )
            slow_sockets.append(sock)
        time.sleep(0.5)
        active = threading.active_count() - baseline
        assert active <= 8
    finally:
        for sock in slow_sockets:
            with suppress(OSError):
                sock.close()
        server.shutdown()
        server.server_close()


def test_bootstrap_and_action_rate_limits_return_429() -> None:
    project_a = _load_fixture("project_a.json")
    server, ctx, token = create_dashboard_server({"project-a": project_a})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        cookie, csrf = _bootstrap_session(base_url, token)

        # Bootstrap failures: 10 allowed per client IP per minute, the 11th
        # is rate-limited instead of falling through to normal 401 handling.
        for _ in range(10):
            resp = _post(
                f"{base_url}/api/session",
                headers={"Authorization": "Bearer not-the-real-token"},
            )
            assert resp.status == 401
        limited = _post(
            f"{base_url}/api/session",
            headers={"Authorization": "Bearer not-the-real-token"},
        )
        assert limited.status == 429
        assert limited.headers.get("Retry-After") == "1"

        # Actions: 60 allowed per session per minute, the 61st is limited.
        headers = {
            "Cookie": cookie,
            "X-Rush-CSRF": csrf,
            "Origin": base_url,
            "Content-Type": "application/json",
        }
        for i in range(60):
            resp = _post(
                f"{base_url}/api/projects/project-a/actions",
                headers=headers,
                body=json.dumps(
                    {"schema_version": 1, "operation": "noop", "request_id": f"rl-{i}"}
                ).encode(),
            )
            assert resp.status == 202
        limited_action = _post(
            f"{base_url}/api/projects/project-a/actions",
            headers=headers,
            body=json.dumps(
                {"schema_version": 1, "operation": "noop", "request_id": "rl-60"}
            ).encode(),
        )
        assert limited_action.status == 429
        assert limited_action.headers.get("Retry-After") == "1"
    finally:
        server.shutdown()
        server.server_close()


def test_error_and_success_bodies_redact_secret_bearing_content() -> None:
    project_a = _load_fixture("project_a.json")
    server, ctx, token = create_dashboard_server({"project-a": project_a})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        cookie, csrf = _bootstrap_session(base_url, token)

        with patch(
            "rush.dashboard.server._build_memory_section",
            side_effect=RuntimeError(f"boom {csrf} leaked"),
        ):
            resp = _get(
                f"{base_url}/api/projects/project-a/snapshot?section=memory",
                headers={"Cookie": cookie},
            )
        assert resp.status == 500
        body_text = resp.read().decode()
        assert csrf not in body_text
        assert "[REDACTED]" in body_text
    finally:
        server.shutdown()
        server.server_close()


def test_bootstrap_and_session_secrets_stored_as_digests_not_plaintext() -> None:
    """P69-01.3 CONNECT (auth.py digest storage) is out of this packet's
    allowed_files -- it is T006's scope. This RED test reproduces the gap
    and is expected to stay red until T006 lands."""
    project_a = _load_fixture("project_a.json")
    server, ctx, token = create_dashboard_server({"project-a": project_a})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        cookie, _csrf = _bootstrap_session(base_url, token)
        cookie_value = cookie.split("=", 1)[1]

        stored_values = json.dumps(
            {
                "bootstrap": vars(ctx.auth._bootstrap) if ctx.auth._bootstrap else {},
                "sessions": {
                    key: vars(session) for key, session in ctx.auth._sessions.items()
                },
            },
            default=str,
        )
        assert token not in stored_values
        assert cookie_value not in stored_values
    finally:
        server.shutdown()
        server.server_close()


def test_concurrent_direct_method_calls_to_exchange_bootstrap_mint_exactly_one_session() -> (
    None
):
    """S11: two threads synchronize immediately before calling the public
    `exchange_bootstrap` method directly (not through HTTP) with the same
    token. Unlike section 10's vulnerable-method probe (which deliberately
    places its barrier *inside* verification to expose the old race), this
    barrier sits before the call -- the correct method-wide lock must still
    let exactly one caller mint a session."""
    from rush.dashboard.auth import DashboardAuth

    auth = DashboardAuth()
    token = auth.issue_bootstrap()
    original_verify = auth.verify_bootstrap

    def _widened_verify(provided: str | None) -> bool:
        # Controlled bounded delay after successful verification (S11 point
        # 3): widens the old unlocked race deterministically. The fixed
        # `exchange_bootstrap` never calls this public method internally
        # (it uses a lock-held private verifier instead), so this delay has
        # no effect on the fixed code path -- it only matters for proving
        # the old, unlocked implementation actually raced.
        valid = original_verify(provided)
        time.sleep(0.05)
        return valid

    auth.verify_bootstrap = _widened_verify

    barrier = threading.Barrier(2)
    results: list[object] = []
    results_lock = threading.Lock()

    def _call() -> None:
        barrier.wait(timeout=5)
        result = auth.exchange_bootstrap(token)
        with results_lock:
            results.append(result)

    threads = [threading.Thread(target=_call) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=6)
    assert sum(result is not None for result in results) == 1
    assert len(auth._sessions) == 1


def test_http_concurrency_and_expired_token_tests_still_pass_after_the_lock_is_added() -> (
    None
):
    """S11 point 2: adding `DashboardAuth`'s owning lock must not regress the
    existing HTTP-level concurrent-exchange behavior or expired-token
    rejection."""
    project_a = _load_fixture("project_a.json")
    server, ctx, token = create_dashboard_server({"project-a": project_a})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        results: list[int] = []
        results_lock = threading.Lock()

        def _exchange() -> None:
            resp = _post(
                f"{base_url}/api/session",
                headers={"Authorization": f"Bearer {token}"},
            )
            with results_lock:
                results.append(resp.status)

        threads = [threading.Thread(target=_exchange) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=6)
        assert results.count(200) == 1
        assert results.count(401) == 4

        expired = _post(
            f"{base_url}/api/session",
            headers={"Authorization": "Bearer not-the-real-token"},
        )
        assert expired.status == 401
    finally:
        server.shutdown()
        server.server_close()


def test_bootstrap_token_value_is_redacted_from_finding_content_via_digest_match() -> (
    None
):
    """S12: a still-live (unused) bootstrap token has no stored plaintext to
    exact-match against globally -- it can only be redacted by hashing this
    request's own presented candidate and checking it against the live
    verifier snapshot."""
    project_a = _load_fixture("project_a.json")
    server, ctx, token = create_dashboard_server({"project-a": project_a})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        # Auth needs a real session cookie; the bootstrap token under test
        # must stay unused so only its digest is stored, so mint a second,
        # still-live one rather than reusing the one `_bootstrap_session`
        # consumes for the cookie.
        cookie, _csrf = _bootstrap_session(base_url, token)
        live_token = ctx.auth.issue_bootstrap()
        with patch(
            "rush.dashboard.server._build_memory_section",
            side_effect=RuntimeError(f"boom {live_token} leaked"),
        ):
            resp = _get(
                f"{base_url}/api/projects/project-a/snapshot?section=memory",
                headers={"Cookie": cookie, "Authorization": f"Bearer {live_token}"},
            )
        assert resp.status == 500
        body_text = resp.read().decode()
        assert live_token not in body_text
        assert "[REDACTED]" in body_text
    finally:
        server.shutdown()
        server.server_close()


def test_session_cookie_value_is_redacted_from_finding_content_via_digest_match() -> (
    None
):
    """S12: same as the bootstrap-token case, for the session cookie secret
    -- only its digest is stored, so redaction depends on hash-matching this
    request's own presented cookie value."""
    project_a = _load_fixture("project_a.json")
    server, ctx, token = create_dashboard_server({"project-a": project_a})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        cookie, _csrf = _bootstrap_session(base_url, token)
        cookie_value = cookie.split("=", 1)[1]

        with patch(
            "rush.dashboard.server._build_memory_section",
            side_effect=RuntimeError(f"boom {cookie_value} leaked"),
        ):
            resp = _get(
                f"{base_url}/api/projects/project-a/snapshot?section=memory",
                headers={"Cookie": cookie},
            )
        assert resp.status == 500
        body_text = resp.read().decode()
        assert cookie_value not in body_text
        assert "[REDACTED]" in body_text
    finally:
        server.shutdown()
        server.server_close()


def test_csrf_value_redaction_still_works_after_digest_matching_is_added() -> None:
    """S12 regression guard: the pre-existing plaintext CSRF redaction path
    (control capability + live CSRF tokens, exact-match) must keep working
    unchanged once bootstrap/cookie hash-matching is added alongside it."""
    project_a = _load_fixture("project_a.json")
    server, ctx, token = create_dashboard_server({"project-a": project_a})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        cookie, csrf = _bootstrap_session(base_url, token)

        with patch(
            "rush.dashboard.server._build_memory_section",
            side_effect=RuntimeError(f"boom {csrf} leaked"),
        ):
            resp = _get(
                f"{base_url}/api/projects/project-a/snapshot?section=memory",
                headers={"Cookie": cookie},
            )
        assert resp.status == 500
        body_text = resp.read().decode()
        assert csrf not in body_text
        assert "[REDACTED]" in body_text
    finally:
        server.shutdown()
        server.server_close()


def test_active_session_churn_during_serialization_does_not_leak_or_crash() -> None:
    """S12 point 4: minting/expiring sessions concurrently with a response's
    own redaction pass must not crash (lock-protected snapshot) and must
    never leak an unrelated session's CSRF token into this request's own
    error body."""
    project_a = _load_fixture("project_a.json")
    server, ctx, token = create_dashboard_server({"project-a": project_a})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        cookie, csrf = _bootstrap_session(base_url, token)
        stop = threading.Event()

        def _churn() -> None:
            while not stop.is_set():
                churn_token = ctx.auth.issue_bootstrap()
                ctx.auth.exchange_bootstrap(churn_token)

        churner = threading.Thread(target=_churn, daemon=True)
        churner.start()
        try:
            with patch(
                "rush.dashboard.server._build_memory_section",
                side_effect=RuntimeError(f"boom {csrf} leaked"),
            ):
                for _ in range(20):
                    resp = _get(
                        f"{base_url}/api/projects/project-a/snapshot?section=memory",
                        headers={"Cookie": cookie},
                    )
                    assert resp.status == 500
                    body_text = resp.read().decode()
                    assert csrf not in body_text
                    assert "[REDACTED]" in body_text
        finally:
            stop.set()
            churner.join(timeout=5)
    finally:
        server.shutdown()
        server.server_close()


def test_ordinary_text_resembling_a_token_format_is_not_falsely_redacted() -> None:
    """S12 point 2: a caller-supplied value that merely looks token-shaped
    but does not hash-match any currently-live secret must never be
    blanket-replaced -- only a cryptographically confirmed live secret is
    redacted."""
    project_a = _load_fixture("project_a.json")
    server, ctx, token = create_dashboard_server({"project-a": project_a})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        cookie, _csrf = _bootstrap_session(base_url, token)
        fake_looking_token = secrets.token_urlsafe(32)

        with patch(
            "rush.dashboard.server._build_memory_section",
            side_effect=RuntimeError(f"boom {fake_looking_token} not-a-real-secret"),
        ):
            resp = _get(
                f"{base_url}/api/projects/project-a/snapshot?section=memory",
                headers={
                    "Cookie": cookie,
                    "Authorization": f"Bearer {fake_looking_token}",
                },
            )
        assert resp.status == 500
        body_text = resp.read().decode()
        assert fake_looking_token in body_text
    finally:
        server.shutdown()
        server.server_close()


def test_referrer_policy_header_present_on_js_response() -> None:
    """S13: JS responses previously omitted Referrer-Policy."""
    project_a = _load_fixture("project_a.json")
    server, ctx, _token = create_dashboard_server({"project-a": project_a})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        resp = _get(f"{base_url}/assets/bootstrap.js")
        assert resp.status == 200
        assert resp.headers.get("Referrer-Policy") == "no-referrer"
        assert resp.headers.get("Content-Security-Policy") is not None
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    finally:
        server.shutdown()
        server.server_close()


def test_referrer_policy_header_present_on_css_response() -> None:
    """S13: CSS responses previously omitted Referrer-Policy."""
    project_a = _load_fixture("project_a.json")
    server, ctx, _token = create_dashboard_server({"project-a": project_a})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        resp = _get(f"{base_url}/assets/dashboard.css")
        assert resp.status == 200
        assert resp.headers.get("Referrer-Policy") == "no-referrer"
        assert resp.headers.get("Content-Security-Policy") is not None
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    finally:
        server.shutdown()
        server.server_close()


def test_pre_thread_503_response_carries_the_same_security_headers_as_normal_responses() -> (
    None
):
    """S13: the semaphore-rejection 503, built before any handler exists,
    previously carried no security headers at all."""
    project_a = _load_fixture("project_a.json")
    server, ctx, _token = create_dashboard_server({"project-a": project_a})
    _serve(server)
    slow_sockets: list[socket.socket] = []
    try:
        host, port = ctx.bound_host, ctx.bound_port
        base_url = ctx.launch_origin
        for _ in range(8):
            sock = socket.create_connection((host, port), timeout=5)
            with suppress(OSError):
                sock.sendall(
                    f"GET /api/health HTTP/1.1\r\nHost: {host}:{port}\r\nX-Hold: ".encode()
                )
            slow_sockets.append(sock)
        time.sleep(0.3)
        resp = _get(f"{base_url}/api/health")
        assert resp.status == 503
        assert resp.headers.get("Retry-After") == "1"
        assert resp.headers.get("Content-Security-Policy") is not None
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("Referrer-Policy") == "no-referrer"
        assert resp.headers.get("Cache-Control") == "no-store"
    finally:
        for sock in slow_sockets:
            with suppress(OSError):
                sock.close()
        server.shutdown()
        server.server_close()


def test_pre_thread_503_service_resumes_after_a_slot_is_released() -> None:
    """S13: releasing one held slot must let the next request through even
    while the semaphore-rejection path was otherwise engaged."""
    project_a = _load_fixture("project_a.json")
    server, ctx, _token = create_dashboard_server({"project-a": project_a})
    _serve(server)
    slow_sockets: list[socket.socket] = []
    try:
        host, port = ctx.bound_host, ctx.bound_port
        base_url = ctx.launch_origin
        for _ in range(8):
            sock = socket.create_connection((host, port), timeout=5)
            with suppress(OSError):
                sock.sendall(
                    f"GET /api/health HTTP/1.1\r\nHost: {host}:{port}\r\nX-Hold: ".encode()
                )
            slow_sockets.append(sock)
        time.sleep(0.3)
        rejected = _get(f"{base_url}/api/health")
        assert rejected.status == 503

        slow_sockets.pop().close()
        time.sleep(0.3)
        resumed = _get(f"{base_url}/api/health")
        assert resumed.status == 200
    finally:
        for sock in slow_sockets:
            with suppress(OSError):
                sock.close()
        server.shutdown()
        server.server_close()


def test_handle_action_rejects_missing_schema_version() -> None:
    """S14: an omitted schema_version was previously silently accepted."""
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
        resp = _post(
            f"{base_url}/api/projects/project-a/actions",
            headers=headers,
            body=json.dumps({"operation": "noop", "request_id": "no-schema"}).encode(),
        )
        assert resp.status == 400
        body = json.loads(resp.read())
        assert body["error"]["code"] == "malformed_request"
    finally:
        server.shutdown()
        server.server_close()


def test_handle_action_rejects_null_string_bool_schema_version() -> None:
    """S14: null, string, and bool schema_version values must all be
    rejected as malformed -- booleans must not pass Python's `int` subtype
    check as if they were 1/0."""
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
        for bad_value in (None, "1", True):
            resp = _post(
                f"{base_url}/api/projects/project-a/actions",
                headers=headers,
                body=json.dumps(
                    {
                        "schema_version": bad_value,
                        "operation": "noop",
                        "request_id": f"bad-{bad_value}",
                    }
                ).encode(),
            )
            assert resp.status == 400, bad_value
            body = json.loads(resp.read())
            assert body["error"]["code"] == "malformed_request", bad_value
    finally:
        server.shutdown()
        server.server_close()


def test_handle_action_accepts_explicit_integer_1_schema_version() -> None:
    """S14: the one supported schema_version value must still retain valid
    behavior after the stricter check is added."""
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
        resp = _post(
            f"{base_url}/api/projects/project-a/actions",
            headers=headers,
            body=json.dumps(
                {"schema_version": 1, "operation": "noop", "request_id": "ok-schema"}
            ).encode(),
        )
        assert resp.status == 202
    finally:
        server.shutdown()
        server.server_close()


def test_handle_control_check_suite_rejects_missing_schema_version() -> None:
    """S14: the control-channel CHECK_SUITE path had the same missing-field
    acceptance bug as the browser action route."""
    project_a = _load_fixture("project_a.json")
    server, ctx, _token = create_dashboard_server({"project-a": project_a})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        resp = _post(
            f"{base_url}/api/control/check-suite",
            headers={
                "X-Rush-Control": ctx.auth.control_capability,
                "Content-Type": "application/json",
            },
            body=json.dumps({}).encode(),
        )
        assert resp.status == 400
        body = json.loads(resp.read())
        assert body["error"]["code"] == "malformed_request"
    finally:
        server.shutdown()
        server.server_close()


def test_handle_control_check_suite_accepts_explicit_integer_1_schema_version() -> None:
    """S14: an explicit, supported schema_version must pass the schema gate
    and reach the next (project_id) validation step, not be rejected as a
    schema problem."""
    project_a = _load_fixture("project_a.json")
    server, ctx, _token = create_dashboard_server({"project-a": project_a})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        resp = _post(
            f"{base_url}/api/control/check-suite",
            headers={
                "X-Rush-Control": ctx.auth.control_capability,
                "Content-Type": "application/json",
            },
            body=json.dumps({"schema_version": 1}).encode(),
        )
        assert resp.status == 400
        body = json.loads(resp.read())
        assert body["error"]["code"] == "malformed_request"
        assert "project_id" in body["error"]["message"]
    finally:
        server.shutdown()
        server.server_close()


def test_concurrent_bootstrap_exchange_mints_exactly_one_session() -> None:
    project_a = _load_fixture("project_a.json")
    server, ctx, token = create_dashboard_server({"project-a": project_a})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        results: list[int] = []
        results_lock = threading.Lock()

        def _attempt() -> None:
            resp = _post(
                f"{base_url}/api/session",
                headers={"Authorization": f"Bearer {token}"},
            )
            with results_lock:
                results.append(resp.status)

        attempt_threads = [threading.Thread(target=_attempt) for _ in range(2)]
        for t in attempt_threads:
            t.start()
        for t in attempt_threads:
            t.join(timeout=5)

        assert sorted(results) == [200, 401]
        assert len(ctx.auth._sessions) == 1
    finally:
        server.shutdown()
        server.server_close()


def test_reconnect_selects_newest_confirmed_live_descriptor_not_newest_by_mtime(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr("rush.setup.provision.default_data_root", lambda: tmp_path)
    from rush import cli as rush_cli

    project_a = _load_fixture("project_a.json")
    live_server, live_ctx, _live_token = create_dashboard_server(
        {"project-a": project_a}
    )
    _serve(live_server)
    try:
        live_descriptor_path = rush_cli._write_dashboard_descriptor(live_ctx)

        # A newer-mtime descriptor for a since-replaced process still
        # listening on the same address -- reachable, but PID/start_nonce
        # no longer match, so it must be recognized as stale and removed.
        stale_path = rush_cli._dashboard_descriptor_path("stale-server")
        stale_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "pid": 999999,
                    "start_nonce": "not-the-real-nonce",
                    "bound_host": live_ctx.bound_host,
                    "bound_port": live_ctx.bound_port,
                    "control_capability": live_ctx.auth.control_capability,
                }
            ),
            encoding="utf-8",
        )
        os.utime(stale_path, None)

        newest = rush_cli._newest_dashboard_descriptor(None)
        assert newest == live_descriptor_path
        assert not stale_path.exists()
    finally:
        live_server.shutdown()
        live_server.server_close()


@pytest.mark.skipif(os.name != "nt", reason="Windows-only data directory ACL check")
def test_windows_data_dir_acl_checked_before_persisting_capability(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr("rush.setup.provision.default_data_root", lambda: tmp_path)
    from rush import cli as rush_cli

    project_a = _load_fixture("project_a.json")
    server, ctx, _token = create_dashboard_server({"project-a": project_a})
    _serve(server)
    try:
        with (
            patch("rush.cli._check_windows_data_dir_acl", return_value=False),
            pytest.raises(Exception),  # noqa: B017 -- click.ClickException
        ):
            rush_cli._write_dashboard_descriptor(ctx)
    finally:
        server.shutdown()
        server.server_close()


def test_memory_edit_archive_delete_apply_true_persists_ledger_entry_apply_false_does_not(
    tmp_path, monkeypatch
) -> None:
    """P69-01.2l real end-to-end proof: a preview (`apply=False`) call to
    memory_edit/memory_archive/memory_delete writes no durable ledger row;
    an applied (`apply=True`) call does."""
    data_root = tmp_path / "data"
    monkeypatch.setattr("rush.setup.provision.default_data_root", lambda: data_root)
    # rush.workflows.projects imports default_data_root at module scope (not
    # lazily like MutationLedger's own __init__ does), so resolve_project()
    # (called with no explicit data_root by the dashboard's memory dispatch
    # functions) needs its own module-local reference patched too.
    monkeypatch.setattr("rush.workflows.projects.default_data_root", lambda: data_root)

    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    record = register_project(project_dir, data_root=data_root)
    project_id = record.project_id

    owner = OwnerScope("project", project_id)
    store = TypedArtifactStore(project_dir)
    for artifact_id in ("edit-target", "archive-target", "delete-target"):
        store.write(
            MemoryArtifact(
                id=artifact_id,
                family="memory",
                subject="domain_knowledge",
                trust_tier="DERIVED",
                content={"note": artifact_id},
                source="test",
                created_at=time.time(),
                owner_scope=owner,
            )
        )

    snapshot = {
        "schema_version": 1,
        "project_id": project_id,
        "source_identity": project_id,
        "root": str(project_dir),
        "files": [],
        "findings": [],
        "memories": [],
        "agents": [],
    }
    server, ctx, token = create_dashboard_server({project_id: snapshot})
    _serve(server)

    def _ledger_row_count() -> int:
        with sqlite3.connect(
            str(data_root / "dashboard" / "mutation_ledger.db")
        ) as conn:
            return conn.execute("SELECT COUNT(*) FROM mutation_ledger").fetchone()[0]

    try:
        base_url = ctx.launch_origin
        cookie, csrf = _bootstrap_session(base_url, token)
        headers = {
            "Cookie": cookie,
            "X-Rush-CSRF": csrf,
            "Origin": base_url,
            "Content-Type": "application/json",
        }

        cases = [
            (
                "memory_edit",
                "edit-target",
                {
                    "scope": "domain_knowledge",
                    "id": "edit-target",
                    "expected_version": 1,
                    "content": {"note": "edited"},
                    "owner_scope": owner.as_dict(),
                },
            ),
            (
                "memory_archive",
                "archive-target",
                {
                    "scope": "domain_knowledge",
                    "id": "archive-target",
                    "expected_version": 1,
                    "owner_scope": owner.as_dict(),
                },
            ),
            (
                "memory_delete",
                "delete-target",
                {
                    "artifact_ids": ["delete-target"],
                    "expected_revisions": {"delete-target": 1},
                    "scope": "domain_knowledge",
                    "owner_scope": owner.as_dict(),
                },
            ),
        ]

        assert _ledger_row_count() == 0
        for operation, target, base_arguments in cases:
            preview_body = json.dumps(
                {
                    "schema_version": 1,
                    "operation": operation,
                    "request_id": f"req-{target}-preview",
                    "arguments": {**base_arguments, "apply": False},
                }
            ).encode()
            preview_resp = _post(
                f"{base_url}/api/projects/{project_id}/actions",
                headers=headers,
                body=preview_body,
            )
            assert preview_resp.status == 200
        assert _ledger_row_count() == 0

        for operation, target, base_arguments in cases:
            apply_body = json.dumps(
                {
                    "schema_version": 1,
                    "operation": operation,
                    "request_id": f"req-{target}-apply",
                    "arguments": {**base_arguments, "apply": True},
                    "grants": {"cache_write": True},
                }
            ).encode()
            apply_resp = _post(
                f"{base_url}/api/projects/{project_id}/actions",
                headers=headers,
                body=apply_body,
            )
            assert apply_resp.status == 200
            apply_payload = json.loads(apply_resp.read())
            assert apply_payload["data"]["raw"]["data"]["applied"] is True
        assert _ledger_row_count() == 3
    finally:
        server.shutdown()
        server.server_close()


def test_action_exception_returns_structured_error_not_stack_trace() -> None:
    """P69-01.2m exception boundary: any exception `_dispatch_scan_action`
    itself doesn't already convert to a structured error (a raw, unhandled
    exception from deep inside dispatch) still returns the JSON error
    envelope, never a raw exception body/stack trace."""
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
        with patch(
            "rush.dashboard.server._dispatch_provision_plan",
            side_effect=RuntimeError("boom, unexpected internal failure"),
        ):
            resp = _post(
                f"{base_url}/api/projects/project-a/actions",
                headers=headers,
                body=json.dumps(
                    {
                        "schema_version": 1,
                        "operation": "provision_plan",
                        "request_id": "req-boom",
                    }
                ).encode(),
            )
        assert resp.status == 500
        body_text = resp.read().decode()
        body = json.loads(body_text)
        assert body["error"]["code"] == "internal_error"
        assert "Traceback" not in body_text
        assert "RuntimeError" not in body_text
    finally:
        server.shutdown()
        server.server_close()


def test_p69_01_action_rejects_unsupported_argument_key() -> None:
    """P69-01.2m operation-specific argument field allowlist: each action's
    own named argument set, an unknown key rejected outright rather than
    silently dropped (Phase 66 Sec 3.6). P69-02's own
    `test_action_rejects_unsupported_argument_keys` exercises the same
    mechanism again alongside schema_version validation once that packet
    lands; this is P69-01's own minimal coverage of the mechanism itself."""
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
        resp = _post(
            f"{base_url}/api/projects/project-a/actions",
            headers=headers,
            body=json.dumps(
                {
                    "schema_version": 1,
                    "operation": "scan_cancel",
                    "request_id": "req-bad-arg",
                    "arguments": {"run_id": "run-1", "evil_extra_field": "x"},
                }
            ).encode(),
        )
        assert resp.status == 400
        body = json.loads(resp.read())
        assert body["error"]["code"] == "unsupported_argument"
    finally:
        server.shutdown()
        server.server_close()


def test_string_false_grant_value_is_rejected_not_coerced_to_true() -> None:
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
        resp = _post(
            f"{base_url}/api/projects/project-a/actions",
            headers=headers,
            body=json.dumps(
                {
                    "schema_version": 1,
                    "operation": "data_export",
                    "request_id": "req-grant-false",
                    "grants": {"download": "false"},
                }
            ).encode(),
        )
        assert resp.status == 400
        body = json.loads(resp.read())
        assert body["error"]["code"] == "malformed_request"
    finally:
        server.shutdown()
        server.server_close()


def test_string_false_apply_value_is_rejected_not_treated_as_true_both_dashboard_and_memory_tool_sites(
    tmp_path,
) -> None:
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
        resp = _post(
            f"{base_url}/api/projects/project-a/actions",
            headers=headers,
            body=json.dumps(
                {
                    "schema_version": 1,
                    "operation": "memory_edit",
                    "request_id": "req-apply-false",
                    "arguments": {
                        "scope": "domain_knowledge",
                        "id": "fake",
                        "expected_version": 1,
                        "content": {},
                        "apply": "false",
                    },
                }
            ).encode(),
        )
        assert resp.status == 400
        body = json.loads(resp.read())
        assert body["error"]["code"] == "malformed_request"
    finally:
        server.shutdown()
        server.server_close()

    from rush.tools.memory import MemoryTool

    result = MemoryTool().run(
        tmp_path,
        operation="delete",
        request={
            "artifact_ids": ["x"],
            "scope": "domain_knowledge",
            "apply": "false",
        },
    )
    assert result["raw"]["code"] == "E_INPUT"
    assert "boolean" in result["raw"]["data"]["message"]


def test_string_false_user_stated_value_is_rejected_not_treated_as_true() -> None:
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
        resp = _post(
            f"{base_url}/api/projects/project-a/actions",
            headers=headers,
            body=json.dumps(
                {
                    "schema_version": 1,
                    "operation": "memory_promote",
                    "request_id": "req-user-stated-false",
                    "arguments": {
                        "subject": "domain_knowledge",
                        "content": {"note": "x"},
                        "source": "test",
                        "user_stated": "false",
                    },
                    "grants": {"cache_write": True},
                }
            ).encode(),
        )
        assert resp.status == 400
        body = json.loads(resp.read())
        assert body["error"]["code"] == "malformed_request"
    finally:
        server.shutdown()
        server.server_close()


# --- P69-02.2 a/b/c: request validation, replay-vs-identity CAS, and the
# acceptance-vs-execution split for async operations -------------------------


def test_action_rejects_unknown_schema_version() -> None:
    """P69-02.2a: a present-but-wrong `schema_version` is rejected outright
    (an absent one defaults to 1, for every caller that predates this field)."""
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
        resp = _post(
            f"{base_url}/api/projects/project-a/actions",
            headers=headers,
            body=json.dumps(
                {
                    "schema_version": 2,
                    "operation": "noop",
                    "request_id": "req-bad-schema",
                }
            ).encode(),
        )
        assert resp.status == 400
        body = json.loads(resp.read())
        assert body["error"]["code"] == "unsupported_schema_version"
    finally:
        server.shutdown()
        server.server_close()


def test_action_rejects_unsupported_argument_keys() -> None:
    """P69-02.2a: same mechanism as P69-01's own
    `test_p69_01_action_rejects_unsupported_argument_key`, exercised again
    alongside a valid `schema_version` and extended to the top-level `grants`
    allowlist too."""
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
        bad_argument = _post(
            f"{base_url}/api/projects/project-a/actions",
            headers=headers,
            body=json.dumps(
                {
                    "schema_version": 1,
                    "operation": "scan_cancel",
                    "request_id": "req-bad-argument-key",
                    "arguments": {"run_id": "run-1", "not_a_real_field": "x"},
                }
            ).encode(),
        )
        assert bad_argument.status == 400
        assert (
            json.loads(bad_argument.read())["error"]["code"] == "unsupported_argument"
        )

        bad_grant = _post(
            f"{base_url}/api/projects/project-a/actions",
            headers=headers,
            body=json.dumps(
                {
                    "schema_version": 1,
                    "operation": "scan_cancel",
                    "request_id": "req-bad-grant-key",
                    "arguments": {"run_id": "run-1"},
                    "grants": {"not_a_real_grant": True},
                }
            ).encode(),
        )
        assert bad_grant.status == 400
        assert json.loads(bad_grant.read())["error"]["code"] == "unsupported_grant"
    finally:
        server.shutdown()
        server.server_close()


def test_action_rejects_stale_expected_identity() -> None:
    """P69-02.2b: a genuinely new `request_id` carrying an `expected.
    source_identity` that no longer matches the project's current identity
    is rejected with a structured 409 -- checked only once the MutationLedger
    has already confirmed this isn't a cached replay (an identical retry
    never re-validates against current state, per Phase 66 Sec 3.6)."""
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
        record = ctx.projects.get("project-a")
        original_identity = record.source_identity
        # Simulate the project's source having changed since this client's
        # `expected` value was last read. ProjectRecord is frozen (M01) --
        # go through the real publish path instead of direct mutation.
        assert ctx.projects.publish_scan_result(
            "project-a",
            snapshot=record.snapshot,
            source_identity="changed-since-client-read",
            generation=record.scan_generation + 1,
        )

        resp = _post(
            f"{base_url}/api/projects/project-a/actions",
            headers=headers,
            body=json.dumps(
                {
                    "schema_version": 1,
                    "operation": "scan_cancel",
                    "request_id": "req-stale-identity",
                    "arguments": {"run_id": "run-1"},
                    "expected": {"source_identity": original_identity},
                }
            ).encode(),
        )
        assert resp.status == 409
        body = json.loads(resp.read())
        assert body["error"]["code"] == "stale_expected_identity"

        # A retry of the *same* request_id/body is a cached replay -- it must
        # never be re-validated against the (still-changed) current state.
        replay = _post(
            f"{base_url}/api/projects/project-a/actions",
            headers=headers,
            body=json.dumps(
                {
                    "schema_version": 1,
                    "operation": "scan_cancel",
                    "request_id": "req-stale-identity",
                    "arguments": {"run_id": "run-1"},
                    "expected": {"source_identity": original_identity},
                }
            ).encode(),
        )
        assert replay.status == 409
        assert json.loads(replay.read()) == body
    finally:
        server.shutdown()
        server.server_close()


def test_expected_identity_changing_while_accepted_work_is_queued_produces_terminal_conflict_not_silent_apply(
    tmp_path,
) -> None:
    """P69-02.2c: acceptance-vs-execution split. The identity comparison
    that gates a queued async effect (`scan_start`/`scan_resume`/`rescan`)
    must be re-run a second time, immediately before the real effect
    executes, not only once at HTTP-acceptance time -- closing the window
    between "202 accepted" and the background thread actually running."""
    from rush.dashboard.server import (
        _check_expected_identity,
        _revalidate_expected_at_execution,
    )
    from rush.dashboard.state import MutationLedger, ProjectRegistry

    registry = ProjectRegistry({"p": {"source_identity": "original"}})
    ledger = MutationLedger(db_path=tmp_path / "ledger.db")

    class _FakeCtx:
        projects = registry
        mutations = ledger

    ctx = _FakeCtx()

    # Acceptance time: still matches -- safe to queue the work.
    accepted_record = ctx.projects.get("p")
    assert (
        _check_expected_identity(accepted_record, {"source_identity": "original"})
        is None
    )

    # The project's real source_identity changes underneath the now-queued
    # work before it actually executes. ProjectRecord is frozen (M01) -- go
    # through the real publish path instead of direct mutation.
    assert ctx.projects.publish_scan_result(
        "p",
        snapshot=accepted_record.snapshot,
        source_identity="changed",
        generation=accepted_record.scan_generation + 1,
    )

    reservation = ledger.reserve("p", "req-1", "hash-1", operation_type="scan_start")
    conflict = _revalidate_expected_at_execution(
        ctx, "p", {"source_identity": "original"}
    )
    assert conflict is not None
    assert conflict["code"] == "stale_expected_identity"

    # P69-02.2g: the revalidation never writes the transition itself -- the
    # terminal write and the admission-row release are one transaction, owned
    # by the server's outcome queue and reached through the worker's `finally`.
    ctx.outcomes = PendingOutcomeQueue(ledger, retry_interval=60.0)
    ctx.mutations.admit(
        "p",
        execution_identity="scan_start:plan-1",
        slot_id=reservation.operation_id,
        operation_id=reservation.operation_id,
        run_id="run-1",
        plan_id="plan-1",
        owner_instance_id="owner-1",
    )
    _run_supervised(
        ctx,
        reservation.operation_id,
        reservation.operation_id,
        lambda: _revalidate_expected_at_execution(
            ctx, "p", {"source_identity": "original"}
        ),
    )

    status = ledger.get_operation_status(reservation.operation_id)
    assert status is not None
    assert status["status"] == "terminal"
    assert status["payload"]["code"] == "stale_expected_identity"
    assert ledger.admission_for_project("p") is None


def test_add_project_returns_200_for_existing_identity_not_201(tmp_path) -> None:
    """P69-02.2n: `add`'s identity (`register_project`'s canonical root) is
    idempotent -- re-adding an already-registered identity reports 200
    (nothing new happened), never 201."""
    repo = tmp_path / "repo-a"
    repo.mkdir()
    server, ctx, token = create_dashboard_server({})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        cookie, csrf = _bootstrap_session(base_url, token)
        headers = {
            "Cookie": cookie,
            "X-Rush-CSRF": csrf,
            "Content-Type": "application/json",
            "Origin": base_url,
        }
        grants = {"cache_write": True, "artifact_write": True}

        first = _post(
            f"{base_url}/api/projects",
            headers=headers,
            body=json.dumps(
                {
                    "operation": "add",
                    "path": str(repo),
                    "grants": grants,
                    "request_id": "req-add-1",
                }
            ).encode(),
        )
        assert first.status == 201
        project_id = json.loads(first.read())["data"]["project_id"]

        second = _post(
            f"{base_url}/api/projects",
            headers=headers,
            body=json.dumps(
                {
                    "operation": "add",
                    "path": str(repo),
                    "grants": grants,
                    "request_id": "req-add-2",
                }
            ).encode(),
        )
        assert second.status == 200
        assert json.loads(second.read())["data"]["project_id"] == project_id
    finally:
        server.shutdown()
        server.server_close()


def test_toolresult_raw_unwrapped_not_skipped_treated_as_success(tmp_path) -> None:
    """P69-02.2n: the shared HTTP-adapter-boundary mapping from a
    `ToolResult` to an HTTP response -- `raw`/`status`/`findings`/`metadata`
    stay exactly as `MemoryTool().run()` returned them, but a `skipped`
    `ToolResult` is never reported as an HTTP success."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    record = register_project(project_dir)
    project_id = record.project_id

    snapshot = {
        "schema_version": 1,
        "project_id": project_id,
        "source_identity": project_id,
        "root": str(project_dir),
        "files": [],
        "findings": [],
        "memories": [],
        "agents": [],
    }
    server, ctx, token = create_dashboard_server({project_id: snapshot})
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
        arguments = {
            "scope": "domain_knowledge",
            "id": "x",
            "expected_version": 1,
            "content": {},
            "apply": False,
            "owner_scope": {"kind": "project", "id": project_id},
        }

        ok_result = {
            "status": "ok",
            "findings": [],
            "raw": {"code": "OK", "data": {"applied": False}},
            "metadata": {},
        }
        with patch("rush.dashboard.server.MemoryTool.run", return_value=ok_result):
            resp = _post(
                f"{base_url}/api/projects/{project_id}/actions",
                headers=headers,
                body=json.dumps(
                    {
                        "schema_version": 1,
                        "operation": "memory_edit",
                        "request_id": "req-tool-ok",
                        "arguments": arguments,
                    }
                ).encode(),
            )
        assert resp.status == 200
        body = json.loads(resp.read())
        assert body["data"]["raw"] == {"code": "OK", "data": {"applied": False}}

        skipped_result = {
            "status": "skipped",
            "findings": [],
            "raw": None,
            "metadata": {},
        }
        with patch("rush.dashboard.server.MemoryTool.run", return_value=skipped_result):
            resp2 = _post(
                f"{base_url}/api/projects/{project_id}/actions",
                headers=headers,
                body=json.dumps(
                    {
                        "schema_version": 1,
                        "operation": "memory_edit",
                        "request_id": "req-tool-skipped",
                        "arguments": arguments,
                    }
                ).encode(),
            )
        assert resp2.status != 200
        assert resp2.status == 503
    finally:
        server.shutdown()
        server.server_close()


def test_admission_matches_on_execution_identity_not_project_alone(tmp_path) -> None:
    """P69-02.2f: the admission decision is the durable table's own
    `UNIQUE(project_id)` insert, not `ScanRunTracker`'s in-memory
    `thread.is_alive()` check."""
    ledger = MutationLedger(db_path=tmp_path / "admission.db")

    first = ledger.admit(
        "project-a",
        execution_identity="scan_start:plan-1",
        slot_id="op-1",
        operation_id="op-1",
        run_id="run-1",
        plan_id="plan-1",
        owner_instance_id="owner-1",
    )
    assert first.started is True

    # Same project, same execution identity: attaches to the already-admitted
    # job -- never a second admission row, never a second thread.
    second = ledger.admit(
        "project-a",
        execution_identity="scan_start:plan-1",
        slot_id="op-2",
        operation_id="op-2",
        run_id="run-2",
        plan_id="plan-1",
        owner_instance_id="owner-1",
    )
    assert second.started is False
    assert second.attached is True
    assert second.conflict is False
    assert second.run_id == "run-1"
    assert second.plan_id == "plan-1"
    assert ledger.resolve_attachment("op-2") == "op-1"


def test_two_different_execution_identities_in_the_same_project_never_both_insert_the_second_gets_structured_busy_conflict(
    tmp_path,
) -> None:
    ledger = MutationLedger(db_path=tmp_path / "admission.db")
    ledger.admit(
        "project-a",
        execution_identity="scan_start:plan-1",
        slot_id="op-1",
        operation_id="op-1",
        run_id="run-1",
        plan_id="plan-1",
        owner_instance_id="owner-1",
    )

    losing = ledger.admit(
        "project-a",
        execution_identity="scan_start:plan-2",
        slot_id="op-2",
        operation_id="op-2",
        run_id="run-2",
        plan_id="plan-2",
        owner_instance_id="owner-1",
    )
    assert losing.conflict is True
    assert losing.started is False
    assert losing.attached is False
    # The conflict response names the *active* row's identity, never the
    # rejected request's own.
    assert losing.execution_identity == "scan_start:plan-1"
    assert losing.run_id == "run-1"
    # No attachment record was written for a rejected request.
    assert ledger.resolve_attachment("op-2") == "op-2"


def test_resume_and_rescan_execution_identities_never_collide_even_with_identical_run_id_and_attempt_id_due_to_operation_type_prefix(
    tmp_path,
) -> None:
    ledger = MutationLedger(db_path=tmp_path / "admission.db")
    ledger.admit(
        "project-a",
        execution_identity="scan_resume:run-7",
        slot_id="op-1",
        operation_id="op-1",
        run_id="run-7",
        owner_instance_id="owner-1",
    )
    collision = ledger.admit(
        "project-a",
        execution_identity="rescan:run-7",
        slot_id="op-2",
        operation_id="op-2",
        run_id="run-7",
        owner_instance_id="owner-1",
    )
    assert collision.conflict is True
    assert collision.attached is False


def test_a_new_request_sharing_an_identity_with_a_previously_completed_not_currently_active_job_executes_independently_not_attached_to_stale_work(
    tmp_path,
) -> None:
    ledger = MutationLedger(db_path=tmp_path / "admission.db")
    ledger.admit(
        "project-a",
        execution_identity="scan_start:plan-1",
        slot_id="op-1",
        operation_id="op-1",
        run_id="run-1",
        plan_id="plan-1",
        owner_instance_id="owner-1",
    )
    ledger.terminalize_and_release(
        "op-1", operation_id="op-1", payload={"status": "success"}
    )

    fresh = ledger.admit(
        "project-a",
        execution_identity="scan_start:plan-1",
        slot_id="op-2",
        operation_id="op-2",
        run_id="run-2",
        plan_id="plan-1",
        owner_instance_id="owner-1",
    )
    assert fresh.started is True
    assert fresh.attached is False
    assert fresh.run_id == "run-2"
    assert ledger.resolve_attachment("op-2") == "op-2"


def test_a_conflicting_requests_attachment_write_that_races_the_winners_terminalization_checks_the_admission_row_not_merely_the_durable_operation_records_existence_and_falls_through_to_fresh_admission_if_the_row_is_already_gone(
    tmp_path,
) -> None:
    """The winner's durable ledger row outlives its admission row by design.
    An attach decision must validate the *admission row*, so a request that
    arrives after terminalization starts fresh instead of attaching to work
    that is already over."""
    ledger = MutationLedger(db_path=tmp_path / "admission.db")
    _seed_operation(ledger, "op-1")
    ledger.admit(
        "project-a",
        execution_identity="scan_start:plan-1",
        slot_id="op-1",
        operation_id="op-1",
        run_id="run-1",
        plan_id="plan-1",
        owner_instance_id="owner-1",
    )
    ledger.terminalize_and_release(
        "op-1", operation_id="op-1", payload={"status": "success"}
    )
    # The durable operation record still exists ...
    assert ledger.get_operation_status("op-1") is not None
    # ... but the admission row is gone, so the late request is admitted fresh.
    late = ledger.admit(
        "project-a",
        execution_identity="scan_start:plan-1",
        slot_id="op-late",
        operation_id="op-late",
        run_id="run-late",
        plan_id="plan-1",
        owner_instance_id="owner-1",
    )
    assert late.started is True
    assert ledger.resolve_attachment("op-late") == "op-late"


def test_an_attachment_record_points_at_the_durable_operation_id_not_the_admission_row_and_survives_the_admission_row_being_freed_for_the_next_job(
    tmp_path,
) -> None:
    ledger = MutationLedger(db_path=tmp_path / "admission.db")
    _seed_operation(ledger, "op-1")
    ledger.admit(
        "project-a",
        execution_identity="scan_start:plan-1",
        slot_id="op-1",
        operation_id="op-1",
        run_id="run-1",
        plan_id="plan-1",
        owner_instance_id="owner-1",
    )
    ledger.admit(
        "project-a",
        execution_identity="scan_start:plan-1",
        slot_id="op-2",
        operation_id="op-2",
        run_id="run-2",
        plan_id="plan-1",
        owner_instance_id="owner-1",
    )
    ledger.terminalize_and_release(
        "op-1", operation_id="op-1", payload={"status": "success", "run_id": "run-1"}
    )
    # Slot freed, next job admitted -- the attachment still resolves to the
    # operation that actually did the work.
    ledger.admit(
        "project-a",
        execution_identity="scan_start:plan-9",
        slot_id="op-3",
        operation_id="op-3",
        run_id="run-3",
        plan_id="plan-9",
        owner_instance_id="owner-1",
    )
    assert ledger.resolve_attachment("op-2") == "op-1"
    assert ledger.get_operation_status("op-2") is None
    assert ledger.get_operation_status(ledger.resolve_attachment("op-2")) is not None


def test_a_thread_never_launches_and_no_202_is_sent_before_its_own_admission_transaction_has_actually_committed(
    tmp_path,
) -> None:
    """The admission boundary is transaction *commit*, not an `INSERT` that
    returned without error: a separate connection must already see the row
    by the time the worker thread runs."""
    ledger = MutationLedger(db_path=tmp_path / "admission.db")
    seen: list[bool] = []
    ready = threading.Event()

    def _worker() -> None:
        # A genuinely separate connection: only a committed row is visible.
        with sqlite3.connect(str(tmp_path / "admission.db")) as probe:
            row = probe.execute(
                "SELECT slot_id FROM scan_admission WHERE project_id = ?",
                ("project-a",),
            ).fetchone()
        seen.append(row is not None)
        ready.set()

    thread = threading.Thread(target=_worker, daemon=True)
    admission = ledger.admit(
        "project-a",
        execution_identity="scan_start:plan-1",
        slot_id="op-1",
        operation_id="op-1",
        run_id="run-1",
        plan_id="plan-1",
        owner_instance_id="owner-1",
    )
    assert admission.started is True
    thread.start()
    ready.wait(5)
    thread.join(timeout=5)
    assert seen == [True]


def test_a_completed_operations_admission_row_is_deleted_in_the_same_transaction_as_its_terminal_status_write_freeing_the_project_slot(
    tmp_path,
) -> None:
    ledger = MutationLedger(db_path=tmp_path / "admission.db")
    _seed_operation(ledger, "op-1")
    ledger.admit(
        "project-a",
        execution_identity="scan_start:plan-1",
        slot_id="op-1",
        operation_id="op-1",
        run_id="run-1",
        plan_id="plan-1",
        owner_instance_id="owner-1",
    )
    statements = _record_sql(ledger)

    ledger.terminalize_and_release(
        "op-1", operation_id="op-1", payload={"status": "success"}
    )

    assert ledger.admission_for_project("project-a") is None
    assert ledger.get_operation_status("op-1")["status"] == "terminal"
    # One transaction: BEGIN IMMEDIATE ... UPDATE ... DELETE ... COMMIT, with
    # no COMMIT between the terminal write and the admission-row delete.
    joined = " | ".join(statements)
    assert "BEGIN IMMEDIATE" in joined
    body = joined.split("BEGIN IMMEDIATE", 1)[1]
    assert "UPDATE mutation_ledger" in body
    assert "DELETE FROM scan_admission" in body
    assert "COMMIT" not in body.split("DELETE FROM scan_admission", 1)[0]


def test_a_worker_that_raises_still_records_a_terminal_error_status_and_releases_its_admission_row_via_the_finally_path_not_suppress_exception(
    tmp_path,
) -> None:
    ctx = _admission_ctx(tmp_path)
    _seed_operation(ctx.mutations, "op-1")
    ctx.mutations.admit(
        "project-a",
        execution_identity="scan_start:plan-1",
        slot_id="op-1",
        operation_id="op-1",
        run_id="run-1",
        plan_id="plan-1",
        owner_instance_id=ctx.owner_instance_id,
    )

    def _body() -> dict:
        raise RuntimeError("engine blew up")

    _run_supervised(ctx, "op-1", "op-1", _body)

    status = ctx.mutations.get_operation_status("op-1")
    assert status["status"] == "terminal"
    assert status["payload"]["status"] == "error"
    assert "engine blew up" in status["payload"]["message"]
    assert ctx.mutations.admission_for_project("project-a") is None


def test_system_exit_inside_a_worker_still_terminalizes_via_the_idempotent_transaction_not_an_unconditional_bare_finally_release(
    tmp_path,
) -> None:
    """`SystemExit` bypasses `except Exception` but still reaches `finally`.
    A bare `finally: <release>` would free the slot with no terminal state
    recorded at all; the pre-seeded outcome must be terminalized instead."""
    ctx = _admission_ctx(tmp_path)
    _seed_operation(ctx.mutations, "op-1")
    ctx.mutations.admit(
        "project-a",
        execution_identity="scan_start:plan-1",
        slot_id="op-1",
        operation_id="op-1",
        run_id="run-1",
        plan_id="plan-1",
        owner_instance_id=ctx.owner_instance_id,
    )

    def _body() -> dict:
        raise SystemExit(1)

    with pytest.raises(SystemExit):
        _run_supervised(ctx, "op-1", "op-1", _body)

    status = ctx.mutations.get_operation_status("op-1")
    assert status["status"] == "terminal"
    assert status["payload"]["status"] == "error"
    assert ctx.mutations.admission_for_project("project-a") is None


def test_a_failed_terminalization_write_leaves_the_admission_row_intact_for_recovery_to_retry_never_independently_deleted(
    tmp_path,
) -> None:
    ledger = MutationLedger(db_path=tmp_path / "admission.db")
    _seed_operation(ledger, "op-1")
    ledger.admit(
        "project-a",
        execution_identity="scan_start:plan-1",
        slot_id="op-1",
        operation_id="op-1",
        run_id="run-1",
        plan_id="plan-1",
        owner_instance_id="owner-1",
    )
    _fail_on(ledger, "UPDATE mutation_ledger")
    with pytest.raises(sqlite3.OperationalError):
        ledger.terminalize_and_release(
            "op-1", operation_id="op-1", payload={"status": "success"}
        )
    row = ledger.admission_for_project("project-a")
    assert row is not None
    assert row["owner_instance_id"] == "owner-1"


def test_a_transient_terminalization_write_failure_durably_registers_a_pending_outcome_before_the_attempt_so_recovery_can_retry_it_while_the_owner_stays_alive(
    tmp_path,
) -> None:
    ledger = MutationLedger(db_path=tmp_path / "admission.db")
    _seed_operation(ledger, "op-1")
    ledger.admit(
        "project-a",
        execution_identity="scan_start:plan-1",
        slot_id="op-1",
        operation_id="op-1",
        run_id="run-1",
        plan_id="plan-1",
        owner_instance_id="owner-1",
    )
    queue = PendingOutcomeQueue(
        ledger, owner_instance_id="owner-1", retry_interval=60.0
    )
    _fail_on(ledger, "UPDATE mutation_ledger")
    queue.submit("op-1", operation_id="op-1", payload={"status": "success"})

    # Terminalization failed, but the outcome is durably recorded and the
    # admission row still names its owner, so recovery can finish it.
    pending = ledger.pending_outcome("op-1")
    assert pending is not None
    assert pending["payload"] == {"status": "success"}
    assert ledger.admission_for_project("project-a") is not None
    assert queue.pending_count() == 1


def test_a_pending_outcome_write_that_itself_fails_transiently_is_retried_by_a_server_owned_in_memory_queue_not_the_exiting_worker_and_eventually_terminalizes_without_re_executing_work(
    tmp_path,
) -> None:
    ledger = MutationLedger(db_path=tmp_path / "admission.db")
    _seed_operation(ledger, "op-1")
    ledger.admit(
        "project-a",
        execution_identity="scan_start:plan-1",
        slot_id="op-1",
        operation_id="op-1",
        run_id="run-1",
        plan_id="plan-1",
        owner_instance_id="owner-1",
    )
    queue = PendingOutcomeQueue(
        ledger, owner_instance_id="owner-1", retry_interval=60.0
    )
    work_runs = {"n": 0}

    def _body() -> dict:
        work_runs["n"] += 1
        return {"status": "success"}

    payload = _body()
    _fail_on(ledger, "INSERT OR REPLACE INTO pending_outcomes")
    queue.submit("op-1", operation_id="op-1", payload=payload)
    assert queue.pending_count() == 1
    assert ledger.pending_outcome("op-1") is None

    # The queue -- not the long-gone worker -- owns the retry, and the retry
    # is bookkeeping only: the real work never runs a second time.
    _clear_failures(ledger)
    assert queue.drain_once() == 1
    assert queue.pending_count() == 0
    assert ledger.get_operation_status("op-1")["status"] == "terminal"
    assert ledger.admission_for_project("project-a") is None
    assert work_runs["n"] == 1


def test_a_thread_launch_failure_outside_any_worker_closure_is_caught_by_the_dispatcher_and_terminalizes_via_the_same_idempotent_transaction(
    tmp_path,
) -> None:
    ctx = _admission_ctx(tmp_path)
    _seed_operation(ctx.mutations, "op-1")

    class _UnlaunchableThread:
        def start(self) -> None:
            raise RuntimeError("can't start new thread")

    with pytest.raises(_ActionDenied) as excinfo:
        _admit_and_launch(
            ctx,
            "project-a",
            execution_identity="scan_start:plan-1",
            slot_id="op-1",
            operation_id="op-1",
            run_id="run-1",
            plan_id="plan-1",
            thread=_UnlaunchableThread(),
        )
    assert excinfo.value.status == 503
    status = ctx.mutations.get_operation_status("op-1")
    assert status["status"] == "terminal"
    assert status["payload"]["code"] == "thread_launch_failed"
    assert ctx.mutations.admission_for_project("project-a") is None


def test_a_live_request_conflicting_with_a_dead_owners_row_receives_the_same_structured_busy_conflict_as_a_live_owner_never_attempting_takeover_itself(
    tmp_path,
) -> None:
    ledger = MutationLedger(db_path=tmp_path / "admission.db")
    ledger.admit(
        "project-a",
        execution_identity="scan_start:plan-1",
        slot_id="op-dead",
        operation_id="op-dead",
        run_id="run-dead",
        plan_id="plan-1",
        owner_instance_id="owner-that-died",
    )
    # No live process holds `owner-that-died`'s lock.
    assert probe_owner_alive("owner-that-died", data_root=tmp_path) is False

    losing = ledger.admit(
        "project-a",
        execution_identity="scan_start:plan-2",
        slot_id="op-live",
        operation_id="op-live",
        run_id="run-live",
        plan_id="plan-2",
        owner_instance_id="owner-live",
    )
    assert losing.conflict is True
    # The dead owner's row is untouched -- a live request never takes over.
    row = ledger.admission_for_project("project-a")
    assert row["owner_instance_id"] == "owner-that-died"
    assert row["slot_id"] == "op-dead"


def test_recovery_alone_reconciles_a_dead_owners_row_using_its_own_recorded_identity_and_clears_it_via_the_terminal_release_path(
    tmp_path,
) -> None:
    ledger = MutationLedger(db_path=tmp_path / "admission.db")
    _seed_operation(ledger, "op-dead")
    ledger.admit(
        "project-a",
        execution_identity="scan_start:plan-1",
        slot_id="op-dead",
        operation_id="op-dead",
        run_id="run-dead",
        plan_id="plan-1",
        owner_instance_id="owner-that-died",
    )
    assert reconcile_admissions(ledger, data_root=tmp_path) == 1
    assert ledger.admission_for_project("project-a") is None
    status = ledger.get_operation_status("op-dead")
    assert status["status"] == "terminal"
    assert status["payload"]["status"] == "interrupted"
    assert status["payload"]["execution_identity"] == "scan_start:plan-1"


def test_recovery_and_a_live_not_actually_crashed_owner_racing_the_same_durable_admission_table_never_both_conclude_they_are_the_sole_executor(
    tmp_path,
) -> None:
    ledger = MutationLedger(db_path=tmp_path / "admission.db")
    ledger.admit(
        "project-a",
        execution_identity="scan_start:plan-1",
        slot_id="op-live",
        operation_id="op-live",
        run_id="run-live",
        plan_id="plan-1",
        owner_instance_id="owner-alive",
    )
    lock = OwnerLock("owner-alive", data_root=tmp_path)
    assert lock.owner_instance_id == "owner-alive"
    # Owner still holds its kernel lock: recovery must not reconcile anything.
    assert reconcile_admissions(ledger, data_root=tmp_path) == 0
    assert ledger.admission_for_project("project-a") is not None


def test_recovery_retrying_a_pending_outcome_never_re_executes_the_operations_actual_work_only_the_bookkeeping_write(
    tmp_path,
) -> None:
    ledger = MutationLedger(db_path=tmp_path / "admission.db")
    _seed_operation(ledger, "op-1")
    ledger.admit(
        "project-a",
        execution_identity="scan_start:plan-1",
        slot_id="op-1",
        operation_id="op-1",
        run_id="run-1",
        plan_id="plan-1",
        owner_instance_id="owner-alive",
    )
    lock = OwnerLock("owner-alive", data_root=tmp_path)
    assert lock.owner_instance_id == "owner-alive"
    ledger.register_pending_outcome(
        "op-1",
        operation_id="op-1",
        payload={"status": "success", "run_id": "run-1"},
        owner_instance_id="owner-alive",
    )

    # Owner is alive, so the dead-owner branch never fires -- but the durably
    # registered pending outcome is still retried, bookkeeping only. S02:
    # this is *this* recovering call's own live owner retrying its own
    # previously-attempted-but-unconfirmed outcome, so it must identify
    # itself as that same owner.
    assert (
        reconcile_admissions(
            ledger, data_root=tmp_path, recovering_owner_instance_id="owner-alive"
        )
        == 1
    )
    status = ledger.get_operation_status("op-1")
    assert status["status"] == "terminal"
    assert status["payload"] == {"status": "success", "run_id": "run-1"}
    assert ledger.admission_for_project("project-a") is None
    assert ledger.pending_outcome("op-1") is None


def _spawn_orphaned_sleeper() -> int:
    """A real, killable process-group leader standing in for an owned engine
    child (`start_new_session=True` makes its own pid its pgid, matching
    `_launch_gated_process`'s real contract) -- spawned and orphaned by a
    fresh, single-threaded helper interpreter that exits immediately after
    printing its child's pid, so the sleeper reparents to init/launchd
    exactly like a real dead owner's genuinely-orphaned child. Spawning it
    directly from this (very much alive, multi-threaded) test process
    instead would leave a permanent zombie a same-process `killpg(pgid, 0)`
    liveness check can misreport on macOS -- or, if forked straight from
    this interpreter, could deadlock the child outright: any process-wide
    lock held by another thread at the instant of `os.fork()` would remain
    held forever in it. Delegating the fork+exec to a throwaway,
    single-threaded `python -c` subprocess sidesteps both hazards (no
    `setsid(1)` binary exists on macOS, so a shell-based equivalent isn't
    portable here)."""
    helper_script = (
        "import subprocess\n"
        "child = subprocess.Popen(['sleep', '30'], start_new_session=True, "
        "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
        "stderr=subprocess.DEVNULL)\n"
        "print(child.pid)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", helper_script],
        capture_output=True,
        text=True,
        check=True,
    )
    return int(result.stdout.strip())


def _pgid_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    return True


def test_dead_owner_reap_terminates_recorded_children_before_release(
    tmp_path, monkeypatch
) -> None:
    """S02: reproduces the exact defect Evidence cites -- a dead owner's
    admission row must never release while its recorded children are still
    alive. Before the fix, `reconcile_admissions` released the row with no
    `reap_owner_processes` call at all; the child kept running."""
    monkeypatch.setattr("rush.setup.provision.default_data_root", lambda: tmp_path)
    from rush.runtime.subprocesses import _record_owned_process

    ledger = MutationLedger(db_path=tmp_path / "admission.db")
    _seed_operation(ledger, "op-dead")
    ledger.admit(
        "project-a",
        execution_identity="scan_start:plan-1",
        slot_id="op-dead",
        operation_id="op-dead",
        run_id="run-dead",
        plan_id="plan-1",
        owner_instance_id="owner-that-died",
    )
    pgid = _spawn_orphaned_sleeper()
    _record_owned_process("owner-that-died", "run-dead", pgid)
    assert probe_owner_alive("owner-that-died", data_root=tmp_path) is False
    try:
        assert _pgid_alive(pgid) is True

        assert (
            reconcile_admissions(
                ledger, data_root=tmp_path, recovering_owner_instance_id="owner-live"
            )
            == 1
        )

        assert _pgid_alive(pgid) is False
        assert ledger.admission_for_project("project-a") is None
        status = ledger.get_operation_status("op-dead")
        assert status["status"] == "terminal"
        assert status["payload"]["code"] == "owner_died"
    finally:
        with suppress(ProcessLookupError, PermissionError):
            os.killpg(pgid, signal.SIGKILL)


def test_live_owners_pending_outcome_retried_without_reaping_its_own_children(
    tmp_path, monkeypatch
) -> None:
    """S02 Fix item 1: a live owner's own durably-registered pending outcome
    is retried as bookkeeping -- but this recovering call must never reap
    that live owner's still-running children just because it also holds a
    pending outcome."""
    monkeypatch.setattr("rush.setup.provision.default_data_root", lambda: tmp_path)
    from rush.runtime.subprocesses import _record_owned_process

    ledger = MutationLedger(db_path=tmp_path / "admission.db")
    _seed_operation(ledger, "op-live")
    ledger.admit(
        "project-a",
        execution_identity="scan_start:plan-1",
        slot_id="op-live",
        operation_id="op-live",
        run_id="run-live",
        plan_id="plan-1",
        owner_instance_id="owner-alive",
    )
    OwnerLock("owner-alive", data_root=tmp_path)
    ledger.register_pending_outcome(
        "op-live",
        operation_id="op-live",
        payload={"status": "success", "run_id": "run-live"},
        owner_instance_id="owner-alive",
    )
    pgid = _spawn_orphaned_sleeper()
    _record_owned_process("owner-alive", "run-live", pgid)
    try:
        assert _pgid_alive(pgid) is True

        assert (
            reconcile_admissions(
                ledger, data_root=tmp_path, recovering_owner_instance_id="owner-alive"
            )
            == 1
        )

        # Bookkeeping only -- the still-live owner's real child is untouched.
        assert _pgid_alive(pgid) is True
        status = ledger.get_operation_status("op-live")
        assert status["status"] == "terminal"
        assert status["payload"] == {"status": "success", "run_id": "run-live"}
    finally:
        with suppress(ProcessLookupError, PermissionError):
            os.killpg(pgid, signal.SIGKILL)


def test_foreign_live_owner_admission_is_never_reaped(tmp_path, monkeypatch) -> None:
    """S02 Fix item 1: a durable pending outcome belonging to some *other*
    live owner is never permission to release that owner's admission or
    touch its children -- only that owner's own recovering call may retry
    its own pending outcome."""
    monkeypatch.setattr("rush.setup.provision.default_data_root", lambda: tmp_path)
    from rush.runtime.subprocesses import _record_owned_process

    ledger = MutationLedger(db_path=tmp_path / "admission.db")
    _seed_operation(ledger, "op-foreign")
    ledger.admit(
        "project-a",
        execution_identity="scan_start:plan-1",
        slot_id="op-foreign",
        operation_id="op-foreign",
        run_id="run-foreign",
        plan_id="plan-1",
        owner_instance_id="owner-foreign-live",
    )
    OwnerLock("owner-foreign-live", data_root=tmp_path)
    ledger.register_pending_outcome(
        "op-foreign",
        operation_id="op-foreign",
        payload={"status": "success", "run_id": "run-foreign"},
        owner_instance_id="owner-foreign-live",
    )
    pgid = _spawn_orphaned_sleeper()
    _record_owned_process("owner-foreign-live", "run-foreign", pgid)
    try:
        assert _pgid_alive(pgid) is True

        # A *different* recovering owner never treats a foreign owner's
        # pending outcome as its own to retry, and the owner is genuinely
        # alive so the dead-owner claim also never succeeds.
        assert (
            reconcile_admissions(
                ledger,
                data_root=tmp_path,
                recovering_owner_instance_id="owner-someone-else",
            )
            == 0
        )

        assert _pgid_alive(pgid) is True
        assert ledger.admission_for_project("project-a") is not None
        status = ledger.get_operation_status("op-foreign")
        assert status["status"] != "terminal"
    finally:
        with suppress(ProcessLookupError, PermissionError):
            os.killpg(pgid, signal.SIGKILL)


def test_failed_reap_retains_admission_and_does_not_release(
    tmp_path, monkeypatch
) -> None:
    """S02 Fix item 3: an unconfirmed termination must never release the
    admission row -- it stays intact, flagged `recovery_required`/
    `termination_unconfirmed`, for the next sweep to retry."""
    monkeypatch.setattr("rush.setup.provision.default_data_root", lambda: tmp_path)
    from rush.runtime import subprocesses as sp

    monkeypatch.setattr(sp, "terminate_owned_group", lambda *a, **k: False)

    ledger = MutationLedger(db_path=tmp_path / "admission.db")
    _seed_operation(ledger, "op-stuck")
    ledger.admit(
        "project-a",
        execution_identity="scan_start:plan-1",
        slot_id="op-stuck",
        operation_id="op-stuck",
        run_id="run-stuck",
        plan_id="plan-1",
        owner_instance_id="owner-that-died",
    )
    sp._record_owned_process("owner-that-died", "run-stuck", 999_999)
    assert probe_owner_alive("owner-that-died", data_root=tmp_path) is False

    assert (
        reconcile_admissions(
            ledger, data_root=tmp_path, recovering_owner_instance_id="owner-live"
        )
        == 0
    )

    assert ledger.admission_for_project("project-a") is not None
    status = ledger.get_operation_status("op-stuck")
    assert status["status"] == "recovery_required"
    assert status["payload"]["code"] == "termination_unconfirmed"
    records = sp.read_owned_process_records("owner-that-died", data_root=tmp_path)
    assert len(records) == 1
    assert records[0]["termination_unconfirmed"] is True


def test_kill_recovery_after_confirmed_reap_but_before_finalization_restart_consumes_receipts_without_repeating_effects(
    tmp_path, monkeypatch
) -> None:
    """S02 Fix item 4: a recovery sweep that reaps a dead owner's children
    for real and then dies before `terminalize_and_release` ever runs (a
    crash strictly between confirmed reap and finalization) must never
    repeat its reap/effects on restart -- the next sweep finds the children
    already gone (nothing left to terminate) and finalizes using the exact
    pre-crash receipt (`register_pending_outcome`'s payload) already
    registered, rather than reaping again or inventing a fresh payload."""
    monkeypatch.setattr("rush.setup.provision.default_data_root", lambda: tmp_path)
    from rush.runtime.subprocesses import _record_owned_process

    ledger = MutationLedger(db_path=tmp_path / "admission.db")
    _seed_operation(ledger, "op-dead")
    ledger.admit(
        "project-a",
        execution_identity="scan_start:plan-1",
        slot_id="op-dead",
        operation_id="op-dead",
        run_id="run-dead",
        plan_id="plan-1",
        owner_instance_id="owner-that-died",
    )
    # Pre-crash committed effect receipt: the real work already reached a
    # terminal outcome before the owner died; only the ledger write (this
    # recovery sweep's finalization) never landed.
    ledger.register_pending_outcome(
        "op-dead",
        operation_id="op-dead",
        payload={
            "status": "success",
            "run_id": "run-dead",
            "receipt_id": "effect-committed-once",
        },
        owner_instance_id="owner-that-died",
    )
    pgid = _spawn_orphaned_sleeper()
    _record_owned_process("owner-that-died", "run-dead", pgid)
    assert probe_owner_alive("owner-that-died", data_root=tmp_path) is False

    real_terminalize = MutationLedger.terminalize_and_release
    call_count = {"n": 0}

    def _crash_before_finalization(self, *args, **kwargs):
        call_count["n"] += 1
        raise RuntimeError("simulated crash before finalization commits")

    try:
        assert _pgid_alive(pgid) is True

        monkeypatch.setattr(
            MutationLedger, "terminalize_and_release", _crash_before_finalization
        )
        assert (
            reconcile_admissions(
                ledger, data_root=tmp_path, recovering_owner_instance_id="owner-live-1"
            )
            == 0
        )
        # The reap already happened for real before the simulated crash --
        # the child is gone even though this sweep never finalized.
        assert _pgid_alive(pgid) is False
        assert call_count["n"] == 1
        assert ledger.admission_for_project("project-a") is not None
        assert ledger.pending_outcome("op-dead") is not None

        monkeypatch.setattr(MutationLedger, "terminalize_and_release", real_terminalize)
        assert (
            reconcile_admissions(
                ledger, data_root=tmp_path, recovering_owner_instance_id="owner-live-2"
            )
            == 1
        )

        assert ledger.admission_for_project("project-a") is None
        assert ledger.pending_outcome("op-dead") is None
        status = ledger.get_operation_status("op-dead")
        assert status["status"] == "terminal"
        # Restart consumed the pre-crash receipt itself, never a freshly
        # synthesized "owner_died" payload -- no effect was repeated, and
        # the reap was never attempted a second time (already asserted via
        # call_count above being the only reap-triggering call).
        assert status["payload"] == {
            "status": "success",
            "run_id": "run-dead",
            "receipt_id": "effect-committed-once",
        }
    finally:
        with suppress(ProcessLookupError, PermissionError):
            os.killpg(pgid, signal.SIGKILL)


# --- S09: durable admission-table attempt_id column -------------------------


def test_admission_schema_carries_attempt_id_column(tmp_path) -> None:
    """S09 Fix item 1: `scan_admission` must carry a durable `attempt_id`
    column (not just be inferred later from a disk lookup), and `admit()`
    must persist and return whatever executing attempt is passed in."""
    ledger = MutationLedger(db_path=tmp_path / "admission.db")
    with sqlite3.connect(str(tmp_path / "admission.db")) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(scan_admission)")}
    assert "attempt_id" in columns

    result = ledger.admit(
        "project-a",
        execution_identity="scan_start:plan-1",
        slot_id="op-1",
        operation_id="op-1",
        run_id="run-1",
        plan_id="plan-1",
        owner_instance_id="owner-1",
        attempt_id="attempt-1",
    )
    assert result.started is True
    assert result.attempt_id == "attempt-1"

    row = ledger.list_admissions()[0]
    assert row["attempt_id"] == "attempt-1"


def test_concurrent_old_schema_startup_migration_is_race_free(tmp_path) -> None:
    """S09/S04 Fix item 1: two server processes starting against the same
    pre-existing OLD-schema database file at once must serialize on the
    additive migration's own `BEGIN IMMEDIATE` transaction rather than both
    racing the same `ALTER TABLE` -- confirmed against a real on-disk
    pre-migration schema (missing `attempt_id` and the S04 ledger columns
    entirely), not just a fresh empty database."""
    db_path = tmp_path / "admission.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.executescript(
            """
            CREATE TABLE mutation_ledger (
                project_id TEXT NOT NULL,
                request_id TEXT NOT NULL,
                operation_id TEXT NOT NULL,
                operation_type TEXT NOT NULL DEFAULT '',
                body_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                status_code INTEGER,
                response_body BLOB,
                transition_status TEXT,
                transition_payload TEXT,
                created_at REAL NOT NULL,
                terminal_at REAL,
                PRIMARY KEY (project_id, request_id)
            );
            CREATE TABLE scan_admission (
                project_id TEXT NOT NULL,
                execution_identity TEXT NOT NULL,
                slot_id TEXT NOT NULL,
                operation_id TEXT NOT NULL DEFAULT '',
                owner_instance_id TEXT NOT NULL DEFAULT '',
                run_id TEXT NOT NULL DEFAULT '',
                plan_id TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL,
                UNIQUE(project_id)
            );
            """
        )
        conn.commit()

    errors: list[BaseException] = []
    ledgers: list[MutationLedger | None] = [None] * 8

    def _start(index: int) -> None:
        try:
            ledgers[index] = MutationLedger(db_path=db_path)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=_start, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert errors == []
    assert all(ledger is not None for ledger in ledgers)

    with sqlite3.connect(str(db_path)) as conn:
        admission_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(scan_admission)")
        }
        ledger_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(mutation_ledger)")
        }
    assert "attempt_id" in admission_columns
    assert {"validated_arguments", "effect_ids", "recovery_schema_version"} <= (
        ledger_columns
    )

    result = ledgers[0].admit(
        "project-a",
        execution_identity="scan_start:plan-1",
        slot_id="op-1",
        operation_id="op-1",
        run_id="run-1",
        plan_id="plan-1",
        owner_instance_id="owner-1",
        attempt_id="attempt-1",
    )
    assert result.started is True
    assert result.attempt_id == "attempt-1"


def test_windows_mutex_name_is_deterministic_and_namespaced() -> None:
    """S03 item 1: pure string derivation, testable without a Windows
    runner -- deterministic per owner, namespaced, never colliding across
    two distinct owner identities. The other 8 named S03 regression tests
    (mutex acquire/release, abandoned-mutex dead-owner detection, gate/job
    fencing) all require real WinAPI calls that cannot execute on this
    macOS environment; per this repo's zero-skipped-tests policy they are
    not added here as `pytest.mark.skip` stubs -- they are named in full in
    this task's own receipt as an explicit, unverified platform gap."""
    from rush.dashboard.state import _windows_mutex_name

    name = _windows_mutex_name("tui:abc-123")
    same_again = _windows_mutex_name("tui:abc-123")
    different_owner = _windows_mutex_name("tui:xyz-789")

    assert name.startswith("Local\\RushOwner-")
    assert name == same_again
    assert name != different_owner


def test_recovery_runs_on_a_recurring_interval_not_only_at_startup_so_a_server_that_outlives_a_dead_peer_eventually_reclaims_its_row(
    tmp_path,
) -> None:
    ctx = _admission_ctx(tmp_path, recovery_interval=0.02)
    _seed_operation(ctx.mutations, "op-1")
    # Row appears *after* the startup sweep already ran.
    ctx.mutations.admit(
        "project-a",
        execution_identity="scan_start:plan-1",
        slot_id="op-dead",
        operation_id="op-dead",
        run_id="run-dead",
        plan_id="plan-1",
        owner_instance_id="owner-that-died",
    )
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if ctx.mutations.admission_for_project("project-a") is None:
            break
        time.sleep(0.01)
    assert ctx.mutations.admission_for_project("project-a") is None


def test_cross_process_project_lock_shared_default_genuinely_contends_but_an_explicit_caller_data_root_is_fully_isolated_from_it(
    tmp_path, monkeypatch
) -> None:
    """T027 regression: `cross_process_project_lock` always fell back to
    the real shared `default_data_root()` whenever a caller didn't pass
    `data_root` -- confirmed via grep, neither of `rush.tools.project`'s
    two call sites did. Combined with test fixtures that reuse the same
    literal project_id (e.g. "project-a") across many tests, this is a
    real, genuinely blocking `flock()` contention point, not just a stale
    on-disk file. This test proves the shared-default path really
    contends (never hangs -- every wait below is bounded), and that a
    caller passing its own explicit, distinct `data_root` is completely
    unaffected by a peer still holding the shared-default lock."""
    shared_root = tmp_path / "shared-default"
    monkeypatch.setattr("rush.setup.provision.default_data_root", lambda: shared_root)
    project_id = "project-a"

    held = threading.Event()
    release = threading.Event()

    def _hold_shared_default_lock() -> None:
        with cross_process_project_lock(project_id):  # no data_root -> shared default
            held.set()
            release.wait(timeout=5.0)

    holder = threading.Thread(target=_hold_shared_default_lock, daemon=True)
    holder.start()
    assert held.wait(timeout=2.0), "holder never acquired the shared-default lock"

    # A second caller using the same implicit shared default genuinely
    # contends -- it must not acquire while the first caller still holds it
    # (simulating a crashed/hung peer that never releases).
    acquired_shared = threading.Event()

    def _try_shared_default() -> None:
        with cross_process_project_lock(project_id):
            acquired_shared.set()

    contender = threading.Thread(target=_try_shared_default, daemon=True)
    contender.start()
    assert not acquired_shared.wait(timeout=0.5), (
        "a second shared-default caller acquired the lock while the first "
        "still held it -- contention no longer real"
    )

    # A caller that instead passes its own explicit, isolated data_root is
    # never blocked by the shared-default holder above -- same project_id,
    # genuinely different on-disk lock file.
    isolated_root = tmp_path / "isolated-caller"
    with cross_process_project_lock(project_id, data_root=isolated_root):
        pass  # acquiring at all (never blocking) is the assertion here.

    release.set()
    holder.join(timeout=2.0)
    contender.join(timeout=2.0)
    assert acquired_shared.wait(timeout=2.0), (
        "contender never acquired after the shared-default holder released"
    )


def test_project_tool_configure_threads_caller_data_root_into_cross_process_project_lock_never_the_shared_default(
    tmp_path,
) -> None:
    """T027 regression: both of `ProjectTool`'s "configure" call sites
    (`.run`/`._dispatch` and `.handle_request`/`._handle_request_unsafe`,
    `rush/tools/project.py` lines 256 and 414) now thread an explicit
    `data_root` all the way into `cross_process_project_lock` instead of
    always defaulting to the real shared root -- this fails if either
    call site regresses back to omitting it."""
    seen: list[Path | None] = []
    real_lock = dashboard_state.cross_process_project_lock

    @contextmanager
    def _spy(project_id: str, *, data_root: Path | None = None):
        seen.append(data_root)
        with real_lock(project_id, data_root=data_root):
            yield

    explicit_root = tmp_path / "caller-root"

    with patch.object(dashboard_state, "cross_process_project_lock", _spy):
        run_result = ProjectTool().run(
            tmp_path,
            action="configure",
            project_id="unknown-project",
            data_root=explicit_root,
        )
        assert seen == [explicit_root]
        # `configure_project` can't find an unregistered project -- the
        # lock was still correctly entered/exited with the right
        # data_root regardless of that unrelated downstream failure.
        assert run_result["status"] == "error"

        envelope_result = ProjectTool().handle_request(
            {
                "schema_version": 1,
                "operation": "configure",
                "project": str(uuid.uuid4()),
            },
            data_root=explicit_root,
        )
        assert seen == [explicit_root, explicit_root]
        assert envelope_result["raw"]["error"] is not None


def test_pruning_a_chain_of_three_attached_operation_ids_removes_every_link_and_every_reservation_row_together_not_just_direct_pointers(
    tmp_path,
) -> None:
    ledger = _chained_attachments(tmp_path)
    assert ledger.prune_expired(ttl_seconds=0) == 3
    assert ledger.get_operation_status("op-c") is None
    assert ledger.get_operation_status("op-b") is None
    assert ledger.get_operation_status("op-a") is None
    assert ledger.attachment_count() == 0


def test_pruning_a_terminal_expired_executing_operation_also_prunes_every_attachment_record_pointing_to_it_in_the_same_pass(
    tmp_path,
) -> None:
    ledger = _chained_attachments(tmp_path)
    assert ledger.attachment_count() == 2
    ledger.prune_expired(ttl_seconds=0)
    assert ledger.attachment_count() == 0


def test_attachment_record_is_never_pruned_before_its_executing_operations_own_row_reaches_terminal_and_expires(
    tmp_path,
) -> None:
    ledger = _chained_attachments(tmp_path, terminal=False)
    assert ledger.prune_expired(ttl_seconds=0) == 0
    assert ledger.attachment_count() == 2
    assert ledger.get_operation_status("op-a") is not None


def test_pruning_uses_begin_immediate_not_a_deferred_transaction_so_discovery_through_deletion_is_genuinely_serialized_against_a_concurrent_attachment_write(
    tmp_path,
) -> None:
    ledger = _chained_attachments(tmp_path)
    statements = _record_sql(ledger)
    ledger.prune_expired(ttl_seconds=0)
    joined = " | ".join(statements)
    assert "BEGIN IMMEDIATE" in joined
    assert "BEGIN" not in joined.replace("BEGIN IMMEDIATE", "")
    body = joined.split("BEGIN IMMEDIATE", 1)[1]
    discovery = body.split("DELETE", 1)[0]
    assert "SELECT operation_id, executing_operation_id FROM operation_attachments" in (
        discovery
    )


def test_a_busy_signal_during_pruning_restarts_the_whole_discover_validate_delete_transaction_never_retries_delete_alone_against_stale_discovered_rows(
    tmp_path,
) -> None:
    ledger = _chained_attachments(tmp_path)
    statements = _record_sql(ledger)
    _fail_on(
        ledger, "DELETE FROM mutation_ledger", times=1, message="database is locked"
    )

    assert ledger.prune_expired(ttl_seconds=0, deadline_seconds=2.0) == 3
    # Two full passes: discovery re-ran, it was never a bare DELETE retry.
    assert (
        len(
            [
                s
                for s in statements
                if s.startswith("SELECT operation_id, executing_operation_id")
            ]
        )
        == 2
    )
    assert len([s for s in statements if s == "BEGIN IMMEDIATE"]) == 2


def test_pruning_retries_are_bounded_by_a_total_deadline_not_unbounded_under_sustained_contention(
    tmp_path,
) -> None:
    ledger = _chained_attachments(tmp_path)
    _fail_on(
        ledger,
        "DELETE FROM mutation_ledger",
        times=10_000,
        message="database is locked",
    )
    started = time.monotonic()
    assert ledger.prune_expired(ttl_seconds=0, deadline_seconds=0.2) == 0
    assert time.monotonic() - started < 3.0


def test_a_prune_that_exhausts_its_retry_deadline_leaves_rows_fully_intact_and_deferred_to_the_next_sweep_never_partially_deleted(
    tmp_path,
) -> None:
    ledger = _chained_attachments(tmp_path)
    _fail_on(
        ledger,
        "DELETE FROM mutation_ledger",
        times=10_000,
        message="database is locked",
    )
    assert ledger.prune_expired(ttl_seconds=0, deadline_seconds=0.2) == 0
    assert ledger.attachment_count() == 2
    assert ledger.get_operation_status("op-a") is not None
    assert ledger.get_operation_status("op-c") is not None

    _clear_failures(ledger)
    assert ledger.prune_expired(ttl_seconds=0) == 3


def test_a_failure_between_individual_deletion_statements_during_pruning_rolls_back_rather_than_leaving_a_partially_pruned_chain(
    tmp_path,
) -> None:
    ledger = _chained_attachments(tmp_path)
    # Attachment rows are deleted first; fail on the ledger delete that
    # follows, with a non-retryable error.
    _fail_on(ledger, "DELETE FROM mutation_ledger", message="disk I/O error")
    with pytest.raises(sqlite3.OperationalError):
        ledger.prune_expired(ttl_seconds=0)
    _clear_failures(ledger)
    assert ledger.attachment_count() == 2
    assert ledger.get_operation_status("op-a") is not None


def test_a_concurrent_attachment_arriving_mid_sweep_is_serialized_against_pruning_never_attaching_to_a_row_being_deleted(
    tmp_path,
) -> None:
    ledger = _chained_attachments(tmp_path)
    # A genuinely live job holding the project's slot, unrelated to the
    # terminal-and-expired op-a/op-b/op-c chain the sweep is about to prune.
    _seed_operation(ledger, "op-e")
    ledger.admit(
        "project-a",
        execution_identity="scan_start:plan-live",
        slot_id="op-e",
        operation_id="op-e",
        run_id="run-e",
        plan_id="plan-live",
        owner_instance_id="owner-1",
    )
    attached: list[object] = []
    pruned: list[int] = []
    barrier = threading.Barrier(2, timeout=5)

    def _attach() -> None:
        barrier.wait()
        attached.append(
            ledger.admit(
                "project-a",
                execution_identity="scan_start:plan-live",
                slot_id="op-d",
                operation_id="op-d",
                run_id="run-d",
                plan_id="plan-live",
                owner_instance_id="owner-1",
            )
        )

    def _prune() -> None:
        barrier.wait()
        pruned.append(ledger.prune_expired(ttl_seconds=0, deadline_seconds=3.0))

    threads = [
        threading.Thread(target=_attach, daemon=True),
        threading.Thread(target=_prune, daemon=True),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert pruned == [3]
    assert attached[0].attached is True
    # Whatever the interleaving, no attachment record survives pointing at an
    # operation row that pruning removed.
    assert ledger.resolve_attachment("op-d") == "op-e"
    for operation_id, executing_id in ledger.attachment_pairs():
        assert ledger.get_operation_status(executing_id) is not None, (
            f"{operation_id} dangles at pruned {executing_id}"
        )


# --------------------------------------------------------------------------
# P69-06e: the CHECK_SUITE control command. A real, header-authenticated
# control-channel route (`POST /api/control/check-suite`) that dispatches the
# suite inside the dashboard's *own* process, through the same admission /
# supervision / status primitives every other async operation uses -- never a
# same-process function call from `tui.py`, and never `scan_start` with a
# fabricated plan_id/grants standing in for a different, lighter operation.
# --------------------------------------------------------------------------


def _check_suite_project(tmp_path):
    """A registered project plus a running dashboard server for it."""
    project_dir = tmp_path / "check-suite-proj"
    project_dir.mkdir()
    record = register_project(project_dir)
    snapshot = {
        "schema_version": 1,
        "project_id": record.project_id,
        "source_identity": record.project_id,
        "root": str(project_dir),
        "files": [],
        "findings": [],
        "memories": [],
        "agents": [],
    }
    server, ctx, token = create_dashboard_server({record.project_id: snapshot})
    _serve(server)
    return server, ctx, token, record.project_id, project_dir


def _control_check_suite(base_url, control_token, project_id, request_id, **extra):
    headers = {
        "X-Rush-Control": control_token,
        "Content-Type": "application/json",
    }
    headers.update(extra.pop("headers", {}))
    body = json.dumps(
        {"schema_version": 1, "project_id": project_id, "request_id": request_id}
    ).encode()
    return _post(f"{base_url}/api/control/check-suite", headers=headers, body=body)


class _SuiteProbe:
    """Records exactly how `run_workflow_suite` was called, and optionally
    blocks inside it so a test can observe real in-flight state."""

    def __init__(self, gate: threading.Event | None = None) -> None:
        self.calls: list[dict] = []
        self.entered = threading.Event()
        self._gate = gate

    def __call__(self, **kwargs):
        self.calls.append({**kwargs, "thread_ident": threading.get_ident()})
        self.entered.set()
        if self._gate is not None:
            self._gate.wait(timeout=10)
        return {
            "tool": "check",
            "status": "ok",
            "duration_ms": 0,
            "summary": "check: ok",
            "findings": [],
            "metadata": {},
        }


def test_check_suite_control_command_calls_start_or_attach_before_dispatching(
    tmp_path, monkeypatch
) -> None:
    """P69-06e: the handler goes through the shared admission decision
    *before* it dispatches, so a concurrent full scan is arbitrated by the
    same mechanism that arbitrates every other operation.

    The plan names `ScanRunTracker.start_or_attach()`; P69-02.2f (T010) had
    already moved that decision out of the in-memory tracker into the durable
    `ctx.mutations.admit()` transaction reached via `_admit_and_launch` -- the
    same call `scan_start`/`scan_resume`/`rescan` now make. This asserts
    against that real, current primitive.
    """
    gate = threading.Event()
    probe = _SuiteProbe(gate)
    monkeypatch.setattr("rush.dashboard.server.run_workflow_suite", probe)
    server, ctx, _token, project_id, _root = _check_suite_project(tmp_path)
    try:
        resp = _control_check_suite(
            ctx.launch_origin, ctx.auth.control_capability, project_id, "req-cs-1"
        )
        assert resp.status == 202, resp.read()
        assert probe.entered.wait(timeout=5)

        admission = ctx.mutations.admission_for_project(project_id)
        assert admission is not None, "dispatched without an admission row"
        assert admission["execution_identity"] == "check_suite:check"
        assert admission["plan_id"] == "check_suite:check"
        assert admission["owner_instance_id"] == ctx.owner_instance_id
    finally:
        gate.set()
        server.shutdown()
        server.server_close()


def test_concurrent_full_scan_and_check_suite_against_same_project_resolve_through_one_admission_check(
    tmp_path, monkeypatch
) -> None:
    """P69-06e + P69-01.2p: a full scan arriving while CHECK_SUITE is running
    must never silently attach to it (it has a genuinely different execution
    identity) -- both requests are arbitrated by the one admission check."""
    gate = threading.Event()
    probe = _SuiteProbe(gate)
    monkeypatch.setattr("rush.dashboard.server.run_workflow_suite", probe)
    server, ctx, _token, project_id, _root = _check_suite_project(tmp_path)
    try:
        resp = _control_check_suite(
            ctx.launch_origin, ctx.auth.control_capability, project_id, "req-cs-2"
        )
        assert resp.status == 202
        assert probe.entered.wait(timeout=5)

        with pytest.raises(ScanConflictError):
            _admit_and_launch(
                ctx,
                project_id,
                execution_identity="scan_start:plan-xyz",
                slot_id="slot-full",
                operation_id="op-full",
                run_id="run-full",
                plan_id="plan-xyz",
                thread=threading.Thread(target=lambda: None),
            )

        # A second CHECK_SUITE request for the same project shares the
        # identity, so it attaches to the running job instead of conflicting.
        second = _control_check_suite(
            ctx.launch_origin, ctx.auth.control_capability, project_id, "req-cs-3"
        )
        assert second.status == 202
        payload = json.loads(second.read())["data"]
        assert payload["attached_to_existing"] is True
        assert len(probe.calls) == 1, "an attach must not dispatch a second suite run"
    finally:
        gate.set()
        server.shutdown()
        server.server_close()


def test_check_suite_control_command_and_a_concurrent_full_scan_never_silently_attach_via_the_real_http_boundary(
    tmp_path, monkeypatch
) -> None:
    """The same guarantee as above, driven end-to-end through both real HTTP
    surfaces: the control channel for CHECK_SUITE, and the browser-facing
    action route for the full scan."""
    from rush.workflows.project_run import plan_scan

    gate = threading.Event()
    probe = _SuiteProbe(gate)
    monkeypatch.setattr("rush.dashboard.server.run_workflow_suite", probe)
    server, ctx, token, project_id, root = _check_suite_project(tmp_path)
    try:
        base_url = ctx.launch_origin
        resp = _control_check_suite(
            base_url, ctx.auth.control_capability, project_id, "req-cs-4"
        )
        assert resp.status == 202
        assert probe.entered.wait(timeout=5)

        plan = plan_scan(root)
        cookie, csrf = _bootstrap_session(base_url, token)
        scan = _post(
            f"{base_url}/api/projects/{project_id}/actions",
            headers={
                "Cookie": cookie,
                "X-Rush-CSRF": csrf,
                "Origin": base_url,
                "Content-Type": "application/json",
            },
            body=json.dumps(
                {
                    "schema_version": 1,
                    "operation": "scan_start",
                    "request_id": "req-full-1",
                    "arguments": {"plan_id": plan.plan_id},
                    "grants": {"cache_write": True, "artifact_write": True},
                }
            ).encode(),
        )
        assert scan.status == 409, scan.read()
        body = json.loads(scan.read())
        assert body["error"]["code"] == "conflict"
        assert "check_suite:check" in body["error"]["message"]
    finally:
        gate.set()
        server.shutdown()
        server.server_close()


def test_check_suite_control_command_actually_dispatches_inside_the_dashboard_process_not_the_caller(
    tmp_path, monkeypatch
) -> None:
    """P69-06e: an "internal dashboard-server function" is not reachable from
    the TUI process. The suite runs on the server's own background worker
    thread, under the server's own `DashboardContext` identity, and the 202
    returns before the work finishes -- never synchronously in the caller."""
    gate = threading.Event()
    probe = _SuiteProbe(gate)
    monkeypatch.setattr("rush.dashboard.server.run_workflow_suite", probe)
    server, ctx, _token, project_id, _root = _check_suite_project(tmp_path)
    try:
        caller_ident = threading.get_ident()
        resp = _control_check_suite(
            ctx.launch_origin, ctx.auth.control_capability, project_id, "req-cs-5"
        )
        assert resp.status == 202
        # The response landed while the suite is still blocked inside its
        # own worker: the caller was never the executor.
        assert probe.entered.wait(timeout=5)
        assert probe.calls[0]["thread_ident"] != caller_ident
        assert probe.calls[0]["owner_instance_id"] == ctx.owner_instance_id
        assert probe.calls[0]["run_id"]
    finally:
        gate.set()
        server.shutdown()
        server.server_close()


def test_check_suite_control_command_rejects_browser_session_credentials(
    tmp_path, monkeypatch
) -> None:
    """P69-06e: the control boundary is distinct from the browser-facing
    session/CSRF auth -- a presented cookie or Origin is rejected outright,
    and a missing control capability is a 401."""
    probe = _SuiteProbe()
    monkeypatch.setattr("rush.dashboard.server.run_workflow_suite", probe)
    server, ctx, token, project_id, _root = _check_suite_project(tmp_path)
    try:
        base_url = ctx.launch_origin
        cookie, csrf = _bootstrap_session(base_url, token)

        with_cookie = _control_check_suite(
            base_url,
            ctx.auth.control_capability,
            project_id,
            "req-cs-6",
            headers={"Cookie": cookie, "X-Rush-CSRF": csrf},
        )
        assert with_cookie.status == 401

        with_origin = _control_check_suite(
            base_url,
            ctx.auth.control_capability,
            project_id,
            "req-cs-7",
            headers={"Origin": base_url},
        )
        assert with_origin.status == 401

        no_capability = _control_check_suite(base_url, "", project_id, "req-cs-8")
        assert no_capability.status == 401

        assert probe.calls == [], "a rejected request must never dispatch"
    finally:
        server.shutdown()
        server.server_close()


def test_check_suite_startup_job_does_not_fabricate_a_scan_start_plan_id_or_grants(
    tmp_path, monkeypatch
) -> None:
    """P69-06e: CHECK_SUITE is a genuinely different, lighter operation --
    it carries no staged plan_id and negotiates no cache_write/artifact_write
    grants, so the route must neither require nor invent them."""
    probe = _SuiteProbe()
    monkeypatch.setattr("rush.dashboard.server.run_workflow_suite", probe)
    server, ctx, _token, project_id, _root = _check_suite_project(tmp_path)
    try:
        resp = _control_check_suite(
            ctx.launch_origin, ctx.auth.control_capability, project_id, "req-cs-9"
        )
        assert resp.status == 202, resp.read()
        data = json.loads(resp.read())["data"]
        assert "plan_id" not in data or data["plan_id"] == "check_suite:check"
        assert probe.entered.wait(timeout=5)

        permissions = probe.calls[0]["permissions"]
        assert permissions.cache_write is False
        assert permissions.artifact_write is False
        assert permissions.network is False
    finally:
        server.shutdown()
        server.server_close()


def test_check_suite_startup_job_uses_its_own_real_tool_selection_not_a_full_scans(
    tmp_path, monkeypatch
) -> None:
    """P69-06e: routing this through `scan_start` would silently substitute a
    full scan; the control command runs CHECK_SUITE's own real tool
    sequence."""
    from rush.workflows.suites import CHECK_SUITE

    probe = _SuiteProbe()
    monkeypatch.setattr("rush.dashboard.server.run_workflow_suite", probe)
    server, ctx, _token, project_id, root = _check_suite_project(tmp_path)
    try:
        resp = _control_check_suite(
            ctx.launch_origin, ctx.auth.control_capability, project_id, "req-cs-10"
        )
        assert resp.status == 202
        assert probe.entered.wait(timeout=5)

        call = probe.calls[0]
        assert call["suite"] is CHECK_SUITE
        assert call["suite"].tool_sequence == (
            "format",
            "lint",
            "typecheck",
            "dead",
            "slop",
            "test",
        )
        assert Path(call["path"]) == root
    finally:
        server.shutdown()
        server.server_close()
