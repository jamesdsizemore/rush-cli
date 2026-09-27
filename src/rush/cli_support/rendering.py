"""CLI rendering and tool execution helpers."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import click

from rush.config import RushConfigError, load_config
from rush.contracts.results import ToolResultV1
from rush.invocation import InvocationContext, InvocationExecutor, resolve_invocation
from rush.invocation.targets import (
    RootSelection,
    assert_contained,
    assert_root_config_not_linked,
    select_root,
)
from rush.permissions import ExecutionPermissions
from rush.theme import render_result
from rush.tools import ALL_TOOLS


def exit_code_for(result: Any) -> int:
    """Map canonical statuses or admin return values to CLI process exit codes."""
    if isinstance(result, int) and not isinstance(result, bool):
        return result
    if hasattr(result, "status"):
        status = result.status
    elif isinstance(result, dict) and "status" in result:
        status = result.get("status")
    elif isinstance(result, str):
        status = result
    else:
        status = None

    if status in ("ok", "skipped"):
        return 0
    if status in ("warn", "fail"):
        return 1
    if status in ("error", "fatal"):
        return 2
    return 0


def exit_with_result(
    result: Any,
    as_json: bool = False,
    tool_name: str | None = None,
    export_sarif: Path | None = None,
    export_html: Path | None = None,
) -> None:
    """Sanitize output via sanitize_value, export SARIF/HTML if requested, print output, and exit."""
    from rush.safety.redactor import sanitize_value

    if export_sarif is not None and tool_name:
        from rush.sarif import export_to_sarif

        sarif_doc = export_to_sarif(result, tool_name=tool_name)
        export_sarif.write_text(json.dumps(sarif_doc, indent=2), encoding="utf-8")

    if export_html is not None:
        from rush.html_export import export_to_html

        title = f"Rush {tool_name} Report" if tool_name else "Rush Report"
        html_doc = export_to_html(result, title=title)
        export_html.write_text(html_doc, encoding="utf-8")

    clean_result = sanitize_value(result).value
    if as_json:
        click.echo(json.dumps(clean_result, indent=2, default=str))
    elif (
        isinstance(clean_result, dict)
        and "tool" in clean_result
        and "status" in clean_result
    ):
        render_result(clean_result)
    elif clean_result is not None and not isinstance(clean_result, int):
        click.echo(str(clean_result))

    sys.exit(exit_code_for(result))


def _path_param_defaulted() -> bool:
    """T8: a Click-defaulted `path` is not user input, so its original is
    unavailable rather than reported as typed."""
    ctx = click.get_current_context(silent=True)
    return (
        ctx is not None
        and ctx.get_parameter_source("path") is click.core.ParameterSource.DEFAULT
    )


def select_cli_target(path: Path | str, *, anchor: Path) -> RootSelection:
    """T8/§3.2: the invocation cwd is the anchor, used exactly once. The
    ROOT-ENTRY walk and the containment pre-check both run before any
    config read, hash or handler call."""
    selection = select_root(str(path), anchor=anchor)
    assert_contained(selection)
    assert_root_config_not_linked(selection.root)
    return selection


def cli_invocation_context(
    tool_name: str,
    selection: RootSelection,
    *,
    original: tuple[str, ...] | None,
    extra_kwargs: dict[str, Any] | None = None,
    permissions: ExecutionPermissions | None = None,
) -> InvocationContext:
    """The CLI invocation for an already-selected, contained target. Config
    discovery starts at the selected root; raises `RushConfigError` on a
    malformed one."""
    req = {
        "operation_id": tool_name,
        "path": selection.relative.as_posix(),
        "permissions": permissions,
        **(extra_kwargs or {}),
    }
    return resolve_invocation(
        req,
        transport="cli",
        workspace_root=selection.root,
        config=load_config(start=selection.root),
        permissions=permissions,
        original_requested_targets=original,
        invocation_start_cwd=selection.anchor,
    )


def _run_tool(
    tool_name: str,
    path: Path,
    *,
    as_json: bool,
    extra_kwargs: dict[str, Any] | None = None,
    permissions: ExecutionPermissions | None = None,
    export_sarif: Path | None = None,
    export_html: Path | None = None,
) -> None:
    """Shared helper: find the tool, call it via InvocationExecutor, sanitize, render, exit."""
    tool = next((t for t in ALL_TOOLS if t.name == tool_name), None)
    if tool is None:
        click.echo(f"unknown tool: {tool_name}", err=True)
        sys.exit(2)
    selection = select_cli_target(path, anchor=Path.cwd())
    try:
        context = cli_invocation_context(
            tool_name,
            selection,
            original=None if _path_param_defaulted() else (str(path),),
            extra_kwargs=extra_kwargs,
            permissions=permissions,
        )
    except RushConfigError as e:
        click.echo(str(e), err=True)
        sys.exit(2)
    executor = InvocationExecutor()
    executor.register(tool_name, tool.__call__)
    result = executor.execute(context)

    exit_with_result(
        result,
        as_json=as_json,
        tool_name=tool_name,
        export_sarif=export_sarif,
        export_html=export_html,
    )


def _render_session_result(
    result: Mapping[str, object] | ToolResultV1, as_json: bool
) -> None:
    rendered = result.to_dict() if isinstance(result, ToolResultV1) else dict(result)
    if as_json:
        click.echo(json.dumps(rendered, indent=2, default=str))
    else:
        render_result(rendered)
    from rush.tools.common import exit_code_for as session_exit_code_for

    raise click.exceptions.Exit(session_exit_code_for(rendered))
