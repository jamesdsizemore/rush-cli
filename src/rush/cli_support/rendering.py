"""CLI rendering and tool execution helpers."""

from __future__ import annotations

import dataclasses
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import click

from rush.config import RushConfigError, load_config
from rush.contracts.results import ToolResultV1
from rush.delivery import compact
from rush.invocation import InvocationContext, InvocationExecutor, resolve_invocation
from rush.invocation.executor import invalid_target_result
from rush.invocation.models import InvalidTargetError
from rush.invocation.targets import (
    RootSelection,
    assert_contained,
    assert_root_config_not_linked,
    select_root,
)
from rush.permissions import ExecutionPermissions
from rush.theme import (
    ROW_CAP,
    copyable_json_command,
    render_result,
    safe_terminal_text,
)
from rush.tools import ALL_TOOLS


class TargetPath(click.Path):
    """T9: an analysis target argument, parsed lexically. Existence is never
    checked here -- a missing target reaches the shared executor validation
    (`TARGET_NOT_FOUND`) -- and input `os.stat` rejects outright (an embedded
    NUL raises `ValueError`, which `click.Path` does not catch) is passed on
    to `select_root`, which reports it as `TARGET_INVALID`."""

    def convert(
        self, value: Any, param: click.Parameter | None, ctx: click.Context | None
    ) -> Any:
        try:
            return super().convert(value, param, ctx)
        except ValueError:
            return self.coerce_path_result(value)


_STATUS_EXIT_CODES = {
    "ok": 0,
    "skipped": 0,
    "warn": 1,
    "fail": 1,
    "error": 2,
    "fatal": 2,
}


def _status_of(result: Any) -> Any:
    if hasattr(result, "status"):
        return result.status
    if isinstance(result, dict):
        return result.get("status")
    return result if isinstance(result, str) else None


def exit_code_for(result: Any) -> int:
    """Map canonical statuses or admin return values to CLI process exit codes.

    T27: a missing or unknown status is INVALID_RESULT (exit 2), never 0."""
    if isinstance(result, int) and not isinstance(result, bool):
        return result
    status = _status_of(result)
    return _STATUS_EXIT_CODES.get(status, 2) if isinstance(status, str) else 2


def report_invalid_result(result: Any) -> None:
    """T27: print INVALID_RESULT on stderr for a result with no valid status."""
    if isinstance(result, int) and not isinstance(result, bool):
        return
    status = _status_of(result)
    if not isinstance(status, str) or status not in _STATUS_EXIT_CODES:
        echo(f"INVALID_RESULT: result has no valid ToolStatus ({status!r})", err=True)


def echo(message: Any = None, **kwargs: Any) -> None:
    """`click.echo` with X3 terminal safety for every dynamic string."""
    if message is not None and not isinstance(message, bytes | bytearray):
        message = safe_terminal_text(str(message))
    click.echo(message, **kwargs)


def secho(message: Any = None, **kwargs: Any) -> None:
    """`click.secho` with X3 terminal safety; styling is applied afterwards."""
    if message is not None and not isinstance(message, bytes | bytearray):
        message = safe_terminal_text(str(message))
    click.secho(message, **kwargs)


COLLECTION_ROUTES: dict[click.Command, tuple[str, ...]] = {}


def collection_route(
    *json_rows: str,
) -> Callable[[click.Command], click.Command]:
    """T27: register an admin command whose human view is capped row lists.

    `json_rows` are the dotted `--json` paths holding each full list, in the
    order the command calls `echo_rows`."""

    def mark(command: click.Command) -> click.Command:
        COLLECTION_ROUTES[command] = json_rows
        return command

    return mark


def echo_rows(
    rows: Sequence[Any],
    line: Callable[[Any], str],
    *,
    cap: int = ROW_CAP,
    noun: str = "records",
    err: bool = False,
) -> None:
    """T27 §1: at most `cap` rows, then always the exact shown/total; when
    truncated, also the copyable `rush ... --json` that prints every row."""
    total = len(rows)
    for row in rows[:cap]:
        echo(line(row), err=err)
    shown = min(total, cap)
    if shown < total:
        command = copyable_json_command("rush")
        echo(f"shown {shown}/{total} {noun}; full list: {command}", err=err)
    else:
        echo(f"{shown}/{total} {noun}", err=err)


def _jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [_jsonable(v) for v in value]
    return value


def echo_json(data: Any) -> None:
    """The untruncated, redacted `--json` view of an admin command's data."""
    from rush.safety.redactor import sanitize_value

    clean = sanitize_value(_jsonable(data)).value
    echo(json.dumps(clean, indent=2, default=str))


def export_reports(
    result: Any,
    tool_name: str | None,
    export_sarif: Path | None,
    export_html: Path | None,
) -> None:
    """Write the requested SARIF/HTML exports of `result` (T16: in compact
    mode this is always the full redacted result, never the projection)."""
    if export_sarif is not None and tool_name:
        from rush.sarif import export_to_sarif

        sarif_doc = export_to_sarif(result, tool_name=tool_name)
        export_sarif.write_text(json.dumps(sarif_doc, indent=2), encoding="utf-8")

    if export_html is not None:
        from rush.html_export import export_to_html

        title = f"Rush {tool_name} Report" if tool_name else "Rush Report"
        html_doc = export_to_html(result, title=title)
        export_html.write_text(html_doc, encoding="utf-8")


def exit_with_result(
    result: Any,
    as_json: bool = False,
    tool_name: str | None = None,
    export_sarif: Path | None = None,
    export_html: Path | None = None,
) -> None:
    """Sanitize output via sanitize_value, export SARIF/HTML if requested, print output, and exit."""
    from rush.safety.redactor import sanitize_value

    export_reports(result, tool_name, export_sarif, export_html)

    clean_result = sanitize_value(result).value
    if as_json:
        echo(json.dumps(clean_result, indent=2, default=str))
    elif (
        isinstance(clean_result, dict)
        and "tool" in clean_result
        and "status" in clean_result
    ):
        render_result(clean_result)
    elif clean_result is not None and not isinstance(clean_result, int):
        echo(str(clean_result))

    report_invalid_result(result)
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


def prepare_cli_tool(
    tool_name: str,
    path: Path,
    *,
    original: tuple[str, ...] | None,
    extra_kwargs: dict[str, Any] | None = None,
    permissions: ExecutionPermissions | None = None,
) -> tuple[Path, Callable[[], Any]] | dict[str, Any]:
    """Select, contain and resolve one catalog tool invocation without
    running it: `(logical_root, run)`, or the `TARGET_INVALID` result.

    T9/R9.2: a malformed target (`InvalidTargetError`) is a `TARGET_INVALID`
    result -- zero engine calls, no traceback. Containment errors keep T8's
    raise contract. A missing target reaches the executor's shared
    validation (`TARGET_NOT_FOUND`)."""
    tool = next((t for t in ALL_TOOLS if t.name == tool_name), None)
    if tool is None:
        click.echo(f"unknown tool: {tool_name}", err=True)
        sys.exit(2)
    try:
        selection = select_cli_target(path, anchor=Path.cwd())
        context = cli_invocation_context(
            tool_name,
            selection,
            original=original,
            extra_kwargs=extra_kwargs,
            permissions=permissions,
        )
    except InvalidTargetError as exc:
        return invalid_target_result(tool_name, exc)
    except RushConfigError as e:
        click.echo(str(e), err=True)
        sys.exit(2)
    executor = InvocationExecutor()
    executor.register(tool_name, tool.__call__)
    return selection.root, lambda: executor.execute(context)


def execute_cli_tool(
    tool_name: str,
    path: Path,
    *,
    original: tuple[str, ...] | None,
    extra_kwargs: dict[str, Any] | None = None,
    permissions: ExecutionPermissions | None = None,
) -> Any:
    """Run one catalog tool for one CLI target and return its result."""
    prepared = prepare_cli_tool(
        tool_name,
        path,
        original=original,
        extra_kwargs=extra_kwargs,
        permissions=permissions,
    )
    return prepared if isinstance(prepared, dict) else prepared[1]()


def deliver_cli(
    tool_name: str,
    view: compact.ViewOptions,
    prepare: Callable[[], compact.Prepared | dict[str, Any]],
    *,
    as_json: bool,
    permissions: ExecutionPermissions | None,
    export_sarif: Path | None,
    export_html: Path | None,
) -> None:
    """T16 §3 item 7: one `compact.deliver` call, then render and exit. In
    compact mode SARIF/HTML exports receive the full redacted result."""

    def export(full: dict[str, Any]) -> None:
        export_reports(full, tool_name, export_sarif, export_html)

    result = compact.deliver(
        tool_name,
        view,
        cache_write=bool(permissions and permissions.cache_write),
        prepare=prepare,
        serialize=compact.cli_size,
        export=export if view.compact else None,
    )
    exit_with_result(
        result,
        as_json=as_json,
        tool_name=tool_name,
        export_sarif=None if view.compact else export_sarif,
        export_html=None if view.compact else export_html,
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
    view: compact.ViewOptions | None = None,
) -> None:
    """Shared helper: find the tool, call it via InvocationExecutor, sanitize, render, exit."""
    view = view or compact.ViewOptions()
    if view.no_cache:
        extra_kwargs = {**(extra_kwargs or {}), "cache_policy": "bypass"}
    original = None if _path_param_defaulted() else (str(path),)
    deliver_cli(
        tool_name,
        view,
        lambda: prepare_cli_tool(
            tool_name,
            path,
            original=original,
            extra_kwargs=extra_kwargs,
            permissions=permissions,
        ),
        as_json=as_json,
        permissions=permissions,
        export_sarif=export_sarif,
        export_html=export_html,
    )


def _render_session_result(
    result: Mapping[str, object] | ToolResultV1, as_json: bool
) -> None:
    rendered = result.to_dict() if isinstance(result, ToolResultV1) else dict(result)
    if as_json:
        echo(json.dumps(rendered, indent=2, default=str))
    else:
        render_result(rendered)
    from rush.tools.common import exit_code_for as session_exit_code_for

    report_invalid_result(rendered)
    raise click.exceptions.Exit(session_exit_code_for(rendered))
