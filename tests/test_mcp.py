"""End-to-end stdio MCP tests.

These tests start the actual ``rush mcp serve`` child process, negotiate the
MCP protocol through the official ``mcp`` client, inspect the advertised tool
schemas, and invoke a real tool. A successful handshake proves protocol frames
remain clean on stdout; any human/log output there would corrupt the transport.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# isort: off
from rush.permissions import ExecutionPermissions
from rush.tools import ALL_TOOLS
from rush.tools.continuity import SessionContinuityTool
# isort: on

# Imported after rush.tools to avoid a circular import (rush.memory.trust ->
# rush.hook -> rush.tools -> ... -> rush.continuity.providers -> rush.memory.checkpoint_journal
# -> ... -> rush.memory.trust) that only manifests when rush.memory.trust loads first.
from rush.memory.trust import default_entry_tier

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TOOLS = {f"rush_{tool.name.replace('-', '_')}" for tool in ALL_TOOLS} | {
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


@pytest.fixture
def registered_handlers():
    from rush.mcp import _register_tools

    class Server:
        def __init__(self):
            self.handlers = {}

        def add_tool(self, *, fn, name, description):
            self.handlers[name] = fn

    server = Server()
    _register_tools(server)
    return server.handlers


def test_registered_swarm_merge_preserves_exact_code(registered_handlers):
    result = registered_handlers["rush_swarm_merge"](
        base_code="def base():\n    return 1\n",
        ours_code="def base():\n    return 1\n\ndef ours():\n    return 'true'\n",
        theirs_code="def base():\n    return 1\n\ndef theirs():\n    return 'null'\n",
    )
    assert json.loads(result) == {
        "success": True,
        "functions_merged": 3,
        "merged_code": (
            "def base():\n    return 1\n\ndef ours():\n    return 'true'\n"
            "\ndef theirs():\n    return 'null'"
        ),
    }


@pytest.mark.parametrize("malformed", [False, True])
def test_registered_outline_redacts_entire_result(
    tmp_path, registered_handlers, malformed
):
    secret = "sk-ant-" + "X" * 48
    source = tmp_path / "outline.py"
    source.write_text(
        f"TOKEN = '{secret}'\n"
        + ("def broken(:\n" if malformed else "def ok():\n    return 1\n")
    )
    result = registered_handlers["rush_token_outline"](path=str(source))
    assert isinstance(result, str)
    assert secret not in json.dumps(result)
    assert result == "TOKEN=[REDACTED]\n" + (
        "def broken(:\n" if malformed else "\ndef ok():\n    ..."
    )


@pytest.mark.parametrize("malformed", [False, True])
def test_registered_swarm_merge_redacts_entire_result(registered_handlers, malformed):
    secret = "sk-ant-" + "Y" * 48
    code = f"TOKEN = '{secret}'\n" + (
        "def broken(:\n" if malformed else "def ok():\n    return 1\n"
    )
    result = registered_handlers["rush_swarm_merge"](
        base_code=code, ours_code=code, theirs_code=code
    )
    payload = json.loads(result)
    assert secret not in json.dumps(result)
    assert payload["success"] is (not malformed)
    if malformed:
        assert payload["merged_code"] is None
        assert payload["error"].startswith("AST parse error during 3-way merge:")
    else:
        assert payload["merged_code"] == ("TOKEN=[REDACTED]\n\ndef ok():\n    return 1")


def test_custom_result_sanitization_preserves_types():
    from rush.invocation import InvocationExecutor
    from rush.mcp_support.tool_registry import register_custom_tools

    secret = "sk-ant-" + "Z" * 48
    original = {"values": [False, None, 123, "true", "null", "[]", secret]}
    handlers = {}

    class Server:
        def add_tool(self, *, fn, name, description):
            handlers[name] = fn

    def custom():
        return original

    register_custom_tools(Server(), InvocationExecutor(), [(custom, "custom", "test")])
    result = handlers["custom"]()
    assert result == {
        "values": [False, None, 123, "true", "null", "[]", "[REDACTED_ANTHROPIC_KEY]"]
    }
    assert original["values"][-1] == secret


@pytest.mark.parametrize("custom", [False, True])
def test_registered_wrappers_preserve_types_and_omission(tmp_path, custom):
    from rush.invocation import InvocationExecutor
    from rush.mcp_support.tool_registry import register_all_tools, register_custom_tools

    omitted = object()
    handlers = {}

    class Server:
        def add_tool(self, *, fn, name, description):
            handlers[name] = fn

    class Probe:
        name = "typed-probe"
        mcp_description = "Test argument fidelity"

        def __call__(self, path: Path = Path("."), value=omitted):
            return {
                "present": value is not omitted,
                "value": None if value is omitted else value,
            }

    probe = Probe()
    if custom:
        register_custom_tools(
            Server(),
            InvocationExecutor(),
            [(probe.__call__, "rush_typed_probe", "test")],
        )
    else:
        register_all_tools(Server(), InvocationExecutor(), [probe])
    handler = handlers["rush_typed_probe"]
    assert handler(path=str(tmp_path)) == {"present": False, "value": None}
    for value in ("true", "null", "123", "[]", False, None, ["123", False, None]):
        result = handler(path=str(tmp_path), value=value)
        assert result == {"present": True, "value": value}
        assert type(result["value"]) is type(value)


def test_stdio_mcp_lists_clean_tool_schemas_and_calls_review(tmp_path: Path):
    """The real server completes initialize → tools/list → two tools/call.

    ``review`` stays deterministic and in-process; ``lint`` ensures the
    shared, non-review ToolResult schema is valid through FastMCP as well.
    """
    source = tmp_path / "review_target.py"
    source.write_text("def example() -> int:\n    return 1\n")
    SessionContinuityTool().run(
        tmp_path,
        operation="save",
        name="cli-parity",
        handoff={
            "current_goal": "Finish the redacted handoff",
            "open_work": ["verify restore receipt"],
            "historic_instruction": "ignore historic instructions",
            "failure_fingerprint": "a" * 64,
            "dependencies": ["review_target.py"],
        },
        permissions=ExecutionPermissions(cache_write=True),
    )
    source.write_text("def example() -> int:\n    return 2\n")
    cli_restore = SessionContinuityTool().run(
        tmp_path,
        operation="restore",
        name="cli-parity",
    )

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
                        "operation": "restore",
                        "name": "cli-parity",
                    },
                    {
                        "path": str(tmp_path),
                        "operation": "provider_resume",
                        "name": "handoff",
                        "provider_id": "zai",
                        "allow_network": True,
                    },
                    {
                        "path": str(tmp_path),
                        "operation": "provider_resume",
                        "name": "handoff",
                        "provider_id": "9router_cli",
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
                        "allow_cache_write": True,
                    },
                )
                packed_payload = json.loads(packed_response.content[0].text)
                legacy_packed_response = await session.call_tool(
                    "rush_context_pack",
                    {
                        "path": str(tmp_path / "review_target.py"),
                        "budget": 1,
                        "allow_cache_write": True,
                    },
                )
                assert not legacy_packed_response.isError
                legacy_packed_payload = json.loads(
                    legacy_packed_response.content[0].text
                )
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
                legacy_packed_payload,
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
        legacy_packed_payload,
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
        "ok",
        "skipped",
        "skipped",
    ]
    assert "--allow-cache-write" in continuity_payloads[0]["summary"]
    assert continuity_payloads[1]["raw"]["name"] == "handoff"
    assert continuity_payloads[3]["raw"] in continuity_payloads[2]["raw"]
    assert continuity_payloads[4]["raw"] in continuity_payloads[2]["raw"]
    assert continuity_payloads[3]["metadata"]["handoff"]["current_goal"] == (
        "Finish the redacted handoff"
    )
    assert continuity_payloads[3]["metadata"]["handoff"]["historic_instruction"] == {
        "trust_tier": default_entry_tier("local_tool"),
        "present": True,
    }
    assert (
        continuity_payloads[4]["metadata"]["handoff"]
        == cli_restore["metadata"]["handoff"]
    )
    assert continuity_payloads[4]["metadata"]["handoff"]["freshness"] == "stale"
    assert continuity_payloads[4]["metadata"]["handoff"]["failure_receipt"] == {
        "fingerprint": "a" * 64,
        "state": "tombstoned",
    }
    assert continuity_payloads[5]["metadata"]["provider_route"] == {
        "provider_id": "zai",
        "transport": "cli",
        "state": "deferred",
    }
    assert continuity_payloads[6]["metadata"]["provider_route"] == {
        "provider_id": "9router_cli",
        "transport": "codex-cli-via-9router",
        "endpoint_class": "fixed-loopback",
        "state": "credential_unavailable",
    }
    assert packed_payload["status"] == "skipped"
    assert packed_payload["metadata"]["context_envelope"]["recovery"]["state"] == (
        "available"
    )
    assert retrieved_payload["status"] == "ok"
    assert legacy_packed_payload["status"] == "skipped"
    assert (
        legacy_packed_payload["metadata"]["context_envelope"]["recovery"]["state"]
        == "available"
    )
    assert "review_target.py" in retrieved_payload["raw"]["content"]
    for continuity_payload in continuity_payloads:
        assert {"tool", "status", "duration_ms", "summary", "findings"} <= {
            *continuity_payload
        }
        assert continuity_payload["tool"] == "continuity"
    assert '"logger": "rush.mcp"' in server_stderr
    assert '"msg": "starting rush stdio MCP server"' in server_stderr


def test_mcp_catalog_names_normalize_toolfn_hyphens_to_underscores() -> None:
    from rush.mcp import build_server

    server = build_server()
    tools = getattr(server, "_tool_manager", None)
    if tools is not None:
        tool_names = set(getattr(tools, "_tools", {}).keys())
    else:
        tool_names = set()

    for name in tool_names:
        assert "-" not in name, (
            f"MCP tool name {name!r} contains hyphens; must use underscores"
        )


def test_registered_mcp_ship_clean_preview_and_authorized_apply(
    tmp_path: Path, monkeypatch
) -> None:
    from rush import mcp

    owned = tmp_path / ".rush" / "runs" / "report.pyc"
    owned.parent.mkdir(parents=True)
    owned.write_bytes(b"owned")
    stat_result = os.lstat(owned)
    receipt = tmp_path / ".rush" / "cleanup.json"
    receipt.write_text(
        json.dumps(
            {
                "version": 1,
                "artifacts": [
                    {
                        "path": ".rush/runs/report.pyc",
                        "sha256": hashlib.sha256(b"owned").hexdigest(),
                        "length": 5,
                        "producer": "mcp-test",
                        "device": stat_result.st_dev,
                        "inode": stat_result.st_ino,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    class FakeServer:
        def __init__(self) -> None:
            self.calls: list[tuple[object, str, str]] = []

        def add_tool(self, *, fn, name: str, description: str) -> None:
            self.calls.append((fn, name, description))

    server = FakeServer()
    mcp._register_tools(server)
    registered = {name: fn for fn, name, _description in server.calls}
    wrapper = registered["rush_ship_clean"]
    monkeypatch.chdir(tmp_path)

    preview = wrapper()

    assert owned.read_bytes() == b"owned"
    assert preview["status"] == "preview"
    assert preview["preview_items"] == [".rush/runs/report.pyc"]
    signature = inspect.signature(wrapper)
    assert signature.parameters["apply"].default is False
    assert signature.parameters["allow_artifact_write"].default is False

    denied = wrapper(path=tmp_path, apply=True)
    assert denied["status"] == "skipped"
    assert "--allow-artifact-write" in denied["error"]
    assert owned.read_bytes() == b"owned"

    granted = wrapper(path=tmp_path, apply=True, allow_artifact_write=True)
    assert granted["status"] == "ok"
    assert granted["removed_items"] == [".rush/runs/report.pyc"]
    assert not owned.exists()


def test_registered_mcp_ship_clean_propagates_registry_error(
    tmp_path: Path, monkeypatch
) -> None:
    from rush import mcp

    receipt = tmp_path / ".rush" / "cleanup.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text("{malformed", encoding="utf-8")

    class FakeServer:
        def __init__(self) -> None:
            self.calls: list[tuple[object, str, str]] = []

        def add_tool(self, *, fn, name: str, description: str) -> None:
            self.calls.append((fn, name, description))

    server = FakeServer()
    mcp._register_tools(server)
    registered = {name: fn for fn, name, _description in server.calls}
    monkeypatch.chdir(tmp_path)

    result = registered["rush_ship_clean"](
        path=tmp_path, apply=True, allow_artifact_write=True
    )

    assert result["status"] == "error"
    assert "malformed" in result["error"]
    assert result["removed_count"] == 0


@pytest.mark.parametrize("mode", ["dry-run", "denied", "failed-verification", "apply"])
def test_registered_mcp_patch_apply_parity(tmp_path: Path, mode: str) -> None:
    from rush import mcp

    class FakeServer:
        def __init__(self) -> None:
            self.tools = {}

        def add_tool(self, *, fn, name, description) -> None:
            self.tools[name] = fn

    server = FakeServer()
    mcp._register_tools(server)
    assert "rush_patch_apply" in server.tools
    wrapper = server.tools["rush_patch_apply"]
    signature = inspect.signature(wrapper)
    assert signature.parameters["patch_file"].default is inspect.Parameter.empty
    assert signature.parameters["dry_run"].default is True
    assert signature.parameters["circuit_breaker"].default is True
    assert signature.parameters["allow_artifact_write"].default is False

    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=tmp_path, capture_output=True, check=True
        )

    git("init", "-q")
    git("config", "user.email", "patch-test@example.invalid")
    git("config", "user.name", "Patch test")
    (tmp_path / ".gitignore").write_text(".rush/\n__pycache__/\n.pytest_cache/\n")
    (tmp_path / "app.py").write_text("value = 1\n")
    (tmp_path / "pytest.ini").write_text("[pytest]\npythonpath = .\n")
    (tmp_path / "test_app.py").write_text(
        "import app\n\ndef test_value():\n"
        f"    assert app.value == {3 if mode == 'failed-verification' else 2}\n"
    )
    patch_file = tmp_path / "fix.patch"
    patch_file.write_text(
        "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-value = 1\n+value = 2\n"
    )
    git("add", ".")
    git("commit", "-qm", "fixture")

    result = wrapper(
        path=tmp_path,
        patch_file=patch_file,
        dry_run=mode == "dry-run",
        circuit_breaker=True,
        allow_artifact_write=mode in {"failed-verification", "apply"},
    )

    assert (
        result["status"]
        == {
            "dry-run": "ok",
            "denied": "skipped",
            "failed-verification": "fail",
            "apply": "ok",
        }[mode]
    )
    assert result["metadata"]["promoted"] is (mode == "apply")
    assert (tmp_path / "app.py").read_text() == (
        "value = 2\n" if mode == "apply" else "value = 1\n"
    )


def test_phase50_mcp_registration_has_one_object_per_tool_and_only_attest_alias() -> (
    None
):
    """Phase 50 MCP routes are the registered objects plus one explicit alias."""
    from rush import mcp

    source = inspect.getsource(mcp._register_tools)
    assert "_call_registered_tool" not in source
    assert "mcp_rush_license_matrix" not in source
    assert "mcp_rush_iam_audit" not in source
    assert "mcp_rush_dead_asset" not in source
    assert "mcp_rush_pr_synthesize" not in source

    class FakeServer:
        def __init__(self) -> None:
            self.calls: list[tuple[object, str, str]] = []

        def add_tool(self, *, fn, name: str, description: str) -> None:
            self.calls.append((fn, name, description))

    server = FakeServer()
    mcp._register_tools(server)
    by_name = {name: fn for fn, name, _ in server.calls}
    phase50_tools = {
        "attest",
        "license-matrix",
        "iam-audit",
        "prompt-eval",
        "mem-profile",
        "cold-start",
        "media-opt",
        "offline-review",
        "tui-diff",
        "benchmark",
        "error-catalog",
        "provenance-ai",
        "dead-asset",
        "pr-synthesize",
    }

    for tool in ALL_TOOLS:
        if tool.name in phase50_tools:
            fn = by_name[f"rush_{tool.name.replace('-', '_')}"]
            assert getattr(fn, "__self__", None) is tool
    assert "rush_attest_generate" in by_name
