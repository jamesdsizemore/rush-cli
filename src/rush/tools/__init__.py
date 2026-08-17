"""Tool registry — single source of truth for CLI and MCP.

Architecture §3.5. ALL_TOOLS is iterated by both:
- src/rush/cli.py: to register subcommands
- src/rush/mcp.py: to register MCP tools
"""

from __future__ import annotations

from .base import Finding, LlmStatus, Severity, ToolFn, ToolName, ToolResult, ToolStatus
from .common import (
    engine_on_path,
    error_result,
    exit_code_for,
    normalize_findings,
    now_ms,
    run_subprocess,
    skipped_result,
)
from .format import FormatTool
from .lint import LintTool
from .review import ReviewTool
from .security import SecurityTool
from .test import TestTool

ALL_TOOLS: list[ToolFn] = [
    ReviewTool(),
    LintTool(),
    FormatTool(),
    TestTool(),
    SecurityTool(),
]

__all__ = [
    # registry
    "ALL_TOOLS",
    "Finding",
    "FormatTool",
    "LintTool",
    "LlmStatus",
    # concrete tool classes (for testing)
    "ReviewTool",
    "SecurityTool",
    "Severity",
    "TestTool",
    "ToolFn",
    "ToolName",
    "ToolResult",
    # core types
    "ToolStatus",
    "elapsed_ms",
    # common helpers
    "engine_on_path",
    "error_result",
    "exit_code_for",
    "normalize_findings",
    "now_ms",
    "resolve_binary",
    "run_engine",
    "run_subprocess",
    "skipped_result",
]
