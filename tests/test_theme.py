"""Tests for Rich theme formatters and interactive dashboard rendering."""

from __future__ import annotations

from rush.theme import render_dashboard, render_result


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
