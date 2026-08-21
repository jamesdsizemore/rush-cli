"""Git Pre-Commit Intelligence & Hook Guard Engine."""

from __future__ import annotations

from rush.hook.ast_linter import FastIncrementalAstLinter
from rush.hook.branch_guard import BranchProtectionGuard
from rush.hook.conflict_guard import ConflictMarkerGuard
from rush.hook.conventional_commit import ConventionalCommitValidator
from rush.hook.dirty_state import DirtyStateStashSupervisor
from rush.hook.staged_scanner import StagedFileScanner
from rush.hook.tamper_detector import HookTamperDetector
from rush.hook.trojan_source import TrojanSourceDetector

__all__ = [
    "BranchProtectionGuard",
    "ConflictMarkerGuard",
    "ConventionalCommitValidator",
    "DirtyStateStashSupervisor",
    "FastIncrementalAstLinter",
    "HookTamperDetector",
    "StagedFileScanner",
    "TrojanSourceDetector",
]
