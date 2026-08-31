"""Unit tests for TuiDiffTool (PR50.12)."""

from __future__ import annotations

from pathlib import Path

from rush.tools.tui_diff import TuiDiffTool


def test_tui_diff_no_findings_delta(tmp_path: Path) -> None:
    tool = TuiDiffTool()
    res = tool.run(tmp_path, base_findings=[], current_findings=[])

    assert res["tool"] == "tui-diff"
    assert res["status"] == "ok"
    assert res["metrics"] is not None
    assert res["metrics"]["new_findings_count"] == 0
    assert res["metrics"]["resolved_findings_count"] == 0


def test_tui_diff_computes_new_and_resolved_findings(tmp_path: Path) -> None:
    base = [
        {
            "path": "a.py",
            "line": 10,
            "rule": "lint/unused-import",
            "message": "Unused import x",
        },
        {
            "path": "b.py",
            "line": 5,
            "rule": "sec/sql-injection",
            "message": "Raw query",
        },
    ]
    current = [
        {
            "path": "a.py",
            "line": 10,
            "rule": "lint/unused-import",
            "message": "Unused import x",
        },
        {
            "path": "c.py",
            "line": 20,
            "rule": "quality/complexity",
            "message": "High cyclomatic complexity",
        },
    ]

    tool = TuiDiffTool()
    res = tool.run(tmp_path, base_findings=base, current_findings=current)

    assert res["status"] == "warn"
    assert res["metrics"] is not None
    assert res["metrics"]["new_findings_count"] == 1
    assert res["metrics"]["resolved_findings_count"] == 1
    assert res["metrics"]["unchanged_findings_count"] == 1
    assert len(res["findings"]) == 1
    assert res["findings"][0]["rule"] == "tui-diff/new-finding-regression"


def test_tui_diff_renders_table(tmp_path: Path) -> None:
    base = [{"path": "a.py", "line": 1, "rule": "r1", "message": "m1"}]
    current = [{"path": "b.py", "line": 2, "rule": "r2", "message": "m2"}]

    tool = TuiDiffTool()
    table_str = tool.render_table(base, current)

    assert "New Findings" in table_str or "NEW" in table_str
    assert "Resolved Findings" in table_str or "RESOLVED" in table_str
    assert "b.py" in table_str
