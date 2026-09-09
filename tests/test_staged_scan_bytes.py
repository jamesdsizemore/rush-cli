"""Index-byte regressions for staged hook checks."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from pytest import MonkeyPatch

from rush.hook.ast_linter import FastIncrementalAstLinter
from rush.hook.conflict_guard import ConflictMarkerGuard
from rush.hook.staged_scanner import StagedFileScanner
from rush.hook.trojan_source import TrojanSourceDetector


def _git(root: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        input=input_bytes,
        capture_output=True,
        check=True,
    ).stdout


def _repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "staged@example.invalid")
    _git(tmp_path, "config", "user.name", "Staged Bytes")
    (tmp_path / "sample.py").write_bytes(b"value = 1\n")
    (tmp_path / "with space.txt").write_bytes(b"clean\n")
    (tmp_path / "deleted.py").write_bytes(b"value = 2\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "fixture")
    return tmp_path


def _state(root: Path) -> tuple[bytes, bytes, bytes, bytes]:
    status = _git(root, "status", "--porcelain=v1", "-z")
    return (
        _git(root, "diff", "--cached", "--binary"),
        status,
        _git(root, "rev-parse", "HEAD"),
        (root / ".git" / "index").read_bytes(),
    )


def test_staged_content_guards_use_selected_bytes(tmp_path: Path) -> None:
    worktree_file = tmp_path / "guarded.txt"
    worktree_file.write_bytes(b"clean worktree\n")
    selected = b"<<<<<<< ours\n=======\n>>>>>>> theirs\n# \xe2\x80\xae\n"

    assert ConflictMarkerGuard.inspect_content(worktree_file, selected)
    assert TrojanSourceDetector.inspect_content(worktree_file, selected)
    assert worktree_file.read_bytes() == b"clean worktree\n"


def test_staged_invalid_python_ignores_repaired_worktree(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    source = root / "sample.py"
    source.write_bytes(b"def broken(:\n")
    _git(root, "add", "sample.py")
    source.write_bytes(b"value = 3\n")
    before = _state(root)

    entries = StagedFileScanner(root).get_staged_entries()

    assert [(entry.relative_path.as_posix(), entry.content) for entry in entries] == [
        ("sample.py", b"def broken(:\n")
    ]
    assert FastIncrementalAstLinter.lint_staged_entries(entries) == [
        "sample.py:1:12: SyntaxError: invalid syntax"
    ]
    assert source.read_bytes() == b"value = 3\n"
    assert _state(root) == before


def test_staged_valid_python_ignores_invalid_worktree(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    source = root / "sample.py"
    source.write_bytes(b"value = 4\n")
    _git(root, "add", "sample.py")
    source.write_bytes(b"def broken(:\n")
    before = _state(root)

    entries = StagedFileScanner(root).get_staged_entries()

    assert entries[0].content == b"value = 4\n"
    assert FastIncrementalAstLinter.lint_staged_entries(entries) == []
    assert source.read_bytes() == b"def broken(:\n"
    assert _state(root) == before


def test_staged_checks_share_index_bytes_and_record_deleted_path(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    guarded = root / "with space.txt"
    guarded.write_bytes(
        "<<<<<<< ours\nclean = True\n=======\nclean = False\n>>>>>>> theirs\n# \u202e\n".encode()
    )
    _git(root, "add", "with space.txt")
    guarded.write_bytes(b"worktree is clean\n")
    _git(root, "rm", "-q", "deleted.py")
    deleted_worktree = root / "deleted.py"
    deleted_worktree.write_bytes(b"<<<<<<< worktree-only\n")
    before = _state(root)

    calls: list[tuple[str, ...]] = []
    original_git = StagedFileScanner._git

    def record_git(scanner: StagedFileScanner, args: list[str]):
        calls.append(tuple(args))
        return original_git(scanner, args)

    monkeypatch.setattr(StagedFileScanner, "_git", record_git)
    entries = StagedFileScanner(root).get_staged_entries()
    by_path = {entry.relative_path.as_posix(): entry for entry in entries}
    staged = by_path["with space.txt"]
    deleted = by_path["deleted.py"]

    assert staged.status == "staged"
    assert staged.content is not None
    assert len(ConflictMarkerGuard.inspect_content(staged.path, staged.content)) == 3
    assert len(TrojanSourceDetector.inspect_content(staged.path, staged.content)) == 1
    assert deleted.status == "deleted"
    assert deleted.content is None
    assert [call for call in calls if call[0] == "show"] == [
        ("show", "--no-textconv", ":with space.txt")
    ]
    assert deleted_worktree.read_bytes() == b"<<<<<<< worktree-only\n"
    assert _state(root) == before


def test_staged_unmerged_index_reports_stage_identities(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    source = root / "sample.py"
    before = _git(root, "rev-parse", "HEAD")
    object_ids = [
        _git(root, "hash-object", "-w", "--stdin", input_bytes=value).strip().decode()
        for value in (b"base\n", b"ours\n", b"theirs\n")
    ]
    index_info = "".join(
        f"100644 {object_id} {stage}\tsample.py\n"
        for stage, object_id in enumerate(object_ids, start=1)
    ).encode()
    _git(root, "update-index", "--force-remove", "sample.py")
    _git(root, "update-index", "--index-info", input_bytes=index_info)
    source.write_bytes(b"worktree substitute\n")
    state = _state(root)

    calls: list[tuple[str, ...]] = []
    original_git = StagedFileScanner._git

    def record_git(scanner: StagedFileScanner, args: list[str]):
        calls.append(tuple(args))
        return original_git(scanner, args)

    monkeypatch.setattr(StagedFileScanner, "_git", record_git)
    entries = StagedFileScanner(root).get_staged_entries()

    assert len(entries) == 1
    entry = entries[0]
    assert entry.status == "unmerged_index"
    assert entry.content is None
    assert [(stage.stage, stage.mode, stage.object_id) for stage in entry.stages] == [
        (1, "100644", object_ids[0]),
        (2, "100644", object_ids[1]),
        (3, "100644", object_ids[2]),
    ]
    assert source.read_bytes() == b"worktree substitute\n"
    assert [call for call in calls if call[0] == "show"] == []
    assert _state(root) == state
    assert _git(root, "rev-parse", "HEAD") == before


def test_staged_typechange_scans_index_blob_not_worktree(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    source = root / "sample.py"
    selected = b"def broken(:\n"
    object_id = _git(root, "hash-object", "-w", "--stdin", input_bytes=selected).strip()
    _git(
        root,
        "update-index",
        "--cacheinfo",
        "120000",
        object_id.decode(),
        "sample.py",
    )
    before = _state(root)

    entries = StagedFileScanner(root).get_staged_entries()

    assert len(entries) == 1
    assert entries[0].content == selected
    assert entries[0].stages[0].mode == "120000"
    assert FastIncrementalAstLinter.lint_staged_entries(entries) == [
        "sample.py:1:12: SyntaxError: invalid syntax"
    ]
    assert source.read_bytes() == b"value = 1\n"
    assert _state(root) == before


@pytest.mark.parametrize(
    "failure",
    [OSError("git unavailable"), subprocess.TimeoutExpired(["git"], timeout=30)],
)
def test_staged_git_process_failure_is_explicit(
    tmp_path: Path, monkeypatch: MonkeyPatch, failure: BaseException
) -> None:
    root = _repo(tmp_path)

    def fail_run(*args: object, **kwargs: object) -> None:
        raise failure

    monkeypatch.setattr(subprocess, "run", fail_run)

    with pytest.raises(RuntimeError, match="git staged-index command failed"):
        StagedFileScanner(root).get_staged_entries()
