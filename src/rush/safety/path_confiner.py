"""Strict workspace path boundary validator."""

from __future__ import annotations

from pathlib import Path


class WorkspacePathConfiner:
    """Ensures that all file operations remain strictly confined to repository root."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def confine_path(self, target_path: Path | str) -> Path:
        p = Path(target_path)
        resolved = (
            (self.repo_root / p).resolve() if not p.is_absolute() else p.resolve()
        )

        if not resolved.is_relative_to(self.repo_root):
            raise PermissionError(
                f"Path traversal blocked: '{target_path}' resolves outside repository root."
            )
        return resolved
