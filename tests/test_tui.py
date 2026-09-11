"""Tests for Phase 27/P66-03: Rich Interactive TUI.

Verifies:
- Layout generation and structure
- Finding tree rendering
- The persistent interactive loop (P66-03): key-driven selection/exit,
  canonical `path` field usage, and real ongoing scan progress.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from rich.console import Console
from rich.layout import Layout

from rush.tools.base import Finding, ToolResult
from rush.tui import ProjectSeed, ScanActions, build_tui_layout, run_interactive_tui


def test_ui_cmd_accepts_multiple_project_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Drives `rush ui` through its real CLI entrypoint (Click's CliRunner),
    not a hand-constructed multi-seed list: T305 found `ProjectSeed(...)` had
    exactly one call site (cli.py, single-item list), making the TUI's
    cross-project separation unreachable through the real product. This
    proves two real, independently-resolved project roots reach
    `run_interactive_tui` as separate seeds via `rush ui path1 path2`."""
    from click.testing import CliRunner

    import rush.tui as tui_module
    import rush.workflows.suites as suites_module
    from rush.cli import cli

    proj_a = tmp_path / "proj_a"
    proj_b = tmp_path / "proj_b"
    proj_a.mkdir()
    proj_b.mkdir()

    captured_seeds: list[ProjectSeed] = []

    def fake_run_workflow_suite(
        *, suite: object, path: Path, permissions: object, **kwargs: object
    ) -> dict:
        return {"tool": "suite", "status": "ok", "findings": [], "summary": str(path)}

    def fake_run_interactive_tui(seeds: list[ProjectSeed], **kwargs: object) -> None:
        captured_seeds.extend(seeds)

    monkeypatch.setattr(suites_module, "run_workflow_suite", fake_run_workflow_suite)
    monkeypatch.setattr(tui_module, "run_interactive_tui", fake_run_interactive_tui)

    runner = CliRunner()
    result = runner.invoke(cli, ["ui", str(proj_a), str(proj_b)])

    assert result.exit_code == 0, result.output
    assert [s.name for s in captured_seeds] == [proj_a.name, proj_b.name]
    assert [s.root for s in captured_seeds] == [proj_a.resolve(), proj_b.resolve()]
    # Real, independently-tracked seeds -- not the same object switched in place.
    assert captured_seeds[0] is not captured_seeds[1]


def test_tui_layout_generation() -> None:
    results = [
        ToolResult(
            tool="lint",
            status="fail",
            duration_ms=15,
            summary="lint: 1 finding",
            findings=[
                Finding(
                    file="src/main.py",
                    line=10,
                    column=1,
                    rule="F401",
                    message="Unused import",
                    severity="error",
                )
            ],
        )
    ]

    layout = build_tui_layout(results)
    assert isinstance(layout, Layout)
    assert "header" in [c.name for c in layout.children]
    assert "main" in [c.name for c in layout.children]
    assert "footer" in [c.name for c in layout.children]


def _noop_actions() -> ScanActions:
    return ScanActions(
        plan_scan=lambda *a, **k: SimpleNamespace(candidates=[]),
        execute_scan=lambda *a, **k: SimpleNamespace(aggregate={}),
        cancel_scan_run=lambda *a, **k: {},
        rescan_project_run=lambda *a, **k: {},
        build_handoff=lambda *a, **k: None,
        dispatch_handoff=lambda *a, **k: None,
        load_scan_events=lambda *a, **k: {"events": [], "run_state": None},
        list_agents=list,
    )


class _ScriptedReader:
    """Injectable `KeyReader` (see `rush.dashboard.terminal_input`) that
    plays back an exact scripted key sequence, then returns None forever."""

    def __init__(self, keys: list[str]) -> None:
        self._keys = iter(keys)

    def read_key(self, timeout: float) -> str | None:
        return next(self._keys, None)

    def get_size(self) -> tuple[int, int]:
        return (80, 24)


def test_input_loop_changes_selection_and_exits() -> None:
    seed = ProjectSeed(
        name="demo",
        root=Path("/tmp/rush-tui-demo"),
        results=[
            ToolResult(
                tool="lint",
                status="fail",
                duration_ms=1,
                summary="x",
                findings=[
                    Finding(
                        path="a.py",
                        line=1,
                        column=1,
                        rule="F1",
                        message="m1",
                        severity="error",
                    ),
                    Finding(
                        path="b.py",
                        line=2,
                        column=1,
                        rule="F2",
                        message="m2",
                        severity="warn",
                    ),
                    Finding(
                        path="c.py",
                        line=3,
                        column=1,
                        rule="F3",
                        message="m3",
                        severity="info",
                    ),
                ],
            )
        ],
    )

    # j, j -> selection moves from 0 to 2; enter -> detail mode; escape ->
    # back to list; q -> exit. Every step is a real dispatched key, not a
    # layout-name-only assertion.
    reader = _ScriptedReader(["j", "j", "enter", "escape", "q"])
    state = run_interactive_tui(
        [seed],
        key_reader=reader,
        actions=_noop_actions(),
        use_live=False,
        max_ticks=50,
    )

    assert state.should_quit is True
    assert state.projects[0].selected_index == 2
    assert state.mode == "list"


def test_finding_uses_canonical_path(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("import os\nprint(os.getcwd())\n")
    results = [
        ToolResult(
            tool="lint",
            status="fail",
            duration_ms=15,
            summary="lint: 1 finding",
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
    ]

    layout = build_tui_layout(results)
    console = Console(record=True, width=100)
    console.print(layout)
    rendered = console.export_text()

    assert "main.py:1" in rendered


def test_progress_updates_before_completion() -> None:
    import time

    total_candidates = 3
    events_state: dict = {"events": [], "run_state": "running"}

    def fake_plan_scan(root: Path, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(candidates=list(range(total_candidates)), root=str(root))

    def fake_execute_scan(
        plan: object, *, run_id: str | None = None, **kwargs: object
    ) -> SimpleNamespace:
        for _ in range(total_candidates):
            time.sleep(0.03)
            events_state["events"].append({"event": "candidate_completed"})
        events_state["run_state"] = "completed"
        return SimpleNamespace(
            aggregate={"tool": "suite", "status": "ok", "findings": []}
        )

    def fake_load_scan_events(
        root: Path, run_id: str, attempt_id: str | None = None
    ) -> dict:
        return dict(events_state)

    actions = ScanActions(
        plan_scan=fake_plan_scan,
        execute_scan=fake_execute_scan,
        cancel_scan_run=lambda *a, **k: {},
        rescan_project_run=lambda *a, **k: {},
        build_handoff=lambda *a, **k: None,
        dispatch_handoff=lambda *a, **k: None,
        load_scan_events=fake_load_scan_events,
        list_agents=list,
    )

    seed = ProjectSeed(name="demo", root=Path("/tmp/rush-tui-progress"), results=[])
    keys: list[str | None] = ["s", "y"] + [None] * 60

    class _WaitingReader:
        def __init__(self, script: list[str | None]) -> None:
            self._script = iter(script)

        def read_key(self, timeout: float) -> str | None:
            time.sleep(0.01)
            try:
                return next(self._script)
            except StopIteration:
                return "q"

        def get_size(self) -> tuple[int, int]:
            return (80, 24)

    state = run_interactive_tui(
        [seed],
        key_reader=_WaitingReader(keys),
        actions=actions,
        use_live=False,
        tick_seconds=0.01,
        max_ticks=400,
    )

    project = state.projects[0]
    history = project.progress_history
    assert any(0 < p.ratio < 1.0 for p in history), history
    assert history, "expected at least one progress observation"
    assert history[-1].status == "complete"
    assert project.status == "complete"


def test_start_scan_blocked_while_scan_running() -> None:
    """Reproduces T305's finding: unlike `rescan`, `start_scan` had no guard
    against re-triggering while `project.status == 'scanning'`, letting a
    second confirm race a second `_start_scan_thread` against the same
    `ProjectState`. Dispatches `start_scan` twice (s, y, s, y) while the
    first scan is still in flight and asserts only one scan ever started."""
    import time

    total_candidates = 5
    events_state: dict = {"events": [], "run_state": "running"}
    plan_scan_calls: list[int] = []

    def fake_plan_scan(root: Path, **kwargs: object) -> SimpleNamespace:
        plan_scan_calls.append(1)
        return SimpleNamespace(candidates=list(range(total_candidates)))

    def fake_execute_scan(
        plan: object, *, run_id: str | None = None, **kwargs: object
    ) -> SimpleNamespace:
        for _ in range(total_candidates):
            time.sleep(0.05)
            events_state["events"].append({"event": "candidate_completed"})
        events_state["run_state"] = "completed"
        return SimpleNamespace(
            aggregate={"tool": "suite", "status": "ok", "findings": []}
        )

    def fake_load_scan_events(
        root: Path, run_id: str, attempt_id: str | None = None
    ) -> dict:
        return dict(events_state)

    actions = ScanActions(
        plan_scan=fake_plan_scan,
        execute_scan=fake_execute_scan,
        cancel_scan_run=lambda *a, **k: {},
        rescan_project_run=lambda *a, **k: {},
        build_handoff=lambda *a, **k: None,
        dispatch_handoff=lambda *a, **k: None,
        load_scan_events=fake_load_scan_events,
        list_agents=list,
    )

    seed = ProjectSeed(name="demo", root=Path("/tmp/rush-tui-race"), results=[])
    # s,y start the first scan (~0.25s to complete); a second s,y arrives
    # ~0.02-0.03s later, well inside the running window -- must be blocked.
    keys: list[str | None] = ["s", "y", "s", "y"] + [None] * 60

    class _WaitingReader:
        def __init__(self, script: list[str | None]) -> None:
            self._script = iter(script)

        def read_key(self, timeout: float) -> str | None:
            time.sleep(0.01)
            try:
                return next(self._script)
            except StopIteration:
                return "q"

        def get_size(self) -> tuple[int, int]:
            return (80, 24)

    state = run_interactive_tui(
        [seed],
        key_reader=_WaitingReader(keys),
        actions=actions,
        use_live=False,
        tick_seconds=0.01,
        max_ticks=400,
    )

    project = state.projects[0]
    assert len(plan_scan_calls) == 1, "second start_scan must not start a new thread"
    assert project.status == "complete"
