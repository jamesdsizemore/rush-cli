"""Tests for Phase 29: Isolated AI Patch Remediation and Memory."""

from __future__ import annotations

import pytest
from pathlib import Path

from rush.patch.circuit_breaker import RemediationCircuitBreaker
from rush.patch.diff_parser import UnifiedDiffParser
from rush.patch.memory import PatchMemoryStore
from rush.patch.syntax_guard import PatchSyntaxGuard


def test_unified_diff_parser(tmp_path: Path) -> None:
    diff_text = """--- a/src/app.py
+++ b/src/app.py
@@ -1,3 +1,3 @@
-x = 1
+x = 2
"""
    patches = UnifiedDiffParser.parse_patch(diff_text, tmp_path)
    assert len(patches) == 1
    assert patches[0].new_path == "src/app.py"


def test_unified_diff_parser_rejects_governance_files(tmp_path: Path) -> None:
    diff_text = """--- a/AGENTS.md
+++ b/AGENTS.md
@@ -1,1 +1,1 @@
-old
+new
"""
    with pytest.raises(PermissionError, match="governance file"):
        UnifiedDiffParser.parse_patch(diff_text, tmp_path)


def test_unified_diff_parser_rejects_path_traversal(tmp_path: Path) -> None:
    diff_text = """--- a/../../etc/passwd
+++ b/../../etc/passwd
@@ -1,1 +1,1 @@
-old
+new
"""
    with pytest.raises(ValueError, match="Path traversal"):
        UnifiedDiffParser.parse_patch(diff_text, tmp_path)


def test_patch_syntax_guard(tmp_path: Path) -> None:
    valid_py = tmp_path / "valid.py"
    valid_py.write_text("def test(): return True\n", encoding="utf-8")
    ok, err = PatchSyntaxGuard.validate_file_syntax(valid_py)
    assert ok is True
    assert err is None

    invalid_py = tmp_path / "invalid.py"
    invalid_py.write_text("def test(: return True\n", encoding="utf-8")
    ok, err = PatchSyntaxGuard.validate_file_syntax(invalid_py)
    assert ok is False
    assert "syntax error" in (err or "").lower()


def test_patch_memory_store(tmp_path: Path) -> None:
    store = PatchMemoryStore(tmp_path)
    store.record_success("SyntaxError: invalid syntax", "app.py", "diff --git a/app.py")

    retrieved = store.lookup_patch("SyntaxError: invalid syntax")
    assert retrieved == "diff --git a/app.py"

    records = store.list_records()
    assert len(records) == 1
    assert records[0].target_file == "app.py"


def test_circuit_breaker() -> None:
    cb = RemediationCircuitBreaker(max_attempts=2)
    assert cb.record_attempt() is True
    assert cb.record_attempt() is True
    assert cb.record_attempt() is False
    assert cb.is_tripped() is True
    cb.reset()
    assert cb.is_tripped() is False
