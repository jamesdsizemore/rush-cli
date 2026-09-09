"""Tests for Rich theme formatters and interactive dashboard rendering."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from rush import theme
from rush.theme import render_dashboard, render_result


def test_findings_table_omits_empty_fix_column(monkeypatch):
    output = StringIO()
    monkeypatch.setattr(theme, "_shared_console", Console(file=output, width=120))
    finding = {"path": "app.py", "line": 1, "rule": "E1", "message": "Problem"}
    result = {"tool": "lint", "status": "warn", "findings": [finding]}

    render_result(result)
    assert "fix" not in output.getvalue()

    output.seek(0)
    output.truncate()
    finding["fix"] = "replacement"
    render_result(result)
    assert "fix" in output.getvalue()
    assert "replacement" in output.getvalue()


def test_render_result():
    res = {
        "tool": "lint",
        "status": "warn",
        "summary": "1 warning found",
        "findings": [
            {
                "path": "src/app.py",
                "line": 12,
                "rule": "E501",
                "severity": "warn",
                "message": "Line too long",
                "fix": "wrap line",
            }
        ],
    }
    # Test that render_result executes cleanly without error
    render_result(res)


def test_render_dashboard():
    results = [
        {
            "tool": "lint",
            "engine": "ruff",
            "status": "ok",
            "duration_ms": 45,
            "summary": "All files clean",
            "findings": [],
        },
        {
            "tool": "security",
            "engine": "semgrep",
            "status": "warn",
            "duration_ms": 120,
            "summary": "1 potential issue",
            "findings": [
                {
                    "path": "src/db.py",
                    "line": 5,
                    "rule": "sql-injection",
                    "severity": "warn",
                    "message": "Verify parameterized queries",
                }
            ],
        },
    ]
    # Test that render_dashboard executes cleanly without error
    render_dashboard(results)
