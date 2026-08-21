"""Protected main/master branch commit guard."""

from __future__ import annotations

from pathlib import Path
from rush.tools.common import run_subprocess

PROTECTED_BRANCHES = {"main", "master", "release"}


class BranchProtectionGuard:
    """Blocks accidental direct commits on protected branches."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def check_current_branch(self) -> tuple[bool, str | None]:
        proc = run_subprocess(
            ["git", "--no-pager", "branch", "--show-current"],
            cwd=self.repo_root,
        )
        if proc.returncode != 0:
            return True, None

        current = proc.stdout.strip()
        if current in PROTECTED_BRANCHES:
            return False, f"Direct commits to protected branch '{current}' are prohibited. Please use a feature branch."
        return True, None
