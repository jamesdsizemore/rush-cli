"""Tests for TDD Guard tool."""

from __future__ import annotations

from pathlib import Path

from rush.tools.tdd_guard import TddGuardTool


def test_tdd_guard_clean(tmp_path: Path) -> None:
    # Create mock test file
    test_file = tmp_path / "test_sample.py"
    test_file.write_text("def test_ok(): pass\n", encoding="utf-8")

    tool = TddGuardTool()
    res = tool.run(tmp_path)
    assert res["status"] == "ok"
    assert "test suite verified" in res["summary"]
    assert res["findings"] == []


def test_tdd_guard_missing_tests(tmp_path: Path) -> None:
    # Empty dir without test files
    empty_dir = tmp_path / "subpkg"
    empty_dir.mkdir()
    (empty_dir / "mod.py").write_text("def foo(): return 1\n", encoding="utf-8")

    tool = TddGuardTool()
    res = tool.run(empty_dir)
    assert res["status"] == "fail"
    assert len(res["findings"]) == 1
    assert res["findings"][0]["rule"] == "tdd/missing-tests"
