"""Contract tests for Public Operations Inventory (Phase 51: P51.2.1)."""

from __future__ import annotations

import tomllib
from pathlib import Path

from rush.governance.public_operations import (
    OperationKind,
    build_operations_inventory,
    render_operations_toml,
)


def test_every_click_leaf_and_advertised_mcp_route_has_one_operation() -> None:
    import asyncio

    from rush.cli import cli
    from rush.mcp import build_server

    inventory = build_operations_inventory()
    op_by_cli = {op.cli_command: op for op in inventory if op.cli_command}
    op_by_mcp = {op.mcp_tool: op for op in inventory if op.mcp_tool}

    # Verify Click root commands and leaf subcommands are represented
    for name, cmd in cli.commands.items():
        if hasattr(cmd, "commands") and cmd.commands:
            for sub_name in cmd.commands:
                full_cmd = f"{name} {sub_name}"
                assert full_cmd in op_by_cli, (
                    f"Click subcommand '{full_cmd}' must be in operations inventory"
                )
        else:
            assert name in op_by_cli, (
                f"Click command '{name}' must be in operations inventory"
            )

    # Verify FastMCP tools are represented
    server = build_server()

    async def get_tools():
        return await server.list_tools()

    mcp_tools = asyncio.run(get_tools())

    for tool in mcp_tools:
        assert tool.name in op_by_mcp, (
            f"FastMCP tool '{tool.name}' must be in operations inventory"
        )


def test_every_advertised_transport_has_a_non_live_probe() -> None:
    inventory = build_operations_inventory()
    for op in inventory:
        assert op.safe_probe is not None and len(op.safe_probe) > 0, (
            f"Operation '{op.id}' must define a safe, non-live probe"
        )
        assert not op.safe_probe.startswith("LIVE:"), (
            "Probes must be non-live and non-destructive"
        )


def test_operation_ids_and_transport_names_are_unique() -> None:
    inventory = build_operations_inventory()

    op_ids = [op.id for op in inventory]
    assert len(op_ids) == len(set(op_ids)), "Operation IDs must be unique"

    cli_cmds = [op.cli_command for op in inventory if op.cli_command]
    assert len(cli_cmds) == len(set(cli_cmds)), (
        "CLI commands must be unique across operations"
    )

    mcp_tools = [op.mcp_tool for op in inventory if op.mcp_tool]
    assert len(mcp_tools) == len(set(mcp_tools)), (
        "MCP tools must be unique across operations"
    )


def test_tool_pairs_share_one_canonical_implementation() -> None:
    inventory = build_operations_inventory()
    tool_ops = [op for op in inventory if op.kind == OperationKind.TOOL.value]

    for op in tool_ops:
        if op.cli_command and op.mcp_tool:
            assert op.canonical_impl is not None and ":" in op.canonical_impl, (
                f"Dual-transport tool '{op.id}' must declare its canonical implementation in src/rush/tools/"
            )


def test_operations_toml_rendering_is_byte_stable(tmp_path: Path) -> None:
    inventory = build_operations_inventory()
    toml1 = render_operations_toml(inventory)
    toml2 = render_operations_toml(inventory)

    assert toml1 == toml2, "Operations TOML must be byte-stable and sorted"
    parsed = tomllib.loads(toml1)
    assert len(parsed["operations"]) == len(inventory)
