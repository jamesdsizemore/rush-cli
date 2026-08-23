"""Ephemeral Git worktree sandbox manager guaranteeing clean isolated execution."""

import os
import shutil
import uuid
from pathlib import Path

from src.rush.tools.common import run_subprocess


class GitSandbox:
    """Creates a temporary, throwaway git worktree for non-destructive test execution."""

    def __init__(
        self,
        project_root: Path | None = None,
        base_ref: str = "HEAD",
        prefix: str = "sandbox",
    ):
        self.project_root = project_root or Path.cwd()
        self.base_ref = base_ref
        self.sandbox_id = f"{prefix}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.worktree_path = self.project_root / ".rush" / "worktrees" / self.sandbox_id
        self.branch_name = f"sandbox/{self.sandbox_id}"

    def __enter__(self) -> Path:
        self.worktree_path.parent.mkdir(parents=True, exist_ok=True)
        res = run_subprocess(
            [
                "git",
                "worktree",
                "add",
                "-b",
                self.branch_name,
                str(self.worktree_path),
                self.base_ref,
            ],
            cwd=self.project_root,
        )
        if res.returncode != 0:
            raise RuntimeError(f"Failed to create git sandbox worktree: {res.stderr}")
        return self.worktree_path

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        run_subprocess(
            ["git", "worktree", "remove", "--force", str(self.worktree_path)],
            cwd=self.project_root,
        )
        run_subprocess(
            ["git", "branch", "-D", self.branch_name],
            cwd=self.project_root,
        )
        if self.worktree_path.exists():
            shutil.rmtree(self.worktree_path, ignore_errors=True)
