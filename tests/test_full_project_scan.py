"""Tests for Phase 65 P65-04: full-project scan, complete coverage, one
aggregate (F34-35).

Fixture: a mixed Python/JS/IaC/docs project with one seeded review finding
(a Python function without a docstring), one engine-only catalog entry with
no adapter (`semgrep` -- deterministic across every machine, real or CI, since
Rush has no scan adapter for it regardless of what's on PATH), one denied
"slow"/grant-gated check (`ai-eval`, real tool, no permission granted), and
one monkeypatched runtime failure (`typecheck`, raising at call time). Every
catalog candidate must get exactly one reasoned disposition and every
applicable candidate exactly one scheduled child -- no skipped child ever
counts as executed, and coverage stays honestly incomplete.

`ALL_TOOLS` is monkeypatched to a small, deterministic tool set for these
fixture tests -- the real, un-monkeypatched candidate set (54 tools + 89
engine-only catalog rows) is exercised directly in
`test_real_candidate_set_has_no_gaps` without executing every real tool
(execution against the entire real inventory is slow and environment-
dependent; see `docs/phase-plans/phase-65-project-provisioning-scan-and-
agent-workflow-plan.md` §6.4 for why an engine-only entry with no PATH
binary and no adapter are both real, honest, distinct gaps).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rush.permissions import ExecutionPermissions
from rush.tools.ai_eval import AiEvalTool
from rush.tools.review import ReviewTool
from rush.tools.scan import ScanTool
from rush.workflows import project_run
from rush.workflows.project_run import (
    ScanInvalidRequestError,
    execute_scan,
    load_run_manifest,
    load_scan_plan,
    plan_scan,
)
from rush.workflows.projects import register_project


class _BrokenTypecheck:
    """Reuses the real `typecheck` catalog name so classification (category
    'quality', not workflow/importer/browser_runtime) matches the real tool
    it stands in for; only the call behavior is faked, deterministically."""

    name = "typecheck"

    def __call__(self, path: Path) -> dict[str, object]:
        raise RuntimeError("typecheck adapter crashed")


def _fixture_root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("def unreviewed():\n    pass\n", encoding="utf-8")
    (root / "web").mkdir()
    (root / "web" / "index.js").write_text("console.log('hi');\n", encoding="utf-8")
    (root / "infra").mkdir()
    (root / "infra" / "main.tf").write_text(
        'resource "null_resource" "x" {}\n', encoding="utf-8"
    )
    (root / "README.md").write_text("# Fixture project\n", encoding="utf-8")
    return root


def _data_root(tmp_path: Path) -> Path:
    return tmp_path / "rush-data"


def _register(tmp_path: Path) -> tuple[str, Path]:
    root = _fixture_root(tmp_path)
    data_root = _data_root(tmp_path)
    record = register_project(root, data_root=data_root)
    return record.project_id, data_root


class _NamedStub:
    """A candidate-set placeholder for a real catalog name whose disposition
    is decided entirely by `TOOL_SPECS` (category/maturity) before any tool
    object is touched -- `not_applicable`/`requires_input` candidates are
    never scheduled, so they never need a real, callable implementation
    here. Keeps fixture execution fast and deterministic while still
    exercising the real catalog's classification for these names."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __call__(self, path: Path) -> dict[str, object]:  # pragma: no cover
        raise AssertionError(f"{self.name} must never be scheduled for execution")


def _use_curated_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deterministic, fast tool set: one real executed check with a seeded
    finding, one real permission-denied check, one monkeypatched failure,
    plus name-only stubs for real workflow/importer catalog rows."""
    monkeypatch.setattr(
        project_run,
        "ALL_TOOLS",
        [
            ReviewTool(),
            AiEvalTool(),
            _BrokenTypecheck(),
            _NamedStub("memory"),
            _NamedStub("coverage"),
            _NamedStub("release"),
            _NamedStub("patch-apply"),
            _NamedStub("ci"),
            _NamedStub("continuity"),
        ],
    )


def test_plan_gives_every_catalog_candidate_exactly_one_disposition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_curated_tools(monkeypatch)
    project_id, data_root = _register(tmp_path)

    plan = plan_scan(project_id, data_root=data_root)

    candidate_ids = [c.candidate_id for c in plan.candidates]
    assert len(candidate_ids) == len(set(candidate_ids)), "duplicate candidate ids"
    assert {"review", "ai-eval", "typecheck"} <= set(candidate_ids)
    assert "semgrep" in candidate_ids, (
        "engine-only catalog entry must still be a candidate"
    )

    by_id = {c.candidate_id: c for c in plan.candidates}
    assert by_id["review"].disposition == "applicable"
    assert by_id["ai-eval"].disposition == "applicable"
    assert by_id["typecheck"].disposition == "applicable"
    assert by_id["semgrep"].disposition == "applicable"
    # `memory`/`continuity`-style catalog tools are non-scan workflow ops --
    # real catalog rows, not injected here, so assert on real known ones.
    assert by_id["memory"].disposition == "not_applicable"
    assert by_id["memory"].reason == "non_scan_workflow_operation"
    # `coverage` has `maturity="importer"` -- a report-only adapter.
    assert by_id["coverage"].disposition == "requires_input"

    for candidate in plan.candidates:
        assert candidate.disposition in {
            "applicable",
            "not_applicable",
            "requires_input",
            "unsupported",
            "excluded_by_user",
        }
        assert candidate.reason


def test_full_scan_covers_seeded_missing_engine_denied_and_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_curated_tools(monkeypatch)
    project_id, data_root = _register(tmp_path)

    plan = plan_scan(project_id, data_root=data_root)
    run = execute_scan(plan, permissions=ExecutionPermissions(), data_root=data_root)

    by_id = {item.candidate.candidate_id: item for item in run.candidate_results}

    # Real seeded issue: review's missing-docstring heuristic on app.py.
    review_result = by_id["review"]
    assert review_result.outcome == "executed"
    assert any(
        finding.get("rule") == "missing-docstring"
        for finding in review_result.result.get("findings") or []
    )
    assert all(
        "finding_id" in finding
        for finding in review_result.result.get("findings") or []
    )

    # One missing engine: semgrep has no owning adapter, ever.
    assert by_id["semgrep"].outcome == "unavailable"
    assert by_id["semgrep"].result["summary"] == "skipped: ENGINE_ROUTE_MISSING"

    # One denied slow/grant-gated check: ai-eval, no permission granted.
    assert by_id["ai-eval"].outcome == "permission_blocked"

    # One runtime failure: typecheck adapter raised.
    assert by_id["typecheck"].outcome == "failed"
    assert "typecheck adapter crashed" in by_id["typecheck"].result["summary"]

    # No skipped child ever counts as executed.
    executed_ids = {
        item.candidate.candidate_id
        for item in run.candidate_results
        if item.outcome == "executed"
    }
    assert "semgrep" not in executed_ids
    assert "ai-eval" not in executed_ids
    assert "typecheck" not in executed_ids

    # Incomplete coverage is honest, not silently "clean".
    assert run.run_state == "incomplete"
    assert run.aggregate["status"] != "ok" or any(
        item.outcome != "executed" for item in run.candidate_results
    )


def test_stable_finding_provenance_across_two_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_curated_tools(monkeypatch)
    project_id, data_root = _register(tmp_path)
    plan = plan_scan(project_id, data_root=data_root)

    first = execute_scan(plan, permissions=ExecutionPermissions(), data_root=data_root)
    second = execute_scan(plan, permissions=ExecutionPermissions(), data_root=data_root)

    def review_finding_ids(run):
        review = next(
            item
            for item in run.candidate_results
            if item.candidate.candidate_id == "review"
        )
        return sorted(f["finding_id"] for f in review.result.get("findings") or [])

    assert review_finding_ids(first) == review_finding_ids(second)
    assert review_finding_ids(first), "expected at least one seeded finding"


def test_run_manifest_is_persisted_and_immutable_terminal_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_curated_tools(monkeypatch)
    project_id, data_root = _register(tmp_path)
    plan = plan_scan(project_id, data_root=data_root)
    run = execute_scan(plan, permissions=ExecutionPermissions(), data_root=data_root)

    manifest_path = Path(run.manifest_path)
    assert manifest_path.is_file()

    reloaded = load_run_manifest(Path(run.root), run.run_id)
    assert reloaded is not None
    assert reloaded["run_id"] == run.run_id
    assert reloaded["run_state"] == "incomplete"
    assert reloaded["totals"]["candidate_count"] == len(plan.candidates)
    assert reloaded["totals"]["scheduled_count"] == len(run.candidate_results)
    assert reloaded["totals"]["executed_count"] == sum(
        1 for item in run.candidate_results if item.outcome == "executed"
    )


def test_coverage_denominator_unchanged_when_an_engine_disappears(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Excluding a candidate at plan time keeps it in the candidate count
    (denominator) -- it is `excluded_by_user`, never removed from coverage."""
    _use_curated_tools(monkeypatch)
    project_id, data_root = _register(tmp_path)

    full_plan = plan_scan(project_id, data_root=data_root)
    reduced_plan = plan_scan(project_id, exclude=("review",), data_root=data_root)

    assert len(full_plan.candidates) == len(reduced_plan.candidates)
    by_id = {c.candidate_id: c for c in reduced_plan.candidates}
    assert by_id["review"].disposition == "excluded_by_user"


def test_no_checks_applicable_reports_empty_coverage_not_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(project_run, "ALL_TOOLS", [])
    monkeypatch.setattr(project_run, "ENGINE_SPECS", {})
    project_id, data_root = _register(tmp_path)

    plan = plan_scan(project_id, data_root=data_root)
    assert plan.candidates == ()

    run = execute_scan(plan, permissions=ExecutionPermissions(), data_root=data_root)
    assert run.run_state == "completed"
    assert run.aggregate["metadata"]["coverage"] == {"empty": True}


def test_explicit_target_upgrades_requires_input_to_applicable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_curated_tools(monkeypatch)
    project_id, data_root = _register(tmp_path)

    plan = plan_scan(
        project_id,
        targets={"coverage": {"config_path": "pyproject.toml"}},
        data_root=data_root,
    )
    by_id = {c.candidate_id: c for c in plan.candidates}
    assert by_id["coverage"].disposition == "applicable"
    assert by_id["coverage"].reason == "explicit_target_provided"


def test_unknown_tool_id_in_exclude_or_targets_is_invalid_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_curated_tools(monkeypatch)
    project_id, data_root = _register(tmp_path)

    with pytest.raises(ScanInvalidRequestError):
        plan_scan(project_id, exclude=("not-a-real-tool",), data_root=data_root)

    with pytest.raises(ScanInvalidRequestError):
        plan_scan(project_id, targets={"not-a-real-tool": {}}, data_root=data_root)


def test_run_requires_a_previously_staged_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`rush_scan.run(project, plan_id, install)` carries no other scan
    parameters (plan §6.1) -- the plan must already be staged by `plan_id`."""
    _use_curated_tools(monkeypatch)
    project_id, data_root = _register(tmp_path)
    plan = plan_scan(project_id, data_root=data_root)

    reloaded = load_scan_plan(Path(plan.root), plan.plan_id)
    assert reloaded is not None
    assert reloaded.plan_id == plan.plan_id
    assert reloaded.candidates == plan.candidates

    assert load_scan_plan(Path(plan.root), "not-a-real-plan-id") is None


def test_real_candidate_set_has_no_gaps(tmp_path: Path) -> None:
    """Against the real, un-monkeypatched catalog (54 `ALL_TOOLS` + 89
    engine-only rows with no owning `TOOL_SPECS`), every candidate still
    gets exactly one disposition and every disposition is a real enum
    value -- no candidate is silently dropped from the plan. Does not call
    `execute_scan`: running the entire real inventory is slow and
    environment-dependent (see module docstring); classification alone is
    fast and deterministic."""
    project_id, data_root = _register(tmp_path)

    plan = plan_scan(project_id, data_root=data_root)

    candidate_ids = [c.candidate_id for c in plan.candidates]
    assert len(candidate_ids) == len(set(candidate_ids))
    assert len(plan.candidates) >= 54 + 80  # 54 ALL_TOOLS + engine-only rows

    valid_dispositions = {
        "applicable",
        "not_applicable",
        "requires_input",
        "unsupported",
        "excluded_by_user",
    }
    for candidate in plan.candidates:
        assert candidate.disposition in valid_dispositions
        assert candidate.reason

    by_id = {c.candidate_id: c for c in plan.candidates}
    assert by_id["semgrep"].kind == "engine"
    assert by_id["semgrep"].disposition == "applicable"
    assert by_id["memory"].kind == "tool"
    assert by_id["memory"].disposition == "not_applicable"


def test_destructive_workflow_tools_never_scheduled_as_scanners(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_curated_tools(monkeypatch)
    project_id, data_root = _register(tmp_path)
    plan = plan_scan(project_id, data_root=data_root)

    workflow_ids = {"release", "patch-apply", "ci", "memory", "continuity"}
    by_id = {c.candidate_id: c for c in plan.candidates}
    for tool_id in workflow_ids:
        assert by_id[tool_id].disposition == "not_applicable"
        assert by_id[tool_id].reason == "non_scan_workflow_operation"

    run = execute_scan(plan, permissions=ExecutionPermissions(), data_root=data_root)
    scheduled_ids = {item.candidate.candidate_id for item in run.candidate_results}
    assert workflow_ids.isdisjoint(scheduled_ids)


def test_scantool_flat_plan_run_status_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_curated_tools(monkeypatch)
    project_id, data_root = _register(tmp_path)
    tool = ScanTool()

    plan_result = tool.run(Path(project_id), action="plan", data_root=data_root)
    assert plan_result["status"] == "ok"
    plan_id = plan_result["raw"]["plan_id"]

    denied = tool.run(
        Path(project_id), action="run", plan_id=plan_id, data_root=data_root
    )
    assert denied["status"] == "skipped"

    run_result = tool.run(
        Path(project_id),
        action="run",
        plan_id=plan_id,
        permissions=ExecutionPermissions(cache_write=True, artifact_write=True),
        data_root=data_root,
    )
    assert run_result["status"] == "ok"
    run_id = run_result["raw"]["run_id"]
    assert run_result["raw"]["run_state"] == "incomplete"

    status_page = tool.run(
        Path(project_id), action="status", run_id=run_id, limit=1, data_root=data_root
    )
    assert status_page["status"] == "ok"
    first_page = status_page["raw"]
    assert len(first_page["scheduled"]) == 1
    assert first_page["next_cursor"] is not None

    second_page = tool.run(
        Path(project_id),
        action="status",
        run_id=run_id,
        limit=1,
        cursor=first_page["next_cursor"],
        data_root=data_root,
    )
    assert (
        second_page["raw"]["scheduled"][0]["candidate_id"]
        != (first_page["scheduled"][0]["candidate_id"])
    )


def test_scantool_handle_request_plan_and_run_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_curated_tools(monkeypatch)
    project_id, data_root = _register(tmp_path)

    import rush.workflows.projects as projects_module

    original_default_data_root = projects_module.default_data_root
    projects_module.default_data_root = lambda: data_root
    try:
        plan_response = ScanTool().handle_request(
            {"schema_version": 1, "operation": "plan", "project": project_id}
        )
        assert plan_response["status"] == "ok"
        assert plan_response["raw"]["schema_version"] == 1
        assert plan_response["raw"]["error"] is None
        plan_id = plan_response["raw"]["data"]["plan_id"]

        run_response = ScanTool().handle_request(
            {
                "schema_version": 1,
                "operation": "run",
                "project": project_id,
                "plan_id": plan_id,
                "allow_cache_write": True,
                "allow_artifact_write": True,
            }
        )
    finally:
        projects_module.default_data_root = original_default_data_root

    assert run_response["status"] == "ok"
    assert run_response["raw"]["data"]["plan_id"] == plan_id


def test_scantool_handle_request_run_denied_without_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_curated_tools(monkeypatch)
    project_id, data_root = _register(tmp_path)

    import rush.workflows.projects as projects_module

    original_default_data_root = projects_module.default_data_root
    projects_module.default_data_root = lambda: data_root
    try:
        plan_response = ScanTool().handle_request(
            {"schema_version": 1, "operation": "plan", "project": project_id}
        )
        plan_id = plan_response["raw"]["data"]["plan_id"]

        run_response = ScanTool().handle_request(
            {
                "schema_version": 1,
                "operation": "run",
                "project": project_id,
                "plan_id": plan_id,
            }
        )
    finally:
        projects_module.default_data_root = original_default_data_root

    assert run_response["status"] == "error"
    assert run_response["raw"]["error"]["code"] == "SCOPE_DENIED"


def test_scantool_handle_request_rejects_unknown_field(tmp_path: Path) -> None:
    result = ScanTool().handle_request(
        {"schema_version": 1, "operation": "plan", "project": "x", "bogus": 1}
    )
    assert result["status"] == "error"
    assert result["raw"]["error"]["code"] == "INVALID_REQUEST"
