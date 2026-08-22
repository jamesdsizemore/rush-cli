"""Working tree mutation and dirty state tracker."""

from __future__ import annotations

from pathlib import Path

from rush.tools.common import run_subprocess


class WorkingTreeDirtyTracker:
    """Tracks uncommitted file modifications and prevents clobbering dirty working states."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def get_dirty_files(self) -> list[str]:
        proc = run_subprocess(["git", "status", "--porcelain"], cwd=self.repo_root)
        if proc.returncode != 0:
            return []
        dirty = []
        for line in proc.stdout.splitlines():
            line_clean = line.strip()
            if len(line_clean) > 3:
                dirty.append(line_clean[3:].strip())
        return dirty
