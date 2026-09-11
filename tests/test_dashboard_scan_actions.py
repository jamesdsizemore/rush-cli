"""Tests for Phase 66 P66-04: full scan triage and repair controls in the
browser dashboard (F38).

Drives the real dashboard HTTP action/snapshot boundary (`server.py`)
against a real registered project and real scan execution -- the same
`rush.workflows.project_run`/`rush.tools.setup_wizard` shared operations the
CLI uses -- with a small, deterministic tool set (`ReviewTool` plus a
name-reusing stub, mirroring `tests/test_full_project_scan.py`'s own
`_BrokenTypecheck` pattern) so results are fast and reproducible without any
external engine binary or network access.

Seed: a baseline scan with two real findings from `review` (one that will
be fixed, one that persists) and one from a stubbed `typecheck` engine.
Before rescanning, the fixed finding's function gets a docstring, a new
function introduces a `new` finding, and `typecheck` is monkeypatched to
fail -- so the rescan comparison yields exactly the packet's own seed: one
`resolved` (fixed), one `persisting`, one `new`, and one `unverified`
finding (the failed engine can never resolve its own prior finding).
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

import pytest

from rush.dashboard.server import create_dashboard_server
from rush.setup import provision as provision_module
from rush.tools.review import ReviewTool
from rush.workflows import project_run as project_run_module
from rush.workflows import projects as projects_module
from rush.workflows.projects import register_project

# --- shared HTTP helpers (mirrors tests/test_dashboard_http_contract.py) ---


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


def _action(
    base_url: str,
    project_id: str,
    cookie: str,
    csrf: str,
    *,
    operation: str,
    arguments: dict[str, Any] | None = None,
    grants: dict[str, Any] | None = None,
    request_id: str | None = None,
):
    body = json.dumps(
        {
            "schema_version": 1,
            "operation": operation,
            "arguments": arguments or {},
            "grants": grants or {},
            "request_id": request_id or str(uuid.uuid4()),
        }
    ).encode("utf-8")
    resp = _post(
        f"{base_url}/api/projects/{project_id}/actions",
        headers={
            "Cookie": cookie,
            "X-Rush-CSRF": csrf,
            "Origin": base_url,
            "Content-Type": "application/json",
        },
        body=body,
    )
    return resp.status, json.loads(resp.read())


def _scans(base_url: str, project_id: str, cookie: str, **query: str):
    from urllib.parse import urlencode

    qs = urlencode({"section": "scans", **query})
    resp = _get(
        f"{base_url}/api/projects/{project_id}/snapshot?{qs}",
        headers={"Cookie": cookie},
    )
    return resp.status, json.loads(resp.read())


def _wait_until(predicate, *, timeout: float = 5.0, interval: float = 0.02) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval)
    assert predicate(), "condition never became true within timeout"


# --- fixture project (real registry, no network) ----------------------------


def _isolate_data_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_root = tmp_path / "rush-data"
    monkeypatch.setattr(projects_module, "default_data_root", lambda: data_root)
    monkeypatch.setattr(provision_module, "default_data_root", lambda: data_root)


def _register(tmp_path: Path) -> tuple[str, Path]:
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text(
        "def stays_broken():\n    pass\n\n\ndef to_be_fixed():\n    pass\n",
        encoding="utf-8",
    )
    record = register_project(root)
    return record.project_id, root


def _start_dashboard(project_id: str, root: Path):
    snapshot = {
        "schema_version": 1,
        "project_id": project_id,
        "source_identity": str(root),
        "root": str(root),
        "files": [],
        "findings": [],
        "memories": [],
        "agents": [{"id": "agent-1", "name": "Agent One"}],
    }
    server, ctx, token = create_dashboard_server({project_id: snapshot})
    _serve(server)
    base_url = ctx.launch_origin
    cookie, csrf = _bootstrap_session(base_url, token)
    return server, base_url, cookie, csrf


class _StubTypecheck:
    """Reuses the real `typecheck` catalog name (see `_BrokenTypecheck` in
    tests/test_full_project_scan.py) so classification matches the real
    tool; `mode='ok'` returns one seeded finding, `mode='broken'` raises so
    its prior finding becomes `unverified` on rescan -- a failed engine can
    never make a finding `resolved`."""

    name = "typecheck"

    def __init__(self, mode: str) -> None:
        self._mode = mode

    def __call__(self, path: Path) -> dict[str, object]:
        if self._mode == "broken":
            raise RuntimeError("typecheck engine unavailable")
        return {
            "tool": "typecheck",
            "engine": None,
            "engine_version": None,
            "status": "ok",
            "duration_ms": 1,
            "summary": "typecheck: 1 issue",
            "findings": [
                {
                    "path": "app.py",
                    "line": 1,
                    "column": 0,
                    "rule": "seeded-typecheck-rule",
                    "severity": "warn",
                    "message": "seeded typecheck issue",
                }
            ],
            "raw": None,
        }


def _grant_all() -> dict[str, bool]:
    return {"cache_write": True, "artifact_write": True}


# --- P66-04.1 RED ------------------------------------------------------------


def test_provision_then_scan_uses_reviewed_plan(
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
        reviewed_plan_id = body["data"]["scan_plan"]["plan_id"]
        assert body["data"]["readiness"]["provision"]["plan_only"] is True

        # An unreviewed/unknown plan_id is refused -- scan_start only ever
        # runs a plan that was actually staged by a review step.
        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="scan_start",
            arguments={"plan_id": "not-a-real-plan"},
            grants=_grant_all(),
        )
        assert status == 409

        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="scan_start",
            arguments={"plan_id": reviewed_plan_id},
            grants=_grant_all(),
        )
        assert status == 202
        assert body["data"]["plan_id"] == reviewed_plan_id
        run_id = body["data"]["run_id"]

        def _run_finished() -> bool:
            status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
            return status == 200 and scans["data"].get("run") is not None

        _wait_until(_run_finished)
        status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
        assert scans["data"]["run"]["plan_id"] == reviewed_plan_id
        # The real, un-curated catalog always includes engine-only entries
        # with no adapter (e.g. semgrep) that schedule as `unavailable`, so
        # a real full scan's coverage is honestly `incomplete` -- only the
        # `review` candidate itself must have actually executed.
        assert scans["data"]["run"]["run_state"] in ("completed", "incomplete")
        assert scans["data"]["run"]["executed_count"] >= 1
        assert scans["data"]["findings"]["total"] == 2
    finally:
        server.shutdown()
        server.server_close()


def _seed_baseline_and_rescan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Any, str, str, str, str, str, str]:
    """Returns (server, base_url, cookie, csrf, project_id, baseline_run_id,
    current_run_id) for the shared fixed/persisting/new/unverified seed."""
    _isolate_data_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(
        project_run_module, "ALL_TOOLS", [ReviewTool(), _StubTypecheck("ok")]
    )
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
    baseline_run_id = body["data"]["run_id"]

    def _baseline_done() -> bool:
        status, scans = _scans(base_url, project_id, cookie, run_id=baseline_run_id)
        return status == 200 and scans["data"].get("run") is not None

    _wait_until(_baseline_done)
    status, scans = _scans(base_url, project_id, cookie, run_id=baseline_run_id)
    assert scans["data"]["findings"]["total"] == 3

    # Fix one finding, introduce a new one, leave the persisting one alone.
    (root / "app.py").write_text(
        "def stays_broken():\n"
        "    pass\n"
        "\n"
        "\n"
        "def to_be_fixed():\n"
        '    """Now documented."""\n'
        "\n"
        "\n"
        "def new_issue():\n"
        "    pass\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        project_run_module, "ALL_TOOLS", [ReviewTool(), _StubTypecheck("broken")]
    )

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

    def _rescan_done() -> bool:
        status, scans = _scans(base_url, project_id, cookie)
        return (
            status == 200
            and scans["data"].get("run") is not None
            and scans["data"]["run"]["run_id"] != baseline_run_id
        )

    _wait_until(_rescan_done)
    status, scans = _scans(base_url, project_id, cookie)
    current_run_id = scans["data"]["run"]["run_id"]
    return server, base_url, cookie, csrf, project_id, baseline_run_id, current_run_id


def test_missing_engine_remains_visible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (
        server,
        base_url,
        cookie,
        _csrf,
        project_id,
        baseline_run_id,
        current_run_id,
    ) = _seed_baseline_and_rescan(tmp_path, monkeypatch)
    try:
        status, scans = _scans(
            base_url,
            project_id,
            cookie,
            run_id=current_run_id,
            compare_with=baseline_run_id,
        )
        assert status == 200
        items = scans["data"]["findings"]["items"]
        by_rule = {item.get("rule"): item for item in items}
        seeded = by_rule["seeded-typecheck-rule"]
        # The engine that produced this finding failed in the current run --
        # it must never read as resolved, and it must still be visible.
        assert seeded["status"] == "unverified"
        assert seeded["status"] != "resolved"
        assert seeded["path"] == "app.py"
    finally:
        server.shutdown()
        server.server_close()


def test_handoff_and_rescan_keep_evidence_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (
        server,
        base_url,
        cookie,
        csrf,
        project_id,
        baseline_run_id,
        current_run_id,
    ) = _seed_baseline_and_rescan(tmp_path, monkeypatch)
    try:
        status, scans = _scans(
            base_url,
            project_id,
            cookie,
            run_id=current_run_id,
            compare_with=baseline_run_id,
        )
        assert status == 200
        items = scans["data"]["findings"]["items"]
        by_status: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            by_status.setdefault(item["status"], []).append(item)

        assert len(by_status.get("resolved", [])) == 1
        assert len(by_status.get("persisting", [])) == 1
        assert len(by_status.get("new", [])) == 1
        assert len(by_status.get("unverified", [])) == 1

        persisting = by_status["persisting"][0]
        assert persisting["provenance"].startswith("review/")
        new_finding = by_status["new"][0]
        assert new_finding["provenance"].startswith("review/")
        resolved = by_status["resolved"][0]
        assert resolved["provenance"].startswith("review/")
        unverified = by_status["unverified"][0]
        assert unverified["provenance"].startswith("typecheck/")

        # Grouping never loses or renames a finding's original identity.
        status, grouped = _scans(
            base_url,
            project_id,
            cookie,
            run_id=current_run_id,
            compare_with=baseline_run_id,
            group_by="severity",
        )
        assert status == 200
        grouped_ids = {
            fid for ids in grouped["data"]["findings"]["groups"].values() for fid in ids
        }
        assert grouped_ids == {item["finding_id"] for item in items}

        # Connected-agent repair: hand off the still-active findings.
        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="handoff_preview",
            arguments={
                "run_id": current_run_id,
                "agent_id": "agent-1",
                "finding_ids": [persisting["finding_id"], new_finding["finding_id"]],
            },
            grants=_grant_all(),
        )
        assert status == 200
        assert body["data"]["state"] == "prepared"
        handoff_id = body["data"]["handoff_id"]
        session_capability = body["data"]["session_capability"]

        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="handoff_send",
            arguments={
                "handoff_id": handoff_id,
                "session_capability": session_capability,
            },
            grants=_grant_all(),
        )
        assert status == 200
        assert body["data"]["state"] == "delivered"
        # Read-back never reveals the one-time capability again.
        assert "session_capability" not in body["data"]
    finally:
        server.shutdown()
        server.server_close()


def test_cancel_retains_partial_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
                "summary": "review: 1 issue",
                "findings": [
                    {
                        "path": "app.py",
                        "line": 1,
                        "column": 0,
                        "rule": "seeded-review-rule",
                        "severity": "warn",
                        "message": "seeded review issue",
                    }
                ],
                "raw": None,
            }

    class _NeverRuns:
        name = "typecheck"

        def __call__(self, path: Path) -> dict[str, object]:
            raise AssertionError("typecheck must never run after cancellation")

    monkeypatch.setattr(
        project_run_module, "ALL_TOOLS", [_PausingReview(), _NeverRuns()]
    )
    project_id, root = _register(tmp_path)
    server, base_url, cookie, csrf = _start_dashboard(project_id, root)
    try:
        status, body = _action(
            base_url, project_id, cookie, csrf, operation="provision_plan"
        )
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

        assert started.wait(timeout=5)
        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="scan_cancel",
            arguments={"run_id": run_id},
            grants={"cache_write": True},
        )
        assert status == 202
        may_finish.set()

        def _run_finished() -> bool:
            status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
            return status == 200 and scans["data"].get("run") is not None

        _wait_until(_run_finished)
        status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
        assert scans["data"]["run"]["run_state"] == "cancelled"
        # review already finished before cancellation landed -- its finding
        # is retained as real partial evidence.
        items = scans["data"]["findings"]["items"]
        assert len(items) == 1
        assert items[0]["rule"] == "seeded-review-rule"
        assert scans["data"]["active_run_id"] is None
    finally:
        server.shutdown()
        server.server_close()


def test_refresh_reconnect_attaches_to_existing_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second scan_start call for the same project while the first job is
    still running -- e.g. a browser tab refreshing/reconnecting -- must
    attach to the already-running job (same run_id, attached_to_existing is
    True) instead of spawning a second scan."""
    _isolate_data_roots(tmp_path, monkeypatch)
    started = threading.Event()
    may_finish = threading.Event()
    call_count = 0
    call_lock = threading.Lock()

    class _PausingCountingReview:
        name = "review"

        def __call__(self, path: Path) -> dict[str, object]:
            nonlocal call_count
            with call_lock:
                call_count += 1
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

    monkeypatch.setattr(project_run_module, "ALL_TOOLS", [_PausingCountingReview()])
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
        first_run_id = body["data"]["run_id"]
        assert body["data"]["attached_to_existing"] is False

        assert started.wait(timeout=5)

        # Simulate a browser refresh/reconnect: scan_start called again for
        # the same project while the first job is still running.
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
        assert body["data"]["run_id"] == first_run_id
        assert body["data"]["attached_to_existing"] is True

        may_finish.set()

        def _run_finished() -> bool:
            status, scans = _scans(base_url, project_id, cookie, run_id=first_run_id)
            return status == 200 and scans["data"].get("run") is not None

        _wait_until(_run_finished)
        # Exactly one underlying tool execution -- the refresh/reconnect
        # call never spawned a second scan job.
        assert call_count == 1
    finally:
        server.shutdown()
        server.server_close()


def test_concurrent_scan_start_calls_resolve_to_one_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Several requests calling scan_start simultaneously for the same
    project -- a real multi-request race, not a single-threaded fake --
    must still resolve to exactly one underlying tool execution and one
    run_id: exactly one request wins (attached_to_existing=False), the
    rest attach to it."""
    _isolate_data_roots(tmp_path, monkeypatch)
    may_finish = threading.Event()
    call_count = 0
    call_lock = threading.Lock()

    class _PausingCountingReview:
        name = "review"

        def __call__(self, path: Path) -> dict[str, object]:
            nonlocal call_count
            with call_lock:
                call_count += 1
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

    monkeypatch.setattr(project_run_module, "ALL_TOOLS", [_PausingCountingReview()])
    project_id, root = _register(tmp_path)
    server, base_url, cookie, csrf = _start_dashboard(project_id, root)
    try:
        status, body = _action(
            base_url, project_id, cookie, csrf, operation="provision_plan"
        )
        assert status == 200
        plan_id = body["data"]["scan_plan"]["plan_id"]

        concurrency = 8
        results: list[tuple[int, dict[str, Any]] | None] = [None] * concurrency

        def _fire(index: int) -> None:
            results[index] = _action(
                base_url,
                project_id,
                cookie,
                csrf,
                operation="scan_start",
                arguments={"plan_id": plan_id},
                grants=_grant_all(),
            )

        threads = [
            threading.Thread(target=_fire, args=(i,)) for i in range(concurrency)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)

        may_finish.set()

        assert all(result is not None for result in results)
        statuses_and_bodies = [result for result in results if result is not None]
        assert all(status == 202 for status, _ in statuses_and_bodies)
        run_ids = {body["data"]["run_id"] for _, body in statuses_and_bodies}
        assert len(run_ids) == 1
        attached_flags = [
            body["data"]["attached_to_existing"] for _, body in statuses_and_bodies
        ]
        assert attached_flags.count(False) == 1
        assert attached_flags.count(True) == concurrency - 1

        run_id = next(iter(run_ids))

        def _run_finished() -> bool:
            status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
            return status == 200 and scans["data"].get("run") is not None

        _wait_until(_run_finished)
        # No matter how many requests raced, exactly one thread ever ran
        # the underlying tool.
        assert call_count == 1
    finally:
        server.shutdown()
        server.server_close()
