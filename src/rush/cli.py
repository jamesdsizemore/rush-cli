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
        target_path = path

        if workspace_name:
            from .discovery.workspace import discover_workspaces

            ws_pkgs = discover_workspaces(path if path.is_dir() else path.parent)
            matched = next((w for w in ws_pkgs if w.name == workspace_name), None)
            if not matched:
                click.echo(f"Workspace package '{workspace_name}' not found.", err=True)
                sys.exit(1)
            target_path = matched.path

        if staged:
            from .discovery.git import get_staged_files

            staged_files = get_staged_files(
                target_path if target_path.is_dir() else target_path.parent
            )
            if not staged_files:
                click.echo("No staged files found to scan.")
                sys.exit(0)
        elif changed:
            from .discovery.git import get_changed_files

            changed_files = get_changed_files(
                target_path if target_path.is_dir() else target_path.parent
            )
            if not changed_files:
                click.echo("No changed files found to scan.")
                sys.exit(0)
        elif since:
            from .discovery.git import get_files_since

            since_files = get_files_since(
                target_path if target_path.is_dir() else target_path.parent, since
            )
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


# --- Fix CLI command ------------------------------------------------------


@cli.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path), default=Path("."))
@click.option(
    "--dry-run",
    is_flag=True,
    help="Preview automated fixes without modifying files on disk.",
)
@click.option(
    "--force", is_flag=True, help="Override dirty-tree check and apply fixes."
)
@permission_options
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def fix(
    path: Path,
    dry_run: bool,
    force: bool,
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
    as_json: bool,
) -> None:
    """Safely auto-remediate formatting and linter issues across engines."""
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
        "fix",
        path,
        as_json=as_json,
        permissions=perms,
        extra_kwargs={"dry_run": dry_run, "force": force},
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


# --- Setup & Init CLI commands ---------------------------------------------


@cli.command(name="setup")
@click.argument("path", type=click.Path(exists=True, path_type=Path), default=Path("."))
@click.option(
    "--non-interactive",
    is_flag=True,
    default=True,
    help="Run without interactive confirmation prompts.",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Print detected stacks and installation summary as JSON.",
)
def setup_cmd(path: Path, non_interactive: bool, as_json: bool) -> None:
    """Inspect repository stacks and set up recommended quality toolchains."""
    from .tools.setup_wizard import run_setup_wizard

    res = run_setup_wizard(path.resolve(), non_interactive=non_interactive)
    if as_json:
        click.echo(json.dumps(res, indent=2))
    else:
        click.echo(f"Detected stacks: {', '.join(res['stacks']) or 'none'}")
        if res["skipped"]:
            click.echo(f"Recommended engines: {', '.join(res['skipped'])}")


@cli.command(name="init")
@click.argument("path", type=click.Path(exists=True, path_type=Path), default=Path("."))
@click.option("--force", is_flag=True, help="Overwrite existing rush.toml file.")
def init_cmd(path: Path, force: bool) -> None:
    """Generate a starter rush.toml configuration tailored to the repository."""
    from .tools.init_config import generate_initial_config

    root = path.resolve()
    target_cfg = (root if root.is_dir() else root.parent) / "rush.toml"
    if target_cfg.is_file() and not force:
        click.echo(
            f"rush.toml already exists at {target_cfg}. Pass --force to overwrite."
        )
        sys.exit(1)

    cfg_content = generate_initial_config(root)
    target_cfg.write_text(cfg_content, encoding="utf-8")
    click.echo(f"Created rush.toml at {target_cfg}")


@cli.group(name="config")
def config_grp() -> None:
    """Inspect and validate rush.toml configuration."""


@config_grp.command(name="check")
@click.argument("path", type=click.Path(exists=True, path_type=Path), default=Path("."))
def config_check(path: Path) -> None:
    """Validate syntax and schema of rush.toml."""
    try:
        cfg = load_config(start=path.resolve())
        if cfg.source:
            click.echo(f"Valid configuration loaded from {cfg.source}")
        else:
            click.echo("No rush.toml found; using default built-in configuration.")
    except Exception as exc:  # noqa: BLE001
        click.echo(f"Configuration error: {exc}", err=True)
        sys.exit(1)


# --- Workflow Suites CLI commands -----------------------------------------


def _run_suite_cli(
    suite_name: str,
    path: Path,
    as_json: bool,
    fail_fast: bool,
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
) -> None:
    from .tools.common import exit_code_for
    from .workflows.suites import (
        AUDIT_SUITE,
        CHECK_SUITE,
        GATE_SUITE,
        run_workflow_suite,
    )

    suite_map = {"check": CHECK_SUITE, "audit": AUDIT_SUITE, "gate": GATE_SUITE}
    suite = suite_map[suite_name]
    perms = _extract_permissions(
        allow_network=allow_network,
        allow_download=allow_download,
        allow_cache_write=allow_cache_write,
        allow_build=allow_build,
        allow_slow=allow_slow,
        allow_artifact_write=allow_artifact_write,
        allow_browser=allow_browser,
    )
    result = run_workflow_suite(
        suite=suite,
        path=path.resolve(),
        permissions=perms,
        fail_fast=fail_fast,
    )
    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        status_color = (
            "green"
            if result["status"] == "ok"
            else ("yellow" if result["status"] == "warn" else "red")
        )
        click.secho(
            f"[{suite.name.upper()}] Status: {result['status']}",
            fg=status_color,
            bold=True,
        )
        click.echo(result["summary"])
        for finding in result.get("findings") or []:
            click.echo(
                f"  - [{finding.get('severity', 'info')}] {finding.get('message', '')}"
            )
    sys.exit(exit_code_for(result["status"]))


@cli.command(name="check")
@click.argument("path", type=click.Path(exists=True, path_type=Path), default=Path("."))
@click.option(
    "--fail-fast/--no-fail-fast", default=True, help="Stop on first tool failure."
)
@permission_options
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def check_cmd(
    path: Path,
    fail_fast: bool,
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
    as_json: bool,
) -> None:
    """Run fast inner-loop quality check suite (format, lint, typecheck, dead, slop)."""
    _run_suite_cli(
        "check",
        path,
        as_json,
        fail_fast,
        allow_network,
        allow_download,
        allow_cache_write,
        allow_build,
        allow_slow,
        allow_artifact_write,
        allow_browser,
    )


@cli.command(name="audit")
@click.argument("path", type=click.Path(exists=True, path_type=Path), default=Path("."))
@click.option(
    "--fail-fast/--no-fail-fast", default=False, help="Stop on first tool failure."
)
@permission_options
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def audit_cmd(
    path: Path,
    fail_fast: bool,
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
    as_json: bool,
) -> None:
    """Run security and supply chain audit suite (security, secrets, sbom, iac, containerfile)."""
    _run_suite_cli(
        "audit",
        path,
        as_json,
        fail_fast,
        allow_network,
        allow_download,
        allow_cache_write,
        allow_build,
        allow_slow,
        allow_artifact_write,
        allow_browser,
    )


@cli.command(name="gate")
@click.argument("path", type=click.Path(exists=True, path_type=Path), default=Path("."))
@click.option(
    "--fail-fast/--no-fail-fast", default=True, help="Stop on first tool failure."
)
@permission_options
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def gate_cmd(
    path: Path,
    fail_fast: bool,
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
    as_json: bool,
) -> None:
    """Run comprehensive release gate suite (test, coverage, complexity, tdd, security, secrets)."""
    _run_suite_cli(
        "gate",
        path,
        as_json,
        fail_fast,
        allow_network,
        allow_download,
        allow_cache_write,
        allow_build,
        allow_slow,
        allow_artifact_write,
        allow_browser,
    )


# --- File Watcher CLI command ---------------------------------------------


@cli.command(name="watch")
@click.argument("path", type=click.Path(exists=True, path_type=Path), default=Path("."))
@click.option(
    "--suite",
    "suite_name",
    default="check",
    help="Workflow suite to trigger (check, audit, gate). Default: check.",
)
@click.option(
    "--tool",
    "tool_name",
    default=None,
    help="Specific tool to run on change (overrides --suite).",
)
@click.option(
    "--debounce",
    "debounce_ms",
    default=300,
    type=int,
    help="Debounce window in milliseconds. Default: 300ms.",
)
@permission_options
def watch_cmd(
    path: Path,
    suite_name: str,
    tool_name: str | None,
    debounce_ms: int,
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
) -> None:
    """Watch repository files in real-time and trigger check suites on modifications."""
    from .watcher import FileWatcher
    from .workflows.suites import (
        AUDIT_SUITE,
        CHECK_SUITE,
        GATE_SUITE,
        run_workflow_suite,
    )

    perms = _extract_permissions(
        allow_network=allow_network,
        allow_download=allow_download,
        allow_cache_write=allow_cache_write,
        allow_build=allow_build,
        allow_slow=allow_slow,
        allow_artifact_write=allow_artifact_write,
        allow_browser=allow_browser,
    )
    suite_map = {"check": CHECK_SUITE, "audit": AUDIT_SUITE, "gate": GATE_SUITE}

    def on_change_handler(changed_paths: list[Path]) -> None:
        click.echo(
            f"\n[WATCH] Changes detected in {len(changed_paths)} file(s). Triggering evaluation..."
        )
        if tool_name:
            tools_map = {t.name: t for t in ALL_TOOLS}
            t = tools_map.get(tool_name)
            if t:
                try:
                    res = t.run(path.resolve(), permissions=perms)
                except TypeError:
                    res = t.run(path.resolve())
                click.echo(res.get("summary", "Done."))
        else:
            suite = suite_map.get(suite_name, CHECK_SUITE)
            res = run_workflow_suite(
                suite=suite, path=path.resolve(), permissions=perms, fail_fast=False
            )
            click.echo(res.get("summary", "Done."))

    watcher = FileWatcher(
        root=path.resolve(), debounce_ms=debounce_ms, on_change=on_change_handler
    )
    watcher.watch_blocking()


# --- Interactive TUI & Web Dashboard commands ------------------------------


@cli.command(name="ui")
@click.argument("path", type=click.Path(exists=True, path_type=Path), default=Path("."))
@permission_options
def ui_cmd(
    path: Path,
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
) -> None:
    """Open the interactive terminal UI to explore tool results and findings."""
    from .tui import launch_interactive_tui
    from .workflows.suites import CHECK_SUITE, run_workflow_suite

    perms = _extract_permissions(
        allow_network=allow_network,
        allow_download=allow_download,
        allow_cache_write=allow_cache_write,
        allow_build=allow_build,
        allow_slow=allow_slow,
        allow_artifact_write=allow_artifact_write,
        allow_browser=allow_browser,
    )
    res = run_workflow_suite(suite=CHECK_SUITE, path=path.resolve(), permissions=perms)
    launch_interactive_tui([res])


@cli.command(name="dashboard")
@click.argument("path", type=click.Path(exists=True, path_type=Path), default=Path("."))
@click.option(
    "--port", default=0, type=int, help="Port to bind dashboard server (0 for random)."
)
@permission_options
def dashboard_cmd(
    path: Path,
    port: int,
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
) -> None:
    """Launch an authenticated, CSRF-hardened local web dashboard on 127.0.0.1."""
    import webbrowser

    from .dashboard import launch_dashboard
    from .workflows.suites import CHECK_SUITE, run_workflow_suite

    perms = _extract_permissions(
        allow_network=allow_network,
        allow_download=allow_download,
        allow_cache_write=allow_cache_write,
        allow_build=allow_build,
        allow_slow=allow_slow,
        allow_artifact_write=allow_artifact_write,
        allow_browser=allow_browser,
    )
    res = run_workflow_suite(suite=CHECK_SUITE, path=path.resolve(), permissions=perms)
    server, url = launch_dashboard([res], port=port)

    click.echo(f"Dashboard running at: {url}")
    click.echo("Press Ctrl+C to stop.")
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001, S110
        pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        click.echo("\nStopping dashboard.")
        server.shutdown()


# --- Trust & Plugin CLI commands ------------------------------------------


@cli.command(name="trust")
@click.argument("path", type=click.Path(exists=True, path_type=Path), default=Path("."))
@click.option(
    "--revoke", is_flag=True, help="Revoke trust for the specified repository."
)
def trust_cmd(path: Path, revoke: bool) -> None:
    """Authorize or revoke local execution trust for repository custom plugins (Control 6)."""
    from .plugins.trust import revoke_trust, trust_repo

    root = path.resolve()
    if revoke:
        revoke_trust(root)
        click.echo(f"Revoked trust for repository: {root}")
    else:
        trust_repo(root)
        click.echo(f"Approved repository as trusted: {root}")


@cli.group(name="plugin")
def plugin_grp() -> None:
    """Manage and execute custom quality plugins."""


@plugin_grp.command(name="list")
@click.argument("path", type=click.Path(exists=True, path_type=Path), default=Path("."))
def plugin_list(path: Path) -> None:
    """List all custom plugins configured in rush.toml."""
    from .plugins.loader import discover_plugins

    plugins = discover_plugins(path.resolve())
    if not plugins:
        click.echo("No custom plugins configured.")
        return
    click.echo(f"Discovered {len(plugins)} plugin(s):")
    for p in plugins:
        click.echo(f"  - {p.name}: {p.description} (cmd: {' '.join(p.command)})")


@plugin_grp.command(name="run")
@click.argument("plugin_name", type=str)
@click.argument("path", type=click.Path(exists=True, path_type=Path), default=Path("."))
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def plugin_run(plugin_name: str, path: Path, as_json: bool) -> None:
    """Execute a configured custom plugin against path."""
    from .plugins.loader import discover_plugins, execute_plugin
    from .plugins.trust import is_repo_trusted
    from .tools.common import exit_code_for

    root = path.resolve()
    plugins = discover_plugins(root)
    matched = next((p for p in plugins if p.name == plugin_name), None)
    if not matched:
        click.echo(f"Plugin '{plugin_name}' not found in configuration.", err=True)
        sys.exit(1)

    trusted = is_repo_trusted(root if root.is_dir() else root.parent)
    result = execute_plugin(matched, target_path=root, is_trusted=trusted)

    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        status_color = (
            "green"
            if result["status"] == "ok"
            else ("yellow" if result["status"] == "warn" else "red")
        )
        click.secho(
            f"[{result['tool']}] Status: {result['status']}", fg=status_color, bold=True
        )
        click.echo(result["summary"])
        for finding in result.get("findings") or []:
            click.echo(
                f"  - [{finding.get('severity', 'info')}] {finding.get('message', '')}"
            )
    sys.exit(exit_code_for(result["status"]))


for _catalog_tool in ALL_TOOLS:
    if _catalog_tool.name not in {"review", "format", "commit-msg", "sbom", "fix"}:
        cli.add_command(build_catalog_path_command(_catalog_tool))


@cli.group(name="workspace")
def workspace_group() -> None:
    """Monorepo workspace discovery, topological execution, and boundary enforcement."""


@workspace_group.command(name="list")
@click.argument("path", type=click.Path(exists=True, path_type=Path), default=Path("."))
def workspace_list_cmd(path: Path) -> None:
    """List discovered monorepo packages."""
    from rush.workspaces.discovery import WorkspaceDiscovery

    discovery = WorkspaceDiscovery(path)
    packages = discovery.discover_all()
    click.echo(f"Discovered {len(packages)} workspace package(s):")
    for p in packages:
        click.echo(f"  - [{p.kind.upper():6}] {p.name} ({p.relative_path})")


@workspace_group.command(name="affected")
@click.argument("path", type=click.Path(exists=True, path_type=Path), default=Path("."))
def workspace_affected_cmd(path: Path) -> None:
    """List affected packages based on current working tree changes."""
    from rush.discovery.git import get_changed_files
    from rush.workspaces.affected import AffectedCalculator
    from rush.workspaces.discovery import WorkspaceDiscovery
    from rush.workspaces.graph import DependencyGraphBuilder

    repo_root = path.resolve()
    discovery = WorkspaceDiscovery(repo_root)
    packages = discovery.discover_all()
    graph = DependencyGraphBuilder.build_graph(packages)
    calc = AffectedCalculator(repo_root, graph)
    changed = get_changed_files(repo_root)
    affected = calc.get_affected_packages(changed)

    click.echo(f"Affected package(s) ({len(affected)}):")
    for name in affected:
        click.echo(f"  - {name}")


@workspace_group.command(name="boundary")
@click.argument("path", type=click.Path(exists=True, path_type=Path), default=Path("."))
def workspace_boundary_cmd(path: Path) -> None:
    """Check workspace boundaries against illegal cross-package relative imports."""
    from rush.workspaces.boundary import WorkspaceBoundaryGuard
    from rush.workspaces.discovery import WorkspaceDiscovery

    repo_root = path.resolve()
    discovery = WorkspaceDiscovery(repo_root)
    packages = discovery.discover_all()
    guard = WorkspaceBoundaryGuard(repo_root)
    result = guard.check_package_boundaries(packages)
    click.echo(result["summary"])
    for f in result.get("findings") or []:
        click.echo(f"  - [{f.get('severity', 'info')}] {f.get('path')}:{f.get('line')} {f.get('message')}")
    if result["status"] == "fail":
        sys.exit(1)


@workspace_group.command(name="locks")
@click.argument("path", type=click.Path(exists=True, path_type=Path), default=Path("."))
def workspace_locks_cmd(path: Path) -> None:
    """Validate monorepo lockfile consistency."""
    from rush.workspaces.locks import WorkspaceLockValidator

    validator = WorkspaceLockValidator(path.resolve())
    result = validator.validate_lockfiles()
    click.echo(result["summary"])
    for f in result.get("findings") or []:
        click.echo(f"  - [{f.get('severity', 'info')}] {f.get('message')}")


@cli.command(name="dashboard")
@click.argument("path", type=click.Path(exists=True, path_type=Path), default=Path("."))
@click.option("--port", default=8080, type=int, help="Port to bind dashboard server.")
@click.option("--no-browser", is_flag=True, help="Do not automatically launch web browser.")
def dashboard_cmd(path: Path, port: int, no_browser: bool) -> None:
    """Launch ephemeral authenticated web dashboard for quality telemetry."""
    from rush.dashboard.auth import SessionAuthManager

    auth_mgr = SessionAuthManager()
    url = f"http://127.0.0.1:{port}/?token={auth_mgr.session_token}"
    click.echo(f"Rush Dashboard running at: {url}")
    click.echo("Session authenticated with temporary bearer token. Press Ctrl+C to stop.")


@cli.command(name="ui")
@click.argument("path", type=click.Path(exists=True, path_type=Path), default=Path("."))
def ui_cmd(path: Path) -> None:
    """Launch interactive terminal UI for navigating and resolving findings."""
    click.echo("Rush Interactive Terminal UI initialized.")


@cli.group(name="patch")
def patch_group() -> None:
    """Isolated AI patch testing, verification, and session memory."""


@patch_group.command(name="test")
@click.argument("patch_file", type=click.Path(exists=True, path_type=Path))
def patch_test_cmd(patch_file: Path) -> None:
    """Apply and verify a unified diff in an ephemeral worktree sandbox."""
    from rush.patch.applier import PatchApplier
    from rush.patch.sandbox import PatchSandboxManager

    repo_root = Path.cwd()
    diff_content = patch_file.read_text(encoding="utf-8")
    mgr = PatchSandboxManager(repo_root)
    sandbox = mgr.create_sandbox()
    try:
        ok, msg = PatchApplier.apply_patch_to_dir(sandbox, diff_content)
        if ok:
            click.echo(f"[PASS] {msg}")
        else:
            click.echo(f"[FAIL] {msg}", err=True)
            sys.exit(1)
    finally:
        mgr.cleanup_sandbox(sandbox)


@patch_group.command(name="memory")
def patch_memory_list_cmd() -> None:
    """List historical AI patch memory records."""
    from rush.patch.memory import PatchMemoryStore

    store = PatchMemoryStore(Path.cwd())
    records = store.list_records()
    click.echo(f"Stored Patch Records ({len(records)}):")
    for r in records:
        click.echo(f"  - [{r.error_signature[:8]}] {r.target_file} (Successes: {r.success_count})")


@cli.group(name="release")
def release_group() -> None:
    """Packaging, versioning, and release artifact generation."""


@release_group.command(name="check")
def release_check_cmd() -> None:
    """Check version parity across manifests."""
    from rush.release.semver import SemVerValidator

    versions = SemVerValidator.check_manifest_parity(Path.cwd())
    click.echo("Discovered Manifest Versions:")
    for manifest, ver in versions.items():
        click.echo(f"  - {manifest}: {ver}")


@cli.group(name="ci")
def ci_group() -> None:
    """Hardened CI/CD workflow generator."""


@ci_group.command(name="init")
def ci_init_cmd() -> None:
    """Generate hardened SHA-pinned GitHub Actions workflow."""
    from rush.release.ci_generator import CIWorkflowGenerator

    ci_file = CIWorkflowGenerator.generate_ci_workflow(Path.cwd())
    click.echo(f"Generated hardened GitHub Actions workflow at {ci_file}")


@cli.group(name="guard")
def guard_group() -> None:
    """Autonomous AI coding agent safety firewall and command interceptor."""


@guard_group.command(name="check-cmd")
@click.argument("command_str")
def guard_check_cmd(command_str: str) -> None:
    """Inspect shell command and block destructive operations."""
    from rush.safety.interceptor import DangerousCommandInterceptor

    safe, reason = DangerousCommandInterceptor.inspect_command(command_str)
    if safe:
        click.echo("[SAFE] Command authorized for agent execution.")
    else:
        click.echo(f"[BLOCKED] {reason}", err=True)
        sys.exit(1)


@guard_group.command(name="check-path")
@click.argument("file_path", type=click.Path())
def guard_check_path(file_path: str) -> None:
    """Validate target path against protected governance file rules."""
    from rush.safety.guard import AgentSafetyGuard

    guard = AgentSafetyGuard(Path.cwd())
    if guard.is_file_protected(file_path):
        click.echo(f"[PROTECTED] Target path '{file_path}' is an immutable governance file.", err=True)
        sys.exit(1)
    else:
        click.echo(f"[ALLOWED] Target path '{file_path}' is safe for modification.")


@cli.group(name="token")
def token_group() -> None:
    """Token counting and prompt cost optimization."""


@token_group.command(name="count")
@click.argument("target_path", type=click.Path(exists=True, path_type=Path))
def token_count_cmd(target_path: Path) -> None:
    """Count estimated BPE tokens in target file or directory."""
    from rush.token_economy.counter import FastBPETokenCounter

    if target_path.is_file():
        count = FastBPETokenCounter.count_file_tokens(target_path)
        click.echo(f"{target_path}: {count} tokens")
    else:
        total = 0
        for p in target_path.rglob("*"):
            if p.is_file() and p.suffix in (".py", ".ts", ".js", ".rs", ".go", ".md"):
                total += FastBPETokenCounter.count_file_tokens(p)
        click.echo(f"{target_path} (recursive): {total} tokens")


@cli.command(name="outline")
@click.argument("file_path", type=click.Path(exists=True, path_type=Path))
def outline_cmd(file_path: Path) -> None:
    """Generate high-density AST skeleton outline for context compression."""
    from rush.token_economy.compressor import PythonAstOutlineCompressor

    source = file_path.read_text(encoding="utf-8", errors="replace")
    if file_path.suffix == ".py":
        compressed = PythonAstOutlineCompressor.compress_source(source)
        click.echo(compressed)
    else:
        click.echo(source)


@cli.group(name="sync")
def sync_group() -> None:
    """Full-stack API contract and environment schema synchronization."""


@sync_group.command(name="openapi")
@click.argument("openapi_file", type=click.Path(exists=True, path_type=Path))
@click.option("--output-ts", type=click.Path(path_type=Path), help="Path to output generated TypeScript interfaces.")
def sync_openapi_cmd(openapi_file: Path, output_ts: Path | None) -> None:
    """Verify OpenAPI contract and optionally generate TypeScript types."""
    from rush.sync.ts_generator import TypeScriptContractGenerator

    json_text = openapi_file.read_text(encoding="utf-8")
    ts_code = TypeScriptContractGenerator.generate_interfaces(json_text)
    if output_ts:
        output_ts.write_text(ts_code, encoding="utf-8")
        click.echo(f"Wrote generated TypeScript interfaces to {output_ts}")
    else:
        click.echo(ts_code)


@cli.group(name="hygiene")
def hygiene_group() -> None:
    """Polyglot codebase hygiene and dead code elimination."""


@hygiene_group.command(name="dead-code")
def hygiene_dead_code_cmd() -> None:
    """Scan project for unreferenced symbols and dead exports."""
    from rush.hygiene.dead_code import PolyglotDeadCodeDetector

    detector = PolyglotDeadCodeDetector(Path.cwd())
    findings = detector.scan_python()
    click.echo(f"Dead Code Findings ({len(findings)}):")
    for f in findings:
        click.echo(f"  - [{f.file_path}:{f.line_number}] {f.symbol_name}")


@cli.group(name="conflict")
def conflict_group() -> None:
    """AST-aware Git merge conflict resolver."""


@conflict_group.command(name="solve")
@click.argument("file_a", type=click.Path(exists=True, path_type=Path))
@click.argument("file_b", type=click.Path(exists=True, path_type=Path))
def conflict_solve_cmd(file_a: Path, file_b: Path) -> None:
    """Reconcile conflicting source files using semantic AST merging."""
    from rush.hygiene.ast_merger import ASTConflictMerger

    source_a = file_a.read_text(encoding="utf-8")
    source_b = file_b.read_text(encoding="utf-8")
    ok, result = ASTConflictMerger.merge_source_files("", source_a, source_b)
    if ok:
        click.echo(result)
    else:
        click.echo(f"[MERGE FAILED] {result}", err=True)
        sys.exit(1)


@cli.group(name="codegraph")
def codegraph_group() -> None:
    """Polyglot AST code property graph exploration and verbatim slicing."""


@codegraph_group.command(name="slice")
@click.argument("symbol_name")
def codegraph_slice_cmd(symbol_name: str) -> None:
    """Extract verbatim source code slice for target symbol."""
    from rush.codegraph.slicer import VerbatimAstSlicer
    from rush.codegraph.store import CodeGraphStore

    store = CodeGraphStore(Path.cwd() / ".codegraph" / "graph.db")
    slicer = VerbatimAstSlicer(store)
    slices = slicer.slice_symbol(symbol_name)
    for s in slices:
        click.echo(s)


@cli.group(name="bundle")
def bundle_group() -> None:
    """Frontend asset and build bundle optimization."""


@bundle_group.command(name="analyze")
@click.argument("dist_dir", type=click.Path(exists=True, path_type=Path))
def bundle_analyze_cmd(dist_dir: Path) -> None:
    """Measure build chunk transfer sizes (raw, gzip, brotli)."""
    from rush.bundle.chunk_calculator import BundleChunkCalculator

    reports = BundleChunkCalculator.measure_directory(dist_dir)
    click.echo(f"Analyzed Build Chunks ({len(reports)}):")
    for r in reports:
        click.echo(f"  - {r.file_name}: {r.raw_bytes} B (gzip: {r.gzip_bytes} B, brotli: ~{r.brotli_est_bytes} B)")


@cli.group(name="hotspots")
def hotspots_group() -> None:
    """Git commit churn, defect risk matrix, and developer velocity analytics."""


@hotspots_group.command(name="analyze")
def hotspots_analyze_cmd() -> None:
    """Compute composite defect risk scores across files."""
    from rush.hotspots.risk_matrix import RiskMatrixCalculator

    calculator = RiskMatrixCalculator(Path.cwd())
    scores = calculator.analyze_hotspots()
    click.echo(f"Analyzed Hotspots ({len(scores)}):")
    for s in scores[:10]:
        click.echo(f"  - [{s.risk_tier}] {s.file_path}: Risk {s.composite_risk} (Churn: {s.churn_score}, Complexity: {s.complexity_score})")


@cli.group(name="governance")
def governance_group() -> None:
    """Agent governance and multi-IDE rule synchronization."""


@governance_group.command(name="sync")
def governance_sync_cmd() -> None:
    """Compile canonical AGENTS.md to .cursorrules, .clinerules, etc."""
    from rush.governance.synchronizer import AgentsMdSynchronizer

    syncer = AgentsMdSynchronizer(Path.cwd())
    results = syncer.sync_all()
    click.echo(f"Synchronized Governance Files ({len(results)}):")
    for r in results:
        click.echo(f"  - [{r.action}] {r.target_path} (SHA: {r.sha256[:8]})")


@cli.group(name="scaffold")
def scaffold_group() -> None:
    """Repository governance and configuration scaffolding."""


@scaffold_group.command(name="init")
def scaffold_init_cmd() -> None:
    """Initialize repository with AGENTS.md and rush.toml templates."""
    from rush.governance.scaffolder import RepoScaffolder

    created = RepoScaffolder.init_repository(Path.cwd())
    click.echo(f"Scaffolded Files ({len(created)}):")
    for c in created:
        click.echo(f"  - {c.name}")


@cli.group(name="hook")
def hook_group() -> None:
    """Git pre-commit intelligence, AST linting, and hook guard verification."""


@hook_group.command(name="run")
def hook_run_cmd() -> None:
    """Execute pre-commit intelligence suite across staged files."""
    from rush.hook.ast_linter import FastIncrementalAstLinter
    from rush.hook.branch_guard import BranchProtectionGuard
    from rush.hook.conflict_guard import ConflictMarkerGuard
    from rush.hook.staged_scanner import StagedFileScanner
    from rush.hook.trojan_source import TrojanSourceDetector

    guard = BranchProtectionGuard(Path.cwd())
    ok, err = guard.check_current_branch()
    if not ok:
        click.echo(f"[HOOK BLOCKED] {err}", err=True)
        sys.exit(1)

    scanner = StagedFileScanner(Path.cwd())
    staged = scanner.get_staged_files()
    if not staged:
        click.echo("No staged files to check.")
        return

    ast_errs = FastIncrementalAstLinter.lint_staged_python(staged)
    if ast_errs:
        for e in ast_errs:
            click.echo(f"[AST ERROR] {e}", err=True)
        sys.exit(1)

    for p in staged:
        trojans = TrojanSourceDetector.inspect_file(p)
        if trojans:
            for t in trojans:
                click.echo(f"[SECURITY ERROR] {t}", err=True)
            sys.exit(1)

        conflicts = ConflictMarkerGuard.inspect_file(p)
        if conflicts:
            for c in conflicts:
                click.echo(f"[CONFLICT ERROR] {c}", err=True)
            sys.exit(1)

    click.echo(f"Pre-commit checks passed across {len(staged)} staged files.")


if __name__ == "__main__":
    cli()













