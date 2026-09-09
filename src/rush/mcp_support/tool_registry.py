"""MCP tool registry and wrapper helpers."""

from __future__ import annotations

import functools
import inspect
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from rush.invocation import InvocationExecutor, resolve_invocation
from rush.invocation.executor import invocation_arguments
from rush.safety.redactor import sanitize_value


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
        context = resolve_invocation(req, transport="mcp", workspace_root=root)
        return exec_instance.execute(context)

    tool_mcp_wrapper.__self__ = tool
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
        context = resolve_invocation(req, transport="mcp", workspace_root=root)
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
