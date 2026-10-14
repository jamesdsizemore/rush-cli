"""T28-C review round 2, Map findings 5-7: selected node evidence, row provenance, shared edges."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console

from rush.dashboard.project_map import build_project_map
from rush.tui import (
    ProjectSeed,
    ProjectState,
    TuiState,
    _dispatch_key,
    _map_nodes,
    _map_visible_nodes,
    _render_map_detail,
)
from tests.test_phase70_tui_usability import (
    _actions,
    _keys,
    _launch,
    _ok_overview,
    _render,
    _result,
)


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway HOME, never the real one (same as the T28 journeys)."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    return home


def _two(root: Path) -> list[Any]:
    (root / "a.py").write_text("alpha_line = 1\n")
    (root / "b.py").write_text("beta_line = 1\n")
    return [
        {
            "path": "a.py",
            "line": 1,
            "message": "alpha msg",
            "severity": "warning",
            "finding_id": "fa",
            "rule": "RA",
            "provenance": "ruff/ruff-0.6",
        },
        {
            "path": "b.py",
            "line": 1,
            "message": "beta msg",
            "severity": "error",
            "finding_id": "fb",
            "rule": "RB",
            "provenance": "ruff/ruff-0.6",
        },
    ]


def test_map_selected_finding_shows_its_own_evidence(
    tmp_path: Path, home: Path
) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    actions = _actions(load_overview=lambda root, **k: _ok_overview("proj"))
    seed = ProjectSeed(
        name="proj", root=root, results=[_result("ruff", "fail", "2", _two(root))]
    )
    state = _launch([seed], actions, None)
    _keys(state, actions, "f3", "2")
    _render(state, 200, 60)
    keys = [
        n["key"] for n in _map_visible_nodes(state.active_project, state.map_expanded)
    ]
    _keys(state, actions, *(["down"] * keys.index("file:b.py")), "right", "down")
    nodes = _map_visible_nodes(state.active_project, state.map_expanded)
    # Navigation precondition: the selected node is b.py's finding. The repro
    # compared label == "beta msg", which contradicts the provenance-in-label
    # requirement below; identity is checked by the unique key and message.
    selected = nodes[state.map_selected_index]
    assert selected["key"] == "file:b.py:finding:0"
    assert selected["finding"]["message"] == "beta msg"
    text = _render(state, 200, 60)
    assert "beta_line" in text or "b.py:1" in text, (
        "Map-selected finding b.py/beta shows no evidence of its own; detail pane:\n"
        + text
    )
    assert "alpha_line" not in text, (
        "detail pane shows the Scans selection (a.py), not the Map node:\n" + text
    )
    # The Map row label now carries "b.py:1", so the pane must show the
    # finding's own file evidence, not only its location.
    assert "beta_line" in text, (
        "detail pane lacks the selected finding's file evidence:\n" + text
    )


def test_map_finding_row_provenance(tmp_path: Path, home: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    actions = _actions(load_overview=lambda root, **k: _ok_overview("proj"))
    seed = ProjectSeed(
        name="proj", root=root, results=[_result("ruff", "fail", "2", _two(root))]
    )
    state = _launch([seed], actions, None)
    _keys(state, actions, "f3", "2")
    _render(state, 200, 60)
    state.map_expanded.add("file:b.py")
    leaf = next(
        n
        for n in _map_visible_nodes(state.active_project, state.map_expanded)
        if n["kind"] == "finding"
    )
    assert any(t in leaf["label"] for t in ("ruff", "error", "RB", "fb", ":1")), (
        f"finding row carries no provenance: {leaf}"
    )


def test_map_edges_match_shared_projection(tmp_path: Path, home: Path) -> None:
    snap = json.loads(Path("tests/fixtures/dashboard/project_a.json").read_text())
    snap["memories"].append({"id": "m9", "cites": ["gone/removed.py"]})
    snap["agents"].append({"id": "ag9", "assigned_to": ["no-such-finding"]})
    graph = build_project_map(snap)
    projected = {
        (e["source"], e["target"])
        for e in graph["edges"]
        if e["relation"] in ("cites", "assigned_to")
    }
    assert not any(src in ("memory:m9", "agent:ag9") for src, _ in projected)
    project = ProjectState(name="A", root=tmp_path)
    project.map_snapshot = snap
    labels = [
        n["label"] for n in _map_nodes(project) if n["kind"] in ("memory", "agent")
    ]
    assert (
        "m9 -> gone/removed.py" not in labels and "ag9 -> no-such-finding" not in labels
    ), f"TUI Map shows relations the shared projection does not record: {labels}"


def test_map_enter_expands_and_memory_detail_shows_projected_record(
    tmp_path: Path, home: Path
) -> None:
    snap = json.loads(Path("tests/fixtures/dashboard/project_a.json").read_text())
    snap["memories"].append({"id": "m9", "cites": ["gone/removed.py"], "note": "N9"})
    project = ProjectState(name="A", root=tmp_path)
    project.map_snapshot = snap
    state = TuiState(projects=[project], active_index=0)
    state.mode = "map"
    state.terminal_size = (200, 60)
    project.map_snapshot_key = None
    keys = [n["key"] for n in _map_visible_nodes(project, state.map_expanded)]
    state.map_selected_index = keys.index("root")
    _dispatch_key(state, "enter", _actions())
    assert state.mode == "map" and "root" in state.map_expanded
    keys = [n["key"] for n in _map_visible_nodes(project, state.map_expanded)]
    state.map_selected_index = keys.index("branch:memories")
    _dispatch_key(state, "enter", _actions())
    nodes = _map_visible_nodes(project, state.map_expanded)
    state.map_selected_index = [n["label"] for n in nodes].index(
        "m9 -> (no recorded relation)"
    )
    console = Console(width=120, record=True)
    console.print(_render_map_detail(state, project))
    text = console.export_text()
    assert "(no recorded relation)" in text and "N9" in text, text
    assert "gone/removed.py" in text  # the raw record stays inspectable
