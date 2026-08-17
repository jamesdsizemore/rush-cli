"""Tool registry — single source of truth for CLI and MCP.

Architecture §3.5. ALL_TOOLS is iterated by both:
- src/rush/cli.py: to register subcommands
- src/rush/mcp.py: to register MCP tools
"""

from __future__ import annotations

from .base import ToolFn, ToolResult, ToolStatus, Finding, ToolName, Severity, LlmStatus
from .common import (
    engine_on_path,
    run_subprocess,
    skipped_result,
    error_result,
    normalize_findings,
    exit_code_for,
    now_ms,
)
from .review import ReviewTool
from .lint import LintTool
from .format import FormatTool
from .test import TestTool
from .security import SecurityTool

ALL_TOOLS: list[ToolFn] = [
    ReviewTool(),
    LintTool(),
    FormatTool(),
    TestTool(),
    SecurityTool(),
]

__all__ = [
    # core types
    "ToolStatus",
    "ToolName",
    "Severity",
    "LlmStatus",
    "Finding",
    "ToolResult",
    "ToolFn",
    # common helpers
    "engine_on_path",
    "resolve_binary",
    "run_subprocess",
    "run_engine",
    "skipped_result",
    "error_result",
    "normalize_findings",
    "exit_code_for",
    "now_ms",
    "elapsed_ms",
    # registry
    "ALL_TOOLS",
    # concrete tool classes (for testing)
    "ReviewTool",
    "LintTool",
    "FormatTool",
    "TestTool",
    "SecurityTool",
]
