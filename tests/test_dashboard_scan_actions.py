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

from rush.dashboard.server import create_dashboard_server, dispatch_control_check_suite
from rush.setup import provision as provision_module
from rush.tools.review import ReviewTool
from rush.workflows import project_run as project_run_module
from rush.workflows import projects as projects_module
from rush.workflows import suites as suites_module
from rush.workflows.projects import register_project

pytestmark = pytest.mark.usefixtures("hermetic_engine_path")

# --- shared HTTP helpers (mirrors tests/test_dashboard_http_contract.py) ---


def _serve(server) -> threading.Thread:
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    )
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
    expected: dict[str, Any] | None = None,
):
    body = json.dumps(
        {
            "schema_version": 1,
            "operation": operation,
            "arguments": arguments or {},
            "grants": grants or {},
            "expected": expected or {},
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


def _wait_until(predicate, *, timeout: float = 60.0, interval: float = 0.02) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval)
    assert predicate(), "condition never became true within timeout"


def _wait_operation_terminal(
    base_url: str, project_id: str, cookie: str, operation_id: str
) -> None:
    """Wait for the operation's own terminal status. A run becomes visible
    in `section=scans` before its admission row is released and its result
    published (both land with the terminal transition), so an action fired
    on "run visible" alone races the still-held admission."""

    def _terminal() -> bool:
        resp = _get(
            f"{base_url}/api/projects/{project_id}/operations/{operation_id}",
            headers={"Cookie": cookie},
        )
        return json.loads(resp.read())["data"]["status"] == "terminal"

    _wait_until(_terminal)


# --- fixture project (real registry, no network) ----------------------------


def _isolate_data_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate the registry/data roots. Scan engines are isolated by this
    module's `hermetic_engine_path` mark (conftest.py): engine rows resolve
    only the engines pinned in this venv instead of whatever the host has on
    PATH (aislop, detect-secrets, osv-scanner, a local LLM, ...) -- the real
    engine route and catalog rows, without host-dependent scan duration,
    findings and cancel timing."""
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
        # Engine rows resolve only from this venv (the module's hermetic
        # PATH), so no host engine (detect-secrets, a local LLM, ...) adds
        # findings, and M17's CACHEDIR.TAG exclusion keeps an installed
        # entropy scanner off that fixed signature string: the total is just
        # the review tool's 2 seeded findings.
        assert scans["data"]["findings"]["total"] == 2
    finally:
        server.shutdown()
        server.server_close()


def _seed_baseline_and_rescan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Any, str, str, str, str, str, str, str]:
    """Returns (server, base_url, cookie, csrf, project_id, baseline_run_id,
    current_run_id, current_attempt_id) for the shared
    fixed/persisting/new/unverified seed."""
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
    baseline_operation_id = body["data"]["operation_id"]

    def _baseline_done() -> bool:
        status, scans = _scans(base_url, project_id, cookie, run_id=baseline_run_id)
        return status == 200 and scans["data"].get("run") is not None

    _wait_until(_baseline_done)
    _wait_operation_terminal(base_url, project_id, cookie, baseline_operation_id)
    status, scans = _scans(base_url, project_id, cookie, run_id=baseline_run_id)
    # Engine rows resolve only from this venv (the module's hermetic PATH),
    # and M17's CACHEDIR.TAG exclusion keeps an installed entropy scanner off
    # that fixed signature string, so the total is just the 3 seeded
    # findings.
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
    current_attempt_id = project_run_module.latest_attempt_id(
        project_id, current_run_id
    )
    return (
        server,
        base_url,
        cookie,
        csrf,
        project_id,
        baseline_run_id,
        current_run_id,
        current_attempt_id,
    )


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
        _current_attempt_id,
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
        # M15: results are now remapped to the real (logical) project path
        # rather than the bare relative string the stub tool returned.
        assert Path(seeded["path"]).name == "app.py"
    finally:
        server.shutdown()
        server.server_close()


def test_handoff_preview_hash_changes_when_packet_content_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S06: the preview hash binds the actual rendered packet, not just the
    top-level envelope fields -- selecting a different subset of findings
    (different packet content) must change the hash even when run/attempt
    are identical."""
    _isolate_data_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(
        project_run_module, "ALL_TOOLS", [ReviewTool(), _StubTypecheck("ok")]
    )
    project_id, root = _register(tmp_path)
    server, base_url, cookie, csrf = _start_dashboard(project_id, root)
    try:
        _status, body = _action(
            base_url, project_id, cookie, csrf, operation="provision_plan"
        )
        plan_id = body["data"]["scan_plan"]["plan_id"]
        _status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="scan_start",
            arguments={"plan_id": plan_id},
            grants=_grant_all(),
        )
        run_id = body["data"]["run_id"]

        def _done() -> bool:
            status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
            return status == 200 and scans["data"].get("run") is not None

        _wait_until(_done)
        _status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
        finding_ids = [f["finding_id"] for f in scans["data"]["findings"]["items"]]
        assert len(finding_ids) >= 2
        attempt_id = project_run_module.latest_attempt_id(project_id, run_id)

        _status, preview_all = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="handoff_preview",
            arguments={
                "run_id": run_id,
                "attempt_id": attempt_id,
                "agent_id": "agent-1",
                "finding_ids": finding_ids,
            },
        )
        _status, preview_one = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="handoff_preview",
            arguments={
                "run_id": run_id,
                "attempt_id": attempt_id,
                "agent_id": "agent-1",
                "finding_ids": finding_ids[:1],
            },
        )
        assert preview_all["data"]["handoff_id"] != preview_one["data"]["handoff_id"]
    finally:
        server.shutdown()
        server.server_close()


def test_handoff_send_returns_terminal_conflict_on_envelope_mismatch_with_zero_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S07: the accept-time hash check can pass and 202 can already be sent,
    yet the envelope can still go stale before the worker's real effects run
    -- the independent, second check from inside the worker must catch that
    and commit zero effects (no artifact/session/delivery), never silently
    send the accepted-but-now-stale packet."""
    _isolate_data_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(project_run_module, "ALL_TOOLS", [ReviewTool()])
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
        run_id = body["data"]["run_id"]

        def _done() -> bool:
            status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
            return status == 200 and scans["data"].get("run") is not None

        _wait_until(_done)
        status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
        finding_id = scans["data"]["findings"]["items"][0]["finding_id"]
        attempt_id = project_run_module.latest_attempt_id(project_id, run_id)

        status, preview_body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="handoff_preview",
            arguments={
                "run_id": run_id,
                "attempt_id": attempt_id,
                "agent_id": "agent-1",
                "finding_ids": [finding_id],
            },
        )
        content_hash = preview_body["data"]["handoff_id"]

        db_path = root / ".rush" / "memory.db"

        def _handoff_artifact_count() -> int:
            if not db_path.exists():
                return 0
            import sqlite3

            with sqlite3.connect(str(db_path)) as conn:
                return conn.execute(
                    "SELECT COUNT(*) FROM memory_artifacts WHERE family = 'handoff'"
                ).fetchone()[0]

        before = _handoff_artifact_count()

        import rush.dashboard.server as server_module

        real_build_handoff = server_module.build_handoff
        calls = {"n": 0}

        def _flaky_build_handoff(*args: Any, **kwargs: Any) -> Any:
            calls["n"] += 1
            handoff = real_build_handoff(*args, **kwargs)
            if calls["n"] == 1:
                return handoff
            from dataclasses import replace

            return replace(handoff, packet={**handoff.packet, "tampered": True})

        monkeypatch.setattr(server_module, "build_handoff", _flaky_build_handoff)

        status, send_body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="handoff_send",
            arguments={
                "run_id": run_id,
                "attempt_id": attempt_id,
                "agent_id": "agent-1",
                "finding_ids": [finding_id],
                "handoff_id": content_hash,
            },
            grants=_grant_all(),
        )
        assert status == 202
        operation_id = send_body["data"]["operation_id"]

        def _terminal() -> bool:
            resp = _get(
                f"{base_url}/api/projects/{project_id}/operations/{operation_id}",
                headers={"Cookie": cookie},
            )
            return json.loads(resp.read())["data"]["status"] == "terminal"

        _wait_until(_terminal)
        resp = _get(
            f"{base_url}/api/projects/{project_id}/operations/{operation_id}",
            headers={"Cookie": cookie},
        )
        outcome = json.loads(resp.read())["data"]["payload"]
        assert outcome["status"] == "conflict"
        assert outcome["code"] == "stale_expected_identity"
        after = _handoff_artifact_count()
        assert after == before, "a stale-at-execution envelope must commit no effects"
    finally:
        server.shutdown()
        server.server_close()


def test_handoff_preview_hash_changes_when_evidence_artifact_version_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S06 Fix item 1/Regression item 4: each attempt is one immutable
    evidence snapshot -- a preview pinned to a stale attempt_id after a
    newer attempt exists for the same run/finding/agent selection must
    produce a different hash than a preview built against the newer
    attempt, and the older evidence version must stay independently
    loadable, never silently substituted by the newer one."""
    _isolate_data_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(project_run_module, "ALL_TOOLS", [ReviewTool()])
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
        run_id = body["data"]["run_id"]
        operation_id = body["data"]["operation_id"]

        def _done() -> bool:
            status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
            return status == 200 and scans["data"].get("run") is not None

        _wait_until(_done)
        _wait_operation_terminal(base_url, project_id, cookie, operation_id)
        status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
        finding_id = scans["data"]["findings"]["items"][0]["finding_id"]
        attempt_id_v1 = project_run_module.latest_attempt_id(project_id, run_id)

        status, preview_v1 = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="handoff_preview",
            arguments={
                "run_id": run_id,
                "attempt_id": attempt_id_v1,
                "agent_id": "agent-1",
                "finding_ids": [finding_id],
            },
        )
        assert status == 200
        hash_v1 = preview_v1["data"]["handoff_id"]

        # A resume with no source change mints a new evidence version
        # (attempt) for the identical run/finding without invalidating the
        # older one.
        status, resume_body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="scan_resume",
            arguments={"run_id": run_id},
            grants=_grant_all(),
        )
        assert status == 202
        resume_operation_id = resume_body["data"]["operation_id"]

        def _resume_terminal() -> bool:
            resp = _get(
                f"{base_url}/api/projects/{project_id}/operations/"
                f"{resume_operation_id}",
                headers={"Cookie": cookie},
            )
            return json.loads(resp.read())["data"]["status"] == "terminal"

        # Wait for the resume operation's own terminal transition, not just
        # the attempt_id changing on disk -- the manifest write completes
        # as part of that same transition, and a preview fired the instant
        # the new attempt directory appears (before its manifest.json is
        # fully written) can race a genuinely completed resume.
        _wait_until(_resume_terminal)
        attempt_id_v2 = project_run_module.latest_attempt_id(project_id, run_id)
        assert attempt_id_v2 != attempt_id_v1

        # A fresh attempt's manifest mints its own finding_ids -- select
        # every finding on the new attempt rather than reusing the old
        # attempt's now-stale id.
        status, preview_v2 = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="handoff_preview",
            arguments={
                "run_id": run_id,
                "attempt_id": attempt_id_v2,
                "agent_id": "agent-1",
            },
        )
        assert status == 200
        hash_v2 = preview_v2["data"]["handoff_id"]
        assert hash_v1 != hash_v2

        # The older evidence version stays independently loadable, never
        # silently substituted by the newer attempt.
        status, preview_v1_again = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="handoff_preview",
            arguments={
                "run_id": run_id,
                "attempt_id": attempt_id_v1,
                "agent_id": "agent-1",
                "finding_ids": [finding_id],
            },
        )
        assert status == 200
        assert preview_v1_again["data"]["handoff_id"] == hash_v1
    finally:
        server.shutdown()
        server.server_close()


def test_handoff_preview_hash_changes_when_session_allowlist_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S06 Fix item 2: the preview hash binds the session allowlist
    (`[handoff.root]`) as part of the complete accepted envelope -- changing
    only that field (isolated via `dataclasses.replace`, mirroring the
    tamper simulation `test_handoff_send_returns_terminal_conflict_...`
    above already uses) must change the hash even though every other input
    is identical."""
    _isolate_data_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(project_run_module, "ALL_TOOLS", [ReviewTool()])
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
        run_id = body["data"]["run_id"]

        def _done() -> bool:
            status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
            return status == 200 and scans["data"].get("run") is not None

        _wait_until(_done)
        status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
        finding_id = scans["data"]["findings"]["items"][0]["finding_id"]
        attempt_id = project_run_module.latest_attempt_id(project_id, run_id)

        status, preview_body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="handoff_preview",
            arguments={
                "run_id": run_id,
                "attempt_id": attempt_id,
                "agent_id": "agent-1",
                "finding_ids": [finding_id],
            },
        )
        assert status == 200
        original_hash = preview_body["data"]["handoff_id"]

        import rush.dashboard.server as server_module

        handoff = project_run_module.ScanHandoff.from_dict(preview_body["data"])
        assert server_module._handoff_preview_hash(handoff) == original_hash

        from dataclasses import replace

        mutated = replace(handoff, root=str(root) + "-other-allowlist-root")
        mutated_hash = server_module._handoff_preview_hash(mutated)
        assert mutated_hash != original_hash
    finally:
        server.shutdown()
        server.server_close()


def test_handoff_send_with_unchanged_input_produces_identical_packet_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S06 Fix item 4: unchanged input between preview and send must yield
    an identical packet -- the dispatched/persisted handoff's packet bytes
    must exactly match what the accepted preview rendered and hashed."""
    _isolate_data_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(project_run_module, "ALL_TOOLS", [ReviewTool()])
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
        run_id = body["data"]["run_id"]

        def _done() -> bool:
            status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
            return status == 200 and scans["data"].get("run") is not None

        _wait_until(_done)
        status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
        finding_id = scans["data"]["findings"]["items"][0]["finding_id"]
        attempt_id = project_run_module.latest_attempt_id(project_id, run_id)

        status, preview_body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="handoff_preview",
            arguments={
                "run_id": run_id,
                "attempt_id": attempt_id,
                "agent_id": "agent-1",
                "finding_ids": [finding_id],
            },
        )
        assert status == 200
        preview_packet_bytes = json.dumps(
            preview_body["data"]["packet"], sort_keys=True
        )
        content_hash = preview_body["data"]["handoff_id"]

        status, send_body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="handoff_send",
            arguments={
                "run_id": run_id,
                "attempt_id": attempt_id,
                "agent_id": "agent-1",
                "finding_ids": [finding_id],
                "handoff_id": content_hash,
            },
            grants=_grant_all(),
        )
        assert status == 202
        operation_id = send_body["data"]["operation_id"]

        def _terminal() -> bool:
            resp = _get(
                f"{base_url}/api/projects/{project_id}/operations/{operation_id}",
                headers={"Cookie": cookie},
            )
            return json.loads(resp.read())["data"]["status"] == "terminal"

        _wait_until(_terminal)
        resp = _get(
            f"{base_url}/api/projects/{project_id}/operations/{operation_id}",
            headers={"Cookie": cookie},
        )
        outcome = json.loads(resp.read())["data"]["payload"]
        assert outcome["status"] == "success"
        real_handoff_id = outcome["handoff_id"]

        status, status_body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="handoff_status",
            arguments={"handoff_id": real_handoff_id},
        )
        assert status == 200
        sent_packet_bytes = json.dumps(status_body["data"]["packet"], sort_keys=True)
        assert sent_packet_bytes == preview_packet_bytes
    finally:
        server.shutdown()
        server.server_close()


def test_provision_apply_revalidation_succeeds_and_proceeds_when_nothing_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S07: only the negative (stale-plan-at-execution) path was tested for
    provisioning's worker-side revalidation -- this proves the positive
    path too: when nothing changes between accept and execution, the
    worker's independent recheck (`_dispatch_provision_apply`'s `_body`)
    must pass and the real install effect must actually proceed to
    success, not just avoid a false conflict."""
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
        operation_id = apply_body["data"]["operation_id"]

        def _terminal() -> bool:
            resp = _get(
                f"{base_url}/api/projects/{project_id}/operations/{operation_id}",
                headers={"Cookie": cookie},
            )
            return json.loads(resp.read())["data"]["status"] == "terminal"

        _wait_until(_terminal)
        resp = _get(
            f"{base_url}/api/projects/{project_id}/operations/{operation_id}",
            headers={"Cookie": cookie},
        )
        outcome = json.loads(resp.read())["data"]["payload"]
        assert outcome["status"] == "success"
        assert outcome.get("code") != "stale_expected_identity"
        assert outcome["run_id"] == apply_body["data"]["run_id"]
        assert outcome["attempt_id"] == apply_body["data"]["attempt_id"]
    finally:
        server.shutdown()
        server.server_close()


def test_handoff_send_revalidation_succeeds_and_proceeds_when_nothing_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S07: the handoff worker's own independent revalidation
    (`_dispatch_handoff_send`'s `_body`, second `_build_preview` +
    `_handoff_preview_hash` compare) must pass and the real effect
    (artifact/session/delivery) must actually proceed to success when
    nothing changes between accept (202) and execution -- only the
    negative stale-envelope conflict path was tested before this."""
    _isolate_data_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(project_run_module, "ALL_TOOLS", [ReviewTool()])
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
        run_id = body["data"]["run_id"]

        def _done() -> bool:
            status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
            return status == 200 and scans["data"].get("run") is not None

        _wait_until(_done)
        status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
        finding_id = scans["data"]["findings"]["items"][0]["finding_id"]
        attempt_id = project_run_module.latest_attempt_id(project_id, run_id)

        status, preview_body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="handoff_preview",
            arguments={
                "run_id": run_id,
                "attempt_id": attempt_id,
                "agent_id": "agent-1",
                "finding_ids": [finding_id],
            },
        )
        content_hash = preview_body["data"]["handoff_id"]

        status, send_body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="handoff_send",
            arguments={
                "run_id": run_id,
                "attempt_id": attempt_id,
                "agent_id": "agent-1",
                "finding_ids": [finding_id],
                "handoff_id": content_hash,
            },
            grants=_grant_all(),
        )
        assert status == 202
        operation_id = send_body["data"]["operation_id"]

        def _terminal() -> bool:
            resp = _get(
                f"{base_url}/api/projects/{project_id}/operations/{operation_id}",
                headers={"Cookie": cookie},
            )
            return json.loads(resp.read())["data"]["status"] == "terminal"

        _wait_until(_terminal)
        resp = _get(
            f"{base_url}/api/projects/{project_id}/operations/{operation_id}",
            headers={"Cookie": cookie},
        )
        outcome = json.loads(resp.read())["data"]["payload"]
        assert outcome["status"] == "success"
        assert outcome.get("code") != "stale_expected_identity"
        assert outcome["run_id"] == run_id
        assert outcome["attempt_id"] == attempt_id
    finally:
        server.shutdown()
        server.server_close()


def test_baseline_attempt_id_differs_from_executing_attempt_id_for_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S09 Fix item 2: a resume's admission executing-attempt column must
    never be conflated with the baseline attempt it is resuming/comparing
    against -- the 202 response's attempt_id is the new executing attempt,
    strictly different from the attempt captured before resume started."""
    _isolate_data_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(project_run_module, "ALL_TOOLS", [ReviewTool()])
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
        run_id = body["data"]["run_id"]
        operation_id = body["data"]["operation_id"]

        def _done() -> bool:
            status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
            return status == 200 and scans["data"].get("run") is not None

        _wait_until(_done)
        _wait_operation_terminal(base_url, project_id, cookie, operation_id)
        baseline_attempt_id = project_run_module.latest_attempt_id(project_id, run_id)
        assert baseline_attempt_id

        status, resume_body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="scan_resume",
            arguments={"run_id": run_id},
            grants=_grant_all(),
        )
        assert status == 202
        executing_attempt_id = resume_body["data"]["attempt_id"]
        assert executing_attempt_id != baseline_attempt_id

        def _resumed() -> bool:
            return (
                project_run_module.latest_attempt_id(project_id, run_id)
                == executing_attempt_id
            )

        _wait_until(_resumed)
        # Drain the resume to terminal so no scan worker outlives this test's
        # data-root isolation.
        _wait_operation_terminal(
            base_url, project_id, cookie, resume_body["data"]["operation_id"]
        )
    finally:
        server.shutdown()
        server.server_close()


def test_fresh_execution_after_release_receives_a_new_attempt_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S09 Fix item 4: once an admission row releases (a run completes),
    the next fresh execution on that same run must mint its own new
    attempt_id -- never reuse the just-released admission's executing
    attempt."""
    _isolate_data_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(project_run_module, "ALL_TOOLS", [ReviewTool()])
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
        run_id = body["data"]["run_id"]
        baseline_operation_id = body["data"]["operation_id"]

        def _baseline_done() -> bool:
            status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
            return status == 200 and scans["data"].get("run") is not None

        _wait_until(_baseline_done)
        _wait_operation_terminal(base_url, project_id, cookie, baseline_operation_id)
        baseline_attempt_id = project_run_module.latest_attempt_id(project_id, run_id)

        status, resume_body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="scan_resume",
            arguments={"run_id": run_id},
            grants=_grant_all(),
        )
        assert status == 202
        first_resume_operation_id = resume_body["data"]["operation_id"]
        first_resume_attempt_id = resume_body["data"]["attempt_id"]

        def _first_resume_terminal() -> bool:
            resp = _get(
                f"{base_url}/api/projects/{project_id}/operations/"
                f"{first_resume_operation_id}",
                headers={"Cookie": cookie},
            )
            return json.loads(resp.read())["data"]["status"] == "terminal"

        # Wait for the operation's own terminal status, not merely the
        # manifest attempt_id changing on disk -- the admission row's
        # release happens as part of that same terminal transition
        # (T037: "release before publish"), and a second resume fired
        # before it actually lands would race the still-held admission.
        _wait_until(_first_resume_terminal)

        # The admission row released when the first resume completed --
        # this next execution must mint its own fresh attempt, never reuse
        # the just-released one.
        status, second_resume_body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="scan_resume",
            arguments={"run_id": run_id},
            grants=_grant_all(),
        )
        assert status == 202
        second_resume_attempt_id = second_resume_body["data"]["attempt_id"]
        assert second_resume_attempt_id != first_resume_attempt_id
        assert second_resume_attempt_id != baseline_attempt_id

        def _second_resume_done() -> bool:
            return (
                project_run_module.latest_attempt_id(project_id, run_id)
                == second_resume_attempt_id
            )

        _wait_until(_second_resume_done)
        # Drain the second resume to terminal so no scan worker outlives this
        # test's data-root isolation.
        _wait_operation_terminal(
            base_url, project_id, cookie, second_resume_body["data"]["operation_id"]
        )
    finally:
        server.shutdown()
        server.server_close()


def test_scan_cancel_retains_explicit_legacy_run_id_compatibility(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S10 Fix item 1: `scan_cancel` extended `arguments.operation_id` but
    must retain explicit legacy `run_id`-only compatibility -- a caller
    that never sends `operation_id` still gets a real, attempt-scoped
    cancel (never a marker write with no attempt resolved at all) and the
    run actually stops."""
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
        run_id = body["data"]["run_id"]
        expected_attempt_id = body["data"]["attempt_id"]

        assert started.wait(timeout=5)
        # Deliberately omit arguments.operation_id -- the explicit legacy
        # contract this scenario protects.
        status, cancel_body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="scan_cancel",
            arguments={"run_id": run_id},
            grants={"cache_write": True},
        )
        assert status == 202
        assert cancel_body["data"]["run_id"] == run_id
        assert cancel_body["data"]["attempt_id"] == expected_attempt_id
        may_finish.set()

        def _run_finished() -> bool:
            status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
            return status == 200 and scans["data"].get("run") is not None

        _wait_until(_run_finished)
        status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
        assert scans["data"]["run"]["run_state"] == "cancelled"
    finally:
        server.shutdown()
        server.server_close()


def test_scan_cancel_on_terminal_target_returns_stored_result_not_a_fresh_cancel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S10 Fix item 1: a cancel targeting an already-terminal operation_id
    must return its stored terminal outcome, not attempt a fresh cancel
    marker write against work that is already over."""
    _isolate_data_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(project_run_module, "ALL_TOOLS", [ReviewTool()])
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
        run_id = body["data"]["run_id"]
        operation_id = body["data"]["operation_id"]

        def _done() -> bool:
            status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
            return status == 200 and scans["data"].get("run") is not None

        _wait_until(_done)
        _wait_operation_terminal(base_url, project_id, cookie, operation_id)

        status, cancel_body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="scan_cancel",
            arguments={"run_id": run_id, "operation_id": operation_id},
            grants={"cache_write": True},
        )
        assert status == 202
        assert cancel_body["data"]["already_terminal"] is True
        assert cancel_body["data"]["cancel_requested_at"] is None

        status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
        assert scans["data"]["run"]["run_state"] != "cancelled", (
            "a completed run's terminal target must never retroactively look cancelled"
        )
    finally:
        server.shutdown()
        server.server_close()


def test_handoff_202_response_includes_attempt_id_matching_preview_source_tuple(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S16 Fix item 1: handoff's 202 response must carry the exact
    run_id/attempt_id source tuple the accepted preview was built from --
    never a freshly reminted or substituted attempt."""
    _isolate_data_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(project_run_module, "ALL_TOOLS", [ReviewTool()])
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
        run_id = body["data"]["run_id"]

        def _done() -> bool:
            status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
            return status == 200 and scans["data"].get("run") is not None

        _wait_until(_done)
        status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
        finding_id = scans["data"]["findings"]["items"][0]["finding_id"]
        attempt_id = project_run_module.latest_attempt_id(project_id, run_id)

        status, preview_body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="handoff_preview",
            arguments={
                "run_id": run_id,
                "attempt_id": attempt_id,
                "agent_id": "agent-1",
                "finding_ids": [finding_id],
            },
        )
        content_hash = preview_body["data"]["handoff_id"]
        assert preview_body["data"]["run_id"] == run_id
        assert preview_body["data"]["attempt_id"] == attempt_id

        status, send_body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="handoff_send",
            arguments={
                "run_id": run_id,
                "attempt_id": attempt_id,
                "agent_id": "agent-1",
                "finding_ids": [finding_id],
                "handoff_id": content_hash,
            },
            grants=_grant_all(),
        )
        assert status == 202
        assert send_body["data"]["run_id"] == run_id
        assert send_body["data"]["attempt_id"] == attempt_id
    finally:
        server.shutdown()
        server.server_close()


def test_handoff_status_and_acceptance_match_previews_source_tuple(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S16 Fix item 1: handoff_status's persisted source tuple must match
    exactly what the accepted preview pinned -- never a latest-attempt
    substitution during persistence/dispatch."""
    _isolate_data_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(project_run_module, "ALL_TOOLS", [ReviewTool()])
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
        run_id = body["data"]["run_id"]

        def _done() -> bool:
            status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
            return status == 200 and scans["data"].get("run") is not None

        _wait_until(_done)
        status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
        finding_id = scans["data"]["findings"]["items"][0]["finding_id"]
        attempt_id = project_run_module.latest_attempt_id(project_id, run_id)

        status, preview_body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="handoff_preview",
            arguments={
                "run_id": run_id,
                "attempt_id": attempt_id,
                "agent_id": "agent-1",
                "finding_ids": [finding_id],
            },
        )
        content_hash = preview_body["data"]["handoff_id"]

        status, send_body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="handoff_send",
            arguments={
                "run_id": run_id,
                "attempt_id": attempt_id,
                "agent_id": "agent-1",
                "finding_ids": [finding_id],
                "handoff_id": content_hash,
            },
            grants=_grant_all(),
        )
        assert status == 202
        operation_id = send_body["data"]["operation_id"]

        def _terminal() -> bool:
            resp = _get(
                f"{base_url}/api/projects/{project_id}/operations/{operation_id}",
                headers={"Cookie": cookie},
            )
            return json.loads(resp.read())["data"]["status"] == "terminal"

        _wait_until(_terminal)
        resp = _get(
            f"{base_url}/api/projects/{project_id}/operations/{operation_id}",
            headers={"Cookie": cookie},
        )
        outcome = json.loads(resp.read())["data"]["payload"]
        assert outcome["status"] == "success"
        real_handoff_id = outcome["handoff_id"]

        status, status_body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="handoff_status",
            arguments={"handoff_id": real_handoff_id},
        )
        assert status == 200
        assert status_body["data"]["run_id"] == run_id
        assert status_body["data"]["attempt_id"] == attempt_id
    finally:
        server.shutdown()
        server.server_close()


def test_provisioning_status_acceptance_and_receipts_match_its_allocated_job_tuple(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S16 Fix item 2: provisioning's status/receipts must report the
    exact run/attempt tuple allocated at 202-acceptance time -- never
    reminted or substituted by the time the worker's terminal payload
    lands."""
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    server, base_url, cookie, csrf = _start_dashboard(project_id, root)
    try:
        status, plan_body = _action(
            base_url, project_id, cookie, csrf, operation="provision_plan"
        )
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
        operation_id = apply_body["data"]["operation_id"]
        accepted_run_id = apply_body["data"]["run_id"]
        accepted_attempt_id = apply_body["data"]["attempt_id"]

        def _terminal() -> bool:
            resp = _get(
                f"{base_url}/api/projects/{project_id}/operations/{operation_id}",
                headers={"Cookie": cookie},
            )
            return json.loads(resp.read())["data"]["status"] == "terminal"

        _wait_until(_terminal)
        resp = _get(
            f"{base_url}/api/projects/{project_id}/operations/{operation_id}",
            headers={"Cookie": cookie},
        )
        outcome = json.loads(resp.read())["data"]["payload"]
        assert outcome["status"] == "success"
        assert outcome["run_id"] == accepted_run_id
        assert outcome["attempt_id"] == accepted_attempt_id
    finally:
        server.shutdown()
        server.server_close()


def test_crash_immediately_after_202_recovers_without_reminting_or_substituting_an_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S16 Fix item 2/Regression: a client retry with the identical
    request_id after a crash immediately following 202 must replay the
    exact cached response -- `MutationLedger.commit()`'s own idempotent
    reservation cache never re-invokes the dispatcher on a cache hit, so
    no new run_id/attempt_id is ever minted or substituted for the one
    already accepted."""
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    server, base_url, cookie, csrf = _start_dashboard(project_id, root)
    try:
        status, plan_body = _action(
            base_url, project_id, cookie, csrf, operation="provision_plan"
        )
        plan_id = plan_body["data"]["readiness"]["plan_id"]
        shared_request_id = str(uuid.uuid4())

        status, first_body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="provision_apply",
            arguments={"plan_id": plan_id},
            grants=_grant_all(),
            request_id=shared_request_id,
        )
        assert status == 202
        first_operation_id = first_body["data"]["operation_id"]
        first_run_id = first_body["data"]["run_id"]
        first_attempt_id = first_body["data"]["attempt_id"]

        # Simulated crash-and-retry: the identical request_id, resubmitted.
        status, retry_body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="provision_apply",
            arguments={"plan_id": plan_id},
            grants=_grant_all(),
            request_id=shared_request_id,
        )
        assert status == 202
        assert retry_body["data"]["operation_id"] == first_operation_id
        assert retry_body["data"]["run_id"] == first_run_id
        assert retry_body["data"]["attempt_id"] == first_attempt_id

        def _terminal() -> bool:
            resp = _get(
                f"{base_url}/api/projects/{project_id}/operations/{first_operation_id}",
                headers={"Cookie": cookie},
            )
            return json.loads(resp.read())["data"]["status"] == "terminal"

        _wait_until(_terminal)
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_owned_normal_scan_cancel_via_direct_marker_write_actually_stops_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """U02/T043: for a normal (non-CHECK_SUITE) dashboard-owned run, the
    TUI's own `_request_cancel` never dispatches the dashboard's
    `scan_cancel` HTTP action -- it calls the shared `cancel_scan_run()`
    filesystem marker directly (ratified acceptable-equivalent, T043),
    because both processes read the same on-disk marker under the shared
    project root. Proves that direct-call marker write, bypassing HTTP
    entirely, still reaches and stops a scan the dashboard server itself
    is actually executing -- mirroring T044's real CHECK_SUITE cancel
    proof (`test_check_suite_cancel_actually_stops_the_dashboard_owned_run`
    above), for scan_start instead."""
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
        # The real production mechanism `_request_cancel` uses for a
        # dashboard-owned run: a direct call to the shared workflow
        # function, never an HTTP scan_cancel dispatch.
        project_run_module.cancel_scan_run(project_id, run_id)
        may_finish.set()

        def _run_finished() -> bool:
            status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
            return status == 200 and scans["data"].get("run") is not None

        _wait_until(_run_finished)
        status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
        assert scans["data"]["run"]["run_state"] == "cancelled"
        items = scans["data"]["findings"]["items"]
        assert len(items) == 1
        assert items[0]["rule"] == "seeded-review-rule"
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
        current_attempt_id,
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
        # Engine rows resolve only from this venv (the module's hermetic
        # PATH), and M17's CACHEDIR.TAG exclusion keeps an installed entropy
        # scanner off that fixed signature string, so only the seeded
        # `stays_broken` review finding persists across rescan.
        assert len(by_status.get("persisting", [])) == 1
        assert len(by_status.get("new", [])) == 1
        assert len(by_status.get("unverified", [])) == 1

        persisting_items = by_status["persisting"]
        persisting = next(
            f for f in persisting_items if f["provenance"].startswith("review/")
        )
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
        finding_ids = [persisting["finding_id"], new_finding["finding_id"]]
        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="handoff_preview",
            arguments={
                "run_id": current_run_id,
                "attempt_id": current_attempt_id,
                "agent_id": "agent-1",
                "finding_ids": finding_ids,
            },
        )
        assert status == 200
        assert body["data"]["state"] == "prepared"
        content_hash = body["data"]["handoff_id"]
        # A genuinely read-only preview never exposes a session capability.
        assert "session_capability" not in body["data"] or not body["data"].get(
            "session_capability"
        )

        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="handoff_send",
            arguments={
                "run_id": current_run_id,
                "attempt_id": current_attempt_id,
                "agent_id": "agent-1",
                "finding_ids": finding_ids,
                "handoff_id": content_hash,
            },
            grants=_grant_all(),
        )
        assert status == 202
        operation_id = body["data"]["operation_id"]

        def _handoff_terminal() -> dict[str, Any]:
            resp = _get(
                f"{base_url}/api/projects/{project_id}/operations/{operation_id}",
                headers={"Cookie": cookie},
            )
            return json.loads(resp.read())

        def _is_terminal() -> bool:
            return _handoff_terminal()["data"]["status"] == "terminal"

        _wait_until(_is_terminal)
        final = _handoff_terminal()["data"]["payload"]
        assert final["status"] == "success"
        real_handoff_id = final["handoff_id"]

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
        # Read-back never reveals the one-time capability again.
        assert "session_capability" not in status_body["data"]
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
        operation_id = body["data"]["operation_id"]

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
        _wait_operation_terminal(base_url, project_id, cookie, operation_id)
        status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
        assert scans["data"]["run"]["run_state"] == "cancelled"
        # review already finished before cancellation landed -- its finding
        # is retained as real partial evidence.
        items = scans["data"]["findings"]["items"]
        # Engine rows resolve only from this venv (the module's hermetic
        # PATH), and M17's CACHEDIR.TAG exclusion keeps an installed entropy
        # scanner off that fixed signature string, so only the review tool's
        # own retained finding is present.
        assert len(items) == 1
        by_rule = {item["rule"]: item for item in items}
        assert "seeded-review-rule" in by_rule
        assert scans["data"]["active_run_id"] is None
    finally:
        server.shutdown()
        server.server_close()


def test_check_suite_cancel_actually_stops_the_dashboard_owned_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T044: `_dispatch_check_suite`'s `cancel_check` only ever polled a
    `threading.Event()` that nothing sets, so a dashboard-owned CHECK_SUITE
    run could never actually be cancelled through `scan_cancel`'s real
    filesystem marker. Proves the marker now actually reaches it: 'format'
    pauses until cancelled, 'lint' (the next scheduled tool) must never
    run."""
    _isolate_data_roots(tmp_path, monkeypatch)
    started = threading.Event()
    may_finish = threading.Event()
    lint_calls: list[Path] = []

    class _PausingFormat:
        name = "format"

        def __call__(self, path: Path) -> dict[str, object]:
            started.set()
            may_finish.wait(timeout=5)
            return {
                "tool": "format",
                "engine": None,
                "engine_version": None,
                "status": "ok",
                "duration_ms": 1,
                "summary": "format: ok",
                "findings": [],
                "raw": None,
            }

    class _NeverRunsLint:
        name = "lint"

        def __call__(self, path: Path) -> dict[str, object]:
            lint_calls.append(path)
            raise AssertionError("lint must never run after cancellation")

    monkeypatch.setattr(
        suites_module, "ALL_TOOLS", [_PausingFormat(), _NeverRunsLint()]
    )
    project_id, root = _register(tmp_path)
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
    server, ctx, bootstrap_token = create_dashboard_server({project_id: snapshot})
    _serve(server)
    base_url = ctx.launch_origin
    cookie, csrf = _bootstrap_session(base_url, bootstrap_token)
    try:
        data = dispatch_control_check_suite(
            base_url, ctx.auth.control_capability, project_id
        )
        operation_id = data["operation_id"]
        run_id = data["run_id"]

        assert started.wait(timeout=5)
        status, _body = _action(
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

        def _op_status() -> dict[str, Any]:
            resp = _get(
                f"{base_url}/api/projects/{project_id}/operations/{operation_id}",
                headers={"Cookie": cookie},
            )
            return json.loads(resp.read())

        def _is_terminal() -> bool:
            return _op_status()["data"]["status"] == "terminal"

        _wait_until(_is_terminal)
        final = _op_status()["data"]["payload"]
        assert final["cancelled"] is True
        assert lint_calls == []
    finally:
        server.shutdown()
        server.server_close()


def test_scan_cancel_accepts_operation_id_and_resolves_the_attached_executor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S10: an accepted/attached caller's own `operation_id` -- never only
    `run_id` -- resolves through the durable admission table to the real
    executor and cancels it."""
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
        operation_id = body["data"]["operation_id"]

        assert started.wait(timeout=5)
        status, cancel_body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="scan_cancel",
            arguments={"operation_id": operation_id},
            grants={"cache_write": True},
        )
        assert status == 202
        assert cancel_body["data"]["run_id"] == run_id
        may_finish.set()

        def _run_finished() -> bool:
            status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
            return status == 200 and scans["data"].get("run") is not None

        _wait_until(_run_finished)
        status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
        assert scans["data"]["run"]["run_state"] == "cancelled"
    finally:
        server.shutdown()
        server.server_close()


def test_cancel_submits_retained_operation_id_including_attached_callers_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """U02: `_dispatch_scan_cancel` resolves an attached caller's own
    `operation_id` through `_resolved_operation_id` to find the real
    executor's run/attempt -- but the 202 response still echoes back the
    caller's *own*, unresolved `operation_id` (never the resolved executor's
    id), so a client polling its own operation never has to know which
    operation_id actually did the work."""
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
        executing_operation_id = body["data"]["operation_id"]
        assert started.wait(timeout=5)

        # A second scan_start for the same plan_id attaches to the already
        # -admitted execution instead of starting a distinct run; its own
        # operation_id is attached, never the executing one.
        status, attach_body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="scan_start",
            arguments={"plan_id": plan_id},
            grants=_grant_all(),
        )
        assert status == 202
        assert attach_body["data"]["attached_to_existing"] is True
        assert attach_body["data"]["run_id"] == run_id
        attached_operation_id = attach_body["data"]["operation_id"]
        assert attached_operation_id != executing_operation_id

        status, cancel_body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="scan_cancel",
            arguments={"operation_id": attached_operation_id},
            grants={"cache_write": True},
        )
        assert status == 202
        # Resolved via _resolved_operation_id to the real executor's run --
        # never a fresh/unrelated run this attached id has no admission for.
        assert cancel_body["data"]["run_id"] == run_id
        # Retained/echoed exactly as submitted -- never silently replaced by
        # the resolved executing operation_id.
        assert cancel_body["data"]["operation_id"] == attached_operation_id
        may_finish.set()

        def _run_finished() -> bool:
            status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
            return status == 200 and scans["data"].get("run") is not None

        _wait_until(_run_finished)
        status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
        assert scans["data"]["run"]["run_state"] == "cancelled"
    finally:
        server.shutdown()
        server.server_close()


def test_cancel_from_a_second_server_process_still_resolves_the_same_durable_intent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S10: the attachment chain (`operation_attachments`) and admission
    table (`scan_admission`) both live in one on-disk SQLite file under the
    project's data root, not in either server's process memory. A second,
    fully independent `DashboardContext`/server -- its own auth, sessions,
    and `MutationLedger` Python object/connection -- started against that
    same data root resolves an attached caller's `operation_id` to the
    first server's admitted run/attempt and can cancel it, writing the real
    filesystem cancel marker for that run, exactly as if it were the server
    that originally admitted it."""
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
    server1, base_url1, cookie1, csrf1 = _start_dashboard(project_id, root)
    server2, base_url2, cookie2, csrf2 = _start_dashboard(project_id, root)
    try:
        status, body = _action(
            base_url1, project_id, cookie1, csrf1, operation="provision_plan"
        )
        plan_id = body["data"]["scan_plan"]["plan_id"]

        status, body = _action(
            base_url1,
            project_id,
            cookie1,
            csrf1,
            operation="scan_start",
            arguments={"plan_id": plan_id},
            grants=_grant_all(),
        )
        assert status == 202
        run_id = body["data"]["run_id"]
        attempt_id = body["data"]["attempt_id"]
        assert started.wait(timeout=5)

        # Server 2 -- a wholly separate DashboardContext/MutationLedger --
        # attaches to server 1's execution_identity via the shared on-disk
        # scan_admission row, minting its own distinct operation_id.
        status, attach_body = _action(
            base_url2,
            project_id,
            cookie2,
            csrf2,
            operation="scan_start",
            arguments={"plan_id": plan_id},
            grants=_grant_all(),
        )
        assert status == 202
        assert attach_body["data"]["attached_to_existing"] is True
        assert attach_body["data"]["run_id"] == run_id
        second_process_operation_id = attach_body["data"]["operation_id"]

        cancel_marker = (
            root
            / ".rush"
            / "runs"
            / run_id
            / "attempts"
            / attempt_id
            / "cancel_requested.json"
        )
        assert not cancel_marker.exists()

        # The cancel request is issued entirely through server 2's own
        # context, naming only server 2's own attached operation_id -- it
        # never sees, and never needs, server 1's operation_id or run_id.
        status, cancel_body = _action(
            base_url2,
            project_id,
            cookie2,
            csrf2,
            operation="scan_cancel",
            arguments={"operation_id": second_process_operation_id},
            grants={"cache_write": True},
        )
        assert status == 202
        assert cancel_body["data"]["run_id"] == run_id
        assert cancel_marker.is_file()
        may_finish.set()

        def _run_finished() -> bool:
            status, scans = _scans(base_url1, project_id, cookie1, run_id=run_id)
            return status == 200 and scans["data"].get("run") is not None

        _wait_until(_run_finished)
        status, scans = _scans(base_url1, project_id, cookie1, run_id=run_id)
        assert scans["data"]["run"]["run_state"] == "cancelled"
    finally:
        server1.shutdown()
        server1.server_close()
        server2.shutdown()
        server2.server_close()


def test_scan_cancel_unknown_or_cross_project_operation_id_returns_uniform_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    server, base_url, cookie, csrf = _start_dashboard(project_id, root)
    try:
        status, _body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="scan_cancel",
            arguments={"operation_id": "unknown-operation-id"},
            grants={"cache_write": True},
        )
        assert status == 404
    finally:
        server.shutdown()
        server.server_close()


def test_provisioning_202_response_includes_its_own_allocated_attempt_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S16: provisioning allocates and returns its own durable
    run_id/attempt_id job tuple, distinct from scan admission."""
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
        assert apply_body["data"]["run_id"]
        assert apply_body["data"]["attempt_id"]

        operation_id = apply_body["data"]["operation_id"]

        # Poll via a direct GET rather than the shared `_get_operation`
        # helper (private to test_dashboard_missing_routes.py).
        def _op_terminal() -> bool:
            resp = _get(
                f"{base_url}/api/projects/{project_id}/operations/{operation_id}",
                headers={"Cookie": cookie},
            )
            payload = json.loads(resp.read())
            return payload["data"]["status"] == "terminal"

        _wait_until(_op_terminal)
        resp = _get(
            f"{base_url}/api/projects/{project_id}/operations/{operation_id}",
            headers={"Cookie": cookie},
        )
        payload = json.loads(resp.read())
        outcome = payload["data"]["payload"]
        assert outcome["status"] == "success"
        assert outcome["attempt_id"] == apply_body["data"]["attempt_id"]
    finally:
        server.shutdown()
        server.server_close()


def test_provisioning_worker_returns_terminal_conflict_on_plan_mismatch_with_zero_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S07: the accept-time plan-freshness check can pass, yet the reviewed
    plan can still go stale before the worker's real install effect runs --
    the independent, second check from inside the worker must catch that and
    apply nothing."""
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    server, base_url, cookie, csrf = _start_dashboard(project_id, root)
    try:
        status, plan_body = _action(
            base_url, project_id, cookie, csrf, operation="provision_plan"
        )
        assert status == 200
        plan_id = plan_body["data"]["readiness"]["plan_id"]

        import rush.dashboard.server as server_module

        real_run_setup_wizard = server_module.run_setup_wizard
        calls = {"n": 0}

        def _flaky_run_setup_wizard(*args: Any, **kwargs: Any) -> Any:
            calls["n"] += 1
            result = real_run_setup_wizard(*args, **kwargs)
            if calls["n"] == 1:
                # The outer, synchronous accept-time check -- unchanged.
                return result
            # The worker's own revalidation, immediately before the real
            # `install=True` effect: simulate a plan that changed underneath
            # the already-accepted request.
            return {**result, "plan_id": "a-different-stale-plan-id"}

        monkeypatch.setattr(server_module, "run_setup_wizard", _flaky_run_setup_wizard)

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
        operation_id = apply_body["data"]["operation_id"]

        def _terminal() -> bool:
            resp = _get(
                f"{base_url}/api/projects/{project_id}/operations/{operation_id}",
                headers={"Cookie": cookie},
            )
            return json.loads(resp.read())["data"]["status"] == "terminal"

        _wait_until(_terminal)
        resp = _get(
            f"{base_url}/api/projects/{project_id}/operations/{operation_id}",
            headers={"Cookie": cookie},
        )
        outcome = json.loads(resp.read())["data"]["payload"]
        assert outcome["status"] == "conflict"
        assert outcome["code"] == "stale_expected_identity"
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
        # S09: every attached response resolves to the *admitted executor's*
        # own durable attempt_id -- never a best-effort disk lookup (which
        # can race the winner's not-yet-written attempt header) or the
        # losing request's own separately minted attempt.
        attempt_ids = {body["data"]["attempt_id"] for _, body in statuses_and_bodies}
        assert len(attempt_ids) == 1
    finally:
        server.shutdown()
        server.server_close()


def test_attach_before_header_publication_returns_the_exact_attempt_later_persisted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S09: an attach that races the winner's own attempt-header write must
    still resolve to that exact winning attempt -- the admission table's own
    durable `attempt_id` column, never a disk read that could still find
    nothing (or a stale prior attempt)."""
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

        status, first_body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="scan_start",
            arguments={"plan_id": plan_id},
            grants=_grant_all(),
        )
        assert status == 202
        winning_attempt_id = first_body["data"]["attempt_id"]
        assert winning_attempt_id

        status, second_body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="scan_start",
            arguments={"plan_id": plan_id},
            grants=_grant_all(),
            request_id=str(uuid.uuid4()),
        )
        assert status == 202
        assert second_body["data"]["attached_to_existing"] is True
        assert second_body["data"]["attempt_id"] == winning_attempt_id

        def _done() -> bool:
            status, scans = _scans(
                base_url, project_id, cookie, run_id=first_body["data"]["run_id"]
            )
            return status == 200 and scans["data"].get("run") is not None

        _wait_until(_done)
    finally:
        server.shutdown()
        server.server_close()


# --- S04 bullet 3: reservation primitive wired into every dispatcher's
# proposed effect-key map (review doc §S04 table) ----------------------------


def test_s04_effect_ids_pure_function_matches_review_doc_table() -> None:
    """S04: `_s04_effect_ids` is the per-operation proposed effect-key map
    (review doc §S04 table), computed before reservation so
    `MutationLedger.reserve()` persists it in the same transaction as the
    operation_id."""
    from rush.dashboard.server import _s04_effect_ids

    for op in (
        "scan_start",
        "scan_resume",
        "rescan",
        "check_suite",
    ):
        assert set(_s04_effect_ids(op, {})) == {
            "scan_manifest_write",
            "snapshot_publish",
        }

    assert set(_s04_effect_ids("scan_cancel", {})) == {"cancellation_intent"}
    assert set(_s04_effect_ids("handoff_send", {})) == {
        "artifact_create",
        "session_create",
        "descriptor_prepare",
        "delivery_transition",
    }
    assert set(_s04_effect_ids("provision_apply", {})) == {
        "cursor_key_ensure",
        "toolchain_manifest",
    }
    assert set(_s04_effect_ids("memory_propose", {})) == {"artifact_create"}
    assert set(_s04_effect_ids("memory_promote", {})) == {
        "candidate_create",
        "promotion",
    }
    assert set(_s04_effect_ids("memory_maintain", {})) == {"maintenance_run"}

    # apply-gated actions: no domain effect keys when apply is absent/false.
    for op in ("configure", "memory_edit", "memory_archive", "memory_delete"):
        assert _s04_effect_ids(op, {}) == {}
        assert _s04_effect_ids(op, {"apply": False}) == {}
    assert set(_s04_effect_ids("configure", {"apply": True})) == {"config_write"}
    assert set(_s04_effect_ids("memory_edit", {"apply": True})) == {"artifact_edit"}
    assert set(_s04_effect_ids("memory_archive", {"apply": True})) == {
        "artifact_archive"
    }
    delete_ids = _s04_effect_ids(
        "memory_delete", {"apply": True, "artifact_ids": ["b", "a"]}
    )
    assert set(delete_ids) == {"delete:a", "delete:b"}
    assert delete_ids["delete:a"] != delete_ids["delete:b"]

    # read-only fixed actions and noop: no domain effect keys.
    for op in (
        "noop",
        "provision_plan",
        "handoff_preview",
        "handoff_status",
        "memory_query",
        "memory_expand",
        "data_export",
        "artifact_export",
    ):
        assert _s04_effect_ids(op, {}) == {}

    # Every call mints fresh, non-empty ids -- never reuses the same value
    # across two calls (no accidental sharing between operations).
    first = _s04_effect_ids("handoff_send", {})
    second = _s04_effect_ids("handoff_send", {})
    assert first != second
    assert all(v for v in first.values())


def test_scan_start_reserves_effect_ids_in_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S04: a real `scan_start` dispatch persists the S04-table effect-key
    map into `MutationLedger` at reservation time -- recoverable via
    `get_reservation(operation_id)` for a crashed operation, never an empty
    `{}` (T004's own self-flagged gap)."""
    _isolate_data_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(project_run_module, "ALL_TOOLS", [ReviewTool()])
    project_id, root = _register(tmp_path)
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
        operation_id = body["data"]["operation_id"]
        assert operation_id

        reservation = ctx.mutations.get_reservation(operation_id)
        assert reservation is not None
        assert set(reservation["effect_ids"]) == {
            "scan_manifest_write",
            "snapshot_publish",
        }
        assert all(reservation["effect_ids"].values())
        assert reservation["validated_arguments"].get("plan_id") == plan_id

        def _done() -> bool:
            status, scans = _scans(
                base_url, project_id, cookie, run_id=body["data"]["run_id"]
            )
            return status == 200 and scans["data"].get("run") is not None

        _wait_until(_done)
    finally:
        server.shutdown()
        server.server_close()


def test_provision_apply_reserves_install_effect_ids_per_plan_entry_in_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T035/S04 residual: `_s04_effect_ids`'s `provision_apply` branch
    reserves one `install:<engine_id>` key per entry in the real, freshly
    built provision plan for the project -- not just the two operation-wide
    keys -- and that reservation actually lands in `MutationLedger` (the
    real receipt row via `get_reservation(operation_id)`), never just a
    non-empty dict from calling `_s04_effect_ids` in isolation."""
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    # `requirements.txt` is a `PYTHON_MARKERS` file (rush/discovery/stack.py)
    # -- `_register`'s bare `app.py` alone triggers no stack detection at
    # all, so this is required for `readiness["skipped"]` to be non-empty.
    (root / "requirements.txt").write_text("flask==0.1\n", encoding="utf-8")
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
    try:
        status, plan_body = _action(
            base_url, project_id, cookie, csrf, operation="provision_plan"
        )
        assert status == 200
        readiness = plan_body["data"]["readiness"]
        plan_id = readiness["plan_id"]
        # Python stack detection suggests real engines (ruff, mypy, pytest,
        # pip-audit, bandit); every non-`unsupported_engines` one gets a
        # real `ProvisionPlan` entry.
        expected_engine_ids = sorted(
            set(readiness["skipped"]) - set(readiness.get("unsupported_engines", []))
        )
        assert expected_engine_ids  # never a vacuous check

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
        operation_id = apply_body["data"]["operation_id"]
        assert operation_id

        reservation = ctx.mutations.get_reservation(operation_id)
        assert reservation is not None
        effect_ids = reservation["effect_ids"]
        assert {"cursor_key_ensure", "toolchain_manifest"} <= set(effect_ids)
        install_keys = {k for k in effect_ids if k.startswith("install:")}
        assert install_keys == {f"install:{e}" for e in expected_engine_ids}
        assert all(effect_ids[k] for k in install_keys)
    finally:
        server.shutdown()
        server.server_close()


def test_trivy_decoded_raw_target_field_uses_logical_path_not_staged_temp_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M20: Trivy's own decoded `Results[].Target` field (never a generic
    `_PATH_KEYS` name) must be remapped to the logical project path when a
    staged attempt is active -- both in the per-finding `target` field and
    in the raw decoded output, mirroring Stylelint's own `source`-field fix
    (`engines/stylelint.py`). Colocated here (T025's allowed_files has no
    engine-adapter test file) rather than alongside Stylelint's own M20
    tests in tests/test_project_run_lifecycle.py."""
    import json as json_module
    import subprocess as subprocess_module

    from rush.engines import trivy as trivy_module
    from rush.engines.staging import stage_inventory, staging_scope

    root = tmp_path / "project"
    root.mkdir()
    (root / "requirements.txt").write_text("flask==0.1\n", encoding="utf-8")
    staged_root = tmp_path / "staged"
    staging = stage_inventory(root, staged_root, ["requirements.txt"])
    staged_target = staged_root / "requirements.txt"

    payload = json_module.dumps(
        {
            "Results": [
                {
                    "Target": str(staged_target),
                    "Vulnerabilities": [
                        {
                            "VulnerabilityID": "CVE-2024-0001",
                            "PkgName": "flask",
                            "InstalledVersion": "0.1",
                            "FixedVersion": "0.2",
                            "Severity": "HIGH",
                            "Title": f"see {staged_target} for details",
                        }
                    ],
                }
            ]
        }
    )

    monkeypatch.setattr(trivy_module, "resolve_binary", lambda _b: "trivy")
    monkeypatch.setattr(
        trivy_module,
        "run_subprocess",
        lambda argv, **k: subprocess_module.CompletedProcess(
            argv, 0, stdout=payload, stderr=""
        ),
    )

    with staging_scope(staging):
        raw = trivy_module.TrivyEngine().run(staged_target, [], cwd=staged_root)

    assert raw["findings"][0]["target"] == str(root / "requirements.txt")
    assert raw["parsed"]["Results"][0]["Target"] == str(root / "requirements.txt")
