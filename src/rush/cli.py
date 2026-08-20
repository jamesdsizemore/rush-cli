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


for _catalog_tool in ALL_TOOLS:
    if _catalog_tool.name not in {"review", "format", "commit-msg", "sbom", "fix"}:
        cli.add_command(build_catalog_path_command(_catalog_tool))


if __name__ == "__main__":
    cli()
