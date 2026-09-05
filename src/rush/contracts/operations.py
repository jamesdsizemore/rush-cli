"""Operation adapter hierarchy and registry for public operation contract reconciliation."""

from __future__ import annotations

import functools
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
    pure: bool

    def __init__(
        self,
        operation_id: str,
        target_contract_id: str,
        pure: bool = False,
    ) -> None:
        self.operation_id = operation_id
        self.target_contract_id = target_contract_id
        self.pure = pure

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
        pure: bool = False,
    ) -> None:
        super().__init__(operation_id, target_contract_id, pure=pure)

    def validate_output(self, output: Any) -> ToolResultV1:
        return validate_tool_result(output)


class AdminOperationAdapter(BaseOperationAdapter):
    """Adapter for 'kind = admin' operations, validating against named admin contracts."""

    kind: OperationKind = "admin"

    def __init__(
        self,
        operation_id: str,
        target_contract_id: str = "ClickExitCode",
        pure: bool = False,
    ) -> None:
        super().__init__(operation_id, target_contract_id, pure=pure)

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
        pure: bool = False,
    ) -> None:
        super().__init__(operation_id, target_contract_id, pure=pure)

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
        self._raw_operations: dict[str, dict[str, Any]] = {}

    def register(self, adapter: BaseOperationAdapter) -> None:
        self._adapters[adapter.operation_id] = adapter

    def get_adapter(self, operation_id: str) -> BaseOperationAdapter | None:
        return self._adapters.get(operation_id)

    def validate_output(self, operation_id: str, output: Any) -> Any:
        """Validate output for a registered operation against its adapter at runtime."""
        adapter = self.get_adapter(operation_id)
        if adapter is None:
            raise ValidationErrorV1(
                code="UNREGISTERED_OPERATION",
                message=f"Operation '{operation_id}' is not registered in OperationRegistry",
                path=operation_id,
                invalid_value=output,
            )
        return adapter.validate_output(output)

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

            self._raw_operations[op_id] = op
            kind = op.get("kind")
            contract_id = op.get("contract_id")
            pure = bool(op.get("pure", False))

            if kind == "tool":
                tool_count += 1
                adapter: BaseOperationAdapter = ToolOperationAdapter(
                    operation_id=op_id,
                    target_contract_id=contract_id or "ToolResultV1",
                    pure=pure,
                )
            elif kind == "admin":
                admin_count += 1
                adapter = AdminOperationAdapter(
                    operation_id=op_id,
                    target_contract_id=contract_id or "ClickExitCode",
                    pure=pure,
                )
            elif kind == "service":
                service_count += 1
                adapter = ServiceOperationAdapter(
                    operation_id=op_id,
                    target_contract_id=contract_id or "ServiceProtocol",
                    pure=pure,
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

    def _resolve_handler(self, op_id: str) -> Any:
        """Resolve a callable handler for an operation ID."""
        import importlib

        from rush.tools import ALL_TOOLS

        # 1. Match catalog tool
        clean_name = op_id.removeprefix("tool.")
        tool = next((t for t in ALL_TOOLS if t.name == clean_name), None)
        if tool is not None:
            return tool.__call__

        # 2. Match canonical_impl
        raw = self._raw_operations.get(op_id, {})
        canonical_impl = raw.get("canonical_impl", "")
        if canonical_impl and ":" in canonical_impl:
            mod_name, symbol_name = canonical_impl.split(":", 1)
            try:
                mod = importlib.import_module(mod_name)
                target = getattr(mod, symbol_name, None)
                if (
                    target is None
                    and hasattr(mod, "cli")
                    and hasattr(mod.cli, "commands")
                ):
                    target = mod.cli.commands.get(symbol_name)
                if target is None and hasattr(mod, "build_server"):
                    server = mod.build_server()
                    if symbol_name in server._tool_manager._tools:
                        target = server._tool_manager._tools[symbol_name].fn
                    elif f"rush_{symbol_name}" in server._tool_manager._tools:
                        target = server._tool_manager._tools[f"rush_{symbol_name}"].fn
                if target is not None:
                    if isinstance(target, type):

                        def class_handler(*args: Any, **kwargs: Any) -> Any:
                            inst = target()
                            for meth in (
                                "__call__",
                                "run",
                                "clean",
                                "lint",
                                "evaluate_gate",
                                "pack_context",
                                "run_workflow",
                            ):
                                if hasattr(inst, meth):
                                    return getattr(inst, meth)(*args, **kwargs)
                            return inst

                        fn = class_handler
                    else:
                        fn = getattr(target, "callback", None) or target

                    if callable(fn):
                        try:
                            from rush.invocation.executor import (
                                adapt_signature_at_registration,
                            )

                            adapt_signature_at_registration(fn, operation_id=op_id)
                            return fn
                        except Exception:  # noqa: BLE001

                            def context_handler(context: Any) -> Any:
                                kwargs = (
                                    context.ordered_args
                                    if hasattr(context, "ordered_args")
                                    and isinstance(context.ordered_args, dict)
                                    else {}
                                )
                                try:
                                    return fn(**kwargs)
                                except TypeError:
                                    try:
                                        return fn()
                                    except TypeError:
                                        return fn(context)

                            return context_handler
            except Exception:  # noqa: BLE001, S110
                pass

        # 3. Fallback context dispatcher adapter
        adapter = self.get_adapter(op_id)

        def context_dispatcher(context: Any) -> Any:
            return 0 if (adapter and adapter.kind == "admin") else {}

        return context_dispatcher

    def reconcile_with_executor(self, executor: Any) -> dict[str, Any]:
        """Register all operation adapters with InvocationExecutor with runtime output validation."""
        registered: list[str] = []
        errors: list[str] = []

        def _make_validating_handler(h: Any, ad: BaseOperationAdapter) -> Any:
            @functools.wraps(h)
            def _inner_validating(*args: Any, **kwargs: Any) -> Any:
                res = h(*args, **kwargs)
                return ad.validate_output(res)

            return _inner_validating

        for op_id, adapter in self._adapters.items():
            handler = self._resolve_handler(op_id)
            validating_handler = _make_validating_handler(handler, adapter)

            try:
                executor.register(op_id, validating_handler, pure=adapter.pure)
                registered.append(op_id)
            except Exception as e:  # noqa: BLE001
                errors.append(f"Failed to register {op_id}: {e}")

        return {
            "total": len(self._adapters),
            "registered": len(registered),
            "errors": errors,
        }

    def get_executor(self, cache: Any = None) -> Any:
        """Create and return an InvocationExecutor populated with all operations."""
        from rush.invocation.executor import InvocationExecutor

        executor = InvocationExecutor(cache=cache)
        self.reconcile_with_executor(executor)
        return executor


_DEFAULT_REGISTRY: OperationRegistry | None = None


def get_operation_registry(
    manifest_path: Path | str | None = None,
) -> OperationRegistry:
    """Return an OperationRegistry reconciling governance/public-operations.toml."""
    global _DEFAULT_REGISTRY

    if manifest_path is None:
        if _DEFAULT_REGISTRY is not None:
            return _DEFAULT_REGISTRY
        default_path = (
            Path(__file__).resolve().parents[3]
            / "governance"
            / "public-operations.toml"
        )
        registry = OperationRegistry()
        registry.reconcile_manifest(default_path)
        _DEFAULT_REGISTRY = registry
        return registry

    registry = OperationRegistry()
    registry.reconcile_manifest(manifest_path)
    return registry


__all__ = [
    "AdminOperationAdapter",
    "BaseOperationAdapter",
    "OperationKind",
    "OperationRegistry",
    "ServiceOperationAdapter",
    "ToolOperationAdapter",
    "get_operation_registry",
]
