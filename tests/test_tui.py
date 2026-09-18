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
    """P69-06c: F2 is bound (Phase 66 §3.8) to the same project-switch
    action Tab already performs -- tested via the injectable `KeyReader`
    seam, since real F2 escape-sequence decoding is `terminal_input.py`
    work, not in this packet's allowed files."""
    seed_a = ProjectSeed(name="alpha", root=Path("/tmp/rush-tui-f2-a"))
    seed_b = ProjectSeed(name="beta", root=Path("/tmp/rush-tui-f2-b"))
    reader = _ScriptedReader(["f2", "q"])
    state = run_interactive_tui(
        [seed_a, seed_b],
        key_reader=reader,
        actions=_noop_actions(),
        use_live=False,
        max_ticks=50,
    )
    assert state.active_index == 1
    assert state.projects[state.active_index].name == "beta"


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
    """P69-06c: F3 switches section (Phase 66 §3.8) -- bound to the same
    `toggle_git_view` action the existing `G` key already implements."""
    seed = ProjectSeed(name="demo", root=Path("/tmp/rush-tui-f3"))
    reader = _ScriptedReader(["f3", "q"])
    state = run_interactive_tui(
        [seed],
        key_reader=reader,
        actions=_noop_actions(),
        use_live=False,
        max_ticks=50,
    )
    assert state.mode == "git"


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


def test_local_scan_with_no_dashboard_server_stays_locally_owned() -> None:
    """P69-06d case (b): with no live dashboard server at start time, the
    run is locally owned -- it runs as today's daemon thread under this TUI
    process's own owner-instance lock id."""
    from rush.tui import ProjectState, _start_scan_thread

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
