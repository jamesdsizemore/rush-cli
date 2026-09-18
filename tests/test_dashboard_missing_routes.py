"""Phase 69 P69-02: dashboard routes/actions the plan names as currently
missing or under-specified (§0 rows 2, 6, 14).

Created fresh by P69-02.2's own RED step (subsections a-c). Only the two
handoff-preview tests were added there -- later P69-02 subsections (n/o/p, a
separate packet slice) add the still-missing GET/POST routes and the seven
currently-unwired actions (`configure`, `handoff_status`, `memory_query`,
`memory_expand`, `memory_propose`, `memory_maintain`, `artifact_export`) this
file will eventually also cover.

The two handoff-preview tests below reproduce a real, currently-unfixed gap:
`build_handoff()` (`rush/workflows/project_run.py`) persists a
`MemoryArtifact` and a handoff descriptor unconditionally on every call, with
no non-persisting preview mode -- fixing that (and only then safely dropping
`handoff_preview`'s mutation-grant requirement) needs changes to
`project_run.py`/`memory/handoff.py`, outside this packet slice's own file
scope. They are expected to stay RED until that fix lands.

P69-02.2d/e (this packet's own RED/GREEN step) adds:
- `GET /api/projects/{project_id}/operations/{operation_id}` route tests
  (subsection e: attachment-resolved status, project-scoping 404s, auth).
- Three `attempt_id`-matching tests for `scan_start`/`scan_resume`/`rescan`
  (subsection d). These three are genuinely RED and stay that way: matching
  the *real* attempt_id `execute_scan`/`resume_scan_run`/`rescan_project_run`
  actually mint requires an `attempt_id: str | None = None` override
  parameter on those three functions (mirroring their existing `run_id`
  pattern) -- that needs `rush/workflows/project_run.py`, outside this
  packet slice's own file scope. See T009's `remaining_blockers` in
  `docs/goals/phase-69-dashboard-tui-contract-remediation/state.yaml`.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

import pytest

from rush.dashboard import state as state_module
from rush.dashboard.server import create_dashboard_server
from rush.tools.review import ReviewTool
from rush.workflows import project_run as project_run_module
from rush.workflows.projects import list_project_artifacts
from tests.test_dashboard_scan_actions import (
    _action,
    _bootstrap_session,
    _get,
    _grant_all,
    _isolate_data_roots,
    _post,
    _register,
    _scans,
    _serve,
    _start_dashboard,
    _wait_until,
)


def _get_operation(
    base_url: str, project_id: str, operation_id: str, *, cookie: str | None
):
    headers = {"Cookie": cookie} if cookie else {}
    resp = _get(
        f"{base_url}/api/projects/{project_id}/operations/{operation_id}",
        headers=headers,
    )
    return resp.status, json.loads(resp.read())


def _start_dashboard_multi(entries: dict[str, Path]):
    """Two-project variant of `_start_dashboard`, for the cross-project
    404-scoping tests below."""
    snapshots = {
        project_id: {
            "schema_version": 1,
            "project_id": project_id,
            "source_identity": str(root),
            "root": str(root),
            "files": [],
            "findings": [],
            "memories": [],
            "agents": [{"id": "agent-1", "name": "Agent One"}],
        }
        for project_id, root in entries.items()
    }
    server, ctx, token = create_dashboard_server(snapshots)
    _serve(server)
    base_url = ctx.launch_origin
    cookie, csrf = _bootstrap_session(base_url, token)
    return server, base_url, cookie, csrf


def _seed_one_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """One real, completed scan run with findings -- the minimal fixture
    `handoff_preview` needs (lighter than `test_dashboard_scan_actions.py`'s
    own `_seed_baseline_and_rescan`, whose baseline+rescan pair neither test
    below needs)."""
    _isolate_data_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(project_run_module, "ALL_TOOLS", [ReviewTool()])
    project_id, root = _register(tmp_path)
    server, base_url, cookie, csrf = _start_dashboard(project_id, root)

    status, body = _action(
        base_url, project_id, cookie, csrf, operation="provision_plan"
    )
    assert status == 200
    plan_id = body["data"]["scan_plan"]["plan_id"]

    status, body = _action(
        base_url,
        project_id,
        cookie,
        csrf,
        operation="scan_start",
        arguments={"plan_id": plan_id},
        grants=_grant_all(),
    )
    assert status == 202
    run_id = body["data"]["run_id"]

    def _done() -> bool:
        status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
        return status == 200 and scans["data"].get("run") is not None

    _wait_until(_done)
    return server, base_url, cookie, csrf, project_id, root, run_id


def test_build_handoff_preview_mode_writes_no_artifact_and_persists_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Targets `build_handoff()` (`project_run.py`) directly through the real
    `handoff_preview` action: assert it writes no `MemoryArtifact` and
    persists no handoff descriptor -- checked against real storage, not just
    the HTTP status."""
    server, base_url, cookie, csrf, project_id, root, run_id = _seed_one_run(
        tmp_path, monkeypatch
    )
    try:
        status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
        assert status == 200
        finding_id = scans["data"]["findings"]["items"][0]["finding_id"]

        db_path = root / ".rush" / "memory.db"

        def _handoff_artifact_count() -> int:
            if not db_path.exists():
                return 0
            with sqlite3.connect(str(db_path)) as conn:
                row = conn.execute(
                    "SELECT COUNT(*) FROM memory_artifacts WHERE family = 'handoff'"
                ).fetchone()
                return row[0]

        before = _handoff_artifact_count()

        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="handoff_preview",
            arguments={
                "run_id": run_id,
                "agent_id": "agent-1",
                "finding_ids": [finding_id],
            },
            grants=_grant_all(),
        )
        assert status == 200
        handoff_id = body["data"]["handoff_id"]

        after = _handoff_artifact_count()
        assert after == before, "handoff_preview must write no MemoryArtifact"

        descriptor_path = root / ".rush" / "handoffs" / f"{handoff_id}.json"
        assert not descriptor_path.exists(), (
            "handoff_preview must persist no handoff descriptor"
        )
    finally:
        server.shutdown()
        server.server_close()


def test_handoff_preview_requires_no_mutation_grant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A genuinely read-only preview must dispatch with no mutation grant at
    all -- only meaningful once the non-persisting split above genuinely
    exists (dropping today's grant requirement without it would make an
    actually-persisting call grant-free)."""
    server, base_url, cookie, csrf, project_id, _root, run_id = _seed_one_run(
        tmp_path, monkeypatch
    )
    try:
        status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
        assert status == 200
        finding_id = scans["data"]["findings"]["items"][0]["finding_id"]

        status, _body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="handoff_preview",
            arguments={
                "run_id": run_id,
                "agent_id": "agent-1",
                "finding_ids": [finding_id],
            },
            grants={},
        )
        assert status == 200
    finally:
        server.shutdown()
        server.server_close()


# --- P69-02.2e: GET /api/projects/{project_id}/operations/{operation_id} ---


def test_operation_status_route_requires_session_auth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    server, base_url, _cookie, _csrf = _start_dashboard(project_id, root)
    try:
        status, _body = _get_operation(base_url, project_id, "unknown-op", cookie=None)
        assert status == 401
    finally:
        server.shutdown()
        server.server_close()


def test_operation_status_route_returns_404_for_unregistered_project_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    server, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        status, _body = _get_operation(
            base_url, "not-a-registered-project", "whatever-op", cookie=cookie
        )
        assert status == 404
    finally:
        server.shutdown()
        server.server_close()


def test_operation_status_route_returns_404_for_unknown_operation_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    server, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        status, _body = _get_operation(
            base_url, project_id, "never-issued-operation-id", cookie=cookie
        )
        assert status == 404
    finally:
        server.shutdown()
        server.server_close()


def test_operation_status_route_returns_404_when_operation_belongs_to_a_different_project_not_its_real_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Register two projects under one server, start a real operation under
    project A, then request A's real operation_id through project B's own
    URL -- must 404, never leak A's actual status through B."""
    _isolate_data_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(project_run_module, "ALL_TOOLS", [ReviewTool()])
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    project_a, _root_a = _register(tmp_path / "a")
    project_b, _root_b = _register(tmp_path / "b")
    server, base_url, cookie, csrf = _start_dashboard_multi(
        {project_a: _root_a, project_b: _root_b}
    )
    try:
        status, body = _action(
            base_url, project_a, cookie, csrf, operation="provision_plan"
        )
        assert status == 200
        plan_id = body["data"]["scan_plan"]["plan_id"]

        status, body = _action(
            base_url,
            project_a,
            cookie,
            csrf,
            operation="scan_start",
            arguments={"plan_id": plan_id},
            grants=_grant_all(),
        )
        assert status == 202
        operation_id = body["data"]["operation_id"]

        status, _body = _get_operation(base_url, project_b, operation_id, cookie=cookie)
        assert status == 404
    finally:
        server.shutdown()
        server.server_close()


def test_operation_status_route_returns_attachment_resolved_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A discarded request that attaches to an already-active scan_start job
    gets its own, distinct operation_id -- polling *that* id must resolve
    through the attachment record to the executing job's own real terminal
    status once it finishes."""
    _isolate_data_roots(tmp_path, monkeypatch)
    started = threading.Event()
    may_finish = threading.Event()

    class _PausingReview:
        name = "review"

        def __call__(self, path: Path) -> dict[str, object]:
            started.set()
            may_finish.wait(timeout=5)
            return {
                "tool": "review",
                "engine": None,
                "engine_version": None,
                "status": "ok",
                "duration_ms": 1,
                "summary": "review: 0 issues",
                "findings": [],
                "raw": None,
            }

    monkeypatch.setattr(project_run_module, "ALL_TOOLS", [_PausingReview()])
    project_id, root = _register(tmp_path)
    server, base_url, cookie, csrf = _start_dashboard(project_id, root)
    try:
        status, body = _action(
            base_url, project_id, cookie, csrf, operation="provision_plan"
        )
        assert status == 200
        plan_id = body["data"]["scan_plan"]["plan_id"]

        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="scan_start",
            arguments={"plan_id": plan_id},
            grants=_grant_all(),
        )
        assert status == 202
        executing_operation_id = body["data"]["operation_id"]
        run_id = body["data"]["run_id"]
        assert started.wait(timeout=5)

        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="scan_start",
            arguments={"plan_id": plan_id},
            grants=_grant_all(),
        )
        assert status == 202
        assert body["data"]["attached_to_existing"] is True
        attached_operation_id = body["data"]["operation_id"]
        assert attached_operation_id != executing_operation_id

        may_finish.set()

        def _attached_is_terminal() -> bool:
            status, body = _get_operation(
                base_url, project_id, attached_operation_id, cookie=cookie
            )
            return status == 200 and body["data"]["status"] == "terminal"

        _wait_until(_attached_is_terminal)

        status, attached_body = _get_operation(
            base_url, project_id, attached_operation_id, cookie=cookie
        )
        assert status == 200
        assert attached_body["data"]["status"] == "terminal"
        assert attached_body["data"]["payload"]["run_id"] == run_id

        status, direct_body = _get_operation(
            base_url, project_id, executing_operation_id, cookie=cookie
        )
        assert status == 200
        assert direct_body["data"] == attached_body["data"]
    finally:
        server.shutdown()
        server.server_close()


def test_operation_status_route_checks_the_executing_operations_project_for_an_attached_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The project-scoping check for an attached operation_id must resolve
    the attachment first and check the *executing* operation's real project
    -- a different, validly-registered project must still 404 for it."""
    _isolate_data_roots(tmp_path, monkeypatch)
    started = threading.Event()
    may_finish = threading.Event()

    class _PausingReview:
        name = "review"

        def __call__(self, path: Path) -> dict[str, object]:
            started.set()
            may_finish.wait(timeout=5)
            return {
                "tool": "review",
                "engine": None,
                "engine_version": None,
                "status": "ok",
                "duration_ms": 1,
                "summary": "review: 0 issues",
                "findings": [],
                "raw": None,
            }

    monkeypatch.setattr(project_run_module, "ALL_TOOLS", [_PausingReview()])
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    project_a, root_a = _register(tmp_path / "a")
    project_b, root_b = _register(tmp_path / "b")
    server, base_url, cookie, csrf = _start_dashboard_multi(
        {project_a: root_a, project_b: root_b}
    )
    try:
        status, body = _action(
            base_url, project_a, cookie, csrf, operation="provision_plan"
        )
        assert status == 200
        plan_id = body["data"]["scan_plan"]["plan_id"]

        status, body = _action(
            base_url,
            project_a,
            cookie,
            csrf,
            operation="scan_start",
            arguments={"plan_id": plan_id},
            grants=_grant_all(),
        )
        assert status == 202
        assert started.wait(timeout=5)

        status, body = _action(
            base_url,
            project_a,
            cookie,
            csrf,
            operation="scan_start",
            arguments={"plan_id": plan_id},
            grants=_grant_all(),
        )
        assert status == 202
        assert body["data"]["attached_to_existing"] is True
        attached_operation_id = body["data"]["operation_id"]

        may_finish.set()

        def _attached_is_terminal() -> bool:
            status, body = _get_operation(
                base_url, project_a, attached_operation_id, cookie=cookie
            )
            return status == 200 and body["data"]["status"] == "terminal"

        _wait_until(_attached_is_terminal)

        status, _body = _get_operation(
            base_url, project_b, attached_operation_id, cookie=cookie
        )
        assert status == 404
    finally:
        server.shutdown()
        server.server_close()


# --- P69-02.2d: attempt_id preallocation, distinct from run_id ------------
#
# All three tests below are genuinely RED and stay that way in this packet
# slice: matching the *real* attempt_id execute_scan/resume_scan_run/
# rescan_project_run actually mint needs an `attempt_id: str | None = None`
# override parameter on those three functions (mirroring their existing
# `run_id` pattern) -- that needs rush/workflows/project_run.py, outside
# this packet slice's own allowed_files. See T009's remaining_blockers.


def test_scan_start_202_response_attempt_id_matches_the_attempt_execute_scan_actually_uses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(project_run_module, "ALL_TOOLS", [ReviewTool()])
    project_id, root = _register(tmp_path)
    server, base_url, cookie, csrf = _start_dashboard(project_id, root)
    try:
        status, body = _action(
            base_url, project_id, cookie, csrf, operation="provision_plan"
        )
        assert status == 200
        plan_id = body["data"]["scan_plan"]["plan_id"]

        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="scan_start",
            arguments={"plan_id": plan_id},
            grants=_grant_all(),
        )
        assert status == 202
        run_id = body["data"]["run_id"]
        response_attempt_id = body["data"].get("attempt_id")

        def _done() -> bool:
            status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
            return status == 200 and scans["data"].get("run") is not None

        _wait_until(_done)

        attempts_dir = root / ".rush" / "runs" / run_id / "attempts"
        attempt_dirs = list(attempts_dir.iterdir())
        assert len(attempt_dirs) == 1
        manifest = json.loads((attempt_dirs[0] / "manifest.json").read_text())
        real_attempt_id = manifest["attempt_id"]

        assert response_attempt_id == real_attempt_id
    finally:
        server.shutdown()
        server.server_close()


def test_scan_resume_202_response_attempt_id_matches_the_attempt_resume_scan_run_actually_uses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, base_url, cookie, csrf, project_id, root, run_id = _seed_one_run(
        tmp_path, monkeypatch
    )
    try:
        attempts_dir = root / ".rush" / "runs" / run_id / "attempts"
        before_attempt_dirs = {p.name for p in attempts_dir.iterdir()}

        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="scan_resume",
            arguments={"run_id": run_id},
            grants=_grant_all(),
        )
        assert status == 202
        response_attempt_id = body["data"].get("attempt_id")

        def _new_manifest_path() -> Path | None:
            new_names = {p.name for p in attempts_dir.iterdir()} - before_attempt_dirs
            if not new_names:
                return None
            candidate = attempts_dir / next(iter(new_names)) / "manifest.json"
            return candidate if candidate.exists() else None

        _wait_until(lambda: _new_manifest_path() is not None)

        manifest = json.loads(_new_manifest_path().read_text())
        real_attempt_id = manifest["attempt_id"]

        assert response_attempt_id == real_attempt_id
    finally:
        server.shutdown()
        server.server_close()


def test_rescan_202_response_attempt_id_matches_the_attempt_rescan_project_run_actually_uses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, base_url, cookie, csrf, project_id, root, baseline_run_id = _seed_one_run(
        tmp_path, monkeypatch
    )
    try:
        runs_dir = root / ".rush" / "runs"
        before_run_ids = {p.name for p in runs_dir.iterdir()}

        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="rescan",
            arguments={"run_id": baseline_run_id},
            grants=_grant_all(),
        )
        assert status == 202
        response_attempt_id = body["data"].get("attempt_id")

        def _new_manifest_path() -> Path | None:
            new_run_ids = {p.name for p in runs_dir.iterdir()} - before_run_ids
            if not new_run_ids:
                return None
            attempts_dir = runs_dir / next(iter(new_run_ids)) / "attempts"
            if not attempts_dir.exists():
                return None
            attempt_dirs = list(attempts_dir.iterdir())
            if not attempt_dirs:
                return None
            candidate = attempt_dirs[0] / "manifest.json"
            return candidate if candidate.exists() else None

        _wait_until(lambda: _new_manifest_path() is not None)

        manifest = json.loads(_new_manifest_path().read_text())
        real_attempt_id = manifest["attempt_id"]

        assert response_attempt_id == real_attempt_id
    finally:
        server.shutdown()
        server.server_close()


# --- P69-02.2n: GET /api/agents, POST /api/agents/actions -------------------


def test_agents_list_route_returns_real_response_not_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    server, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        resp = _get(f"{base_url}/api/agents", headers={"Cookie": cookie})
        assert resp.status == 200
        body = json.loads(resp.read())
        assert "raw" in body["data"]
    finally:
        server.shutdown()
        server.server_close()


def test_agents_actions_route_dispatches_list_and_doctor_not_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    server, base_url, cookie, csrf = _start_dashboard(project_id, root)
    try:
        for action in ("list", "doctor"):
            body_bytes = json.dumps({"action": action}).encode("utf-8")
            resp = _post(
                f"{base_url}/api/agents/actions",
                headers={
                    "Cookie": cookie,
                    "X-Rush-CSRF": csrf,
                    "Origin": base_url,
                    "Content-Type": "application/json",
                },
                body=body_bytes,
            )
            assert resp.status == 200, action

        denied = _post(
            f"{base_url}/api/agents/actions",
            headers={
                "Cookie": cookie,
                "X-Rush-CSRF": csrf,
                "Origin": base_url,
                "Content-Type": "application/json",
            },
            body=json.dumps({"action": "connect", "agent_id": "x"}).encode("utf-8"),
        )
        assert denied.status == 403
    finally:
        server.shutdown()
        server.server_close()


# --- P69-02.2n: GET /api/projects/{id}/artifacts/{artifact_id} -------------


def test_artifact_route_and_artifact_export_action_return_real_content_not_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, base_url, cookie, csrf, project_id, _root, _run_id = _seed_one_run(
        tmp_path, monkeypatch
    )
    try:
        refs = list_project_artifacts(project_id)
        artifact_ref = refs["scan_outputs"][0]["artifact_ref"]

        resp = _get(
            f"{base_url}/api/projects/{project_id}/artifacts/{artifact_ref}",
            headers={"Cookie": cookie},
        )
        assert resp.status == 200
        body = json.loads(resp.read())
        assert body["data"]["found"] is True

        status, action_body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="artifact_export",
            arguments={"artifact_id": artifact_ref},
            grants={"download": True},
        )
        assert status == 200
        assert action_body["data"]["found"] is True

        unknown = _get(
            f"{base_url}/api/projects/{project_id}/artifacts/unknown:ref",
            headers={"Cookie": cookie},
        )
        assert unknown.status == 404
    finally:
        server.shutdown()
        server.server_close()


# --- P69-02.2n: configure, handoff_status, memory_* new actions ------------


def test_configure_action_dispatches_rush_project_configure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    server, base_url, cookie, csrf = _start_dashboard(project_id, root)
    try:
        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="configure",
            arguments={"settings": {"concurrency": 2}},
        )
        assert status == 200
        plan_id = body["data"]["raw"]["plan_id"]

        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="configure",
            arguments={
                "settings": {"concurrency": 2},
                "apply": True,
                "plan_id": plan_id,
                "expected_revision": 1,
            },
            grants=_grant_all(),
        )
        assert status == 200
        assert body["data"]["raw"]["settings"]["concurrency"] == 2
    finally:
        server.shutdown()
        server.server_close()


def test_memory_propose_action_dispatches_write_and_refreshes_map_memory_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    server, base_url, cookie, csrf = _start_dashboard(project_id, root)
    try:
        resp = _get(
            f"{base_url}/api/projects/{project_id}/snapshot", headers={"Cookie": cookie}
        )
        before = json.loads(resp.read())["data"]["memories"]

        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="memory_propose",
            arguments={
                "subject": "domain_knowledge",
                "content": {"note": "proposed fact"},
                "source": "test-agent",
            },
            grants={"cache_write": True},
        )
        assert status == 200
        assert body["data"]["status"] == "ok"
        artifact = body["data"]["raw"]
        artifact_id = artifact["id"]

        resp = _get(
            f"{base_url}/api/projects/{project_id}/snapshot", headers={"Cookie": cookie}
        )
        after = json.loads(resp.read())["data"]["memories"]
        assert len(after) == len(before) + 1

        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="memory_query",
            arguments={
                "mode": "list",
                "subject": "domain_knowledge",
                "session_allowlist": ["test-agent"],
            },
        )
        assert status == 200
        assert body["data"]["status"] == "ok"

        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="memory_expand",
            arguments={
                "id": artifact_id,
                "version": artifact["artifact_version"],
                "session_allowlist": ["test-agent"],
            },
        )
        assert status == 200
        assert body["data"]["status"] == "ok"
    finally:
        server.shutdown()
        server.server_close()


def test_memory_maintain_action_dispatches_maintain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    server, base_url, cookie, csrf = _start_dashboard(project_id, root)
    try:
        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="memory_maintain",
            arguments={"task": "staleness_sweep"},
            grants={"cache_write": True},
        )
        assert status == 200
        assert body["data"]["status"] in ("ok", "warn")
    finally:
        server.shutdown()
        server.server_close()


# --- P69-02.2n: handoff_send/provision_apply 202 async lifecycle -----------


def test_handoff_send_and_provisioning_return_202_with_run_id_not_200(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, base_url, cookie, csrf, project_id, _root, run_id = _seed_one_run(
        tmp_path, monkeypatch
    )
    try:
        status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
        assert status == 200
        finding_id = scans["data"]["findings"]["items"][0]["finding_id"]

        status, preview_body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="handoff_preview",
            arguments={
                "run_id": run_id,
                "agent_id": "agent-1",
                "finding_ids": [finding_id],
            },
        )
        assert status == 200
        content_hash = preview_body["data"]["handoff_id"]

        resp = _get(
            f"{base_url}/api/projects/{project_id}/snapshot", headers={"Cookie": cookie}
        )
        memories_before = json.loads(resp.read())["data"]["memories"]

        status, send_body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="handoff_send",
            arguments={
                "run_id": run_id,
                "agent_id": "agent-1",
                "finding_ids": [finding_id],
                "handoff_id": content_hash,
            },
            grants=_grant_all(),
        )
        assert status == 202
        operation_id = send_body["data"]["operation_id"]
        assert send_body["data"]["run_id"] == run_id

        def _terminal() -> bool:
            op_status, op_body = _get_operation(
                base_url, project_id, operation_id, cookie=cookie
            )
            return op_status == 200 and op_body["data"]["status"] == "terminal"

        _wait_until(_terminal)
        _op_status, op_body = _get_operation(
            base_url, project_id, operation_id, cookie=cookie
        )
        payload = op_body["data"]["payload"]
        assert payload["status"] == "success"
        real_handoff_id = payload["handoff_id"]
        assert real_handoff_id != content_hash

        status, status_body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="handoff_status",
            arguments={"handoff_id": real_handoff_id},
        )
        assert status == 200
        assert status_body["data"]["state"] == "delivered"

        resp = _get(
            f"{base_url}/api/projects/{project_id}/snapshot", headers={"Cookie": cookie}
        )
        memories_after = json.loads(resp.read())["data"]["memories"]
        assert len(memories_after) == len(memories_before) + 1
    finally:
        server.shutdown()
        server.server_close()


def test_provision_apply_returns_202_with_run_id_not_200(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    server, base_url, cookie, csrf = _start_dashboard(project_id, root)
    try:
        status, plan_body = _action(
            base_url, project_id, cookie, csrf, operation="provision_plan"
        )
        assert status == 200
        plan_id = plan_body["data"]["readiness"]["plan_id"]
        status, apply_body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="provision_apply",
            arguments={"plan_id": plan_id},
            grants=_grant_all(),
        )
        assert status == 202
        assert "operation_id" in apply_body["data"]
        assert "run_id" in apply_body["data"]

        def _terminal() -> bool:
            op_status, op_body = _get_operation(
                base_url, project_id, apply_body["data"]["operation_id"], cookie=cookie
            )
            return op_status == 200 and op_body["data"]["status"] == "terminal"

        _wait_until(_terminal)
    finally:
        server.shutdown()
        server.server_close()


def test_handoff_send_rejects_tampered_or_stale_preview_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, base_url, cookie, csrf, project_id, _root, run_id = _seed_one_run(
        tmp_path, monkeypatch
    )
    try:
        status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
        assert status == 200
        finding_id = scans["data"]["findings"]["items"][0]["finding_id"]

        status, _send_body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="handoff_send",
            arguments={
                "run_id": run_id,
                "agent_id": "agent-1",
                "finding_ids": [finding_id],
                "handoff_id": "not-a-real-preview-hash",
            },
            grants=_grant_all(),
        )
        assert status == 409
    finally:
        server.shutdown()
        server.server_close()


# --- P69-03p: GET /api/projects/{id}/events -- durable /events route + real
# backing store (moved here from P69-02.1: this packet is the one that
# actually builds the durable log `record_status_transition` writes into,
# per Phase 66 §3.6's unchanged numeric contract). ---------------------------


def _start_dashboard_with_ctx(project_id: str, root: Path):
    """`_start_dashboard`'s counterpart that also returns `ctx`, needed here
    to seed events directly through `ctx.mutations` (real, but far faster
    than driving thousands of real scan dispatches through HTTP)."""
    snapshot = {
        "schema_version": 1,
        "project_id": project_id,
        "source_identity": str(root),
        "root": str(root),
        "files": [],
        "findings": [],
        "memories": [],
        "agents": [],
    }
    server, ctx, token = create_dashboard_server({project_id: snapshot})
    _serve(server)
    base_url = ctx.launch_origin
    cookie, csrf = _bootstrap_session(base_url, token)
    return server, ctx, base_url, cookie, csrf


def _events(base_url: str, project_id: str, cookie: str, **query: str):
    from urllib.parse import urlencode

    url = f"{base_url}/api/projects/{project_id}/events"
    if query:
        url += f"?{urlencode(query)}"
    resp = _get(url, headers={"Cookie": cookie})
    return resp.status, json.loads(resp.read())


def test_events_route_returns_real_response_not_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    server, _ctx, base_url, cookie, _csrf = _start_dashboard_with_ctx(project_id, root)
    try:
        status, body = _events(base_url, project_id, cookie)
        assert status == 200
        assert body["data"]["events"] == []
        assert body["data"]["after"] == 0
        assert body["data"]["has_more"] is False
    finally:
        server.shutdown()
        server.server_close()


def test_events_response_honors_100_per_page_and_2000_per_run_retention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Phase 66 §3.6's exact numeric contract: at most 100 events/response,
    2,000 retained per project before the oldest are pruned. Uses the real
    default retention (never monkeypatched) so this is the one test that
    actually proves the literal "2,000" number, not just the rejection
    mechanism (covered separately, cheaply, below)."""
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    server, ctx, base_url, cookie, _csrf = _start_dashboard_with_ctx(project_id, root)
    try:
        operation_id = ctx.mutations.reserve(
            project_id, "req-events", "hash"
        ).operation_id
        for i in range(2001):
            ctx.mutations.record_status_transition(operation_id, "running", {"i": i})

        seen: list[int] = []
        page_sizes: list[int] = []
        after = 1  # oldest retained sequence is 2001 - 2000 + 1 = 2
        while True:
            status, body = _events(base_url, project_id, cookie, after=str(after))
            assert status == 200
            events = body["data"]["events"]
            page_sizes.append(len(events))
            seen.extend(e["sequence"] for e in events)
            after = body["data"]["after"]
            if not body["data"]["has_more"]:
                break

        assert all(size <= 100 for size in page_sizes)
        assert len(page_sizes) >= 2, "2,000 retained events must page, not 1 giant page"
        assert len(seen) == 2000
        assert min(seen) == 2
        assert max(seen) == 2001

        # The pruned event (sequence 1) is no longer reachable at all.
        status, body = _events(base_url, project_id, cookie, after="0")
        assert status == 409
    finally:
        server.shutdown()
        server.server_close()


def test_events_stale_cursor_returns_409_event_cursor_expired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rejection mechanism itself, proven cheaply against a monkeypatched
    small retention window -- the exact "2,000" number is proven once, for
    real, in the test above."""
    monkeypatch.setattr(state_module, "_EVENT_RETENTION_PER_PROJECT", 5)
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    server, ctx, base_url, cookie, _csrf = _start_dashboard_with_ctx(project_id, root)
    try:
        operation_id = ctx.mutations.reserve(
            project_id, "req-events", "hash"
        ).operation_id
        for i in range(8):
            ctx.mutations.record_status_transition(operation_id, "running", {"i": i})

        status, body = _events(base_url, project_id, cookie, after="0")
        assert status == 409
        assert body["error"]["code"] == "event_cursor_expired"
    finally:
        server.shutdown()
        server.server_close()


def test_events_gap_beyond_retention_requires_snapshot_reload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(state_module, "_EVENT_RETENTION_PER_PROJECT", 5)
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    server, ctx, base_url, cookie, _csrf = _start_dashboard_with_ctx(project_id, root)
    try:
        operation_id = ctx.mutations.reserve(
            project_id, "req-events", "hash"
        ).operation_id
        for i in range(8):
            ctx.mutations.record_status_transition(operation_id, "running", {"i": i})

        status, body = _events(base_url, project_id, cookie, after="0")
        assert status == 409
        assert body["error"]["details"].get("recovery") == "reload_snapshot"
    finally:
        server.shutdown()
        server.server_close()
