"""Tests for Phase 29: Patch Confinement & Remediation (Control 7).

Verifies:
- Generating unified diff patches from suggested fixes
- Blocking patches targeting paths outside the workspace boundary
- Protecting sensitive repository files (.git/, .env, .rush/)
- Atomically applying patches to target files
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rush.patch_generator import apply_unified_patch, generate_unified_diff


def test_generate_unified_diff() -> None:
    original = "def foo():\n    return 1\n"
    modified = "def foo():\n    return 2\n"
    diff = generate_unified_diff(original, modified, file_path="src/foo.py")

    assert "--- a/src/foo.py" in diff
    assert "+++ b/src/foo.py" in diff
    assert "+    return 2" in diff


def test_apply_unified_patch_success(tmp_path: Path) -> None:
    target_file = tmp_path / "app.py"
    target_file.write_text("a = 1\nb = 2\n", encoding="utf-8")

    diff = generate_unified_diff(
        "a = 1\nb = 2\n", "a = 1\nb = 42\n", file_path="app.py"
    )
    success = apply_unified_patch(diff, repo_root=tmp_path)
    assert success is True
    assert target_file.read_text(encoding="utf-8") == "a = 1\nb = 42\n"


def test_apply_patch_rejects_path_traversal(tmp_path: Path) -> None:
    malicious_diff = """--- a/../../secret.txt
+++ b/../../secret.txt
@@ -1,1 +1,1 @@
-original
+hacked
"""
    with pytest.raises(ValueError, match="resolves outside repository root"):
        apply_unified_patch(malicious_diff, repo_root=tmp_path)


def test_apply_patch_protects_git_directory(tmp_path: Path) -> None:
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    git_config = git_dir / "config"
    git_config.write_text("[core]\n", encoding="utf-8")

    git_diff = """--- a/.git/config
+++ b/.git/config
@@ -1,1 +1,1 @@
-[core]
+[core]\nhacked = true
"""
    with pytest.raises(ValueError, match="Protected system file"):
        apply_unified_patch(git_diff, repo_root=tmp_path)


def test_apply_patch_preserves_twenty_line_prefix_and_suffix(tmp_path: Path) -> None:
    target = tmp_path / "module.py"
    original = "".join(f"line {number}\n" for number in range(1, 21))
    modified = original.replace("line 10\n", "middle replacement\n")
    target.write_text(original, encoding="utf-8")

    assert apply_unified_patch(
        generate_unified_diff(original, modified, "module.py"), tmp_path
    )
    assert target.read_text(encoding="utf-8") == modified
    assert target.read_text(encoding="utf-8").splitlines()[0] == "line 1"
    assert target.read_text(encoding="utf-8").splitlines()[-1] == "line 20"


def test_apply_patch_applies_complete_multiple_hunks(tmp_path: Path) -> None:
    target = tmp_path / "module.py"
    original = "".join(f"line {number}\n" for number in range(1, 31))
    modified = original.replace("line 4\n", "first replacement\n").replace(
        "line 25\n", "second replacement\n"
    )
    target.write_text(original, encoding="utf-8")
    patch = generate_unified_diff(original, modified, "module.py")

    assert patch.count("@@") == 4
    assert apply_unified_patch(patch, tmp_path)
    assert target.read_text(encoding="utf-8") == modified


def test_apply_patch_context_mismatch_is_atomic(tmp_path: Path) -> None:
    target = tmp_path / "module.py"
    original = "one\ntwo\nthree\n"
    target.write_text("one\nchanged outside patch\nthree\n", encoding="utf-8")
    patch = generate_unified_diff(
        original, "one\ntwo replacement\nthree\n", "module.py"
    )
    before = target.read_bytes()

    assert apply_unified_patch(patch, tmp_path) is False
    assert target.read_bytes() == before


def test_apply_patch_zero_count_insertion_follows_declared_old_line(
    tmp_path: Path,
) -> None:
    target = tmp_path / "module.py"
    target.write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
    patch = """--- a/module.py
+++ b/module.py
@@ -3,0 +4,1 @@
+inserted
"""

    assert apply_unified_patch(patch, tmp_path)
    assert target.read_text(encoding="utf-8") == "one\ntwo\nthree\ninserted\nfour\n"


def test_apply_patch_zero_count_deletion_uses_declared_new_coordinate(
    tmp_path: Path,
) -> None:
    target = tmp_path / "module.py"
    target.write_text("one\ntwo\nthree\n", encoding="utf-8")
    patch = """--- a/module.py
+++ b/module.py
@@ -2,1 +1,0 @@
-two
"""

    assert apply_unified_patch(patch, tmp_path)
    assert target.read_text(encoding="utf-8") == "one\nthree\n"


def test_apply_patch_counts_disambiguate_header_like_hunk_content(
    tmp_path: Path,
) -> None:
    target = tmp_path / "module.py"
    target.write_text("-- old\n", encoding="utf-8")
    patch = """--- a/module.py
+++ b/module.py
@@ -1,1 +1,1 @@
--- old
+++ new
"""

    assert apply_unified_patch(patch, tmp_path)
    assert target.read_text(encoding="utf-8") == "++ new\n"


def test_apply_patch_preserves_mode_and_crlf_bytes(tmp_path: Path) -> None:
    target = tmp_path / "module.py"
    original = "one\r\ntwo\r\n"
    modified = "one\r\nreplacement\r\n"
    target.write_bytes(original.encode("utf-8"))
    target.chmod(0o640)

    assert apply_unified_patch(
        generate_unified_diff(original, modified, "module.py"), tmp_path
    )
    assert target.read_bytes() == modified.encode("utf-8")
    assert target.stat().st_mode & 0o777 == 0o640


def test_apply_patch_rejects_hunk_count_overshoot_without_write(tmp_path: Path) -> None:
    target = tmp_path / "module.py"
    target.write_text("one\ntwo\n", encoding="utf-8")
    patch = """--- a/module.py
+++ b/module.py
@@ -1,1 +1,2 @@
 one
 two
"""
    before = target.read_bytes()

    assert apply_unified_patch(patch, tmp_path) is False
    assert target.read_bytes() == before


def test_apply_patch_preserves_missing_final_newline(tmp_path: Path) -> None:
    target = tmp_path / "module.py"
    original = "alpha\nbeta"
    modified = "alpha\nBETA"
    target.write_text(original, encoding="utf-8")

    assert apply_unified_patch(
        generate_unified_diff(original, modified, "module.py"), tmp_path
    )
    assert target.read_text(encoding="utf-8") == modified


@pytest.mark.parametrize(
    "patch",
    [
        "--- a/module.py\n+++ b/module.py\n@@ malformed\n+replacement\n",
        "diff --git a/module.py b/module.py\nBinary files a/module.py and b/module.py differ\n",
    ],
)
def test_apply_patch_rejects_malformed_or_binary_without_write(
    tmp_path: Path, patch: str
) -> None:
    target = tmp_path / "module.py"
    target.write_text("original\\n", encoding="utf-8")
    before = target.read_bytes()

    assert apply_unified_patch(patch, tmp_path) is False
    assert target.read_bytes() == before


def test_apply_patch_accepts_git_metadata_and_deleted_dash_content(
    tmp_path: Path,
) -> None:
    target = tmp_path / "module.py"
    target.write_text("keep\n-- obsolete\nsuffix\n", encoding="utf-8")
    patch = """diff --git a/module.py b/module.py
index 1111111..2222222 100644
--- a/module.py
+++ b/module.py
@@ -1,3 +1,2 @@
 keep
--- obsolete
 suffix
"""

    assert apply_unified_patch(patch, tmp_path)
    assert target.read_text(encoding="utf-8") == "keep\nsuffix\n"


def test_apply_patch_rejects_bad_new_coordinate_without_write(tmp_path: Path) -> None:
    target = tmp_path / "module.py"
    target.write_text("one\ntwo\n", encoding="utf-8")
    patch = """--- a/module.py
+++ b/module.py
@@ -1,2 +7,2 @@
 one
-two
+replacement
"""
    before = target.read_bytes()

    assert apply_unified_patch(patch, tmp_path) is False
    assert target.read_bytes() == before


def test_apply_patch_rejects_duplicate_file_sections_without_write(
    tmp_path: Path,
) -> None:
    target = tmp_path / "module.py"
    target.write_text("one\ntwo\n", encoding="utf-8")
    patch = """--- a/module.py
+++ b/module.py
@@ -1,2 +1,2 @@
 one
-two
+first
--- a/module.py
+++ b/module.py
@@ -1,2 +1,2 @@
 one
-two
+second
"""
    before = target.read_bytes()

    assert apply_unified_patch(patch, tmp_path) is False
    assert target.read_bytes() == before
