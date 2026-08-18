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
from .complexity import ComplexityTool
from .dead import DeadTool
from .format import FormatTool
from .lint import LintTool
from .markdown import MarkdownTool
from .review import ReviewTool
from .security import SecurityTool
from .slop import SlopTool
from .test import TestTool
from .typecheck import TypecheckTool

ALL_TOOLS: list[ToolFn] = [
    ReviewTool(),
    LintTool(),
    FormatTool(),
    TestTool(),
    SecurityTool(),
    TypecheckTool(),
    DeadTool(),
    ComplexityTool(),
    SlopTool(),
    MarkdownTool(),
]

__all__ = [
    # registry
    "ALL_TOOLS",
    "ComplexityTool",
    "DeadTool",
    "Finding",
    "FormatTool",
    "LintTool",
    "LlmStatus",
    "MarkdownTool",
    # concrete tool classes (for testing)
    "ReviewTool",
    "SecurityTool",
    "Severity",
    "SlopTool",
    "TestTool",
    "ToolFn",
    "ToolName",
    "ToolResult",
    # core types
    "ToolStatus",
    "TypecheckTool",
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
