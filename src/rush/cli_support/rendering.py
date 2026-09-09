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
from rush.invocation import InvocationExecutor, resolve_invocation
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
    try:
        config = load_config(start=path)
    except RushConfigError as e:
        click.echo(str(e), err=True)
        sys.exit(2)
    executor = InvocationExecutor()
    executor.register(tool_name, tool.__call__)
    kwargs = dict(extra_kwargs or {})
    target_p = path.resolve()
    workspace_root = target_p if target_p.is_dir() else target_p.parent
    req = {
        "operation_id": tool_name,
        "path": str(path),
        "permissions": permissions,
        **kwargs,
    }
    context = resolve_invocation(
        req,
        transport="cli",
        workspace_root=workspace_root,
        config=config,
        permissions=permissions,
    )
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
