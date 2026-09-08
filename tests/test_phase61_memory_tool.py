"""Contract tests for Phase 61 P61.12 — Memory Query/Write Interface (`MemoryTool`)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from click.testing import CliRunner

from rush.catalog import TOOL_SPECS
from rush.cli import cli
from rush.invocation import InvocationExecutor
from rush.mcp_support.tool_registry import register_all_tools
from rush.tools import ALL_TOOLS
from rush.tools.memory import MemoryTool


def test_memory_tool_registers_as_both_cli_and_mcp() -> None:
    """T-61.32: `MemoryTool` is registered via the real two-part CLI+MCP path, matching
    `SessionContinuityTool`'s `"session"` group/`ALL_TOOLS` entry shape."""
    # (a) MemoryTool present in ALL_TOOLS, "memory" key present in TOOL_SPECS.
    assert any(isinstance(tool, MemoryTool) for tool in ALL_TOOLS)
    assert "memory" in TOOL_SPECS

    # (b) register_all_tools with a stub FastMCP server records an add_tool call named
    # rush_memory (make_tool_wrapper is MCP-only).
    stub_server = MagicMock()
    register_all_tools(stub_server, InvocationExecutor(), ALL_TOOLS)
    registered_names = [
        call.kwargs.get("name") for call in stub_server.add_tool.call_args_list
    ]
    assert "rush_memory" in registered_names

    # (c) cli.commands contains a "memory" group with ask/write/promote/list/recall subcommands.
    memory_group = cli.commands.get("memory")
    assert memory_group is not None
    for sub_name in ("ask", "write", "promote", "list", "recall"):
        assert sub_name in memory_group.commands, (
            f"missing 'memory {sub_name}' subcommand"
        )


def test_memory_ask_returns_tool_result_with_skipped_on_denied(tmp_path: Path) -> None:
    """T-61.33: A denied/absent-checkpoint-equivalent case for a memory `ask` — no
    `session_allowlist` supplied — asserts `status="skipped"` in the returned dict-shaped
    `ToolResult`, matching the `rush_continuity` precedent (fail-closed, same shape every
    other `ALL_TOOLS` member returns)."""
    result = MemoryTool().run(
        tmp_path,
        operation="ask",
        subject="preference",
        query="editor theme",
        session_allowlist=None,
    )
    assert isinstance(result, dict)
    assert result["status"] == "skipped"


def test_memory_maintain_cli_runs_with_task_option(tmp_path: Path, monkeypatch) -> None:
    """`rush memory maintain --task <valid task>` dispatches through to `MemoryTool`
    and succeeds (T028 gap: CLI path previously had no --task option and always
    returned status='error')."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "memory",
            "maintain",
            "--task",
            "promotion_sweep",
            "--allow-cache-write",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "ok"
    assert payload["metadata"]["operation"] == "maintain"
