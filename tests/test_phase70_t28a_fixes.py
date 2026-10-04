"""Phase 70 T28-A review fixes (302078e review, majors 1-9 and minors 10).

Every case drives the real TUI/CLI/ProjectTool entry points and fails on the
reviewed commit without the fix."""

from __future__ import annotations

import io
import json
import os
import subprocess
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from click.testing import CliRunner
from rich.console import Console

from rush import tui
from rush.permissions import ExecutionPermissions
from rush.tui import (
    ProjectSeed,
    ProjectState,
    ScanActions,
    SectionView,
    TuiState,
    _apply_registration,
    _dispatch_key,
    _project_grant_worker,
    _pump,
    load_overview,
    project_key,
    render_app,
    run_interactive_tui,
)
from rush.workflows.projects import register_project, resolve_project

HOSTILE = "p\x1b]0;X\x07q"


def _actions(**extra: Any) -> ScanActions:
    return ScanActions(
        plan_scan=lambda *a, **k: SimpleNamespace(candidates=[]),
        execute_scan=lambda *a, **k: SimpleNamespace(aggregate={}),
        cancel_scan_run=lambda *a, **k: {},
        rescan_project_run=lambda *a, **k: {},
        build_handoff=lambda *a, **k: None,
        dispatch_handoff=lambda *a, **k: None,
        load_scan_events=lambda *a, **k: {"events": [], "run_state": None},
        list_agents=list,
        **extra,
    )


def _render(state: TuiState, width: int = 120, height: int = 40) -> str:
    state.terminal_size = (width, height)
    console = Console(record=True, width=width, height=height, file=io.StringIO())
    console.print(render_app(state))
    return console.export_text()


def _assert_no_controls(text: str) -> None:
    assert "\x1b" not in text and "\x07" not in text, repr(text[:400])


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


def _pump_until(state: TuiState, actions: ScanActions, done: Any) -> None:
    deadline = time.monotonic() + 10
    while not done():
        assert time.monotonic() < deadline, "background load never applied"
        _pump(state, actions)
        time.sleep(0.01)


# -- 1: every dynamic value escaped -----------------------------------------


def test_grant_review_escapes_hostile_project_values(tmp_path: Path) -> None:
    root = tmp_path / HOSTILE
    root.mkdir()
    project = ProjectState(
        name=HOSTILE, root=root, registration={"state": "none", "reason": None}
    )
    state = TuiState(projects=[project])
    _dispatch_key(state, "A", _actions())
    assert state.mode == "grant_review"
    _assert_no_controls(_render(state))


def test_memory_panel_escapes_hostile_rows() -> None:
    import base64

    state = TuiState(projects=[ProjectState(name="m", root=Path("/tmp/t28a-m"))])
    state.mode = "memory"
    state.memory_items = [
        {"id": HOSTILE, "trust_tier": HOSTILE, "source": HOSTILE, "stale": False}
    ]
    state.memory_message = HOSTILE
    _assert_no_controls(_render(state))
    content = HOSTILE + " [bold]literal[/bold]"
    page = {
        "offset": 0,
        "next_offset": len(content.encode()),
        "complete": True,
        "content": content,
    }
    state.memory_expanded = {
        "id": HOSTILE,
        "version": 1,
        **page,
        "content_base64": base64.b64encode(content.encode()).decode(),
        "content_bytes_base64": base64.b64encode(content.encode()).decode(),
        "project_key": project_key(state.active_project),
        "pages": [page],
        "page_index": 0,
        "scroll": 0,
        "relationships": [
            {
                "id": HOSTILE,
                "artifact_version": 1,
                "kind": HOSTILE,
                "direction": HOSTILE,
            }
        ],
        "relationships_complete": True,
        "receipts": [
            {"id": HOSTILE, "artifact_version": 1, "kind": HOSTILE, "origin": HOSTILE}
        ],
        "receipts_bounded": False,
    }
    rendered = _render(state)
    _assert_no_controls(rendered)
    assert "[bold]literal[/bold]" in rendered
    assert "Relationships:" in rendered
    assert "Receipts:" in rendered


def test_git_panel_escapes_hostile_rows() -> None:
    state = TuiState(projects=[ProjectState(name="g", root=Path("/tmp/t28a-g"))])
    state.mode = "git"
    commit = {"hash": HOSTILE, "author": HOSTILE, "date": HOSTILE, "subject": HOSTILE}
    state.git_data = {
        "git": {
            "has_git": True,
            "head": HOSTILE,
            "dirty": True,
            "history": [commit],
            "dirty_files": [{"status": HOSTILE, "path": HOSTILE}],
        },
        "artifacts": {"scan_outputs": [{"category": HOSTILE}]},
    }
    state.git_message = HOSTILE
    _assert_no_controls(_render(state))


# -- 2: `rush ui --json` / non-TTY never run checks --------------------------


def _ui_invoke(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, args: list[str]
) -> tuple[Any, list[Any]]:
    import rush.cli as cli_module
    import rush.workflows.suites as suites_module
    from rush.cli import cli

    calls: list[Any] = []

    def record_suite(**kw: Any) -> dict[str, Any]:
        calls.append(kw)
        return {}

    monkeypatch.setattr(suites_module, "run_workflow_suite", record_suite)
    monkeypatch.setattr(cli_module, "_interactive_terminal", lambda: False)
    result = CliRunner().invoke(cli, ["ui", *args])
    return result, calls


def test_ui_json_prints_status_never_runs_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path
) -> None:
    proj = tmp_path / "proj"
    proj.mkdir()
    result, calls = _ui_invoke(monkeypatch, tmp_path, ["--json", str(proj)])
    assert result.exit_code == 0, result.output
    assert calls == []
    payload = json.loads(result.output)
    assert [set(item) for item in payload] == [{"project", "path", "status"}]
    assert payload[0]["project"] == "proj"
    assert payload[0]["path"] == str(proj.resolve())
    assert payload[0]["status"]["data"]["project"]["registration"] == "unregistered"


def test_ui_plain_non_tty_prints_next_steps_never_runs_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path
) -> None:
    proj = tmp_path / "proj"
    proj.mkdir()
    result, calls = _ui_invoke(monkeypatch, tmp_path, [str(proj)])
    assert result.exit_code == 0, result.output
    assert calls == []
    lines = [line.strip() for line in result.output.splitlines()]
    assert lines[0].startswith("proj: ")
    path = str(proj.resolve())
    assert f"Next: rush status {path} --json" in lines
    assert f"rush check {path}" in lines


# -- 3: the keymap footer is visible ----------------------------------------


@pytest.mark.parametrize("size", [(120, 40), (80, 24), (60, 20)])
def test_keymap_footer_visible(size: tuple[int, int]) -> None:
    state = TuiState(projects=[ProjectState(name="f", root=Path("/tmp/t28a-f"))])
    state.message = "status line"
    text = _render(state, *size)
    assert "?:Help" in text
    assert "status line" in text


def test_action_focus_remains_visible_when_navigation_clips(tmp_path: Path) -> None:
    state = TuiState(
        projects=[
            ProjectState(name="alpha", root=tmp_path / "alpha"),
            ProjectState(name="beta", root=tmp_path / "beta"),
        ],
        active_index=1,
    )
    for size in ((60, 20), (80, 24), (120, 40)):
        state.focus = "list"
        state.action_index = 0
        _dispatch_key(state, "tab", _actions())
        assert state.focus == "detail"
        assert ">Refresh" not in _render(state, *size)
        _dispatch_key(state, "tab", _actions())
        assert state.focus == "actions"
        assert ">Refresh" in _render(state, *size)
        _dispatch_key(state, "down", _actions())
        assert ">Check" in _render(state, *size)
        _dispatch_key(state, "down", _actions())
        assert ">Scan" in _render(state, *size)
        state.action_index = 6
        text = _render(state, *size)
        assert ">Cancel run" in text
        assert "f5:Refresh" in text


# -- 4: section loads survive a scan start -----------------------------------


def test_overview_load_applied_after_scan_start(tmp_path: Path) -> None:
    release = threading.Event()

    def slow_overview(root: Path, **kwargs: Any) -> dict[str, Any]:
        release.wait(5)
        return {"registration": {"state": "none", "reason": "x"}, "status": {}}

    actions = _actions(load_overview=slow_overview)
    project = ProjectState(name="s", root=tmp_path)
    state = TuiState(projects=[project])
    state.load_requests.add((project_key(project), "overview"))
    _pump(state, actions)
    assert "overview" in project.pending
    project.run_id = "run-started-by-scan"  # what `_start_scan_thread` does
    release.set()
    key = (project_key(project), "overview")
    _pump_until(state, actions, lambda: state.views[key].state == "populated")
    assert project.registration is not None
    assert project.registration["state"] == "none"


def test_invalidate_drops_inflight_load(tmp_path: Path) -> None:
    release = threading.Event()

    def slow_overview(root: Path, **kwargs: Any) -> dict[str, Any]:
        release.wait(5)
        return {"registration": {"state": "none", "reason": "x"}}

    actions = _actions(load_overview=slow_overview)
    project = ProjectState(name="i", root=tmp_path)
    state = TuiState(projects=[project])
    state.load_requests.add((project_key(project), "overview"))
    _pump(state, actions)
    project.invalidate()
    release.set()
    time.sleep(0.2)
    _pump(state, actions)
    assert state.views[(project_key(project), "overview")].state == "loading"
    assert project.registration is None


def test_f5_replays_one_refresh_after_loading(tmp_path: Path) -> None:
    release = threading.Event()
    captured = threading.Event()
    loaded: list[str] = []
    root = tmp_path / "project"
    root.mkdir()

    def slow_overview(root: Path, **kwargs: Any) -> dict[str, Any]:
        result = load_overview(root, **kwargs)
        loaded.append(result["status"]["config"]["state"])
        if len(loaded) == 1:
            captured.set()
            release.wait(5)
        return result

    actions = _actions(load_overview=slow_overview)
    project = ProjectState(name="f5", root=root)
    state = TuiState(projects=[project], data_root=tmp_path / "data")
    key = (project_key(project), "overview")
    state.load_requests.add(key)
    _pump(state, actions)
    try:
        assert captured.wait(5)
        assert loaded == ["missing"]
        (root / "rush.toml").write_text("[tools\n")
        for _ in range(5):
            _dispatch_key(state, "f5", actions)
            _pump(state, actions)
        assert loaded == ["missing"]  # one loader at a time
        assert state.load_requests == {key}  # one refresh kept for its completion
    finally:
        release.set()

    post = state.result_queue.get(timeout=5)
    state.result_queue.put(post)
    _pump(state, actions)
    post = state.result_queue.get(timeout=5)
    state.result_queue.put(post)
    _pump(state, actions)
    assert loaded == ["missing", "invalid"]
    assert state.views[key].data["status"]["config"]["state"] == "invalid"
    assert "rush.toml: invalid" in _render(state, 80, 24)

    (root / "rush.toml").write_text("[tools]\n")
    _dispatch_key(state, "f5", actions)
    _pump(state, actions)
    post = state.result_queue.get(timeout=5)
    state.result_queue.put(post)
    _pump(state, actions)
    assert loaded == ["missing", "invalid", "valid"]
    assert state.views[key].data["status"]["config"]["state"] == "valid"
    assert "rush.toml: valid" in _render(state, 80, 24)


# -- 5: reduced motion redraws after background results ----------------------


def test_reduced_motion_redraws_after_background_load(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("RUSH_REDUCED_MOTION", "1")
    renders: list[Any] = []

    class _FakeLive:
        def __init__(self, renderable: object, **kwargs: object) -> None:
            pass

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

        def update(self, renderable: object, refresh: bool = False) -> None:
            renders.append(renderable)

    monkeypatch.setattr("rich.live.Live", _FakeLive)

    class _IdleReader:
        def read_key(self, timeout: float) -> str | None:
            time.sleep(0.01)
            return None

        def get_size(self) -> tuple[int, int]:
            return (120, 40)

    actions = _actions(
        load_overview=lambda root, **kw: {
            "registration": {"state": "none", "reason": "no project registered"}
        }
    )
    run_interactive_tui(
        [ProjectSeed(name="rm", root=tmp_path)],
        key_reader=_IdleReader(),
        actions=actions,
        use_live=True,
        max_ticks=100,
    )
    assert renders, "reduced motion never redrew after the Overview load"
    console = Console(record=True, width=120, height=40, file=io.StringIO())
    console.print(renders[-1])
    assert "No project registered for this folder." in console.export_text()


# -- 6: Overview renders StatusTool fields with reasons ----------------------


def test_overview_renders_status_fields_and_unavailable_reasons(
    tmp_path: Path, home: Path
) -> None:
    proj = tmp_path / "proj"
    proj.mkdir()
    data = load_overview(proj, data_root=tmp_path / "data")
    project = ProjectState(name="o", root=proj)
    state = TuiState(projects=[project])
    state.views[(project_key(project), "overview")] = SectionView(
        state="populated", data=data
    )
    project.registration = data["registration"]
    text = _render(state, 120, 60)
    for needle in (
        "rush.toml:",
        "Engines",
        "Activity",
        "Published result",
        "Memory",
        "Runs: unavailable -- project not registered",
        "Coverage: unavailable -- project not registered",
        "Git: unavailable -- no Git repository",
    ):
        assert needle in text, needle
    assert '"has_git"' not in text and "evidence:" not in text


# -- 7: a moved project is offered Relink at launch --------------------------


def test_moved_project_launch_offers_relink_not_add(tmp_path: Path, home: Path) -> None:
    data_root = tmp_path / "data"
    old = tmp_path / "old"
    old.mkdir()
    record = register_project(old, data_root=data_root)
    new = tmp_path / "new"
    old.rename(new)
    data = load_overview(new, data_root=data_root)
    registration = data["registration"]
    assert registration["state"] == "moved"
    assert registration["project_id"] == record.project_id
    project = ProjectState(name="new", root=new, registration=registration)
    state = TuiState(projects=[project])
    text = _render(state)
    assert "Relink" in text
    assert "[A] Add this folder" not in text
    ok, _ = tui._add_enabled(state)
    assert not ok


# -- 8 / 9: the real launch read is zero-write, even in a hostile repo -------


def _tree(base: Path) -> dict[str, float]:
    if not base.exists():
        return {}
    return {
        str(p.relative_to(base)): p.stat().st_mtime_ns
        for p in base.rglob("*")
        if p.is_file()
    }


def test_launch_read_is_zero_write_and_ignores_fsmonitor(
    tmp_path: Path, home: Path
) -> None:
    proj = tmp_path / "proj"
    proj.mkdir()
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run([*git, "init", "-q"], cwd=proj, check=True)
    (proj / "a.py").write_text("x = 1\n")
    subprocess.run([*git, "add", "a.py"], cwd=proj, check=True)
    subprocess.run([*git, "commit", "-qm", "c"], cwd=proj, check=True)
    (proj / "a.py").write_text("x = 2\n")
    marker = tmp_path / "fsmonitor-ran"
    hook = tmp_path / "hook.sh"
    hook.write_text(f"#!/bin/sh\ntouch {marker}\n")
    hook.chmod(0o755)
    subprocess.run(["git", "config", "core.fsmonitor", str(hook)], cwd=proj, check=True)
    # Make the index racy-stale so an optional-lock refresh would rewrite it.
    os.utime(proj / ".git" / "index", (1, 1))
    data_root = tmp_path / "data"
    before = _tree(proj)
    data = load_overview(proj, data_root=data_root)
    assert data["evidence"]["git"]["dirty"] is True
    assert not marker.exists(), "git ran the repository's core.fsmonitor hook"
    assert _tree(proj) == before
    assert not data_root.exists()
    assert _tree(home) == {}


# -- 9: `_apply_registration` re-keys views and re-requests loads ------------


def test_apply_registration_rekeys_views_and_rerequests() -> None:
    project = ProjectState(name="r", root=Path("/tmp/t28a-rekey"))
    state = TuiState(projects=[project])
    old_key = project_key(project)
    state.views[(old_key, "overview")] = SectionView(state="loading")
    project.begin_request("tokens")
    _apply_registration(state, project, {"state": "ok", "project_id": "pid-1"})
    assert project.project_id == "pid-1"
    assert ("pid-1", "overview") in state.views
    assert (old_key, "overview") not in state.views
    assert ("pid-1", "tokens") in state.load_requests
    assert project.pending == {}


def test_registration_from_status_maps_each_state() -> None:
    f = tui._registration_from_status
    assert f({"registry": {"state": "corrupt", "error": "bad"}})["state"] == "corrupt"
    assert f({"project": {"registration": "ambiguous"}})["state"] == "ambiguous"
    assert f({"project": {"registration": "unregistered"}})["state"] == "none"
    moved = f(
        {
            "project": {
                "registration": "registered",
                "project_id": "p",
                "root_exists": False,
            }
        }
    )
    assert moved["state"] == "moved" and moved["project_id"] == "p"
    assert (
        f({"project": {"registration": "registered", "project_id": "p"}})["state"]
        == "ok"
    )


# -- 9 / 10: add/create/relink grant path and root readback ------------------


def test_add_create_relink_grants_read_back_roots(tmp_path: Path, home: Path) -> None:
    data_root = tmp_path / "data"
    proj = tmp_path / "proj"
    proj.mkdir()
    added = _project_grant_worker({"kind": "project_add", "root": str(proj)}, data_root)
    assert Path(added["root"]) == proj.resolve()
    created = _project_grant_worker(
        {
            "kind": "project_create",
            "parent": str(tmp_path),
            "name": "made",
            "init_git": False,
        },
        data_root,
    )
    assert Path(created["root"]) == (tmp_path / "made").resolve()
    moved = tmp_path / "moved"
    proj.rename(moved)
    relinked = _project_grant_worker(
        {
            "kind": "project_relink",
            "new_root": str(moved),
            "project_id": added["project_id"],
            "expected_revision": added["revision"],
        },
        data_root,
    )
    assert Path(relinked["root"]) == moved.resolve()
    assert resolve_project(added["project_id"], data_root=data_root)["root"] == str(
        moved.resolve()
    )


def test_grant_readback_rejects_a_different_root(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "data"
    proj = tmp_path / "proj"
    proj.mkdir()
    real = resolve_project
    monkeypatch.setattr(
        "rush.workflows.projects.resolve_project",
        lambda *a, **k: {**real(*a, **k), "root": str(tmp_path / "elsewhere")},
    )
    with pytest.raises(RuntimeError, match="readback"):
        _project_grant_worker({"kind": "project_add", "root": str(proj)}, data_root)


# -- 10: minors ---------------------------------------------------------------


def test_launch_grants_listed_in_every_review() -> None:
    project = ProjectState(name="g", root=Path("/tmp/t28a-grants"), run_id="r1")
    state = TuiState(
        projects=[project],
        launch_permissions=ExecutionPermissions(slow=True, network=True),
    )
    _dispatch_key(state, "s", _actions())
    assert state.pending_grant is not None
    assert state.pending_grant["pre-granted at launch"] == "network, slow"


def test_add_not_claimed_registered_while_loading() -> None:
    state = TuiState(projects=[ProjectState(name="l", root=Path("/tmp/t28a-l"))])
    ok, reason = tui._add_enabled(state)
    assert not ok and "loading" in reason


def test_project_tool_select_honours_data_root(tmp_path: Path, home: Path) -> None:
    from rush.tools.project import ProjectTool

    data_root = tmp_path / "data"
    proj = tmp_path / "proj"
    proj.mkdir()
    record = register_project(proj, data_root=data_root)
    result = ProjectTool().run(
        proj,
        action="select",
        project_id=record.project_id,
        session_id="s1",
        permissions=ExecutionPermissions(cache_write=True, artifact_write=True),
        data_root=data_root,
    )
    assert result["status"] == "ok", result
    assert _tree(home) == {}


def test_empty_projects_active_index_none() -> None:
    state = TuiState(projects=[])
    assert state.active_index is None
    assert "No project open" in _render(state)


def test_f2_overlay_offers_switch_add_create_later(tmp_path: Path) -> None:
    project = ProjectState(
        name="f2", root=tmp_path, registration={"state": "none", "reason": None}
    )
    state = TuiState(projects=[project])
    actions = _actions()
    _dispatch_key(state, "f2", actions)
    text = _render(state)
    for label in ("f2", "Add this folder", "Create a new project", "Choose later"):
        assert label in text, label
    _dispatch_key(state, "down", actions)  # Add
    _dispatch_key(state, "down", actions)  # Create
    _dispatch_key(state, "enter", actions)
    assert state.overlay == "form"
    assert state.form is not None and state.form["kind"] == "project_create"


def test_right_l_expand_left_h_collapse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tui,
        "_map_visible_nodes",
        lambda project, expanded: [{"key": "k", "children": [1]}],
    )
    state = TuiState(projects=[ProjectState(name="m", root=Path("/tmp/t28a-map"))])
    state.mode = "map"
    actions = _actions()
    for expand, collapse in (("right", "left"), ("l", "h")):
        _dispatch_key(state, expand, actions)
        assert "k" in state.map_expanded
        _dispatch_key(state, collapse, actions)
        assert "k" not in state.map_expanded


def test_resize_guidance_below_60x20_keeps_state() -> None:
    project = ProjectState(name="rz", root=Path("/tmp/t28a-rz"))
    state = TuiState(projects=[project])
    state.section = project.section = "tokens"
    text = _render(state, 50, 15)
    assert "60x20" in text
    state.terminal_size = (50, 15)
    actions = _actions()
    _dispatch_key(state, "j", actions)  # ignored while too small
    assert state.section == "tokens"
    _dispatch_key(state, "f2", actions)
    # While too small, resize_guidance covers the opened projects overlay,
    # which is recorded to be restored unchanged.
    assert "60x20" in _render(state, 50, 15)
    assert state.section == "tokens"
    assert state.overlay_under_resize == "projects"
    selection = (
        state.active_index,
        state.project_selector_index,
        state.nav_index,
        project.selected_index,
    )
    _render(state, 120, 40)
    assert state.overlay == "projects"
    assert (
        state.active_index,
        state.project_selector_index,
        state.nav_index,
        project.selected_index,
    ) == selection
    _dispatch_key(state, "escape", actions)
    assert state.overlay is None and state.section == "tokens"
    _dispatch_key(state, "q", actions)
    assert state.should_quit or state.mode == "quit_confirm"


class _SizedReader:
    """One (key, size) pair per tick; the launch read gets `launch_size`."""

    def __init__(
        self,
        launch_size: tuple[int, int],
        script: list[tuple[str | None, tuple[int, int]]],
    ) -> None:
        self._sizes = iter([launch_size] + [size for _key, size in script])
        self._keys = iter([key for key, _size in script])
        self._last = launch_size

    def read_key(self, timeout: float) -> str | None:
        return next(self._keys, None)

    def get_size(self) -> tuple[int, int]:
        self._last = next(self._sizes, self._last)
        return self._last


def test_resize_below_minimum_and_back_keeps_map_selection_and_expanded(
    tmp_path: Path,
) -> None:
    """The run loop's resize path: expand at 120x40, shrink to 60x18 (keys
    other than q/c/F2/Escape wait), grow back; selection and expanded nodes
    are untouched throughout, and keys act again at full size."""
    from rush.tools.base import Finding, ToolResult

    findings = [
        Finding(path=name, line=1, column=1, rule="R", message="m", severity="warn")
        for name in ("a.py", "b.py")
    ]
    seed = ProjectSeed(
        name="rz",
        root=tmp_path,
        results=[
            ToolResult(
                tool="lint",
                status="fail",
                duration_ms=1,
                summary="x",
                findings=findings,
            )
        ],
    )
    big, small = (120, 40), (60, 18)
    script: list[tuple[str | None, tuple[int, int]]] = [
        ("f3", big),
        ("2", big),
        ("down", big),
        ("l", big),  # expands file:a.py
        ("h", small),  # waits: below 60x20
        ("down", small),  # waits: below 60x20
        (None, big),
        ("down", big),  # acts again at full size
        ("q", big),
    ]
    state = run_interactive_tui(
        [seed],
        key_reader=_SizedReader(big, script),
        actions=_actions(),
        use_live=False,
        max_ticks=50,
    )
    assert state.mode == "map"
    assert "file:a.py" in state.map_expanded
    assert state.map_selected_index == 2
    assert state.terminal_size == big


def _hostile_repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A repo whose own .git/config names a clean filter and a gpg program
    that each touch a marker, with a racily-clean tracked file and a commit
    carrying a gpgsig header (so signature display would run gpg.program)."""
    repo = tmp_path / "hostile"
    repo.mkdir()
    clean_marker = tmp_path / "clean-ran"
    gpg_marker = tmp_path / "gpg-ran"
    clean = tmp_path / "clean.sh"
    clean.write_text(f'#!/bin/sh\ntouch "{clean_marker}"\ncat\n')
    clean.chmod(0o755)
    gpg = tmp_path / "gpg.sh"
    gpg.write_text(f'#!/bin/sh\ntouch "{gpg_marker}"\nexit 1\n')
    gpg.chmod(0o755)

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=repo, check=True, capture_output=True, text=True
        ).stdout.strip()

    git("init", "-q")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (repo / ".gitattributes").write_text("* filter=evil\n")
    (repo / "a.txt").write_text("one\n")
    git("add", "-A")
    git("commit", "-qm", "one")
    tree = git("rev-parse", "HEAD^{tree}")
    parent = git("rev-parse", "HEAD")
    signed = (
        f"tree {tree}\nparent {parent}\n"
        "author t <t@example.com> 1700000000 +0000\n"
        "committer t <t@example.com> 1700000000 +0000\n"
        "gpgsig -----BEGIN PGP SIGNATURE-----\n \n"
        " iQEzBAABCAAdFiEE\n -----END PGP SIGNATURE-----\n\nsigned\n"
    )
    commit = subprocess.run(
        ["git", "hash-object", "-t", "commit", "-w", "--stdin"],
        cwd=repo,
        input=signed,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    git("update-ref", "HEAD", commit)
    git("config", "filter.evil.clean", str(clean))
    git("config", "gpg.program", str(gpg))
    git("config", "log.showSignature", "true")
    time.sleep(1.1)
    (repo / "a.txt").write_text("two\n")
    return repo, clean_marker, gpg_marker


def test_overview_git_read_never_runs_repo_configured_filters_or_gpg(
    tmp_path: Path,
) -> None:
    """Review round 3 #1: `git status` must not run a clean filter and
    `git log`/`show` must not run gpg.program from the repo's own config."""
    from rush.workflows import projects

    repo, clean_marker, gpg_marker = _hostile_repo(tmp_path)
    summary = projects._git_summary(repo)
    head = summary["head"]
    projects._git_show_path_digest(repo, head, "a.txt")
    assert summary["has_git"] is True
    assert summary["dirty"] is True
    assert not clean_marker.exists(), "git ran the repository's clean filter"
    assert not gpg_marker.exists(), "git ran the repository's gpg.program"


def test_git_read_keeps_the_users_global_filters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only filter drivers from the repository's own config are neutralized;
    a driver from the user's global config (e.g. git-lfs) stays active."""
    from rush.workflows import projects

    home = tmp_path / "home"
    home.mkdir()
    (home / ".gitconfig").write_text('[filter "lfs"]\n\tclean = git-lfs clean -- %f\n')
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(home / ".gitconfig"))
    repo, _, _ = _hostile_repo(tmp_path)
    argv = projects._git_read(repo)
    assert "filter.evil.clean=" in argv
    assert not any(part.startswith("filter.lfs.") for part in argv)


def test_ui_plain_output_escapes_names_and_quotes_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path
) -> None:
    """Review round 3 #5: the non-TTY listing prints a project name taken from
    the filesystem, so terminal controls are escaped, and the suggested
    commands shell-quote the path so a path with spaces stays copyable."""
    proj = tmp_path / "my proj\x1b[31m"
    proj.mkdir()
    result, calls = _ui_invoke(monkeypatch, tmp_path, [str(proj)])
    assert result.exit_code == 0, result.output
    assert calls == []
    assert "\x1b" not in result.output
    assert "Next: rush status '" in result.output
    assert "      rush check '" in result.output


def test_ui_json_help_names_read_only_status() -> None:
    """Review round 3 #6: `--json` reports `rush status`, not a check suite."""
    from rush.cli import cli

    result = CliRunner().invoke(cli, ["ui", "--help"])
    assert result.exit_code == 0, result.output
    assert "read-only status" in result.output
    assert "check-suite result" not in result.output


# -- review round 3, fixed directly by the orchestrator ----------------------


def test_footer_keeps_help_visible_when_the_status_line_wraps(tmp_path: Path) -> None:
    """R3 major 2: the footer height counts the wrapped status line, so a long
    message or the quit-confirm choices never push `?:Help` out of view."""
    for width, height in ((60, 20), (80, 24), (120, 40)):
        state = TuiState(projects=[ProjectState(name="p", root=tmp_path)])
        state.message = "m" * 70 + " " + "word " * 12
        assert "?:Help" in _render(state, width, height), (width, height)
        state = TuiState(projects=[ProjectState(name="p", root=tmp_path)])
        state.active_project.status = "scanning"
        _dispatch_key(state, "q", _actions())
        assert state.mode == "quit_confirm"
        text = _render(state, width, height)
        assert "?:Help" in text, (width, height, text)
        assert "[r]" in text, (width, height, text)


def test_reduced_motion_draws_the_finished_scan_and_reloads_its_views(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """R3 major 3 + minor: when running work finishes, reduced motion draws
    the finished state without a key press, and Overview, Tokens and Scans
    are reloaded for that project."""
    import rush.tui as tui_module

    monkeypatch.setenv("RUSH_REDUCED_MOTION", "1")
    drawn: list[str] = []
    submitted: list[str] = []
    ticks = {"n": 0}
    seen: dict[str, TuiState] = {}

    class _FakeLive:
        def __init__(self, renderable: object, **kwargs: object) -> None:
            pass

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

        def update(self, renderable: object, refresh: bool = False) -> None:
            drawn.append(seen["state"].active_project.status)

    def poll(state: TuiState, actions: ScanActions) -> None:
        seen["state"] = state
        ticks["n"] += 1
        state.active_project.status = "scanning" if ticks["n"] < 4 else "done"

    monkeypatch.setattr("rich.live.Live", _FakeLive)
    monkeypatch.setattr(tui_module, "_poll_running_scans", poll)
    monkeypatch.setattr(
        tui_module,
        "_submit",
        lambda state, project, section, actions: submitted.append(section),
    )

    class _IdleReader:
        def read_key(self, timeout: float) -> str | None:
            return None

        def get_size(self) -> tuple[int, int]:
            return (120, 40)

    run_interactive_tui(
        [ProjectSeed(name="rm", root=tmp_path)],
        key_reader=_IdleReader(),
        actions=_actions(),
        use_live=True,
        max_ticks=8,
    )
    assert "done" in drawn, drawn
    # Launch loads only the Overview; finishing reloads all three.
    assert submitted[0] == "overview", submitted
    assert {"overview", "tokens", "scans"} <= set(submitted[1:]), submitted


def test_below_minimum_size_quit_and_projects_are_visible_and_answerable(
    tmp_path: Path,
) -> None:
    """R3 minor: under 60x20 the guidance overlay still shows what q and F2
    opened and accepts that choice's keys; all state is kept."""
    state = TuiState(
        projects=[
            ProjectState(name="alpha", root=tmp_path / "a"),
            ProjectState(name="beta", root=tmp_path / "b"),
        ]
    )
    state.terminal_size = (50, 15)
    state.active_project.status = "scanning"
    _dispatch_key(state, "q", _actions())
    text = _render(state, 50, 15)
    assert "too small" in text and "[r]" in text, text
    _dispatch_key(state, "r", _actions())
    assert state.mode == "list"
    assert "quit cancelled" in _render(state, 50, 15)

    _dispatch_key(state, "f2", _actions())
    assert state.mode == "project_selector"
    text = _render(state, 50, 15)
    assert ">alpha" in text and "beta" in text, text
    _dispatch_key(state, "down", _actions())
    assert ">beta" in _render(state, 50, 15)
    _dispatch_key(state, "escape", _actions())
    assert state.mode == "list" and state.active_index == 0


@pytest.mark.parametrize("key", ["n", "escape"])
def test_no_projects_screen_can_decline_a_grant_review(
    tmp_path: Path, key: str
) -> None:
    """R3 minor: with no project open, a pending grant review is declined by
    n or Escape (only y runs it)."""
    ran: list[Any] = []
    state = TuiState(projects=[])
    state.pending_grant = {"kind": "project_create", "target": str(tmp_path)}
    state.mode = "grant_review"
    import rush.tui as tui_module

    original = tui_module._execute_grant
    try:
        tui_module._execute_grant = lambda *a, **k: ran.append(a)  # type: ignore[assignment]
        _dispatch_key(state, key, _actions())
    finally:
        tui_module._execute_grant = original  # type: ignore[assignment]
    assert ran == []
    assert state.pending_grant is None and state.mode == "list"
    assert state.message == "declined"


def test_relink_form_prefills_the_known_new_root(tmp_path: Path, home: Path) -> None:
    """R3 minor: when the Overview found a moved project at this root, the
    Relink form opens with that root filled in."""
    import rush.tui as tui_module

    old = tmp_path / "old"
    old.mkdir()
    data_root = tmp_path / "data"
    record = register_project(old, data_root=data_root)
    new = tmp_path / "new"
    old.rename(new)
    registration = tui_module._moved_registration(new, data_root)
    assert registration is not None and registration["new_root"] == str(new)
    state = TuiState(projects=[ProjectState(name="p", root=new)], data_root=data_root)
    _apply_registration(state, state.active_project, registration)
    tui_module._project_relink_form(state, _actions())
    assert state.form is not None
    assert state.form["values"]["new_root"] == str(new), (record, state.form)
