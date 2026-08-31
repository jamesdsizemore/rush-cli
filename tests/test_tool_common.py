"""Tests for shared tool primitives (containment, atomic writes)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def test_resolve_contained_output_rejects_absolute_parent_and_symlink(
    tmp_path: Path,
) -> None:
    from rush.tools.common import resolve_contained_output

    root = tmp_path / "root"
    root.mkdir()
    nested = root / "subdir" / "out.txt"

    # Valid relative
    res = resolve_contained_output(root, "subdir/out.txt")
    assert res == nested.resolve()

    # Absolute path
    with pytest.raises(ValueError, match="absolute"):
        resolve_contained_output(root, "/outside.txt")

    # Parent traversal
    with pytest.raises(ValueError, match="travers"):
        resolve_contained_output(root, "../outside.txt")

    # Symlink target if supported
    outside = tmp_path / "outside.txt"
    outside.write_text("leak", encoding="utf-8")
    link = root / "link.txt"
    try:
        link.symlink_to(outside)
        with pytest.raises(ValueError, match="symlink"):
            resolve_contained_output(root, "link.txt")
    except (OSError, NotImplementedError):
        pass


def test_atomic_write_replaces_only_contained_target_and_is_deterministic(
    tmp_path: Path,
) -> None:
    from rush.tools.common import atomic_write_bytes

    root = tmp_path / "root"
    root.mkdir()
    target_rel = "nested/artifact.json"
    data = b'{"hello": "world"}'

    written = atomic_write_bytes(root, target_rel, data)
    assert written.is_file()
    assert written.read_bytes() == data

    # Overwrite deterministically
    new_data = b'{"hello": "updated"}'
    written2 = atomic_write_bytes(root, target_rel, new_data)
    assert written2 == written
    assert written2.read_bytes() == new_data

    # Ensure no temporary files left in the directory
    parent_files = list(written.parent.iterdir())
    assert parent_files == [written]


def test_atomic_write_preserves_existing_target_and_removes_temp_on_failure(
    tmp_path: Path, monkeypatch
) -> None:
    from rush.tools.common import atomic_write_bytes

    root = tmp_path / "root"
    root.mkdir()
    target_rel = "out.txt"
    initial_data = b"initial content"

    written = atomic_write_bytes(root, target_rel, initial_data)
    assert written.read_bytes() == initial_data

    # Injected replace failure
    def fake_replace(src, dst):
        raise OSError("disk error on replace")

    monkeypatch.setattr(os, "replace", fake_replace)

    with pytest.raises(OSError, match="disk error"):
        atomic_write_bytes(root, target_rel, b"corrupted data")

    # Old content is preserved
    assert written.read_bytes() == initial_data

    # No leftover temp files in root
    files = list(root.iterdir())
    assert files == [written]


def test_atomic_write_rejects_intermediate_symlink_without_creating_a_target(
    tmp_path: Path,
) -> None:
    from rush.tools.common import atomic_write_bytes

    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "redirect"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable on this platform")

    with pytest.raises(ValueError, match="symlink"):
        atomic_write_bytes(root, "redirect/output.json", b"must not escape")
    assert not (outside / "output.json").exists()
