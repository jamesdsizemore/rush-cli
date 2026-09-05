"""Isolated closed-loop AI patch remediation and session memory."""

from __future__ import annotations

from rush.patch.applier import PatchApplier
from rush.patch.circuit_breaker import RemediationCircuitBreaker
from rush.patch.contracts import (
    DirtyWorkspaceError,
    PatchContract,
    PatchOutcome,
    PatchVerificationError,
    PatchVerificationResult,
    VerifierCommandPlan,
)
from rush.patch.diff_parser import DiffHunk, ParsedFilePatch, UnifiedDiffParser
from rush.patch.memory import PatchMemoryRecord, PatchMemoryStore
from rush.patch.promoter import PatchPromoter
from rush.patch.sandbox import PatchSandboxManager
from rush.patch.syntax_guard import PatchSyntaxGuard
from rush.patch.verifier import PatchVerifier

__all__ = [
    "DiffHunk",
    "DirtyWorkspaceError",
    "ParsedFilePatch",
    "PatchApplier",
    "PatchContract",
    "PatchMemoryRecord",
    "PatchMemoryStore",
    "PatchOutcome",
    "PatchPromoter",
    "PatchSandboxManager",
    "PatchSyntaxGuard",
    "PatchVerificationError",
    "PatchVerificationResult",
    "PatchVerifier",
    "RemediationCircuitBreaker",
    "UnifiedDiffParser",
    "VerifierCommandPlan",
]
