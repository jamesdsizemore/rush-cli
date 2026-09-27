"""Single execution boundary and registration-time signature adaptation.

Enforces zero-retry execution semantics and registration-time callable signature
adaptation for CLI and MCP transports.
"""

from __future__ import annotations

import copy
import inspect
import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from rush.contracts.results import ToolResultV1
from rush.invocation.models import (
    InvalidTargetError,
    InvocationContext,
    InvocationError,
    SignatureAdaptationError,
)
from rush.safety.redactor import sanitize_value

_SENTINEL = object()

# T10 (R10.1, finding 4): ambient roots of the executing invocation, set by
# `InvocationExecutor.execute` around the handler call -- never a handler
# parameter, so nothing new is published into any MCP schema.
_INVOCATION_ROOT: ContextVar[Path | None] = ContextVar(
    "rush_invocation_root", default=None
)
_EXECUTION_ROOT: ContextVar[Path | None] = ContextVar(
    "rush_execution_root", default=None
)


def current_invocation_root() -> Path | None:
    """The executing invocation's logical project root (the original root inside a
    staged scan), or `None` outside `InvocationExecutor.execute`."""
    return _INVOCATION_ROOT.get()


def current_execution_root() -> Path | None:
    """The tree the executing invocation actually analyzes (the staged root inside a
    staged scan), or `None` outside `InvocationExecutor.execute`."""
    return _EXECUTION_ROOT.get()


def _invocation_roots(context: InvocationContext) -> tuple[Path, Path]:
    """(logical, execution) roots: a workspace root inside the active staging
    copy maps its logical root back to `staging.original_root`."""
    from rush.engines.staging import active_staging

    execution = context.workspace_root
    staging = active_staging()
    if staging is not None and execution.is_relative_to(staging.staged_root):
        return staging.original_root, execution
    return execution, execution


@contextmanager
def _invocation_root_scope(context: InvocationContext) -> Iterator[None]:
    logical, execution = _invocation_roots(context)
    logical_token = _INVOCATION_ROOT.set(logical)
    execution_token = _EXECUTION_ROOT.set(execution)
    try:
        yield
    finally:
        _EXECUTION_ROOT.reset(execution_token)
        _INVOCATION_ROOT.reset(logical_token)


RECOGNIZED_CONTEXT_PARAM_NAMES: frozenset[str] = frozenset(
    {
        "context",
        "ctx",
        "path",
        "target",
        "target_path",
        "paths",
        "target_paths",
        "targets",
        # T10 (R10.5): the contained targets built from the request's `files`.
        "files",
        "workspace_root",
        "root",
        "transport",
        "permissions",
        "ordered_args",
        "args",
        "operation_id",
        "request_id",
        "cache_policy",
        "effective_config_digest",
        "config_digest",
        "environment_digest",
        # P69-01.2j: bound from the context only. A tool whose `__call__`
        # doesn't declare them is unaffected.
        "owner_instance_id",
        "run_id",
    }
)

OWNERSHIP_CONTEXT_PARAM_NAMES: frozenset[str] = frozenset(
    {"owner_instance_id", "run_id"}
)
"""P69-01.2j: structural execution ownership. Filtered out of every tool
argument path so a request can never smuggle a forged owner identity in as a
tool argument, and so an unopted-in `**kwargs` handler never receives them."""

POSITIONAL_BINDABLE_NAMES: frozenset[str] = frozenset(
    {
        "context",
        "ctx",
        "path",
        "target",
        "target_path",
        "paths",
        "target_paths",
        "targets",
        "workspace_root",
        "root",
    }
)


@dataclass(frozen=True)
class RegisteredOperation:
    """Represents a registered operation with a fixed, adapted execution signature."""

    operation_id: str
    handler: Callable[..., Any]
    signature_adapter: Callable[
        [InvocationContext], tuple[tuple[Any, ...], dict[str, Any]]
    ]
    pure: bool = False


def _parse_ordered_args(ordered_args: tuple[str, ...]) -> dict[str, Any]:
    """Parse ordered arguments (e.g. --flag, --key=val) into kwargs dictionary."""
    kwargs: dict[str, Any] = {}
    for arg in ordered_args:
        if arg.startswith("--"):
            kv = arg[2:]
            if "=" in kv:
                k, v = kv.split("=", 1)
                k = k.replace("-", "_")
                if v.lower() == "true":
                    val: Any = True
                elif v.lower() == "false":
                    val = False
                elif v.lower() in ("none", "null"):
                    val = None
                else:
                    try:
                        val = json.loads(v)
                    except (json.JSONDecodeError, ValueError):
                        try:
                            val = int(v)
                        except ValueError:
                            try:
                                val = float(v)
                            except ValueError:
                                val = v
                kwargs[k] = val
            else:
                k = kv.replace("-", "_")
                kwargs[k] = True
    return kwargs


def invocation_arguments(context: InvocationContext) -> dict[str, Any]:
    """Return typed request arguments, falling back only for legacy ordered records.

    P69-01.2j: the ownership pair is stripped here, inside the one function
    both `general_signature_adapter` and `var_args_adapter` call, and in both
    branches -- a legacy request smuggling `--owner-instance-id=leak` through
    hyphen-normalization is blocked exactly like a modern typed-args one.
    """
    if context.typed_args is not None:
        arguments = copy.deepcopy(dict(context.typed_args))
    else:
        arguments = _parse_ordered_args(context.ordered_args)
    for name in OWNERSHIP_CONTEXT_PARAM_NAMES:
        arguments.pop(name, None)
    return arguments


def _is_bindable_context_param(
    name: str,
    annotation: Any,
    kind: inspect._ParameterKind,
) -> bool:
    """Check if parameter can be bound deterministically from InvocationContext."""
    if annotation in (InvocationContext, "InvocationContext") or name in (
        "context",
        "ctx",
    ):
        return True

    if kind == inspect.Parameter.POSITIONAL_ONLY:
        return name in POSITIONAL_BINDABLE_NAMES

    if name.startswith("allow_"):
        return True

    return name in RECOGNIZED_CONTEXT_PARAM_NAMES


def _resolve_context_val(
    name: str,
    annotation: Any,
    context: InvocationContext,
) -> Any:
    """Resolve context parameter value for a parameter name/annotation."""
    if name in ("context", "ctx") or annotation in (
        InvocationContext,
        "InvocationContext",
    ):
        return context

    if name.startswith("allow_"):
        perm_name = name[6:].replace("-", "_")
        return perm_name in context.permissions

    if name in ("path", "target", "target_path"):
        if context.targets:
            return context.workspace_root / context.targets[0].relative_path
        return context.workspace_root

    if name in ("paths", "target_paths"):
        return tuple(
            (context.workspace_root / t.relative_path) for t in context.targets
        )

    if name == "targets":
        return context.targets

    if name == "files":
        # T10 (R10.5): `files` is a reserved request key, so it never reaches the
        # typed arguments; bind the contained targets built from it instead, as
        # root-relative POSIX strings (what CLI `--file` from the root carries).
        if context.file_targets is None:
            return _SENTINEL
        return [t.relative_path.as_posix() for t in context.file_targets]

    if name in ("workspace_root", "root"):
        return context.workspace_root

    if name == "transport":
        return context.transport

    if name == "permissions":
        return context.permissions

    if name in ("ordered_args", "args"):
        return context.ordered_args

    if name == "operation_id":
        return context.operation_id

    if name == "request_id":
        return context.request_id

    if name == "cache_policy":
        return context.cache_policy

    if name in ("effective_config_digest", "config_digest"):
        return context.effective_config_digest

    if name == "environment_digest":
        return context.environment_digest

    if name == "owner_instance_id":
        return context.owner_instance_id or None

    if name == "run_id":
        return context.run_id or None

    return _SENTINEL


def adapt_signature_at_registration(
    handler: Callable[..., Any],
    operation_id: str = "",
) -> Callable[[InvocationContext], tuple[tuple[Any, ...], dict[str, Any]]]:
    """Inspect and adapt a callable handler signature once during registration.

    Validates that the handler can be bound against InvocationContext.
    Raises SignatureAdaptationError immediately at registration time if parameters
    cannot be bound.
    """
    try:
        sig = inspect.signature(handler)
    except Exception as exc:
        raise SignatureAdaptationError(
            f"Unable to inspect signature for handler '{handler!r}': {exc}",
            operation_id=operation_id,
        ) from exc

    params = list(sig.parameters.values())

    # Fast-path: 0 parameters
    if len(params) == 0:

        def zero_arg_adapter(
            context: InvocationContext,
        ) -> tuple[tuple[Any, ...], dict[str, Any]]:
            return ((), {})

        return zero_arg_adapter

    # Fast-path: single parameter receiving context directly
    if len(params) == 1:
        sole_p = params[0]
        if sole_p.name in ("context", "ctx") or sole_p.annotation in (
            InvocationContext,
            "InvocationContext",
        ):

            def single_context_adapter(
                context: InvocationContext,
            ) -> tuple[tuple[Any, ...], dict[str, Any]]:
                return ((context,), {})

            return single_context_adapter

    # Fast-path: (*targets, **kwargs)
    has_var_positional = any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in params)
    has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params)
    regular_params = [
        p
        for p in params
        if p.kind
        not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    ]

    if len(regular_params) == 0 and has_var_positional and has_var_keyword:

        def var_args_adapter(
            context: InvocationContext,
        ) -> tuple[tuple[Any, ...], dict[str, Any]]:
            target_paths = (
                tuple(
                    (context.workspace_root / t.relative_path) for t in context.targets
                )
                if context.targets
                else (context.workspace_root,)
            )
            parsed_kwargs = invocation_arguments(context)
            return (target_paths, parsed_kwargs)

        return var_args_adapter

    # Catalog-declared options are supplied through the invocation's ordered arguments.
    from rush.catalog import TOOL_SPECS

    spec = TOOL_SPECS.get(operation_id)
    declared_options = {option.name for option in spec.option_specs} if spec else set()

    # Validate all parameters at registration time
    for p in params:
        if p.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue

        is_bindable = _is_bindable_context_param(p.name, p.annotation, p.kind) or (
            p.kind != inspect.Parameter.POSITIONAL_ONLY and p.name in declared_options
        )
        has_default = p.default is not inspect.Parameter.empty

        if not is_bindable and not has_default:
            if p.kind == inspect.Parameter.POSITIONAL_ONLY:
                raise SignatureAdaptationError(
                    f"Cannot adapt positional-only parameter '{p.name}' for handler '{getattr(handler, '__name__', repr(handler))}'",
                    operation_id=operation_id,
                    param_name=p.name,
                )
            raise SignatureAdaptationError(
                f"Cannot adapt required parameter '{p.name}' for handler '{getattr(handler, '__name__', repr(handler))}': parameter cannot be bound from InvocationContext",
                operation_id=operation_id,
                param_name=p.name,
            )

    # General adapter function
    def general_signature_adapter(
        context: InvocationContext,
    ) -> tuple[tuple[Any, ...], dict[str, Any]]:
        call_args: list[Any] = []
        call_kwargs: dict[str, Any] = {}
        parsed_kwargs = invocation_arguments(context)

        for p in params:
            if p.kind == inspect.Parameter.POSITIONAL_ONLY:
                val = _resolve_context_val(p.name, p.annotation, context)
                if val is _SENTINEL:
                    if p.default is not inspect.Parameter.empty:
                        val = p.default
                    else:
                        raise SignatureAdaptationError(
                            f"Missing positional-only parameter '{p.name}'",
                            operation_id=operation_id,
                            param_name=p.name,
                        )
                call_args.append(val)
            elif p.kind in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            ):
                val = _resolve_context_val(p.name, p.annotation, context)
                if val is not _SENTINEL:
                    call_kwargs[p.name] = val
                elif p.name in parsed_kwargs:
                    call_kwargs[p.name] = parsed_kwargs[p.name]
                elif p.default is not inspect.Parameter.empty:
                    call_kwargs[p.name] = p.default
                else:
                    raise SignatureAdaptationError(
                        f"Missing required parameter '{p.name}'",
                        operation_id=operation_id,
                        param_name=p.name,
                    )
            elif p.kind == inspect.Parameter.VAR_POSITIONAL:
                target_paths = (
                    tuple(
                        (context.workspace_root / t.relative_path)
                        for t in context.targets
                    )
                    if context.targets
                    else (context.workspace_root,)
                )
                call_args.extend(target_paths)
            elif p.kind == inspect.Parameter.VAR_KEYWORD:
                for k, v in parsed_kwargs.items():
                    if k not in call_kwargs:
                        call_kwargs[k] = v

        return (tuple(call_args), call_kwargs)

    return general_signature_adapter


def _redacted(text: str) -> str:
    return str(sanitize_value(text).value)


def target_error_result(
    tool: str,
    code: str,
    message: str,
    *,
    target: str,
    reason: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """T9: the canonical not-run ToolResult for a target that cannot be
    analyzed -- `status:"error"`, no findings, no engine, no cache entry."""
    from rush.permissions import build_execution_metadata
    from rush.runtime.result_helpers import error_result
    from rush.tools.routing import no_target_scope

    return dict(
        error_result(
            tool,
            None,
            _redacted(message),
            metadata={
                "error": {"code": code, "target": _redacted(target), **(extra or {})},
                "execution": build_execution_metadata(
                    "executed", extra={"disposition": "not_run", "cause": reason}
                ),
                "scope": no_target_scope(reason),
            },
        )
    )


def invalid_target_result(tool: str, exc: InvalidTargetError) -> dict[str, Any]:
    """T9/R9.2: a malformed target (`TARGET_INVALID`), never a traceback."""
    return target_error_result(
        tool, exc.code, str(exc), target=exc.target, reason="target_invalid"
    )


def missing_explicit_target(context: InvocationContext) -> dict[str, Any] | None:
    """T9/R9.1: the shared validation point for every transport. A catalog
    tool that validates its target (`ToolSpec.validates_target`) never runs
    against an explicitly requested target that does not exist. A `deleted`
    target with any other provenance (e.g. a staged deletion) stays legal."""
    from rush.catalog import TOOL_SPECS

    spec = TOOL_SPECS.get(context.operation_id)
    if spec is None or not spec.supports_path or not spec.validates_target:
        return None
    originals = context.original_requested_targets
    for index, target in enumerate(context.targets):
        if target.state == "deleted" and target.provenance == "explicit":
            shown = (
                originals[index]
                if index < len(originals)
                else target.relative_path.as_posix()
            )
            return target_error_result(
                context.operation_id,
                "TARGET_NOT_FOUND",
                f"target not found: {shown}",
                target=shown,
                reason="target_not_found",
            )
    return None


class InvocationExecutor:
    """Single execution boundary with registration-time signature adaptation and cache gating."""

    def __init__(self, cache: Any = None) -> None:
        self._registry: dict[str, RegisteredOperation] = {}
        self._cache = cache

    @property
    def cache(self) -> Any:
        return self._cache

    @cache.setter
    def cache(self, val: Any) -> None:
        self._cache = val

    def register(
        self,
        operation_id: str,
        handler: Callable[..., Any],
        pure: bool = False,
    ) -> RegisteredOperation:
        """Adapt handler signature once and store in registry."""
        adapter = adapt_signature_at_registration(handler, operation_id=operation_id)
        operation = RegisteredOperation(
            operation_id=operation_id,
            handler=handler,
            signature_adapter=adapter,
            pure=pure,
        )
        self._registry[operation_id] = operation
        return operation

    def get_registered(self, operation_id: str) -> RegisteredOperation | None:
        """Return registered operation by ID if present."""
        return self._registry.get(operation_id)

    def execute(self, context: InvocationContext) -> Any:
        """Execute registered operation exactly once without retry.

        Retrieves registered operation, checks deterministic cache policy,
        adapts context into args/kwargs, and invokes handler(*args, **kwargs).
        Propagates genuine exceptions directly without catching TypeError for retry.
        """
        operation = self._registry.get(context.operation_id)
        if operation is None:
            raise InvocationError(
                f"Operation '{context.operation_id}' is not registered in InvocationExecutor"
            )

        missing = missing_explicit_target(context)
        if missing is not None:
            return missing

        from rush.invocation.cache_policy import decide_cache

        decision = decide_cache(context, pure=operation.pure)

        if (
            decision.decision == "eligible"
            and self._cache is not None
            and decision.cache_key is not None
        ):
            cached_result = self._cache.get(decision.cache_key)
            if cached_result is not None:
                return mark_cache_hit(cached_result, decision.cache_key)

        args, kwargs = operation.signature_adapter(context)

        # S01: the shared ownership boundary for every registered operation.
        # Individual tool call sites need not forward owner_instance_id/run_id
        # themselves -- `run_subprocess` already adopts this ambient pair
        # when no explicit one reaches it (see `owned_execution_scope`).
        owner_instance_id = context.owner_instance_id or None
        run_id = context.run_id or None
        if (owner_instance_id is None) != (run_id is None):
            raise InvocationError(
                "owner_instance_id and run_id must be supplied together, or not at all"
            )

        from rush.runtime.subprocesses import owned_execution_scope

        # Invokes handler(*args, **kwargs) exactly once. Zero retry on TypeError.
        with (
            owned_execution_scope(owner_instance_id, run_id),
            _invocation_root_scope(context),
        ):
            result = operation.handler(*args, **kwargs)
        result = with_default_scope(result, context)

        # MC05 §6.4: capture one real observation after execution, before the
        # result-cache write, only when opted in and host-granted cache_write.
        # Memory/telemetry operations never recursively record themselves.
        # Never converts or reruns the original result on any observation failure.
        if (
            context.memory_record
            and "cache_write" in context.permissions
            and context.operation_id != "memory"
        ):
            result = _record_observation(context, result)

        if (
            decision.decision == "eligible"
            and self._cache is not None
            and decision.cache_key is not None
        ):
            try:
                self._cache.set(decision.cache_key, result)
            except Exception:  # noqa: BLE001, S110
                pass

        return result


def _record_observation(context: InvocationContext, result: Any) -> Any:
    """MC05/T19: commit one observation and attach its `written` receipt after
    the tool's own receipts. A failed write (`None` or a raise) attaches
    nothing and never converts or reruns the original result."""
    try:
        from rush.memory.experience import record_observation
        from rush.tools.routing import (
            attach_memory_attribution,
            memory_block,
            memory_receipt,
        )

        artifact = record_observation(context, result)
        if artifact is None:
            return result
        return attach_memory_attribution(
            result,
            memory_block(
                written=[
                    memory_receipt(
                        artifact.id,
                        artifact.artifact_version,
                        artifact.source,
                        "observation",
                    )
                ]
            ),
        )
    except Exception:  # noqa: BLE001
        return result


def _with_metadata(result: Any, update: Callable[[dict[str, Any]], None]) -> Any:
    """Apply `update` to a copy of the result's metadata: legacy
    `metadata`, or `extensions.metadata` of a strict ToolResultV1."""
    if isinstance(result, ToolResultV1):
        from rush.tools.routing import with_v1_extensions

        extensions = copy.deepcopy(result.extensions)
        metadata = dict(extensions.get("metadata") or {})
        update(metadata)
        extensions["metadata"] = metadata
        return with_v1_extensions(result, extensions)
    if not isinstance(result, dict):
        return result
    updated = dict(result)
    metadata = dict(updated.get("metadata") or {})
    update(metadata)
    updated["metadata"] = metadata
    return updated


def _current_metadata(result: Any) -> dict[str, Any]:
    if isinstance(result, ToolResultV1):
        return dict(result.extensions.get("metadata") or {})
    if isinstance(result, dict):
        return dict(result.get("metadata") or {})
    return {}


def mark_cache_hit(result: Any, cache_key: str) -> Any:
    """T16 §3 item 4: a cache hit returns a copy carrying
    `metadata.execution.cache={"hit": true, "cache_key": key}`; the cached
    object -- and its original scope -- is never rewritten.

    T19 B6: the original invocation's memory receipts move to
    `metadata.cache.original_memory`; this invocation consumed and committed
    nothing, so the copy carries no `metadata.memory`."""
    result = copy.deepcopy(result)

    def update(metadata: dict[str, Any]) -> None:
        execution = dict(metadata.get("execution") or {})
        execution["cache"] = {"hit": True, "cache_key": cache_key}
        metadata["execution"] = execution
        original_memory = metadata.pop("memory", None)
        if original_memory is not None:
            metadata["cache"] = {
                **(metadata.get("cache") or {}),
                "original_memory": original_memory,
            }

    return _with_metadata(result, update)


def default_scope(result: Any, context: InvocationContext) -> dict[str, Any]:
    """R16.2: the scope of a catalog result whose tool reports none --
    `unavailable` with a reason, never a guessed count."""
    from rush.catalog import TOOL_SPECS

    logical, _ = _invocation_roots(context)
    kind = TOOL_SPECS[context.operation_id].scope_kind
    engines = _current_metadata(result).get("engines") or []
    originals = context.original_requested_targets
    scope: dict[str, Any] = {
        "version": 1,
        "kind": kind,
        "logical_root": str(logical),
        "requested_targets": [t.relative_path.as_posix() for t in context.targets],
        "original_requested_targets": [_redacted(o) for o in originals]
        if originals
        else None,
        "invocation_start_cwd": str(context.invocation_start_cwd)
        if context.invocation_start_cwd is not None
        else None,
        "execution_cwds": list(
            dict.fromkeys(str(e["cwd"]) for e in engines if e.get("cwd"))
        ),
        "requested_file_count": None,
        "matched_file_count": None,
        "consumed_file_count": None,
        "coverage": "unavailable",
        "reason": "tool_reports_no_file_consumption",
    }
    if kind == "operation":
        scope["file_count"] = None
        scope["reason"] = "not_file_analysis"
    return scope


def with_default_scope(result: Any, context: InvocationContext) -> Any:
    """S16.1: every catalog ToolResult carries a v1 `metadata.scope` (strict
    V1: `extensions.metadata.scope`); a tool's own v1 scope is kept."""
    from rush.catalog import TOOL_SPECS

    if context.operation_id not in TOOL_SPECS:
        return result
    if not isinstance(result, (dict, ToolResultV1)):
        return result
    scope = _current_metadata(result).get("scope")
    if isinstance(scope, dict) and scope.get("version") == 1:
        return result
    fallback = default_scope(result, context)
    return _with_metadata(result, lambda metadata: metadata.update(scope=fallback))


def format_signature_error_diagnostic(
    error: SignatureAdaptationError | Exception,
    transport: Literal["cli", "mcp"] = "cli",
) -> dict[str, Any]:
    """Format signature adaptation error into a standardized diagnostic structure across transports."""
    op_id = getattr(error, "operation_id", "")
    param = getattr(error, "param_name", "")
    return {
        "status": "error",
        "error_type": type(error).__name__,
        "operation_id": op_id,
        "param_name": param,
        "message": str(error),
        "transport": transport,
        "diagnostic_code": "SIGNATURE_ADAPTATION_FAILED",
    }


__all__ = [
    "InvocationExecutor",
    "RegisteredOperation",
    "ToolResultV1",
    "adapt_signature_at_registration",
    "current_execution_root",
    "current_invocation_root",
    "format_signature_error_diagnostic",
    "invalid_target_result",
    "invocation_arguments",
    "missing_explicit_target",
    "target_error_result",
]
