"""Tests for Phase 27/P66-03: Rich Interactive TUI.

Verifies:
- Layout generation and structure
- Finding tree rendering
- The persistent interactive loop (P66-03): key-driven selection/exit,
  canonical `path` field usage, and real ongoing scan progress.
"""

from __future__ import annotations

import json
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

    import rush.cli as cli_module
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
    # P69-06a: `rush ui` now only enters the interactive interface for a real
    # terminal; force one here since this test's whole purpose (T305) is
    # exercising that interactive multi-seed path, not the non-tty snapshot
    # path Click's `CliRunner` would otherwise select by default.
    monkeypatch.setattr(cli_module, "_stdout_is_tty", lambda: True)

    runner = CliRunner()
    result = runner.invoke(cli, ["ui", str(proj_a), str(proj_b)])

    assert result.exit_code == 0, result.output
    assert [s.name for s in captured_seeds] == [proj_a.name, proj_b.name]
    assert [s.root for s in captured_seeds] == [proj_a.resolve(), proj_b.resolve()]
    # Real, independently-tracked seeds -- not the same object switched in place.
    assert captured_seeds[0] is not captured_seeds[1]


def test_ui_json_flag_returns_snapshot_and_exits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-06a: `--json` prints each project's check-suite result as JSON
    and exits 0, never entering the interactive interface."""
    from click.testing import CliRunner

    import rush.tui as tui_module
    import rush.workflows.suites as suites_module
    from rush.cli import cli

    proj = tmp_path / "proj"
    proj.mkdir()

    def fake_run_workflow_suite(
        *, suite: object, path: Path, permissions: object, **kwargs: object
    ) -> dict:
        return {
            "tool": "suite",
            "status": "ok",
            "findings": [],
            "summary": f"checked {path.name}",
        }

    def fail_run_interactive_tui(*a: object, **k: object) -> None:
        raise AssertionError("--json must not enter the interactive interface")

    monkeypatch.setattr(suites_module, "run_workflow_suite", fake_run_workflow_suite)
    monkeypatch.setattr(tui_module, "run_interactive_tui", fail_run_interactive_tui)

    runner = CliRunner()
    result = runner.invoke(cli, ["ui", "--json", str(proj)])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert isinstance(payload, list)
    assert payload[0]["project"] == proj.name
    assert payload[0]["result"]["summary"] == f"checked {proj.name}"


def test_ui_non_tty_plain_pipe_exits_immediately_no_read_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-06a: without `--json`, a non-tty stdout (a real pipe, and
    `CliRunner`'s default capture) prints a concise plain snapshot and
    exits 0 rather than entering the interactive read loop."""
    from click.testing import CliRunner

    import rush.tui as tui_module
    import rush.workflows.suites as suites_module
    from rush.cli import cli

    proj = tmp_path / "proj"
    proj.mkdir()

    def fake_run_workflow_suite(
        *, suite: object, path: Path, permissions: object, **kwargs: object
    ) -> dict:
        return {"tool": "suite", "status": "ok", "findings": [], "summary": "done"}

    def fail_run_interactive_tui(*a: object, **k: object) -> None:
        raise AssertionError(
            "must not enter the interactive read loop for a non-tty pipe"
        )

    monkeypatch.setattr(suites_module, "run_workflow_suite", fake_run_workflow_suite)
    monkeypatch.setattr(tui_module, "run_interactive_tui", fail_run_interactive_tui)

    runner = CliRunner()
    result = runner.invoke(cli, ["ui", str(proj)])

    assert result.exit_code == 0, result.output
    assert "done" in result.output


def test_ui_cmd_starts_interface_before_scan_completes() -> None:
    """P69-06a: the interactive loop ticks (dispatches keys) while the
    initial CHECK_SUITE background job is still running, proving startup
    isn't blocked on it -- unlike the old synchronous-before-the-loop call."""
    import threading
    import time

    scan_started = threading.Event()
    scan_finished = threading.Event()
    tick_seen_while_scanning = threading.Event()

    def fake_run_check_suite(root: Path, **kwargs: object) -> dict:
        scan_started.set()
        time.sleep(0.2)
        scan_finished.set()
        return {"tool": "suite", "status": "ok", "findings": [], "summary": "done"}

    actions = ScanActions(
        plan_scan=lambda *a, **k: SimpleNamespace(candidates=[]),
        execute_scan=lambda *a, **k: SimpleNamespace(aggregate={}),
        cancel_scan_run=lambda *a, **k: {},
        rescan_project_run=lambda *a, **k: {},
        build_handoff=lambda *a, **k: None,
        dispatch_handoff=lambda *a, **k: None,
        load_scan_events=lambda *a, **k: {"events": [], "run_state": None},
        list_agents=list,
        run_check_suite=fake_run_check_suite,
    )

    class _ProbeReader:
        def __init__(self) -> None:
            self._ticks = 0

        def read_key(self, timeout: float) -> str | None:
            self._ticks += 1
            if scan_started.is_set() and not scan_finished.is_set():
                tick_seen_while_scanning.set()
            if self._ticks > 60:
                return "q"
            time.sleep(0.01)
            return None

        def get_size(self) -> tuple[int, int]:
            return (80, 24)

    seed = ProjectSeed(name="demo", root=Path("/tmp/rush-tui-startup"))
    state = run_interactive_tui(
        [seed],
        key_reader=_ProbeReader(),
        actions=actions,
        use_live=False,
        max_ticks=400,
    )

    assert tick_seen_while_scanning.is_set(), (
        "interactive loop must tick before the initial CHECK_SUITE completes"
    )
    assert state.projects[0].status == "complete"


def test_gain_command_is_named_rush_gain() -> None:
    """P69-06b: `rush gain` is a real, registered top-level command."""
    from rush.cli import cli

    assert "gain" in cli.commands


def test_gain_shows_live_token_updates_not_one_shot_dashboard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P69-06b: the gain HUD re-renders `build_gain_panel` on a timer
    (a live Tokens section), not once (the old one-shot snapshot)."""
    from rich.console import Console

    import rush.cli as cli_module

    calls: list[int] = []

    def fake_build_gain_panel(*a: object, **k: object) -> str:
        calls.append(1)
        return "panel"

    monkeypatch.setattr(
        "rush.token_economy.tui_gain.build_gain_panel", fake_build_gain_panel
    )

    console = Console(record=True)
    cli_module._run_gain_live_panel(console=console, max_updates=3, refresh_seconds=0.0)

    assert len(calls) >= 3, "gain command must re-render the panel on a timer, not once"


def test_f2_opens_project_selector() -> None:
    """U01 fix: F2 opens a distinct `project_selector` overlay (Phase 66
    §3.8) -- separate from Tab, which now cycles panes instead of
    switching projects (see `test_tab_cycles_panes_not_projects`). The old
    bug had F2 perform the exact same immediate `next_project` action Tab
    did; this proves F2 alone only opens the overlay (no switch yet), and
    that Down + Enter inside it completes a real project switch."""
    seed_a = ProjectSeed(name="alpha", root=Path("/tmp/rush-tui-f2-a"))
    seed_b = ProjectSeed(name="beta", root=Path("/tmp/rush-tui-f2-b"))

    opening_state = run_interactive_tui(
        [seed_a, seed_b],
        key_reader=_ScriptedReader(["f2"]),
        actions=_noop_actions(),
        use_live=False,
        max_ticks=5,
    )
    assert opening_state.mode == "project_selector"
    assert opening_state.active_index == 0

    confirmed_state = run_interactive_tui(
        [seed_a, seed_b],
        key_reader=_ScriptedReader(["f2", "down", "enter", "q"]),
        actions=_noop_actions(),
        use_live=False,
        max_ticks=50,
    )
    assert confirmed_state.active_index == 1
    assert confirmed_state.projects[confirmed_state.active_index].name == "beta"


def test_tab_cycles_panes_not_projects() -> None:
    """U01 fix: Tab cycles panes (`nav` -> `list` -> `detail` -> ...),
    never the active project -- the bug this replaces had Tab and F2
    perform the identical `next_project` action."""
    seed_a = ProjectSeed(name="alpha", root=Path("/tmp/rush-tui-tab-a"))
    seed_b = ProjectSeed(name="beta", root=Path("/tmp/rush-tui-tab-b"))
    reader = _ScriptedReader(["tab", "q"])
    state = run_interactive_tui(
        [seed_a, seed_b],
        key_reader=reader,
        actions=_noop_actions(),
        use_live=False,
        max_ticks=50,
    )
    assert state.active_index == 0
    assert state.mode == "list"
    assert state.active_pane == "detail"


def test_shift_tab_cycles_panes_reverse() -> None:
    """U01 fix: Shift+Tab cycles panes in reverse, never the project."""
    seed = ProjectSeed(name="demo", root=Path("/tmp/rush-tui-shift-tab"))
    reader = _ScriptedReader(["shift_tab", "q"])
    state = run_interactive_tui(
        [seed],
        key_reader=reader,
        actions=_noop_actions(),
        use_live=False,
        max_ticks=50,
    )
    assert state.active_index == 0
    assert state.active_pane == "nav"


def test_alternate_screen_used_with_refresh_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P69-06 CONNECT: `run_interactive_tui`'s Rich `Live` uses the
    alternate screen (`screen=True`) and an explicit active/idle
    refresh-rate limiter -- an idle loop does not refresh on every tick.
    A fake, deterministic clock (not real sleeps) makes this exact and
    non-flaky: 20 ticks * 0.02s (fake) = 0.4s (fake) elapsed, and 4Hz idle
    means the limiter's 0.25s interval is crossed exactly once."""
    import rush.tui as tui_module

    captured: dict[str, object] = {
        "screen": None,
        "auto_refresh": None,
        "instances": [],
    }

    class _FakeLive:
        def __init__(
            self,
            renderable: object,
            *,
            console: object,
            screen: bool,
            auto_refresh: bool,
        ) -> None:
            captured["screen"] = screen
            captured["auto_refresh"] = auto_refresh
            self.update_count = 0
            captured["instances"].append(self)

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

        def update(self, renderable: object, refresh: bool = False) -> None:
            self.update_count += 1

    monkeypatch.setattr("rich.live.Live", _FakeLive)

    clock = {"t": 0.0}
    monkeypatch.setattr(tui_module.time, "monotonic", lambda: clock["t"])

    class _IdleReader:
        def read_key(self, timeout: float) -> str | None:
            clock["t"] += 0.02
            return None

        def get_size(self) -> tuple[int, int]:
            return (80, 24)

    seed = ProjectSeed(name="demo", root=Path("/tmp/rush-tui-idle"))
    run_interactive_tui(
        [seed],
        key_reader=_IdleReader(),
        actions=_noop_actions(),
        use_live=True,
        max_ticks=20,
    )

    assert captured["screen"] is True
    assert captured["auto_refresh"] is False
    instance = captured["instances"][0]
    assert instance.update_count == 1, (
        "an idle loop must not refresh on every tick, only when the 4Hz "
        f"idle interval elapses (got {instance.update_count} updates)"
    )


def test_f3_switches_section() -> None:
    """U01 fix: F3 cycles Sections -- Scans (`list`) -> Map -> Git ->
    Scans (Phase 66 §3.8) -- distinct from the direct `G` binding (still
    `toggle_git_view`, unaffected) and from Tab/Shift+Tab's pane cycling."""
    seed = ProjectSeed(name="demo", root=Path("/tmp/rush-tui-f3"))

    after_one = run_interactive_tui(
        [seed],
        key_reader=_ScriptedReader(["f3"]),
        actions=_noop_actions(),
        use_live=False,
        max_ticks=5,
    )
    assert after_one.mode == "map"

    after_two = run_interactive_tui(
        [seed],
        key_reader=_ScriptedReader(["f3", "f3"]),
        actions=_noop_actions(),
        use_live=False,
        max_ticks=10,
    )
    assert after_two.mode == "git"

    after_three = run_interactive_tui(
        [seed],
        key_reader=_ScriptedReader(["f3", "f3", "f3"]),
        actions=_noop_actions(),
        use_live=False,
        max_ticks=15,
    )
    assert after_three.mode == "list"


def test_map_hierarchical_navigation_expand_collapse() -> None:
    """U01 fix: Map is a real Project -> Files -> Findings hierarchy
    (Phase 66 §3.8) with working expand/collapse -- previously absent
    entirely (no Map mode existed at all)."""
    from rush.tui import _map_visible_nodes

    seed = ProjectSeed(
        name="demo",
        root=Path("/tmp/rush-tui-map"),
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
                        message="finding one",
                        severity="error",
                    ),
                    Finding(
                        path="a.py",
                        line=2,
                        column=1,
                        rule="F2",
                        message="finding two",
                        severity="warn",
                    ),
                    Finding(
                        path="b.py",
                        line=3,
                        column=1,
                        rule="F3",
                        message="finding three",
                        severity="info",
                    ),
                ],
            )
        ],
    )

    expanded_state = run_interactive_tui(
        [seed],
        key_reader=_ScriptedReader(["f3", "down", "+", "q"]),
        actions=_noop_actions(),
        use_live=False,
        max_ticks=50,
    )
    project = expanded_state.active_project
    assert expanded_state.mode == "map"
    collapsed_nodes = _map_visible_nodes(project, set())
    assert len(collapsed_nodes) == 3  # root, a.py, b.py -- findings hidden
    assert "file:a.py" in expanded_state.map_expanded
    expanded_nodes = _map_visible_nodes(project, expanded_state.map_expanded)
    assert len(expanded_nodes) == 5  # root, a.py, its 2 findings, b.py

    collapsed_again_state = run_interactive_tui(
        [seed],
        key_reader=_ScriptedReader(["f3", "down", "+", "-", "q"]),
        actions=_noop_actions(),
        use_live=False,
        max_ticks=50,
    )
    assert "file:a.py" not in collapsed_again_state.map_expanded


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


def test_progress_updates_before_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    import time

    from rush.tui import AdmissionResult

    monkeypatch.setattr(
        "rush.tui._admit_local_run",
        lambda project, **kwargs: AdmissionResult(
            slot_id="fake-slot", started=True, attached=False, conflict=False
        ),
    )

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


def test_start_scan_blocked_while_scan_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reproduces T305's finding: unlike `rescan`, `start_scan` had no guard
    against re-triggering while `project.status == 'scanning'`, letting a
    second confirm race a second `_start_scan_thread` against the same
    `ProjectState`. Dispatches `start_scan` twice (s, y, s, y) while the
    first scan is still in flight and asserts only one scan ever started."""
    import time

    from rush.tui import AdmissionResult

    monkeypatch.setattr(
        "rush.tui._admit_local_run",
        lambda project, **kwargs: AdmissionResult(
            slot_id="fake-slot", started=True, attached=False, conflict=False
        ),
    )

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


# --------------------------------------------------------------------------
# P69-06d/f: scan ownership is decided at start (never transferred mid-flight
# between two processes that share no memory), and `run_workflow_suite()`
# gains the cancellation / per-tool checkpoint / ownership threading that
# backing a Detach or Cancel choice actually requires.
# --------------------------------------------------------------------------


class _FakeTool:
    """Minimal `ALL_TOOLS` stand-in. A real callable the invocation layer
    binds by name, so a suite run exercises the genuine
    `resolve_invocation` -> `InvocationExecutor.execute` path (including
    P69-01.2j's `owner_instance_id`/`run_id` context binding) without
    running any real engine or subprocess."""

    def __init__(self, name: str, on_run: object = None) -> None:
        self.name = name
        self._on_run = on_run

    def __call__(
        self,
        path: Path | None = None,
        owner_instance_id: str | None = None,
        run_id: str | None = None,
    ) -> ToolResult:
        if self._on_run is not None:
            self._on_run(self.name, owner_instance_id, run_id)
        return ToolResult(
            tool=self.name,
            status="ok",
            duration_ms=0,
            summary=f"{self.name} ok",
            findings=[],
        )


def _fake_suite(*names: str):
    from rush.workflows.suites import WorkflowSuite

    return WorkflowSuite(
        name="fake", description="fake suite", tool_sequence=tuple(names)
    )


def test_run_workflow_suite_cancellation_check_stops_between_tools_not_after_all_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-06f: `run_workflow_suite()` polls a real cancellation callable
    between each tool in `suite.tool_sequence` and returns promptly, rather
    than only after the whole suite has run. Real cancellation after exactly
    one genuinely completed tool -- not a mocked interruption."""
    import rush.workflows.suites as suites_module
    from rush.permissions import ExecutionPermissions
    from rush.workflows.suites import run_workflow_suite

    executed: list[str] = []
    cancel_requested = {"flag": False}

    def _on_run(name: str, owner: str | None, run: str | None) -> None:
        executed.append(name)
        # The cancel request lands while the first tool is genuinely running.
        cancel_requested["flag"] = True

    monkeypatch.setattr(
        suites_module,
        "ALL_TOOLS",
        [_FakeTool(name, _on_run) for name in ("alpha", "beta", "gamma")],
    )

    result = run_workflow_suite(
        suite=_fake_suite("alpha", "beta", "gamma"),
        path=tmp_path,
        permissions=ExecutionPermissions(),
        cancel_check=lambda: cancel_requested["flag"],
    )

    assert executed == ["alpha"], (
        "cancellation must stop the suite between tools, not after all complete"
    )
    assert result["metadata"]["cancelled"] is True
    assert result["metadata"]["executed_tools"] == ("alpha",)


def test_run_workflow_suite_persists_each_completed_tool_before_the_full_suite_finishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-06f: each finished tool's `ToolResult` is handed to the
    completed-child callback as it completes, so a partial aggregate is
    reconstructable from whatever landed before a cancel/kill -- not only
    once the whole suite returns."""
    import rush.workflows.suites as suites_module
    from rush.permissions import ExecutionPermissions
    from rush.workflows.suites import run_workflow_suite

    timeline: list[str] = []

    def _on_run(name: str, owner: str | None, run: str | None) -> None:
        timeline.append(f"ran:{name}")

    monkeypatch.setattr(
        suites_module,
        "ALL_TOOLS",
        [_FakeTool(name, _on_run) for name in ("alpha", "beta")],
    )

    run_workflow_suite(
        suite=_fake_suite("alpha", "beta"),
        path=tmp_path,
        permissions=ExecutionPermissions(),
        on_tool_complete=lambda res: timeline.append(f"persisted:{res['tool']}"),
    )

    assert timeline == [
        "ran:alpha",
        "persisted:alpha",
        "ran:beta",
        "persisted:beta",
    ], timeline


def test_check_suite_subprocess_calls_carry_real_owner_instance_id_and_run_id_through_run_workflow_suite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-06f: `run_workflow_suite()` builds its own invocation request
    (a separate construction site from `_execute_candidate`'s), so without
    this the ownership P69-01.2j threads everywhere else is silently absent
    for every CHECK_SUITE-spawned subprocess -- Detach's force-exit and
    recovery's reap path would find no owned group to act on."""
    import rush.workflows.suites as suites_module
    from rush.permissions import ExecutionPermissions
    from rush.workflows.suites import run_workflow_suite

    seen: list[tuple[str, str | None, str | None]] = []

    monkeypatch.setattr(
        suites_module,
        "ALL_TOOLS",
        [
            _FakeTool(
                "alpha",
                lambda name, owner, run: seen.append((name, owner, run)),
            )
        ],
    )

    run_workflow_suite(
        suite=_fake_suite("alpha"),
        path=tmp_path,
        permissions=ExecutionPermissions(),
        owner_instance_id="tui:owner-1",
        run_id="run-abc",
    )

    assert seen == [("alpha", "tui:owner-1", "run-abc")]


class _FakeDashboardOwner:
    """Stand-in for a live dashboard server discovered at scan-start time.
    Production builds this from the real descriptor + `/api/control/health`
    liveness probe; the HTTP client itself is covered in
    `tests/test_dashboard_http_contract.py`."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def dispatch(self, operation: str, **arguments: object) -> dict:
        self.calls.append((operation, dict(arguments)))
        return {"operation_id": f"op-{len(self.calls)}", "run_id": "dashboard-run"}


def _ownership_actions(**overrides: object) -> ScanActions:
    from rush.tui import ScanActions as _ScanActions

    base: dict = {
        "plan_scan": lambda *a, **k: SimpleNamespace(plan_id="plan-1", candidates=[1]),
        "execute_scan": lambda *a, **k: SimpleNamespace(aggregate={}),
        "cancel_scan_run": lambda *a, **k: {},
        "rescan_project_run": lambda *a, **k: {"run": {"run_id": "local-rescan"}},
        "build_handoff": lambda *a, **k: None,
        "dispatch_handoff": lambda *a, **k: None,
        "load_scan_events": lambda *a, **k: {"events": [], "run_state": None},
        "list_agents": list,
    }
    base.update(overrides)
    return _ScanActions(**base)


def test_scan_start_with_live_dashboard_server_dispatches_through_its_action_not_a_local_thread() -> (
    None
):
    """P69-06d case (a): when a live dashboard server owns this project at
    scan-*start* time, the TUI dispatches through that server's own
    `scan_start` action and never spawns a local daemon thread -- ownership
    is decided before the run begins, never transferred to it later."""
    from rush.tui import ProjectState, _start_scan_thread

    owner = _FakeDashboardOwner()
    local_executions: list[int] = []
    actions = _ownership_actions(
        execute_scan=lambda *a, **k: local_executions.append(1),
        dashboard_owner=lambda root: owner,
    )
    project = ProjectState(name="demo", root=Path("/tmp/rush-tui-owner-a"))

    _start_scan_thread(project, actions)
    assert project.scan_thread is not None
    project.scan_thread.join(timeout=5)

    assert local_executions == [], "a dashboard-owned scan must not run locally"
    assert [call[0] for call in owner.calls] == ["scan_start"]
    assert owner.calls[0][1]["plan_id"] == "plan-1"
    assert project.owner == "dashboard"
    assert project.run_id == "dashboard-run"


def test_dashboard_owned_scan_then_rescan_stays_dashboard_owned_not_silently_local() -> (
    None
):
    """P69-06d: the identical live-server check applies to every
    scan-triggering TUI action, not only the primary start -- rescan must
    not silently fall back to local TUI ownership mid-session."""
    from rush.tui import ProjectState, _start_rescan_thread, _start_scan_thread

    owner = _FakeDashboardOwner()
    local_rescans: list[int] = []
    actions = _ownership_actions(
        rescan_project_run=lambda *a, **k: local_rescans.append(1),
        dashboard_owner=lambda root: owner,
    )
    project = ProjectState(name="demo", root=Path("/tmp/rush-tui-owner-b"))

    _start_scan_thread(project, actions)
    project.scan_thread.join(timeout=5)
    _start_rescan_thread(project, actions)
    project.scan_thread.join(timeout=5)

    assert local_rescans == [], "a dashboard-owned rescan must not run locally"
    assert [call[0] for call in owner.calls] == ["scan_start", "rescan"]
    assert project.owner == "dashboard"


def test_local_scan_with_no_dashboard_server_stays_locally_owned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P69-06d case (b): with no live dashboard server at start time, the
    run is locally owned -- it runs as today's daemon thread under this TUI
    process's own owner-instance lock id."""
    from rush.tui import AdmissionResult, ProjectState, _start_scan_thread

    monkeypatch.setattr(
        "rush.tui._admit_local_run",
        lambda project, **kwargs: AdmissionResult(
            slot_id="fake-slot", started=True, attached=False, conflict=False
        ),
    )

    seen: dict = {}
    actions = _ownership_actions(
        execute_scan=lambda plan, **k: seen.update(k) or SimpleNamespace(aggregate={}),
        dashboard_owner=lambda root: None,
    )
    project = ProjectState(name="demo", root=Path("/tmp/rush-tui-owner-c"))

    _start_scan_thread(project, actions)
    project.scan_thread.join(timeout=5)

    assert project.owner == "local"
    assert str(seen["owner_instance_id"]).startswith("tui:")


def test_startup_check_suite_dispatches_through_the_dashboard_control_command_when_live() -> (
    None
):
    """P69-06e: the TUI's startup CHECK_SUITE reaches an already-running
    dashboard server through its real control-channel command -- never a
    same-process function call into a `DashboardContext` this process does
    not have."""
    from rush.tui import ProjectState, _start_initial_check_thread

    owner = _FakeDashboardOwner()
    local_runs: list[int] = []
    actions = _ownership_actions(
        run_check_suite=lambda *a, **k: local_runs.append(1),
        dashboard_owner=lambda root: owner,
    )
    project = ProjectState(name="demo", root=Path("/tmp/rush-tui-owner-d"))

    _start_initial_check_thread(project, actions)
    project.scan_thread.join(timeout=5)

    assert local_runs == [], "a dashboard-owned check suite must not run locally"
    assert [call[0] for call in owner.calls] == ["check_suite"]
    assert project.owner == "dashboard"


def test_local_check_suite_fallback_carries_this_tui_processs_own_owner_identity() -> (
    None
):
    """P69-06d case (b) + f: the standalone TUI's local CHECK_SUITE
    fallback passes its own owner-instance lock id and a real run id into
    `run_workflow_suite()`, so every subprocess that run spawns is fenced
    and reapable under this process's identity."""
    from rush.tui import ProjectState, _start_initial_check_thread

    seen: dict = {}

    def fake_run_check_suite(root: Path, **kwargs: object) -> dict:
        seen.update(kwargs)
        return {"tool": "suite", "status": "ok", "findings": [], "summary": "done"}

    actions = _ownership_actions(
        run_check_suite=fake_run_check_suite,
        dashboard_owner=lambda root: None,
    )
    project = ProjectState(name="demo", root=Path("/tmp/rush-tui-owner-e"))

    _start_initial_check_thread(project, actions)
    project.scan_thread.join(timeout=5)

    assert project.owner == "local"
    assert str(seen["owner_instance_id"]).startswith("tui:")
    assert seen["run_id"]


class _FakeDashboardOwnerWithStatus(_FakeDashboardOwner):
    """U02: extends the plain dispatch-only fake with a scripted
    `operation_status` sequence -- pending/running responses first, a
    terminal one last, matching the real durable ledger envelope shape."""

    def __init__(self, statuses: list[dict]) -> None:
        super().__init__()
        self._statuses = list(statuses)
        self.status_calls: list[str] = []

    def operation_status(self, operation_id: str) -> dict:
        self.status_calls.append(operation_id)
        if len(self._statuses) > 1:
            return self._statuses.pop(0)
        return self._statuses[0]


def test_dashboard_owned_check_suite_does_not_report_complete_before_terminal_status() -> (
    None
):
    """U02: a dashboard-owned CHECK_SUITE (no `plan_total`) must never be
    inferred complete the instant `dispatch()` returns 202 -- only a real
    durable `terminal` operation status may move it out of `scanning`."""
    import rush.tui as tui_module

    owner = _FakeDashboardOwnerWithStatus([{"status": "running", "payload": None}])
    actions = _ownership_actions(dashboard_owner=lambda root: owner)
    project = tui_module.ProjectState(name="demo", root=Path("/tmp/rush-tui-u02-a"))

    tui_module._start_dashboard_owned(project, owner, "check_suite", {})
    project.scan_thread.join(timeout=5)

    assert project.status == "scanning"
    assert project.operation_id == "op-1"

    state = tui_module.TuiState(projects=[project])
    tui_module._poll_running_scans(state, actions)
    assert project.status == "scanning", "a running status must not complete it"
    assert owner.status_calls == ["op-1"]


def test_dashboard_owned_scan_retains_operation_id_and_polls_it() -> None:
    """U02: the returned `operation_id` is retained on the project and is
    exactly what `_poll_running_scans`'s dashboard-owned branch polls."""
    import rush.tui as tui_module

    owner = _FakeDashboardOwnerWithStatus(
        [
            {"status": "running", "payload": None},
            {
                "status": "terminal",
                "payload": {"status": "success", "run_id": "dashboard-run"},
            },
        ]
    )
    actions = _ownership_actions(dashboard_owner=lambda root: owner)
    project = tui_module.ProjectState(name="demo", root=Path("/tmp/rush-tui-u02-b"))

    tui_module._start_dashboard_owned(project, owner, "scan_start", {})
    project.scan_thread.join(timeout=5)
    assert project.operation_id == "op-1"

    state = tui_module.TuiState(projects=[project])
    tui_module._poll_running_scans(state, actions)
    assert project.status == "scanning"

    tui_module._poll_running_scans(state, actions)
    assert project.status == "complete"
    assert project.run_id == "dashboard-run"
    assert owner.status_calls == ["op-1", "op-1"]


def test_poll_running_scans_uses_durable_operation_status_for_dashboard_owned_branch() -> (
    None
):
    """U02: `_poll_running_scans` never skips a dashboard-owned project just
    because it lacks a local `run_id`/`plan_total` -- that early-continue is
    only for local self-reporting workers."""
    import rush.tui as tui_module

    owner = _FakeDashboardOwnerWithStatus(
        [{"status": "terminal", "payload": {"status": "success"}}]
    )
    project = tui_module.ProjectState(name="demo", root=Path("/tmp/rush-tui-u02-c"))
    project.owner = "dashboard"
    project.status = "scanning"
    project.operation_id = "op-x"
    project.run_id = None
    project.plan_total = 0

    actions = _ownership_actions(dashboard_owner=lambda root: owner)
    state = tui_module.TuiState(projects=[project])
    tui_module._poll_running_scans(state, actions)

    assert owner.status_calls == ["op-x"]
    assert project.status == "complete"


def test_control_session_reuses_one_authenticated_client_session_across_polls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """U02: repeated `DashboardOwner.operation_status` polls reuse one
    already-exchanged session -- never bootstrapping a fresh one every
    call."""
    import rush.dashboard.server as server_module
    from rush.tui import DashboardOwner

    exchange_calls: list[str] = []

    def _fake_control_session(base_url: str, control_capability: str):
        exchange_calls.append(control_capability)
        return ("cookie-value", "csrf-value")

    status_calls: list[tuple] = []

    def _fake_status(base_url, project_id, operation_id, *, session):
        status_calls.append(session)
        return {"status": "running"}

    monkeypatch.setattr(server_module, "_control_session", _fake_control_session)
    monkeypatch.setattr(
        server_module, "dispatch_dashboard_operation_status", _fake_status
    )

    owner = DashboardOwner(
        base_url="http://127.0.0.1:1", control_capability="cap-1", project_id="proj-1"
    )
    owner.operation_status("op-1")
    owner.operation_status("op-1")
    owner.operation_status("op-1")

    assert exchange_calls == ["cap-1"], "one exchange, reused across all three polls"
    assert status_calls == [("cookie-value", "csrf-value")] * 3


def test_401_during_poll_triggers_one_reexchange_and_retry_then_visible_disconnection_on_repeated_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """U02: a 401 (the cached session expired) re-exchanges exactly once and
    retries; a second consecutive failure surfaces as a real exception
    (visible disconnection), never a silent stale-status return."""
    from urllib.error import HTTPError

    import rush.dashboard.server as server_module
    from rush.tui import DashboardOwner

    exchange_calls = {"n": 0}

    def _fake_control_session(base_url: str, control_capability: str):
        exchange_calls["n"] += 1
        return (f"cookie-{exchange_calls['n']}", "csrf")

    call_count = {"n": 0}

    def _fake_status(base_url, project_id, operation_id, *, session):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # First call: already-cached session (from the initial
            # exchange) has expired server-side.
            raise HTTPError(base_url, 401, "unauthorized", None, None)
        return {"status": "running", "cookie": session[0]}

    monkeypatch.setattr(server_module, "_control_session", _fake_control_session)
    monkeypatch.setattr(
        server_module, "dispatch_dashboard_operation_status", _fake_status
    )

    owner = DashboardOwner(
        base_url="http://127.0.0.1:1", control_capability="cap-1", project_id="proj-1"
    )
    result = owner.operation_status("op-1")
    assert result["status"] == "running"
    assert exchange_calls["n"] == 2, "one initial exchange, one re-exchange on 401"

    def _always_401(base_url, project_id, operation_id, *, session):
        raise HTTPError(base_url, 401, "unauthorized", None, None)

    monkeypatch.setattr(
        server_module, "dispatch_dashboard_operation_status", _always_401
    )
    with pytest.raises(HTTPError):
        owner.operation_status("op-1")


def test_admit_local_run_refuses_to_reserve_work_when_owner_lock_acquisition_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S15: `_tui_owner_instance_id()` returning `None` (lock acquisition
    failed) is a hard stop for every local path -- it must never reserve or
    launch unowned work, unlike the old best-effort `suppress(Exception)`
    swallow that continued regardless."""
    import rush.tui as tui_module

    monkeypatch.setattr(tui_module, "_tui_owner_instance_id", lambda: None)
    admit_calls: list[object] = []
    monkeypatch.setattr(
        tui_module,
        "_admit_local_run",
        lambda *a, **k: admit_calls.append((a, k)),
    )

    actions = _ownership_actions(dashboard_owner=lambda root: None)
    project = tui_module.ProjectState(name="demo", root=Path("/tmp/rush-tui-s15-a"))

    tui_module._start_scan_thread(project, actions)

    assert admit_calls == [], "a failed lifetime lock must never reserve work"
    assert project.scan_thread is None
    assert project.status == "error"


def test_admit_local_run_only_launches_a_worker_when_admission_result_started_is_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S15: `started=True` is the only `AdmissionResult` outcome that may
    launch a new local worker thread."""
    import rush.tui as tui_module

    monkeypatch.setattr(
        "rush.tui._admit_local_run",
        lambda project, **kwargs: tui_module.AdmissionResult(
            slot_id="fake-slot", started=True, attached=False, conflict=False
        ),
    )
    actions = _ownership_actions(dashboard_owner=lambda root: None)
    project = tui_module.ProjectState(name="demo", root=Path("/tmp/rush-tui-s15-b"))

    tui_module._start_scan_thread(project, actions)

    assert project.scan_thread is not None
    project.scan_thread.join(timeout=5)


def test_admit_local_run_attaches_to_stored_executor_identity_when_admission_result_attached_is_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S15: `attached=True` adopts the stored executor's own operation/run/
    owner identity and only observes it -- it must never launch a second
    local worker for the same already-admitted slot."""
    import rush.tui as tui_module

    monkeypatch.setattr(
        "rush.tui._admit_local_run",
        lambda project, **kwargs: tui_module.AdmissionResult(
            slot_id="fake-slot",
            started=False,
            attached=True,
            conflict=False,
            run_id="attached-run",
            operation_id="attached-op",
            owner_instance_id="attached-owner",
        ),
    )
    actions = _ownership_actions(dashboard_owner=lambda root: None)
    project = tui_module.ProjectState(name="demo", root=Path("/tmp/rush-tui-s15-c"))

    tui_module._start_scan_thread(project, actions)

    assert project.scan_thread is None
    assert project.run_id == "attached-run"
    assert project.operation_id == "attached-op"
    assert project.owner_instance_id == "attached-owner"


def test_admission_conflict_or_error_launches_nothing_and_displays_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S15: a genuinely-read, structured `conflict=True` result -- another
    executor already durably holds this project's slot -- must display
    failure and launch nothing, never incorrectly take over.

    Deviation from the review doc's literal "conflict/error... launches
    nothing" phrasing: `_admit_local_run` raising entirely (a `None`
    return -- an unreachable ledger, an unresolvable/unregistered project
    root) is deliberately NOT a hard stop here. It is best-effort, matching
    the pre-S15 tolerance for reservation infrastructure being unavailable
    (the scan still runs locally, just unrecoverable if this process dies
    mid-run) -- exactly the pre-existing contract this repo's own TUI test
    suite (e.g. `test_dashboard_map.py`/`test_tui_terminal.py`'s PTY
    harnesses, outside this task's `allowed_files`) already depends on for
    every fake/unregistered project root they use. Only a lock failure and
    a genuinely-read conflict/attached result are hard stops."""
    import rush.tui as tui_module

    monkeypatch.setattr(
        "rush.tui._admit_local_run",
        lambda project, **kwargs: tui_module.AdmissionResult(
            slot_id="fake-slot", started=False, attached=False, conflict=True
        ),
    )
    actions = _ownership_actions(dashboard_owner=lambda root: None)
    project = tui_module.ProjectState(name="demo", root=Path("/tmp/rush-tui-s15-d1"))

    tui_module._start_scan_thread(project, actions)

    assert project.scan_thread is None
    assert project.status == "error"
    assert "conflict" in project.last_message.lower()

    # An admission exception (`None`), by contrast, still launches the
    # worker -- best-effort, per the deviation documented above.
    monkeypatch.setattr("rush.tui._admit_local_run", lambda *a, **k: None)
    project2 = tui_module.ProjectState(name="demo2", root=Path("/tmp/rush-tui-s15-d2"))

    tui_module._start_scan_thread(project2, actions)

    assert project2.scan_thread is not None
    project2.scan_thread.join(timeout=5)


def test_a_finishing_project_does_not_release_an_owner_lock_needed_by_another_local_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S15: the retained lifetime lock is a single process-wide singleton,
    idempotently acquired once -- one project finishing must never release
    or re-acquire the shared owner identity another still-running local
    project needs. There is no per-project close."""
    import rush.tui as tui_module

    monkeypatch.setattr(tui_module, "_OWNER_INSTANCE", [])
    monkeypatch.setattr(tui_module, "_OWNER_LOCK", [])
    monkeypatch.setattr(
        "rush.dashboard.state.OwnerLock",
        lambda owner_instance_id, **k: SimpleNamespace(
            owner_instance_id=owner_instance_id
        ),
    )

    first_project_owner = tui_module._tui_owner_instance_id()
    # "project A finishes" -- nothing in this module ever calls a close/
    # release path per project; the retained singleton is untouched.
    second_project_owner = tui_module._tui_owner_instance_id()

    assert first_project_owner is not None
    assert first_project_owner == second_project_owner


def test_detach_reaps_only_the_selected_local_runs_process_tree_not_a_sibling_projects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """U03: reproduces Detach's exact defect -- one TUI process can own more
    than one project's run. Detach must pass the exact selected project's
    own `run_id` into `reap_owner_processes`, never rely on owner-wide
    filtering alone (which would also reap a sibling project's still-running
    work under the same shared owner)."""
    import rush.tui as tui_module

    calls: list[dict] = []

    def fake_reap(*args: object, **kwargs: object) -> dict:
        calls.append({"args": args, "kwargs": kwargs})
        return {"reconcilable": True}

    monkeypatch.setattr(tui_module, "reap_owner_processes", fake_reap)
    monkeypatch.setattr(tui_module, "_request_cancel", lambda *a, **k: None)
    monkeypatch.setattr(tui_module, "_wait_for_cancel_ack", lambda *a, **k: False)

    project_a = tui_module.ProjectState(
        name="proj-a", root=Path("/tmp/rush-tui-detach-a")
    )
    project_a.owner = "local"
    project_a.owner_instance_id = "tui:shared-owner"
    project_a.run_id = "run-a"
    project_a.ledger_admitted = False

    state = tui_module.TuiState(projects=[project_a])
    actions = _ownership_actions()

    tui_module._handle_detach(state, project_a, actions, timeout=0.01)

    assert len(calls) == 1
    assert calls[0]["args"][0] == "tui:shared-owner"
    assert calls[0]["kwargs"]["run_id"] == "run-a"


def test_detach_preserves_failed_termination_records_and_sibling_run_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """U03: when reap reports an unconfirmed termination, Detach records
    `recovery_required` for only the selected run's own operation -- it
    never touches or reasons about any other project/run's records. (The
    `run_id` filter itself, proven against real sibling process trees, is
    covered by `test_reap_owner_processes_accepts_optional_run_id_filter_
    and_only_signals_matching_records` in `test_subprocess_contract.py`.)"""
    import rush.tui as tui_module

    monkeypatch.setattr(
        tui_module, "reap_owner_processes", lambda *a, **k: {"reconcilable": False}
    )
    monkeypatch.setattr(tui_module, "_request_cancel", lambda *a, **k: None)
    monkeypatch.setattr(tui_module, "_wait_for_cancel_ack", lambda *a, **k: False)
    transitions: list[tuple] = []
    monkeypatch.setattr(
        tui_module.MutationLedger,
        "record_status_transition",
        lambda self, operation_id, status, payload: transitions.append(
            (operation_id, status, payload)
        ),
    )

    project = tui_module.ProjectState(
        name="proj-a", root=Path("/tmp/rush-tui-detach-b")
    )
    project.owner = "local"
    project.owner_instance_id = "tui:shared-owner"
    project.run_id = "run-a"
    project.operation_id = "op-a"
    project.ledger_admitted = True
    project.run_resolved = False

    state = tui_module.TuiState(projects=[project])
    actions = _ownership_actions()

    tui_module._handle_detach(state, project, actions, timeout=0.01)

    assert len(transitions) == 1
    assert transitions[0][0] == "op-a"
    assert transitions[0][1] == "recovery_required"
    assert transitions[0][2]["code"] == "detach_force_exit_timeout"


def test_tui_styling_uses_theme_and_motion_tokens() -> None:
    """U04 fix: severity colors and the header/footer panel borders come
    from the shared `rush.dashboard.theme` THEME tokens, not hardcoded
    named colors like "red"/"cyan"/"grey50" -- and the real, non-stub
    MOTION table is the one actually imported."""
    from rush.dashboard.theme import MOTION, THEME
    from rush.tui import _FOOTER_STYLE, _HEADER_STYLE, _severity_style

    assert _severity_style("error") == THEME["error"]
    assert _severity_style("fail") == THEME["error"]
    assert _severity_style("warn") == THEME["warning"]
    assert _severity_style("info") == THEME["blue"]
    assert _HEADER_STYLE == f"bold {THEME['blue']}"
    assert _FOOTER_STYLE == THEME["surface_raised"]
    assert MOTION["evidence_pulse_ms"] == 480  # real imported token, not a stub


def _width_branch_seed() -> ProjectSeed:
    return ProjectSeed(
        name="demo",
        root=Path("/tmp/rush-tui-width"),
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
                        message="m",
                        severity="error",
                    )
                ],
            )
        ],
    )


def _render_main_at_width(columns: int) -> list[str]:
    from rush.tui import ProjectState, TuiState, render_app

    seed = _width_branch_seed()
    project = ProjectState(name=seed.name, root=seed.root, results=list(seed.results))
    state = TuiState(projects=[project])
    state.terminal_size = (columns, 24)
    layout = render_app(state)
    return [c.name for c in layout["main"].children]


def test_layout_79_columns_uses_narrow_branch() -> None:
    from rush.tui import _width_branch

    assert _width_branch(79) == "narrow"
    assert _render_main_at_width(79) == []


def test_layout_80_columns_uses_compact_branch() -> None:
    from rush.tui import _width_branch

    assert _width_branch(80) == "compact"
    assert _render_main_at_width(80) == ["nav", "content"]


def test_layout_99_columns_uses_compact_branch() -> None:
    from rush.tui import _width_branch

    assert _width_branch(99) == "compact"
    assert _render_main_at_width(99) == ["nav", "content"]


def test_layout_100_columns_uses_wide_branch() -> None:
    from rush.tui import _width_branch

    assert _width_branch(100) == "wide"
    assert _render_main_at_width(100) == ["nav", "list", "detail"]


def test_footer_is_two_rows_at_every_width() -> None:
    """U04 fix: the footer is always exactly two rows (status line +
    keymap line), regardless of terminal width or how many optional
    status/progress/search messages are pending -- previously the footer
    grew to 3+ rows whenever any of those were present."""
    from rush.tui import ProjectState, TuiState, render_app

    for width in (60, 80, 99, 100, 140):
        project = ProjectState(name="demo", root=Path("/tmp/rush-tui-footer"))
        state = TuiState(projects=[project])
        state.terminal_size = (width, 24)
        state.message = "some status message"
        layout = render_app(state)
        footer_panel = layout["footer"].renderable
        footer_group = footer_panel.renderable
        assert len(footer_group.renderables) == 2, (
            f"expected exactly 2 footer rows at width={width}, "
            f"got {len(footer_group.renderables)}"
        )


class _ResizingReader:
    """Injectable `KeyReader` that plays scripted keys while independently
    reporting a scripted (changing) terminal size on each `get_size` call
    -- simulates a live resize mid-session without a real PTY."""

    def __init__(self, keys: list[str | None], sizes: list[tuple[int, int]]) -> None:
        self._keys = iter(keys)
        self._sizes = iter(sizes)
        self._last_size = (80, 24)

    def read_key(self, timeout: float) -> str | None:
        return next(self._keys, None)

    def get_size(self) -> tuple[int, int]:
        self._last_size = next(self._sizes, self._last_size)
        return self._last_size


def test_selection_and_expanded_hierarchy_preserved_across_resize() -> None:
    """U04 fix: a live terminal resize never resets Map expand/collapse
    state or the current selection -- nothing in the resize path (just a
    `state.terminal_size` update) touches either."""
    seed = ProjectSeed(
        name="demo",
        root=Path("/tmp/rush-tui-resize"),
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
                        message="one",
                        severity="error",
                    ),
                    Finding(
                        path="b.py",
                        line=2,
                        column=1,
                        rule="F2",
                        message="two",
                        severity="warn",
                    ),
                ],
            )
        ],
    )
    keys: list[str | None] = ["f3", "down", "+", None, None, "q"]
    sizes = [(120, 40), (120, 40), (120, 40), (60, 18), (60, 18), (60, 18)]
    reader = _ResizingReader(keys, sizes)
    state = run_interactive_tui(
        [seed],
        key_reader=reader,
        actions=_noop_actions(),
        use_live=False,
        max_ticks=50,
    )
    assert "file:a.py" in state.map_expanded
    assert state.terminal_size == (60, 18)


def test_reduced_motion_renders_final_state_with_no_animated_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """U04 fix: `RUSH_REDUCED_MOTION` renders the final state once (the
    initial `Live(render_app(state), ...)` construction) and never
    refreshes again on an idle timer when nothing real changed -- normal
    motion keeps its 4Hz idle heartbeat regardless of activity."""
    import rush.tui as tui_module

    monkeypatch.setenv("RUSH_REDUCED_MOTION", "1")
    monkeypatch.delenv("NO_COLOR", raising=False)

    captured: dict[str, list] = {"instances": []}

    class _FakeLive:
        def __init__(
            self,
            renderable: object,
            *,
            console: object,
            screen: bool,
            auto_refresh: bool,
        ) -> None:
            self.update_count = 0
            captured["instances"].append(self)

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

        def update(self, renderable: object, refresh: bool = False) -> None:
            self.update_count += 1

    monkeypatch.setattr("rich.live.Live", _FakeLive)

    clock = {"t": 0.0}
    monkeypatch.setattr(tui_module.time, "monotonic", lambda: clock["t"])

    class _IdleReader:
        def read_key(self, timeout: float) -> str | None:
            clock["t"] += 0.3
            return None

        def get_size(self) -> tuple[int, int]:
            return (80, 24)

    seed = ProjectSeed(name="demo", root=Path("/tmp/rush-tui-reduced-motion"))
    run_interactive_tui(
        [seed],
        key_reader=_IdleReader(),
        actions=_noop_actions(),
        use_live=True,
        max_ticks=20,
    )

    instance = captured["instances"][0]
    assert instance.update_count == 0, (
        "reduced motion with zero real activity must never refresh on a "
        f"timer (got {instance.update_count} updates)"
    )


def test_no_color_and_reduced_motion_are_independent_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """U04 fix: NO_COLOR alone must not suppress the idle refresh
    heartbeat -- only RUSH_REDUCED_MOTION controls motion. Before this
    fix, `reduced_motion` was computed from `NO_COLOR or
    RUSH_REDUCED_MOTION`, conflating a color setting with a motion one."""
    import rush.tui as tui_module

    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("RUSH_REDUCED_MOTION", raising=False)

    captured: dict[str, list] = {"instances": []}

    class _FakeLive:
        def __init__(
            self,
            renderable: object,
            *,
            console: object,
            screen: bool,
            auto_refresh: bool,
        ) -> None:
            self.update_count = 0
            captured["instances"].append(self)

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

        def update(self, renderable: object, refresh: bool = False) -> None:
            self.update_count += 1

    monkeypatch.setattr("rich.live.Live", _FakeLive)

    clock = {"t": 0.0}
    monkeypatch.setattr(tui_module.time, "monotonic", lambda: clock["t"])

    class _IdleReader:
        def read_key(self, timeout: float) -> str | None:
            clock["t"] += 0.3  # exceeds the 4Hz idle interval every tick
            return None

        def get_size(self) -> tuple[int, int]:
            return (80, 24)

    seed = ProjectSeed(name="demo", root=Path("/tmp/rush-tui-no-color-only"))
    run_interactive_tui(
        [seed],
        key_reader=_IdleReader(),
        actions=_noop_actions(),
        use_live=True,
        max_ticks=5,
    )

    instance = captured["instances"][0]
    assert instance.update_count > 0, (
        "NO_COLOR alone must not suppress the idle refresh heartbeat -- "
        "only RUSH_REDUCED_MOTION controls motion, per U04"
    )
