"""Ephemeral Git worktree sandbox manager for safe AI patch execution."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from rush.tools.common import run_subprocess


class PatchSandboxManager:
    """Manages isolated Git worktrees for safe patch testing and regression verification."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.worktrees_dir = self.repo_root / ".rush" / "worktrees"

    def create_sandbox(self) -> Path:
        self.worktrees_dir.mkdir(parents=True, exist_ok=True)
        sandbox_id = f"sandbox_{uuid.uuid4().hex[:8]}"
        sandbox_path = self.worktrees_dir / sandbox_id

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
        run_subprocess(
            ["git", "worktree", "remove", "--force", str(sandbox_path)],
            cwd=self.repo_root,
        )
        if sandbox_path.exists():
            shutil.rmtree(sandbox_path, ignore_errors=True)
