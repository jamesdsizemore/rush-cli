"""CLI catalog command scaffolding."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import click

from rush.catalog import TOOL_SPECS
from rush.cli_support.options import (
    _extract_permissions,
    permission_options,
    result_view_options,
)
from rush.cli_support.rendering import (
    TargetPath,
    _run_tool,
    deliver_cli,
    execute_cli_tool,
    select_cli_target,
)
from rush.delivery import compact
from rush.invocation.executor import invalid_target_result, target_error_result
from rush.invocation.models import InvalidTargetError
from rush.permissions import ExecutionPermissions
from rush.tools.base import ToolFn, ToolResult
from rush.tools.common import skipped_result
from rush.tools.routing import (
    aggregate_results,
    concat_engine_entries,
    no_target_scope,
)

_EMPTY_SELECTION_REASONS = {
    "staged": "no_staged_files",
    "changed": "no_changed_files",
    "since": "no_files_since_ref",
}


@dataclass(frozen=True)
class _Scope:
    """The catalog command's scoping flags (T9/finding 18)."""

    workspace_name: str | None
    all_workspaces: bool
    staged: bool
    changed: bool
    since: str | None

    @property
    def active(self) -> bool:
        return bool(
            self.workspace_name
            or self.all_workspaces
            or self.staged
            or self.changed
            or self.since
        )


def _skipped_scope(tool_name: str, summary: str, reason: str) -> dict[str, Any]:
    result = dict(skipped_result(tool_name, None, summary))
    result["metadata"] = {"scope": no_target_scope(reason, matched_file_count=0)}
    return result


def _git_selection(target: Path, scope: _Scope) -> tuple[str, list[Path]] | None:
    """The requested git selection (kind, files under `target`), or `None`
    when no selection flag is set."""
    base = target if target.is_dir() else target.parent
    if scope.staged:
        from rush.discovery.git import get_staged_files

        kind, files = "staged", get_staged_files(base)
    elif scope.changed:
        from rush.discovery.git import get_changed_files

        kind, files = "changed", get_changed_files(base)
    elif scope.since:
        from rush.discovery.git import get_files_since

        kind, files = "since", get_files_since(base, scope.since)
    else:
        return None
    anchor = target.resolve()
    return kind, [f for f in files if f == anchor or anchor in f.parents]


def _unit_result(
    tool_name: str, target: Path, scope: _Scope, run: dict[str, Any]
) -> dict[str, Any]:
    """One target's result: the whole target, or -- under a git selection --
    exactly the selected files (one invocation each), never the whole tree.
    An empty selection is a skipped result with the exact reason."""
    try:
        selection = _git_selection(target, scope)
    except ValueError as exc:  # a hostile `--since` ref (validate_git_ref)
        return target_error_result(
            tool_name,
            "TARGET_INVALID",
            str(exc),
            target=str(scope.since),
            reason="invalid_git_ref",
        )
    if selection is None:
        return cast(
            "dict[str, Any]",
            execute_cli_tool(tool_name, target, original=None, **run),
        )
    kind, files = selection
    if not files:
        return _skipped_scope(
            tool_name, f"no {kind} files under {target}", _EMPTY_SELECTION_REASONS[kind]
        )
    children = [
        execute_cli_tool(tool_name, file, original=None, **run) for file in files
    ]
    result = dict(aggregate_results(tool_name, children))
    result["metadata"] = {
        # T16 S16.2: every child's engine entries survive the selection.
        "engines": concat_engine_entries(children),
        "scope": {
            "version": 1,
            "kind": "files",
            "reason": f"{kind}_selection",
            "matched_file_count": len(files),
        },
        "children": [
            {"path": str(file), "status": child.get("status")}
            for file, child in zip(files, children, strict=True)
        ],
    }
    return result


def _workspace_units(
    tool_name: str, path: Path, scope: _Scope
) -> list[tuple[str, Path]] | dict[str, Any]:
    """The discovered workspaces to run, or the error/skipped result when the
    named workspace is unknown or none exist. `--all-workspaces` runs them in
    dependency-first (topological) order."""
    from rush.discovery.workspace import (
        discover_workspaces,
        topological_sort_workspaces,
    )

    try:
        packages = topological_sort_workspaces(
            discover_workspaces(path if path.is_dir() else path.parent)
        )
    except ValueError as exc:
        return target_error_result(
            tool_name,
            "TARGET_INVALID",
            str(exc),
            target=str(path),
            reason="workspace_definition_invalid",
        )
    if scope.workspace_name:
        matched = [w for w in packages if w.name == scope.workspace_name]
        if not matched:
            return target_error_result(
                tool_name,
                "TARGET_NOT_FOUND",
                f"workspace package '{scope.workspace_name}' not found under {path}",
                target=str(path),
                reason="workspace_not_found",
                extra={
                    "reason": "workspace_not_found",
                    "workspace": scope.workspace_name,
                },
            )
        packages = matched[:1]
    if not packages:
        return _skipped_scope(
            tool_name, f"no workspaces discovered under {path}", "no_workspaces"
        )
    return [(w.name, w.path) for w in packages]


def _scoped_result(
    tool_name: str, path: Path, scope: _Scope, run: dict[str, Any]
) -> dict[str, Any]:
    """T9/finding 18: `--workspace`, `--all-workspaces` and the git selection
    flags decide exactly what is analyzed; `--all-workspaces` returns one
    child per workspace."""
    if not (scope.workspace_name or scope.all_workspaces):
        return _unit_result(tool_name, path, scope, run)
    units = _workspace_units(tool_name, path, scope)
    if isinstance(units, dict):
        return units
    results = [_unit_result(tool_name, target, scope, run) for _, target in units]
    if scope.workspace_name:
        return results[0]
    aggregate = dict(aggregate_results(tool_name, cast("list[ToolResult]", results)))
    aggregate["metadata"] = {
        **cast("dict[str, Any]", aggregate.get("metadata") or {}),
        "children": [
            {
                "workspace": name,
                "path": str(target),
                "tool": result.get("tool"),
                "status": result.get("status"),
                "summary": result.get("summary"),
            }
            for (name, target), result in zip(units, results, strict=True)
        ],
    }
    return aggregate


def _prepare_scoped(
    tool_name: str, path: Path, scope: _Scope, run: dict[str, Any]
) -> compact.Prepared | dict[str, Any]:
    """The scoped run, deferred until the view checks pass (T16 §3 item 7)."""
    try:
        root = select_cli_target(path, anchor=Path.cwd()).root
    except InvalidTargetError as exc:
        return invalid_target_result(tool_name, exc)
    return root, lambda: _scoped_result(tool_name, path, scope, run)


def _run_catalog_command(
    tool_name: str,
    path: Path,
    scope: _Scope,
    *,
    as_json: bool,
    permissions: ExecutionPermissions,
    export_sarif: Path | None,
    export_html: Path | None,
    extra_kwargs: dict[str, Any] | None,
    view: compact.ViewOptions,
) -> None:
    """A missing target, or a call with no scoping flag, goes straight to the
    shared `_run_tool` path (so a missing target is `TARGET_NOT_FOUND` with no
    git or engine call); otherwise the scoped result is rendered."""
    if not scope.active or not os.path.lexists(path):
        _run_tool(
            tool_name,
            path,
            as_json=as_json,
            permissions=permissions,
            export_sarif=export_sarif,
            export_html=export_html,
            extra_kwargs=extra_kwargs,
            view=view,
        )
        return
    if view.no_cache:
        extra_kwargs = {**(extra_kwargs or {}), "cache_policy": "bypass"}
    run = {"extra_kwargs": extra_kwargs, "permissions": permissions}
    deliver_cli(
        tool_name,
        view,
        lambda: _prepare_scoped(tool_name, path, scope, run),
        as_json=as_json,
        permissions=permissions,
        export_sarif=export_sarif,
        export_html=export_html,
    )


# Per-tool CLI options, mapped explicitly (R11.6): generating flags from every
# tool's `option_specs` would silently add unrelated options to other commands.
_TOOL_CLI_OPTIONS: dict[str, tuple[click.Option, ...]] = {
    "typecheck": (
        click.Option(
            ["--environment"],
            type=click.Choice(["project", "isolated"]),
            default=None,
            help=(
                "Python interpreter environment: project (.venv, requires "
                "--allow-build) or isolated. Default prefers project and falls "
                "back to isolated without --allow-build."
            ),
        ),
        click.Option(
            ["--typecheck-config"],
            type=click.Path(dir_okay=False),
            default=None,
            # S12.7/finding 7: anchored to the invocation cwd, exactly once.
            callback=lambda _ctx, _param, value: (
                None if value is None else os.path.abspath(value)
            ),
            help=(
                "Owning config that wins over auto-detection: a tsconfig (.json) "
                "for tsc, or a mypy/pyrefly config for Python. Must lie within "
                "the project root; relative paths resolve against the current "
                "directory."
            ),
        ),
    ),
}


def build_catalog_path_command(tool: ToolFn) -> click.Command:
    """Build the standard ``PATH --json`` CLI surface for a catalog tool."""

    @click.command(
        name=tool.name,
        help=(
            f"{tool.mcp_description} Maturity: "
            f"{TOOL_SPECS[tool.name].maturity.replace('_', ' ')}."
        ),
    )
    @click.argument("path", type=TargetPath(path_type=Path))
    @click.option(
        "--report-path",
        type=click.Path(path_type=Path),
        default=None,
        help="Optional explicit report path for import mode.",
    )
    @click.option(
        "--export-sarif",
        type=click.Path(path_type=Path),
        default=None,
        help="Optional destination path to export SARIF 2.1.0 JSON report.",
    )
    @click.option(
        "--export-html",
        type=click.Path(path_type=Path),
        default=None,
        help="Optional destination path to export standalone HTML report artifact.",
    )
    @click.option(
        "--no-cache", is_flag=True, help="Bypass and do not write to result cache."
    )
    @click.option("--staged", is_flag=True, help="Scan only files staged in git index.")
    @click.option(
        "--changed", is_flag=True, help="Scan only modified uncommitted files."
    )
    @click.option(
        "--since", type=str, default=None, help="Scan files changed since git ref."
    )
    @click.option(
        "--workspace",
        "-w",
        "workspace_name",
        type=str,
        default=None,
        help="Scope execution to a specific monorepo workspace package.",
    )
    @click.option(
        "--all-workspaces",
        is_flag=True,
        help="Execute tool across all discovered monorepo workspaces.",
    )
    @permission_options
    @result_view_options
    @click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
    def command(
        path: Path,
        report_path: Path | None,
        export_sarif: Path | None,
        export_html: Path | None,
        no_cache: bool,
        result_view: str | None,
        limit: int | None,
        max_bytes: int | None,
        staged: bool,
        changed: bool,
        since: str | None,
        workspace_name: str | None,
        all_workspaces: bool,
        allow_network: bool,
        allow_download: bool,
        allow_cache_write: bool,
        allow_build: bool,
        allow_slow: bool,
        allow_artifact_write: bool,
        allow_browser: bool,
        as_json: bool,
        **tool_options: object,
    ) -> None:
        perms = _extract_permissions(
            allow_network=allow_network,
            allow_download=allow_download,
            allow_cache_write=allow_cache_write,
            allow_build=allow_build,
            allow_slow=allow_slow,
            allow_artifact_write=allow_artifact_write,
            allow_browser=allow_browser,
        )
        extra_kwargs: dict[str, object] = {
            name: value for name, value in tool_options.items() if value is not None
        }
        if report_path:
            extra_kwargs["report_path"] = report_path
        _run_catalog_command(
            tool.name,
            path,
            _Scope(workspace_name, all_workspaces, staged, changed, since),
            as_json=as_json,
            permissions=perms,
            export_sarif=export_sarif,
            export_html=export_html,
            extra_kwargs=extra_kwargs or None,
            view=compact.ViewOptions(result_view, limit, max_bytes, no_cache),
        )

    command.params.extend(_TOOL_CLI_OPTIONS.get(tool.name, ()))
    return command


# ---------------------------------------------------------------------------
# T25: navigable help (everyday set, category index, `rush help`, `--help-all`)
# ---------------------------------------------------------------------------

CLI_CATEGORY_OVERRIDES: dict[str, str] = {
    # quality
    "api-diff": "quality",
    "arch-guard": "quality",
    "audit": "quality",
    "blast-radius": "quality",
    "check": "quality",
    "codegraph": "quality",
    "consensus": "quality",
    "guard": "quality",
    "hotspots": "quality",
    "hygiene": "quality",
    "outline": "quality",
    "score": "quality",
    "simplify": "quality",
    "strictify": "quality",
    # security
    "hallu-guard": "security",
    "trust": "security",
    # test
    "simulate-ci": "test",
    "test-heal": "test",
    # workflow
    "bundle": "workflow",
    "conflict": "workflow",
    "db-drift": "workflow",
    "gate": "workflow",
    "patch": "workflow",
    "plan": "workflow",
    "scaffold": "workflow",
    "scan": "workflow",
    "ship": "workflow",
    "swarm-merge": "workflow",
    "sync": "workflow",
    "workspace": "workflow",
    "watch": "workflow",
    "lock": "workflow",
    # memory (a CLI grouping name distinct from the `memory` command, which
    # falls back to its own ToolSpec category)
    "context": "memory",
    "flight-recorder": "memory",
    "session": "memory",
    # services
    "dashboard": "services",
    "mcp": "services",
    "ui": "services",
    # administration
    "agent": "administration",
    "cache": "administration",
    "capabilities": "administration",
    "config": "administration",
    "gain": "administration",
    "governance": "administration",
    "help": "administration",
    "hook": "administration",
    "init": "administration",
    "install": "administration",
    "plugin": "administration",
    "project": "administration",
    "setup": "administration",
    "status": "administration",
    "token": "administration",
    "trace": "administration",
}

ALL_CATEGORIES = (
    "quality",
    "security",
    "test",
    "workflow",
    "memory",
    "services",
    "administration",
)

EVERYDAY_SET = (
    "status",
    "check",
    "lint",
    "review",
    "security",
    "test",
    "memory",
    "setup",
    "install",
    "agent",
    "mcp",
)


def command_category(name: str) -> str:
    """Resolve `name`'s help category: pinned override first, else its real
    ToolSpec category (an alias inherits whatever its own name resolves to,
    same as any other command -- no group-based guessing)."""
    override = CLI_CATEGORY_OVERRIDES.get(name)
    if override is not None:
        return override
    return TOOL_SPECS[name].category


def _live_names(group: click.Group, ctx: click.Context) -> list[str]:
    return sorted(set(group.list_commands(ctx)) | {"lock"})


def _members_of_category(names: list[str], category: str) -> list[str]:
    return sorted(name for name in names if command_category(name) == category)


def format_everyday_commands(
    group: click.Group, ctx: click.Context, formatter: click.HelpFormatter
) -> None:
    """Default `--help` body: the everyday set, then a category index
    (`rush help CATEGORY` for the rest) -- never the full flat command list.
    Each everyday row keeps its one-line description, truncated the way
    click.Group.format_commands does."""
    commands = [
        (name, cmd)
        for name in EVERYDAY_SET
        if (cmd := group.get_command(ctx, name)) is not None and not cmd.hidden
    ]
    limit = formatter.width - 6 - max((len(name) for name, _ in commands), default=0)
    rows: list[tuple[str, str]] = [
        (name, cmd.get_short_help_str(limit)) for name, cmd in commands
    ]
    if rows:
        with formatter.section("Commands"):
            formatter.write_dl(rows)

    live_names = _live_names(group, ctx)
    category_rows = [
        (
            category,
            (
                f"{len(_members_of_category(live_names, category))} commands "
                f"-- rush help {category}"
            ),
        )
        for category in ALL_CATEGORIES
    ]
    with formatter.section("Categories"):
        formatter.write_dl(category_rows)


def _echo_help_all(ctx: click.Context, _param: click.Parameter, value: bool) -> None:
    if not value or ctx.resilient_parsing:
        return
    for name in _live_names(cast("click.Group", ctx.command), ctx):
        click.echo(name)
    ctx.exit()


help_all_option = click.option(
    "--help-all",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=_echo_help_all,
    help="List every registered command name, not just the everyday set.",
)


def build_help_command(group: click.Group) -> click.Command:
    """`rush help` / `rush help CATEGORY`: the category index / membership,
    routed through the same override-or-ToolSpec resolution as the default
    `--help` view."""

    @click.command(name="help")
    @click.argument("category", required=False)
    @click.pass_context
    def help_cmd(ctx: click.Context, category: str | None) -> None:
        live_names = _live_names(group, ctx)
        if category is None:
            click.echo("Categories:")
            for cat in ALL_CATEGORIES:
                count = len(_members_of_category(live_names, cat))
                click.echo(f"  {cat} ({count}) -- rush help {cat}")
            return
        if category not in ALL_CATEGORIES:
            raise click.UsageError(
                f"Unknown category {category!r}. Valid categories: "
                f"{', '.join(ALL_CATEGORIES)}",
                ctx=ctx,
            )
        click.echo(f"{category}:")
        for name in _members_of_category(live_names, category):
            click.echo(f"  {name}")

    return help_cmd
