"""Tool registry — single source of truth for CLI and MCP.

Architecture §3.5. ALL_TOOLS is iterated by both:
- src/rush/cli.py: to register subcommands
- src/rush/mcp.py: to register MCP tools
"""

from __future__ import annotations

from .actions import ActionsTool
from .ai_eval import AiEvalTool
from .attest import AttestationTool
from .base import (
    Finding,
    FindingV1,
    LlmStatus,
    Severity,
    ToolFn,
    ToolName,
    ToolResult,
    ToolResultV1,
    ToolStatus,
    ValidationErrorV1,
    adapt_legacy_finding,
    adapt_legacy_tool_result,
    validate_tool_result,
)
from .benchmark import BenchmarkTool
from .ci import CiTool
from .codeql import CodeqlTool
from .cold_start import ColdStartTool
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
from .continuity import SessionContinuityTool
from .contract import ContractTool
from .coverage import CoverageTool
from .dead import DeadTool
from .dead_asset import DeadAssetScanner, DeadAssetTool
from .doctor import DoctorTool
from .e2e import E2eTool
from .error_catalog import ErrorCatalogTool
from .fix import FixTool
from .flaky import FlakyTool
from .format import FormatTool
from .fuzz import FuzzTool
from .iac import IacTool
from .iam_audit import IamAuditTool
from .license_matrix import LicenseMatrixTool
from .lint import LintTool
from .load import LoadTool
from .markdown import MarkdownTool
from .media_opt import MediaOptTool
from .mem_profile import MemProfileTool
from .memory import MemoryTool
from .mutation import MutationTool
from .offline_runner import OfflineReviewTool
from .patch_apply import PatchApplyTool
from .pbt import PbtTool
from .pr_synthesize import PrSynthesizer, PrSynthesizeTool
from .prompt_eval import PromptEvalTool
from .provenance_ai import ProvenanceAiTool
from .release import ReleaseTool
from .review import ReviewTool
from .sbom import SbomTool
from .secrets import SecretsTool
from .security import SecurityTool
from .semantic_drift import SemanticDriftTool
from .slop import SlopTool
from .snapshot import SnapshotTool
from .sql import SqlTool
from .tdd_guard import TddGuardTool
from .templates import TemplatesTool
from .test import TestTool
from .tui_diff import TuiDiffTool
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
    SessionContinuityTool(),
    MemoryTool(),
    CiTool(),
    ReleaseTool(),
    SemanticDriftTool(),
    AiEvalTool(),
    TddGuardTool(),
    FixTool(),
    PatchApplyTool(),
    DoctorTool(),
    AttestationTool(),
    LicenseMatrixTool(),
    IamAuditTool(),
    PromptEvalTool(),
    MemProfileTool(),
    ColdStartTool(),
    MediaOptTool(),
    OfflineReviewTool(),
    TuiDiffTool(),
    BenchmarkTool(),
    ErrorCatalogTool(),
    ProvenanceAiTool(),
    DeadAssetTool(),
    PrSynthesizeTool(),
]

__all__ = [  # noqa: RUF022
    # registry
    "ALL_TOOLS",
    "AiEvalTool",
    "AttestationTool",
    "BenchmarkTool",
    "ColdStartTool",
    "ComplexityTool",
    "DeadAssetScanner",
    "DeadAssetTool",
    "DeadTool",
    "DoctorTool",
    "ErrorCatalogTool",
    "Finding",
    "FindingV1",
    "FixTool",
    "FormatTool",
    "IamAuditTool",
    "LicenseMatrixTool",
    "LintTool",
    "LlmStatus",
    "MarkdownTool",
    "MediaOptTool",
    "MemProfileTool",
    "MemoryTool",
    "OfflineReviewTool",
    "PatchApplyTool",
    "PrSynthesizeTool",
    "PrSynthesizer",
    "PromptEvalTool",
    "ProvenanceAiTool",
    # concrete tool classes (for testing)
    "ReviewTool",
    "SecurityTool",
    "SemanticDriftTool",
    "SessionContinuityTool",
    "Severity",
    "SlopTool",
    "TestTool",
    "ToolFn",
    "ToolName",
    "ToolResult",
    "ToolResultV1",
    "ValidationErrorV1",
    "adapt_legacy_finding",
    "adapt_legacy_tool_result",
    "validate_tool_result",
    "TuiDiffTool",
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
