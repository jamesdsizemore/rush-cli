"""End-to-end stdio MCP tests.

These tests start the actual ``rush mcp serve`` child process, negotiate the
MCP protocol through the official ``mcp`` client, inspect the advertised tool
schemas, and invoke a real tool. A successful handshake proves protocol frames
remain clean on stdout; any human/log output there would corrupt the transport.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from rush.tools import ALL_TOOLS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TOOLS = {f"rush_{tool.name}" for tool in ALL_TOOLS} | {
    "rush_session_save",
    "rush_ship_clean",
    "rush_ship_env",
    "rush_ship_gate",
    "rush_token_outline",
    "rush_context_retrieve",
    "rush_hallu_guard",
    "rush_context_mistakes_check",
    "rush_context_pack",
    "rush_context_gain_stats",
    "rush_blast_radius",
    "rush_arch_guard",
}


def _run(coro):
    """Run one MCP client session from synchronous pytest."""
    return asyncio.run(coro)


def test_stdio_mcp_lists_clean_tool_schemas_and_calls_review(tmp_path: Path):
    """The real server completes initialize → tools/list → two tools/call.

    ``review`` stays deterministic and in-process; ``lint`` ensures the
    shared, non-review ToolResult schema is valid through FastMCP as well.
    """
    source = tmp_path / "review_target.py"
    source.write_text("def example() -> int:\n    return 1\n")

    async def exercise() -> tuple[
        str, set[str], dict[str, object], dict[str, object], dict[str, object], str
    ]:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "rush.cli", "mcp", "serve"],
            cwd=PROJECT_ROOT,
            # MCP treats this as the complete child environment. Preserve the
            # Windows runtime values (SystemRoot, TEMP, PATH, ...) and alter
            # only Rush's log level.
            env={
                **os.environ,
                "RUSH_LOG_LEVEL": "debug",
                "PYTHONPATH": str(PROJECT_ROOT / "src"),
            },
        )
        # stdio_client gives this handle directly to CreateProcess on Windows,
        # so capture stderr in a real file rather than io.StringIO (no fileno).
        with tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8") as server_stderr:
            async with (
                stdio_client(params, errlog=server_stderr) as (
                    read,
                    write,
                ),
                ClientSession(read, write) as session,
            ):
                initialized = await session.initialize()
                listed = await session.list_tools()
                schemas = {tool.name: tool.inputSchema for tool in listed.tools}

                response = await session.call_tool(
                    "rush_review",
                    {"path": str(source), "changed_files": ["review_target.py"]},
                )
                assert not response.isError
                assert response.content
                payload = json.loads(response.content[0].text)

                lint_response = await session.call_tool(
                    "rush_lint", {"path": str(source)}
                )
                assert not lint_response.isError
                assert lint_response.content
                lint_payload = json.loads(lint_response.content[0].text)

            server_stderr.seek(0)
            return (
                initialized.protocolVersion,
                set(schemas),
                schemas,
                payload,
                lint_payload,
                server_stderr.read(),
            )

    protocol, names, schemas, payload, lint_payload, server_stderr = _run(exercise())

    assert protocol
    assert names == EXPECTED_TOOLS
    catalog_tool_names = {f"rush_{tool.name}" for tool in ALL_TOOLS}
    for name, schema in schemas.items():
        if name in catalog_tool_names:
            assert "path" in schema["properties"]
            assert "config" not in schema["properties"]

    assert payload["tool"] == "review"
    assert payload["status"] in {"ok", "warn"}
    assert isinstance(payload["findings"], list)
    assert isinstance(payload["summary"], str)
    assert all(len(finding["fingerprint"]) == 64 for finding in payload["findings"])
    assert {finding["freshness"] for finding in payload["findings"]} <= {"unknown"}
    assert lint_payload["tool"] == "lint"
    assert lint_payload["status"] in {"ok", "warn", "fail", "skipped"}
    assert isinstance(lint_payload["findings"], list)
    assert '"logger": "rush.mcp"' in server_stderr
    assert '"msg": "starting rush stdio MCP server"' in server_stderr
