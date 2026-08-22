"""FastMCP server — stdio transport, 35 registered catalog tools.

Architecture §5, §6.

Tool naming: rush_<verb>_<noun>  (matches Graft's verb_noun pattern;
avoids collisions with other MCP servers in multi-server agent sessions).
"""

from __future__ import annotations

from .catalog import TOOL_SPECS
from .logging import get_logger
from .tools import ALL_TOOLS

SERVER_NAME = "rush"


def build_server_instructions() -> str:
    """Describe the live catalog without duplicating a fixed tool list."""
    tool_names = ", ".join(f"rush_{name}" for name in TOOL_SPECS)
    maturity = "; ".join(
        f"rush_{name}={spec.maturity}" for name, spec in TOOL_SPECS.items()
    )
    return (
        "rush — code-quality tools for coding agents. "
        f"Available tools: {tool_names}. "
        "Each takes a path (file or directory) and returns a structured JSON "
        "with status (ok|warn|fail|error|skipped), findings, and summary. "
        "If status='skipped', the underlying engine is not installed; install it "
        "or pick a different path. Pairs well with `npx @nanonets/graft` for "
        f"context-graph queries. Maturity: {maturity}."
    )


def build_server():
    """Construct and return the FastMCP server with all catalog tools registered.

    Does NOT start serving — caller decides transport. See ``run_stdio``.
    """
    from mcp.server.fastmcp import FastMCP

    server = FastMCP(SERVER_NAME, instructions=build_server_instructions())
    _register_tools(server)
    return server


def _register_tools(server) -> None:
    """Register each tool function as an MCP tool."""
    for tool in ALL_TOOLS:
        server.add_tool(
            fn=tool.__call__,
            name=f"rush_{tool.name}",
            description=tool.mcp_description,
        )

    # Phase 41 Tools
    def mcp_rush_session_save(name: str, files: list[str]) -> str:
        from rush.memory.checkpoint_journal import CheckpointJournal

        journal = CheckpointJournal()
        dest = journal.save_checkpoint(name, {}, files)
        return f"Session saved: {dest}"

    def mcp_rush_ship_clean(dry_run: bool = False) -> str:
        from rush.tools.ship.cleaner import ScratchCleaner

        cleaner = ScratchCleaner()
        res = cleaner.clean(dry_run=dry_run)
        return (
            f"Cleaned {res['removed_count']} items ({res['bytes_freed']} bytes freed)."
        )

    def mcp_rush_ship_env() -> str:
        from rush.tools.ship.env_linter import EnvParityLinter

        linter = EnvParityLinter()
        res = linter.lint()
        if res["passed"]:
            return "All environment variables declared in .env.example."
        return f"Missing declarations in .env.example: {', '.join(res['missing_in_example'])}"

    server.add_tool(
        fn=mcp_rush_session_save,
        name="rush_session_save",
        description="Save developer context snapshot to .rush/sessions/",
    )
    server.add_tool(
        fn=mcp_rush_ship_clean,
        name="rush_ship_clean",
        description="Clean scratch directories and build caches before release",
    )
    server.add_tool(
        fn=mcp_rush_ship_env,
        name="rush_ship_env",
        description="Audit codebase environment variable usage against .env.example",
    )


async def run_stdio() -> None:
    """Entry point for ``rush mcp serve``. Blocks until stdin closes."""
    server = build_server()
    get_logger("mcp").debug("starting rush stdio MCP server")
    await server.run_stdio_async()
