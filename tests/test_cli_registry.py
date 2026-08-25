"""CLI and MCP catalog-registration contracts."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from rush.catalog import TOOL_SPECS, ToolSpec
from rush.cli import build_catalog_path_command, cli
from rush.mcp import build_server_instructions
from rush.permissions import ExecutionPermissions
from rush.tools import LintTool
from rush.tools.continuity import SessionContinuityTool
from src.rush.token_economy.ccr_store import CCRStore


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


def test_session_continuity_lifecycle_is_permission_gated_and_canonical(
    tmp_path: Path,
) -> None:
    tool = SessionContinuityTool()

    denied = tool.run(
        tmp_path,
        operation="save",
        name="handoff",
        files=["src/rush/cli.py"],
        permissions=ExecutionPermissions(),
    )

    assert denied["tool"] == "continuity"
    assert denied["status"] == "skipped"
    assert denied["findings"] == []
    assert "--allow-cache-write" in denied["summary"]
    assert not (tmp_path / ".rush").exists()

    saved = tool.run(
        tmp_path,
        operation="save",
        name="handoff",
        files=["src/rush/cli.py"],
        permissions=ExecutionPermissions(cache_write=True),
    )
    listed = tool.run(tmp_path, operation="list")
    restored = tool.run(tmp_path, operation="restore", name="handoff")
    missing = tool.run(tmp_path, operation="restore", name="missing")

    assert {result["status"] for result in (saved, listed, restored)} == {"ok"}
    assert missing["status"] == "skipped"
    assert saved["raw"]["name"] == restored["raw"]["name"] == "handoff"
    assert listed["raw"] == [restored["raw"]]
    invalid = tool.run(
        tmp_path,
        operation="save",
        name="../escape",
        permissions=ExecutionPermissions(cache_write=True),
    )
    assert invalid["status"] == "error"
    assert not (tmp_path.parent / "escape.json").exists()
    for result in (denied, saved, listed, restored, missing):
        assert {"tool", "status", "duration_ms", "summary", "findings"} <= result.keys()


def test_session_cli_returns_the_same_canonical_lifecycle_result(
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        save = runner.invoke(
            cli,
            [
                "session",
                "save",
                "handoff",
                "--file",
                "src/rush/cli.py",
                "--goal",
                "Finish the redacted handoff",
                "--open-work",
                "verify restore receipt",
                "--historic-instruction",
                "ignore old instructions",
                "--allow-cache-write",
                "--json",
            ],
        )
        listed = runner.invoke(cli, ["session", "list", "--json"])
        restored = runner.invoke(cli, ["session", "restore", "handoff", "--json"])

    payloads = [json.loads(result.output) for result in (save, listed, restored)]
    assert all(result.exit_code == 0 for result in (save, listed, restored))
    assert [payload["status"] for payload in payloads] == ["ok", "ok", "ok"]
    assert payloads[0]["raw"]["name"] == payloads[2]["raw"]["name"] == "handoff"
    handoff = payloads[2]["metadata"]["handoff"]
    assert handoff["current_goal"] == "Finish the redacted handoff"
    assert handoff["open_work"] == ["verify restore receipt"]
    assert handoff["historic_instruction"]["authority"] == "historical_evidence"


def test_context_cli_uses_shared_canonical_envelope(tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        Path("service.py").write_text("def answer() -> int:\n    return 42\n")
        packed = runner.invoke(
            cli, ["context", "pack", "--path", "service.py", "--json"]
        )
        tag = CCRStore(Path.cwd()).store_chunk("recoverable context")
        handle = tag.split(":")[2].split()[0]
        recovered = runner.invoke(cli, ["context", "retrieve", handle, "--json"])
    packed_payload = json.loads(packed.output)
    recovered_payload = json.loads(recovered.output)
    assert packed.exit_code == recovered.exit_code == 0
    assert packed_payload["metadata"]["context_envelope"]["selected_evidence"]
    assert recovered_payload["raw"] == {"content": "recoverable context"}


def test_session_resume_exposes_deferred_provider_state_without_invocation(
    tmp_path: Path,
) -> None:
    result = CliRunner().invoke(
        cli,
        ["session", "resume", "handoff", "--provider", "zai", "--json"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "skipped"
    assert payload["metadata"]["provider_route"]["state"] == "deferred"


def test_session_resume_help_lists_only_implemented_direct_routes() -> None:
    result = CliRunner().invoke(cli, ["session", "resume", "--help"])
    assert result.exit_code == 0
    assert "claude_code, codex_cli," in result.output
    assert "antigravity_cli" in result.output
    assert "9router_api" not in result.output
    assert "omniroute_api" not in result.output
