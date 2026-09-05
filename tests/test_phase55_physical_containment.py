from __future__ import annotations

import os
import stat
from pathlib import Path

try:
    import _winapi
except ImportError:
    _winapi = None  # type: ignore[assignment]

import pytest

from rush.io.physical_paths import ContainmentError, PhysicalRoot


def test_file_and_directory_links_cannot_escape_root(tmp_path: Path) -> None:
    """T-55.06: Verify symlinks pointing outside physical root are rejected fail-closed."""
    outside_dir = tmp_path / "outside_jail"
    outside_dir.mkdir()
    outside_file = outside_dir / "secret_document.txt"
    outside_file.write_text("SENSITIVE_OUTSIDE_CONTENT", encoding="utf-8")

    outside_nested = outside_dir / "nested_dir"
    outside_nested.mkdir()
    outside_nested_file = outside_nested / "confidential.txt"
    outside_nested_file.write_text("CONFIDENTIAL_NESTED_DATA", encoding="utf-8")

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    # Create file symlink pointing outside
    file_symlink = workspace_root / "link_to_file.txt"
    os.symlink(outside_file, file_symlink)

    # Create directory symlink pointing outside
    dir_symlink = workspace_root / "link_to_dir"
    os.symlink(outside_nested, dir_symlink, target_is_directory=True)

    # Create nested directory containing symlink to outside
    inner_dir = workspace_root / "inner"
    inner_dir.mkdir()
    nested_symlink = inner_dir / "escape_link"
    os.symlink(outside_dir, nested_symlink, target_is_directory=True)

    root = PhysicalRoot(workspace_root)

    # 1. File symlink read attempt must fail-closed
    with pytest.raises(ContainmentError) as exc_read_file:
        root.open_contained("link_to_file.txt", purpose="read")
    assert exc_read_file.value.code == "SYMLINK_DISALLOWED"
    assert "link_to_file.txt" in exc_read_file.value.path

    # 2. File symlink write attempt must fail-closed
    with pytest.raises(ContainmentError) as exc_write_file:
        root.open_contained("link_to_file.txt", purpose="write")
    assert exc_write_file.value.code == "SYMLINK_DISALLOWED"

    # 3. Directory symlink traversal read attempt must fail-closed
    with pytest.raises(ContainmentError) as exc_read_dir:
        root.open_contained("link_to_dir/confidential.txt", purpose="read")
    assert exc_read_dir.value.code == "SYMLINK_DISALLOWED"

    # 4. Directory symlink traversal write attempt must fail-closed
    with pytest.raises(ContainmentError) as exc_write_dir:
        root.open_contained("link_to_dir/new_exploit.txt", purpose="write")
    assert exc_write_dir.value.code == "SYMLINK_DISALLOWED"

    # 5. Nested intermediate component symlink must fail-closed
    with pytest.raises(ContainmentError) as exc_nested:
        root.open_contained("inner/escape_link/secret_document.txt", purpose="read")
    assert exc_nested.value.code == "SYMLINK_DISALLOWED"

    # 6. Verify outside files remain completely untouched
    assert outside_file.read_text(encoding="utf-8") == "SENSITIVE_OUTSIDE_CONTENT"
    assert outside_nested_file.read_text(encoding="utf-8") == "CONFIDENTIAL_NESTED_DATA"
    assert not (outside_dir / "new_exploit.txt").exists()
    assert not (outside_nested / "new_exploit.txt").exists()


def test_junction_reparse_and_parent_target_swaps_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-55.07: Verify Windows junctions, reparse points, and parent target swap races fail-closed."""
    outside_dir = tmp_path / "outside_jail"
    outside_dir.mkdir()
    outside_target = outside_dir / "target_folder"
    outside_target.mkdir()
    target_file = outside_target / "target.txt"
    target_file.write_text("TARGET_DOCUMENT_BODY", encoding="utf-8")

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    root = PhysicalRoot(workspace_root)

    # 1. Real Windows directory junction point (if supported on platform)
    if _winapi is not None and hasattr(_winapi, "CreateJunction"):
        junction_path = workspace_root / "junction_escape"
        _winapi.CreateJunction(str(outside_target), str(junction_path))

        with pytest.raises(ContainmentError) as exc_junc_read:
            root.open_contained("junction_escape/target.txt", purpose="read")
        assert exc_junc_read.value.code == "REPARSE_POINT_DISALLOWED"

        with pytest.raises(ContainmentError) as exc_junc_write:
            root.open_contained("junction_escape/malicious.txt", purpose="write")
        assert exc_junc_write.value.code == "REPARSE_POINT_DISALLOWED"

    # 2. Simulated stat.FILE_ATTRIBUTE_REPARSE_POINT attribute check
    simulated_dir = workspace_root / "simulated_junction"
    simulated_dir.mkdir()
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    orig_lstat = os.lstat

    class MockStatResult:
        def __init__(self, orig: os.stat_result) -> None:
            self._orig = orig
            self.st_file_attributes = (
                getattr(orig, "st_file_attributes", 0) | reparse_flag
            )
            self.st_mode = orig.st_mode

        def __getattr__(self, name: str) -> object:
            return getattr(self._orig, name)

    def mock_lstat(
        path: os.PathLike[str] | str, *args: object, **kwargs: object
    ) -> object:
        st = orig_lstat(path, *args, **kwargs)
        if Path(path) == simulated_dir:
            return MockStatResult(st)
        return st

    monkeypatch.setattr(os, "lstat", mock_lstat)
    with pytest.raises(ContainmentError) as exc_reparse:
        root.open_contained("simulated_junction/child.txt", purpose="read")
    assert exc_reparse.value.code == "REPARSE_POINT_DISALLOWED"
    monkeypatch.undo()

    # 3. Parent target swap race condition simulation (candidate resolves outside root)
    def fake_resolve(self: Path, *args: object, **kwargs: object) -> Path:
        return outside_target / "swapped_target.txt"

    monkeypatch.setattr(Path, "resolve", fake_resolve)
    with pytest.raises(ContainmentError) as exc_swap:
        root.open_contained("regular_dir/swapped_target.txt", purpose="read")
    assert exc_swap.value.code == "PATH_ESCAPE_DISALLOWED"
    monkeypatch.undo()

    # 4. Outside target must remain unaltered
    assert target_file.read_text(encoding="utf-8") == "TARGET_DOCUMENT_BODY"
    assert not (outside_target / "malicious.txt").exists()
    assert not (outside_target / "swapped_target.txt").exists()


def test_unsupported_capability_writes_nothing(tmp_path: Path) -> None:
    """T-55.08: Verify invalid, escaping, or traversal paths fail-closed with zero writes."""
    outside_dir = tmp_path / "outside_jail"
    outside_dir.mkdir()
    sentinel = outside_dir / "sentinel.txt"
    sentinel.write_text("OUTSIDE_UNMODIFIED_CONTENT", encoding="utf-8")

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    import rush.io

    assert rush.io.PhysicalRoot is PhysicalRoot
    assert rush.io.ContainmentError is ContainmentError

    root = PhysicalRoot(workspace_root)

    outside_before = list(outside_dir.rglob("*"))
    workspace_before = list(workspace_root.rglob("*"))

    disallowed_constructs = [
        ("/etc/passwd", "ABSOLUTE_PATH_DISALLOWED"),
        ("\\Windows\\System32\\calc.exe", "ABSOLUTE_PATH_DISALLOWED"),
        ("C:/Windows/System32/drivers/etc/hosts", "ABSOLUTE_PATH_DISALLOWED"),
        ("D:\\escape.txt", "ABSOLUTE_PATH_DISALLOWED"),
        ("C:drive_relative.txt", "ABSOLUTE_PATH_DISALLOWED"),
        ("../outside_jail/attack.txt", "PARENT_TRAVERSAL_DISALLOWED"),
        ("sub/../../outside_jail/attack.txt", "PARENT_TRAVERSAL_DISALLOWED"),
        ("a/b/../../../c", "PARENT_TRAVERSAL_DISALLOWED"),
    ]

    for path_str, expected_code in disallowed_constructs:
        with pytest.raises(ContainmentError) as exc_info:
            root.open_contained(path_str, purpose="write")
        assert exc_info.value.code == expected_code, f"Failed for path '{path_str}'"

    # Root validation checks
    with pytest.raises(ValueError, match="does not exist"):
        PhysicalRoot(tmp_path / "nonexistent_root")

    not_a_dir = tmp_path / "not_a_dir.txt"
    not_a_dir.write_text("plain file", encoding="utf-8")
    with pytest.raises(ValueError, match="not a directory"):
        PhysicalRoot(not_a_dir)

    # Valid candidate check: open_contained returns candidate path without writing anything
    valid_candidate = root.open_contained(
        "deep/nested/path/target.txt", purpose="write"
    )
    assert valid_candidate == workspace_root / "deep/nested/path/target.txt"
    assert not valid_candidate.exists()
    assert not (workspace_root / "deep").exists()

    # Zero bytes or directories written outside or inside workspace root
    assert list(outside_dir.rglob("*")) == outside_before
    assert sentinel.read_text(encoding="utf-8") == "OUTSIDE_UNMODIFIED_CONTENT"
    assert list(workspace_root.rglob("*")) == workspace_before
