"""Git repository boundary discovery and scoping utilities.

Architecture §8, Phase 21.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from rush.logging import log_subsystem

SAFE_GIT_REF_PATTERN = re.compile(r"^[a-zA-Z0-9_./@~^-]+$")


def validate_git_ref(ref: str) -> str:
    """Validate Git reference to prevent CLI argument injection.

    Raises:
        ValueError: If reference contains hostile shell characters or starts with a dash.
    """
    ref_clean = ref.strip()
    if (
        not ref_clean
        or ref_clean.startswith("-")
        or not SAFE_GIT_REF_PATTERN.match(ref_clean)
    ):
        raise ValueError(
            f"Security Error: Invalid Git reference specification: '{ref}'"
        )
    return ref_clean


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


def _files_under(target: Path, diff_args: list[str]) -> list[Path]:
    """`git diff --name-only` paths are relative to the repository top level,
    not to `target`: resolve them against `rev-parse --show-toplevel`, then
    keep only existing files inside `target` (the whole repo when `target`
    is its root)."""
    toplevel = _run_git(["rev-parse", "--show-toplevel"], target)
    if not toplevel:
        return []
    top = Path(toplevel[0]).resolve()
    scope = target.resolve()
    files = [(top / p).resolve() for p in _run_git(diff_args, target)]
    return [f for f in files if f.is_file() and (f == scope or scope in f.parents)]


def get_staged_files(repo_root: Path) -> list[Path]:
    """Return the files staged in the Git index under `repo_root`."""
    return _files_under(
        repo_root, ["diff", "--cached", "--name-only", "--diff-filter=ACMR"]
    )


def get_changed_files(repo_root: Path) -> list[Path]:
    """Return the modified, unstaged working-tree files under `repo_root`."""
    return _files_under(repo_root, ["diff", "--name-only", "--diff-filter=ACMR"])


def get_files_since(repo_root: Path, ref: str) -> list[Path]:
    """Return the files under `repo_root` changed since a commit, branch or tag."""
    safe_ref = validate_git_ref(ref)
    return _files_under(
        repo_root, ["diff", "--name-only", "--diff-filter=ACMR", safe_ref]
    )
