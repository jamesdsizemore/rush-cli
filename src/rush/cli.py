"""Click CLI entrypoint — 34 canonical subcommands + `mcp serve`.

Architecture §6. Each subcommand calls the same ToolFn.__call__ that the
MCP tool calls (requirement C3 — single source of truth).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from . import __version__
from .catalog import TOOL_SPECS
from .config import RushConfigError, load_config
from .logging import setup_logging
from .permissions import ExecutionPermissions
from .theme import render_result
from .tools import ALL_TOOLS
from .tools.base import ToolFn


def _extract_permissions(
    allow_network: bool = False,
    allow_download: bool = False,
    allow_cache_write: bool = False,
    allow_build: bool = False,
    allow_slow: bool = False,
    allow_artifact_write: bool = False,
    allow_browser: bool = False,
) -> ExecutionPermissions:
    return ExecutionPermissions(
        network=allow_network,
        download=allow_download,
        cache_write=allow_cache_write,
        build=allow_build,
        slow=allow_slow,
        artifact_write=allow_artifact_write,
        browser=allow_browser,
    )


def permission_options(fn):
    """Add standard explicit execution permission flags to a Click command."""
    fn = click.option(
        "--allow-network",
        is_flag=True,
        help="Explicitly authorize external network access.",
    )(fn)
    fn = click.option(
        "--allow-download",
        is_flag=True,
        help="Explicitly authorize external downloads.",
    )(fn)
    fn = click.option(
        "--allow-cache-write",
        is_flag=True,
        help="Explicitly authorize local cache modification.",
    )(fn)
    fn = click.option(
        "--allow-build",
        is_flag=True,
        help="Explicitly authorize local build execution.",
    )(fn)
    fn = click.option(
        "--allow-slow",
        is_flag=True,
        help="Explicitly authorize long-running execution.",
    )(fn)
    fn = click.option(
        "--allow-artifact-write",
        is_flag=True,
        help="Explicitly authorize writing contained artifacts.",
    )(fn)
    fn = click.option(
        "--allow-browser",
        is_flag=True,
        help="Explicitly authorize browser runtime execution.",
    )(fn)
    return fn


def _run_tool(
    tool_name: str,
    path: Path,
    *,
    as_json: bool,
    extra_kwargs: dict | None = None,
    permissions: ExecutionPermissions | None = None,
    export_sarif: Path | None = None,
    export_html: Path | None = None,
) -> None:
    """Shared helper: find the tool, call it, render or JSON-print, exit."""
    tool = next((t for t in ALL_TOOLS if t.name == tool_name), None)
    if tool is None:
        click.echo(f"unknown tool: {tool_name}", err=True)
        sys.exit(2)
    try:
        config = load_config(start=path)
    except RushConfigError as e:
        click.echo(str(e), err=True)
        sys.exit(2)
    kwargs = dict(extra_kwargs or {})
    # Use the .run() entry point so the CLI can pass config and permissions
    # without leaking it into the MCP-exposed __call__ signature.
    try:
        result = tool.run(path, config=config, permissions=permissions, **kwargs)
    except TypeError:
        # Fallback if specific tool does not yet accept permissions
        result = tool.run(path, config=config, **kwargs)

    if export_sarif is not None:
        from .sarif import export_to_sarif

        sarif_doc = export_to_sarif(result, tool_name=tool_name)
        export_sarif.write_text(json.dumps(sarif_doc, indent=2), encoding="utf-8")

    if export_html is not None:
        from .html_export import export_to_html

        html_doc = export_to_html(result, title=f"Rush {tool_name} Report")
        export_html.write_text(html_doc, encoding="utf-8")

    if as_json:
        click.echo(json.dumps(result, indent=2, default=str))
    else:
        render_result(result)
    from .tools.common import exit_code_for

    sys.exit(exit_code_for(result))


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
        target_path = path
        if staged:
            from .discovery.git import get_staged_files

            staged_files = get_staged_files(path if path.is_dir() else path.parent)
            if not staged_files:
                click.echo("No staged files found to scan.")
                sys.exit(0)
        elif changed:
            from .discovery.git import get_changed_files

            changed_files = get_changed_files(path if path.is_dir() else path.parent)
            if not changed_files:
                click.echo("No changed files found to scan.")
                sys.exit(0)
        elif since:
            from .discovery.git import get_files_since

            since_files = get_files_since(path if path.is_dir() else path.parent, since)
            if not since_files:
                click.echo(f"No files changed since {since}.")
                sys.exit(0)

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


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "--version", "-V", message="%(version)s")
@click.option(
    "--log-level",
    envvar="RUSH_LOG_LEVEL",
    default="warn",
    type=click.Choice(["debug", "info", "warn", "error"], case_sensitive=False),
    help="Log verbosity (stderr NDJSON). Env: RUSH_LOG_LEVEL. Default: warn.",
)
def cli(log_level: str) -> None:
    """rush — agentic code-quality tools for coding agents.

    \b
    Five tools: review, lint, format, test, security.
    Pairs well with `npx @nanonets/graft` for context-graph queries.
    """
    setup_logging(log_level)


@cli.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--json", "as_json", is_flag=True, help="Print capability inventory JSON."
)
def capabilities(path: Path, as_json: bool) -> None:
    """Inspect local scan applicability without executing an engine."""
    from .capabilities import inspect_capabilities

    try:
        result = inspect_capabilities(path)
    except RushConfigError as error:
        raise click.UsageError(str(error)) from error
    if as_json:
        click.echo(json.dumps(result, indent=2, default=str))
    else:
        for name, capability in result["tools"].items():
            click.echo(f"{name}: {capability['state']} ({capability['reason']})")


@cli.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--profile", default="default", show_default=True)
@click.option("--json", "as_json", is_flag=True, help="Print deterministic plan JSON.")
def plan(path: Path, profile: str, as_json: bool) -> None:
    """Plan completed non-browser checks without executing them."""
    from .capabilities import build_plan

    try:
        result = build_plan(path, profile)
    except (RushConfigError, ValueError) as error:
        raise click.UsageError(str(error)) from error
    if as_json:
        click.echo(json.dumps(result, indent=2, default=str))
    else:
        for step in result["steps"]:
            click.echo(f"{step['tool']}: {step['state']} ({step['reason']})")


# --- Subcommands (one per tool) --------------------------------------------


@cli.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--llm",
    "use_llm",
    is_flag=True,
    help="Call configured LLM (ANTHROPIC_API_KEY or OPENAI_API_KEY).",
)
@click.option("--use-graft", is_flag=True, help="Add optional local Graft context.")
@click.option(
    "--changed-file",
    "changed_files",
    multiple=True,
    help="Restrict review to an explicit target-relative file; repeat as needed.",
)
@permission_options
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def review(
    path: Path,
    use_llm: bool,
    use_graft: bool,
    changed_files: tuple[str, ...],
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
    as_json: bool,
) -> None:
    """Review code for deterministic heuristics. Maturity: real adapter."""
    perms = _extract_permissions(
        allow_network=allow_network,
        allow_download=allow_download,
        allow_cache_write=allow_cache_write,
        allow_build=allow_build,
        allow_slow=allow_slow,
        allow_artifact_write=allow_artifact_write,
        allow_browser=allow_browser,
    )
    _run_tool(
        "review",
        path,
        as_json=as_json,
        permissions=perms,
        extra_kwargs={
            "use_llm": use_llm,
            "use_graft": use_graft,
            "changed_files": list(changed_files) or None,
        },
    )


@cli.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--check", "check_only", is_flag=True, help="Only check; don't modify files."
)
@permission_options
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def format(
    path: Path,
    check_only: bool,
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
    as_json: bool,
) -> None:
    """Format Python and JS/TS safely. Maturity: real adapter."""
    perms = _extract_permissions(
        allow_network=allow_network,
        allow_download=allow_download,
        allow_cache_write=allow_cache_write,
        allow_build=allow_build,
        allow_slow=allow_slow,
        allow_artifact_write=allow_artifact_write,
        allow_browser=allow_browser,
    )
    _run_tool(
        "format",
        path,
        as_json=as_json,
        permissions=perms,
        extra_kwargs={"check": check_only} if check_only else None,
    )


@cli.command(name="commit-msg")
@click.argument(
    "path",
    type=click.Path(exists=True, path_type=Path),
    default=Path("."),
    required=False,
)
@click.option(
    "--message", "-m", "message", default="", help="Commit message to validate."
)
@permission_options
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def commit_msg_cmd(
    path: Path,
    message: str,
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
    as_json: bool,
) -> None:
    """Validate commit messages without rewriting history. Maturity: real adapter."""
    perms = _extract_permissions(
        allow_network=allow_network,
        allow_download=allow_download,
        allow_cache_write=allow_cache_write,
        allow_build=allow_build,
        allow_slow=allow_slow,
        allow_artifact_write=allow_artifact_write,
        allow_browser=allow_browser,
    )
    _run_tool(
        "commit-msg",
        path,
        as_json=as_json,
        permissions=perms,
        extra_kwargs={"message": message} if message else None,
    )


@cli.command(name="sbom")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output",
    "-o",
    "output_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Explicit output path for the generated SBOM artifact.",
)
@click.option(
    "--overwrite",
    is_flag=True,
    help="Explicitly permit overwriting an existing SBOM file.",
)
@permission_options
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def sbom_cmd(
    path: Path,
    output_path: Path | None,
    overwrite: bool,
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
    as_json: bool,
) -> None:
    """Generate a safe SBOM artifact. Maturity: real adapter."""
    perms = _extract_permissions(
        allow_network=allow_network,
        allow_download=allow_download,
        allow_cache_write=allow_cache_write,
        allow_build=allow_build,
        allow_slow=allow_slow,
        allow_artifact_write=allow_artifact_write,
        allow_browser=allow_browser,
    )
    _run_tool(
        "sbom",
        path,
        as_json=as_json,
        permissions=perms,
        extra_kwargs={
            "output_path": output_path,
            "overwrite": overwrite,
        },
    )


# --- MCP server subcommand -------------------------------------------------


@cli.group()
def mcp() -> None:
    """MCP server commands (stdio transport)."""


@mcp.command()
def serve() -> None:
    """Start the rush MCP server on stdio (for coding agents)."""
    import asyncio

    from .mcp import run_stdio

    asyncio.run(run_stdio())


# --- Cache CLI commands ---------------------------------------------------


@cli.group()
def cache() -> None:
    """Manage Rush result cache."""


@cache.command(name="stats")
def cache_stats() -> None:
    """Display cache entry count, file size, and location."""
    from .cache import ResultCache

    c = ResultCache()
    stats_data = c.stats()
    click.echo(json.dumps(stats_data, indent=2))


@cache.command(name="clean")
def cache_clean() -> None:
    """Purge all cached results from .rush/cache.db."""
    from .cache import ResultCache

    c = ResultCache()
    count = c.clear()
    click.echo(f"Purged {count} cached result(s).")


for _catalog_tool in ALL_TOOLS:
    if _catalog_tool.name not in {"review", "format", "commit-msg", "sbom"}:
        cli.add_command(build_catalog_path_command(_catalog_tool))


if __name__ == "__main__":
    cli()
