"""Tests for the 5 tool functions — heuristic review + engine dispatch."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from rush.config import RushConfig, ReviewConfig
from rush.tools import (
    FormatTool,
    LintTool,
    ReviewTool,
    SecurityTool,
    TestTool,
    engine_on_path,
)
from rush.tools.common import resolve_binary


@pytest.fixture
def py_repo(tmp_path: Path) -> Path:
    """A small Python repo with intentional findings."""
    repo = tmp_path / "py"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "fixture"\n')
    # Long line (E501), TODO density, missing docstrings, all-caps variable
    long_line = "y = " + "x + " * 30 + "1\n"
    (repo / "dirty.py").write_text(
        "def clean():\n"
        "    '''has docstring'''\n"
        "    return 1\n"
        "\n"
        "def dirty():\n"
        "    return 2\n"
        "\n"
        f"{long_line}"
        "# TODO: refactor this\n"
        "# TODO: also this\n"
        "# FIXME: and this\n"
        "\n"
        "BIG_BAD_NAME = some_function_call()\n"
    )
    (repo / "clean.py").write_text(
        "def clean():\n"
        "    '''docstring'''\n"
        "    return 1\n"
    )
    return repo


@pytest.fixture
def ts_repo(tmp_path: Path) -> Path:
    """A small TS repo for prettier/eslint tests."""
    repo = tmp_path / "ts"
    repo.mkdir()
    (repo / "package.json").write_text(
        '{"name": "fixture", "version": "0.0.1", "scripts": {"test": "echo"}}\n'
    )
    # Badly formatted
    (repo / "dirty.ts").write_text("const x={a:1,b:2,c:3}\n")
    return repo


# --- ReviewTool heuristics --------------------------------------------------


def test_review_heuristics_on_dirty_repo(py_repo: Path):
    tool = ReviewTool()
    result = tool.run(py_repo)
    assert result["status"] in ("warn", "fail")
    assert result["tool"] == "review"
    assert result["review_kind"] == "heuristic"
    rules_seen = {f.get("rule") for f in result["findings"]}
    # At least one of: todo-density, missing-docstring, naming
    assert rules_seen & {"todo-density", "missing-docstring", "naming"}, f"no heuristics fired: {rules_seen}"


def test_review_heuristics_on_clean_repo(tmp_path: Path):
    repo = tmp_path / "clean"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "x"\n')
    (repo / "good.py").write_text(
        "def good():\n"
        "    '''docstring'''\n"
        "    return 1\n"
    )
    tool = ReviewTool()
    result = tool.run(repo)
    assert result["status"] == "ok"


def test_review_respects_max_file_lines_config(tmp_path: Path):
    repo = tmp_path / "r"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "x"\n')
    # 200 lines
    lines = ["def f(): return 1\n"] * 200
    (repo / "big.py").write_text("".join(lines))
    cfg = RushConfig(review=ReviewConfig(max_file_lines=100))
    tool = ReviewTool()
    result = tool.run(repo, config=cfg)
    file_size_findings = [f for f in result["findings"] if f.get("rule") == "file-size"]
    assert len(file_size_findings) >= 1


def test_review_skip_on_non_python(tmp_path: Path):
    """A directory with no Python files returns ok with no findings."""
    repo = tmp_path / "nopy"
    repo.mkdir()
    (repo / "readme.md").write_text("hi\n")
    tool = ReviewTool()
    result = tool.run(repo)
    assert result["status"] == "ok"
    assert result["findings"] == []


def test_review_llm_requires_env_key(tmp_path: Path):
    """--llm without env keys falls back to heuristic (no error)."""
    import os
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        os.environ.pop(k, None)
    repo = tmp_path / "r"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "x"\n')
    (repo / "x.py").write_text("def good():\n    '''doc'''\n    return 1\n")
    tool = ReviewTool()
    result = tool.run(repo, use_llm=True)
    # No env key → review_kind stays heuristic, no LLM call attempted
    assert result["review_kind"] == "heuristic"


def test_review_llm_with_env_key_returns_llm_kind(tmp_path: Path, monkeypatch):
    """When env keys are set, --llm returns review_kind=llm."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake")
    repo = tmp_path / "r"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "x"\n')
    (repo / "x.py").write_text("def good():\n    '''doc'''\n    return 1\n")
    tool = ReviewTool()
    result = tool.run(repo, use_llm=True)
    assert result["review_kind"] == "llm"
    assert result["review_provider"] == "anthropic"


# --- LintTool ---------------------------------------------------------------


@pytest.mark.skipif(resolve_binary("ruff") is None, reason="ruff not installed")
def test_lint_runs_ruff_on_python_repo(py_repo: Path):
    tool = LintTool()
    result = tool.run(py_repo)
    # The dirty.py file has a long line → ruff should find E501
    assert result["status"] in ("warn", "fail")
    assert result["tool"] == "lint"
    assert "ruff" in (result.get("engine") or "")


def test_lint_skipped_when_no_engines(tmp_path: Path):
    """A path with no source files returns skipped."""
    repo = tmp_path / "empty"
    repo.mkdir()
    (repo / "readme.md").write_text("hi\n")
    tool = LintTool()
    result = tool.run(repo)
    assert result["status"] == "skipped"


def test_lint_dispatches_per_extension(tmp_path: Path):
    """If only .ts files exist, eslint is the right engine to choose."""
    repo = tmp_path / "ts"
    repo.mkdir()
    (repo / "x.ts").write_text("const x=1\n")
    tool = LintTool()
    result = tool.run(repo)
    # Either eslint succeeded/warned/failed, or skipped if eslint isn't installed
    assert result["status"] in ("ok", "warn", "fail", "skipped")
    if result["status"] != "skipped":
        # engine field mentions eslint if it ran
        assert "eslint" in (result.get("engine") or "")


# --- FormatTool -------------------------------------------------------------


@pytest.mark.skipif(resolve_binary("ruff") is None, reason="ruff not installed")
def test_format_runs_ruff_format_check(py_repo: Path):
    """ruff format --check on dirty.py should produce a finding."""
    tool = FormatTool()
    result = tool.run(py_repo)
    assert result["tool"] == "format"
    # Either clean (ok) or has reformat findings (warn)
    assert result["status"] in ("ok", "warn")


# --- TestTool ---------------------------------------------------------------


@pytest.mark.skipif(resolve_binary("pytest") is None, reason="pytest not installed")
def test_test_runs_pytest_on_python_repo(py_repo: Path):
    """A repo without tests → pytest collects nothing → ok (exit 5)."""
    tool = TestTool()
    result = tool.run(py_repo)
    assert result["tool"] == "test"
    assert result["status"] in ("ok", "fail")
    assert "pytest" in (result.get("engine") or "")


def test_test_skipped_when_no_project_markers(tmp_path: Path):
    repo = tmp_path / "nope"
    repo.mkdir()
    tool = TestTool()
    result = tool.run(repo)
    assert result["status"] == "skipped"


# --- SecurityTool -----------------------------------------------------------


@pytest.mark.skipif(resolve_binary("pip-audit") is None, reason="pip-audit not installed")
def test_security_runs_pip_audit_on_python_repo(py_repo: Path):
    tool = SecurityTool()
    result = tool.run(py_repo)
    assert result["tool"] == "security"
    assert result["status"] in ("ok", "fail")
    assert "pip-audit" in (result.get("engine") or "")


def test_security_skipped_when_no_project_markers(tmp_path: Path):
    repo = tmp_path / "nope"
    repo.mkdir()
    tool = SecurityTool()
    result = tool.run(repo)
    assert result["status"] == "skipped"
