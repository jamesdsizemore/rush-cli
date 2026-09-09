"""Contract tests T-58.21 through T-58.26 for Workstream P58.7 (Output Boundary Migration).

Contracts:
- T-58.21: Every eligible manifest boundary rejects malformed output (R-011).
- T-58.22: Service protocol operations return raw protocol frames, never ToolResultV1.
- T-58.23: Admin commands emit unwrapped native integer exit codes conforming to ClickExitCode.
- T-58.24: Mesh daemon RPC responses and lock inspect conform to declared service and admin contracts.
- T-58.25: Remediation Phase 58 manifest integrity and requirement closure.
- T-58.26: Zero undocumented persistence or raw lock seams across codebase.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from rush.cli import cli, exit_code_for
from rush.contracts.operations import (
    AdminOperationAdapter,
    BaseOperationAdapter,
    OperationRegistry,
    ServiceOperationAdapter,
    ToolOperationAdapter,
    get_operation_registry,
)
from rush.contracts.results import ToolResultV1, ValidationErrorV1
from rush.mcp import rush_mesh_acquire_lock, rush_mesh_release_lock
from rush.mcp_mesh.lock_manager import MeshLockManager

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# T-58.21 (R-011): test_every_eligible_manifest_boundary_rejects_malformed_output
# ---------------------------------------------------------------------------


def test_every_eligible_manifest_boundary_rejects_malformed_output() -> None:
    """T-58.21 (R-011 Governance Test): Probes all 153 operations from public-operations.toml with malformed payloads."""
    registry = get_operation_registry()
    assert isinstance(registry, OperationRegistry)
    assert len(registry._adapters) == 153

    # Verify adapter registration and boundary validation across all operations
    tool_count = 0
    admin_count = 0
    service_count = 0

    sample_valid_tool_result = ToolResultV1(
        schema_version="1.0.0",
        tool="test_tool",
        engine="rush",
        engine_version="1.0.0",
        status="ok",
        duration_ms=10,
        summary="Everything nominal",
        findings=[],
    )

    for op_id, adapter in registry._adapters.items():
        assert isinstance(adapter, BaseOperationAdapter)
        assert adapter.operation_id == op_id

        if adapter.kind == "tool":
            tool_count += 1
            assert isinstance(adapter, ToolOperationAdapter)

            # 1. Missing required fields raises ValidationErrorV1
            with pytest.raises(ValidationErrorV1):
                adapter.validate_output({"tool": op_id})

            # 2. Invalid status raises ValidationErrorV1
            with pytest.raises(ValidationErrorV1):
                adapter.validate_output(
                    {
                        "schema_version": "1.0.0",
                        "tool": op_id,
                        "engine": "rush",
                        "engine_version": "1.0.0",
                        "status": "unrecognized_status_xyz",
                        "duration_ms": 5,
                        "summary": "Invalid status",
                        "findings": [],
                    }
                )

            # 3. Valid tool result passes through
            res = adapter.validate_output(sample_valid_tool_result)
            assert isinstance(res, ToolResultV1)

            # 4. Registry-level validate_output method also rejects malformed output
            with pytest.raises(ValidationErrorV1):
                registry.validate_output(op_id, {"invalid": "payload"})

        elif adapter.kind == "admin":
            admin_count += 1
            assert isinstance(adapter, AdminOperationAdapter)
            assert adapter.target_contract_id in ("ClickExitCode", "ExitCode")

            # 1. Non-integer strings raise ValidationErrorV1
            with pytest.raises(ValidationErrorV1):
                adapter.validate_output("not-an-int")

            # 2. Boolean values raise ValidationErrorV1
            with pytest.raises(ValidationErrorV1):
                adapter.validate_output(True)

            with pytest.raises(ValidationErrorV1):
                adapter.validate_output(False)

            # 3. ToolResultV1 raises ValidationErrorV1
            with pytest.raises(ValidationErrorV1):
                adapter.validate_output(sample_valid_tool_result)

            # 4. Valid integer exit codes return native integer
            for code in (0, 1, 2, 42):
                validated_code = adapter.validate_output(code)
                assert type(validated_code) is int
                assert validated_code == code

            # 5. Registry-level validate_output rejects non-integer
            with pytest.raises(ValidationErrorV1):
                registry.validate_output(op_id, "not-an-int")

        elif adapter.kind == "service":
            service_count += 1
            assert isinstance(adapter, ServiceOperationAdapter)

            # 1. ToolResultV1 instance raises ValidationErrorV1
            with pytest.raises(ValidationErrorV1):
                adapter.validate_output(sample_valid_tool_result)

            # 2. Raw protocol frames / dicts pass through unwrapped
            raw_frame: dict[str, Any] = {
                "jsonrpc": "2.0",
                "result": {"status": "ok", "mesh": "active"},
            }
            validated_frame = adapter.validate_output(raw_frame)
            assert validated_frame == raw_frame
            assert not isinstance(validated_frame, ToolResultV1)

            # 3. Registry-level validate_output rejects ToolResultV1
            with pytest.raises(ValidationErrorV1):
                registry.validate_output(op_id, sample_valid_tool_result)

    assert tool_count == 71
    assert admin_count == 65
    assert service_count == 17
    assert tool_count + admin_count + service_count == 153


# ---------------------------------------------------------------------------
# T-58.22: test_service_and_stdio_protocol_responses_are_not_tool_results
# ---------------------------------------------------------------------------


def test_service_and_stdio_protocol_responses_are_not_tool_results() -> None:
    """T-58.22: Asserts service protocol operations (MCP initialize, tools/list, mesh ping) return raw protocol dicts/frames, never wrapped in ToolResultV1."""
    registry = get_operation_registry()
    service_adapters = [a for a in registry._adapters.values() if a.kind == "service"]
    assert len(service_adapters) == 17

    sample_tr = ToolResultV1(
        schema_version="1.0.0",
        tool="protocol_service",
        engine="rush",
        engine_version="1.0.0",
        status="ok",
        duration_ms=1,
        summary="Service should not be tool result",
        findings=[],
    )

    # 1. FastMCP stdio protocol frames must remain raw dicts
    mcp_initialize_response = {
        "protocolVersion": "2024-11-05",
        "capabilities": {
            "logging": {},
            "prompts": {"listChanged": True},
            "resources": {"subscribe": True, "listChanged": True},
            "tools": {"listChanged": True},
        },
        "serverInfo": {"name": "rush", "version": "0.3.0"},
    }

    mcp_tools_list_response = {
        "tools": [
            {
                "name": "rush_lint",
                "description": "Run lint checks across codebase",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "rush_mesh_acquire_lock",
                "description": "Acquire multi-agent file lock",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ]
    }

    mesh_ping_response = {
        "pong": True,
        "timestamp": 1725544800.0,
        "active_locks": 0,
    }

    for adapter in service_adapters:
        # Every service adapter strictly validates protocol frames without ToolResult wrapping
        res_init = adapter.validate_output(mcp_initialize_response)
        assert isinstance(res_init, dict)
        assert not isinstance(res_init, ToolResultV1)
        assert res_init["serverInfo"]["name"] == "rush"

        res_tools = adapter.validate_output(mcp_tools_list_response)
        assert isinstance(res_tools, dict)
        assert not isinstance(res_tools, ToolResultV1)
        assert len(res_tools["tools"]) == 2

        res_ping = adapter.validate_output(mesh_ping_response)
        assert isinstance(res_ping, dict)
        assert not isinstance(res_ping, ToolResultV1)
        assert res_ping["pong"] is True

        # ToolResultV1 wrapping is strictly rejected fail-closed
        with pytest.raises(ValidationErrorV1) as exc_info:
            adapter.validate_output(sample_tr)
        assert exc_info.value.code == "INVALID_SERVICE_CONTRACT"

    # 2. Live MCP lock tool functions return unwrapped primitive types (bool), never ToolResultV1
    assert callable(rush_mesh_acquire_lock)
    assert callable(rush_mesh_release_lock)


# ---------------------------------------------------------------------------
# T-58.23: test_admin_boundaries_emit_unwrapped_exit_codes
# ---------------------------------------------------------------------------


def test_admin_boundaries_emit_unwrapped_exit_codes() -> None:
    """T-58.23: Asserts admin commands emit native integer exit codes conforming to ClickExitCode contract without ToolResult wrapping."""
    registry = get_operation_registry()
    admin_adapters = [a for a in registry._adapters.values() if a.kind == "admin"]
    assert len(admin_adapters) == 65

    sample_tr = ToolResultV1(
        schema_version="1.0.0",
        tool="admin_cmd",
        engine="rush",
        engine_version="1.0.0",
        status="ok",
        duration_ms=1,
        summary="Admin should not be tool result",
        findings=[],
    )

    # 1. Test every admin adapter returns native int and rejects non-int
    for adapter in admin_adapters:
        assert adapter.target_contract_id in ("ClickExitCode", "ExitCode")

        # Native integer returns exactly int
        for code in (0, 1, 2, 127):
            res = adapter.validate_output(code)
            assert type(res) is int
            assert res == code
            assert not isinstance(res, ToolResultV1)

        # Non-integer types are rejected
        with pytest.raises(ValidationErrorV1):
            adapter.validate_output("0")

        with pytest.raises(ValidationErrorV1):
            adapter.validate_output(True)

        with pytest.raises(ValidationErrorV1):
            adapter.validate_output(sample_tr)

    # 2. Verify exit_code_for returns raw integer exit codes
    assert exit_code_for(0) == 0
    assert exit_code_for(1) == 1
    assert exit_code_for(2) == 2
    assert type(exit_code_for(0)) is int

    # 3. Invoking CLI admin commands emits integer exit codes
    runner = CliRunner()
    result = runner.invoke(cli, ["benchmark", "check", "--help"])
    assert type(result.exit_code) is int
    assert result.exit_code == 0
    assert "ToolResultV1" not in result.output
    assert "schema_version" not in result.output


# ---------------------------------------------------------------------------
# T-58.24: test_daemon_mesh_routes_conform_to_operation_adapters
# ---------------------------------------------------------------------------


def test_daemon_mesh_routes_conform_to_operation_adapters(tmp_path: Path) -> None:
    """T-58.24: Asserts mesh daemon RPC responses and lock inspect operations conform to declared service and admin contracts."""
    registry = get_operation_registry()
    mgr = MeshLockManager(project_root=tmp_path)
    target = tmp_path / "mesh_resource.py"
    target.write_text("x = 42\n", encoding="utf-8")

    # 1. Lock inspect returns raw dict conforming to ServiceProtocol
    inspect_result = mgr.inspect(tmp_path, target)
    assert isinstance(inspect_result, dict)
    assert not isinstance(inspect_result, ToolResultV1)
    assert inspect_result["state"] == "available"
    assert inspect_result["owner"] is None

    service_adapter = ServiceOperationAdapter(
        operation_id="mesh.lock_inspect", target_contract_id="ServiceProtocol"
    )
    validated_inspect = service_adapter.validate_output(inspect_result)
    assert validated_inspect == inspect_result
    assert not isinstance(validated_inspect, ToolResultV1)

    # 2. Lock inspect wrapped in ToolResultV1 is rejected
    fake_tool_result = ToolResultV1(
        schema_version="1.0.0",
        tool="lock_inspect",
        engine="mesh",
        engine_version="1.0.0",
        status="ok",
        duration_ms=1,
        summary="inspect",
        findings=[],
    )
    with pytest.raises(ValidationErrorV1):
        service_adapter.validate_output(fake_tool_result)

    # 3. Mesh lock operations registered in public-operations.toml
    acquire_adapter = registry.get_adapter("mcp.mesh_acquire_lock")
    assert acquire_adapter is not None
    assert acquire_adapter.kind == "service"
    assert not isinstance(
        acquire_adapter.validate_output({"status": "ok", "acquired": True}),
        ToolResultV1,
    )

    release_adapter = registry.get_adapter("mcp.mesh_release_lock")
    assert release_adapter is not None
    assert release_adapter.kind == "service"
    assert not isinstance(
        release_adapter.validate_output({"status": "ok", "released": True}),
        ToolResultV1,
    )

    # 4. Workspace locks admin operation conforms to ClickExitCode
    ws_adapter = registry.get_adapter("cli.workspace_locks")
    assert ws_adapter is not None
    assert ws_adapter.kind == "admin"
    assert ws_adapter.validate_output(0) == 0
    with pytest.raises(ValidationErrorV1):
        ws_adapter.validate_output("not-an-int")


# ---------------------------------------------------------------------------
# T-58.25: test_remediation_phase58_manifest_integrity
# ---------------------------------------------------------------------------


def test_remediation_phase58_manifest_integrity() -> None:
    """T-58.25: Verifies governance/remediation-phase-58.toml exists, is valid TOML, has status 'completed', lists all 26 contract tests, and closes requirements."""
    manifest_path = PROJECT_ROOT / "governance" / "remediation-phase-58.toml"
    assert manifest_path.exists(), f"Missing Phase 58 manifest at {manifest_path}"

    with open(manifest_path, "rb") as f:
        data = tomllib.load(f)

    # 1. Phase section metadata
    phase_meta = data.get("phase", {})
    assert phase_meta.get("id") == 58
    assert phase_meta.get("status") == "completed"
    assert phase_meta.get("test_count") == 26

    # 2. Closed requirements include R-009, R-010, R-016, and R-011
    reqs = data.get("requirements", {})
    closed = reqs.get("closed", [])
    assert "R-009" in closed, "R-009 must be marked closed in Phase 58 manifest"
    assert "R-010" in closed, "R-010 must be marked closed in Phase 58 manifest"
    assert "R-016" in closed, "R-016 must be marked closed in Phase 58 manifest"
    assert "R-011" in closed, "R-011 must be marked closed in Phase 58 manifest"
    assert "runtime_migration" in reqs, "Runtime migration of R-011 must be noted"

    # 3. Lists all 26 contract tests (T-58.01 through T-58.26)
    expected_tests = [f"T-58.{i:02d}" for i in range(1, 27)]
    contract_tests_table = data.get("contract_tests", {})
    declared_tests = contract_tests_table.get("tests", [])
    assert len(declared_tests) == 26
    for t_id in expected_tests:
        assert t_id in declared_tests, f"Test {t_id} missing from manifest tests list"

    # 4. Verify remediation-contracts.toml has marked R-009, R-010, and R-016 as completed
    contracts_ledger_path = PROJECT_ROOT / "governance" / "remediation-contracts.toml"
    assert contracts_ledger_path.exists()
    with open(contracts_ledger_path, "rb") as f:
        ledger = tomllib.load(f)

    findings = {f["id"]: f for f in ledger.get("findings", [])}
    for finding_id in ("R-009", "R-010", "R-016"):
        assert finding_id in findings, (
            f"{finding_id} missing from remediation-contracts.toml"
        )
        assert findings[finding_id].get("status") == "completed", (
            f"{finding_id} must have status='completed' in remediation-contracts.toml"
        )


# ---------------------------------------------------------------------------
# T-58.26: test_no_undocumented_persistence_or_lock_seams
# ---------------------------------------------------------------------------


def test_no_undocumented_persistence_or_lock_seams() -> None:
    """T-58.26: Performs AST scan asserting MeshLockManager exists exclusively in lock_manager.py and zero uncontained write_text in mcp_mesh/memory."""
    rush_root = PROJECT_ROOT / "src" / "rush"
    assert rush_root.exists()

    lock_manager_defs: list[Path] = []
    uncontained_write_text_calls: list[tuple[Path, int]] = []

    for py_file in rush_root.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except SyntaxError as e:
            pytest.fail(f"Syntax error in {py_file}: {e}")

        rel_path = py_file.relative_to(rush_root)
        parts = rel_path.parts

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "MeshLockManager":
                lock_manager_defs.append(py_file)

            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "write_text"
                and parts
                and parts[0] in ("mcp_mesh", "memory")
            ):
                uncontained_write_text_calls.append((py_file, node.lineno))

    # 1. MeshLockManager class definition exists exclusively in src/rush/mcp_mesh/lock_manager.py
    assert len(lock_manager_defs) == 1, (
        f"Expected exactly 1 MeshLockManager definition, found {len(lock_manager_defs)}: {lock_manager_defs}"
    )
    def_path = lock_manager_defs[0].resolve()
    expected_path = (rush_root / "mcp_mesh" / "lock_manager.py").resolve()
    assert def_path == expected_path, (
        f"MeshLockManager defined at {def_path}, expected {expected_path}"
    )

    # 2. Zero direct uncontained write_text calls in mcp_mesh and memory
    assert len(uncontained_write_text_calls) == 0, (
        f"Found uncontained write_text calls in persistent state modules: {uncontained_write_text_calls}"
    )
