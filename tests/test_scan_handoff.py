"""Tests for Phase 65 P65-06.1/.2: bounded agent handoff (F35).

Fixture manifests are written directly against the real, documented
`project_run` manifest schema (`{"aggregate": {"findings": [...]}, "scheduled":
[...]}`, produced by `execute_scan`/`_build_manifest`) rather than re-deriving
real tool execution -- `build_handoff`'s contract is "given a persisted run
manifest, prepare a bounded handoff", already independent of how that
manifest's findings were produced (covered by `test_full_project_scan.py`).
`test_prepare_dispatch_acknowledge_complete_round_trip` additionally proves
the whole lifecycle against a *real* `plan_scan`/`execute_scan` run so the
manifest-schema fixtures below are never the only path exercised.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rush.permissions import ExecutionPermissions
from rush.tools.review import ReviewTool
from rush.tools.scan_handoff import ScanHandoffTool
from rush.workflows import project_run
from rush.workflows.project_run import (
    ScanHandoffAuthError,
    ScanHandoffInvalidStateError,
    ScanHandoffSourceChangedError,
    ScanInvalidRequestError,
    acknowledge_handoff,
    build_handoff,
    complete_handoff,
    dispatch_handoff,
    execute_scan,
    plan_scan,
    status_handoff,
)
from rush.workflows.projects import register_project


def _fixture_root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("def unreviewed():\n    pass\n", encoding="utf-8")
    return root


def _register(tmp_path: Path) -> tuple[str, Path]:
    root = _fixture_root(tmp_path)
    data_root = tmp_path / "rush-data"
    record = register_project(root, data_root=data_root)
    return record.project_id, data_root


def _finding(
    finding_id: str,
    *,
    tool: str = "review",
    engine: str | None = "no-engine",
    message: str = "issue",
    severity: str = "warn",
    path: str = "app.py",
    line: int = 1,
    column: int = 0,
    rule: str = "seeded-rule",
) -> dict[str, object]:
    return {
        "finding_id": finding_id,
        "path": path,
        "line": line,
        "column": column,
        "rule": rule,
        "severity": severity,
        "message": message,
        "provenance": f"{tool}/{engine or 'no-engine'}",
    }


def _write_manifest(
    root: Path,
    run_id: str,
    *,
    findings: list[dict[str, object]],
    scheduled: list[dict[str, object]] | None = None,
    plan_id: str = "fixture-plan",
) -> None:
    manifest_dir = root / ".rush" / "runs" / run_id / "attempts" / "attempt-1"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "attempt_id": "attempt-1",
        "plan_id": plan_id,
        "run_state": "completed",
        "aggregate": {"findings": findings},
        "scheduled": scheduled or [],
        "totals": {"finding_count": len(findings)},
    }
    (manifest_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


def test_prepare_dispatch_acknowledge_complete_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(project_run, "ALL_TOOLS", [ReviewTool()])
    project_id, data_root = _register(tmp_path)
    plan = plan_scan(project_id, data_root=data_root)
    run = execute_scan(plan, permissions=ExecutionPermissions(), data_root=data_root)

    handoff = build_handoff(project_id, run.run_id, "codex-cli", data_root=data_root)
    assert handoff.state == "prepared"
    assert handoff.finding_ids, "expected at least one seeded finding"

    dispatched = dispatch_handoff(
        project_id, handoff.handoff_id, handoff.session_capability, data_root=data_root
    )
    assert dispatched.state == "delivered"

    acknowledged = acknowledge_handoff(
        project_id, handoff.handoff_id, handoff.delivery_nonce, data_root=data_root
    )
    assert acknowledged.state == "acknowledged"

    completed = complete_handoff(
        project_id,
        handoff.handoff_id,
        handoff.delivery_nonce,
        artifact_ids=("agent-patch-1",),
        data_root=data_root,
    )
    assert completed.state == "agent_reported_complete"
    assert completed.agent_reported_complete_artifact_ids == ("agent-patch-1",)
    # Never auto-promoted to a verified fix -- no "resolved"/"verified" state exists here.
    assert completed.state not in ("resolved", "verified")

    status = status_handoff(project_id, handoff.handoff_id, data_root=data_root)
    assert status["state"] == "agent_reported_complete"
    assert "session_capability" not in status
    assert "delivery_nonce" not in status


def test_duplicate_findings_from_two_engines_retain_both_provenance_records(
    tmp_path: Path,
) -> None:
    project_id, data_root = _register(tmp_path)
    from rush.workflows.projects import resolve_project

    root = Path(resolve_project(project_id, data_root=data_root)["root"])

    same_location = {"path": "app.py", "line": 5, "column": 0, "rule": "seeded-rule"}
    finding_a = _finding(
        "finding-engine-a", tool="eslint", engine="engine-a", **same_location
    )
    finding_b = _finding(
        "finding-engine-b", tool="eslint", engine="engine-b", **same_location
    )
    _write_manifest(root, "run-dup", findings=[finding_a, finding_b])

    handoff = build_handoff(project_id, "run-dup", "codex-cli", data_root=data_root)

    assert set(handoff.finding_ids) == {"finding-engine-a", "finding-engine-b"}
    assert "eslint/engine-a" in {
        item.get("provenance") for item in handoff.packet["items"]
    }
    assert "eslint/engine-b" in {
        item.get("provenance") for item in handoff.packet["items"]
    }
    assert len(handoff.packet["items"]) == 2


def test_large_logs_exceed_budget_but_compact_packet_fits(tmp_path: Path) -> None:
    project_id, data_root = _register(tmp_path)
    from rush.workflows.projects import resolve_project

    root = Path(resolve_project(project_id, data_root=data_root)["root"])

    huge_message = "x" * 50_000
    huge_finding = _finding("finding-huge", message=huge_message, line=1)
    normal_finding = _finding("finding-normal", message="short issue", line=2)
    _write_manifest(root, "run-huge", findings=[huge_finding, normal_finding])

    handoff = build_handoff(
        project_id,
        "run-huge",
        "codex-cli",
        max_tokens=256,
        max_bytes=2048,
        data_root=data_root,
    )

    assert handoff.packet["bytes"] <= 2048
    assert handoff.packet["tokens"] <= 256
    # Never silently loses a selected finding: both IDs are still accounted for,
    # either embedded or referenced.
    assert set(handoff.finding_ids) == {"finding-huge", "finding-normal"}
    huge_item = next(
        item
        for item in handoff.packet["items"]
        if item.get("finding_id") == "finding-huge"
    )
    assert huge_item.get("reference_only") is True
    assert huge_item["excerpt_truncated"] is True
    assert len(huge_item["excerpt"]) < len(huge_message)


def test_stale_source_identity_refuses_apply(tmp_path: Path) -> None:
    project_id, data_root = _register(tmp_path)
    from rush.workflows.projects import resolve_project

    root = Path(resolve_project(project_id, data_root=data_root)["root"])
    _write_manifest(root, "run-stale", findings=[_finding("finding-1")])

    handoff = build_handoff(project_id, "run-stale", "codex-cli", data_root=data_root)

    (root / "app.py").write_text("def changed():\n    return 1\n", encoding="utf-8")

    with pytest.raises(ScanHandoffSourceChangedError):
        dispatch_handoff(
            project_id,
            handoff.handoff_id,
            handoff.session_capability,
            data_root=data_root,
        )

    status = status_handoff(project_id, handoff.handoff_id, data_root=data_root)
    assert status["state"] == "prepared"


def test_delivered_without_ack_remains_unacknowledged(tmp_path: Path) -> None:
    project_id, data_root = _register(tmp_path)
    from rush.workflows.projects import resolve_project

    root = Path(resolve_project(project_id, data_root=data_root)["root"])
    _write_manifest(root, "run-ack", findings=[_finding("finding-1")])

    handoff = build_handoff(project_id, "run-ack", "codex-cli", data_root=data_root)
    dispatch_handoff(
        project_id, handoff.handoff_id, handoff.session_capability, data_root=data_root
    )

    status = status_handoff(project_id, handoff.handoff_id, data_root=data_root)
    assert status["state"] == "delivered"

    with pytest.raises(ScanHandoffAuthError):
        acknowledge_handoff(
            project_id, handoff.handoff_id, "wrong-nonce", data_root=data_root
        )

    # A rejected wrong-nonce attempt never advances state either.
    status_again = status_handoff(project_id, handoff.handoff_id, data_root=data_root)
    assert status_again["state"] == "delivered"


def test_acknowledge_before_dispatch_is_invalid_state(tmp_path: Path) -> None:
    project_id, data_root = _register(tmp_path)
    from rush.workflows.projects import resolve_project

    root = Path(resolve_project(project_id, data_root=data_root)["root"])
    _write_manifest(root, "run-order", findings=[_finding("finding-1")])

    handoff = build_handoff(project_id, "run-order", "codex-cli", data_root=data_root)
    with pytest.raises(ScanHandoffInvalidStateError):
        acknowledge_handoff(
            project_id, handoff.handoff_id, handoff.delivery_nonce, data_root=data_root
        )


def test_complete_before_acknowledge_is_invalid_state(tmp_path: Path) -> None:
    project_id, data_root = _register(tmp_path)
    from rush.workflows.projects import resolve_project

    root = Path(resolve_project(project_id, data_root=data_root)["root"])
    _write_manifest(root, "run-order2", findings=[_finding("finding-1")])

    handoff = build_handoff(project_id, "run-order2", "codex-cli", data_root=data_root)
    dispatch_handoff(
        project_id, handoff.handoff_id, handoff.session_capability, data_root=data_root
    )
    with pytest.raises(ScanHandoffInvalidStateError):
        complete_handoff(
            project_id, handoff.handoff_id, handoff.delivery_nonce, data_root=data_root
        )


def test_unknown_run_id_and_handoff_id_are_invalid_request(tmp_path: Path) -> None:
    project_id, data_root = _register(tmp_path)
    with pytest.raises(ScanInvalidRequestError):
        build_handoff(project_id, "no-such-run", "codex-cli", data_root=data_root)
    with pytest.raises(ScanInvalidRequestError):
        status_handoff(project_id, "no-such-handoff", data_root=data_root)


def test_wrong_session_capability_denies_dispatch(tmp_path: Path) -> None:
    project_id, data_root = _register(tmp_path)
    from rush.workflows.projects import resolve_project

    root = Path(resolve_project(project_id, data_root=data_root)["root"])
    _write_manifest(root, "run-cap", findings=[_finding("finding-1")])

    handoff = build_handoff(project_id, "run-cap", "codex-cli", data_root=data_root)
    with pytest.raises(ScanHandoffAuthError):
        dispatch_handoff(
            project_id, handoff.handoff_id, "wrong-capability", data_root=data_root
        )


def test_scanhandofftool_envelope_prepare_requires_run_id_and_agent_id(
    tmp_path: Path,
) -> None:
    project_id, data_root = _register(tmp_path)

    import rush.workflows.projects as projects_module

    original_default_data_root = projects_module.default_data_root
    projects_module.default_data_root = lambda: data_root
    try:
        response = ScanHandoffTool().handle_request(
            {"schema_version": 1, "operation": "prepare", "project": project_id}
        )
    finally:
        projects_module.default_data_root = original_default_data_root

    assert response["status"] == "error"
    assert response["raw"]["error"]["code"] == "INVALID_REQUEST"


def test_scanhandofftool_flat_run_denies_prepare_without_scope(tmp_path: Path) -> None:
    project_id, data_root = _register(tmp_path)
    from rush.workflows.projects import resolve_project

    root = Path(resolve_project(project_id, data_root=data_root)["root"])
    _write_manifest(root, "run-scope", findings=[_finding("finding-1")])

    result = ScanHandoffTool().run(
        Path(project_id),
        action="prepare",
        run_id="run-scope",
        agent_id="codex-cli",
        data_root=data_root,
    )
    assert result["status"] == "skipped"


def test_scanhandofftool_flat_run_full_lifecycle(tmp_path: Path) -> None:
    project_id, data_root = _register(tmp_path)
    from rush.workflows.projects import resolve_project

    root = Path(resolve_project(project_id, data_root=data_root)["root"])
    _write_manifest(root, "run-tool", findings=[_finding("finding-1")])

    perms = ExecutionPermissions(cache_write=True, artifact_write=True)
    prepare_result = ScanHandoffTool().run(
        Path(project_id),
        action="prepare",
        run_id="run-tool",
        agent_id="codex-cli",
        permissions=perms,
        data_root=data_root,
    )
    assert prepare_result["status"] == "ok"
    handoff_id = prepare_result["raw"]["handoff_id"]
    session_capability = prepare_result["raw"]["session_capability"]
    delivery_nonce = prepare_result["raw"]["delivery_nonce"]

    dispatch_result = ScanHandoffTool().run(
        Path(project_id),
        action="dispatch",
        handoff_id=handoff_id,
        session_capability=session_capability,
        permissions=perms,
        data_root=data_root,
    )
    assert dispatch_result["status"] == "ok"
    assert dispatch_result["raw"]["state"] == "delivered"

    ack_result = ScanHandoffTool().run(
        Path(project_id),
        action="acknowledge",
        handoff_id=handoff_id,
        delivery_nonce=delivery_nonce,
        permissions=perms,
        data_root=data_root,
    )
    assert ack_result["status"] == "ok"
    assert ack_result["raw"]["state"] == "acknowledged"
