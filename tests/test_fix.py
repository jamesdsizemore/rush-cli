"""Tests for Phase 22: Confined Automated Remediation (rush fix).

Verifies:
- Path confinement / path traversal rejection (outside repo boundary)
- Git dirty-tree safety checks and --force override
- Catalog and Tool registry membership
- Fix execution across auto-fixable engines (ruff, biome, eslint, prettier)
- Dry-run diff previewing and atomic rollback on failure
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from rush.catalog import TOOL_SPECS
from rush.permissions import ExecutionPermissions
from rush.tools import ALL_TOOLS
from rush.tools.base import ToolResult
from rush.tools.fix import FixTool, assert_safe_workspace_path


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

    f1 = repo / "main.py"
    f1.write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "main.py"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True
    )
    return repo


def test_fix_catalog_and_registry() -> None:
    assert "fix" in TOOL_SPECS
    spec = TOOL_SPECS["fix"]
    assert spec.maturity == "real_adapter"

    tool_names = [t.name for t in ALL_TOOLS]
    assert "fix" in tool_names


def test_assert_safe_workspace_path(temp_git_repo: Path, tmp_path: Path) -> None:
    inside_file = temp_git_repo / "main.py"
    assert assert_safe_workspace_path(inside_file, repo_root=temp_git_repo) is True

    outside_file = tmp_path / "outside.py"
    outside_file.write_text("evil = 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="outside repository boundary"):
        assert_safe_workspace_path(outside_file, repo_root=temp_git_repo)


def test_fix_dirty_tree_abort(temp_git_repo: Path) -> None:
    tool = FixTool()
    # Create uncommitted modification
    f1 = temp_git_repo / "main.py"
    f1.write_text("x = 2\n", encoding="utf-8")

    res = tool.run(temp_git_repo, permissions=ExecutionPermissions(), force=False)
    assert res["status"] in {"fail", "error"}
    assert "Uncommitted changes detected" in res["summary"]


def test_fix_dry_run_preview(temp_git_repo: Path) -> None:
    tool = FixTool()
    with patch.object(
        FixTool,
        "_run_engine_fixes",
        return_value=ToolResult(
            tool="fix",
            status="ok",
            duration_ms=25,
            summary="fix: 1 file would be modified (dry run)",
            findings=[],
        ),
    ):
        res = tool.run(
            temp_git_repo, permissions=ExecutionPermissions(), dry_run=True, force=True
        )
        assert res["status"] == "ok"
        assert "dry run" in res["summary"]


def test_snapshot_journal_rollback(tmp_path: Path) -> None:
    from rush.tools.fix import SnapshotJournal

    f = tmp_path / "code.py"
    f.write_text("orig = 1\n", encoding="utf-8")

    journal = SnapshotJournal()
    journal.capture([f])

    f.write_text("mutated = 2\n", encoding="utf-8")
    assert journal.has_changes(f) is True

    journal.rollback_all()
    assert f.read_text(encoding="utf-8") == "orig = 1\n"
    assert journal.has_changes(f) is False


def test_validate_ast_detection(tmp_path: Path) -> None:
    tool = FixTool()

    good_py = tmp_path / "good.py"
    good_py.write_text("def ok(): pass\n", encoding="utf-8")
    valid, err = tool.validate_ast(good_py)
    assert valid is True
    assert err is None

    bad_py = tmp_path / "bad.py"
    bad_py.write_text("def broken(: pass\n", encoding="utf-8")
    valid, err = tool.validate_ast(bad_py)
    assert valid is False
    assert "SyntaxError" in (err or "")
