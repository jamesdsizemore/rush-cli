"""Scratch cleaner purging temporary directories and cache files."""

import shutil
from pathlib import Path
from typing import Any, ClassVar


class ScratchCleaner:
    """Cleans temporary build artifacts, pytest caches, and scratch files."""

    CLEAN_PATTERNS: ClassVar[list[str]] = [
        "scratch",
        "tmp",
        ".pytest_cache",
        "__pycache__",
        "*.pyc",
        ".ruff_cache",
    ]

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()

    def clean(self, dry_run: bool = False) -> dict[str, Any]:
        removed: list[str] = []
        bytes_freed = 0

        for pattern in self.CLEAN_PATTERNS:
            for p in self.project_root.glob(f"**/{pattern}"):
                if ".venv" in str(p) or ".git" in str(p):
                    continue
                if p.is_file():
                    size = p.stat().st_size
                    bytes_freed += size
                    removed.append(str(p.relative_to(self.project_root)))
                    if not dry_run:
                        p.unlink()
                elif p.is_dir():
                    removed.append(str(p.relative_to(self.project_root)))
                    if not dry_run:
                        shutil.rmtree(p, ignore_errors=True)

        return {
            "dry_run": dry_run,
            "removed_count": len(removed),
            "removed_items": removed,
            "bytes_freed": bytes_freed,
        }
