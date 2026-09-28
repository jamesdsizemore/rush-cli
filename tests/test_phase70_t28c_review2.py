"""T28-C review round 2, Scans findings 3, 4, 8, 9 (plan line 414).

Scans shows every tool/engine/version, actual targets/coverage, per-step
status and execution time independently of finding count; filters by
severity, tool/engine, path and status with a shown/total count; and a
current operation failure surfaces even with no findings.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from test_phase70_tui_usability import (
    _actions,
    _keys,
    _launch,
    _ok_overview,
    _render,
    _result,
    home,
)

from rush.tui import ProjectSeed, ToolResult

__all__ = ["home"]


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


def test_filter_by_severity(tmp_path: Path, home: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    actions = _actions(load_overview=lambda root, **k: _ok_overview("proj"))
    seed = ProjectSeed(
        name="proj", root=root, results=[_result("ruff", "fail", "2", _two(root))]
    )
    state = _launch([seed], actions, None)
    _keys(state, actions, "f3", "3", "/", *"error", "enter")
    text = _render(state, 200, 50)
    assert "beta msg" in text, "severity=error filter hides the error finding:\n" + text


def test_filter_shows_shown_over_total(tmp_path: Path, home: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    actions = _actions(load_overview=lambda root, **k: _ok_overview("proj"))
    seed = ProjectSeed(
        name="proj", root=root, results=[_result("ruff", "fail", "2", _two(root))]
    )
    state = _launch([seed], actions, None)
    _keys(state, actions, "f3", "3", "/", *"b.py", "enter")
    text = _render(state, 200, 50)
    title = [l for l in text.splitlines() if "Findings (" in l]
    assert re.search(r"1\s*(/|of)\s*2", " ".join(title)), (
        f"no shown/total count: {title}"
    )


def test_engine_version_time_for_result_with_findings(
    tmp_path: Path, home: Path
) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    actions = _actions(load_overview=lambda root, **k: _ok_overview("proj"))
    res = ToolResult(
        tool="ruff",
        engine="ruff",
        engine_version="0.6.9",
        status="fail",
        duration_ms=4321,
        summary="2 findings",
        findings=_two(root),
    )
    state = _launch([ProjectSeed(name="proj", root=root, results=[res])], actions, None)
    _keys(state, actions, "f3", "3")
    text = _render(state, 200, 50)
    missing = [n for n in ("0.6.9", "4321") if n not in text]
    assert not missing, f"Scans hides {missing} for a tool that has findings:\n{text}"


def test_scans_surfaces_current_operation_failure_without_findings(
    tmp_path: Path, home: Path
) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    actions = _actions(load_overview=lambda root, **k: _ok_overview("proj"))
    seed = ProjectSeed(name="proj", root=root, results=[_result("ruff", "ok", "clean")])
    state = _launch([seed], actions, None)
    _keys(state, actions, "f3", "3")
    project = state.active_project
    project.status = "error"
    project.last_message = "rescan error: BOOM-OPFAIL"
    text = _render(state, 200, 50)
    assert "BOOM-OPFAIL" in text, "Scans hides the current operation failure:\n" + text


def test_filter_field_prefixes_and_escape_clears(tmp_path: Path, home: Path) -> None:
    """`severity:`, `status:`, `tool:`, `engine:` and `path:` narrow to that
    field only; Escape clears the filter and restores every row."""
    root = tmp_path / "proj"
    root.mkdir()
    actions = _actions(load_overview=lambda root, **k: _ok_overview("proj"))
    ruff = ToolResult(
        tool="ruff",
        engine="ruff",
        engine_version="0.6.9",
        status="fail",
        duration_ms=5,
        summary="2",
        findings=_two(root),
    )
    gamma: list[Any] = [
        {
            "path": "c.py",
            "line": 2,
            "message": "gamma msg",
            "severity": "info",
            "finding_id": "fc",
        }
    ]
    bandit = ToolResult(
        tool="bandit",
        engine="bandit",
        engine_version="1.7",
        status="warn",
        duration_ms=5,
        summary="1",
        findings=gamma,
    )
    state = _launch(
        [ProjectSeed(name="proj", root=root, results=[ruff, bandit])], actions, None
    )
    project = state.active_project
    expected = {
        "severity:error": ["beta msg"],
        "status:warn": ["gamma msg"],
        "tool:ruff": ["alpha msg", "beta msg"],
        "engine:bandit": ["gamma msg"],
        "path:b.py": ["beta msg"],
        "severity:msg": [],
    }
    for needle, messages in expected.items():
        project.filter_text = needle
        assert [r["message"] for r in project.visible_findings()] == messages, needle
    project.filter_text = ""
    _keys(state, actions, "f3", "3", "/", *"severity:error", "enter")
    text = _render(state, 200, 50)
    assert "Findings (1 of 3)" in text and "alpha msg" not in text, text
    _keys(state, actions, "/", "escape")
    assert project.filter_text == ""
    text = _render(state, 200, 50)
    assert all(m in text for m in ("alpha msg", "beta msg", "gamma msg")), text


def test_outcome_detail_shows_recorded_targets(tmp_path: Path, home: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    actions = _actions(load_overview=lambda root, **k: _ok_overview("proj"))
    scoped = ToolResult(
        tool="ruff",
        engine="ruff",
        engine_version="0.6.9",
        status="ok",
        duration_ms=7,
        summary="clean",
        findings=[],
        metadata={
            "scope": {
                "version": 1,
                "kind": "files",
                "requested_targets": ["src/pkg/mod_one.py", "src/pkg/mod_two.py"],
                "consumed_file_count": 1,
                "coverage": "partial",
                "reason": "one_target_ignored",
            }
        },
    )
    state = _launch(
        [ProjectSeed(name="proj", root=root, results=[scoped])], actions, None
    )
    _keys(state, actions, "f3", "3")
    text = _render(state, 200, 50)
    for part in (
        "src/pkg/mod_one.py",
        "src/pkg/mod_two.py",
        "coverage: partial",
        "one_target_ignored",
    ):
        assert part in text, f"outcome detail hides recorded {part!r}:\n{text}"
    assert "no targets recorded" not in text, text

    unscoped = ToolResult(
        tool="mypy",
        engine="mypy",
        engine_version="1.11",
        status="ok",
        duration_ms=3,
        summary="clean",
        findings=[],
    )
    state = _launch(
        [ProjectSeed(name="proj", root=root, results=[unscoped])], actions, None
    )
    _keys(state, actions, "f3", "3")
    text = _render(state, 200, 50)
    assert "(project root; no targets recorded)" in text, text
