"""Sub-second staged file extractor and dispatcher."""

from __future__ import annotations

from pathlib import Path

from rush.tools.common import run_subprocess


class StagedFileScanner:
    """Discovers files currently staged in Git index for ultra-fast incremental scanning."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def get_staged_files(self) -> list[Path]:
        proc = run_subprocess(
            [
                "git",
                "--no-pager",
                "diff",
                "--cached",
                "--name-only",
                "--diff-filter=ACMR",
            ],
            cwd=self.repo_root,
        )
        if proc.returncode != 0:
            return []

        staged = []
        for line in proc.stdout.splitlines():
            line_clean = line.strip()
            if line_clean:
                p = self.repo_root / line_clean
                if p.exists() and p.is_file():
                    staged.append(p)
        return staged
