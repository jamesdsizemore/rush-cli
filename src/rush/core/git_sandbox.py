"""Ephemeral Git worktree sandbox manager guaranteeing clean isolated execution."""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

from rush.io.physical_paths import PhysicalRoot
from rush.patch.contracts import DirtyWorkspaceError
from rush.tools.common import run_subprocess


class GitSandbox:
    """Creates a temporary, throwaway git worktree for non-destructive test execution."""

    def __init__(
        self,
        project_root: Path | None = None,
        base_ref: str = "HEAD",
        prefix: str = "sandbox",
    ):
        self.project_root = (project_root or Path.cwd()).resolve()
        self.physical_root = PhysicalRoot(self.project_root)
        self.base_ref = base_ref
        self.sandbox_id = f"{prefix}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.worktree_path = self.project_root / ".rush" / "worktrees" / self.sandbox_id
        self.branch_name = f"sandbox/{self.sandbox_id}"

    def __enter__(self) -> Path:
        # Pre-flight dirty check
        res = run_subprocess(["git", "status", "--porcelain"], cwd=self.project_root)
        if res.returncode != 0:
            raise DirtyWorkspaceError(
                f"Failed to check git status: {res.stderr or res.stdout}"
            )
        dirty_lines = [
            line
            for line in res.stdout.splitlines()
            if not line.strip().endswith(".rush/")
            and not line.strip().endswith(".rush")
        ]
        if dirty_lines:
            raise DirtyWorkspaceError(
                "Working directory has uncommitted or dirty changes. GitSandbox refuses dirty workspace."
            )

        rush_dir = self.project_root / ".rush"
        rush_dir.mkdir(parents=True, exist_ok=True)
        gitignore = rush_dir / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("*\n", encoding="utf-8")
        (rush_dir / "worktrees").mkdir(parents=True, exist_ok=True)

        contained_path = self.physical_root.open_contained(
            f".rush/worktrees/{self.sandbox_id}"
        )
        res = run_subprocess(
            [
                "git",
                "worktree",
                "add",
                "-b",
                self.branch_name,
                str(contained_path),
                self.base_ref,
            ],
            cwd=self.project_root,
        )
        if res.returncode != 0:
            raise RuntimeError(f"Failed to create git sandbox worktree: {res.stderr}")
        return contained_path

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
