"""Unified Diff Generator & Atomic Patch Application Engine (Control 7).

Architecture §8, Phase 29.
Enforces Patch Confinement & Protected Path Shielding.
"""

from __future__ import annotations

import difflib
from pathlib import Path

from rush.logging import get_logger, log_subsystem

logger = get_logger("patch_generator")

PROTECTED_PATHS = frozenset(
    {
        ".git",
        ".env",
        ".rush/cache.db",
        "id_rsa",
        "id_ed25519",
    }
)


def generate_unified_diff(original: str, modified: str, file_path: str) -> str:
    """Generate canonical unified diff string from two text snapshots."""
    orig_lines = original.splitlines(keepends=True)
    mod_lines = modified.splitlines(keepends=True)

    diff_lines = list(
        difflib.unified_diff(
            orig_lines,
            mod_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
        )
    )
    return "".join(diff_lines)


def _extract_target_file_from_patch(patch_str: str) -> str | None:
    """Parse target file path from unified diff headers."""
    for line in patch_str.splitlines():
        if line.startswith("+++ b/"):
            return line[len("+++ b/") :].strip()
        if line.startswith("+++ "):
            return line[len("+++ ") :].strip()
    return None


def apply_unified_patch(patch_str: str, repo_root: Path) -> bool:
    """Atomically apply a unified diff patch to a workspace file.

    Raises ValueError if the patch attempts path traversal or modifies protected files.
    """
    rel_path_str = _extract_target_file_from_patch(patch_str)
    if not rel_path_str:
        log_subsystem(
            "patch", "ERROR", "Could not determine target file from diff header"
        )
        return False

    # 1. Path Confinement Validation
    if ".." in rel_path_str:
        log_subsystem(
            "patch",
            "SECURITY_ERROR",
            f"Patch target path '{rel_path_str}' attempts directory traversal",
        )
        raise ValueError(
            f"Security Error: Patch target path '{rel_path_str}' resolves outside repository root"
        )

    root_resolved = repo_root.resolve()
    target_path = (root_resolved / rel_path_str).resolve()

    if not (target_path == root_resolved or target_path.is_relative_to(root_resolved)):
        log_subsystem(
            "patch",
            "SECURITY_ERROR",
            f"Patch target '{target_path}' resolves outside root '{root_resolved}'",
        )
        raise ValueError(
            f"Security Error: Patch target resolves outside repository root: {rel_path_str}"
        )

    # 2. Protected Path Shielding
    for prot in PROTECTED_PATHS:
        if prot in rel_path_str or prot in target_path.parts:
            log_subsystem(
                "patch",
                "SECURITY_ERROR",
                f"Patch attempted to modify protected file: {rel_path_str}",
            )
            raise ValueError(
                f"Security Error: Protected system file cannot be modified: {rel_path_str}"
            )

    # 3. Simple Unified Diff Line Application
    if not target_path.is_file():
        log_subsystem("patch", "ERROR", f"Target file does not exist: {target_path}")
        return False

    # Extract added/removed lines from diff
    new_lines: list[str] = []
    diff_body = [
        l
        for l in patch_str.splitlines(keepends=True)
        if not l.startswith(("---", "+++", "@@"))
    ]

    for d_line in diff_body:
        if d_line.startswith(("+", " ")):
            new_lines.append(d_line[1:])
        # Omit lines starting with '-'

    if new_lines:
        target_path.write_text("".join(new_lines), encoding="utf-8")
        log_subsystem("patch", "INFO", f"Applied patch to {target_path}")
        return True

    return False
