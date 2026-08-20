"""Tests for standalone HTML report generation."""

from __future__ import annotations

from rush.html_export import export_to_html
from rush.tools.base import Finding, ToolResult


def test_export_to_html_clean():
    res: ToolResult = {
        "tool": "lint",
        "engine": "ruff",
        "engine_version": "0.5.0",
        "status": "ok",
        "duration_ms": 50,
        "summary": "All 10 files clean",
        "findings": [],
        "raw": None,
        "metadata": {},
    }

    doc = export_to_html(res)
    assert "<!DOCTYPE html>" in doc
    assert "Rush Quality &amp; Verification Report" in doc
    assert "All 10 files clean" in doc
    assert "No findings recorded" in doc


def test_export_to_html_findings():
    res: ToolResult = {
        "tool": "security",
        "engine": "semgrep",
        "engine_version": "1.0.0",
        "status": "fail",
        "duration_ms": 120,
        "summary": "1 critical finding",
        "findings": [
            Finding(
                path="src/main.py",
                line=42,
                rule="hardcoded-key",
                severity="fail",
                message="Do not hardcode API keys",
                fix="os.environ.get('KEY')",
            )
        ],
        "raw": None,
        "metadata": {},
    }

    doc = export_to_html(res)
    assert "<!DOCTYPE html>" in doc
    assert "hardcoded-key" in doc
    assert "src/main.py:42" in doc
    assert "os.environ.get(&#x27;KEY&#x27;)" in doc or "os.environ.get" in doc
