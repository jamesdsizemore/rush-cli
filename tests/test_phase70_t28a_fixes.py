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
    state = TuiState(projects=[ProjectState(name="m", root=Path("/tmp/t28a-m"))])
    state.mode = "memory"
    state.memory_items = [
        {"id": HOSTILE, "trust_tier": HOSTILE, "source": HOSTILE, "stale": False}
    ]
    state.memory_expanded = {"body": HOSTILE}
    state.memory_message = HOSTILE
    _assert_no_controls(_render(state))


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


def test_f5_does_not_start_a_second_thread_while_loading(tmp_path: Path) -> None:
    release = threading.Event()
    started: list[int] = []

    def slow_overview(root: Path, **kwargs: Any) -> dict[str, Any]:
        started.append(1)
        release.wait(5)
        return {"registration": {"state": "none", "reason": "x"}}

    actions = _actions(load_overview=slow_overview)
    project = ProjectState(name="f5", root=tmp_path)
    state = TuiState(projects=[project])
    state.load_requests.add((project_key(project), "overview"))
    _pump(state, actions)
    for _ in range(5):
        _dispatch_key(state, "f5", actions)
        _pump(state, actions)
    time.sleep(0.1)
    release.set()
    assert len(started) == 1


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
    assert state.overlay == "projects"
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
        ("+", big),  # expands file:a.py
        ("-", small),  # waits: below 60x20
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
