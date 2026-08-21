"""Workspace filesystem read/write boundary guard."""

from __future__ import annotations

from pathlib import Path


class WorkspaceBoundaryGuard:
    """Ensures agent file operations remain strictly confined within repository root."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def is_safe_path(self, target_path: Path) -> bool:
        try:
            resolved = target_path.resolve()
            return resolved == self.repo_root or resolved.is_relative_to(self.repo_root)
        except Exception:
            return False
