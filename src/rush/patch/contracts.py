"""Immutable contracts and outcome schemas for fail-closed patch verification."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

PatchOutcome = Literal["completed", "unavailable", "failed"]


class DirtyWorkspaceError(Exception):
    """Raised when patch operation refuses execution on a dirty workspace."""


class PatchVerificationError(Exception):
    """Raised when patch verification or contract invariants fail closed."""


@dataclass(frozen=True)
class VerifierCommandPlan:
    """Declared verification command plan to execute in sandbox."""

    command: tuple[str, ...]
    cwd_relative: str = "."
    expected_exit_code: int = 0
    timeout_seconds: float = 60.0


@dataclass(frozen=True)
class PatchContract:
    """Cryptographic binding of base commit, patch, sandbox, command plan, and policy."""

    base_commit: str
    base_tree_digest: str
    patch_content_digest: str
    sandbox_path: Path
    required_commands: tuple[VerifierCommandPlan, ...]
    config_digest: str
    review_class: str = "standard"  # 'standard', 'policy-changing', 'privileged'


@dataclass(frozen=True)
class PatchVerificationResult:
    """Truthful outcome record from patch sandbox execution."""

    outcome: PatchOutcome
    executed_commands: tuple[dict[str, Any], ...]
    passed_count: int
    summary: str
    rollback_applied: bool = False
