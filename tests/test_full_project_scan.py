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

import os
import subprocess
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

    # One missing engine: semgrep has no owning adapter, ever, and isn't on
    # PATH in this environment -- M17 now routes it through real execution,
    # which reports the genuine not-on-PATH reason instead of a stub.
    assert by_id["semgrep"].outcome == "unavailable"
    assert by_id["semgrep"].result["summary"] == (
        "skipped: semgrep not on PATH (install: see engine docs)"
    )

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


# --- T049: M15/M16/M17 §12-named regression tests ---------------------------


def test_offline_review_dead_asset_license_matrix_all_read_staged_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M15: offline-review, dead-asset, and license-matrix -- the review's
    other named direct readers -- must also operate on the staged copy a
    scan attempt already captured, never the live tree, mirroring the
    slop-tool regression for each of the other affected routes."""
    from rush.engines.staging import stage_inventory, staging_scope
    from rush.tools import offline_runner as offline_runner_module
    from rush.tools.dead_asset import DeadAssetTool
    from rush.tools.license_matrix import LicenseMatrixTool
    from rush.tools.offline_runner import OfflineReviewTool

    root = tmp_path / "project"
    root.mkdir()
    (root / "index.html").write_text('<img src="logo.png">\n', encoding="utf-8")
    (root / "logo.png").write_bytes(b"staged-bytes")
    (root / "pyproject.toml").write_text(
        '[project]\ndependencies = ["safepkg"]\n', encoding="utf-8"
    )
    (root / "app.py").write_text("STAGED_MARKER = 1\n", encoding="utf-8")

    staged_root = tmp_path / "staged"
    staging = stage_inventory(
        root, staged_root, ["index.html", "logo.png", "pyproject.toml", "app.py"]
    )
    with staging_scope(staging):
        # Live content diverges after staging -- every assertion below must
        # reflect the staged bytes captured before this mutation, not this.
        (root / "index.html").write_text("no image reference here\n", encoding="utf-8")
        (root / "pyproject.toml").write_text(
            '[project]\ndependencies = ["riskypkg"]\n', encoding="utf-8"
        )
        (root / "app.py").write_text("LIVE_MARKER = 1\n", encoding="utf-8")

        staged_workspace = staging.stage_path(root)

        dead_asset_result = DeadAssetTool().run(staged_workspace)
        assert not any(
            finding.get("path", "").endswith("logo.png")
            for finding in dead_asset_result.get("findings") or []
        ), "logo.png must still show as referenced via the staged index.html"

        # `package_licenses` keys are audited even when undiscovered, so
        # only the staged manifest's real dependency ("safepkg") gets an
        # override here -- if the tool fell through to live's "riskypkg"
        # instead, that undeclared package would hit the real (unspecified)
        # license lookup and produce a manual-review finding.
        license_result = LicenseMatrixTool().run(
            staged_workspace,
            package_licenses={"safepkg": "MIT"},
        )
        assert license_result.get("findings") == [], (
            "must evaluate staged pyproject.toml's 'safepkg', never live's 'riskypkg'"
        )

        captured_cmd: list[str] = []

        def _fake_run_subprocess(cmd, **_kwargs):
            captured_cmd.extend(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(
            offline_runner_module,
            "discover_local_runner",
            lambda *_a, **_k: {"path": "ollama", "type": "ollama"},
        )
        monkeypatch.setattr(
            offline_runner_module, "run_subprocess", _fake_run_subprocess
        )
        OfflineReviewTool().run(staged_workspace, model="codellama")

    assert any("STAGED_MARKER" in part for part in captured_cmd), (
        "offline-review's prompt must be built from staged source, not live"
    )
    assert not any("LIVE_MARKER" in part for part in captured_cmd)


def test_explicit_configuration_file_target_is_recorded_as_declared_consumption(
    tmp_path: Path,
) -> None:
    """M16 bullet 2: an explicitly passed configuration file belongs in
    declared consumption alongside the engine's file targets -- it is not
    silently dropped just because it is not itself a source scan target."""
    from rush.engines.ruff import RuffEngine
    from rush.engines.staging import stage_inventory, staging_scope
    from rush.runtime.subprocesses import _staged_invocation

    root = tmp_path / "project"
    root.mkdir()
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    (root / "b.js").write_text("const y = 1;\n", encoding="utf-8")
    (root / "ruff.toml").write_text("line-length = 100\n", encoding="utf-8")
    staged_root = tmp_path / "staged"
    staging = stage_inventory(root, staged_root, ["a.py", "b.js", "ruff.toml"])
    with staging_scope(staging):
        _staged_invocation(
            RuffEngine(),
            root,
            root,
            [str(root / "a.py"), "--config", str(root / "ruff.toml")],
            consumed_paths=[str(root / "a.py"), str(root / "ruff.toml")],
        )
        consumed = staging.take_candidate_digests()

    assert set(consumed) == {"a.py", "ruff.toml"}, (
        "an explicit configuration file target must be declared consumption "
        "alongside the file target, and b.js must still not be claimed"
    )


def test_unregistered_engine_stays_engine_route_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M17 bullet 3: a registered `ENGINE_SPECS` row with no matching
    `ENGINES` runtime entry is an honest `ENGINE_ROUTE_MISSING` skip --
    never an invented tool route."""
    import rush.engines as engines_module

    monkeypatch.setattr(engines_module, "ENGINES", {})
    candidate = project_run.ScanCandidate(
        "semgrep", "engine", "security", "applicable", "static_analysis_default"
    )

    outcome, result = project_run._execute_candidate(
        candidate,
        root=tmp_path,
        permissions=ExecutionPermissions(),
        targets={},
        config=None,
        tools_by_name={},
    )

    assert outcome == "unavailable"
    assert "ENGINE_ROUTE_MISSING" in result["summary"]


def test_registered_engine_with_absent_binary_returns_structured_skipped_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M17 bullet 3: a registered engine whose binary is genuinely absent
    from PATH returns `run_engine`'s structured skipped result --
    `unavailable`, never a route-missing gap or an invented tool stub."""
    import rush.tools.common as common_module

    monkeypatch.setattr(common_module, "engine_on_path", lambda _binary: False)
    candidate = project_run.ScanCandidate(
        "semgrep", "engine", "security", "applicable", "static_analysis_default"
    )

    outcome, result = project_run._execute_candidate(
        candidate,
        root=tmp_path,
        permissions=ExecutionPermissions(),
        targets={},
        config=None,
        tools_by_name={},
    )

    assert outcome == "unavailable"
    assert "not on PATH" in result["summary"]


def test_denied_explicit_permission_returns_permission_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M17 bullet 3: an applicable candidate whose real required permission
    is not granted returns `permission_blocked` -- distinct from an
    unavailable/route-missing skip."""
    _use_curated_tools(monkeypatch)
    project_id, data_root = _register(tmp_path)

    plan = plan_scan(project_id, data_root=data_root)
    run = execute_scan(plan, permissions=ExecutionPermissions(), data_root=data_root)

    by_id = {item.candidate.candidate_id: item for item in run.candidate_results}
    assert by_id["ai-eval"].outcome == "permission_blocked"


def test_gitguard_candidate_executes_through_execute_scan_with_a_real_or_fixture_engine_binary_and_persists_evidence(
    tmp_path: Path,
) -> None:
    """M17 bullet 4: an applicable GitGuard/repository-state candidate,
    executed through the real, un-monkeypatched `execute_scan` route (no
    dummy owning tool), actually subprocess-executes against `git` (always
    present here) and persists real repository-state evidence -- not a
    skipped/unavailable stub."""
    root = tmp_path / "project"
    root.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)
    (root / "app.py").write_text("print('hi')\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=root, check=True)
    git_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "seed"], cwd=root, check=True, env=git_env
    )

    data_root = tmp_path / "rush-data"
    record = register_project(root, data_root=data_root)

    plan = plan_scan(record.project_id, data_root=data_root)
    run = execute_scan(
        plan,
        permissions=ExecutionPermissions(cache_write=True, artifact_write=True),
        data_root=data_root,
    )

    by_id = {item.candidate.candidate_id: item for item in run.candidate_results}
    assert by_id["git-guard"].outcome == "executed"
    assert by_id["git-guard"].repository_state_evidence
