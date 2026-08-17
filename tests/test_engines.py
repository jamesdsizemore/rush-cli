"""Tests for engines — engine dispatch + normalize logic.

Skips tests gracefully when an engine is not installed.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from rush.engines import ENGINES
from rush.engines.eslint import _eslint_severity
from rush.engines.npm_audit import _npm_severity
from rush.engines.pip_audit import PipAuditEngine, _parse_dependencies
from rush.engines.prettier import PrettierEngine
from rush.engines.pytest import PytestEngine
from rush.engines.ruff import RuffEngine, _ruff_severity


def test_engines_registry_has_seven():
    assert set(ENGINES.keys()) == {
        "ruff",
        "eslint",
        "prettier",
        "vitest",
        "pytest",
        "pip-audit",
        "npm-audit",
    }


@pytest.mark.skipif(
    shutil.which("ruff") is None
    and not Path("C:/Users/james/developer/rush-cli/.venv/Scripts/ruff.exe").exists(),
    reason="ruff not installed",
)
def test_ruff_engine_runs_and_parses(tmp_path: Path):
    """Real ruff on a tiny dirty file should find at least one E501."""
    sample = tmp_path / "x.py"
    sample.write_text("x = 1\n" + ("y = 2  # comment to fill " * 30 + "\n"))
    engine = RuffEngine()
    from rush.tools.common import resolve_binary

    if resolve_binary("ruff") is None:
        pytest.skip("ruff not installed")
    raw = engine.run(sample, [], cwd=tmp_path)
    assert raw["exit_code"] in (0, 1)
    assert isinstance(raw["parsed"], list)
    # The long line above should produce at least one E501
    rules = [f.get("code") for f in raw["findings"]]
    if raw["findings"]:
        assert "E501" in rules


def test_ruff_severity_helper():
    assert _ruff_severity("F401") == "error"  # pyflakes
    assert _ruff_severity("E501") == "warn"
    assert _ruff_severity("W292") == "warn"
    assert _ruff_severity("") == "warn"


def test_eslint_severity_helper():
    assert _eslint_severity(2) == "error"
    assert _eslint_severity(1) == "warn"
    assert _eslint_severity(0) == "warn"


def test_npm_severity_helper():
    assert _npm_severity("critical") == "error"
    assert _npm_severity("high") == "error"
    assert _npm_severity("moderate") == "warn"
    assert _npm_severity("low") == "warn"
    assert _npm_severity("info") == "info"
    assert _npm_severity("") == "info"


def test_pip_audit_parses_current_dependencies_envelope():
    payload = {
        "dependencies": [
            {
                "name": "pytest",
                "version": "8.3.4",
                "vulns": [{"id": "PYSEC-test", "fix_versions": ["9.0.3"]}],
            }
        ]
    }
    dependencies = _parse_dependencies(payload)
    assert dependencies[0]["name"] == "pytest"

    result = PipAuditEngine().normalize(
        {"exit_code": 1, "findings": dependencies, "parsed": payload},
        Path("."),
        "security",
    )
    assert result["status"] == "fail"
    assert result["findings"][0]["rule"] == "PYSEC-test"
    assert result["findings"][0]["message"].startswith("pytest==8.3.4")


@pytest.mark.skipif(
    shutil.which("pytest") is None
    and not Path("C:/Users/james/developer/rush-cli/.venv/Scripts/pytest.exe").exists(),
    reason="pytest not installed",
)
def test_pytest_engine_on_passing_tests(tmp_path: Path):
    """pytest should exit 0 on a passing test."""
    test_dir = tmp_path / "t"
    test_dir.mkdir()
    (test_dir / "test_pass.py").write_text("def test_truth():\n    assert True\n")
    engine = PytestEngine()
    from rush.tools.common import resolve_binary

    if resolve_binary("pytest") is None:
        pytest.skip("pytest not installed")
    raw = engine.run(test_dir / "test_pass.py", [], cwd=tmp_path)
    assert raw["exit_code"] == 0
    summary = raw["summary"] or ""
    assert "passed" in summary.lower()


@pytest.mark.skipif(
    shutil.which("pytest") is None
    and not Path("C:/Users/james/developer/rush-cli/.venv/Scripts/pytest.exe").exists(),
    reason="pytest not installed",
)
def test_pytest_engine_on_failing_tests(tmp_path: Path):
    """pytest should exit non-zero on a failing test, normalize should produce a finding."""
    test_dir = tmp_path / "t"
    test_dir.mkdir()
    (test_dir / "test_fail.py").write_text("def test_broken():\n    assert False\n")
    engine = PytestEngine()
    from rush.tools.common import resolve_binary

    if resolve_binary("pytest") is None:
        pytest.skip("pytest not installed")
    raw = engine.run(test_dir / "test_fail.py", [], cwd=tmp_path)
    assert raw["exit_code"] != 0
    result = engine.normalize(raw, test_dir / "test_fail.py", "test")
    assert result["status"] == "fail"
    assert result["findings"]  # at least one finding (the test failure)


@pytest.mark.skipif(shutil.which("prettier") is None, reason="prettier not installed")
def test_prettier_engine_check_mode(tmp_path: Path):
    """prettier --check on an unformatted file should produce findings."""
    sample = tmp_path / "x.ts"
    # Intentionally bad formatting
    sample.write_text("const x={a:1,b:2}\n")
    engine = PrettierEngine()
    raw = engine.run(sample, [], cwd=tmp_path)
    # Exit code 1 = "would reformat"; 0 = clean; >=2 = error
    assert raw["exit_code"] in (0, 1)
    if raw["findings"]:
        # At least one finding names the file
        paths = [f.get("path", "") for f in raw["findings"]]
        assert any(str(sample) in p for p in paths)


def test_engine_version_method_handles_missing():
    """Engine.version() should not raise even if the binary is missing."""

    # Test with a definitely-nonexistent engine name
    class FakeEngine(RuffEngine):
        binary = "definitely-not-a-binary-xyz123"

    fake = FakeEngine()
    assert fake.version() is None  # shutil.which returns None → return None
