"""Phase 70 T28 plan-named acceptance journeys (packets A, B and C).

`docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md` names one
selector per T28 packet in this file. Each is an end-to-end journey driven by
real key events (`run_interactive_tui` with a scripted key reader, then
`_dispatch_key`/`_pump`/`render_app`) over projects registered under
`tmp_path` with an explicit data root. Assertions name concrete visible text
and backend calls (or their absence), never layout snapshots or state flips
alone. Helpers are copied from the per-packet suites, not imported.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import sqlite3
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from rich.console import Console

from rush.setup.provision import default_data_root
from rush.tools import setup_wizard
from rush.tools.base import ToolResult
from rush.tools.review import ReviewTool
from rush.tui import (
    SECTION_LABELS,
    SECTIONS,
    ProjectSeed,
    ScanActions,
    TuiState,
    _dispatch_key,
    _poll_running_scans,
    _pump,
    _reload_after_finished_work,
    default_scan_actions,
    load_overview,
    project_key,
    render_app,
    run_interactive_tui,
)
from rush.workflows import project_run
from rush.workflows.projects import (
    _registry_path,
    read_registry_strict,
    register_project,
    resolve_project,
)

# -- shared journey helpers ---------------------------------------------------


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway HOME: `run_interactive_tui` resolves seeds through the
    default data root, which must never be the real one."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    return home


def _actions(**extra: Any) -> ScanActions:
    base: dict[str, Any] = {
        "plan_scan": lambda *a, **k: SimpleNamespace(candidates=[]),
        "execute_scan": lambda *a, **k: SimpleNamespace(aggregate={}),
        "cancel_scan_run": lambda *a, **k: {},
        "rescan_project_run": lambda *a, **k: {},
        "build_handoff": lambda *a, **k: None,
        "dispatch_handoff": lambda *a, **k: None,
        "load_scan_events": lambda *a, **k: {"events": [], "run_state": None},
        "list_agents": list,
    }
    base.update(extra)
    return ScanActions(**base)


def _render(state: TuiState, width: int = 120, height: int = 40) -> str:
    state.terminal_size = (width, height)
    console = Console(record=True, width=width, height=height, file=io.StringIO())
    console.print(render_app(state))
    return console.export_text()


def _pump_until(
    state: TuiState, actions: ScanActions, done: Callable[[], bool]
) -> None:
    deadline = time.monotonic() + 15
    while not done():
        assert time.monotonic() < deadline, "background work never applied"
        _pump(state, actions)
        time.sleep(0.01)


def _keys(state: TuiState, actions: ScanActions, *keys: str) -> None:
    for key in keys:
        _dispatch_key(state, key, actions)
        _pump(state, actions)


class _IdleReader:
    """The launch reader: no key, fixed terminal size."""

    def __init__(self, size: tuple[int, int] = (120, 40)) -> None:
        self.size = size

    def read_key(self, timeout: float) -> str | None:
        return None

    def get_size(self) -> tuple[int, int]:
        return self.size


def _launch(
    seeds: list[ProjectSeed],
    actions: ScanActions,
    data_root: Path | None,
    *,
    settle: bool = True,
) -> TuiState:
    """The real `rush ui` launch loop for one tick (no key pressed), then the
    returned state continues under `_dispatch_key`/`_pump`."""
    state = run_interactive_tui(
        seeds,
        key_reader=_IdleReader(),
        actions=actions,
        use_live=False,
        data_root=data_root,
        max_ticks=1,
    )
    if settle and state.projects:
        _pump_until(state, actions, lambda: _view_state(state, "overview") != "loading")
    return state


def _view_state(state: TuiState, section: str) -> str | None:
    view = state.views.get((project_key(state.active_project), section))
    return None if view is None else view.state


def _tree_bytes(base: Path) -> dict[str, str]:
    if not base.exists():
        return {}
    return {
        str(p.relative_to(base)): (
            hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "<dir>"
        )
        for p in base.rglob("*")
    }


def _result(tool: str, status: str, summary: str, findings: Any = ()) -> ToolResult:
    return ToolResult(
        tool=tool,
        status=status,  # type: ignore[typeddict-item]
        duration_ms=1,
        summary=summary,
        findings=list(findings),
    )


def _ok_overview(marker: str) -> dict[str, Any]:
    return {
        "status": {},
        "status_summary": marker,
        "evidence": None,
        "registration": {"state": "ok", "reason": None},
    }


# -- T28-A ----------------------------------------------------------------------


def _a_baseline_outcomes(tmp_path: Path, home: Path) -> None:
    """The three recorded baseline zero-finding results (clean, skipped
    missing engine, engine error) now render distinct outcomes and reasons on
    both Overview and Scans/Findings, switched through the real F2 selector."""
    cases = [
        ("clean", _result("lint", "ok", "no issues found")),
        ("skipped", _result("lint", "skipped", "engine not installed: ruff")),
        ("error", _result("lint", "error", "engine crashed: exit 1")),
    ]
    seeds = []
    for name, result in cases:
        root = tmp_path / name
        root.mkdir()
        seeds.append(ProjectSeed(name=name, root=root, results=[result]))
    actions = _actions(load_overview=lambda root, **k: _ok_overview(root.name))
    state = _launch(seeds, actions, tmp_path / "data")
    expected = {
        "clean": ("lint: clean -- no issues found", "Findings (0) page 1/1"),
        "skipped": (
            "lint: unavailable -- engine not installed: ruff",
            "Findings (unavailable: no tool completed)",
        ),
        "error": (
            "lint: error -- engine crashed: exit 1",
            "Findings (unavailable: no tool completed)",
        ),
    }
    overviews: dict[str, str] = {}
    scans: dict[str, str] = {}
    normal: dict[str, str] = {}
    for index, (name, _result_) in enumerate(cases):
        if index:
            _keys(state, actions, "f2", "down", "enter")
            _pump_until(
                state, actions, lambda: _view_state(state, "overview") != "loading"
            )
        assert state.active_project.name == name
        overview = _render(state)
        outcome, title = expected[name]
        assert outcome in overview, (name, overview)
        _keys(state, actions, "f3", "3")
        assert state.section == "scans"
        scan_text = _render(state, 200, 50)
        assert title in scan_text, (name, scan_text)
        overviews[name], scans[name] = overview, scan_text
        normal[name] = _render(state)
        _keys(state, actions, "f3", "1")
        assert state.section == "overview"
    assert "lint: clean" not in overviews["skipped"] + overviews["error"]
    assert "lint: unavailable" not in overviews["clean"] + overviews["error"]
    assert "lint: error" not in overviews["clean"] + overviews["skipped"]
    assert "Findings (0)" not in scans["skipped"] + scans["error"]
    # The Scans/Findings row itself must carry each outcome's reason at the
    # normal 120x40 size and at 200x50, not only the Overview line.
    hidden = [
        (name, width, str(result.get("summary")))
        for name, result in cases
        for width, text in (("120x40", normal[name]), ("200x50", scans[name]))
        if str(result.get("summary")) not in text
    ]
    assert not hidden, f"Scans/Findings rows hide the outcome reason: {hidden}"


def _a_no_project(tmp_path: Path, home: Path) -> None:
    """No project at all: a chooser (create or quit), never a crash or an
    active project fabricated from an empty list; `q` quits."""
    state = _launch([], _actions(), tmp_path / "data")
    assert state.active_index is None
    text = _render(state)
    assert "No project open." in text
    assert "[N] Create a new project  [q] Quit" in text
    _keys(state, _actions(), "N")
    assert state.overlay == "form" and state.form is not None
    assert state.form["kind"] == "project_create"
    _keys(state, _actions(), "escape")
    _keys(state, _actions(), "q")
    assert state.should_quit


def _a_unregistered(tmp_path: Path, home: Path) -> None:
    """A folder no project claims: Add/Create/Choose-later offered; Add opens a
    reviewed grant whose decline writes nothing; Choose later is shown."""
    data_root = tmp_path / "data"
    root = tmp_path / "fresh"
    root.mkdir()
    actions = _actions(load_overview=load_overview)
    state = _launch([ProjectSeed(name="fresh", root=root)], actions, data_root)
    text = _render(state)
    assert "No project registered for this folder." in text
    assert "[A] Add this folder  [N] Create a new project  [L] Choose later" in text
    _keys(state, actions, "A")
    assert state.mode == "grant_review"
    assert state.pending_grant is not None
    assert state.pending_grant["kind"] == "project_add"
    _keys(state, actions, "n")
    assert state.message == "declined"
    assert not _registry_path(data_root).exists()
    _keys(state, actions, "L")
    assert "Project choice deferred." in _render(state)


def _a_moved_root(tmp_path: Path, home: Path) -> None:
    data_root = tmp_path / "data"
    old = tmp_path / "old"
    old.mkdir()
    register_project(old, data_root=data_root)
    new = tmp_path / "new"
    old.rename(new)
    actions = _actions(load_overview=load_overview)
    state = _launch([ProjectSeed(name="new", root=new)], actions, data_root)
    text = _render(state, 300, 50)
    assert f"Project root moved: registered root missing: {old.resolve()}" in text
    assert "[R] Relink to the new root (reviewed)" in text
    assert "[A] Add this folder" not in text
    _keys(state, actions, "A")
    assert state.mode != "grant_review"
    assert state.message == "project already registered or registry not readable"
    _keys(state, actions, "R")
    assert state.overlay == "form" and state.form is not None
    assert state.form["kind"] == "project_relink"


def _a_corrupt_registry(tmp_path: Path, home: Path) -> None:
    data_root = tmp_path / "data"
    registry = _registry_path(data_root)
    registry.parent.mkdir(parents=True)
    registry.write_text("{not json", encoding="utf-8")
    root = tmp_path / "proj"
    root.mkdir()
    actions = _actions(load_overview=load_overview)
    state = _launch([ProjectSeed(name="proj", root=root)], actions, data_root)
    text = _render(state)
    assert "Registry corrupt:" in text
    assert "No project registered for this folder." not in text
    _keys(state, actions, "A")
    assert state.mode != "grant_review", "a corrupt registry must not offer Add"
    assert registry.read_text(encoding="utf-8") == "{not json"


def _a_first_load_failure(tmp_path: Path, home: Path) -> None:
    def failing(root: Path, **kwargs: Any) -> dict[str, Any]:
        raise OSError("status read failed: permission denied")

    root = tmp_path / "proj"
    root.mkdir()
    actions = _actions(load_overview=failing)
    state = _launch([ProjectSeed(name="proj", root=root)], actions, tmp_path / "data")
    assert _view_state(state, "overview") == "failed"
    text = _render(state)
    assert "Overview failed (F5 retry)" in text
    assert "status read failed: permission denied" in text
    assert "Findings (0)" not in text


def _a_refresh_failure(tmp_path: Path, home: Path) -> None:
    calls: list[int] = []

    def flaky(root: Path, **kwargs: Any) -> dict[str, Any]:
        calls.append(1)
        if len(calls) > 1:
            raise ConnectionResetError("connection reset")
        return _ok_overview("first-load-summary")

    root = tmp_path / "proj"
    root.mkdir()
    actions = _actions(load_overview=flaky)
    state = _launch([ProjectSeed(name="proj", root=root)], actions, tmp_path / "data")
    assert "Status unavailable -- first-load-summary" in _render(state)
    _keys(state, actions, "f5")
    _pump_until(state, actions, lambda: _view_state(state, "overview") == "stale")
    view = state.views[(project_key(state.active_project), "overview")]
    text = _render(state)
    assert "Overview stale (F5 retry)" in text
    assert f"last loaded {view.loaded_at}" in text
    assert "refresh failed: connection reset" in text
    assert "Status unavailable -- first-load-summary" in text, "old content kept"
    assert len(calls) == 2


def _a_zero_versus_unavailable(tmp_path: Path, home: Path) -> None:
    """Registered project with no run: counts render unavailable with a
    reason, never 0; a completed clean tool renders a real 0."""
    data_root = tmp_path / "data"
    root = tmp_path / "proj"
    root.mkdir()
    register_project(root, data_root=data_root)
    actions = _actions(load_overview=load_overview)
    state = _launch([ProjectSeed(name="proj", root=root)], actions, data_root)
    text = _render(state, 120, 60)
    assert "Runs: 0 recorded" in text
    assert "Findings: unavailable -- no completed run" in text
    assert "Coverage: unavailable -- the latest run recorded no coverage" in text
    assert "Findings: 0" not in text
    state.active_project.results = [_result("lint", "ok", "no issues found")]
    _keys(state, actions, "f3", "3")
    assert "Findings (0) page 1/1" in _render(state)
    state.active_project.results = [_result("lint", "skipped", "engine missing")]
    scans = _render(state, 200, 50)
    assert "Findings (unavailable: no tool completed)" in scans
    assert "Findings (0)" not in scans


_SECTION_MARKERS = {
    "overview": "Overview",
    "map": "Map",
    "scans": "Scan history",
    "memory": "press / to search",
    "tokens": "Tokens",
    "git": "has_git=",
    "artifacts": "Captured (",
    "setup": "Stage grants",
}


def _a_navigation_destinations(tmp_path: Path, home: Path) -> None:
    """Every one of the eight sections is reached three ways -- F3 digit, F3
    cycling, and the visible nav pane (Tab to focus, arrows, Enter) -- each
    showing its own body with the same selected project identity."""
    data_root = tmp_path / "data"
    root = tmp_path / "proj"
    root.mkdir()
    record = register_project(root, data_root=data_root)
    actions = default_scan_actions()
    actions.list_agents = list
    state = _launch([ProjectSeed(name="navproj", root=root)], actions, data_root)
    assert state.active_project.project_id == record.project_id

    def check(section: str, *, body: bool = True) -> None:
        assert state.section == section
        assert state.active_project.section == section
        assert project_key(state.active_project) == record.project_id
        text = _render(state)
        assert f"navproj  {SECTION_LABELS[section]}" in text, (section, text)
        if body:
            assert _SECTION_MARKERS[section] in text, (section, text)

    for digit, section in enumerate(SECTIONS, start=1):
        _keys(state, actions, "f3", str(digit))
        check(section)
    _keys(state, actions, "f3", "1")
    check("overview")
    # F3 inside the open chooser steps to the next section (header follows;
    # the chooser stays open until Escape shows that section's body).
    _keys(state, actions, "f3")
    for section in (*SECTIONS[1:], SECTIONS[0]):
        _keys(state, actions, "f3")
        check(section, body=False)
    _keys(state, actions, "escape")
    check("overview")
    for section in SECTIONS:
        _keys(state, actions, "f3", "1")
        while state.focus != "nav":
            _keys(state, actions, "tab")
        assert "Navigate" in _render(state)
        for _ in range(SECTIONS.index(section)):
            _keys(state, actions, "down")
        _keys(state, actions, "enter")
        check(section)


def _a_delayed_a_after_b(tmp_path: Path, home: Path) -> None:
    """Project A's Overview answers only after the user switched to B: A's
    late answer is never applied or shown; returning to A reloads A's own."""
    release = threading.Event()
    calls: list[str] = []

    def loader(root: Path, **kwargs: Any) -> dict[str, Any]:
        calls.append(root.name)
        if root.name == "a" and len(calls) == 1:
            release.wait(10)
            return _ok_overview("A-LATE-ANSWER")
        return _ok_overview(f"{root.name.upper()}-ANSWER")

    seeds = []
    for name in ("a", "b"):
        (tmp_path / name).mkdir()
        seeds.append(ProjectSeed(name=name, root=tmp_path / name))
    actions = _actions(load_overview=loader)
    state = _launch(seeds, actions, tmp_path / "data", settle=False)
    project_a = state.projects[0]
    assert "overview" in project_a.pending
    _keys(state, actions, "f2", "down", "enter")
    assert state.active_project.name == "b"
    _pump_until(state, actions, lambda: _view_state(state, "overview") == "populated")
    release.set()
    time.sleep(0.2)
    _pump(state, actions)
    text = _render(state)
    assert "B-ANSWER" in text
    assert "A-LATE-ANSWER" not in text
    assert (project_key(project_a), "overview") not in state.views or state.views[
        (project_key(project_a), "overview")
    ].data is None
    _keys(state, actions, "f2", "up", "enter")
    assert state.active_project is project_a
    _pump_until(state, actions, lambda: _view_state(state, "overview") == "populated")
    text = _render(state)
    assert "A-ANSWER" in text and "A-LATE-ANSWER" not in text
    assert calls.count("a") == 2


def _a_reads_zero_write(tmp_path: Path, home: Path) -> None:
    """The launch read and a visit to every section create or change nothing
    under the data root, the project tree or HOME: no registry, store, lock
    or telemetry file."""
    import subprocess

    data_root = tmp_path / "data"
    root = tmp_path / "proj"
    root.mkdir()
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run([*git, "init", "-q"], cwd=root, check=True)
    (root / "a.py").write_text("x = 1\n")
    subprocess.run([*git, "add", "a.py"], cwd=root, check=True)
    subprocess.run([*git, "commit", "-qm", "c"], cwd=root, check=True)
    register_project(root, data_root=data_root)
    before = {b: _tree_bytes(b) for b in (data_root, root, home)}
    actions = default_scan_actions()
    state = _launch([ProjectSeed(name="proj", root=root)], actions, data_root)
    for digit in range(1, len(SECTIONS) + 1):
        _keys(state, actions, "f3", str(digit))
        _pump_until(
            state, actions, lambda: _view_state(state, state.section) != "loading"
        )
        _render(state)
    after = {b: _tree_bytes(b) for b in (data_root, root, home)}
    for base, prior in before.items():
        created = set(after[base]) - set(prior)
        changed = {k for k, digest in prior.items() if after[base].get(k) != digest}
        assert not created and not changed, (base, created, changed)


_A_CASES: dict[str, Callable[[Path, Path], None]] = {
    "baseline_outcomes": _a_baseline_outcomes,
    "no_project": _a_no_project,
    "unregistered": _a_unregistered,
    "moved_root": _a_moved_root,
    "corrupt_registry": _a_corrupt_registry,
    "first_load_failure": _a_first_load_failure,
    "refresh_failure": _a_refresh_failure,
    "zero_versus_unavailable": _a_zero_versus_unavailable,
    "navigation_destinations": _a_navigation_destinations,
    "delayed_a_after_b": _a_delayed_a_after_b,
    "reads_zero_write": _a_reads_zero_write,
}


@pytest.mark.parametrize("case", list(_A_CASES))
def test_t28a_workspace_and_outcomes(case: str, tmp_path: Path, home: Path) -> None:
    _A_CASES[case](tmp_path, home)


# -- T28-B ----------------------------------------------------------------------


def _settle(state: TuiState, actions: ScanActions) -> None:
    """The run loop's own per-tick work (drain loads, poll running scans,
    reload views after finished work) until nothing is running or loading."""
    seen = state.__dict__.setdefault("_journey_seen", {})
    deadline = time.monotonic() + 30
    while True:
        _pump(state, actions)
        _poll_running_scans(state, actions)
        _reload_after_finished_work(state, seen)
        threads = [
            t
            for p in state.projects
            for t in (p.scan_thread, p.setup_apply_thread)
            if t is not None and t.is_alive()
        ]
        busy = any(p.status in ("scanning", "cancelling") for p in state.projects)
        loading = state.load_requests or any(p.pending for p in state.projects)
        if not threads and not busy and not loading:
            return
        assert time.monotonic() < deadline, "work never settled"
        time.sleep(0.02)


def _select_agent(state: TuiState, actions: ScanActions, agent_id: str) -> None:
    """Setup/Agents: `a` cycles the detected agents until `agent_id`."""
    _keys(state, actions, "f3", "8")
    for _ in range(12):
        if state.selected_agent_id == agent_id:
            return
        _keys(state, actions, "a")
    pytest.fail(f"agent {agent_id!r} never offered by `a`: {state.agent_ids!r}")


def _handoff_files(root: Path) -> list[str]:
    handoffs = root / ".rush" / "handoffs"
    return sorted(p.name for p in handoffs.glob("*.json")) if handoffs.is_dir() else []


def _b_full_cycle(tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """new project -> declined then accepted setup -> verified configured
    host -> faulty real fixture scan -> selected finding and agent -> denied
    then approved handoff -> actual returned receipt -> rescan -> old and new
    findings, all through the real shared project/plan/execute/handoff/
    rescan adapters (`default_scan_actions`)."""
    monkeypatch.setattr(project_run, "ALL_TOOLS", [ReviewTool()])
    data_root = default_data_root()
    root = tmp_path / "repair"
    root.mkdir()
    (root / "app.py").write_text("def unreviewed():\n    pass\n", encoding="utf-8")
    applied: list[str] = []
    real_apply = setup_wizard.apply_setup_review

    def spy_apply(review: dict[str, Any], *args: Any, **kwargs: Any) -> Any:
        applied.append(review["review_id"])
        return real_apply(review, *args, **kwargs)

    monkeypatch.setattr(setup_wizard, "apply_setup_review", spy_apply)
    actions = default_scan_actions()
    state = _launch([ProjectSeed(name="repair", root=root)], actions, data_root)
    gaps: list[str] = []

    # new project
    assert "No project registered for this folder." in _render(state, 200, 50)

    # declined, then accepted setup (config, register, configure toggled on)
    _keys(state, actions, "f3", "8")
    text = _render(state, 200, 60)
    assert "1. Config: create rush.toml" in text, text
    assert "2. Register: add project" in text
    _keys(state, actions, "t", "j", "t", "j", "t")
    assert "config_create on, register on, >configure on" in _render(state, 400, 80)
    _keys(state, actions, "p")
    assert state.mode == "grant_review"
    review_text = _render(state, 200, 60)
    assert "stages: config_create, register, configure" in review_text
    assert "grants: artifact_write, cache_write" in review_text
    _keys(state, actions, "n")
    assert state.message == "declined"
    assert applied == [], "a declined setup review applies nothing"
    assert not (root / "rush.toml").exists()
    assert not _registry_path(data_root).exists()
    _keys(state, actions, "p", "y")
    _settle(state, actions)
    assert len(applied) == 1
    project = state.active_project
    assert project.setup_apply_events == [
        ("config", "started"),
        ("config", "completed"),
        ("register", "started"),
        ("register", "completed"),
        ("configure", "started"),
        ("configure", "completed"),
        ("engines", "started"),
        ("engines", "completed"),
    ], (project.setup_apply_events, project.last_message)
    text = _render(state, 200, 60)
    for needle in ("config completed", "register completed", "engines completed"):
        assert needle in text, needle
    assert (root / "rush.toml").is_file()
    record = resolve_project(root, data_root=data_root)
    assert Path(record["root"]) == root.resolve()

    # readback on Overview: the registry now reports the project
    _keys(state, actions, "f3", "1", "f5")
    _settle(state, actions)
    assert state.active_project.project_id == record["project_id"]
    overview = _render(state, 200, 60)
    assert "No project registered for this folder." not in overview
    assert "registration: registered" in overview, overview

    # verified configured host: the Setup/Agents section binds a selected
    # T26 host (Claude Code / Codex) with its configured/connected/verified
    # states kept separate.
    _select_agent(state, actions, "claude-code")
    setup_text = _render(state, 200, 60)
    if "Host: Claude Code" not in setup_text:
        gaps.append(
            "Setup/Agents with claude-code selected shows no T26 host stage "
            "('Host: Claude Code'): no host registration, readback or "
            "capability verification is reachable from the TUI"
        )

    # faulty real fixture scan
    _keys(state, actions, "f3", "3", "s")
    assert state.mode == "grant_review"
    assert "summary: Run a full scan" in _render(state, 200, 60)
    _keys(state, actions, "y")
    _settle(state, actions)
    project = state.active_project
    baseline_run = project.run_id
    assert baseline_run, project.last_message
    assert project.status == "complete", (project.status, project.last_message)
    baseline_ids = [row["finding_id"] for row in project.flattened_findings()]
    assert baseline_ids, "the ReviewTool fixture scan must report a finding"
    scans = _render(state, 200, 60)
    assert baseline_run in scans, "Scans history lists the finished run"
    if "app.py:1" not in scans:
        gaps.append(
            "Scans/Findings row for the real scan finding hides its location: "
            f"{project.flattened_findings()[0].get('path')!r} is cut to 30 "
            "columns so 'app.py:1' never shows"
        )

    # selected finding
    _keys(state, actions, "enter")
    assert state.mode == "detail"
    detail = _render(state, 200, 60)
    first = project.visible_findings()[0]
    assert str(first["message"]) in detail, detail
    if "def unreviewed():" not in detail:
        gaps.append(
            "Detail of the real scan finding shows only its message, not the "
            f"file content around {first.get('path')}:{first.get('line')} "
            "(live file context refused)"
        )
    _keys(state, actions, "escape")

    # selected agent, denied then approved handoff
    _select_agent(state, actions, "claude-code")
    _keys(state, actions, "f3", "3", "H")
    assert state.mode == "grant_review", state.message
    review_text = _render(state, 200, 60)
    assert f"run_id: {baseline_run}" in review_text
    assert "agent_id: claude-code" in review_text
    assert f"finding_count: {len(baseline_ids)}" in review_text
    _keys(state, actions, "n")
    assert state.message == "declined"
    assert _handoff_files(root) == [], "a denied handoff prepares nothing"
    _keys(state, actions, "H", "y")
    _settle(state, actions)
    assert state.message == "handoff delivered", (state.message, project.last_message)
    handoff_id = project.last_message.split()[1]
    receipt = project_run.status_handoff(
        record["project_id"], handoff_id, data_root=data_root
    )
    assert receipt["state"] == "delivered"
    assert _handoff_files(root) == [f"{handoff_id}.json"]
    _keys(state, actions, "f3", "1")
    overview = _render(state, 200, 60)
    assert f"handoff {handoff_id} delivered" in overview
    assert "repaired" not in overview.lower()

    # rescan the reviewed baseline against changed source
    (root / "app.py").write_text("def unreviewed():\n    return 1\n", encoding="utf-8")
    (root / "second.py").write_text("def second():\n    pass\n", encoding="utf-8")
    _keys(state, actions, "f3", "3", "r")
    assert state.mode == "grant_review"
    assert f"run_id: {baseline_run}" in _render(state, 200, 60)
    _keys(state, actions, "y")
    _settle(state, actions)
    if project.run_id == baseline_run:
        gaps.append(
            f"the approved rescan of {baseline_run} never ran: "
            f"{project.last_message!r}, yet the project status reads "
            f"{project.status!r}"
        )
        pytest.fail("\n".join(gaps))
    assert project.status == "complete", (project.status, project.last_message)
    current_ids = [row["finding_id"] for row in project.flattened_findings()]
    _keys(state, actions, "f5")
    _settle(state, actions)
    scans = _render(state, 200, 80)
    assert baseline_run in scans and str(project.run_id) in scans, "both runs listed"
    # old and new findings: the rescan's comparison against the reviewed
    # baseline (resolved / persisting / new) is visible, not only the new list.
    if not any(word in scans for word in ("resolved", "persisting", "new finding")):
        gaps.append(
            "after rescan, Scans shows only the new run's rows: the baseline's "
            f"old findings {baseline_ids} and the comparison verdicts for "
            f"{current_ids} (resolved/persisting/new) are not visible"
        )
    assert not gaps, "\n".join(gaps)


def _b_unavailable_agent(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An agent chosen in Setup/Agents disappears before dispatch: the
    Agents view shows it unavailable with its cause; nothing is delivered."""
    agents = ["ghost", "agent-1"]
    root = tmp_path / "proj"
    root.mkdir()
    dispatched: list[Any] = []

    def dispatch(*args: Any, **kwargs: Any) -> Any:
        dispatched.append(args)
        raise RuntimeError("ghost not found")

    actions = _fake_repair_actions(
        list_agents=lambda: list(agents), dispatch_handoff=dispatch
    )
    state = _launch([_repair_seed(root)], actions, tmp_path / "data")
    _scan_once(state, actions)
    _select_agent(state, actions, "ghost")
    agents.remove("ghost")
    _keys(state, actions, "f3", "3", "H", "y")
    assert dispatched, "the approved handoff reached dispatch"
    assert state.message == "agent ghost unavailable: ghost not found"
    _keys(state, actions, "f3", "8")
    text = _render(state, 200, 60)
    assert "Agent unavailable" in text
    assert "agent ghost unavailable: ghost not found" in text
    assert "delivered" not in text


def _b_stale_review(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A handoff reviewed against one result set: a scan publishing before
    confirmation makes the review stale -- nothing is built or sent."""
    root = tmp_path / "proj"
    root.mkdir()
    built: list[Any] = []

    def build(*args: Any, **kwargs: Any) -> Any:
        built.append(args)
        return SimpleNamespace(handoff_id="h1", session_capability="c")

    actions = _fake_repair_actions(build_handoff=build)
    state = _launch([_repair_seed(root)], actions, tmp_path / "data")
    _scan_once(state, actions)
    _select_agent(state, actions, "agent-1")
    _keys(state, actions, "f3", "3", "H")
    assert state.mode == "grant_review"
    # a background scan publishes a new result set while the review is open
    state.active_project.results = [_result("lint", "ok", "clean after fix")]
    _keys(state, actions, "y")
    assert state.message == "handoff review is stale; nothing was run"
    assert built == []
    assert "handoff review is stale; nothing was run" in _render(state, 200, 60)


def _b_wrong_run(tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The run a handoff names no longer exists on disk: the real adapter
    refuses and the cause is shown; nothing is prepared or delivered."""
    import shutil

    monkeypatch.setattr(project_run, "ALL_TOOLS", [ReviewTool()])
    data_root = default_data_root()
    root = tmp_path / "repair"
    root.mkdir()
    (root / "app.py").write_text("def unreviewed():\n    pass\n", encoding="utf-8")
    register_project(root, data_root=data_root)
    actions = default_scan_actions()
    state = _launch([ProjectSeed(name="repair", root=root)], actions, data_root)
    _keys(state, actions, "f3", "3", "s", "y")
    _settle(state, actions)
    run_id = state.active_project.run_id
    assert run_id and state.active_project.status == "complete"
    shutil.rmtree(root / ".rush" / "runs" / run_id)
    _select_agent(state, actions, "claude-code")
    _keys(state, actions, "f3", "3", "H", "y")
    assert state.message.startswith("handoff failed:"), state.message
    assert "delivered" not in state.message
    assert _handoff_files(root) == []
    assert state.message in _render(state, 300, 60)


def _b_failed_dispatch(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dispatch fails for an available agent: the real cause shows, the
    agent stays available, and no receipt is claimed."""
    root = tmp_path / "proj"
    root.mkdir()
    actions = _fake_repair_actions(
        dispatch_handoff=lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("agent unreachable")
        )
    )
    state = _launch([_repair_seed(root)], actions, tmp_path / "data")
    _scan_once(state, actions)
    _select_agent(state, actions, "agent-1")
    _keys(state, actions, "f3", "3", "H", "y")
    assert state.message == "handoff failed: agent unreachable"
    assert state.active_project.status == "error"
    assert (project_key(state.active_project), "agents") not in state.views
    text = _render(state, 200, 60)
    assert "handoff failed: agent unreachable" in text
    assert "delivered" not in text


def _b_newer_attempt_race(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rescan reviewed against run-1: a newer attempt published before
    confirmation invalidates it; the rescan adapter is never called."""
    root = tmp_path / "proj"
    root.mkdir()
    rescans: list[Any] = []

    def rescan(*args: Any, **kwargs: Any) -> dict[str, Any]:
        rescans.append((args, kwargs))
        return {"run": {}}

    actions = _fake_repair_actions(rescan_project_run=rescan)
    state = _launch([_repair_seed(root)], actions, tmp_path / "data")
    _scan_once(state, actions)
    reviewed = state.active_project.run_id
    _keys(state, actions, "f3", "3", "r")
    assert state.pending_grant is not None
    assert state.pending_grant["run_id"] == reviewed
    state.active_project.run_id = "newer-run"  # a newer attempt finished meanwhile
    _keys(state, actions, "y")
    assert rescans == []
    assert state.message == "rescan review is stale; nothing was run"


def _b_partial_setup_rerun(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first apply fails at configure (partial); retry regenerates the
    review, and the rerun applies the fresh review to completion."""
    data_root = default_data_root()
    root = tmp_path / "proj"
    root.mkdir()
    real_apply = setup_wizard.apply_setup_review
    applied: list[str] = []

    def apply(
        review: dict[str, Any], *args: Any, on_progress: Any = None, **kw: Any
    ) -> Any:
        applied.append(review["review_id"])
        if len(applied) == 1:
            on_progress("configure", "started")
            on_progress("configure", "failed")
            return {"status": "partial"}
        return real_apply(review, *args, on_progress=on_progress, **kw)

    monkeypatch.setattr(setup_wizard, "apply_setup_review", apply)
    actions = _fake_repair_actions()
    state = _launch([ProjectSeed(name="proj", root=root)], actions, data_root)
    _keys(state, actions, "f3", "8", "t", "j", "t", "j", "t", "p", "y")
    _settle(state, actions)
    assert "configure failed" in _render(state, 200, 60)
    assert state.active_project.last_message == "setup apply partial"
    _keys(state, actions, "x")
    assert state.pending_grant is not None
    assert state.pending_grant["failed_stage"] == "configure"
    _keys(state, actions, "y")
    assert "review regenerated" in state.message
    _keys(state, actions, "p", "y")
    _settle(state, actions)
    assert len(applied) == 2, "retry reran the apply exactly once"
    assert state.active_project.last_message == "setup apply ok", (
        state.active_project.setup_apply_events
    )
    assert ("engines", "completed") in state.active_project.setup_apply_events
    assert (root / "rush.toml").is_file()
    assert read_registry_strict(data_root)["state"] == "ok"


def _b_cancel_acknowledged(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`c` during a running scan sends the run's cancel marker; the
    worker's acknowledgment lands as a visible cancelled outcome."""
    root = tmp_path / "proj"
    root.mkdir()
    started = threading.Event()
    cancelled = threading.Event()
    cancel_calls: list[tuple[Path, str]] = []

    def execute(plan: Any, **kwargs: Any) -> Any:
        started.set()
        assert cancelled.wait(10), "cancel never reached the worker"
        return SimpleNamespace(aggregate=None)

    def cancel(root_: Path, run_id: str) -> dict[str, Any]:
        cancel_calls.append((root_, run_id))
        cancelled.set()
        return {}

    def events(root_: Path, run_id: str) -> dict[str, Any]:
        return {
            "events": [],
            "run_state": "cancelled" if cancelled.is_set() else None,
        }

    actions = _fake_repair_actions(
        execute_scan=execute, cancel_scan_run=cancel, load_scan_events=events
    )
    state = _launch([_repair_seed(root)], actions, tmp_path / "data")
    _keys(state, actions, "f3", "3", "s", "y")
    assert started.wait(10)
    project = state.active_project
    assert project.status == "scanning", project.last_message
    _keys(state, actions, "c")
    assert cancel_calls == [(root, project.run_id)]
    assert project.status == "cancelling"
    _settle(state, actions)
    assert project.status == "cancelled"
    shown = {}
    for digit, section in (("1", "overview"), ("3", "scans")):
        _keys(state, actions, "f3", digit)
        shown[section] = "cancelled" in _render(state, 200, 60)
    assert all(shown.values()), f"acknowledged cancel visible per section: {shown}"


def _fake_repair_actions(**extra: Any) -> ScanActions:
    base: dict[str, Any] = {
        "plan_scan": lambda *a, **k: SimpleNamespace(plan_id="plan-1", candidates=[1]),
        "execute_scan": lambda *a, **k: SimpleNamespace(aggregate=_repair_aggregate()),
        "build_handoff": lambda *a, **k: SimpleNamespace(
            handoff_id="h1", session_capability="c1"
        ),
        "dispatch_handoff": lambda *a, **k: SimpleNamespace(state="delivered"),
        "rescan_project_run": lambda *a, **k: {"run": {"run_id": "run-2"}},
        "load_scan_events": lambda *a, **k: {"events": [], "run_state": "completed"},
        "list_agents": lambda: ["agent-1"],
        "dashboard_owner": lambda root: None,
        "load_overview": lambda root, **k: _ok_overview(root.name),
    }
    base.update(extra)
    return _actions(**base)


def _scan_once(state: TuiState, actions: ScanActions) -> None:
    """A reviewed scan (`s`, `y`) records the run the repair steps target."""
    _keys(state, actions, "f3", "3", "s", "y")
    _settle(state, actions)
    assert state.active_project.run_id, state.active_project.last_message


def _repair_aggregate() -> dict[str, Any]:
    return dict(_repair_seed(Path(".")).results[0])


def _repair_seed(root: Path) -> ProjectSeed:
    finding = {
        "path": "a.py",
        "line": 1,
        "column": 1,
        "rule": "F1",
        "message": "issue in a.py",
        "severity": "error",
        "finding_id": "fa",
    }
    return ProjectSeed(
        name="proj",
        root=root,
        results=[_result("lint", "fail", "1 finding", [finding])],
    )


_B_CASES: dict[str, Callable[[Path, Path, pytest.MonkeyPatch], None]] = {
    "full_cycle": _b_full_cycle,
    "unavailable_agent": _b_unavailable_agent,
    "stale_review": _b_stale_review,
    "wrong_run": _b_wrong_run,
    "failed_dispatch": _b_failed_dispatch,
    "newer_attempt_race": _b_newer_attempt_race,
    "partial_setup_rerun": _b_partial_setup_rerun,
    "cancel_acknowledged": _b_cancel_acknowledged,
}


@pytest.mark.usefixtures("hermetic_engine_path")
@pytest.mark.parametrize("case", list(_B_CASES))
def test_t28b_setup_handoff_rescan(
    case: str, tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _B_CASES[case](tmp_path, home, monkeypatch)


# -- T28-C ----------------------------------------------------------------------

_FIXTURES = Path(__file__).parent / "fixtures" / "dashboard"


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def _record_run(
    root: Path,
    project_id: str,
    *,
    run_id: str,
    findings: list[dict[str, Any]],
    files: list[str] | None = None,
    raw_text: str | None = None,
) -> None:
    """A recorded current attempt: a chronology-valid attempt header plus its
    terminal manifest (the `project_map_snapshot` inputs)."""
    attempt = root / ".rush" / "runs" / run_id / "attempts" / "1"
    attempt.mkdir(parents=True)
    (attempt / "attempt.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "attempt_id": "1",
                "started_at": datetime.now(UTC).isoformat(),
                "project_id": project_id,
                "attempt_generation": 1,
            }
        ),
        encoding="utf-8",
    )
    manifest = attempt / "manifest.json"
    if raw_text is not None:
        manifest.write_text(raw_text, encoding="utf-8")
        return
    body: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "attempt_id": "1",
        "run_state": "completed",
        "aggregate": {"findings": findings},
        "totals": {"finding_count": len(findings)},
    }
    if files is not None:
        body["file_inventory"] = [{"path": path} for path in files]
    manifest.write_text(json.dumps(body), encoding="utf-8")


def _record_handoff(
    root: Path, run_id: str, agent_id: str, finding_ids: list[str]
) -> None:
    handoffs = root / ".rush" / "handoffs"
    handoffs.mkdir(parents=True, exist_ok=True)
    (handoffs / f"h-{agent_id}.json").write_text(
        json.dumps(
            {
                "handoff_id": f"h-{agent_id}",
                "run_id": run_id,
                "agent_id": agent_id,
                "finding_ids": finding_ids,
            }
        ),
        encoding="utf-8",
    )


def _record_memory(root: Path, memory_id: str, symbol_ref: str) -> None:
    db = root / ".rush" / "memory.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS memory_artifacts "
            "(id TEXT, symbol_ref TEXT, source TEXT)"
        )
        conn.execute(
            "INSERT INTO memory_artifacts VALUES (?, ?, 'agent')",
            (memory_id, symbol_ref),
        )
        conn.commit()
    finally:
        conn.close()


def _fixture_project(
    tmp_path: Path, fixture: str, data_root: Path | None = None
) -> tuple[Path, str, dict[str, Any]]:
    """A registered project whose recorded current run carries the fixture's
    findings, memories (memory.db) and agents (run-scoped handoffs)."""
    snapshot = _fixture(fixture)
    root = tmp_path / snapshot["project_id"]
    for entry in snapshot["files"]:
        path = root / entry["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {snapshot['project_id']} {entry['path']}\n" * 10)
    record = register_project(root, data_root=data_root or default_data_root())
    findings = [
        {
            "finding_id": f["id"],
            "path": f["path"],
            "line": f["line"],
            "severity": f["severity"],
            "rule": "R1",
            "message": f"{f['id']} in {f['path']}",
            "provenance": "ruff/ruff-0.6",
        }
        for f in snapshot["findings"]
    ]
    _record_run(
        root,
        record.project_id,
        run_id="run-1",
        findings=findings,
        files=[f["path"] for f in snapshot["files"]],
    )
    for memory in snapshot["memories"]:
        for cite in memory["cites"]:
            if cite.endswith(".py"):
                _record_memory(root, memory["id"], f"{cite}::f")
    for agent in snapshot["agents"]:
        _record_handoff(root, "run-1", agent["id"], agent["assigned_to"])
    return root, record.project_id, snapshot


def _map_text(state: TuiState, actions: ScanActions) -> str:
    """Enter Map, expand every expandable node, return the rendered text."""
    _keys(state, actions, "f3", "2")
    assert state.section == "map"
    from rush.tui import _map_visible_nodes

    for _ in range(200):
        _render(state, 300, 120)  # a frame loads the Map's recorded snapshot
        nodes = _map_visible_nodes(state.active_project, state.map_expanded)
        closed = [
            i
            for i, n in enumerate(nodes)
            if n.get("children")
            and n["key"] not in state.map_expanded
            and n.get("kind") != "more"
        ]
        if not closed:
            break
        state.map_selected_index = 0
        _keys(state, actions, *(["down"] * closed[0]), "right")
    return _render(state, 300, 120)


def _no_controls(text: str) -> None:
    assert "\x1b" not in text and "\x07" not in text, repr(text[:300])


def _c_zero_finding_outcomes(tmp_path: Path, home: Path) -> None:
    """clean / skipped / denied / error with no findings: every tool row
    shows its engine, version, status, reason and execution time on
    Scans/Findings, and each row expands to its own detail."""
    root = tmp_path / "proj"
    root.mkdir()
    results = [
        ToolResult(
            tool="ruff",
            engine="ruff",
            engine_version="0.6.9",
            status="ok",
            duration_ms=41,
            summary="clean",
            findings=[],
        ),  # type: ignore[typeddict-item]
        ToolResult(
            tool="bandit",
            engine="bandit",
            engine_version=None,
            status="skipped",
            duration_ms=0,
            summary="engine not installed",
            findings=[],
        ),  # type: ignore[typeddict-item]
        ToolResult(
            tool="semgrep",
            engine="semgrep",
            engine_version="1.90.0",
            status="skipped",
            duration_ms=0,
            summary="denied: missing artifact_write grant",
            findings=[],
        ),  # type: ignore[typeddict-item]
        ToolResult(
            tool="mypy",
            engine="mypy",
            engine_version="1.11.2",
            status="error",
            duration_ms=1250,
            summary="typecheck crashed",
            findings=[],
        ),  # type: ignore[typeddict-item]
    ]
    actions = _actions(load_overview=lambda root, **k: _ok_overview("proj"))
    state = _launch(
        [ProjectSeed(name="proj", root=root, results=results)], actions, None
    )
    _keys(state, actions, "f3", "3")
    text = _render(state, 200, 50)
    missing = [
        needle
        for needle in (
            "ruff",
            "0.6.9",
            "41",
            "clean",
            "bandit",
            "engine not installed",
            "semgrep",
            "1.90.0",
            "denied: missing artifact_write grant",
            "mypy",
            "1.11.2",
            "1250",
            "typecheck crashed",
        )
        if needle not in text
    ]
    _keys(state, actions, "enter")
    expanded = state.mode == "detail"
    assert not missing and expanded, (
        f"Scans/Findings at 200x50 hides {missing}; Enter on an outcome row "
        f"opens its detail: {expanded}"
    )


def _c_partial_suite(tmp_path: Path, home: Path) -> None:
    """A check started with `C` is still running: Scans shows the finished
    tool rows and a visible running row; when it ends the running row goes."""
    root = tmp_path / "proj"
    root.mkdir()
    release = threading.Event()

    def suite(root_: Path, **kwargs: Any) -> Any:
        assert release.wait(10)
        return _result("suite", "ok", "check suite finished")

    actions = _actions(
        run_check_suite=suite,
        load_overview=lambda root, **k: _ok_overview("proj"),
        dashboard_owner=lambda root: None,
    )
    seed = ProjectSeed(name="proj", root=root, results=[_result("ruff", "ok", "clean")])
    state = _launch([seed], actions, None)
    _keys(state, actions, "f3", "3", "C")
    project = state.active_project
    assert project.status == "scanning", (state.message, project.last_message)
    running_row = re.compile(r"suite\s+│\s+-\s+│\s+running")
    text = _render(state, 200, 50)
    assert running_row.search(text), text
    assert re.search(r"ruff\s+│\s+-\s+│\s+ok", text), "finished tool row kept"
    release.set()
    _settle(state, actions)
    text = _render(state, 200, 50)
    assert not running_row.search(text)
    assert re.search(r"suite\s+│\s+-\s+│\s+ok", text), text


def _c_result_pages(tmp_path: Path, home: Path) -> None:
    """25 findings: page 1/2 then, moving the cursor past row 20, page 2/2
    with the later rows; every row keeps its tool and location."""
    root = tmp_path / "proj"
    root.mkdir()
    findings = [
        {
            "path": f"f{i:02d}.py",
            "line": i + 1,
            "message": f"msg-{i:02d}",
            "severity": "warn",
            "finding_id": f"id-{i:02d}",
        }
        for i in range(25)
    ]
    actions = _actions(load_overview=lambda root, **k: _ok_overview("proj"))
    seed = ProjectSeed(
        name="proj", root=root, results=[_result("ruff", "fail", "25", findings)]
    )
    state = _launch([seed], actions, None)
    _keys(state, actions, "f3", "3")
    first = _render(state, 200, 60)
    assert "Findings (25) page 1/2" in first
    assert "f00.py:1" in first and "f24.py" not in first
    _keys(state, actions, *(["down"] * 22))
    second = _render(state, 200, 60)
    assert "Findings (25) page 2/2" in second, second
    assert "f24.py:25" in second and "f00.py:1" not in second
    _keys(state, actions, "enter")
    assert "msg-22" in _render(state, 200, 60)


def _c_long_report(tmp_path: Path, home: Path) -> None:
    """A 3000-line file with a finding at line 1500: Detail opens at the
    finding, says earlier lines exist, and scrolls both ways."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "big.py").write_text(
        "\n".join(f"row_{i:04d} = {i}" for i in range(1, 3001)) + "\n",
        encoding="utf-8",
    )
    finding = {
        "path": "big.py",
        "line": 1500,
        "message": "too long",
        "severity": "warn",
        "finding_id": "big-1",
    }
    actions = _actions(load_overview=lambda root, **k: _ok_overview("proj"))
    seed = ProjectSeed(
        name="proj", root=root, results=[_result("ruff", "fail", "1", [finding])]
    )
    state = _launch([seed], actions, None)
    _keys(state, actions, "f3", "3", "enter")
    text = _render(state, 120, 40)
    assert "row_1500 = 1500" in text and "earlier lines above" in text
    assert "too long" in text
    _keys(state, actions, *(["down"] * 40))
    assert "row_1540 = 1540" in _render(state, 120, 40)
    _keys(state, actions, *(["up"] * 2000))
    assert "row_0001 = 1" in _render(state, 120, 40)


def _c_duplicate_paths(tmp_path: Path, home: Path) -> None:
    """Two registered projects both containing src/a.py: switching with F2
    shows only the selected project's findings, relations and file text."""
    root_a, _id_a, snap_a = _fixture_project(tmp_path, "project_a.json")
    root_b, _id_b, snap_b = _fixture_project(tmp_path, "project_b.json")
    actions = _actions(load_overview=load_overview, dashboard_owner=lambda root: None)
    seeds = [ProjectSeed(name="A", root=root_a), ProjectSeed(name="B", root=root_b)]
    state = _launch(seeds, actions, default_data_root())
    _keys(state, actions, "f2", "down", "enter")
    assert state.active_project.name == "B"
    text = _map_text(state, actions)
    assert "m1-b -> src/a.py" in text and "ag1-b -> f1-b" in text, text
    assert "m1 -> " not in text and "ag1 -> " not in text, "A's relations leak into B"
    assert not any(f"{f['id']} in " in text for f in snap_a["findings"])
    shown = [f["id"] for f in snap_b["findings"] if f"{f['id']} in src/" in text]
    assert shown == [f["id"] for f in snap_b["findings"]], (
        f"B's recorded findings on its Map: {shown}"
    )


def _c_mixed_graph_edges(tmp_path: Path, home: Path) -> None:
    """The recorded current run of fixture project A, relaunched without a
    new analysis: the Map shows every file, finding, memory and agent node of
    the shared `build_project_map` projection with each exact edge."""
    from rush.dashboard.project_map import build_project_map
    from rush.workflows.projects import project_map_snapshot

    root, project_id, _snap = _fixture_project(tmp_path, "project_a.json")
    actions = _actions(load_overview=load_overview, dashboard_owner=lambda root: None)
    state = _launch([ProjectSeed(name="A", root=root)], actions, default_data_root())
    text = _map_text(state, actions)
    snapshot = project_map_snapshot(resolve_project(project_id), None, None)
    graph = build_project_map(snapshot)
    assert {e["relation"] for e in graph["edges"]} == {
        "contains",
        "reports",
        "cites",
        "assigned_to",
    }, "the shared projection records every relation of the fixture"
    missing = []
    for finding in snapshot["findings"]:
        # reports: the recorded finding is a node under its own file
        if f"{finding['id']} in {finding['path']}" not in text:
            missing.append(("reports", finding["id"], finding["path"]))
    for memory in snapshot["memories"]:
        if f"{memory['id']} -> {', '.join(memory['cites'])}" not in text:
            missing.append(("cites", memory["id"], memory["cites"]))
    for agent in snapshot["agents"]:
        if f"{agent['id']} -> {', '.join(agent['assigned_to'])}" not in text:
            missing.append(("assigned_to", agent["id"], agent["assigned_to"]))
    assert not missing, f"Map is missing recorded nodes/edges {missing}:\n{text}"


def _c_collapsed_search(tmp_path: Path, home: Path) -> None:
    """`/` on the Map finds a file under a collapsed directory beyond its
    first page, and an agent leaf under the collapsed Agents branch."""
    root, project_id, _snap = _fixture_project(tmp_path, "project_a.json")
    files = ["src/a.py", "src/b.py", "deep/nested/target_mod.py"] + [
        f"big/f_{i:04d}.py" for i in range(250)
    ]
    import shutil

    shutil.rmtree(root / ".rush" / "runs")
    _record_run(root, project_id, run_id="run-1", findings=[], files=files)
    _record_handoff(root, "run-1", "ag1", ["f1"])
    actions = _actions(load_overview=load_overview, dashboard_owner=lambda root: None)
    state = _launch([ProjectSeed(name="A", root=root)], actions, default_data_root())
    _keys(state, actions, "f3", "2")
    _render(state, 300, 120)  # a frame loads the Map's recorded snapshot
    from rush.tui import _map_visible_nodes

    for query, expected in (
        ("f_0230", "file:big/f_0230.py"),
        ("target_mod", "file:deep/nested/target_mod.py"),
        ("ag1", "branch:agents:0"),
    ):
        _keys(state, actions, "/", *query, "enter")
        visible = _map_visible_nodes(state.active_project, state.map_expanded)
        assert visible[state.map_selected_index]["key"] == expected, (
            query,
            state.message,
        )
        frame = _render(state, 300, 120)
        assert query in frame, (
            f"search selected {expected} (row {state.map_selected_index}) but the "
            "300x120 Map frame never scrolls to show the selected node"
        )


def _c_empty_graph(tmp_path: Path, home: Path) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    register_project(root, data_root=default_data_root())
    actions = _actions(load_overview=load_overview, dashboard_owner=lambda root: None)
    state = _launch([ProjectSeed(name="E", root=root)], actions, default_data_root())
    text = _map_text(state, actions)
    assert "Memories (0)" in text and "Agents (0)" in text, text
    assert "No findings" in text or "E" in text


def _c_no_relations(tmp_path: Path, home: Path) -> None:
    root = tmp_path / "flat"
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.py").write_text("x = 1\n")
    record = register_project(root, data_root=default_data_root())
    _record_run(
        root,
        record.project_id,
        run_id="run-1",
        findings=[
            {
                "finding_id": "f1",
                "path": "src/a.py",
                "line": 1,
                "message": "lonely",
                "severity": "warn",
            }
        ],
        files=["src/a.py"],
    )
    actions = _actions(load_overview=load_overview, dashboard_owner=lambda root: None)
    state = _launch([ProjectSeed(name="F", root=root)], actions, default_data_root())
    text = _map_text(state, actions)
    assert "Memories (0)" in text and "Agents (0)" in text, text
    assert "src/a.py" in text
    assert "->" not in text, "no relation is invented"


def _c_corrupt_graph(tmp_path: Path, home: Path) -> None:
    root = tmp_path / "corrupt"
    root.mkdir()
    record = register_project(root, data_root=default_data_root())
    _record_run(
        root, record.project_id, run_id="run-1", findings=[], raw_text="{not json"
    )
    actions = _actions(load_overview=load_overview, dashboard_owner=lambda root: None)
    state = _launch([ProjectSeed(name="C", root=root)], actions, default_data_root())
    text = _map_text(state, actions)
    assert "Memories: unavailable (" in text and "Agents: unavailable (" in text, text


def _c_unsafe_report(tmp_path: Path, home: Path) -> None:
    """Control characters in a path/message and a path escaping the root:
    no raw escape reaches any rendered section, and the outside file's text
    is never shown."""
    root = tmp_path / "proj"
    root.mkdir()
    (tmp_path / "secret.txt").write_text("OUTSIDE_SECRET\n")
    findings = [
        {
            "path": "evil\x1b[2J.py",
            "line": 1,
            "message": "pwn\x1b]0;x\x07ed",
            "severity": "error",
            "finding_id": "u1",
        },
        {
            "path": "../secret.txt",
            "line": 1,
            "message": "escape attempt",
            "severity": "error",
            "finding_id": "u2",
        },
    ]
    actions = _actions(load_overview=lambda root, **k: _ok_overview("proj"))
    seed = ProjectSeed(
        name="proj", root=root, results=[_result("ruff", "fail", "2", findings)]
    )
    state = _launch([seed], actions, None)
    for keys in (("f3", "1"), ("f3", "3"), ("f3", "3", "enter")):
        _keys(state, actions, "escape", *keys)
        text = _render(state, 200, 60)
        _no_controls(text)
    _keys(state, actions, "escape", "f3", "3", "down", "enter")
    detail = _render(state, 200, 60)
    _no_controls(detail)
    assert "escape attempt" in detail and "OUTSIDE_SECRET" not in detail
    _no_controls(_map_text(state, actions))


def _c_explicit_data_root_map(tmp_path: Path, home: Path) -> None:
    """The project is registered under the explicit data root `rush ui` was
    given (not the default one): its Map still shows the recorded relations,
    never an unavailable snapshot from a different registry."""
    data_root = tmp_path / "explicit-data"
    root, _project_id, _snap = _fixture_project(tmp_path, "project_a.json", data_root)
    actions = _actions(load_overview=load_overview, dashboard_owner=lambda root: None)
    state = _launch([ProjectSeed(name="A", root=root)], actions, data_root)
    text = _map_text(state, actions)
    assert "ag1 -> f1" in text, text


_C_CASES: dict[str, Callable[[Path, Path], None]] = {
    "zero_finding_outcomes": _c_zero_finding_outcomes,
    "partial_suite": _c_partial_suite,
    "result_pages": _c_result_pages,
    "long_report": _c_long_report,
    "duplicate_paths": _c_duplicate_paths,
    "mixed_graph_edges": _c_mixed_graph_edges,
    "collapsed_search": _c_collapsed_search,
    "empty_graph": _c_empty_graph,
    "no_relations": _c_no_relations,
    "corrupt_graph": _c_corrupt_graph,
    "unsafe_report": _c_unsafe_report,
    "explicit_data_root_map": _c_explicit_data_root_map,
}


@pytest.mark.parametrize("case", list(_C_CASES))
def test_t28c_results_and_relationships(case: str, tmp_path: Path, home: Path) -> None:
    _C_CASES[case](tmp_path, home)
