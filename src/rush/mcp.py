"""FastMCP server — stdio transport, 5 registered tools.

Architecture §5, §6.

Tool naming: rush_<verb>_<noun>  (matches Graft's verb_noun pattern;
avoids collisions with other MCP servers in multi-server agent sessions).
"""

from __future__ import annotations

from .logging import get_logger
from .tools import ALL_TOOLS

SERVER_NAME = "rush"
SERVER_INSTRUCTIONS = (
    "rush — code-quality tools for coding agents. "
    "Five tools: rush_review, rush_lint, rush_format, rush_test, rush_security. "
    "Each takes a path (file or directory) and returns a structured JSON "
    "with status (ok|warn|fail|error|skipped), findings, and summary. "
    "If status='skipped', the underlying engine (ruff/eslint/etc.) is not "
    "installed; install it or pick a different path. "
    "Pairs well with `npx @nanonets/graft` for context-graph queries."
)


def build_server():
    """Construct and return the FastMCP server with all 5 tools registered.

    Does NOT start serving — caller decides transport. See ``run_stdio``.
    """
    from mcp.server.fastmcp import FastMCP

    server = FastMCP(SERVER_NAME, instructions=SERVER_INSTRUCTIONS)
    _register_tools(server)
    return server


def _register_tools(server) -> None:
    """Register each tool function as an MCP tool.

    Tool name = ``rush_<tool.name>``. Description from the tool's
    ``mcp_description`` property (kept <200 chars per architecture §5.2).
    """
    for tool in ALL_TOOLS:
        server.add_tool(
            fn=tool.__call__,
            name=f"rush_{tool.name}",
            description=tool.mcp_description,
        )


async def run_stdio() -> None:
    """Entry point for ``rush mcp serve``. Blocks until stdin closes."""
    server = build_server()
    get_logger("mcp").debug("starting rush stdio MCP server")
    await server.run_stdio_async()
