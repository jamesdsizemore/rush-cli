"""Smoke tests for the Phase 3 skeleton.

Verifies the package imports, exposes version, and the CLI surface renders
without crashing. Per architecture §12 acceptance gates.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

import rush
from rush import __version__
from rush.cli import cli
from rush.tools import ALL_TOOLS


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_version_string():
    assert __version__ == "0.1.0"


def test_imports():
    """Every public module imports without error."""
    from rush import cli

    assert rush is not None
    assert cli is not None


def test_all_tools_has_five():
    """ALL_TOOLS is the single registry. C3 — single source of truth."""
    from rush.catalog import TOOL_SPECS

    names = sorted(t.name for t in ALL_TOOLS)
    assert names == sorted(TOOL_SPECS)


def test_every_tool_has_short_mcp_description():
    """Architecture §5.2: descriptions must be <200 chars."""
    for tool in ALL_TOOLS:
        desc = tool.mcp_description
        assert isinstance(desc, str)
        assert len(desc) < 200, f"{tool.name} description too long: {len(desc)}"


def test_cli_help_renders(runner: CliRunner):
    """`rush --help` shows the group + subcommand list."""
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "rush" in result.output.lower()
    assert "review" in result.output
    assert "lint" in result.output
    assert "format" in result.output
    assert "test" in result.output
    assert "security" in result.output
    assert "mcp" in result.output


def test_cli_version_flag(runner: CliRunner):
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_review_subcommand_runs(runner: CliRunner, tmp_path: Path):
    """The review stub returns a ToolResult. `--json` produces parseable JSON."""
    sample = tmp_path / "x.py"
    sample.write_text("x = 1\n")
    result = runner.invoke(cli, ["review", str(sample), "--json"])
    # The stub returns status='ok' so exit_code 0
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["tool"] == "review"
    assert payload["status"] in ("ok", "warn", "fail", "error", "skipped")
    assert "findings" in payload


def test_lint_subcommand_runs_or_skips(runner: CliRunner, tmp_path: Path):
    """The lint subcommand runs ruff on a .py file. If ruff is installed
    (it is, via uv pip install in this venv), it returns a real ToolResult.
    Either way the JSON parses and status is one of the documented values."""
    sample = tmp_path / "x.py"
    sample.write_text("x = 1\n")
    result = runner.invoke(cli, ["lint", str(sample), "--json"])
    assert result.exit_code in (0, 1), result.output
    payload = json.loads(result.output)
    assert payload["tool"] == "lint"
    assert payload["status"] in ("ok", "warn", "fail", "error", "skipped")


def test_logging_writes_ndjson_to_stderr(runner: CliRunner, tmp_path: Path, capsys):
    """C5: logs go to stderr, stdout reserved for output."""
    from rush.logging import get_logger, setup_logging

    setup_logging("debug")
    log = get_logger("test")
    log.warning("hello-from-test")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "hello-from-test" in captured.err
    # NDJSON: one JSON object per line
    lines = [ln for ln in captured.err.splitlines() if ln.strip()]
    assert any('"level": "WARNING"' in ln for ln in lines)


def test_logging_redacts_secrets(runner: CliRunner, capsys):
    """C5: secret-like values never reach logs."""
    from rush.logging import get_logger, setup_logging

    setup_logging("debug")
    log = get_logger("test.redact")
    log.error("failed with api_key=sk-12345abcdef")

    captured = capsys.readouterr()
    assert "sk-12345abcdef" not in captured.err
    assert "REDACTED" in captured.err
