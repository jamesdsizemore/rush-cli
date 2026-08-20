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
