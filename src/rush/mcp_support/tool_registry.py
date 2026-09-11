"""MCP tool registry and wrapper helpers."""

from __future__ import annotations

import functools
import inspect
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, cast

from rush.config import RushConfigError, load_config
from rush.invocation import InvocationExecutor, resolve_invocation
from rush.invocation.executor import invocation_arguments
from rush.safety.redactor import sanitize_value


def _load_config_or_none(root: Path) -> Any:
    """Best-effort `rush.toml` load for MCP invocations.

    MC05: MCP invocations must resolve real `[tools.memory]` config (same as CLI's
    `load_config(start=path)` in `cli_support/rendering.py`) so `memory_record` is
    populated identically on both transports. A malformed `rush.toml` fails open to
    no config here (unchanged pre-MC05 MCP behavior) rather than newly breaking
    every MCP tool call over a config error MCP never validated before.
    """
    try:
        return load_config(start=root)
    except RushConfigError:
        return None


def make_tool_wrapper(
    tool: Any, executor: InvocationExecutor | None = None
) -> Callable[..., Any]:
    """Wrap a catalog ToolFn into an MCP tool handler using InvocationExecutor."""
    exec_instance = executor if executor is not None else InvocationExecutor()

    @functools.wraps(tool.__call__)
    def tool_mcp_wrapper(*args: Any, **kwargs: Any) -> Any:
        bound = inspect.signature(tool.__call__).bind(*args, **kwargs)
        call_args = bound.arguments
        path_val = call_args.get("path", ".")
        p = Path(path_val).resolve()
        root = p if p.is_dir() else p.parent
        req = {
            "operation_id": tool.name,
            "path": str(p),
            **{k: v for k, v in call_args.items() if k != "path"},
        }
        context = resolve_invocation(
            req,
            transport="mcp",
            workspace_root=root,
            config=_load_config_or_none(root),
        )
        return exec_instance.execute(context)

    tool_mcp_wrapper.__dict__["__self__"] = tool
    return tool_mcp_wrapper


def make_custom_wrapper(
    fn: Any, tool_id: str, executor: InvocationExecutor | None = None
) -> Callable[..., Any]:
    """Wrap a custom phase function into an MCP tool handler using InvocationExecutor."""
    exec_instance = executor if executor is not None else InvocationExecutor()

    @functools.wraps(fn)
    def custom_mcp_wrapper(*args: Any, **kwargs: Any) -> Any:
        bound = inspect.signature(fn).bind(*args, **kwargs)
        call_args = bound.arguments
        path_val = call_args.get(
            "path", call_args.get("file", call_args.get("target", "."))
        )
        try:
            p = Path(path_val).resolve()
            root = p if p.is_dir() else p.parent
        except Exception:  # noqa: BLE001
            root = Path.cwd().resolve()
        req = {
            "operation_id": tool_id,
            **call_args,
        }
        context = resolve_invocation(
            req,
            transport="mcp",
            workspace_root=root,
            config=_load_config_or_none(root),
        )
        return exec_instance.execute(context)

    return custom_mcp_wrapper


def register_all_tools(
    server: Any,
    executor: InvocationExecutor,
    tools: Sequence[Any],
) -> None:
    """Register all catalog tools and legacy compatibility aliases onto FastMCP server."""
    for tool in tools:
        executor.register(tool.name, tool.__call__)
        server.add_tool(
            fn=make_tool_wrapper(tool, executor),
            name=f"rush_{tool.name.replace('-', '_')}",
            description=tool.mcp_description,
        )

    # Backward compatibility alias for rush_attest
    for tool in tools:
        if tool.name == "attest":
            server.add_tool(
                fn=make_tool_wrapper(tool, executor),
                name="rush_attest_generate",
                description="Deprecated alias for rush_attest",
            )
            break


def _bind_path_parameter(
    p_name: str,
    param_type: Any,
    kwargs: dict[str, Any],
    context: Any,
) -> None:
    target_p = (
        context.workspace_root / context.targets[0].relative_path
        if context.targets
        else context.workspace_root
    )
    kwargs[p_name] = target_p if param_type is Path else str(target_p)


def _bind_custom_handler_kwargs(
    target_fn: Any,
    context: Any,
) -> dict[str, Any]:
    kwargs = invocation_arguments(context)
    sig = inspect.signature(target_fn)
    for p_name in ("path", "file", "target"):
        if p_name in sig.parameters and p_name not in kwargs:
            param_type = sig.parameters[p_name].annotation
            _bind_path_parameter(p_name, param_type, kwargs, context)
    for p_name in sig.parameters:
        if p_name.startswith("allow_") and p_name not in kwargs:
            perm_name = p_name[6:]
            kwargs[p_name] = perm_name in context.permissions
    return kwargs


def _make_handler(target_fn: Any) -> Callable[[Any], Any]:
    def handler(context: Any) -> Any:
        kwargs = _bind_custom_handler_kwargs(target_fn, context)
        result = target_fn(**kwargs)
        if isinstance(result, str):
            try:
                structured = json.loads(result)
            except ValueError:
                pass
            else:
                if isinstance(structured, (dict, list)):
                    return json.dumps(sanitize_value(structured).value)
        return sanitize_value(result).value

    return handler


def register_custom_tools(
    server: Any,
    executor: InvocationExecutor,
    custom_tools: Sequence[tuple[Any, str, str]],
) -> None:
    """Register domain/phase custom tools onto FastMCP server."""
    for fn, name, desc in custom_tools:
        executor.register(name, _make_handler(fn))
        server.add_tool(
            fn=make_custom_wrapper(fn, name, executor),
            name=name,
            description=desc,
        )


_MEMORY_BRIDGE_OPERATIONS = ("receive", "expand", "related", "resume")


def build_memory_bridge_handler(
    *, root: Path, session_id: str, capability: str
) -> Callable[[str, dict[str, Any] | None], Any]:
    """MC11.3: the restricted-receiver `rush_memory` handler -- the *only* tool a
    `--memory-session` MCP server exposes. `operation` must be one of
    `_MEMORY_BRIDGE_OPERATIONS`; every other value (including every other catalog tool's
    name) is denied identically, never routed anywhere. `expand`/`related`/`resume` always
    run with this session's own stored `session_allowlist` -- a caller-supplied allowlist
    inside `request` can never widen it, because none is ever read from `request` here.
    """
    from rush.memory import handoff
    from rush.memory.store import TypedArtifactStore
    from rush.tools.memory import MemoryOperation, MemoryTool

    tool = MemoryTool()

    def rush_memory_bridge(
        operation: str, request: dict[str, Any] | None = None
    ) -> Any:
        if operation not in _MEMORY_BRIDGE_OPERATIONS:
            return {
                "schema_version": 1,
                "operation": operation,
                "code": "E_PERMISSION",
                "data": {
                    "message": "This restricted handoff receiver only permits "
                    f"{_MEMORY_BRIDGE_OPERATIONS}."
                },
            }
        validated_operation = cast(MemoryOperation, operation)
        store = TypedArtifactStore(root)
        try:
            session = handoff.load_session(store, session_id, capability)
        except handoff.HandoffError as exc:
            return {
                "schema_version": 1,
                "operation": operation,
                "code": exc.code,
                "data": {"message": str(exc)},
            }
        req = dict(request or {})
        if operation == "receive":
            req["session_id"] = session_id
            req["capability"] = capability
            result = tool(path=root, operation="receive", request=req)
        else:
            req.pop("session_allowlist", None)
            result = tool(
                path=root,
                operation=validated_operation,
                request=req,
                session_allowlist=list(session.session_allowlist),
            )
        return result["raw"]

    return rush_memory_bridge


def register_memory_bridge_tool(
    server: Any, *, root: Path, session_id: str, capability: str
) -> None:
    """MC11.3: register the single restricted `rush_memory` tool onto an MCP server built
    for one `--memory-session`. No other catalog tool is ever registered on this server."""
    server.add_tool(
        fn=build_memory_bridge_handler(
            root=root, session_id=session_id, capability=capability
        ),
        name="rush_memory",
        description=(
            "Restricted cross-tool memory handoff receiver bound to one bounded, "
            "capability-gated session. Only receive/expand/related/resume are permitted."
        ),
    )
