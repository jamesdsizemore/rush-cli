from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from rush.contracts.operations import (
    AdminOperationAdapter,
    OperationRegistry,
    ServiceOperationAdapter,
    ToolOperationAdapter,
)
from rush.contracts.results import ToolResultV1, ValidationErrorV1

REPO_ROOT = Path(__file__).parent.parent
MANIFEST_PATH = REPO_ROOT / "governance" / "public-operations.toml"


def test_tool_operation_targets_tool_result_v1() -> None:
    """T-54.08: ToolOperationAdapter validates that tool outputs conform to ToolResultV1."""
    adapter = ToolOperationAdapter(
        operation_id="lint", target_contract_id="ToolResultV1"
    )
    assert adapter.kind == "tool"
    assert adapter.target_contract_id == "ToolResultV1"

    valid_payload = {
        "schema_version": "1.0.0",
        "tool": "lint",
        "engine": "ruff",
        "engine_version": "0.9.9",
        "status": "ok",
        "duration_ms": 25,
        "summary": "linting passed",
        "findings": [],
    }
    validated = adapter.validate_output(valid_payload)
    assert isinstance(validated, ToolResultV1)
    assert validated.tool == "lint"

    # Malformed output raises ValidationErrorV1
    with pytest.raises(ValidationErrorV1):
        adapter.validate_output({"tool": "lint", "status": "invalid_status"})


def test_admin_operation_uses_named_contract() -> None:
    """T-54.09: AdminOperationAdapter validates against named contract without ToolResult wrapping."""
    adapter = AdminOperationAdapter(
        operation_id="version", target_contract_id="ClickExitCode"
    )
    assert adapter.kind == "admin"
    assert adapter.target_contract_id == "ClickExitCode"

    # Exit code contract accepts integer exit codes
    validated_exit = adapter.validate_output(0)
    assert validated_exit == 0
    assert not isinstance(validated_exit, ToolResultV1)

    # Dictionary admin contracts
    json_adapter = AdminOperationAdapter(
        operation_id="stats", target_contract_id="AdminJsonContract"
    )
    admin_payload = {"version": "0.3.0", "active_plugins": 3}
    validated_dict = json_adapter.validate_output(admin_payload)
    assert validated_dict == admin_payload
    assert not isinstance(validated_dict, ToolResultV1)

    # Rejection of invalid output type for exit code contract
    with pytest.raises(ValidationErrorV1) as exc_info:
        adapter.validate_output("not-an-exit-code")
    assert exc_info.value.code == "INVALID_TYPE"


def test_service_liveness_is_not_wrapped_as_tool_result() -> None:
    """T-54.10: ServiceOperationAdapter preserves protocol frames without ToolResult wrapping."""
    adapter = ServiceOperationAdapter(
        operation_id="mcp.initialize", target_contract_id="ServiceProtocol"
    )
    assert adapter.kind == "service"

    protocol_frame = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "rush", "version": "0.3.0"},
        },
    }
    validated = adapter.validate_output(protocol_frame)
    assert validated == protocol_frame
    assert not isinstance(validated, ToolResultV1)

    # Wrapping protocol frame into ToolResult is rejected
    with pytest.raises(ValidationErrorV1) as exc_info:
        wrapped_as_tool_result = ToolResultV1(
            schema_version="1.0.0",
            tool="mcp.initialize",
            engine=None,
            engine_version=None,
            status="ok",
            duration_ms=0,
            summary="service response",
            findings=[],
            raw=protocol_frame,
        )
        adapter.validate_output(wrapped_as_tool_result)
    assert exc_info.value.code == "INVALID_SERVICE_CONTRACT"


def test_every_manifest_operation_has_one_adapter() -> None:
    """T-54.11: 100% of the 152 operations in public-operations.toml are reconciled into adapters."""
    with open(MANIFEST_PATH, "rb") as f:
        manifest_data = tomllib.load(f)

    operations = manifest_data.get("operations", [])
    assert len(operations) == 152

    registry = OperationRegistry()
    report = registry.reconcile_manifest(MANIFEST_PATH)

    assert report["total"] == 152
    assert report["tool_count"] == 70
    assert report["admin_count"] == 65
    assert report["service_count"] == 17
    assert len(report["unmapped"]) == 0
    assert len(report["errors"]) == 0

    # Ensure every single manifest entry can be retrieved from registry with the right adapter
    for op in operations:
        op_id = op["id"]
        adapter = registry.get_adapter(op_id)
        assert adapter is not None
        assert adapter.operation_id == op_id
        assert adapter.kind == op["kind"]
        if op["kind"] == "tool":
            assert isinstance(adapter, ToolOperationAdapter)
            assert adapter.target_contract_id == "ToolResultV1"
        elif op["kind"] == "admin":
            assert isinstance(adapter, AdminOperationAdapter)
        elif op["kind"] == "service":
            assert isinstance(adapter, ServiceOperationAdapter)
