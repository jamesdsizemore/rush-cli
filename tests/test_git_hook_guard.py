"""Tests for Phase 39: Git Pre-Commit Intelligence & Hook Guard."""

from __future__ import annotations

from pathlib import Path

from rush.hook.ast_linter import FastIncrementalAstLinter
from rush.hook.conflict_guard import ConflictMarkerGuard
from rush.hook.conventional_commit import ConventionalCommitValidator
from rush.hook.tamper_detector import HookTamperDetector
from rush.hook.trojan_source import TrojanSourceDetector


def test_conventional_commit_validator() -> None:
    ok, _err = ConventionalCommitValidator.validate_message(
        "feat(auth): implement oauth2 token flow"
    )
    assert ok is True

    ok_bad, err_bad = ConventionalCommitValidator.validate_message(
        "random bad commit message"
    )
    assert ok_bad is False
    assert "Conventional Commits" in (err_bad or "")


def test_trojan_source_detector(tmp_path: Path) -> None:
    f = tmp_path / "trojan.py"
    f.write_text("isAdmin = False; \u202e } \u2066if (isAdmin)", encoding="utf-8")

    findings = TrojanSourceDetector.inspect_file(f)
    assert len(findings) >= 1
    assert "Trojan Source" in findings[0]


def test_fast_ast_linter(tmp_path: Path) -> None:
    good = tmp_path / "good.py"
    good.write_text("def hello(): pass\n", encoding="utf-8")

    bad = tmp_path / "bad.py"
    bad.write_text("def broken_syntax(:\n", encoding="utf-8")

    errors = FastIncrementalAstLinter.lint_staged_python([good, bad])
    assert len(errors) == 1
    assert "SyntaxError" in errors[0]


def test_conflict_marker_guard(tmp_path: Path) -> None:
    f = tmp_path / "conflict.txt"
    f.write_text(
        "line 1\n<<<<<<< HEAD\nline 2\n=======\nline 2b\n>>>>>>> feature\n",
        encoding="utf-8",
    )

    findings = ConflictMarkerGuard.inspect_file(f)
    assert len(findings) >= 3


def test_hook_tamper_detector(tmp_path: Path) -> None:
    git_dir = tmp_path / ".git" / "hooks"
    git_dir.mkdir(parents=True)
    hook = git_dir / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    detector = HookTamperDetector(tmp_path)
    sigs = detector.record_signatures()
    assert "pre-commit" in sigs

    ok, _errors = detector.verify_signatures()
    assert ok is True

    # Tamper with hook
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    ok_tampered, errs = detector.verify_signatures()
    assert ok_tampered is False
    assert len(errs) == 1
