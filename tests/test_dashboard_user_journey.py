"""Tests for Phase 66 P66-07: real interface acceptance (F41).

Exercises `scripts.benchmarks.run.run_dashboard_user_journey` -- the
dashboard-HTTP extension of the shared, single P65-09 journey builder
(`run_project_journey`, also embedded as its `ui_journey` key so the CLI
`--suite project_journey` report carries the same evidence; no second
harness) -- against the real `create_dashboard_server` HTTP boundary the
browser and `rush ui` both share: add project -> provision -> scan ->
findings -> handoff -> rescan -> memory -> tokens -> Git -> artifact.

Every stage below asserts its own named `coverage[...]` flag rather than a
blanket "journey succeeded" check, so a missing section/control fails a
named assertion instead of passing silently. `errors` carries a
human-readable reason for any stage that failed, surfaced in the assertion
message rather than requiring a debugger.
"""

from __future__ import annotations

from typing import Any

import pytest

from scripts.benchmarks.run import run_dashboard_user_journey


@pytest.fixture(scope="module")
def ui_journey(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Runs the whole real dashboard HTTP journey exactly once; every test
    below asserts a different stage of this single, shared execution."""
    tmp_root = tmp_path_factory.mktemp("dashboard-user-journey")
    return run_dashboard_user_journey(tmp_root)


def _assert_stage(ui_journey: dict[str, Any], stage: str) -> None:
    assert ui_journey["coverage"].get(stage) is True, (
        f"stage {stage!r} did not pass: {ui_journey['errors']}"
    )


def test_session_bootstraps_and_reports_time_to_first_interactive(
    ui_journey: dict[str, Any],
) -> None:
    _assert_stage(ui_journey, "session_bootstrap")
    ttfi = ui_journey["time_to_first_interactive_ms"]
    assert isinstance(ttfi, float)
    assert 0.0 < ttfi < 5000.0, ttfi


def test_add_project_action_registers_a_real_project(
    ui_journey: dict[str, Any],
) -> None:
    _assert_stage(ui_journey, "add_project")
    assert ui_journey["timings_ms"]["add_project"] > 0.0


def test_provision_plan_action_stages_a_reviewed_scan_plan(
    ui_journey: dict[str, Any],
) -> None:
    _assert_stage(ui_journey, "provision")


def test_scan_start_action_executes_a_real_run(ui_journey: dict[str, Any]) -> None:
    _assert_stage(ui_journey, "scan")


def test_scans_snapshot_returns_real_findings(ui_journey: dict[str, Any]) -> None:
    _assert_stage(ui_journey, "findings")


def test_hostile_finding_text_travels_as_inert_json_never_as_markup(
    ui_journey: dict[str, Any],
) -> None:
    """A real `<script>` payload in a finding's own message must survive the
    scans HTTP section as an untouched JSON string, and neither owned
    rendering asset (`application.js`, `project_map.js`) may use `innerHTML`
    -- the sink that would turn that inert string into executable markup."""
    _assert_stage(ui_journey, "hostile_finding_text")


def test_handoff_preview_and_send_actions_deliver_a_real_handoff(
    ui_journey: dict[str, Any],
) -> None:
    _assert_stage(ui_journey, "handoff")


def test_rescan_action_produces_a_new_run(ui_journey: dict[str, Any]) -> None:
    _assert_stage(ui_journey, "rescan")


def test_memory_write_is_visible_and_editable_through_the_dashboard(
    ui_journey: dict[str, Any],
) -> None:
    _assert_stage(ui_journey, "memory")


def test_tokens_snapshot_reflects_real_telemetry(ui_journey: dict[str, Any]) -> None:
    _assert_stage(ui_journey, "tokens")


def test_git_snapshot_reports_real_repo_identity(ui_journey: dict[str, Any]) -> None:
    _assert_stage(ui_journey, "git")


def test_artifacts_snapshot_lists_real_manifest_entries(
    ui_journey: dict[str, Any],
) -> None:
    _assert_stage(ui_journey, "artifact")


def test_every_named_stage_is_covered_with_no_unexplained_errors(
    ui_journey: dict[str, Any],
) -> None:
    """A missing section/control fails a named assertion rather than being
    silently absent from `coverage` -- every one of the ten journey stages
    must be present and every present stage must have actually passed."""
    expected_stages = {
        "session_bootstrap",
        "add_project",
        "provision",
        "scan",
        "findings",
        "hostile_finding_text",
        "handoff",
        "rescan",
        "memory",
        "tokens",
        "git",
        "artifact",
    }
    assert expected_stages <= ui_journey["coverage"].keys()
    failed = {stage for stage, ok in ui_journey["coverage"].items() if not ok}
    assert failed == set(), ui_journey["errors"]
    assert ui_journey["errors"] == []


def test_browser_and_windows_lanes_are_named_open_blockers_never_omitted(
    ui_journey: dict[str, Any],
) -> None:
    blockers = "\n".join(ui_journey["blockers"])
    assert "pixel layout" in blockers
    assert "keyboard focus ring" in blockers
    assert "Windows console" in blockers
    assert "no usable headless-Chromium" in blockers
