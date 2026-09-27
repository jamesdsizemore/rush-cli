"""MCP tool registry and wrapper helpers."""

from __future__ import annotations

import functools
import inspect
import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Annotated, Any, Literal, cast, get_args

from pydantic import Field

from rush.config import RushConfigError, load_config
from rush.delivery import compact
from rush.invocation import InvocationContext, InvocationExecutor, resolve_invocation
from rush.invocation.executor import invalid_target_result, invocation_arguments
from rush.invocation.models import InvalidTargetError, SignatureAdaptationError
from rush.invocation.targets import (
    anchor_path_value,
    assert_contained,
    assert_root_config_not_linked,
    registered_root_index,
    route_project_reference,
    select_member,
    select_root,
)
from rush.safety.redactor import sanitize_value


def _load_config_or_none(root: Path) -> Any:
    """Best-effort `rush.toml` load for MCP invocations.

    MC05: MCP invocations must resolve real `[tools.memory]` config (same as the
    CLI in `cli_support/rendering.py`) so `memory_record` is populated
    identically on both transports. T8: discovery starts at the selected
    logical root, after containment. A malformed `rush.toml` fails open to no
    config here (unchanged pre-MC05 MCP behavior) rather than newly breaking
    every MCP tool call over a config error MCP never validated before.
    """
    try:
        return load_config(start=root)
    except RushConfigError:
        return None


# §3.8: cwd-relative secondary arguments, anchored like the target itself
# (to the declared root, else the server-start cwd). Root- or target-relative
# arguments keep their own tool contracts and are deliberately absent.
_CWD_RELATIVE_ARGS: dict[str, tuple[str, ...]] = {
    "coverage": ("report_path",),
    "codeql": ("report_path",),
    "snapshot": ("report_path",),
    "pbt": ("report_path",),
    "mutation": ("report_path",),
    "flaky": ("report_path",),
    "contract": ("report_path",),
    "fuzz": ("report_path",),
    "load": ("report_path",),
    "sbom": ("output_path",),
    "offline-review": ("runner_path",),
    # T12 S12.7/finding 7: containment and family checks follow in the tool.
    "typecheck": ("typecheck_config",),
}

_PROJECT_DESCRIPTION = (
    "Registered project ID or registered project root path (§3.2). When "
    "given, every relative path in this call resolves against that project "
    "root instead of the server-start working directory; without it, "
    "relative paths resolve against the server-start working directory."
)


def _public_signature(sig: inspect.Signature) -> inspect.Signature:
    """The published MCP signature: no `_`-prefixed internal parameter, and
    exactly one optional declared-root argument -- the tool's own
    `project_id` (re-described), or an injected keyword-only `project`."""
    params = [p for p in sig.parameters.values() if not p.name.startswith("_")]
    if "project_id" in sig.parameters:
        params = [
            p.replace(
                annotation=Annotated[
                    str | None,
                    Field(
                        description="Also serves as this call's declared root. "
                        + _PROJECT_DESCRIPTION
                    ),
                ]
            )
            if p.name == "project_id"
            else p
            for p in params
        ]
        return sig.replace(parameters=params)
    if "project" in sig.parameters:
        return sig.replace(parameters=params)
    project = inspect.Parameter(
        "project",
        kind=inspect.Parameter.KEYWORD_ONLY,
        default=None,
        annotation=Annotated[str | None, Field(description=_PROJECT_DESCRIPTION)],
    )
    insert_at = next(
        (
            index
            for index, p in enumerate(params)
            if p.kind is inspect.Parameter.VAR_KEYWORD
        ),
        len(params),
    )
    params.insert(insert_at, project)
    return sig.replace(parameters=params)


# T16 R16.5/finding 1: the view parameters every catalog tool publishes.
# name -> (default, published annotation, annotations a tool may declare).
_VIEW_PARAMS: dict[str, tuple[Any, Any, tuple[Any, ...]]] = {
    "result_view": (
        None,
        compact.ResultViewParam,
        (str | None, Literal["full", "compact"] | None, compact.ResultViewParam),
    ),
    "limit": (None, compact.LimitParam, (int | None, compact.LimitParam)),
    "max_bytes": (None, compact.MaxBytesParam, (int | None, compact.MaxBytesParam)),
    "no_cache": (
        False,
        Annotated[
            bool,
            Field(description="Bypass the result cache; not allowed with compact."),
        ],
        (bool,),
    ),
}
_ALLOW_CACHE_WRITE = inspect.Parameter(
    "allow_cache_write",
    kind=inspect.Parameter.KEYWORD_ONLY,
    default=False,
    annotation=Annotated[
        bool, Field(description="Explicitly authorize local cache modification.")
    ],
)


def _declared_view_params(tool_name: str, sig: inspect.Signature) -> frozenset[str]:
    """Finding 1: view parameters the tool declares itself. Each must use the
    identical contract (same default, an equivalent type); only a different
    contract is a registration-time `SignatureAdaptationError`."""
    declared = frozenset(_VIEW_PARAMS) & frozenset(sig.parameters)
    for name in declared:
        default, _, accepted = _VIEW_PARAMS[name]
        param = sig.parameters[name]
        annotation_ok = (
            param.annotation is inspect.Parameter.empty or param.annotation in accepted
        )
        if param.default is not default or not annotation_ok:
            raise SignatureAdaptationError(
                f"Tool '{tool_name}' declares '{name}' with a contract that "
                "differs from the shared result-view parameter",
                operation_id=tool_name,
                param_name=name,
            )
    return declared


def _with_view_params(sig: inspect.Signature) -> inspect.Signature:
    """Publish each view parameter exactly once (declared ones get the shared
    annotation), plus `allow_cache_write` only when the tool lacks it."""
    params = [
        p.replace(annotation=_VIEW_PARAMS[p.name][1]) if p.name in _VIEW_PARAMS else p
        for p in sig.parameters.values()
    ]
    names = {p.name for p in params}
    extra = [
        inspect.Parameter(
            name,
            kind=inspect.Parameter.KEYWORD_ONLY,
            default=default,
            annotation=annotation,
        )
        for name, (default, annotation, _) in _VIEW_PARAMS.items()
        if name not in names
    ]
    if "allow_cache_write" not in names:
        extra.append(_ALLOW_CACHE_WRITE)
    insert_at = next(
        (i for i, p in enumerate(params) if p.kind is inspect.Parameter.VAR_KEYWORD),
        len(params),
    )
    return sig.replace(parameters=[*params[:insert_at], *extra, *params[insert_at:]])


def _take_view_options(
    call_args: dict[str, Any], declared: frozenset[str]
) -> compact.ViewOptions:
    """R16.5: injected view parameters are consumed here and never reach the
    tool; declared ones stay for the tool too. `no_cache` becomes the
    request's `cache_policy`."""
    values = {
        name: call_args.get(name) if name in declared else call_args.pop(name, None)
        for name in _VIEW_PARAMS
    }
    if values["no_cache"]:
        call_args["cache_policy"] = "bypass"
    return compact.ViewOptions(
        result_view=values["result_view"],
        limit=values["limit"],
        max_bytes=values["max_bytes"],
        no_cache=bool(values["no_cache"]),
    )


def _mcp_serializer(wrapper: Callable[..., Any]) -> compact.Serializer:
    """R16.6: measure with FastMCP's own result conversion for this tool."""
    from mcp.server.fastmcp.tools.base import Tool

    metadata = Tool.from_function(wrapper).fn_metadata
    return compact.mcp_size(metadata.convert_result)


def _declared_root(value: Any, anchor: Path, index: Mapping[str, str]) -> Path | None:
    """§3.2/T8: route a declared `project`/`project_id` (ID first, then a path
    anchored to the server-start cwd). `None` when nothing was declared."""
    if value is None:
        return None
    from rush.workflows.projects import ProjectRootMissingError

    _, root = route_project_reference(value, anchor=anchor, index=index)
    if not root.is_dir():
        raise ProjectRootMissingError(
            str(sanitize_value(f"registered project root is missing: {root}").value)
        )
    return root


def _anchored_arg(value: Any, anchor: Path) -> Any:
    if isinstance(value, Path):
        return value if value.is_absolute() else anchor / value
    return anchor_path_value(value, anchor)


def _standard_context(
    tool_name: str,
    call_args: dict[str, Any],
    cwd_relative: tuple[str, ...],
    *,
    server_anchor: Path,
    declared: Path | None,
    index: Mapping[str, str],
) -> InvocationContext:
    """The standard wrapper's T8 walk, member walk, containment pre-check and
    invocation. Raises `InvalidTargetError` for malformed input (T9)."""
    anchor = declared or server_anchor
    raw = call_args.pop("path", None)
    selection = select_root(
        "." if raw is None else str(raw),
        anchor=anchor,
        declared_root=declared,
        index=index,
    )
    # `files`/`paths` members are root-relative (their base contract),
    # walked like the target and required to stay under the root.
    for key in ("files", "paths"):
        members = call_args.get(key)
        if isinstance(members, (list, tuple)):
            call_args[key] = [
                select_member(
                    str(member),
                    anchor=selection.root,
                    root=selection.root,
                    index=index,
                ).as_posix()
                for member in members
            ]
    for key in cwd_relative:
        if call_args.get(key) is not None:
            call_args[key] = _anchored_arg(call_args[key], anchor)
    assert_contained(selection)
    assert_root_config_not_linked(selection.root)
    req = {
        "operation_id": tool_name,
        "path": selection.relative.as_posix(),
        **call_args,
    }
    return resolve_invocation(
        req,
        transport="mcp",
        workspace_root=selection.root,
        config=_load_config_or_none(selection.root),
        original_requested_targets=None if raw is None else (str(raw),),
        invocation_start_cwd=server_anchor,
        declared_root=declared,
    )


def _callable_signature(sig: inspect.Signature, tool: Any) -> inspect.Signature:
    """T23: parameters a caller can never supply -- the invocation context
    (`context`/`ctx` or an `InvocationContext` annotation, bound by the
    executor) and a tool's declared `internal_parameters` -- are not
    published."""
    internal: frozenset[str] = getattr(tool, "internal_parameters", frozenset())
    return sig.replace(
        parameters=[
            p
            for p in sig.parameters.values()
            if p.name not in ("context", "ctx")
            and p.name not in internal
            and InvocationContext not in (p.annotation, *get_args(p.annotation))
        ]
    )


def make_tool_wrapper(
    tool: Any,
    executor: InvocationExecutor | None = None,
    anchor_cwd: Path | None = None,
) -> Callable[..., Any]:
    """Wrap a catalog ToolFn into an MCP tool handler using InvocationExecutor.

    Without a shared `executor` the wrapper owns a private one, with this
    tool registered on it (`register_all_tools` registers on the shared one)."""
    if executor is None:
        executor = InvocationExecutor()
        executor.register(tool.name, tool.__call__)
    exec_instance = executor
    real_sig = inspect.signature(tool.__call__, eval_str=True)
    declared_views = _declared_view_params(tool.name, real_sig)
    public_sig = _with_view_params(
        _public_signature(_callable_signature(real_sig, tool))
    )
    inject = (
        "project_id" not in real_sig.parameters and "project" not in real_sig.parameters
    )
    cwd_relative = _CWD_RELATIVE_ARGS.get(tool.name, ())
    serializer: list[compact.Serializer] = []

    def prepare(call_args: dict[str, Any]) -> compact.Prepared | dict[str, Any]:
        # T8: build_server's server-start snapshot stays fixed regardless of a
        # later chdir; a wrapper built without one uses the live cwd per call.
        server_anchor = anchor_cwd if anchor_cwd is not None else Path.cwd()
        if inject:
            value = call_args.pop("project", None)
        else:
            value = call_args.get(
                "project_id" if "project_id" in real_sig.parameters else "project"
            )
        index = registered_root_index(strict=value is not None)
        declared = _declared_root(value, server_anchor, index)
        try:
            context = _standard_context(
                tool.name,
                call_args,
                cwd_relative,
                server_anchor=server_anchor,
                declared=declared,
                index=index,
            )
        except InvalidTargetError as exc:
            # T9/R9.2: malformed input is a result, never a traceback.
            return invalid_target_result(tool.name, exc)
        return context.workspace_root, lambda: exec_instance.execute(context)

    def serialize(value: dict[str, Any]) -> int:
        if not serializer:
            serializer.append(_mcp_serializer(tool_mcp_wrapper))
        return serializer[0](value)

    @functools.wraps(tool.__call__)
    def tool_mcp_wrapper(*args: Any, **kwargs: Any) -> Any:
        call_args = dict(public_sig.bind(*args, **kwargs).arguments)
        options = _take_view_options(call_args, declared_views)
        # T16 §3 item 7: one delivery call per request, compact or full.
        return compact.deliver(
            tool.name,
            options,
            cache_write=bool(call_args.get("allow_cache_write")),
            prepare=lambda: prepare(call_args),
            serialize=serialize,
        )

    tool_mcp_wrapper.__dict__["__self__"] = tool
    tool_mcp_wrapper.__dict__["__signature__"] = public_sig
    return tool_mcp_wrapper


def _custom_context(
    tool_id: str,
    call_args: dict[str, Any],
    path_key: str | None,
    *,
    inject: bool,
    server_anchor: Path,
) -> InvocationContext:
    """The custom wrapper's invocation: a bare request-dict tool is resolved
    at the server anchor; a path/file/target tool walks its target like the
    standard wrapper. Raises `InvalidTargetError` for malformed input (T9)."""
    if path_key is None:
        return resolve_invocation(
            {"operation_id": tool_id, **call_args},
            transport="mcp",
            workspace_root=server_anchor,
            config=_load_config_or_none(server_anchor),
            invocation_start_cwd=server_anchor,
        )
    value = call_args.pop("project", None) if inject else call_args.get("project")
    index = registered_root_index(strict=value is not None)
    declared = _declared_root(value, server_anchor, index)
    anchor = declared or server_anchor
    # An omitted path/file/target means "." exactly like the standard
    # wrapper: the anchor directory, never the climbed logical root.
    raw = call_args.get(path_key)
    selection = select_root(
        "." if raw is None else str(raw),
        anchor=anchor,
        declared_root=declared,
        index=index,
    )
    assert_contained(selection)
    assert_root_config_not_linked(selection.root)
    # The handler receives the contained canonical path, never the raw
    # relative string next to a root derived from it (the double rebase).
    req = {
        "operation_id": tool_id,
        **call_args,
        path_key: str(selection.target),
    }
    return resolve_invocation(
        req,
        transport="mcp",
        workspace_root=selection.root,
        config=_load_config_or_none(selection.root),
        original_requested_targets=None if raw is None else (str(raw),),
        invocation_start_cwd=server_anchor,
        declared_root=declared,
    )


def make_custom_wrapper(
    fn: Any,
    tool_id: str,
    executor: InvocationExecutor | None = None,
    anchor_cwd: Path | None = None,
) -> Callable[..., Any]:
    """Wrap a custom phase function into an MCP tool handler using InvocationExecutor.

    `_`-prefixed parameters (e.g. `_anchor`) are internal: never published,
    never caller-supplied, bound from the invocation context instead.
    """
    exec_instance = executor if executor is not None else InvocationExecutor()
    real_sig = inspect.signature(fn, eval_str=True)
    visible = [p for p in real_sig.parameters if not p.startswith("_")]
    path_key = next((k for k in ("path", "file", "target") if k in visible), None)
    # Only a custom tool whose handler takes path/file/target is path-taking
    # and gets `project`; a bare `request` dict tool (rush_scan, rush_project)
    # is untouched and anchors its own request fields through `_anchor`.
    public_sig = (
        _public_signature(real_sig)
        if path_key is not None
        else real_sig.replace(
            parameters=[real_sig.parameters[name] for name in visible]
        )
    )
    inject = path_key is not None and "project" not in real_sig.parameters

    @functools.wraps(fn)
    def custom_mcp_wrapper(*args: Any, **kwargs: Any) -> Any:
        call_args = dict(public_sig.bind(*args, **kwargs).arguments)
        server_anchor = anchor_cwd if anchor_cwd is not None else Path.cwd()
        try:
            context = _custom_context(
                tool_id,
                call_args,
                path_key,
                inject=inject,
                server_anchor=server_anchor,
            )
        except InvalidTargetError as exc:
            # T9/R9.2: malformed input is a result, never a traceback.
            return invalid_target_result(tool_id, exc)
        return exec_instance.execute(context)

    custom_mcp_wrapper.__dict__["__signature__"] = public_sig
    return custom_mcp_wrapper


def register_all_tools(
    server: Any,
    executor: InvocationExecutor,
    tools: Sequence[Any],
    anchor_cwd: Path | None = None,
) -> None:
    """Register all catalog tools and legacy compatibility aliases onto FastMCP server."""
    for tool in tools:
        executor.register(tool.name, tool.__call__)
        server.add_tool(
            fn=make_tool_wrapper(tool, executor, anchor_cwd=anchor_cwd),
            name=f"rush_{tool.name.replace('-', '_')}",
            description=tool.mcp_description,
        )

    # Backward compatibility alias for rush_attest
    for tool in tools:
        if tool.name == "attest":
            server.add_tool(
                fn=make_tool_wrapper(tool, executor, anchor_cwd=anchor_cwd),
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
    # T8 (5.3)/§3.7: an internal root for the custom helpers -- the declared
    # root, else the server-start cwd. Never published, so never
    # caller-supplied; always overwritten here.
    if "_anchor" in sig.parameters:
        kwargs["_anchor"] = (
            context.declared_root
            if context.declared_root is not None
            else context.invocation_start_cwd
        )
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
    anchor_cwd: Path | None = None,
) -> None:
    """Register domain/phase custom tools onto FastMCP server."""
    for fn, name, desc in custom_tools:
        executor.register(name, _make_handler(fn))
        server.add_tool(
            fn=make_custom_wrapper(fn, name, executor, anchor_cwd=anchor_cwd),
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
