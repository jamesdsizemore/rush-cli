"""CLI and MCP catalog-registration contracts."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from rush.catalog import TOOL_SPECS, ToolSpec
from rush.cli import build_catalog_path_command, cli
from rush.mcp import build_server_instructions
from rush.tools import LintTool


def test_catalog_path_command_uses_the_tool_name_and_standard_options() -> None:
    command = build_catalog_path_command(LintTool())

    assert command.name == "lint"
    options = {parameter.name for parameter in command.params}
    assert {"path", "as_json"} <= options


def test_cli_help_contains_every_registered_catalog_tool() -> None:
    result = CliRunner().invoke(cli, ["--help"])

    assert result.exit_code == 0
    for name in ("review", "lint", "format", "test", "security"):
        assert name in result.output


def test_catalog_path_command_emits_canonical_json(tmp_path: Path) -> None:
    source = tmp_path / "example.py"
    source.write_text("def example() -> int:\n    return 1\n")

    result = CliRunner().invoke(
        build_catalog_path_command(LintTool()), [str(source), "--json"]
    )

    assert result.exit_code in {0, 1, 2}
    assert '"tool": "lint"' in result.output


def test_review_cli_passes_only_explicit_changed_files_to_shared_tool(
    tmp_path: Path,
) -> None:
    (tmp_path / "changed.py").write_text(
        "# TODO: scope signal\ndef changed():\n    return 1\n"
    )
    (tmp_path / "unscoped.py").write_text(
        "# TODO: unscoped\ndef unscoped():\n    return 1\n"
    )

    result = CliRunner().invoke(
        cli,
        ["review", str(tmp_path), "--changed-file", "changed.py", "--json"],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert {finding["path"] for finding in payload["findings"]} == {
        str(tmp_path / "changed.py")
    }


def test_mcp_instructions_are_generated_from_catalog(monkeypatch) -> None:
    monkeypatch.setitem(
        TOOL_SPECS,
        "example",
        ToolSpec(
            name="example",
            category="quality",
            description="Example catalog tool.",
            mcp_description="Example MCP tool.",
            engine_names=(),
        ),
    )

    assert "rush_example" in build_server_instructions()
