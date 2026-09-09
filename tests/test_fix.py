"""Tests for Phase 22: Confined Automated Remediation (rush fix).

Verifies:
- Path confinement / path traversal rejection (outside repo boundary)
- Git dirty-tree safety checks and --force override
- Catalog and Tool registry membership
- Fix execution across auto-fixable engines (ruff, biome, eslint, prettier)
- Dry-run diff previewing and atomic rollback on failure
"""

from __future__ import annotations

import inspect
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from rush.catalog import TOOL_SPECS
from rush.cli import cli
from rush.invocation import InvocationExecutor
from rush.mcp_support.tool_registry import register_all_tools
from rush.permissions import ExecutionPermissions
from rush.tools import ALL_TOOLS
from rush.tools.base import ToolResult
from rush.tools.fix import FixTool, assert_safe_workspace_path

WRITE_PERMISSIONS = ExecutionPermissions(artifact_write=True)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _dirty_repo(tmp_path: Path, source: str) -> Path:
    repo = tmp_path / "dirty-repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "RushTester")
    _git(repo, "config", "user.email", "rush@example.com")
    (repo / "main.py").write_text(source, encoding="utf-8")
    (repo / "notes.txt").write_text("committed\n", encoding="utf-8")
    _git(repo, "add", "main.py", "notes.txt")
    _git(repo, "commit", "-m", "fixture")
    (repo / "notes.txt").write_text("committed\nstaged\n", encoding="utf-8")
    _git(repo, "add", "notes.txt")
    (repo / "notes.txt").write_text("committed\nstaged\nunstaged\n", encoding="utf-8")
    (repo / "sentinel.txt").write_text("untracked\n", encoding="utf-8")
    return repo


def _repo_state(repo: Path) -> tuple[dict[str, bytes], bytes, bytes, tuple[str, ...]]:
    files = {
        path.name: path.read_bytes()
        for path in (repo / "main.py", repo / "notes.txt", repo / "sentinel.txt")
    }
    cached = _git(repo, "diff", "--cached", "--binary").stdout
    head = _git(repo, "rev-parse", "HEAD").stdout
    untracked = tuple(
        sorted(
            _git(repo, "ls-files", "--others", "--exclude-standard")
            .stdout.decode()
            .splitlines()
        )
    )
    return files, cached, head, untracked


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

    res = tool.run(temp_git_repo, permissions=WRITE_PERMISSIONS, force=False)
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


@pytest.mark.parametrize(
    ("source", "expected_status"),
    [
        ("def add( a,b ):return a+b\n", "warn"),
        ("print(missing)\n", "warn"),
        ("def broken(:\n", "error"),
    ],
)
def test_dry_run_preserves_index_and_unrelated_files(
    tmp_path: Path, source: str, expected_status: str
) -> None:
    repo = _dirty_repo(tmp_path, source)
    before = _repo_state(repo)

    result = FixTool().run(repo, dry_run=True, force=True)

    assert result["status"] == expected_status, result
    assert _repo_state(repo) == before


def test_failed_fix_preserves_untracked_files(tmp_path: Path) -> None:
    repo = _dirty_repo(tmp_path, "x=1\n")
    target = repo / "main.py"
    target.chmod(0o754)
    before = _repo_state(repo)
    mode_before = target.stat().st_mode
    secret = "sk-ant-api03-abcdef123456789012345678"

    def failed_engine(
        argv: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if "--show-files" in argv:
            return subprocess.CompletedProcess(argv, 0, stdout=f"{target}\n", stderr="")
        target.write_text("changed = True\n", encoding="utf-8")
        target.chmod(0o600)
        return subprocess.CompletedProcess(
            args=["ruff"],
            returncode=2,
            stdout="",
            stderr=f"invalid config {secret}",
        )

    with patch("rush.tools.common.run_subprocess", side_effect=failed_engine):
        result = FixTool().run(repo, permissions=WRITE_PERMISSIONS, force=True)

    assert result["status"] == "error"
    assert "invalid config" in result["summary"]
    assert secret not in str(result)
    assert "[REDACTED_ANTHROPIC_KEY]" in str(result)
    assert _repo_state(repo) == before
    assert target.stat().st_mode == mode_before


def test_fix_restores_owned_targets_on_invalid_ast(tmp_path: Path) -> None:
    repo = _dirty_repo(tmp_path, "x = 1\n")
    target = repo / "main.py"
    before = _repo_state(repo)

    def invalid_ast(
        argv: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if "--show-files" in argv:
            return subprocess.CompletedProcess(argv, 0, stdout=f"{target}\n", stderr="")
        target.write_text("def broken(:\n", encoding="utf-8")
        return subprocess.CompletedProcess(
            args=["ruff"], returncode=0, stdout="", stderr=""
        )

    with (
        patch("rush.tools.common.resolve_binary", return_value="/ruff"),
        patch("rush.tools.common.run_subprocess", side_effect=invalid_ast),
    ):
        result = FixTool().run(repo, permissions=WRITE_PERMISSIONS, force=True)

    assert result["status"] == "error"
    assert "invalid AST" in result["summary"]
    assert _repo_state(repo) == before


def test_fix_restores_owned_targets_on_cancellation(tmp_path: Path) -> None:
    repo = _dirty_repo(tmp_path, "x = 1\n")
    target = repo / "main.py"
    target.chmod(0o754)
    before = _repo_state(repo)
    mode_before = target.stat().st_mode

    def cancelled(
        argv: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if "--show-files" in argv:
            return subprocess.CompletedProcess(argv, 0, stdout=f"{target}\n", stderr="")
        target.write_text("changed = True\n", encoding="utf-8")
        target.chmod(0o600)
        raise KeyboardInterrupt

    with (
        patch("rush.tools.common.resolve_binary", return_value="/ruff"),
        patch("rush.tools.common.run_subprocess", side_effect=cancelled),
        pytest.raises(KeyboardInterrupt),
    ):
        FixTool().run(repo, permissions=WRITE_PERMISSIONS, force=True)

    assert _repo_state(repo) == before
    assert target.stat().st_mode == mode_before


def test_fix_restores_owned_targets_when_ast_validation_is_cancelled(
    tmp_path: Path,
) -> None:
    repo = _dirty_repo(tmp_path, "x = 1\n")
    target = repo / "main.py"
    before = _repo_state(repo)

    def modified(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "--show-files" in argv:
            return subprocess.CompletedProcess(argv, 0, stdout=f"{target}\n", stderr="")
        target.write_text("changed = True\n", encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    tool = FixTool()
    with (
        patch("rush.tools.common.resolve_binary", return_value="/ruff"),
        patch("rush.tools.common.run_subprocess", side_effect=modified),
        patch.object(tool, "validate_ast", side_effect=KeyboardInterrupt),
        pytest.raises(KeyboardInterrupt),
    ):
        tool.run(repo, permissions=WRITE_PERMISSIONS, force=True)

    assert _repo_state(repo) == before


def test_fix_passes_exact_python_targets_with_cache_disabled(tmp_path: Path) -> None:
    repo = _dirty_repo(tmp_path, "x = 1\n")
    package = repo / "package"
    package.mkdir()
    stub = package / "types.pyi"
    stub.write_text("value: int\n", encoding="utf-8")
    targets = [str(repo / "main.py"), str(stub)]
    calls: list[list[str]] = []

    def successful(
        argv: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        stdout = "\n".join(targets) + "\n" if "--show-files" in argv else ""
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    with (
        patch("rush.tools.common.resolve_binary", return_value="/ruff"),
        patch("rush.tools.common.run_subprocess", side_effect=successful),
    ):
        result = FixTool().run(repo, permissions=WRITE_PERMISSIONS, force=True)

    assert result["status"] == "ok"
    assert calls == [
        ["/ruff", "check", "--show-files", "--no-cache", str(repo)],
        ["/ruff", "format", "--no-cache", *targets],
        ["/ruff", "check", "--fix", "--no-cache", *targets],
    ]


def test_fix_preserves_ruff_excluded_python_files(tmp_path: Path) -> None:
    repo = _dirty_repo(tmp_path, "x = 1\n")
    excluded = repo / ".venv" / "vendor.py"
    excluded.parent.mkdir()
    excluded.write_text("def vendor( a,b ):return a+b\n", encoding="utf-8")
    before = excluded.read_bytes()

    result = FixTool().run(repo, permissions=WRITE_PERMISSIONS, force=True)

    assert result["status"] == "ok"
    assert excluded.read_bytes() == before


def test_fix_missing_ruff_is_skipped_without_launch(tmp_path: Path) -> None:
    repo = _dirty_repo(tmp_path, "def broken(:\n")
    with (
        patch("rush.tools.common.resolve_binary", return_value=None),
        patch("rush.tools.common.run_subprocess") as run,
    ):
        result = FixTool().run(repo, dry_run=True, force=True)

    assert result["status"] == "skipped"
    assert result["engine"] == "ruff"
    run.assert_not_called()


def test_fix_reports_restore_failure_and_continues_other_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _dirty_repo(tmp_path, "x = 1\n")
    first = repo / "main.py"
    second = repo / "second.py"
    second.write_text("y = 2\n", encoding="utf-8")
    original_write_bytes = Path.write_bytes

    def failed_engine(
        argv: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if "--show-files" in argv:
            return subprocess.CompletedProcess(
                argv, 0, stdout=f"{first}\n{second}\n", stderr=""
            )
        first.write_text("changed = 1\n", encoding="utf-8")
        second.write_text("changed = 2\n", encoding="utf-8")
        return subprocess.CompletedProcess(["ruff"], 2, stdout="", stderr="bad config")

    def fail_first(path: Path, data: bytes) -> int:
        if path == first:
            raise OSError("read-only filesystem")
        return original_write_bytes(path, data)

    monkeypatch.setattr(Path, "write_bytes", fail_first)
    with patch("rush.tools.common.run_subprocess", side_effect=failed_engine):
        result = FixTool().run(repo, permissions=WRITE_PERMISSIONS, force=True)

    assert result["status"] == "error"
    assert "rollback failed" in result["summary"]
    assert str(first) in result["summary"]
    assert "read-only filesystem" in result["summary"]
    assert second.read_bytes() == b"y = 2\n"


def test_fix_apply_requires_artifact_write_before_ruff_launch(
    temp_git_repo: Path,
) -> None:
    with (
        patch("rush.tools.common.resolve_binary") as resolve,
        patch("rush.tools.common.run_subprocess") as run,
    ):
        result = FixTool().run(
            temp_git_repo, permissions=ExecutionPermissions(), force=True
        )

    assert result["status"] == "skipped"
    assert "--allow-artifact-write" in result["summary"]
    resolve.assert_not_called()
    run.assert_not_called()


@pytest.mark.parametrize("failure_call", [1, 2])
def test_fix_sanitizes_subprocess_exceptions(tmp_path: Path, failure_call: int) -> None:
    repo = _dirty_repo(tmp_path, "x = 1\n")
    target = repo / "main.py"
    secret = "sk-ant-api03-abcdef123456789012345678"
    calls = 0

    def raises(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        if calls == failure_call:
            raise OSError(f"engine failed with {secret}")
        return subprocess.CompletedProcess(argv, 0, stdout=f"{target}\n", stderr="")

    with (
        patch("rush.tools.common.resolve_binary", return_value="/ruff"),
        patch("rush.tools.common.run_subprocess", side_effect=raises),
    ):
        result = FixTool().run(repo, dry_run=True, force=True)

    assert result["status"] == "error"
    assert secret not in str(result)
    assert "[REDACTED_ANTHROPIC_KEY]" in result["summary"]


def test_fix_restores_target_deleted_by_engine(tmp_path: Path) -> None:
    repo = _dirty_repo(tmp_path, "x = 1\n")
    target = repo / "main.py"
    before = target.read_bytes()

    def deletes_target(
        argv: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if "--show-files" in argv:
            return subprocess.CompletedProcess(argv, 0, stdout=f"{target}\n", stderr="")
        target.unlink(missing_ok=True)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    with patch("rush.tools.common.run_subprocess", side_effect=deletes_target):
        result = FixTool().run(repo, permissions=WRITE_PERMISSIONS, force=True)

    assert result["status"] == "error"
    assert "missing" in result["summary"]
    assert target.read_bytes() == before


def test_fix_refuses_dangling_symlink_during_rollback(tmp_path: Path) -> None:
    repo = _dirty_repo(tmp_path, "x = 1\n")
    target = repo / "main.py"
    outside = tmp_path / "outside.py"

    def replaces_with_symlink(
        argv: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if "--show-files" in argv:
            return subprocess.CompletedProcess(argv, 0, stdout=f"{target}\n", stderr="")
        target.unlink(missing_ok=True)
        target.symlink_to(outside)
        return subprocess.CompletedProcess(argv, 2, stdout="", stderr="engine failed")

    with patch("rush.tools.common.run_subprocess", side_effect=replaces_with_symlink):
        result = FixTool().run(repo, permissions=WRITE_PERMISSIONS, force=True)

    assert result["status"] == "error"
    assert "rollback failed" in result["summary"]
    assert "symbolic link" in result["summary"]
    assert not outside.exists()


def test_fix_refuses_parent_symlink_redirection_during_rollback(
    tmp_path: Path,
) -> None:
    repo = _dirty_repo(tmp_path, "x = 1\n")
    package = repo / "package"
    package.mkdir()
    target = package / "code.py"
    target.write_text("value = 1\n", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()

    def redirects_parent(
        argv: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if "--show-files" in argv:
            return subprocess.CompletedProcess(argv, 0, stdout=f"{target}\n", stderr="")
        package.rename(repo / "package-original")
        package.symlink_to(outside, target_is_directory=True)
        return subprocess.CompletedProcess(argv, 2, stdout="", stderr="engine failed")

    with patch("rush.tools.common.run_subprocess", side_effect=redirects_parent):
        result = FixTool().run(repo, permissions=WRITE_PERMISSIONS, force=True)

    assert result["status"] == "error"
    assert "rollback failed" in result["summary"]
    assert "redirect" in result["summary"]
    assert not (outside / "code.py").exists()


@pytest.mark.parametrize("replacement", ["missing", "directory"])
def test_fix_rejects_incomplete_snapshot_before_mutating_launch(
    tmp_path: Path, replacement: str
) -> None:
    repo = _dirty_repo(tmp_path, "x = 1\n")
    target = repo / "main.py"
    calls = 0

    def target_disappears(
        argv: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        if calls == 1:
            target.unlink()
            if replacement == "directory":
                target.mkdir()
            return subprocess.CompletedProcess(argv, 0, stdout=f"{target}\n", stderr="")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    with patch("rush.tools.common.run_subprocess", side_effect=target_disappears):
        result = FixTool().run(repo, permissions=WRITE_PERMISSIONS, force=True)

    assert result["status"] == "error"
    assert "snapshot" in result["summary"]
    assert calls == 1


def test_fix_restores_after_unexpected_validation_exception(tmp_path: Path) -> None:
    repo = _dirty_repo(tmp_path, "x = 1\n")
    target = repo / "main.py"
    before = _repo_state(repo)
    secret = "sk-ant-api03-abcdef123456789012345678"

    def modifies(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "--show-files" in argv:
            return subprocess.CompletedProcess(argv, 0, stdout=f"{target}\n", stderr="")
        target.write_text("changed = True\n", encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    tool = FixTool()
    with (
        patch("rush.tools.common.run_subprocess", side_effect=modifies),
        patch.object(tool, "validate_ast", side_effect=RuntimeError(secret)),
    ):
        result = tool.run(repo, permissions=WRITE_PERMISSIONS, force=True)

    assert result["status"] == "error"
    assert secret not in str(result)
    assert "[REDACTED_ANTHROPIC_KEY]" in result["summary"]
    assert _repo_state(repo) == before


@pytest.mark.parametrize(
    "git_failure",
    [
        subprocess.CompletedProcess(["git"], 128, stdout="", stderr="fatal"),
        OSError("git unavailable"),
    ],
)
def test_fix_git_status_failure_stops_before_ruff(
    temp_git_repo: Path, git_failure: object
) -> None:
    status = (
        patch("rush.tools.fix.subprocess.run", side_effect=git_failure)
        if isinstance(git_failure, BaseException)
        else patch("rush.tools.fix.subprocess.run", return_value=git_failure)
    )
    with (
        status,
        patch("rush.tools.common.resolve_binary") as resolve,
        patch("rush.tools.common.run_subprocess") as run,
    ):
        result = FixTool().run(
            temp_git_repo, permissions=WRITE_PERMISSIONS, force=False
        )

    assert result["status"] == "error"
    assert "Git status" in result["summary"]
    resolve.assert_not_called()
    run.assert_not_called()


def test_registered_mcp_fix_apply_denies_and_grants_artifact_write(
    tmp_path: Path,
) -> None:
    repo = _dirty_repo(tmp_path, "x = 1\n")
    target = repo / "main.py"
    registered: dict[str, object] = {}

    class Server:
        def add_tool(self, *, fn: object, name: str, description: str) -> None:
            registered[name] = fn

    calls: list[list[str]] = []

    def successful(
        argv: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        stdout = f"{target}\n" if "--show-files" in argv else ""
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    register_all_tools(Server(), InvocationExecutor(), [FixTool()])
    wrapper = registered["rush_fix"]
    assert callable(wrapper)
    permission = inspect.signature(wrapper).parameters["allow_artifact_write"]
    assert permission.default is False
    with (
        patch("rush.tools.common.resolve_binary", return_value=Path("/ruff")),
        patch("rush.tools.common.run_subprocess", side_effect=successful),
    ):
        denied = wrapper(path=repo, force=True)
        granted = wrapper(path=repo, force=True, allow_artifact_write=True)

    assert denied["status"] == "skipped"
    assert granted["status"] == "ok"
    assert calls == [
        [Path("/ruff"), "check", "--show-files", "--no-cache", str(repo)],
        [Path("/ruff"), "format", "--no-cache", str(target)],
        [Path("/ruff"), "check", "--fix", "--no-cache", str(target)],
    ]


def test_fix_cli_and_direct_dry_run_preserve_same_dirty_fixture(tmp_path: Path) -> None:
    repo = _dirty_repo(tmp_path, "def add( a,b ):return a+b\n")
    before = _repo_state(repo)

    direct = FixTool().run(repo, dry_run=True, force=True)
    cli_result = CliRunner().invoke(
        cli, ["fix", str(repo), "--dry-run", "--force", "--json"]
    )
    cli_payload = json.loads(cli_result.output)

    assert direct["status"] == "warn"
    assert cli_result.exit_code == 1
    assert cli_payload["status"] == direct["status"]
    assert _repo_state(repo) == before


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
