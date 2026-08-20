"""Git repository boundary discovery and scoping utilities.

Architecture §8, Phase 21.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.logging import log_subsystem


def _run_git(args: list[str], repo_root: Path) -> list[str]:
    try:
        res = subprocess.run(
            ["git", *args],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
            stdin=subprocess.DEVNULL,
        )
        if res.returncode == 0:
            return [line.strip() for line in res.stdout.splitlines() if line.strip()]
        return []
    except Exception as exc:  # noqa: BLE001
        log_subsystem("git", "WARN", f"Git invocation error: {exc}")
        return []


def get_staged_files(repo_root: Path) -> list[Path]:
    """Return list of files staged in the Git index."""
    lines = _run_git(
        ["diff", "--cached", "--name-only", "--diff-filter=ACMR"], repo_root
    )
    return [(repo_root / p).resolve() for p in lines if (repo_root / p).is_file()]


def get_changed_files(repo_root: Path) -> list[Path]:
    """Return list of modified, unstaged files in the working tree."""
    lines = _run_git(["diff", "--name-only", "--diff-filter=ACMR"], repo_root)
    return [(repo_root / p).resolve() for p in lines if (repo_root / p).is_file()]


def get_files_since(repo_root: Path, ref: str) -> list[Path]:
    """Return list of files changed since a Git commit, branch, or tag."""
    lines = _run_git(["diff", "--name-only", "--diff-filter=ACMR", ref], repo_root)
    return [(repo_root / p).resolve() for p in lines if (repo_root / p).is_file()]
