"""Tests for Phase 57 Public Operations, Single Execution Boundary, and Signature Adaptation.

Contracts:
- T-57.07: Single execution invariant: internal TypeError propagates without retry; side effect executes strictly once.
- T-57.08: Registration-time validation: incompatible/unsupported callable signatures fail immediately with SignatureAdaptationError.
- T-57.09: Transport equivalence: CLI and MCP adapters produce equivalent diagnostic error structures for signature mismatch.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from rush.contracts.results import ToolResultV1
from rush.invocation import (
    InvocationContext,
    InvocationExecutor,
    RegisteredOperation,
    SignatureAdaptationError,
    adapt_signature_at_registration,
    format_signature_error_diagnostic,
    resolve_invocation,
)


def test_internal_typeerror_after_side_effect_executes_once(tmp_path: Path) -> None:
    """T-57.07: Asserts callable raising internal TypeError executes side-effect strictly once (no retry)."""
    workspace = tmp_path.resolve()
    sentinel_file = workspace / "side_effect_sentinel.txt"
    side_effect_counter = 0

    def faulty_tool(path: Path) -> ToolResultV1:
        nonlocal side_effect_counter
        side_effect_counter += 1
        sentinel_file.write_text(f"run_count_{side_effect_counter}", encoding="utf-8")
        # Simulate internal logic failure that raises TypeError
        msg: str = "cannot add int to string"
        bad_val: Any = 123
        raise TypeError(f"Internal calculation fault: {msg} {bad_val}")

    executor = InvocationExecutor()
    op = executor.register("faulty_op", faulty_tool)
    assert isinstance(op, RegisteredOperation)
    assert op.operation_id == "faulty_op"
    assert op.pure is False

    request = {
        "operation_id": "faulty_op",
        "path": str(workspace),
    }
    context = resolve_invocation(request, transport="cli", workspace_root=workspace)

    # Invariant: TypeError propagates directly and is not swallowed or retried
    with pytest.raises(TypeError, match="Internal calculation fault"):
        executor.execute(context)

    # Invariant: Side effect executed strictly once; zero fallback retry attempts
    assert side_effect_counter == 1
    assert sentinel_file.read_text(encoding="utf-8") == "run_count_1"

    # Also verify with a tool taking context directly
    ctx_counter = 0

    def faulty_context_tool(ctx: InvocationContext) -> ToolResultV1:
        nonlocal ctx_counter
        ctx_counter += 1
        raise TypeError("Context tool internal TypeError")

    executor.register("faulty_ctx_op", faulty_context_tool)
    ctx_context = resolve_invocation(
        {"operation_id": "faulty_ctx_op"},
        transport="mcp",
        workspace_root=workspace,
    )

    with pytest.raises(TypeError, match="Context tool internal TypeError"):
        executor.execute(ctx_context)

    assert ctx_counter == 1


def test_unsupported_signature_fails_registration() -> None:
    """T-57.08: Asserts registering an unresolvable signature raises SignatureAdaptationError immediately."""
    executor = InvocationExecutor()

    # Incompatible signature: requires parameters that cannot be satisfied by InvocationContext
    def incompatible_callable(
        unknown_mandatory_service: object, external_db: str
    ) -> None:
        pass

    with pytest.raises(SignatureAdaptationError) as exc_info:
        executor.register("unsupported_op", incompatible_callable)

    err = exc_info.value
    assert err.operation_id == "unsupported_op"
    assert err.param_name == "unknown_mandatory_service"
    assert "unknown_mandatory_service" in str(err)

    # Direct call to adapt_signature_at_registration must also fail immediately
    with pytest.raises(SignatureAdaptationError):
        adapt_signature_at_registration(incompatible_callable)

    # Incompatible signature with unresolvable positional-only parameter
    def unresolvable_positional_only(unknown_arg: int, /) -> None:
        pass

    with pytest.raises(SignatureAdaptationError) as exc_pos:
        executor.register("pos_only_op", unresolvable_positional_only)

    assert exc_pos.value.operation_id == "pos_only_op"
    assert exc_pos.value.param_name == "unknown_arg"

    # Incompatible signature with invalid keyword parameters that cannot be adapted
    def incompatible_kwargs(unbound_required_kw: str, *, flag: bool = False) -> None:
        pass

    with pytest.raises(SignatureAdaptationError):
        executor.register("bad_kw_op", incompatible_kwargs)


def test_cli_mcp_signature_error_is_equivalent() -> None:
    """T-57.09: Asserts CLI and MCP signature mismatch errors produce equivalent diagnostic error structures."""

    def unadaptable_callable(unresolvable_mandatory: int, missing_token: str) -> None:
        pass

    # Simulate signature inspection mismatch for both CLI and MCP adapters
    executor_cli = InvocationExecutor()
    executor_mcp = InvocationExecutor()

    with pytest.raises(SignatureAdaptationError) as exc_cli:
        executor_cli.register("mismatch_op", unadaptable_callable)

    with pytest.raises(SignatureAdaptationError) as exc_mcp:
        executor_mcp.register("mismatch_op", unadaptable_callable)

    cli_error = exc_cli.value
    mcp_error = exc_mcp.value

    # Extract diagnostic structures for both transports
    cli_diagnostic = format_signature_error_diagnostic(cli_error, transport="cli")
    mcp_diagnostic = format_signature_error_diagnostic(mcp_error, transport="mcp")

    # Asserts both transports produce equivalent diagnostic error structures
    assert cli_diagnostic["status"] == mcp_diagnostic["status"] == "error"
    assert (
        cli_diagnostic["error_type"]
        == mcp_diagnostic["error_type"]
        == "SignatureAdaptationError"
    )
    assert (
        cli_diagnostic["diagnostic_code"]
        == mcp_diagnostic["diagnostic_code"]
        == "SIGNATURE_ADAPTATION_FAILED"
    )
    assert (
        cli_diagnostic["operation_id"]
        == mcp_diagnostic["operation_id"]
        == "mismatch_op"
    )
    assert (
        cli_diagnostic["param_name"]
        == mcp_diagnostic["param_name"]
        == "unresolvable_mandatory"
    )
    assert cli_diagnostic["message"] == mcp_diagnostic["message"]
    assert cli_diagnostic["transport"] == "cli"
    assert mcp_diagnostic["transport"] == "mcp"

    # Ensure structural schema matches exactly (excluding transport label)
    cli_keys = {k: type(v) for k, v in cli_diagnostic.items() if k != "transport"}
    mcp_keys = {k: type(v) for k, v in mcp_diagnostic.items() if k != "transport"}
    assert cli_keys == mcp_keys

    # Also test error object's native to_dict() equivalent structure
    assert cli_error.to_dict() == mcp_error.to_dict()


# ---------------------------------------------------------------------------
# T-57.10 (R-004): test_transport_contracts_reconcile_with_operation_manifest
# ---------------------------------------------------------------------------


def test_transport_contracts_reconcile_with_operation_manifest() -> None:
    """T-57.10 (R-004): Asserts all 153 operations in public-operations.toml reconcile with registry and executor."""
    import tomllib

    from rush.contracts.operations import (
        AdminOperationAdapter,
        ServiceOperationAdapter,
        ToolOperationAdapter,
        get_operation_registry,
    )
    from rush.invocation import InvocationExecutor

    manifest_path = Path("governance/public-operations.toml")
    with open(manifest_path, "rb") as f:
        manifest_data = tomllib.load(f)

    operations = manifest_data.get("operations", [])
    assert len(operations) == 153
    assert manifest_data.get("manifest", {}).get("total_operations") == 153

    # 1. Assert all operations are valid and have declared transport modes
    declared_transports: dict[str, str] = {}
    for op in operations:
        op_id = op.get("id")
        assert op_id and isinstance(op_id, str), f"Invalid or missing op id: {op}"
        assert op.get("kind") in ("tool", "admin", "service"), f"Invalid op kind: {op}"
        assert op.get("effect_class") in (
            "read-only",
            "idempotent-write",
            "stateful-mutation",
        ), f"Invalid effect_class in {op_id}"
        assert op.get("output_contract") in (
            "ToolResult",
            "ToolResultV1",
            "ClickExitCode",
            "AdminJsonContract",
            "McpCallResult",
            "ServiceProtocol",
            "RawResult",
        ), f"Invalid output_contract in {op_id}"

        has_cli = bool(op.get("cli_command"))
        has_mcp = bool(op.get("mcp_tool"))
        assert has_cli or has_mcp, f"Operation {op_id} has no declared transport"

        if has_cli and has_mcp:
            declared_transports[op_id] = "both"
        elif has_cli:
            declared_transports[op_id] = "cli"
        else:
            declared_transports[op_id] = "mcp"

    assert len(declared_transports) == 153
    # 62 dual-transport, 74 cli-only, 17 mcp-only
    assert sum(1 for t in declared_transports.values() if t == "both") == 62
    assert sum(1 for t in declared_transports.values() if t == "cli") == 74
    assert sum(1 for t in declared_transports.values() if t == "mcp") == 17

    # 2. Reconcile with OperationRegistry
    registry = get_operation_registry()
    report = registry.reconcile_manifest(manifest_path)
    assert report["total"] == 153
    assert report["tool_count"] == 71
    assert report["admin_count"] == 65
    assert report["service_count"] == 17
    assert len(report["unmapped"]) == 0
    assert len(report["errors"]) == 0

    for op in operations:
        op_id = op["id"]
        adapter = registry.get_adapter(op_id)
        assert adapter is not None, f"Operation {op_id} missing adapter in registry"
        assert adapter.operation_id == op_id
        assert adapter.kind == op["kind"]
        if op["kind"] == "tool":
            assert isinstance(adapter, ToolOperationAdapter)
        elif op["kind"] == "admin":
            assert isinstance(adapter, AdminOperationAdapter)
        elif op["kind"] == "service":
            assert isinstance(adapter, ServiceOperationAdapter)

    # 3. Reconcile with InvocationExecutor
    executor = registry.get_executor()
    assert isinstance(executor, InvocationExecutor)
    for op in operations:
        op_id = op["id"]
        reg_op = executor.get_registered(op_id)
        assert reg_op is not None, f"Operation {op_id} not registered in executor"
        assert reg_op.operation_id == op_id


# ---------------------------------------------------------------------------
# T-57.11: test_every_retained_operation_reaches_manifest_implementation
# ---------------------------------------------------------------------------


def test_every_retained_operation_reaches_manifest_implementation() -> None:
    """T-57.11: Verifies operations in registry map to real callable implementations with no stubs."""
    import importlib
    import inspect
    import tomllib

    from rush.contracts.operations import get_operation_registry

    manifest_path = Path("governance/public-operations.toml")
    with open(manifest_path, "rb") as f:
        manifest_data = tomllib.load(f)

    operations = manifest_data.get("operations", [])
    registry = get_operation_registry()

    for op in operations:
        op_id = op["id"]
        adapter = registry.get_adapter(op_id)
        assert adapter is not None, f"Operation {op_id} missing adapter"

        canonical_impl = op.get("canonical_impl")
        assert canonical_impl and ":" in canonical_impl, (
            f"Operation {op_id} missing valid canonical_impl: {canonical_impl}"
        )

        mod_name, symbol_name = canonical_impl.split(":", 1)
        mod = importlib.import_module(mod_name)
        assert mod is not None, f"Could not import module {mod_name} for {op_id}"

        target = getattr(mod, symbol_name, None)
        if target is None and hasattr(mod, "cli") and hasattr(mod.cli, "commands"):
            target = mod.cli.commands.get(symbol_name)
        if target is None and hasattr(mod, "build_server"):
            server = mod.build_server()
            if symbol_name in server._tool_manager._tools:
                target = server._tool_manager._tools[symbol_name].fn
            elif f"rush_{symbol_name}" in server._tool_manager._tools:
                target = server._tool_manager._tools[f"rush_{symbol_name}"].fn

        assert target is not None, (
            f"Could not resolve callable symbol '{symbol_name}' in '{mod_name}' for operation '{op_id}'"
        )
        assert callable(target), (
            f"Target '{symbol_name}' for operation '{op_id}' is not callable"
        )

        # Invariant: Zero placeholder / deferred stubs returning "unknown" or "deferred"
        try:
            source = inspect.getsource(target)
            assert 'return "unknown"' not in source, (
                f"Stub returning 'unknown' in {op_id}"
            )
            assert "return 'unknown'" not in source, (
                f"Stub returning 'unknown' in {op_id}"
            )
            assert 'return "deferred"' not in source, (
                f"Stub returning 'deferred' in {op_id}"
            )
            assert "return 'deferred'" not in source, (
                f"Stub returning 'deferred' in {op_id}"
            )
            assert "raise NotImplementedError" not in source, (
                f"Unimplemented stub in {op_id}"
            )
        except (TypeError, OSError):
            pass


# ---------------------------------------------------------------------------
# T-57.12: test_only_tool_pairs_require_semantic_parity
# ---------------------------------------------------------------------------


def test_only_tool_pairs_require_semantic_parity() -> None:
    """T-57.12: Asserts dual-transport parity is strictly required for tool pairs, while admin/service keep distinct contracts."""
    import tomllib

    from rush.contracts.operations import (
        AdminOperationAdapter,
        ServiceOperationAdapter,
        ToolOperationAdapter,
        get_operation_registry,
    )
    from rush.contracts.results import ToolResultV1, ValidationErrorV1

    manifest_path = Path("governance/public-operations.toml")
    with open(manifest_path, "rb") as f:
        manifest_data = tomllib.load(f)

    operations = manifest_data.get("operations", [])
    registry = get_operation_registry()

    paired_ops = [
        op for op in operations if op.get("cli_command") and op.get("mcp_tool")
    ]
    assert len(paired_ops) == 62

    # 1. All paired operations MUST be kind == "tool" and enforce ToolResultV1,
    #    except deliberately dual-transport admin mutations (e.g. memory
    #    write/promote, routed through the shared "rush_memory" MCP tool)
    #    which keep RawResult/AdminOperationAdapter semantics, validated by
    #    the admin block below instead of the tool-parity checks here.
    for op in paired_ops:
        if op["kind"] == "admin":
            assert op["output_contract"] == "RawResult", (
                f"Dual-transport admin operation {op['id']} must use RawResult"
            )
            continue
        assert op["kind"] == "tool", f"Paired operation {op['id']} must be kind='tool'"
        assert op["output_contract"] in ("ToolResult", "ToolResultV1")
        adapter = registry.get_adapter(op["id"])
        assert isinstance(adapter, ToolOperationAdapter)
        assert adapter.target_contract_id in ("ToolResult", "ToolResultV1")

        # Must validate output as ToolResultV1
        dummy_tool_result = ToolResultV1(
            schema_version="1.0.0",
            tool=op["id"],
            engine="test-engine",
            engine_version="1.0.0",
            status="ok",
            duration_ms=5,
            summary="sample tool output",
            findings=[],
        )
        validated = adapter.validate_output(dummy_tool_result)
        assert isinstance(validated, ToolResultV1)

        # Invalid shape must fail
        with pytest.raises(ValidationErrorV1):
            adapter.validate_output({"invalid": "shape"})

    # 2. Admin operations must retain ClickExitCode / AdminJsonContract without ToolResultV1 parity.
    #    Exception: deliberately dual-transport admin mutations (memory write/promote,
    #    routed through the shared "rush_memory" MCP tool per its RawResult contract)
    #    are allowed both transports, unlike every other admin operation.
    admin_ops = [op for op in operations if op["kind"] == "admin"]
    assert len(admin_ops) == 65
    _dual_transport_admin_ids = {"admin.memory_promote", "admin.memory_write"}
    for op in admin_ops:
        if op["id"] not in _dual_transport_admin_ids:
            assert not (op.get("cli_command") and op.get("mcp_tool")), (
                f"Admin operation {op['id']} should not be a dual-transport tool pair"
            )
        adapter = registry.get_adapter(op["id"])
        assert isinstance(adapter, AdminOperationAdapter)
        assert adapter.target_contract_id in ("ClickExitCode", "AdminJsonContract")
        assert adapter.validate_output(0) == 0
        assert adapter.validate_output(1) == 1
        assert adapter.validate_output(2) == 2

    # 3. Service operations must retain ServiceProtocol / McpCallResult and reject ToolResultV1 wrapping
    service_ops = [op for op in operations if op["kind"] == "service"]
    assert len(service_ops) == 17
    for op in service_ops:
        assert not (op.get("cli_command") and op.get("mcp_tool")), (
            f"Service operation {op['id']} should not be a dual-transport tool pair"
        )
        adapter = registry.get_adapter(op["id"])
        assert isinstance(adapter, ServiceOperationAdapter)
        assert adapter.target_contract_id in ("ServiceProtocol", "McpCallResult")

        raw_frame = {"jsonrpc": "2.0", "result": {"capabilities": {}}}
        assert adapter.validate_output(raw_frame) == raw_frame

        dummy_service_result = ToolResultV1(
            schema_version="1.0.0",
            tool=op["id"],
            engine="test-engine",
            engine_version="1.0.0",
            status="ok",
            duration_ms=0,
            summary="illegal wrap",
            findings=[],
        )
        with pytest.raises(ValidationErrorV1) as exc_info:
            adapter.validate_output(dummy_service_result)
        assert exc_info.value.code == "INVALID_SERVICE_CONTRACT"


# ---------------------------------------------------------------------------
# T-57.13: test_unprobed_route_is_not_advertised
# ---------------------------------------------------------------------------


def test_unprobed_route_is_not_advertised() -> None:
    """T-57.13: Scans CLI commands and FastMCP tools; asserts every advertised route maps to declared operation in manifest."""
    import tomllib

    import click

    import rush.mcp
    from rush.cli import cli

    manifest_path = Path("governance/public-operations.toml")
    with open(manifest_path, "rb") as f:
        manifest_data = tomllib.load(f)

    operations = manifest_data.get("operations", [])
    manifest_cli_commands = {
        op["cli_command"]: op["id"] for op in operations if op.get("cli_command")
    }
    manifest_mcp_tools = {
        op["mcp_tool"]: op["id"] for op in operations if op.get("mcp_tool")
    }

    # 1. Recursively scan CLI commands for all advertised leaf commands
    advertised_cli_commands: set[str] = set()

    def collect_leaf_commands(cmd_group: click.Group, prefix: str = "") -> None:
        for name, cmd in cmd_group.commands.items():
            full_name = f"{prefix} {name}".strip()
            if isinstance(cmd, click.Group) and cmd.commands:
                collect_leaf_commands(cmd, full_name)
            else:
                advertised_cli_commands.add(full_name)

    collect_leaf_commands(cli)

    for cmd_path in advertised_cli_commands:
        assert cmd_path in manifest_cli_commands, (
            f"Advertised CLI command '{cmd_path}' is unprobed / unmanifested in governance/public-operations.toml"
        )

    # 2. Scan FastMCP server tools
    server = getattr(rush.mcp, "mcp_server", None) or rush.mcp.build_server()
    advertised_mcp_tools = set(server._tool_manager._tools.keys())

    for tool_name in advertised_mcp_tools:
        assert tool_name in manifest_mcp_tools, (
            f"Advertised MCP tool '{tool_name}' is unprobed / unmanifested in governance/public-operations.toml"
        )

    assert len(advertised_cli_commands) == len(manifest_cli_commands) == 136
    assert len(advertised_mcp_tools) == len(manifest_mcp_tools) == 75


# ---------------------------------------------------------------------------
# T-57.14 (R-006): test_output_egress_and_error_codes
# ---------------------------------------------------------------------------


def test_output_egress_and_error_codes(capsys: pytest.CaptureFixture[str]) -> None:
    """T-57.14 (R-006): Tests CLI egress helper exit_with_result / exit_code_for status mappings, admin codes, and sanitization."""
    from rush.cli import exit_code_for, exit_with_result
    from rush.contracts.results import ToolResultV1

    # 1. Assert status mappings: "ok" -> 0, "warn" -> 1, "error" -> 2, "skipped" -> 0
    assert exit_code_for("ok") == 0
    assert exit_code_for("warn") == 1
    assert exit_code_for("fail") == 1
    assert exit_code_for("error") == 2
    assert exit_code_for("skipped") == 0

    assert (
        exit_code_for(
            ToolResultV1(
                schema_version="1.0.0",
                tool="lint",
                engine="test-engine",
                engine_version="1.0.0",
                status="ok",
                duration_ms=1,
                summary="ok",
                findings=[],
            )
        )
        == 0
    )
    assert (
        exit_code_for(
            ToolResultV1(
                schema_version="1.0.0",
                tool="lint",
                engine="test-engine",
                engine_version="1.0.0",
                status="warn",
                duration_ms=1,
                summary="warn",
                findings=[],
            )
        )
        == 1
    )
    assert (
        exit_code_for(
            ToolResultV1(
                schema_version="1.0.0",
                tool="lint",
                engine="test-engine",
                engine_version="1.0.0",
                status="error",
                duration_ms=1,
                summary="error",
                findings=[],
            )
        )
        == 2
    )
    assert (
        exit_code_for(
            ToolResultV1(
                schema_version="1.0.0",
                tool="lint",
                engine="test-engine",
                engine_version="1.0.0",
                status="skipped",
                duration_ms=1,
                summary="skipped",
                findings=[],
            )
        )
        == 0
    )

    assert exit_code_for({"status": "ok"}) == 0
    assert exit_code_for({"status": "warn"}) == 1
    assert exit_code_for({"status": "fail"}) == 1
    assert exit_code_for({"status": "error"}) == 2
    assert exit_code_for({"status": "skipped"}) == 0

    # 2. Assert admin exit codes are preserved as integers
    assert exit_code_for(0) == 0
    assert exit_code_for(1) == 1
    assert exit_code_for(2) == 2
    assert exit_code_for(42) == 42
    assert exit_code_for(127) == 127

    # 3. Test exit_with_result raises SystemExit with expected exit code
    with pytest.raises(SystemExit) as exc:
        exit_with_result({"status": "ok"})
    assert exc.value.code == 0

    with pytest.raises(SystemExit) as exc:
        exit_with_result({"status": "warn"})
    assert exc.value.code == 1

    with pytest.raises(SystemExit) as exc:
        exit_with_result({"status": "error"})
    assert exc.value.code == 2

    with pytest.raises(SystemExit) as exc:
        exit_with_result({"status": "skipped"})
    assert exc.value.code == 0

    with pytest.raises(SystemExit) as exc:
        exit_with_result(42)
    assert exc.value.code == 42

    # 4. Assert outputs are sanitized via sanitize_value
    secret_sentinel = "sk-ant-api03-abcdef123456789012345678"
    bearer_sentinel = "Bearer secret-auth-token-1234567890"
    payload = {
        "status": "warn",
        "secret": secret_sentinel,
        "token": bearer_sentinel,
    }

    with pytest.raises(SystemExit) as exc:
        exit_with_result(payload, as_json=True)
    assert exc.value.code == 1

    captured = capsys.readouterr()
    assert secret_sentinel not in captured.out
    assert bearer_sentinel not in captured.out
    assert "[REDACTED" in captured.out
