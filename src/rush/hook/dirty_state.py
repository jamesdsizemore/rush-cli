"""Working tree stash and isolation supervisor."""

from __future__ import annotations

from pathlib import Path
from rush.tools.common import run_subprocess


class DirtyStateStashSupervisor:
    """Stashes unstaged working tree changes to ensure hooks validate staged snapshots."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.stashed = False

    def stash_unstaged(self) -> bool:
        proc = run_subprocess(
            ["git", "stash", "push", "--keep-index", "-u", "-m", "rush-pre-commit-isolation"],
            cwd=self.repo_root,
        )
        if proc.returncode == 0 and "No local changes to save" not in proc.stdout:
            self.stashed = True
            return True
        return False

    def pop_stash(self) -> None:
        if self.stashed:
            run_subprocess(["git", "stash", "pop", "-q"], cwd=self.repo_root)
            self.stashed = False
