"""Operation adapter hierarchy and registry for public operation contract reconciliation."""

from __future__ import annotations

import tomllib
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Literal

from rush.contracts.results import (
    ToolResultV1,
    ValidationErrorV1,
    validate_tool_result,
)

OperationKind = Literal["tool", "admin", "service"]


class BaseOperationAdapter(ABC):
    """Abstract base adapter for public operations."""

    operation_id: str
    kind: OperationKind
    target_contract_id: str

    def __init__(
        self,
        operation_id: str,
        target_contract_id: str,
    ) -> None:
        self.operation_id = operation_id
        self.target_contract_id = target_contract_id

    @abstractmethod
    def validate_output(self, output: Any) -> Any:
        """Validate that operation output conforms to its target contract."""
        ...


class ToolOperationAdapter(BaseOperationAdapter):
    """Adapter for 'kind = tool' operations, requiring ToolResultV1 compliance."""

    kind: OperationKind = "tool"

    def __init__(
        self,
        operation_id: str,
        target_contract_id: str = "ToolResultV1",
    ) -> None:
        super().__init__(operation_id, target_contract_id)

    def validate_output(self, output: Any) -> ToolResultV1:
        return validate_tool_result(output)


class AdminOperationAdapter(BaseOperationAdapter):
    """Adapter for 'kind = admin' operations, validating against named admin contracts."""

    kind: OperationKind = "admin"

    def __init__(
        self,
        operation_id: str,
        target_contract_id: str = "ClickExitCode",
    ) -> None:
        super().__init__(operation_id, target_contract_id)

    def validate_output(self, output: Any) -> Any:
        if self.target_contract_id in ("ClickExitCode", "ExitCode"):
            if not isinstance(output, int) or isinstance(output, bool):
                raise ValidationErrorV1(
                    code="INVALID_TYPE",
                    message=f"Admin operation '{self.operation_id}' expected integer exit code, got {type(output).__name__}",
                    path=self.operation_id,
                    invalid_value=output,
                )
            return output
        if self.target_contract_id == "ToolResultV1":
            return validate_tool_result(output)
        return output


class ServiceOperationAdapter(BaseOperationAdapter):
    """Adapter for 'kind = service' operations, preserving unwrapped protocol frames."""

    kind: OperationKind = "service"

    def __init__(
        self,
        operation_id: str,
        target_contract_id: str = "ServiceProtocol",
    ) -> None:
        super().__init__(operation_id, target_contract_id)

    def validate_output(self, output: Any) -> Any:
        if isinstance(output, ToolResultV1):
            raise ValidationErrorV1(
                code="INVALID_SERVICE_CONTRACT",
                message=(
                    f"Service operation '{self.operation_id}' must never return "
                    "ToolResultV1 wrapped payloads"
                ),
                path=self.operation_id,
                invalid_value=output,
            )
        return output


class OperationRegistry:
    """Registry maintaining operation adapter instances and reconciling governance manifests."""

    def __init__(self) -> None:
        self._adapters: dict[str, BaseOperationAdapter] = {}

    def register(self, adapter: BaseOperationAdapter) -> None:
        self._adapters[adapter.operation_id] = adapter

    def get_adapter(self, operation_id: str) -> BaseOperationAdapter | None:
        return self._adapters.get(operation_id)

    def reconcile_manifest(self, manifest_path: Path | str) -> dict[str, Any]:
        """Verify that 100% of the operations in public-operations.toml are registered."""
        path = Path(manifest_path)
        with open(path, "rb") as f:
            data = tomllib.load(f)

        operations = data.get("operations", [])
        tool_count = 0
        admin_count = 0
        service_count = 0
        unmapped: list[str] = []
        errors: list[str] = []

        for op in operations:
            op_id = op.get("id")
            if not op_id:
                errors.append("Operation missing 'id' field")
                continue

            kind = op.get("kind")
            contract_id = op.get("contract_id")

            if kind == "tool":
                tool_count += 1
                adapter: BaseOperationAdapter = ToolOperationAdapter(
                    operation_id=op_id,
                    target_contract_id=contract_id or "ToolResultV1",
                )
            elif kind == "admin":
                admin_count += 1
                adapter = AdminOperationAdapter(
                    operation_id=op_id,
                    target_contract_id=contract_id or "ClickExitCode",
                )
            elif kind == "service":
                service_count += 1
                adapter = ServiceOperationAdapter(
                    operation_id=op_id,
                    target_contract_id=contract_id or "ServiceProtocol",
                )
            else:
                unmapped.append(op_id)
                errors.append(
                    f"Unknown operation kind '{kind}' for operation '{op_id}'"
                )
                continue

            self.register(adapter)

        return {
            "total": len(operations),
            "tool_count": tool_count,
            "admin_count": admin_count,
            "service_count": service_count,
            "unmapped": unmapped,
            "errors": errors,
        }
