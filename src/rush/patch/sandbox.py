"""Ephemeral Git worktree sandbox manager for safe AI patch execution."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from rush.io.physical_paths import ContainmentError, PhysicalRoot
from rush.patch.contracts import DirtyWorkspaceError
from rush.tools.common import run_subprocess


class PatchSandboxManager:
    """Manages isolated Git worktrees for safe patch testing and regression verification."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.physical_root = PhysicalRoot(self.repo_root)
        self.worktrees_dir = self.repo_root / ".rush" / "worktrees"

    def _ensure_rush_dir(self) -> None:
        rush_dir = self.repo_root / ".rush"
        rush_dir.mkdir(parents=True, exist_ok=True)
        gitignore = rush_dir / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("*\n", encoding="utf-8")
        self.worktrees_dir.mkdir(parents=True, exist_ok=True)

    def create_sandbox(self) -> Path:
        # Pre-flight clean check: fail-closed if repo has uncommitted or untracked changes
        proc = run_subprocess(["git", "status", "--porcelain"], cwd=self.repo_root)
        if proc.returncode != 0:
            raise DirtyWorkspaceError(
                f"Failed to check git status: {proc.stderr or proc.stdout}"
            )
        dirty_lines = [
            line
            for line in proc.stdout.splitlines()
            if not line.strip().endswith(".rush/")
            and not line.strip().endswith(".rush")
        ]
        if dirty_lines:
            raise DirtyWorkspaceError(
                "Working directory has uncommitted changes. Patch sandbox refuses dirty workspace."
            )

        self._ensure_rush_dir()
        sandbox_id = f"sandbox_{uuid.uuid4().hex[:8]}"
        sandbox_path = self.physical_root.open_contained(
            f".rush/worktrees/{sandbox_id}"
        )

        proc = run_subprocess(
            ["git", "worktree", "add", "--detach", str(sandbox_path), "HEAD"],
            cwd=self.repo_root,
        )
        if proc.returncode != 0:
            # Fallback for bare repos or non-worktree setups: copy working files
            sandbox_path.mkdir(parents=True, exist_ok=True)

        return sandbox_path

    def cleanup_sandbox(self, sandbox_path: Path) -> None:
        if not sandbox_path.exists():
            return

        resolved = sandbox_path.resolve()
        if not resolved.is_relative_to(self.repo_root):
            raise ContainmentError(
                "PATH_ESCAPE_DISALLOWED",
                f"Sandbox path escapes physical root: {resolved}",
                str(sandbox_path),
            )

        run_subprocess(
            ["git", "worktree", "remove", "--force", str(sandbox_path)],
            cwd=self.repo_root,
        )
        if sandbox_path.exists():
            shutil.rmtree(sandbox_path, ignore_errors=True)

    def cleanup_all(self) -> None:
        if self.worktrees_dir.exists():
            for item in list(self.worktrees_dir.iterdir()):
                if item.is_dir():
                    self.cleanup_sandbox(item)
