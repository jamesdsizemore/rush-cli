"""CLI catalog command scaffolding."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from rush.catalog import TOOL_SPECS
from rush.cli_support.options import _extract_permissions, permission_options
from rush.cli_support.rendering import _run_tool
from rush.tools.base import ToolFn


def _resolve_target_path(
    path: Path,
    workspace_name: str | None,
    staged: bool,
    changed: bool,
    since: str | None,
) -> Path:
    target_path = path

    if workspace_name:
        from rush.discovery.workspace import discover_workspaces

        ws_pkgs = discover_workspaces(path if path.is_dir() else path.parent)
        matched = next((w for w in ws_pkgs if w.name == workspace_name), None)
        if not matched:
            click.echo(f"Workspace package '{workspace_name}' not found.", err=True)
            sys.exit(1)
        target_path = matched.path

    if staged:
        from rush.discovery.git import get_staged_files

        staged_files = get_staged_files(
            target_path if target_path.is_dir() else target_path.parent
        )
        if not staged_files:
            click.echo("No staged files found to scan.")
            sys.exit(0)
    elif changed:
        from rush.discovery.git import get_changed_files

        changed_files = get_changed_files(
            target_path if target_path.is_dir() else target_path.parent
        )
        if not changed_files:
            click.echo("No changed files found to scan.")
            sys.exit(0)
    elif since:
        from rush.discovery.git import get_files_since

        since_files = get_files_since(
            target_path if target_path.is_dir() else target_path.parent, since
        )
        if not since_files:
            click.echo(f"No files changed since {since}.")
            sys.exit(0)

    return target_path


def build_catalog_path_command(tool: ToolFn) -> click.Command:
    """Build the standard ``PATH --json`` CLI surface for a catalog tool."""

    @click.command(
        name=tool.name,
        help=(
            f"{tool.mcp_description} Maturity: "
            f"{TOOL_SPECS[tool.name].maturity.replace('_', ' ')}."
        ),
    )
    @click.argument("path", type=click.Path(exists=True, path_type=Path))
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
        target_path = _resolve_target_path(
            path=path,
            workspace_name=workspace_name,
            staged=staged,
            changed=changed,
            since=since,
        )

        _run_tool(
            tool.name,
            target_path,
            as_json=as_json,
            permissions=perms,
            export_sarif=export_sarif,
            export_html=export_html,
            extra_kwargs={"report_path": report_path} if report_path else None,
        )

    return command
