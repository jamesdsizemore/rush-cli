"""Tests for Phase 65 P65-06.1/.2: verified rescan comparison (F35).

`compare_runs` marks every baseline finding `resolved`, `persisting`, or
`unverified`, and every current-only finding `new` (plan §6.1/§6.4).
Fixture manifests are written directly against the real, documented
`project_run` manifest schema -- see `test_scan_handoff.py`'s module
docstring for why that is a legitimate way to test a function whose entire
contract is "given two persisted run manifests, compare them."
`test_rescan_project_run_against_a_real_execute_scan_run` additionally
exercises `rescan_project_run` against a real `plan_scan`/`execute_scan`
pair so the manifest-schema fixtures below are never the only path
exercised.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rush.permissions import ExecutionPermissions
from rush.tools.review import ReviewTool
from rush.workflows import project_run
from rush.workflows.project_run import (
    ScanInvalidRequestError,
    compare_runs,
    execute_scan,
    plan_scan,
    rescan_project_run,
)
from rush.workflows.projects import register_project, resolve_project


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
    finding_id: str, *, tool: str = "eslint", engine: str = "engine-a"
) -> dict[str, object]:
    return {
        "finding_id": finding_id,
        "path": "app.py",
        "line": 1,
        "column": 0,
        "rule": "seeded-rule",
        "severity": "warn",
        "message": "issue",
        "provenance": f"{tool}/{engine}",
    }


def _write_manifest(
    root: Path,
    run_id: str,
    *,
    findings: list[dict[str, object]],
    scheduled: list[dict[str, object]],
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
        "scheduled": scheduled,
        "totals": {"finding_count": len(findings)},
    }
    (manifest_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


def _executed(candidate_id: str) -> dict[str, object]:
    return {"candidate_id": candidate_id, "outcome": "executed"}


def _unavailable(candidate_id: str) -> dict[str, object]:
    return {"candidate_id": candidate_id, "outcome": "unavailable"}


def test_fixed_finding_is_resolved(tmp_path: Path) -> None:
    project_id, data_root = _register(tmp_path)
    root = Path(resolve_project(project_id, data_root=data_root)["root"])

    fixed = _finding("finding-fixed")
    _write_manifest(root, "run-a", findings=[fixed], scheduled=[_executed("eslint")])
    _write_manifest(root, "run-b", findings=[], scheduled=[_executed("eslint")])

    comparison = compare_runs(project_id, "run-a", "run-b", data_root=data_root)
    assert comparison["resolved"] == ["finding-fixed"]
    assert comparison["persisting"] == []
    assert comparison["new"] == []
    assert comparison["unverified"] == []
    assert comparison["verdicts"]["finding-fixed"] == "resolved"


def test_persisting_finding_stays_persisting(tmp_path: Path) -> None:
    project_id, data_root = _register(tmp_path)
    root = Path(resolve_project(project_id, data_root=data_root)["root"])

    persistent = _finding("finding-persists")
    _write_manifest(
        root, "run-a", findings=[persistent], scheduled=[_executed("eslint")]
    )
    _write_manifest(
        root, "run-b", findings=[persistent], scheduled=[_executed("eslint")]
    )

    comparison = compare_runs(project_id, "run-a", "run-b", data_root=data_root)
    assert comparison["persisting"] == ["finding-persists"]
    assert comparison["resolved"] == []
    assert comparison["new"] == []
    assert comparison["unverified"] == []


def test_new_finding_in_current_run_is_new(tmp_path: Path) -> None:
    project_id, data_root = _register(tmp_path)
    root = Path(resolve_project(project_id, data_root=data_root)["root"])

    _write_manifest(root, "run-a", findings=[], scheduled=[_executed("eslint")])
    new_finding = _finding("finding-new")
    _write_manifest(
        root, "run-b", findings=[new_finding], scheduled=[_executed("eslint")]
    )

    comparison = compare_runs(project_id, "run-a", "run-b", data_root=data_root)
    assert comparison["new"] == ["finding-new"]
    assert comparison["resolved"] == []
    assert comparison["persisting"] == []
    assert comparison["unverified"] == []


def test_missing_engine_in_current_run_is_unverified_never_resolved(
    tmp_path: Path,
) -> None:
    project_id, data_root = _register(tmp_path)
    root = Path(resolve_project(project_id, data_root=data_root)["root"])

    finding = _finding("finding-1")
    _write_manifest(root, "run-a", findings=[finding], scheduled=[_executed("eslint")])
    # eslint did not execute in the current run (e.g. removed from PATH) -- the
    # finding disappearing from the aggregate must never read as "resolved".
    _write_manifest(root, "run-b", findings=[], scheduled=[_unavailable("eslint")])

    comparison = compare_runs(project_id, "run-a", "run-b", data_root=data_root)
    assert comparison["unverified"] == ["finding-1"]
    assert comparison["resolved"] == []
    assert comparison["persisting"] == []
    assert comparison["new"] == []


def test_unknown_run_id_is_invalid_request(tmp_path: Path) -> None:
    project_id, data_root = _register(tmp_path)
    root = Path(resolve_project(project_id, data_root=data_root)["root"])
    _write_manifest(root, "run-a", findings=[], scheduled=[])

    with pytest.raises(ScanInvalidRequestError):
        compare_runs(project_id, "run-a", "no-such-run", data_root=data_root)
    with pytest.raises(ScanInvalidRequestError):
        compare_runs(project_id, "no-such-run", "run-a", data_root=data_root)


def test_rescan_project_run_against_a_real_execute_scan_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(project_run, "ALL_TOOLS", [ReviewTool()])
    project_id, data_root = _register(tmp_path)
    plan = plan_scan(project_id, data_root=data_root)
    baseline = execute_scan(
        plan, permissions=ExecutionPermissions(), data_root=data_root
    )

    result = rescan_project_run(project_id, baseline.run_id, data_root=data_root)

    assert result["run"]["run_id"] != baseline.run_id
    comparison = result["comparison"]
    assert comparison["baseline_run_id"] == baseline.run_id
    assert comparison["current_run_id"] == result["run"]["run_id"]
    # Same unmodified source, same tool: every seeded finding must persist,
    # never silently "resolved".
    baseline_finding_ids = {
        f["finding_id"] for f in baseline.aggregate.get("findings") or []
    }
    assert baseline_finding_ids, "expected at least one seeded finding"
    assert set(comparison["persisting"]) == baseline_finding_ids
    assert comparison["resolved"] == []
