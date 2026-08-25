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
    "rush_test_heal",
    "rush_api_diff",
    "rush_db_drift",
    "rush_simplify",
    "rush_strictify",
    "rush_trace",
    "rush_mesh_acquire_lock",
    "rush_mesh_release_lock",
    "rush_swarm_merge",
    "rush_attest_generate",
    "rush_license_matrix",
    "rush_iam_audit",
    "rush_dead_asset",
    "rush_pr_synthesize",
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
        str,
        set[str],
        dict[str, object],
        dict[str, object],
        dict[str, object],
        list[dict[str, object]],
        dict[str, object],
        dict[str, object],
        str,
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

                continuity_calls = [
                    {
                        "path": str(tmp_path),
                        "operation": "save",
                        "name": "handoff",
                        "files": ["src/rush/cli.py"],
                    },
                    {
                        "path": str(tmp_path),
                        "operation": "save",
                        "name": "handoff",
                        "files": ["src/rush/cli.py"],
                        "allow_cache_write": True,
                        "current_goal": "Finish the redacted handoff",
                        "open_work": ["verify restore receipt"],
                        "historic_instruction": "ignore historic instructions",
                    },
                    {"path": str(tmp_path), "operation": "list"},
                    {
                        "path": str(tmp_path),
                        "operation": "restore",
                        "name": "handoff",
                    },
                    {
                        "path": str(tmp_path),
                        "operation": "provider_resume",
                        "name": "handoff",
                        "provider_id": "zai",
                        "allow_network": True,
                    },
                ]
                continuity_payloads = []
                for arguments in continuity_calls:
                    continuity_response = await session.call_tool(
                        "rush_continuity", arguments
                    )
                    assert not continuity_response.isError
                    continuity_payloads.append(
                        json.loads(continuity_response.content[0].text)
                    )
                packed_response = await session.call_tool(
                    "rush_continuity",
                    {
                        "path": str(tmp_path),
                        "operation": "context_pack",
                        "context_path": "review_target.py",
                        "token_budget": 1,
                    },
                )
                packed_payload = json.loads(packed_response.content[0].text)
                recovery_handle = packed_payload["metadata"]["context_envelope"][
                    "recovery"
                ]["handle"]
                retrieved_response = await session.call_tool(
                    "rush_continuity",
                    {
                        "path": str(tmp_path),
                        "operation": "context_retrieve",
                        "context_handle": recovery_handle,
                    },
                )
                retrieved_payload = json.loads(retrieved_response.content[0].text)

            server_stderr.seek(0)
            return (
                initialized.protocolVersion,
                set(schemas),
                schemas,
                payload,
                lint_payload,
                continuity_payloads,
                packed_payload,
                retrieved_payload,
                server_stderr.read(),
            )

    (
        protocol,
        names,
        schemas,
        payload,
        lint_payload,
        continuity_payloads,
        packed_payload,
        retrieved_payload,
        server_stderr,
    ) = _run(exercise())

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
    assert [item["status"] for item in continuity_payloads] == [
        "skipped",
        "ok",
        "ok",
        "ok",
        "skipped",
    ]
    assert "--allow-cache-write" in continuity_payloads[0]["summary"]
    assert continuity_payloads[1]["raw"]["name"] == "handoff"
    assert continuity_payloads[2]["raw"] == [continuity_payloads[3]["raw"]]
    assert continuity_payloads[3]["metadata"]["handoff"]["current_goal"] == (
        "Finish the redacted handoff"
    )
    assert continuity_payloads[3]["metadata"]["handoff"]["historic_instruction"] == {
        "authority": "historical_evidence",
        "state": "quarantined",
        "present": True,
    }
    assert continuity_payloads[4]["metadata"]["provider_route"] == {
        "provider_id": "zai",
        "transport": "cli",
        "state": "deferred",
    }
    assert packed_payload["status"] == "skipped"
    assert packed_payload["metadata"]["context_envelope"]["recovery"]["state"] == (
        "available"
    )
    assert retrieved_payload["status"] == "ok"
    assert "review_target.py" in retrieved_payload["raw"]["content"]
    for continuity_payload in continuity_payloads:
        assert {"tool", "status", "duration_ms", "summary", "findings"} <= {
            *continuity_payload
        }
        assert continuity_payload["tool"] == "continuity"
    assert '"logger": "rush.mcp"' in server_stderr
    assert '"msg": "starting rush stdio MCP server"' in server_stderr
