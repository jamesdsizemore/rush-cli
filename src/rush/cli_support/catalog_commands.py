"""CLI catalog command scaffolding."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import click

from rush.catalog import TOOL_SPECS
from rush.cli_support.options import _extract_permissions, permission_options
from rush.cli_support.rendering import (
    TargetPath,
    _run_tool,
    execute_cli_tool,
    exit_with_result,
)
from rush.invocation.executor import target_error_result
from rush.permissions import ExecutionPermissions
from rush.tools.base import ToolFn, ToolResult
from rush.tools.common import skipped_result
from rush.tools.routing import aggregate_results, no_target_scope

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
        "children": [
            {
                "workspace": name,
                "path": str(target),
                "tool": result.get("tool"),
                "status": result.get("status"),
                "summary": result.get("summary"),
            }
            for (name, target), result in zip(units, results, strict=True)
        ]
    }
    return aggregate


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
        )
        return
    run = {"extra_kwargs": extra_kwargs, "permissions": permissions}
    exit_with_result(
        _scoped_result(tool_name, path, scope, run),
        as_json=as_json,
        tool_name=tool_name,
        export_sarif=export_sarif,
        export_html=export_html,
    )


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
    @click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
    def command(
        path: Path,
        report_path: Path | None,
        export_sarif: Path | None,
        export_html: Path | None,
        no_cache: bool,
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
        _run_catalog_command(
            tool.name,
            path,
            _Scope(workspace_name, all_workspaces, staged, changed, since),
            as_json=as_json,
            permissions=perms,
            export_sarif=export_sarif,
            export_html=export_html,
            extra_kwargs={"report_path": report_path} if report_path else None,
        )

    return command
