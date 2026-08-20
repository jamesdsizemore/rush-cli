"""Tool registry — single source of truth for CLI and MCP.

Architecture §3.5. ALL_TOOLS is iterated by both:
- src/rush/cli.py: to register subcommands
- src/rush/mcp.py: to register MCP tools
"""

from __future__ import annotations

from .actions import ActionsTool
from .ai_eval import AiEvalTool
from .base import Finding, LlmStatus, Severity, ToolFn, ToolName, ToolResult, ToolStatus
from .ci import CiTool
from .codeql import CodeqlTool
from .commit_msg import CommitMsgTool
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
from .containerfile import ContainerfileTool
from .contract import ContractTool
from .coverage import CoverageTool
from .dead import DeadTool
from .e2e import E2eTool
from .flaky import FlakyTool
from .format import FormatTool
from .fuzz import FuzzTool
from .iac import IacTool
from .lint import LintTool
from .load import LoadTool
from .markdown import MarkdownTool
from .mutation import MutationTool
from .pbt import PbtTool
from .release import ReleaseTool
from .review import ReviewTool
from .sbom import SbomTool
from .secrets import SecretsTool
from .security import SecurityTool
from .semantic_drift import SemanticDriftTool
from .slop import SlopTool
from .snapshot import SnapshotTool
from .sql import SqlTool
from .templates import TemplatesTool
from .test import TestTool
from .typecheck import TypecheckTool
from .visual import VisualTool
from .yaml import YamlTool

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
    ActionsTool(),
    YamlTool(),
    SqlTool(),
    TemplatesTool(),
    ContainerfileTool(),
    IacTool(),
    SecretsTool(),
    SbomTool(),
    CoverageTool(),
    CodeqlTool(),
    E2eTool(),
    SnapshotTool(),
    VisualTool(),
    PbtTool(),
    MutationTool(),
    FlakyTool(),
    ContractTool(),
    FuzzTool(),
    LoadTool(),
    CommitMsgTool(),
    CiTool(),
    ReleaseTool(),
    SemanticDriftTool(),
    AiEvalTool(),
]

__all__ = [
    # registry
    "ALL_TOOLS",
    "AiEvalTool",
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
    "SemanticDriftTool",
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
