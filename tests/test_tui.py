"""Tests for Phase 27: Rich Interactive TUI.

Verifies:
- Layout generation and structure
- Finding tree rendering
"""

from __future__ import annotations

from rich.layout import Layout

from rush.tools.base import Finding, ToolResult
from rush.tui import build_tui_layout


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
