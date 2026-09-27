"""Phase 70 T28-A (TUI workspace, navigation, truthful shared state):
failing-first test matrix, written against the binding design in
`.scratch/phase-70-design-gate/W4-T23-T29.md` (T28-A section and the T28
"Shared design (all packets)" section) and the T28-A packet in
`docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md`.

None of T28-A's new state model (Overview section, `registration`,
per-section truthful states, an 8-section chooser) is merged yet -- every
`test_t28a_*` case below drives the real, currently-merged entry points
(`render_app`, `_dispatch_key`, `run_interactive_tui`, `ui_cmd`,
`project_snapshot`, `read_registry_strict`) and asserts the *new*,
not-yet-true behavior. Cases that would otherwise crash on a missing
dataclass field are wrapped so the failure surfaces as a descriptive
`pytest.fail`/`AssertionError`, never a bare traceback.

`test_t28a_keepgreen_*` cases assert current, already-shipped behavior that
T28-A must not regress; they pass today and must keep passing after T28-A
lands.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner
from rich.console import Console

from rush.tools.base import Finding, ToolResult
from rush.tui import (
    ProjectSeed,
    ProjectState,
    TuiState,
    _dispatch_key,
    default_scan_actions,
    render_app,
    run_interactive_tui,
)
from rush.workflows.projects import (
    ProjectNotFoundError,
    project_snapshot,
    read_registry_strict,
    register_project,
)


def _render_text(state: TuiState, *, width: int = 100) -> str:
    console = Console(record=True, width=width)
    console.print(render_app(state))
    return console.export_text()


def _project_with_registration(
    root: Path, registration: dict[str, Any], **extra: Any
) -> ProjectState:
    """`ProjectState` does not yet carry a `registration` field (T28-A's
    shared design: "`ProjectState` gains ... `registration` ..."). Building
    one is exactly what a T28-A-aware caller will do once it lands; today it
    must raise `TypeError`, which we turn into a readable failure instead of
    a bare traceback."""
    try:
        return ProjectState(name="demo", root=root, registration=registration, **extra)
    except TypeError as exc:
        pytest.fail(
            "ProjectState must accept a `registration` field carrying the "
            "project's registry state (none/ok/moved/corrupt/unreadable) so "
            f"Overview can render it truthfully -- not yet supported: {exc}"
        )


def _zero_finding_result(status: str, summary: str) -> ToolResult:
    return ToolResult(
        tool="lint",
        status=status,  # type: ignore[typeddict-item]
        duration_ms=1,
        summary=summary,
        findings=[],
    )


def test_t28a_workspace_and_outcomes() -> None:
    """Design brief T28-A bullet 1 / plan RED->GREEN: a clean pass, a
    skipped-missing-engine result and an engine error, all with zero
    findings, must render distinct outcome text and reasons. Baseline
    (recorded in the design brief) is that all three currently render
    identically."""
    clean = ProjectState(
        name="demo",
        root=Path("/tmp/t28a-clean"),
        results=[_zero_finding_result("ok", "no issues found")],
    )
    skipped = ProjectState(
        name="demo",
        root=Path("/tmp/t28a-skip"),
        results=[_zero_finding_result("skipped", "engine not installed")],
    )
    errored = ProjectState(
        name="demo",
        root=Path("/tmp/t28a-error"),
        results=[_zero_finding_result("error", "engine crashed: exit 1")],
    )

    clean_text = _render_text(TuiState(projects=[clean]))
    skipped_text = _render_text(TuiState(projects=[skipped]))
    errored_text = _render_text(TuiState(projects=[errored]))

    assert len({clean_text, skipped_text, errored_text}) == 3, (
        "clean/skipped/error zero-finding results must render distinct "
        "outcome text; today all three collapse to the same "
        "'Findings (0) page 1/1' table"
    )
    assert "engine not installed" in skipped_text
    assert "engine crashed" in errored_text
    assert "no issues found" in clean_text


def test_t28a_zero_versus_unavailable_counts() -> None:
    """A real zero-finding clean pass must never render the same way as an
    unavailable/skipped tool -- 'zero' and 'unavailable' are different
    states, not both '0'."""
    clean = ProjectState(
        name="demo",
        root=Path("/tmp/t28a-zero"),
        results=[_zero_finding_result("ok", "no issues found")],
    )
    unavailable = ProjectState(
        name="demo",
        root=Path("/tmp/t28a-unavail"),
        results=[_zero_finding_result("skipped", "engine not installed")],
    )
    clean_text = _render_text(TuiState(projects=[clean]))
    unavailable_text = _render_text(TuiState(projects=[unavailable]))
    assert "unavailable" in unavailable_text
    assert "unavailable" not in clean_text
    assert clean_text != unavailable_text


def test_t28a_no_registered_project_shows_chooser_not_crash(tmp_path: Path) -> None:
    """Design brief: 'Empty registry or unregistered cwd: a chooser
    offering add ... create ... or choose later.' Today an unregistered
    project just renders the ordinary findings table with no chooser at
    all."""
    registration = {"state": "none", "reason": "no project registered for this root"}
    project = _project_with_registration(tmp_path, registration)
    text = _render_text(TuiState(projects=[project]))
    assert "choose later" in text.lower() or "add" in text.lower(), (
        "an unregistered project must offer a register/create/choose-later "
        "workspace chooser, not the plain findings table"
    )


def test_t28a_moved_root_shows_relink_action(tmp_path: Path) -> None:
    """Design brief: 'Moved root: relink offered through a reviewed
    ProjectTool relink.'"""
    moved_root = tmp_path / "no-longer-here"
    registration = {"state": "moved", "reason": f"root missing: {moved_root}"}
    project = _project_with_registration(moved_root, registration)
    text = _render_text(TuiState(projects=[project]))
    assert "relink" in text.lower(), (
        "a project whose registered root no longer exists must surface a "
        "relink action, not silently show an empty/blank result"
    )


def test_t28a_corrupt_registry_state_surfaced(tmp_path: Path) -> None:
    """Corrupt registry must be distinguished from 'no project' (X5's
    missing/ok/corrupt/unreadable states), and shown, not silently treated
    as empty."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    from rush.workflows.projects import _registry_path

    registry_path = _registry_path(data_root)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text("{not json", encoding="utf-8")
    # Exercise the real, already-shipped strict reader so this test proves
    # the corrupt state is real, not fabricated in the test itself.
    result = read_registry_strict(data_root)
    assert result["state"] == "corrupt"

    project = _project_with_registration(
        tmp_path / "proj", {"state": result["state"], "reason": result["error"]}
    )
    text = _render_text(TuiState(projects=[project]))
    assert "corrupt" in text.lower(), (
        "Overview must render the real corrupt-registry state (T23/X5), "
        "not silently fall back to an empty/'no project' view"
    )


def test_t28a_first_load_failure_never_blank_success(tmp_path: Path) -> None:
    """Design brief: 'First-load failure never shows blank success.'"""
    project = _project_with_registration(
        tmp_path,
        {"state": "ok", "reason": None},
        views={
            "overview": {
                "state": "failed",
                "reason": "status read failed: permission denied",
            }
        },
    )
    text = _render_text(TuiState(projects=[project]))
    assert "permission denied" in text, (
        "a first-load failure must show its cause, never a blank/'clean' success panel"
    )
    assert "Findings (0)" not in text, (
        "a failed first load must not be rendered as a successful, "
        "empty-findings result"
    )


def test_t28a_refresh_failure_shows_stale_with_cause_and_time() -> None:
    """Design brief: 'Refresh failure shows stale content with cause and
    time.'"""
    project = _project_with_registration(
        Path("/tmp/t28a-stale"),
        {"state": "ok", "reason": None},
        results=[_zero_finding_result("ok", "no issues found")],
        views={
            "overview": {
                "state": "stale",
                "reason": "refresh failed: connection reset",
                "loaded_at": "2026-01-01T00:00:00Z",
            }
        },
    )
    text = _render_text(TuiState(projects=[project]))
    assert "stale" in text.lower()
    assert "connection reset" in text
    assert "2026-01-01" in text


def test_t28a_every_section_reachable() -> None:
    """Design brief: 'section in {overview,map,scans,memory,tokens,git,
    artifacts,setup}' and 'All eight sections reachable through visible
    navigation and F3 section chooser.' Today F3 (`next_section`) only
    cycles the 3-entry legacy `SECTION_CYCLE = ("list", "map", "git")`."""
    project = ProjectState(name="demo", root=Path("/tmp/t28a-sections"))
    state = TuiState(projects=[project])
    actions = default_scan_actions()
    seen_modes: set[str] = {state.mode}
    for _ in range(12):
        _dispatch_key(state, "f3", actions)
        seen_modes.add(getattr(state, "section", state.mode))

    required = {
        "overview",
        "map",
        "scans",
        "memory",
        "tokens",
        "git",
        "artifacts",
        "setup",
    }
    assert required <= seen_modes, (
        "F3 must be able to reach all eight required sections; it currently "
        f"only cycles through {seen_modes!r}"
    )


def test_t28a_delayed_response_after_switching_project_ignored() -> None:
    """Design brief: 'Delayed A response after selecting B.' A stale
    background result for project A that arrives after the user switched to
    project B must never be applied to B's view."""
    project_a = ProjectState(name="A", root=Path("/tmp/t28a-race-a"))
    project_b = ProjectState(name="B", root=Path("/tmp/t28a-race-b"))
    state = TuiState(projects=[project_a, project_b])
    state.active_index = 1  # user already switched to B

    generation_before = getattr(project_a, "generation", None)
    # Simulate A's delayed background response landing after the switch.
    stale_result = {"tool": "lint", "status": "ok", "findings": [], "summary": "stale"}
    apply_result = getattr(project_a, "apply_delayed_result", None)
    if apply_result is None:
        pytest.fail(
            "ProjectState (or TuiState) must expose a generation-guarded "
            "way to apply a background result so a stale response for A "
            "arriving after switching to B is provably dropped -- no such "
            "hook exists yet"
        )
    apply_result(stale_result, generation=generation_before)
    assert stale_result not in project_a.results, (
        "a delayed response for the no-longer-current generation must be "
        "dropped, not merged into project A's results"
    )


def test_t28a_reads_create_no_registry_store_lock_telemetry_files(
    tmp_path: Path,
) -> None:
    """Design brief: 'Zero registry, store, lock, or telemetry files
    created.' `project_snapshot` currently constructs `TypedArtifactStore`
    and `TelemetryStore` (both of which create/migrate on-disk state) as
    part of a supposedly read-only Overview call."""
    data_root = tmp_path / "data"
    project_root = tmp_path / "proj"
    project_root.mkdir()
    record = register_project(project_root, data_root=data_root)

    def _tree(base: Path) -> set[str]:
        if not base.exists():
            return set()
        return {str(p.relative_to(base)) for p in base.rglob("*")}

    before_data = _tree(data_root)
    before_project = _tree(project_root)

    project_snapshot(record.project_id, data_root=data_root)

    after_data = _tree(data_root)
    after_project = _tree(project_root)

    assert after_data == before_data, (
        f"project_snapshot wrote under data_root: {after_data - before_data}"
    )
    assert after_project == before_project, (
        f"project_snapshot wrote under the project root: "
        f"{after_project - before_project}"
    )


def test_t28a_non_tty_requires_both_stdin_and_stdout_tty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Shared design (T28's ui_cmd deliverable, owned by A): 'Interactive
    mode requires stdin and stdout to both be TTYs.' Today `ui_cmd` only
    checks stdout (`_stdout_is_tty()`); with stdout forced 'true' it enters
    the interactive path even though Click's `CliRunner` never provides a
    real stdin TTY."""
    import rush.cli as cli_module
    import rush.tui as tui_module
    import rush.workflows.suites as suites_module
    from rush.cli import cli

    proj = tmp_path / "proj"
    proj.mkdir()

    captured_seeds: list[ProjectSeed] = []

    def fake_run_workflow_suite(
        *, suite: object, path: Path, permissions: object, **kwargs: object
    ) -> dict:
        return {"tool": "suite", "status": "ok", "findings": [], "summary": "ok"}

    def fake_run_interactive_tui(seeds: list[ProjectSeed], **kwargs: object) -> None:
        captured_seeds.extend(seeds)

    monkeypatch.setattr(suites_module, "run_workflow_suite", fake_run_workflow_suite)
    monkeypatch.setattr(tui_module, "run_interactive_tui", fake_run_interactive_tui)
    monkeypatch.setattr(cli_module, "_stdout_is_tty", lambda: True)

    runner = CliRunner()
    result = runner.invoke(cli, ["ui", str(proj)])

    assert result.exit_code == 0, result.output
    assert captured_seeds == [], (
        "ui_cmd entered the interactive TUI with stdout forced TTY even "
        "though stdin is not a TTY; it must require both before starting "
        "the raw-terminal loop"
    )


def test_t28a_keepgreen_populated_results_still_render_findings_table() -> None:
    """Regression guard: existing populated-findings rendering must keep
    working exactly as today once T28-A lands."""
    project = ProjectState(
        name="demo",
        root=Path("/tmp/t28a-keepgreen"),
        results=[
            ToolResult(
                tool="lint",
                status="fail",
                duration_ms=1,
                summary="1 issue",
                findings=[
                    Finding(
                        path="main.py",
                        line=1,
                        column=1,
                        rule="F401",
                        message="Unused import",
                        severity="error",
                    )
                ],
            )
        ],
    )
    text = _render_text(TuiState(projects=[project]))
    assert "main.py:1" in text
    assert "Findings (1)" in text


def test_t28a_keepgreen_registered_project_resolves_by_id(tmp_path: Path) -> None:
    """Regression guard: `project_snapshot` must still resolve a real,
    currently-registered project and still raise `ProjectNotFoundError` for
    an unknown id -- the exact contract T28-A's Overview reads from."""
    data_root = tmp_path / "data"
    project_root = tmp_path / "proj"
    project_root.mkdir()
    record = register_project(project_root, data_root=data_root)

    snapshot = project_snapshot(record.project_id, data_root=data_root)
    assert snapshot["project"]["project_id"] == record.project_id

    with pytest.raises(ProjectNotFoundError):
        project_snapshot("not-a-real-id", data_root=data_root)


def test_t28a_keepgreen_run_interactive_tui_still_seeds_from_input(
    tmp_path: Path,
) -> None:
    """Regression guard: `run_interactive_tui` must still build one
    `ProjectState` per seed with `max_ticks=0` (no key loop iterations)."""
    seed = ProjectSeed(name="demo", root=tmp_path)
    state = run_interactive_tui(
        [seed],
        key_reader=None,
        actions=default_scan_actions(),
        max_ticks=0,
        use_live=False,
    )
    assert [p.name for p in state.projects] == ["demo"]


def test_t28a_overview_text_safe_against_terminal_injection() -> None:
    """Shared design X3 as it applies to A's own Overview/findings
    rendering: a hostile finding message (rich markup plus raw ESC/OSC
    bytes) must never crash the renderer or leak raw control bytes.
    Verified directly against real code before writing this test: today
    `render_app` raises `rich.errors.MarkupError` on this exact input,
    because table cell strings are still interpolated as Rich markup
    instead of passed through `safe_terminal_text` into a `Text` object."""
    hostile = "clean [/bad] \x1b[2Jbcd \x1b]0;pwned\x07"
    project = ProjectState(
        name="demo",
        root=Path("/tmp/t28a-injection"),
        results=[
            ToolResult(
                tool="lint",
                status="fail",
                duration_ms=1,
                summary="s",
                findings=[
                    Finding(
                        path="a.py",
                        line=1,
                        column=1,
                        rule="F1",
                        message=hostile,
                        severity="error",
                    )
                ],
            )
        ],
    )
    state = TuiState(projects=[project])
    try:
        text = _render_text(state)
    except Exception as exc:  # noqa: BLE001 -- the render crash IS the finding under test
        pytest.fail(
            "render_app must never raise on a hostile finding message "
            f"(X3 safe_terminal_text is required before every dynamic "
            f"value reaches Console/Table); it raised {type(exc).__name__}: {exc}"
        )
    assert "\x1b" not in text, (
        "a hostile finding message reached the terminal as a raw, "
        "unescaped control sequence instead of being passed through "
        "safe_terminal_text"
    )
