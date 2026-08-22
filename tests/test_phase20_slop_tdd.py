"""Phase 20 test suite for AI Anti-Slop, Modular Boundaries, and TDD Guard."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from rush.cli import cli
from rush.mcp import build_server


def test_cli_slop_clean_file(tmp_path: Path) -> None:
    test_file = tmp_path / "app.py"
    test_file.write_text("def hello() -> str:\n    return 'world'\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(cli, ["slop", str(tmp_path), "--json"])
    assert result.exit_code in (0, 1, 2)
    payload = json.loads(result.output)
    assert payload["tool"] == "slop"
    assert "findings" in payload


def test_cli_tdd_missing_tests(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "service.py").write_text("class Service: pass\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(cli, ["tdd", str(src_dir), "--json"])
    assert result.exit_code in (0, 1, 2)
    payload = json.loads(result.output)
    assert payload["tool"] == "tdd"
    assert payload["status"] == "fail"
    assert any(f["rule"] == "tdd/missing-tests" for f in payload["findings"])


def test_mcp_server_registers_phase20_tools() -> None:
    server = build_server()
    # FastMCP server tool names check
    tool_names = [t.name for t in server._tool_manager.list_tools()]
    assert "rush_slop" in tool_names
    assert "rush_tdd" in tool_names
