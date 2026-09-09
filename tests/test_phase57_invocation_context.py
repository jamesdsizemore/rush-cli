"""Tests for Phase 57 Invocation Context, immutability, and dual-transport parity.

Contracts:
- T-57.01: Equivalent InvocationContext resolution across CLI and MCP transports.
- T-57.02: Zero mutable config leaks to MCP requests; deepcopy / frozen immutability.
- T-57.03 (R-007): Dual-transport parity across all 10 core quality tools.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from types import MappingProxyType

import pytest

from rush.contracts.results import ToolResultV1, adapt_legacy_tool_result
from rush.invocation import (
    InvocationContext,
    ScopeWideningError,
    decide_cache,
    resolve_invocation,
)
from rush.invocation.executor import InvocationExecutor
from rush.mcp import build_server
from rush.tools import ALL_TOOLS

CORE_QUALITY_TOOLS: tuple[str, ...] = (
    "continuity",
    "semantic-drift",
    "review",
    "lint",
    "format",
    "test",
    "security",
    "typecheck",
    "dead",
    "complexity",
)


def test_invocation_preserves_scalar_types_and_presence(tmp_path: Path) -> None:
    executor = InvocationExecutor()
    executor.register("capture", lambda **kwargs: kwargs)

    literal = resolve_invocation(
        {
            "operation_id": "capture",
            "boolean": "true",
            "nullable": "null",
            "number": "123",
            "items": "[]",
        },
        transport="mcp",
        workspace_root=tmp_path,
    )
    actual = resolve_invocation(
        {
            "operation_id": "capture",
            "boolean": False,
            "nullable": None,
            "number": 123,
            "items": [],
        },
        transport="mcp",
        workspace_root=tmp_path,
    )
    omitted = resolve_invocation(
        {"operation_id": "capture"},
        transport="mcp",
        workspace_root=tmp_path,
    )

    assert executor.execute(literal) == {
        "boolean": "true",
        "nullable": "null",
        "number": "123",
        "items": "[]",
    }
    assert executor.execute(actual) == {
        "boolean": False,
        "nullable": None,
        "number": 123,
        "items": [],
    }
    assert executor.execute(omitted) == {}

    legacy = resolve_invocation(
        {
            "operation_id": "capture",
            "ordered_args": ["--boolean=false", "--nullable=null", "--items=[]"],
        },
        transport="mcp",
        workspace_root=tmp_path,
    )
    assert executor.execute(legacy) == {
        "boolean": False,
        "nullable": None,
        "items": [],
    }
    assert (
        executor.execute(replace(legacy, typed_args=(), ordered_args=("--value=true",)))
        == {}
    )

    typed_empty_record = json.loads(
        json.dumps(
            {
                "operation_id": "capture",
                "typed_args": omitted.typed_args,
                "ordered_args": ["--value=true"],
            }
        )
    )
    replayed_empty = resolve_invocation(
        typed_empty_record,
        transport="mcp",
        workspace_root=tmp_path,
    )
    assert replayed_empty.typed_args == ()
    assert executor.execute(replayed_empty) == {}

    legacy_record = json.loads(
        json.dumps(
            {
                "operation_id": "capture",
                "ordered_args": ["--value=false", "--nullable=null"],
            }
        )
    )
    replayed_legacy = resolve_invocation(
        legacy_record,
        transport="mcp",
        workspace_root=tmp_path,
    )
    assert replayed_legacy.typed_args is None
    assert executor.execute(replayed_legacy) == {"value": False, "nullable": None}

    assert decide_cache(literal).cache_key != decide_cache(actual).cache_key

    persisted_one = resolve_invocation(
        {
            "operation_id": "capture",
            "typed_args": [["value", "one"]],
            "ordered_args": ["--value=legacy"],
        },
        transport="mcp",
        workspace_root=tmp_path,
    )
    persisted_two = resolve_invocation(
        {
            "operation_id": "capture",
            "typed_args": [["value", "two"]],
            "ordered_args": ["--value=legacy"],
        },
        transport="mcp",
        workspace_root=tmp_path,
    )
    assert (
        decide_cache(persisted_one).cache_key != decide_cache(persisted_two).cache_key
    )

    for invalid_name in ("path", "allow_artifact_write"):
        with pytest.raises(ValueError, match="typed_args names"):
            resolve_invocation(
                {
                    "operation_id": "capture",
                    "typed_args": [[invalid_name, True]],
                },
                transport="mcp",
                workspace_root=tmp_path,
            )


def test_cli_and_mcp_resolve_equivalent_context(tmp_path: Path) -> None:
    """T-57.01: Asserts CLI and MCP requests with identical inputs produce equal InvocationContext."""
    workspace = tmp_path.resolve()
    target_file = workspace / "module.py"
    target_file.write_text(
        "def hello() -> str:\n    return 'world'\n", encoding="utf-8"
    )

    config = {
        "tools": {
            "lint": {"rules": ["E", "W"]},
            "format": {"line_length": 88},
        },
        "cache": {"enabled": True},
    }
    permissions = ["cache_write", "network"]

    cli_request = {
        "operation_id": "lint",
        "path": str(target_file),
        "args": ["--verbose"],
    }
    mcp_request = {
        "operation_id": "lint",
        "path": str(target_file),
        "args": ["--verbose"],
    }

    ctx_cli = resolve_invocation(
        cli_request,
        transport="cli",
        workspace_root=workspace,
        config=config,
        permissions=permissions,
    )
    ctx_mcp = resolve_invocation(
        mcp_request,
        transport="mcp",
        workspace_root=workspace,
        config=config,
        permissions=permissions,
    )

    # Both objects are instances of InvocationContext
    assert isinstance(ctx_cli, InvocationContext)
    assert isinstance(ctx_mcp, InvocationContext)

    # Specific transport field is preserved
    assert ctx_cli.transport == "cli"
    assert ctx_mcp.transport == "mcp"

    # Contexts are semantically equivalent
    assert ctx_cli == ctx_mcp

    # Digest and permissions snapshots match exactly
    assert ctx_cli.effective_config_digest == ctx_mcp.effective_config_digest
    assert len(ctx_cli.effective_config_digest) == 64
    assert ctx_cli.permissions == ctx_mcp.permissions == ("cache_write", "network")

    # Target path, hash, and metadata match
    assert len(ctx_cli.targets) == 1
    assert ctx_cli.targets == ctx_mcp.targets
    target = ctx_cli.targets[0]
    assert target.relative_path == Path("module.py")
    assert target.state == "present"
    assert len(target.content_hash) == 64

    # Workspace root, environment digest, and cache policy match
    assert ctx_cli.workspace_root == ctx_mcp.workspace_root == workspace
    assert ctx_cli.environment_digest == ctx_mcp.environment_digest
    assert len(ctx_cli.environment_digest) == 64
    assert ctx_cli.cache_policy == ctx_mcp.cache_policy == "eligible"
    assert ctx_cli.ordered_args == ctx_mcp.ordered_args == ("--verbose",)


def test_mcp_request_never_receives_mutable_config(tmp_path: Path) -> None:
    """T-57.02: Asserts MCP requests receive a frozen/deep copy of declared values."""
    workspace = tmp_path.resolve()
    target = workspace / "sample.py"
    target.write_text("a = 1\n", encoding="utf-8")

    declared_config = {
        "tools": {
            "review": {"max_file_lines": 250, "weights": [1, 2, 3]},
            "lint": {"ignored": ["W503"]},
        },
        "nested": {"level1": {"level2": "immutable_anchor"}},
    }
    mcp_request = {
        "operation_id": "review",
        "path": str(target),
        "config": declared_config,
    }

    ctx = resolve_invocation(
        mcp_request,
        transport="mcp",
        workspace_root=workspace,
        config=declared_config,
        permissions=["network"],
    )

    initial_digest = ctx.effective_config_digest
    assert len(initial_digest) == 64

    # Invariant: InvocationContext is frozen
    with pytest.raises(FrozenInstanceError):
        ctx.effective_config_digest = "tampered_digest"  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        ctx.workspace_root = Path("/tampered")  # type: ignore[misc]

    # Invariant: Mutating declared_config afterwards has zero effect on the resolved context
    declared_config["tools"]["review"]["max_file_lines"] = 9999
    declared_config["tools"]["review"]["weights"].append(4)
    declared_config["nested"]["level1"]["level2"] = "mutated_value"
    declared_config["injected_leak"] = True

    # Invariant: Mutating original request dict has zero effect on resolved context
    mcp_request["operation_id"] = "tampered_operation"

    # Digested state and attributes remain strictly unchanged
    assert ctx.effective_config_digest == initial_digest
    assert ctx.operation_id == "review"
    assert ctx.targets[0].relative_path == Path("sample.py")

    # Mutating path to escape workspace boundary must trigger ScopeWideningError
    escaping_request = dict(mcp_request, path="../../escape_target.py")
    with pytest.raises(ScopeWideningError):
        resolve_invocation(
            escaping_request,
            transport="mcp",
            workspace_root=workspace,
            config=declared_config,
        )

    # A subsequent resolution with the mutated config produces a divergent digest,
    # proving the initial context was deeply isolated and not coupled to the mutated dict.
    valid_mutated_request = dict(mcp_request, path=str(target))
    ctx_subsequent = resolve_invocation(
        valid_mutated_request,
        transport="mcp",
        workspace_root=workspace,
        config=declared_config,
        permissions=["network"],
    )
    assert ctx_subsequent.effective_config_digest != initial_digest
    assert ctx.effective_config_digest == initial_digest


def test_invocation_accepts_immutable_typed_tool_config(tmp_path: Path) -> None:
    options = {
        "dynamic": True,
        "limit": 3,
        "nullable": None,
        "paths": ("src", "tests"),
    }
    frozen_options = MappingProxyType(options)

    frozen_context = resolve_invocation(
        {"operation_id": "mem-profile"},
        transport="cli",
        workspace_root=tmp_path,
        config=frozen_options,
    )
    mutable_context = resolve_invocation(
        {"operation_id": "mem-profile"},
        transport="cli",
        workspace_root=tmp_path,
        config=options,
    )

    assert (
        frozen_context.effective_config_digest
        == mutable_context.effective_config_digest
    )
    assert options == {
        "dynamic": True,
        "limit": 3,
        "nullable": None,
        "paths": ("src", "tests"),
    }


def test_dual_transport_parity_across_transports(tmp_path: Path) -> None:
    """T-57.03 (R-007): Asserts dual-transport parity across CLI and MCP for all 10 core quality tools."""
    workspace = tmp_path.resolve()
    # Create git boundary so test engine skips safely and immediately
    (workspace / ".git").mkdir()

    sample_file = workspace / "parity_test.py"
    sample_file.write_text("def ping() -> str:\n    return 'pong'\n", encoding="utf-8")

    server = build_server()

    for tool_name in CORE_QUALITY_TOOLS:
        tool_fn = next((t for t in ALL_TOOLS if t.name == tool_name), None)
        assert tool_fn is not None, (
            f"Tool '{tool_name}' must be registered in ALL_TOOLS"
        )

        mcp_tool_name = f"rush_{tool_name.replace('-', '_')}"

        # Identical parameter dict for both transports
        params: dict[str, object] = {
            "path": str(
                sample_file
                if tool_name not in ("continuity", "semantic-drift")
                else workspace
            )
        }
        if tool_name == "continuity":
            params["operation"] = "list"
        elif tool_name == "format":
            params["check"] = True

        # MCP Transport invocation
        mcp_response, _ = asyncio.run(server.call_tool(mcp_tool_name, params))
        assert mcp_response, f"MCP call for {tool_name} returned empty response"
        mcp_dict = json.loads(mcp_response[0].text)
        mcp_v1 = adapt_legacy_tool_result(mcp_dict)

        # CLI Transport invocation
        cli_kwargs = {
            k: Path(v) if k == "path" and isinstance(v, str) else v
            for k, v in params.items()
        }
        cli_raw = tool_fn(**cli_kwargs)
        cli_v1 = adapt_legacy_tool_result(cli_raw)

        # Assert ToolResultV1 shape compliance
        assert isinstance(mcp_v1, ToolResultV1), (
            f"MCP result for {tool_name} not ToolResultV1"
        )
        assert isinstance(cli_v1, ToolResultV1), (
            f"CLI result for {tool_name} not ToolResultV1"
        )
        assert mcp_v1.schema_version == "1.0.0"
        assert cli_v1.schema_version == "1.0.0"
        assert mcp_v1.tool == tool_name
        assert cli_v1.tool == tool_name

        # Assert identical status and engine resolution across transports
        assert mcp_v1.status == cli_v1.status, (
            f"Transport status divergence on tool '{tool_name}': MCP={mcp_v1.status} != CLI={cli_v1.status}"
        )
        assert mcp_v1.engine == cli_v1.engine, (
            f"Transport engine divergence on tool '{tool_name}': MCP={mcp_v1.engine} != CLI={cli_v1.engine}"
        )

        # Assert InvocationContext resolution parity for both transports
        ctx_cli = resolve_invocation(params, transport="cli", workspace_root=workspace)
        ctx_mcp = resolve_invocation(params, transport="mcp", workspace_root=workspace)
        assert ctx_cli == ctx_mcp
        assert ctx_cli.effective_config_digest == ctx_mcp.effective_config_digest
