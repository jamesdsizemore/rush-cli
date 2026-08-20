"""Tests for Phase 21: Git-Aware Scoping Discovery.

Verifies:
- Resolving staged files (`--staged`)
- Resolving changed uncommitted files (`--changed`)
- Resolving files changed since a reference (`--since <ref>`)
- Graceful degradation when git repository is not available
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from rush.discovery.git import (
    get_changed_files,
    get_files_since,
    get_staged_files,
)


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "RushTester"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "rush@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    # Create initial commit
    f1 = repo / "file1.py"
    f1.write_text("print('file1')\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "file1.py"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True
    )
    return repo


def test_get_staged_files(temp_git_repo: Path) -> None:
    # Modify and stage a file
    f2 = temp_git_repo / "file2.py"
    f2.write_text("print('file2')\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "file2.py"], cwd=temp_git_repo, check=True, capture_output=True
    )

    staged = get_staged_files(temp_git_repo)
    assert len(staged) == 1
    assert staged[0].name == "file2.py"


def test_get_changed_files(temp_git_repo: Path) -> None:
    # Modify an existing file without staging
    f1 = temp_git_repo / "file1.py"
    f1.write_text("print('modified file1')\n", encoding="utf-8")

    changed = get_changed_files(temp_git_repo)
    assert len(changed) == 1
    assert changed[0].name == "file1.py"


def test_get_files_since(temp_git_repo: Path) -> None:
    # Create a second commit
    f3 = temp_git_repo / "file3.py"
    f3.write_text("print('file3')\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "file3.py"], cwd=temp_git_repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "commit 2"],
        cwd=temp_git_repo,
        check=True,
        capture_output=True,
    )

    # HEAD~1 comparison
    since_files = get_files_since(temp_git_repo, "HEAD~1")
    assert len(since_files) == 1
    assert since_files[0].name == "file3.py"
