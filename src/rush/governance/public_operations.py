"""Public Operations Inventory & Reconciliation Engine (Phase 51: P51.2.2).

Reconciles all Click command leaves and FastMCP routes into single, auditable
operations with declared input/output contracts, effect classes, and safe probes.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum

from rush.catalog import TOOL_SPECS
from rush.cli import cli
from rush.mcp import build_server
from rush.tools import ALL_TOOLS


class OperationKind(str, Enum):
    TOOL = "tool"
    ADMIN = "admin"
    SERVICE = "service"
    DEPRECATED = "deprecated"


@dataclass(frozen=True)
class PublicOperation:
    id: str
    kind: str
    canonical_impl: str
    cli_command: str | None
    mcp_tool: str | None
    input_contract: str
    output_contract: str
    effect_class: str
    safe_probe: str


def build_operations_inventory() -> list[PublicOperation]:
    """Reconcile Click leaf commands and FastMCP tools into an exhaustive inventory."""
    inventory: list[PublicOperation] = []

    # Map of all canonical tools in rush.tools
    tool_impl_map = {
        tool.name: f"{tool.__class__.__module__}:{tool.__class__.__name__}"
        for tool in ALL_TOOLS
    }

    # 1. Discover all Click leaf commands
    click_leaves: list[str] = []
    for name, cmd in cli.commands.items():
        if hasattr(cmd, "commands") and cmd.commands:
            for sub_name in cmd.commands:
                click_leaves.append(f"{name} {sub_name}")
            # A group invocable bare (invoke_without_command=True, e.g. `rush
            # scan --full`) is also its own callable leaf -- don't let having
            # subcommands hide that route.
            if getattr(cmd, "invoke_without_command", False):
                click_leaves.append(name)
        else:
            click_leaves.append(name)

    # 2. Discover all FastMCP registered tools
    async def get_mcp_tools():
        server = build_server()
        return [t.name for t in await server.list_tools()]

    mcp_tools: list[str] = asyncio.run(get_mcp_tools())

    assigned_cli: set[str] = set()
    assigned_mcp: set[str] = set()

    # Explicit known pairings between Click command leaves and MCP tools
    explicit_pairs: dict[str, tuple[str | None, str, str, str, str]] = {
        "benchmark check": (
            "rush_benchmark",
            "rush.tools.benchmark:BenchmarkTool",
            "read-only",
            "rush benchmark check --help",
            "tool",
        ),
        "release": (
            "rush_release",
            "rush.cli:release",
            "stateful-mutation",
            "rush release --dry-run",
            "admin",
        ),
        "simulate-ci": (
            "rush_ci",
            "rush.tools.simulate_ci:SimulateCiTool",
            "read-only",
            "rush simulate-ci --help",
            "tool",
        ),
        "mesh acquire-lock": (
            "rush_mesh_acquire_lock",
            "rush.core.distributed_mesh:acquire_mesh_lock",
            "stateful-mutation",
            "rush mesh acquire-lock --help",
            "service",
        ),
        "mesh release-lock": (
            "rush_mesh_release_lock",
            "rush.core.distributed_mesh:release_mesh_lock",
            "stateful-mutation",
            "rush mesh release-lock --help",
            "service",
        ),
        "ship clean": (
            "rush_ship_clean",
            "rush.tools.ship.cleaner:ScratchCleaner",
            "idempotent-write",
            "rush ship clean --dry-run",
            "tool",
        ),
        "ship env": (
            "rush_ship_env",
            "rush.tools.ship.env_linter:EnvParityLinter",
            "read-only",
            "rush ship env --help",
            "tool",
        ),
        "ship gate": (
            "rush_ship_gate",
            "rush.tools.ship.cockpit:ShipCockpit",
            "read-only",
            "rush ship gate --help",
            "tool",
        ),
        "context pack": (
            "rush_context_pack",
            "rush.codegraph.context_packer:ContextPacker",
            "read-only",
            "rush context pack --help",
            "tool",
        ),
        "context gain": (
            "rush_context_gain_stats",
            "rush.token_economy.tui_gain:render_gain_summary",
            "read-only",
            "rush context gain --help",
            "tool",
        ),
        "context-mistakes": (
            "rush_context_mistakes_check",
            "rush.memory.mistake_miner:MistakeMiner",
            "read-only",
            "rush context-mistakes --help",
            "tool",
        ),
        "ccr-retrieve": (
            "rush_context_retrieve",
            "rush.codegraph.context_cache:retrieve_context",
            "read-only",
            "rush ccr-retrieve --help",
            "tool",
        ),
        "skeletonize": (
            "rush_token_outline",
            "rush.token_economy.ast_skeletonizer:AstSkeletonizer",
            "read-only",
            "rush skeletonize --help",
            "tool",
        ),
        "attest": (
            "rush_attest",
            "rush.tools.attest:AttestationTool",
            "read-only",
            "rush attest --help",
            "tool",
        ),
        "memory ask": (
            "rush_memory",
            "rush.tools.memory:MemoryTool",
            "read-only",
            "rush memory ask --help",
            "tool",
        ),
        "memory list": (
            None,
            "rush.tools.memory:MemoryTool",
            "read-only",
            "rush memory list --help",
            "tool",
        ),
        "memory recall": (
            None,
            "rush.tools.memory:MemoryTool",
            "read-only",
            "rush memory recall --help",
            "tool",
        ),
        "memory write": (
            None,
            "rush.tools.memory:MemoryTool",
            "stateful-mutation",
            "rush memory write --help",
            "admin",
        ),
        "memory promote": (
            None,
            "rush.tools.memory:MemoryTool",
            "stateful-mutation",
            "rush memory promote --help",
            "admin",
        ),
        "memory maintain": (
            None,
            "rush.tools.memory:MemoryTool",
            "stateful-mutation",
            "rush memory maintain --help",
            "admin",
        ),
        # MC14 (Phase 63 §9.1): the 13 new memory operations. None of them claim the
        # shared "rush_memory" MCP tool name (already claimed by "memory ask" above --
        # test_operation_ids_and_transport_names_are_unique requires mcp_tool uniqueness),
        # matching the existing memory list/recall/write/promote/maintain precedent.
        "memory expand": (
            None,
            "rush.tools.memory:MemoryTool",
            "read-only",
            "rush memory expand --help",
            "admin",
        ),
        "memory link": (
            None,
            "rush.tools.memory:MemoryTool",
            "stateful-mutation",
            "rush memory link --help",
            "admin",
        ),
        "memory related": (
            None,
            "rush.tools.memory:MemoryTool",
            "read-only",
            "rush memory related --help",
            "admin",
        ),
        "memory consolidate": (
            None,
            "rush.tools.memory:MemoryTool",
            "stateful-mutation",
            "rush memory consolidate --help",
            "admin",
        ),
        "memory verify-attempt": (
            None,
            "rush.tools.memory:MemoryTool",
            "stateful-mutation",
            "rush memory verify-attempt --help",
            "admin",
        ),
        "memory prepare": (
            None,
            "rush.tools.memory:MemoryTool",
            "read-only",
            "rush memory prepare --help",
            "admin",
        ),
        "memory resume": (
            None,
            "rush.tools.memory:MemoryTool",
            "read-only",
            "rush memory resume --help",
            "admin",
        ),
        "memory intent": (
            None,
            "rush.tools.memory:MemoryTool",
            "stateful-mutation",
            "rush memory intent --help",
            "admin",
        ),
        "memory recipe": (
            None,
            "rush.tools.memory:MemoryTool",
            "stateful-mutation",
            "rush memory recipe --help",
            "admin",
        ),
        "memory plan-checks": (
            None,
            "rush.tools.memory:MemoryTool",
            "read-only",
            "rush memory plan-checks --help",
            "admin",
        ),
        "memory last-success-diagnose": (
            None,
            "rush.tools.memory:MemoryTool",
            "read-only",
            "rush memory last-success-diagnose --help",
            "admin",
        ),
        "memory handoff": (
            None,
            "rush.tools.memory:MemoryTool",
            "stateful-mutation",
            "rush memory handoff --help",
            "admin",
        ),
        "memory receive": (
            None,
            "rush.tools.memory:MemoryTool",
            "stateful-mutation",
            "rush memory receive --help",
            "admin",
        ),
        # P65-07.3 (Phase 65 §6.4): the public memory-delete operation. Matches the
        # MC14 "13 new memory operations" precedent immediately above -- doesn't claim
        # the shared "rush_memory" MCP tool name, "admin" kind regardless that preview
        # is read-only (apply is a real, gated database mutation).
        "memory delete": (
            None,
            "rush.tools.memory:MemoryTool",
            "stateful-mutation",
            "rush memory delete --help",
            "admin",
        ),
        # T031 (Phase 65 §6.4): edit/archive, added to the same P65-07 file set as
        # delete above -- same non-shared-mcp-tool-name, "admin" kind precedent.
        "memory edit": (
            None,
            "rush.tools.memory:MemoryTool",
            "stateful-mutation",
            "rush memory edit --help",
            "admin",
        ),
        "memory archive": (
            None,
            "rush.tools.memory:MemoryTool",
            "stateful-mutation",
            "rush memory archive --help",
            "admin",
        ),
        # P65-03.3 (Phase 65 §3.2): project registry operations over `ProjectTool`.
        # `list`/`show` are read-only queries ("tool" kind, matching the "memory
        # ask/recall/list" precedent); `add`/`select`/`configure`/`create`/`relink`
        # mutate registry or session state ("admin" kind, matching "memory
        # write/promote/maintain"). `list` claims the shared `rush_project` MCP tool
        # name, alphabetically first among the read-only actions.
        "project add": (
            None,
            "rush.tools.project:ProjectTool",
            "stateful-mutation",
            "rush project add --help",
            "admin",
        ),
        "project list": (
            "rush_project",
            "rush.tools.project:ProjectTool",
            "read-only",
            "rush project list --help",
            "tool",
        ),
        "project show": (
            None,
            "rush.tools.project:ProjectTool",
            "read-only",
            "rush project show --help",
            "tool",
        ),
        # P65-07.3 (Phase 65 §6.4): the shared project-evidence view and its categorized
        # artifact listing -- read-only queries, matching the "project show" precedent.
        "project snapshot": (
            None,
            "rush.tools.project:ProjectTool",
            "read-only",
            "rush project snapshot --help",
            "tool",
        ),
        "project artifacts": (
            None,
            "rush.tools.project:ProjectTool",
            "read-only",
            "rush project artifacts --help",
            "tool",
        ),
        "project select": (
            None,
            "rush.tools.project:ProjectTool",
            "stateful-mutation",
            "rush project select --help",
            "admin",
        ),
        "project configure": (
            None,
            "rush.tools.project:ProjectTool",
            "stateful-mutation",
            "rush project configure --help",
            "admin",
        ),
        "project create": (
            None,
            "rush.tools.project:ProjectTool",
            "stateful-mutation",
            "rush project create --help",
            "admin",
        ),
        "project relink": (
            None,
            "rush.tools.project:ProjectTool",
            "stateful-mutation",
            "rush project relink --help",
            "admin",
        ),
        # P65-04.3 (Phase 65 §3.2): full-project scan over `ScanTool`. One CLI
        # leaf (`--full` executes; otherwise the plan is only previewed) paired
        # directly with the one `rush_scan` MCP tool, matching "patch apply"'s
        # single-row pairing rather than `rush_project`'s split-by-action rows.
        "scan": (
            "rush_scan",
            "rush.tools.scan:ScanTool",
            "stateful-mutation",
            "rush scan --help",
            "tool",
        ),
        "patch apply": (
            "rush_patch_apply",
            "rush.tools.patch_apply:PatchApplyTool",
            "stateful-mutation",
            "rush patch apply --help",
            "tool",
        ),
        # P65-05.3 (Phase 65 §3.2): agent connection operations over
        # `AgentConnectionTool`, matching `rush_project`'s split-by-action rows.
        # `list`/`doctor` are read-only queries ("tool" kind); `connect` mutates
        # a third-party agent's own config file ("admin" kind, matching
        # "project add"/"project select"). `list` claims the shared
        # `rush_agent_connection` MCP tool name -- it is the tool's default
        # action, matching `rush_project`'s "list" precedent.
        "agent list": (
            "rush_agent_connection",
            "rush.tools.agent_connection:AgentConnectionTool",
            "read-only",
            "rush agent list --help",
            "tool",
        ),
        "agent connect": (
            None,
            "rush.tools.agent_connection:AgentConnectionTool",
            "stateful-mutation",
            "rush agent connect --help",
            "admin",
        ),
        "agent doctor": (
            None,
            "rush.tools.agent_connection:AgentConnectionTool",
            "read-only",
            "rush agent doctor --help",
            "tool",
        ),
        # T024 (Phase 65 §6.1): InstallTool is administrative CLI composition,
        # not a remotely callable installer MCP tool -- mcp_tool stays None.
        # It mutates the local filesystem, agent configs, and installs a
        # binary, so it is "admin"/"stateful-mutation" (matching "agent
        # connect"'s CLI-only administrative-mutation precedent) rather than
        # the read-only fallback the generic CLI-leaf pass (step 6) would
        # otherwise assign it.
        "install": (
            None,
            "rush.tools.install:InstallTool",
            "stateful-mutation",
            "rush install --help",
            "admin",
        ),
    }

    # 3. Pair canonical tool specs first
    for name, spec in sorted(TOOL_SPECS.items()):
        mcp_name = f"rush_{name.replace('-', '_')}"
        if (
            name in click_leaves
            and mcp_name in mcp_tools
            and name not in explicit_pairs
        ):
            canonical = tool_impl_map.get(
                name, f"rush.tools.{name.replace('-', '_')}:Tool"
            )
            op = PublicOperation(
                id=f"tool.{name.replace('-', '_')}",
                kind=OperationKind.TOOL.value,
                canonical_impl=canonical,
                cli_command=name,
                mcp_tool=mcp_name,
                input_contract="ToolInputOptions",
                output_contract="ToolResult",
                effect_class="read-only"
                if not spec.name.startswith("format")
                else "idempotent-write",
                safe_probe=f"rush {name} --help",
            )
            inventory.append(op)
            assigned_cli.add(name)
            assigned_mcp.add(mcp_name)

    # 4. Pair explicit routes
    for cli_cmd, (paired_mcp_name, impl, effect, probe, kind_str) in sorted(
        explicit_pairs.items()
    ):
        if cli_cmd in click_leaves and (
            paired_mcp_name is None or paired_mcp_name in mcp_tools
        ):
            clean_id = cli_cmd.replace(" ", "_").replace("-", "_")
            op = PublicOperation(
                id=f"{kind_str}.{clean_id}",
                kind=kind_str,
                canonical_impl=impl,
                cli_command=cli_cmd,
                mcp_tool=paired_mcp_name,
                input_contract="ToolInputOptions",
                output_contract="ToolResult" if kind_str == "tool" else "RawResult",
                effect_class=effect,
                safe_probe=probe,
            )
            inventory.append(op)
            assigned_cli.add(cli_cmd)
            if paired_mcp_name is not None:
                assigned_mcp.add(paired_mcp_name)

    # 5. Remaining MCP tools (MCP-only routes / aliases)
    for mcp_name in sorted(mcp_tools):
        if mcp_name not in assigned_mcp:
            clean_id = mcp_name.replace("rush_", "")
            impl = f"rush.mcp:{mcp_name}"
            # Check if canonical tool exists
            raw_tool = clean_id.replace("_", "-")
            if raw_tool in tool_impl_map:
                impl = tool_impl_map[raw_tool]

            op = PublicOperation(
                id=f"mcp.{clean_id}",
                kind=OperationKind.SERVICE.value,
                canonical_impl=impl,
                cli_command=None,
                mcp_tool=mcp_name,
                input_contract="McpArguments",
                output_contract="McpCallResult",
                effect_class="read-only",
                safe_probe=f"mcp:inspect:{mcp_name}",
            )
            inventory.append(op)
            assigned_mcp.add(mcp_name)

    # 6. Remaining Click leaves (CLI-only administration / subcommands)
    for cli_cmd in sorted(click_leaves):
        if cli_cmd not in assigned_cli:
            clean_id = cli_cmd.replace(" ", "_").replace("-", "_")
            parts = cli_cmd.split()
            root_cmd = parts[0]
            kind = OperationKind.ADMIN.value
            if root_cmd in {"bundle", "hotspots", "governance", "hook", "context"}:
                kind = OperationKind.TOOL.value

            op = PublicOperation(
                id=f"cli.{clean_id}",
                kind=kind,
                canonical_impl=f"rush.cli:{root_cmd}",
                cli_command=cli_cmd,
                mcp_tool=None,
                input_contract="ClickArguments",
                output_contract="ClickExitCode",
                effect_class="read-only",
                safe_probe=f"rush {cli_cmd} --help",
            )
            inventory.append(op)
            assigned_cli.add(cli_cmd)

    # Deterministic sorting by operation id
    inventory.sort(key=lambda op: op.id)
    return inventory


def render_operations_toml(inventory: list[PublicOperation]) -> str:
    """Render operations inventory as deterministic, byte-stable TOML."""
    lines = [
        "# Public Operations Manifest (RM-P0-02)",
        "# Generated deterministically by rush.governance.public_operations",
        "",
        "[manifest]",
        f"total_operations = {len(inventory)}",
        "",
    ]

    for op in inventory:
        lines.append("[[operations]]")
        lines.append(f'id = "{op.id}"')
        lines.append(f'kind = "{op.kind}"')
        lines.append(f'canonical_impl = "{op.canonical_impl}"')
        if op.cli_command is not None:
            lines.append(f'cli_command = "{op.cli_command}"')
        if op.mcp_tool is not None:
            lines.append(f'mcp_tool = "{op.mcp_tool}"')
        lines.append(f'input_contract = "{op.input_contract}"')
        lines.append(f'output_contract = "{op.output_contract}"')
        lines.append(f'effect_class = "{op.effect_class}"')
        lines.append(f'safe_probe = "{op.safe_probe}"')
        lines.append("")

    return "\n".join(lines)
