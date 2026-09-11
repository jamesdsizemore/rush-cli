"""Click CLI entrypoint — 34 canonical subcommands + `mcp serve`.

Architecture §6. Each subcommand calls the same ToolFn.__call__ that the
MCP tool calls (requirement C3 — single source of truth).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, get_args

import click

from . import __version__
from .cli_support.catalog_commands import build_catalog_path_command
from .cli_support.options import _extract_permissions, permission_options
from .cli_support.rendering import (
    _render_session_result,
    _run_tool,
    exit_code_for,
    exit_with_result,
)
from .config import RushConfigError, load_config
from .logging import setup_logging
from .memory.store import MemorySubject
from .permissions import ExecutionPermissions
from .tools import ALL_TOOLS

if TYPE_CHECKING:
    from .memory.maintenance import MaintenanceTask
    from .tools.memory import SourceKind

_MEMORY_SUBJECTS = get_args(MemorySubject)

__all__ = [
    "_extract_permissions",
    "_render_session_result",
    "_run_tool",
    "build_catalog_path_command",
    "cli",
    "exit_code_for",
    "exit_with_result",
    "permission_options",
]


class RushGroup(click.Group):
    """Click group dynamically resolving mesh commands while preserving public operations inventory."""

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        if cmd_name == "lock":
            return lock_cmd_group
        return super().get_command(ctx, cmd_name)


@click.group(cls=RushGroup, context_settings={"help_option_names": ["-h", "--help"]})
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


def _benchmark_default_root() -> Path:
    """Return the durable user-local benchmark root, never a repository path."""
    return (
        Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        / "Rush"
        / "benchmarks"
    )


def _benchmark_default_model_cache() -> Path:
    """Return the durable user-local model cache, never a repository path."""
    return (
        Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        / "Rush"
        / "benchmark-model-cache"
    )


@cli.group()
def benchmark() -> None:
    """Run and inspect durable local benchmark artifacts."""


@benchmark.command("run")
@click.option("--scenario", type=str, default=None, help="One declared scenario ID.")
@click.option("--all", "run_all", is_flag=True, help="Run every declared scenario.")
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=_benchmark_default_root() / "run",
    show_default=True,
)
@click.option(
    "--model-cache",
    type=click.Path(path_type=Path),
    default=_benchmark_default_model_cache(),
    show_default=True,
)
@click.option(
    "--allow-model-download",
    type=str,
    multiple=True,
    help="Candidate ID permitted to download into the external model cache.",
)
@click.option(
    "--local-runtime-executable",
    type=click.Path(path_type=Path),
    multiple=True,
    help="Explicit llama.cpp and/or onnxruntime_perf_test executable; repeat as needed.",
)
@click.option(
    "--allow-live-route",
    type=str,
    multiple=True,
    help="Provider route ID permitted for live execution; repeat as needed.",
)
@click.option(
    "--provider-executable",
    type=click.Path(path_type=Path),
    default=None,
    help="Explicit provider CLI executable.",
)
@click.option(
    "--router-url",
    multiple=True,
    help="Explicit router endpoint as NAME=URL; repeat for multiple routers.",
)
@click.option(
    "--foreground",
    is_flag=True,
    help="Run in the invoking process; detached execution is the default.",
)
def benchmark_run(
    scenario: str | None,
    run_all: bool,
    output: Path,
    model_cache: Path,
    allow_model_download: tuple[str, ...],
    local_runtime_executable: tuple[Path, ...],
    allow_live_route: tuple[str, ...],
    provider_executable: Path | None,
    router_url: tuple[str, ...],
    foreground: bool,
) -> None:
    """Start a durable detached benchmark; live routes require explicit opt-in."""
    from scripts.benchmarks.run import main as benchmark_main

    argv = ["--output", str(output), "--model-cache", str(model_cache)]
    if scenario:
        argv.extend(["--scenario", scenario])
    else:
        argv.append("--all")
    for candidate_id in allow_model_download:
        argv.extend(["--allow-model-download", candidate_id])
    for runtime_path in local_runtime_executable:
        argv.extend(["--local-runtime-executable", str(runtime_path)])
    for route_id in allow_live_route:
        argv.extend(["--allow-live-route", route_id])
    if provider_executable:
        argv.extend(["--provider-executable", str(provider_executable)])
    for endpoint in router_url:
        argv.extend(["--router-url", endpoint])
    if foreground:
        raise click.exceptions.Exit(benchmark_main(argv))

    from scripts.benchmarks.jobs import start_job

    job = start_job(
        job_root=output.parent / "jobs",
        argv=argv,
        output=output,
    )
    click.echo(
        f"Started {job['job_id']}; durable state: {output.parent / 'jobs' / (job['job_id'] + '.json')}"
    )


@benchmark.command("status")
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=_benchmark_default_root() / "run",
    show_default=True,
)
def benchmark_status(output: Path) -> None:
    """Print durable job and scenario state without attaching to a worker."""
    jobs_root = output.parent / "jobs"
    if jobs_root.is_dir():
        for path in sorted(jobs_root.glob("benchmark-*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            click.echo(
                f"{payload.get('job_id', path.stem)}: {payload.get('state', 'unknown')}"
            )
    if not output.is_dir():
        return
    results: list[dict[str, object]] = []
    for path in sorted(output.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if (
            isinstance(payload, dict)
            and "scenario_id" in payload
            and "outcome" in payload
        ):
            results.append(payload)
    if not results:
        click.echo("No benchmark scenario results found.")
        return
    for result in results:
        click.echo(
            f"{result['scenario_id']}: {result['outcome']} ({result.get('duration_ms', 0)}ms)"
        )


@benchmark.command("check")
@click.argument("path", type=click.Path(exists=True, path_type=Path), default=Path("."))
@click.option(
    "--threshold", default=5.0, type=float, help="Percentage threshold for regression."
)
@click.option(
    "--record",
    is_flag=True,
    help="Record current samples as baseline in .rush/baselines.json.",
)
@permission_options
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def benchmark_check_cmd(
    path: Path,
    threshold: float,
    record: bool,
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
    as_json: bool,
) -> None:
    """Compare performance samples against baseline thresholds at <path>."""
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
        "benchmark",
        path,
        as_json=as_json,
        permissions=perms,
        extra_kwargs={"threshold_percent": threshold, "record": record},
    )


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
@click.option(
    "--memory-session",
    default=None,
    help=(
        "MC11: restrict this server to one bounded memory-handoff session's restricted "
        "rush_memory receiver (receive/expand/related/resume only). The session's "
        "capability is read from RUSH_MEMORY_CAPABILITY, never a CLI argument."
    ),
)
def serve(memory_session: str | None) -> None:
    """Start the rush MCP server on stdio (for coding agents)."""
    import asyncio

    from .mcp import run_stdio

    asyncio.run(run_stdio(memory_session))


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
    "--non-interactive/--interactive",
    "non_interactive",
    default=True,
    help="Select prompting behavior; does not by itself suppress an explicitly granted --install.",
)
@click.option(
    "--install",
    is_flag=True,
    help=(
        "Build and apply the engine provision plan for recommended toolchains. "
        "Requires the relevant --allow-* grants; without them the plan is previewed only."
    ),
)
@permission_options
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Print detected stacks and installation summary as JSON.",
)
def setup_cmd(
    path: Path,
    non_interactive: bool,
    install: bool,
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
    as_json: bool,
) -> None:
    """Inspect repository stacks and set up recommended quality toolchains."""
    from .tools.setup_wizard import run_setup_wizard

    permissions = (
        _extract_permissions(
            allow_network=allow_network,
            allow_download=allow_download,
            allow_cache_write=allow_cache_write,
            allow_build=allow_build,
            allow_slow=allow_slow,
            allow_artifact_write=allow_artifact_write,
            allow_browser=allow_browser,
        )
        if install
        else None
    )
    res = run_setup_wizard(
        path.resolve(),
        non_interactive=non_interactive,
        install=install,
        permissions=permissions,
    )
    if as_json:
        click.echo(json.dumps(res, indent=2, default=str))
    else:
        click.echo(f"Detected stacks: {', '.join(res['stacks']) or 'none'}")
        if res["skipped"]:
            click.echo(f"Recommended engines: {', '.join(res['skipped'])}")
        provision = res.get("provision")
        if provision and provision.get("plan_only"):
            click.echo(
                f"Provision plan {res['plan_id'][:12]} built (preview only); "
                "pass --allow-network --allow-download --allow-cache-write (and --allow-build "
                "where required) to apply it."
            )
        elif provision:
            if provision["applied"]:
                click.echo(f"Installed: {', '.join(provision['applied'])}")
            if provision["failed"]:
                click.echo(f"Failed: {', '.join(sorted(provision['failed']))}")
            if provision["permission_blocked"]:
                click.echo(
                    f"Permission blocked: {', '.join(sorted(provision['permission_blocked']))}"
                )


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
    from .safety.redactor import sanitize_value

    target_cfg.write_text(sanitize_value(cfg_content).value, encoding="utf-8")
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
                from .invocation import InvocationExecutor, resolve_invocation

                target = path.resolve()
                executor = InvocationExecutor()
                executor.register(t.name, t.__call__)
                context = resolve_invocation(
                    {"operation_id": t.name, "path": str(target)},
                    transport="cli",
                    workspace_root=target if target.is_dir() else target.parent,
                    permissions=perms,
                )
                res = executor.execute(context)
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
@click.argument("paths", nargs=-1, type=click.Path(exists=True, path_type=Path))
@permission_options
def ui_cmd(
    paths: tuple[Path, ...],
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
) -> None:
    """Open the interactive terminal UI to explore tool results and findings.

    Accepts one or more project paths (`rush ui path1 path2 ...`) to open
    and switch between multiple projects; defaults to the current directory
    when none are given.
    """
    from .tui import ProjectSeed, run_interactive_tui
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
    resolved_paths = [p.resolve() for p in paths] or [Path.cwd()]
    seeds = []
    for resolved in resolved_paths:
        res = run_workflow_suite(suite=CHECK_SUITE, path=resolved, permissions=perms)
        seeds.append(
            ProjectSeed(
                name=resolved.name or str(resolved), root=resolved, results=[res]
            )
        )
    run_interactive_tui(seeds)


def _dashboard_descriptor_path(server_id: str) -> Path:
    from .setup.provision import default_data_root

    return default_data_root() / "dashboard" / f"{server_id}.json"


def _write_dashboard_descriptor(ctx: Any) -> Path:
    """Private per-instance descriptor for `--reconnect` discovery (plan
    3.7): schema_version, PID, start nonce, bound port, control capability.
    Never a project artifact or browser response. POSIX-only 0700/0600
    modes; on non-POSIX platforms `os.chmod` is a no-op and this descriptor
    is skipped entirely rather than persisting an unverified-ACL secret."""
    path = _dashboard_descriptor_path(ctx.server_id)
    if os.name != "posix":
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    payload = {
        "schema_version": 1,
        "pid": ctx.pid,
        "start_nonce": ctx.start_nonce,
        "bound_host": ctx.bound_host,
        "bound_port": ctx.bound_port,
        "control_capability": ctx.auth.control_capability,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def _remove_dashboard_descriptor(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def _newest_dashboard_descriptor(server_id: str | None) -> Path | None:
    directory = _dashboard_descriptor_path("_").parent
    if not directory.is_dir():
        return None
    if server_id is not None:
        candidate = directory / f"{server_id}.json"
        return candidate if candidate.is_file() else None
    candidates = sorted(
        directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    return candidates[0] if candidates else None


def _reconnect_existing_dashboard(
    *, server_id: str | None, no_open: bool, json_output: bool
) -> None:
    import webbrowser

    from .dashboard.server import reconnect_dashboard

    descriptor_path = _newest_dashboard_descriptor(server_id)
    if descriptor_path is None:
        raise click.ClickException("no running dashboard server found to reconnect to.")
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    base_url = f"http://{descriptor['bound_host']}:{descriptor['bound_port']}"
    try:
        new_token = reconnect_dashboard(base_url, descriptor["control_capability"])
    except Exception as exc:
        _remove_dashboard_descriptor(descriptor_path)
        raise click.ClickException(
            f"dashboard server is no longer reachable: {exc}"
        ) from exc

    launch_url = f"{base_url}/#token={new_token}"
    if json_output:
        click.echo(json.dumps({"ready": True, "url": launch_url}))
    else:
        click.echo(f"Reconnected: {launch_url}")
    if not no_open:
        try:
            webbrowser.open(launch_url)
        except Exception:  # noqa: BLE001, S110
            pass


@cli.command(name="dashboard")
@click.argument("path", type=click.Path(exists=True, path_type=Path), default=Path("."))
@click.option(
    "--port", default=0, type=int, help="Port to bind dashboard server (0 for random)."
)
@click.option(
    "--no-open", is_flag=True, help="Do not open a browser automatically on launch."
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Emit a readiness/URL JSON record instead of prose.",
)
@click.option(
    "--reconnect",
    is_flag=True,
    help=(
        "Issue a fresh one-use launch URL for an already-running dashboard "
        "server instead of starting a new one."
    ),
)
@click.option(
    "--server-id",
    default=None,
    help="Select a specific running server for --reconnect (default: newest live one).",
)
@permission_options
def dashboard_cmd(
    path: Path,
    port: int,
    no_open: bool,
    json_output: bool,
    reconnect: bool,
    server_id: str | None,
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
) -> None:
    """Launch an authenticated, CSRF-hardened local web dashboard on 127.0.0.1."""
    if reconnect:
        _reconnect_existing_dashboard(
            server_id=server_id, no_open=no_open, json_output=json_output
        )
        return

    import threading
    import webbrowser

    from .dashboard.server import bootstrap_launch_url, create_dashboard_server
    from .workflows.projects import register_project
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

    resolved_path = path.resolve()
    record = register_project(resolved_path)
    empty_snapshot = {
        "schema_version": 1,
        "project_id": record.project_id,
        "source_identity": record.root,
        "root": record.root,
        "files": [],
        "findings": [],
        "memories": [],
        "agents": [],
    }
    # Start the authenticated server first -- never block the browser
    # opening on a long scan (plan §2/3.7). The scan below runs in the
    # background; wiring its results into this project's live map data is
    # P66-04's scan-actions packet, not this one.
    server, ctx, token = create_dashboard_server(
        {record.project_id: empty_snapshot}, port=port
    )
    launch_url = bootstrap_launch_url(ctx, token)
    descriptor_path = _write_dashboard_descriptor(ctx)

    if json_output:
        click.echo(
            json.dumps({"ready": True, "url": launch_url, "server_id": ctx.server_id})
        )
    else:
        click.echo(f"Dashboard running at: {launch_url}")
        click.echo("Press Ctrl+C to stop.")

    if not no_open:
        try:
            webbrowser.open(launch_url)
        except Exception:  # noqa: BLE001, S110
            pass

    def _run_initial_scan() -> None:
        run_workflow_suite(suite=CHECK_SUITE, path=resolved_path, permissions=perms)

    scan_thread = threading.Thread(target=_run_initial_scan, daemon=True)
    scan_thread.start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        click.echo("\nStopping dashboard.")
    finally:
        server.shutdown()
        server.server_close()
        _remove_dashboard_descriptor(descriptor_path)


# --- Trust & Plugin CLI commands ------------------------------------------


@cli.command(name="trust")
@click.argument("target", required=False, default=".")
@click.argument("extra", required=False, default=None)
@click.option(
    "--plugin",
    "plugin_opt",
    default=None,
    help="Authorize or revoke trust for a specific plugin.",
)
@click.option(
    "--revoke",
    is_flag=True,
    help="Revoke trust for the specified repository or plugin.",
)
def trust_cmd(
    target: str,
    extra: str | None,
    plugin_opt: str | None,
    revoke: bool,
) -> None:
    """Authorize or revoke local execution trust for repositories or plugins (Control 6)."""
    from .plugins.closure import build_plugin_closure
    from .plugins.loader import discover_plugins
    from .plugins.snapshot_store import PluginSnapshotStore
    from .plugins.trust import revoke_trust, trust_repo
    from .plugins.trust_store import PluginTrustStore

    plugin_name = plugin_opt
    repo_path = Path(target) if target != "plugin" else Path(".")
    if target == "plugin":
        plugin_name = extra
        if not plugin_name:
            click.echo(
                "Error: Plugin name required when using 'rush trust plugin <name>'",
                err=True,
            )
            sys.exit(1)

    if plugin_name:
        root = repo_path.resolve()
        repo_root = root if root.is_dir() else root.parent
        trust_store = PluginTrustStore(repo_root=repo_root)

        if revoke:
            revoked = trust_store.revoke_trust(plugin_name)
            if revoked:
                click.echo(f"Revoked trust for plugin: {plugin_name}")
            else:
                click.echo(f"Plugin '{plugin_name}' was not found in trust ledger.")
        else:
            plugins = discover_plugins(repo_root)
            matched = next((p for p in plugins if p.name == plugin_name), None)
            if not matched:
                click.echo(
                    f"Plugin '{plugin_name}' not found in configuration.", err=True
                )
                sys.exit(1)

            exec_path = (
                Path(matched.command[1])
                if len(matched.command) > 1 and not matched.command[1].startswith("-")
                else Path(matched.command[0])
            )
            if not exec_path.is_absolute():
                exec_path = (repo_root / exec_path).resolve()

            plugin_root = exec_path.parent if exec_path.is_file() else repo_root
            closure = build_plugin_closure(
                plugin_root=plugin_root,
                entrypoint=exec_path,
                config={"name": matched.name, "command": matched.command},
                plugin_name=matched.name,
            )
            snapshot_store = PluginSnapshotStore()
            snapshot_dir = snapshot_store.materialize_snapshot(
                closure=closure, plugin_root=plugin_root
            )
            trust_store.grant_trust(plugin_name, closure.closure_digest, snapshot_dir)
            click.echo(
                f"Approved plugin as trusted: {plugin_name} (digest: {closure.closure_digest[:12]}...)"
            )
    else:
        root = repo_path.resolve()
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
    """Execute a configured custom plugin against path using HardenedPluginExecutor."""
    from .contracts.operations import AdminOperationAdapter
    from .plugins.closure import build_plugin_closure
    from .plugins.executor import HardenedPluginExecutor
    from .plugins.loader import PluginSpec, discover_plugins
    from .plugins.snapshot_store import PluginSnapshotStore
    from .plugins.trust_store import PluginTrustStore

    root = path.resolve()
    repo_root = root if root.is_dir() else root.parent
    plugins = discover_plugins(repo_root)
    matched = next((p for p in plugins if p.name == plugin_name), None)
    if not matched:
        click.echo(f"Plugin '{plugin_name}' not found in configuration.", err=True)
        sys.exit(1)

    exec_path = (
        Path(matched.command[1])
        if len(matched.command) > 1 and not matched.command[1].startswith("-")
        else Path(matched.command[0])
    )
    if not exec_path.is_absolute():
        exec_path = (repo_root / exec_path).resolve()

    plugin_root = exec_path.parent if exec_path.is_file() else repo_root

    closure = None
    if exec_path.is_file():
        try:
            closure = build_plugin_closure(
                plugin_root=plugin_root,
                entrypoint=exec_path,
                config={"name": matched.name, "command": matched.command},
                plugin_name=matched.name,
            )
        except Exception:  # noqa: BLE001
            closure = None

    spec = PluginSpec(
        name=matched.name,
        executable_path=exec_path,
        command=list(matched.command),
        description=matched.description,
        file_extensions=matched.file_extensions,
        closure=closure,
    )

    trust_store = PluginTrustStore(repo_root=repo_root)
    snapshot_store = PluginSnapshotStore()
    executor = HardenedPluginExecutor(
        repo_root=repo_root,
        trust_store=trust_store,
        snapshot_store=snapshot_store,
    )

    paths = [root] if root.is_file() else []
    result = executor.execute(spec, paths=paths)

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        status_color = (
            "green"
            if result.status == "ok"
            else ("yellow" if result.status == "warn" else "red")
        )
        click.secho(
            f"[{result.tool}] Status: {result.status}", fg=status_color, bold=True
        )
        click.echo(result.summary)
        for finding in result.findings:
            click.echo(f"  - [{finding.severity}] {finding.message}")

    adapter = AdminOperationAdapter(
        operation_id="cli.plugin_run",
        target_contract_id="ClickExitCode",
    )
    code = exit_code_for(result.status)
    sys.exit(adapter.validate_output(code))


for _catalog_tool in ALL_TOOLS:
    if _catalog_tool.name not in {
        "review",
        "format",
        "commit-msg",
        "sbom",
        "fix",
        "benchmark",
        "memory",
        "patch-apply",
    }:
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
        click.echo(
            f"  - [{f.get('severity', 'info')}] {f.get('path')}:{f.get('line')} {f.get('message')}"
        )
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


@cli.group(name="patch")
def patch_group() -> None:
    """Isolated AI patch testing, verification, and session memory."""


@patch_group.command(name="apply")
@click.argument(
    "patch_file", metavar="PATH", type=click.Path(exists=True, path_type=Path)
)
@click.option(
    "--dry-run/--no-dry-run", default=True, help="Verify without promoting changes."
)
@click.option(
    "--circuit-breaker/--no-circuit-breaker",
    default=True,
    help="Stop after failed verification.",
)
@click.option(
    "--allow-artifact-write", is_flag=True, help="Permit verified patch promotion."
)
@click.option("--json", "as_json", is_flag=True, help="Print ToolResult JSON.")
def patch_apply_cmd(
    patch_file: Path,
    dry_run: bool,
    circuit_breaker: bool,
    allow_artifact_write: bool,
    as_json: bool,
) -> None:
    """Verify PATH as a unified diff in isolation; explicitly grant promotion."""
    _run_tool(
        "patch-apply",
        Path.cwd(),
        as_json=as_json,
        permissions=ExecutionPermissions(artifact_write=allow_artifact_write),
        extra_kwargs={
            "patch_file": patch_file,
            "dry_run": dry_run,
            "circuit_breaker": circuit_breaker,
        },
    )


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
        click.echo(
            f"  - [{r.error_signature[:8]}] {r.target_file} (Successes: {r.success_count})"
        )


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
        click.echo(
            f"[PROTECTED] Target path '{file_path}' is an immutable governance file.",
            err=True,
        )
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


@token_group.command(name="outline")
@click.argument("file_path", type=click.Path(exists=True, path_type=Path))
def token_outline_cmd(file_path: Path) -> None:
    """Generate high-density AST skeleton outline for context compression."""
    from rush.token_economy.compressor import PythonAstOutlineCompressor

    source = file_path.read_text(encoding="utf-8", errors="replace")
    if file_path.suffix == ".py":
        compressed = PythonAstOutlineCompressor.compress_source(source)
        click.echo(compressed)
    else:
        click.echo(source)


@token_group.command(name="cache-advisor")
@click.argument("file_path", type=click.Path(exists=True, path_type=Path))
def token_cache_advisor_cmd(file_path: Path) -> None:
    """Analyze prompt prefix cache breakpoints."""
    from rush.token_economy.cache_advisor import PromptCacheAdvisor

    text = file_path.read_text(encoding="utf-8", errors="replace")
    suggestion = PromptCacheAdvisor.analyze_prefix(text)
    click.echo(
        f"Cache Advisor Analysis: {suggestion.reason} (Est. Savings: {suggestion.estimated_cache_savings_percent}%)"
    )


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
@click.option(
    "--output-ts",
    type=click.Path(path_type=Path),
    help="Path to output generated TypeScript interfaces.",
)
def sync_openapi_cmd(openapi_file: Path, output_ts: Path | None) -> None:
    """Verify OpenAPI contract and optionally generate TypeScript types."""
    from rush.sync.ts_generator import TypeScriptContractGenerator

    json_text = openapi_file.read_text(encoding="utf-8")
    ts_code = TypeScriptContractGenerator.generate_interfaces(json_text)
    if output_ts:
        from .safety.redactor import sanitize_value

        output_ts.write_text(sanitize_value(ts_code).value, encoding="utf-8")
        click.echo(f"Wrote generated TypeScript interfaces to {output_ts}")
    else:
        click.echo(ts_code)


@sync_group.command(name="env")
@click.argument("env_example", default=".env.example", type=click.Path(path_type=Path))
@click.argument("env_actual", default=".env", type=click.Path(path_type=Path))
def sync_env_cmd(env_example: Path, env_actual: Path) -> None:
    """Check environment variable synchronization between .env.example and .env."""
    from rush.sync.env_sync import EnvironmentVariableSynchronizer

    missing = EnvironmentVariableSynchronizer.find_missing_keys(env_example, env_actual)
    if missing:
        click.echo(f"Missing environment variables in {env_actual} ({len(missing)}):")
        for k in missing:
            click.echo(f"  - {k}")
        sys.exit(1)
    else:
        click.echo(
            f"All environment variables in {env_example} are present in {env_actual}."
        )


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


@hygiene_group.command(name="clean-imports")
@click.argument("target_file", type=click.Path(exists=True, path_type=Path))
def hygiene_clean_imports_cmd(target_file: Path) -> None:
    """Remove unused imports from target Python source file."""
    from rush.hygiene.unused_import_cleaner import UnusedImportCleaner

    cleaned, count = UnusedImportCleaner.clean_file(target_file)
    if count > 0:
        target_file.write_text(cleaned, encoding="utf-8")
        click.echo(f"Cleaned {count} unused import(s) in {target_file}")
    else:
        click.echo(f"No unused imports found in {target_file}")


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


@codegraph_group.command(name="callers")
@click.argument("symbol_name")
def codegraph_callers_cmd(symbol_name: str) -> None:
    """Trace all reverse callers of target symbol."""
    from rush.codegraph.store import CodeGraphStore
    from rush.codegraph.traverser import CallGraphTraverser

    store = CodeGraphStore(Path.cwd() / ".codegraph" / "graph.db")
    traverser = CallGraphTraverser(store)
    steps = traverser.trace_callers(symbol_name)
    click.echo(f"Callers of '{symbol_name}' ({len(steps)}):")
    for s in steps:
        click.echo(
            f"  - [{s.caller.file_path}:{s.caller.start_line}] {s.caller.symbol_name} -> calls -> {s.callee.symbol_name} (depth: {s.depth})"
        )


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
        click.echo(
            f"  - {r.file_name}: {r.raw_bytes} B (gzip: {r.gzip_bytes} B, brotli: ~{r.brotli_est_bytes} B)"
        )


@bundle_group.command(name="dead-assets")
@click.argument("assets_dir", type=click.Path(exists=True, path_type=Path))
def bundle_dead_assets_cmd(assets_dir: Path) -> None:
    """Scan public/assets directories for unreferenced images and media."""
    from rush.bundle.dead_assets import OrphanedAssetScanner

    assets_root = assets_dir.resolve()
    unused = [
        asset
        for asset in OrphanedAssetScanner(Path.cwd()).find_orphaned_assets()
        if asset.is_relative_to(assets_root)
    ]
    click.echo(f"Unreferenced Assets ({len(unused)}):")
    for u in unused:
        click.echo(f"  - {u}")


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
        click.echo(
            f"  - [{s.risk_tier}] {s.file_path}: Risk {s.composite_risk} (Churn: {s.churn_score}, Complexity: {s.complexity_score})"
        )


@hotspots_group.command(name="bus-factor")
def hotspots_bus_factor_cmd() -> None:
    """Calculate module knowledge distribution and bus factor risks."""
    from rush.hotspots.bus_factor import BusFactorAssessor

    reports = BusFactorAssessor(Path.cwd()).assess_ownership()
    click.echo(f"Bus Factor Analysis ({len(reports)} files):")
    for r in reports[:10]:
        click.echo(
            f"  - {r.file_path}: {r.total_authors} authors, ownership entropy {r.author_entropy} "
            f"(Primary author: {r.primary_owner} {r.ownership_percent}%)"
        )


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


@governance_group.command(name="check")
def governance_check_cmd() -> None:
    """Check that multi-IDE rule files are synchronized with AGENTS.md."""
    from rush.governance.parity_checker import RuleParityChecker

    drifted = RuleParityChecker(Path.cwd()).check_parity()
    if not drifted:
        click.echo("[OK] All multi-IDE governance rule files match AGENTS.md.")
    else:
        click.echo(
            f"[DRIFT DETECTED] Unsynchronized governance files ({len(drifted)}):",
            err=True,
        )
        for d in drifted:
            click.echo(f"  - {d.target_path}: {d.reason}", err=True)
        sys.exit(1)


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
    try:
        entries = scanner.get_staged_entries()
    except RuntimeError:
        click.echo("[INDEX ERROR] Cannot read staged index.", err=True)
        sys.exit(1)
    if not entries:
        click.echo("No staged files to check.")
        return

    invalid = [
        entry for entry in entries if entry.status in {"error", "unmerged_index"}
    ]
    if invalid:
        for entry in invalid:
            stages = ", ".join(
                f"stage {stage.stage}: {stage.mode} {stage.object_id}"
                for stage in entry.stages
            )
            click.echo(
                f"[INDEX ERROR] {entry.status}: {entry.relative_path} ({stages})",
                err=True,
            )
        sys.exit(1)

    staged = [entry for entry in entries if entry.status == "staged"]
    deleted_count = sum(entry.status == "deleted" for entry in entries)
    ast_errs = FastIncrementalAstLinter.lint_staged_entries(staged)
    if ast_errs:
        click.echo("\n".join(f"[AST ERROR] {e}" for e in ast_errs), err=True)
        sys.exit(1)

    for entry in staged:
        assert entry.content is not None, "staged entry has no index blob"
        for detector, label in (
            (TrojanSourceDetector, "SECURITY"),
            (ConflictMarkerGuard, "CONFLICT"),
        ):
            errors = detector.inspect_content(entry.path, entry.content)
            if errors:
                click.echo("\n".join(f"[{label} ERROR] {e}" for e in errors), err=True)
                sys.exit(1)

    click.echo(
        f"Pre-commit checks passed across {len(staged)} staged files "
        f"({deleted_count} staged deletions)."
    )


@cli.group(name="score")
def score_group() -> None:
    """Repository quality scorecard and health grade calculator."""


@score_group.command(name="compute")
@click.option("--type-safety", default=90.0, help="Type safety pillar score (0-100).")
@click.option(
    "--test-coverage", default=85.0, help="Test coverage pillar score (0-100)."
)
@click.option("--code-health", default=92.0, help="Code health pillar score (0-100).")
@click.option("--security", default=95.0, help="Security pillar score (0-100).")
@click.option(
    "--token-economy", default=88.0, help="Token economy pillar score (0-100)."
)
@click.option("--governance", default=94.0, help="Governance pillar score (0-100).")
@click.option(
    "--export-svg", type=click.Path(path_type=Path), help="Path to write SVG badge."
)
@click.option(
    "--export-html", type=click.Path(path_type=Path), help="Path to write HTML report."
)
def score_compute_cmd(
    type_safety: float,
    test_coverage: float,
    code_health: float,
    security: float,
    token_economy: float,
    governance: float,
    export_svg: Path | None,
    export_html: Path | None,
) -> None:
    """Calculate deterministic 0-100% composite score and grade."""
    from rush.score.calculator import CompositeScorecardCalculator, PillarScores
    from rush.score.html_report import HtmlReportGenerator
    from rush.score.svg_badge import SvgBadgeGenerator

    pillars = PillarScores(
        type_safety=type_safety,
        test_coverage=test_coverage,
        code_health=code_health,
        security=security,
        token_economy=token_economy,
        governance=governance,
    )
    report = CompositeScorecardCalculator.compute_scorecard(pillars)
    click.echo(report.summary)

    if export_svg:
        svg = SvgBadgeGenerator.generate_badge_svg(
            report.composite_score, report.letter_grade
        )
        from .safety.redactor import sanitize_value

        export_svg.write_text(sanitize_value(svg).value, encoding="utf-8")
        click.echo(f"Wrote SVG badge to {export_svg}")

    if export_html:
        html = HtmlReportGenerator.generate_html_report(report)
        export_html.write_text(html, encoding="utf-8")
        click.echo(f"Wrote HTML report to {export_html}")


@cli.group(name="consensus")
def consensus_group() -> None:
    """Multi-model AI code review reconciliation."""


@consensus_group.command(name="reconcile")
@click.argument(
    "findings_files", nargs=-1, type=click.Path(exists=True, path_type=Path)
)
@click.option(
    "--min-agreement", default=0.5, help="Minimum model agreement ratio (0.0 - 1.0)."
)
def consensus_reconcile_cmd(
    findings_files: tuple[Path, ...], min_agreement: float
) -> None:
    """Reconcile findings from multi-model reviews using weighted consensus."""
    import json

    from rush.score.consensus import ModelFinding, MultiModelConsensusReconciler

    reconciler = MultiModelConsensusReconciler(min_agreement_ratio=min_agreement)
    all_findings: list[ModelFinding] = []
    models: set[str] = set()

    for f_path in findings_files:
        try:
            data = json.loads(f_path.read_text(encoding="utf-8"))
            items = data if isinstance(data, list) else data.get("findings", [])
            model_name = f_path.stem
            models.add(model_name)
            for item in items:
                all_findings.append(
                    ModelFinding(
                        model_name=item.get("model", model_name),
                        file_path=item.get("path", item.get("file_path", "")),
                        line_number=item.get("line", item.get("line_number", 1)),
                        rule_id=item.get("rule", item.get("rule_id", "ai-review")),
                        severity=item.get("severity", "warn"),
                        description=item.get("message", item.get("description", "")),
                    )
                )
        except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError) as e:
            click.echo(f"Warning: Could not parse '{f_path}': {e}", err=True)

    total_models = max(len(models), 1)
    consensus = reconciler.reconcile_findings(all_findings, total_models=total_models)
    click.echo(
        f"Consensus Findings ({len(consensus)} agreed by >={int(min_agreement * 100)}% of {total_models} models):"
    )
    for c in consensus:
        click.echo(
            f"  - [{c.severity.upper()}] {c.file_path}:{c.line_number} {c.rule_id} ({c.description}) [Confidence: {int(c.confidence * 100)}%, Models: {', '.join(c.agreeing_models)}]"
        )


# -----------------------------------------------------------------------------
# Phase 41: Foundations, Preferences, Sessions & Ship Vectors
# -----------------------------------------------------------------------------


@cli.group(name="session")
def session_group() -> None:
    """Developer session checkpoint management."""


@session_group.command(name="save")
@click.argument("name")
@click.option(
    "--file",
    "-f",
    "files",
    multiple=True,
    help="Active files to include in session snapshot.",
)
@click.option(
    "--goal", "current_goal", help="Current user goal recorded as handoff evidence."
)
@click.option(
    "--open-work",
    multiple=True,
    help="Open work item recorded as handoff evidence; repeat for multiple items.",
)
@click.option(
    "--historic-instruction",
    help="Historic instruction captured only as quarantined evidence.",
)
@click.option(
    "--failure-fingerprint",
    help="Optional failed-attempt fingerprint; no failed patch is returned.",
)
@click.option(
    "--dependency",
    "dependencies",
    multiple=True,
    help="Repository-local dependency path to snapshot for handoff freshness.",
)
@click.option(
    "--provider",
    "provider_id",
    default=None,
    help="Target provider this handoff is destined for; enables delta-only handoffs.",
)
@permission_options
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def session_save_cmd(
    name: str,
    files: tuple[str, ...],
    current_goal: str | None,
    open_work: tuple[str, ...],
    historic_instruction: str | None,
    failure_fingerprint: str | None,
    dependencies: tuple[str, ...],
    provider_id: str | None,
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
    as_json: bool,
) -> None:
    """Save an active session checkpoint to .rush/sessions/."""
    from .tools.continuity import SessionContinuityTool

    result = SessionContinuityTool().run(
        Path.cwd(),
        operation="save",
        name=name,
        files=list(files),
        handoff={
            "current_goal": current_goal,
            "open_work": list(open_work),
            "historic_instruction": historic_instruction,
            "failure_fingerprint": failure_fingerprint,
            "dependencies": list(dependencies),
        },
        provider_id=provider_id,
        permissions=_extract_permissions(
            allow_network=allow_network,
            allow_download=allow_download,
            allow_cache_write=allow_cache_write,
            allow_build=allow_build,
            allow_slow=allow_slow,
            allow_artifact_write=allow_artifact_write,
            allow_browser=allow_browser,
        ),
    )
    _render_session_result(result, as_json)


@session_group.command(name="list")
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def session_list_cmd(as_json: bool) -> None:
    """List all saved session checkpoints."""
    from .tools.continuity import SessionContinuityTool

    _render_session_result(
        SessionContinuityTool().run(Path.cwd(), operation="list"),
        as_json,
    )


@session_group.command(name="restore")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def session_restore_cmd(name: str, as_json: bool) -> None:
    """Restore a saved session checkpoint."""
    from .tools.continuity import SessionContinuityTool

    _render_session_result(
        SessionContinuityTool().run(Path.cwd(), operation="restore", name=name),
        as_json,
    )


@session_group.command(name="resume")
@click.argument("name")
@click.option(
    "--provider",
    "provider_id",
    required=True,
    help="Implemented route: claude_code, codex_cli, antigravity_cli, or omniroute_api.",
)
@permission_options
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def session_resume_cmd(
    name: str,
    provider_id: str,
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
    as_json: bool,
) -> None:
    """Resume a checkpoint through an enabled user-owned provider route."""
    from .tools.continuity import SessionContinuityTool

    result = SessionContinuityTool().run(
        Path.cwd(),
        operation="provider_resume",
        name=name,
        provider_id=provider_id,
        permissions=_extract_permissions(
            allow_network=allow_network,
            allow_download=allow_download,
            allow_cache_write=allow_cache_write,
            allow_build=allow_build,
            allow_slow=allow_slow,
            allow_artifact_write=allow_artifact_write,
            allow_browser=allow_browser,
        ),
    )
    _render_session_result(result, as_json)


# -----------------------------------------------------------------------------
# Phase 61: Cross-LLM Memory — Memory Query/Write Interface (MemoryTool, P61.12)
# -----------------------------------------------------------------------------


@cli.group(name="memory")
def memory_group() -> None:
    """Query, write, and promote cross-tool memory artifacts."""


@memory_group.command(name="ask")
@click.argument("subject", type=click.Choice(_MEMORY_SUBJECTS))
@click.argument("query")
@click.option(
    "--session",
    "session_allowlist",
    multiple=True,
    help="Source to scope this query to; repeat for multiple. Fail-closed if omitted.",
)
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def memory_ask_cmd(
    subject: MemorySubject,
    query: str,
    session_allowlist: tuple[str, ...],
    as_json: bool,
) -> None:
    """Ask the memory store a question, scoped to an explicit session allowlist."""
    from .tools.memory import MemoryTool

    result = MemoryTool().run(
        Path.cwd(),
        operation="ask",
        subject=subject,
        query=query,
        session_allowlist=list(session_allowlist) or None,
    )
    _render_session_result(dict(result), as_json)


@memory_group.command(name="recall")
@click.argument("subject", type=click.Choice(_MEMORY_SUBJECTS))
@click.argument("query")
@click.option(
    "--session",
    "session_allowlist",
    multiple=True,
    help="Source to scope this query to; repeat for multiple. Fail-closed if omitted.",
)
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def memory_recall_cmd(
    subject: MemorySubject,
    query: str,
    session_allowlist: tuple[str, ...],
    as_json: bool,
) -> None:
    """Recall memory artifacts, scoped to an explicit session allowlist."""
    from .tools.memory import MemoryTool

    result = MemoryTool().run(
        Path.cwd(),
        operation="recall",
        subject=subject,
        query=query,
        session_allowlist=list(session_allowlist) or None,
    )
    _render_session_result(dict(result), as_json)


@memory_group.command(name="list")
@click.argument("subject", type=click.Choice(_MEMORY_SUBJECTS))
@click.argument("query")
@click.option(
    "--session",
    "session_allowlist",
    multiple=True,
    help="Source to scope this query to; repeat for multiple. Fail-closed if omitted.",
)
@click.option(
    "--include-archived",
    is_flag=True,
    help="Also return artifacts a `memory archive` call has excluded from normal recall.",
)
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def memory_list_cmd(
    subject: MemorySubject,
    query: str,
    session_allowlist: tuple[str, ...],
    include_archived: bool,
    as_json: bool,
) -> None:
    """List defended memory artifacts scoped to explicit sessions."""
    from .tools.memory import MemoryTool

    result = MemoryTool().run(
        Path.cwd(),
        operation="list",
        subject=subject,
        query=query,
        session_allowlist=list(session_allowlist) or None,
        include_archived=include_archived,
    )
    _render_session_result(dict(result), as_json)


@memory_group.command(name="write")
@click.argument("subject", type=click.Choice(_MEMORY_SUBJECTS))
@click.argument("source")
@click.option("--content", required=True, help="JSON-encoded content dict to persist.")
@click.option(
    "--symbol-ref", help="Optional 'path/to/file.py::Symbol' grounding reference."
)
@click.option(
    "--source-kind",
    type=click.Choice(["local_tool", "cross_tool_handoff", "human_derived"]),
    default="local_tool",
    help="Origin kind, determines the entry trust tier.",
)
@permission_options
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def memory_write_cmd(
    subject: MemorySubject,
    source: str,
    content: str,
    symbol_ref: str | None,
    source_kind: SourceKind,
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
    as_json: bool,
) -> None:
    """Write a memory artifact. Requires --allow-cache-write."""
    import json as _json

    from .tools.memory import MemoryTool

    result = MemoryTool().run(
        Path.cwd(),
        operation="write",
        subject=subject,
        content=_json.loads(content),
        source=source,
        symbol_ref=symbol_ref,
        source_kind=source_kind,
        permissions=_extract_permissions(
            allow_network=allow_network,
            allow_download=allow_download,
            allow_cache_write=allow_cache_write,
            allow_build=allow_build,
            allow_slow=allow_slow,
            allow_artifact_write=allow_artifact_write,
            allow_browser=allow_browser,
        ),
    )
    _render_session_result(dict(result), as_json)


@memory_group.command(name="promote")
@click.argument("subject", type=click.Choice(_MEMORY_SUBJECTS))
@click.argument("source")
@click.option("--content", required=True, help="JSON-encoded content dict to evaluate.")
@click.option(
    "--symbol-ref", help="Optional 'path/to/file.py::Symbol' grounding reference."
)
@click.option(
    "--source-kind",
    type=click.Choice(["local_tool", "cross_tool_handoff", "human_derived"]),
    default="local_tool",
    help="Origin kind, determines the entry trust tier.",
)
@click.option(
    "--user-stated", is_flag=True, help="This record was explicitly stated by the user."
)
@click.option(
    "--candidate-source",
    "candidate_sources",
    multiple=True,
    help="Corroborating source id; repeat for multiple.",
)
@permission_options
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def memory_promote_cmd(
    subject: MemorySubject,
    source: str,
    content: str,
    symbol_ref: str | None,
    source_kind: SourceKind,
    user_stated: bool,
    candidate_sources: tuple[str, ...],
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
    as_json: bool,
) -> None:
    """Evaluate and persist a candidate memory artifact for STATED promotion. Requires
    --allow-cache-write."""
    import json as _json

    from .tools.memory import MemoryTool

    result = MemoryTool().run(
        Path.cwd(),
        operation="promote",
        subject=subject,
        content=_json.loads(content),
        source=source,
        symbol_ref=symbol_ref,
        source_kind=source_kind,
        user_stated=user_stated,
        candidate_sources=list(candidate_sources) or None,
        permissions=_extract_permissions(
            allow_network=allow_network,
            allow_download=allow_download,
            allow_cache_write=allow_cache_write,
            allow_build=allow_build,
            allow_slow=allow_slow,
            allow_artifact_write=allow_artifact_write,
            allow_browser=allow_browser,
        ),
    )
    _render_session_result(dict(result), as_json)


@memory_group.command(name="maintain")
@click.option(
    "--task",
    type=click.Choice(
        ["promotion_sweep", "staleness_sweep", "skill_admission_check", "expiry_sweep"]
    ),
    required=True,
    help="Which maintenance sweep to run.",
)
@click.option(
    "--batch-size",
    type=int,
    default=500,
    show_default=True,
    help="Max rows processed in one sweep.",
)
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
@click.option(
    "--allow-cache-write", is_flag=True, help="Allow memory maintenance writes."
)
def memory_maintain_cmd(
    task: MaintenanceTask,
    batch_size: int,
    as_json: bool,
    allow_cache_write: bool,
) -> None:
    """Run a bounded memory-store maintenance sweep (Phase 62 §6.2)."""
    from .tools.memory import MemoryTool

    result = MemoryTool().run(
        Path.cwd(),
        operation="maintain",
        task=task,
        batch_size=batch_size,
        permissions=ExecutionPermissions(cache_write=allow_cache_write),
    )
    _render_session_result(dict(result), as_json)


# MC14 (Phase 63 §9.1): the 13 new memory operations added by MC02-MC12 (expand, link,
# related, consolidate, verify_attempt, prepare, resume, intent, recipe, plan_checks,
# last_success_diagnose, handoff, receive) share one request-shaped contract --
# `{schema_version, operation, code, data}` in/out -- so one generator builds every leaf
# instead of duplicating 13 near-identical commands. Each leaf routes through `_run_tool`
# (catalog CLI -> InvocationExecutor.execute), the same executor `make_tool_wrapper` uses
# for MCP, so CLI and MCP calls with an identical request produce byte-identical
# MemoryTool status/raw (excluding duration).
_MEMORY_OPERATION_HELP: dict[str, str] = {
    "expand": "Expand exact stored artifact bytes by id/version.",
    "link": "Add a versioned evidence edge between two artifacts. Requires --allow-cache-write.",
    "related": "Bounded, authorized relation traversal from one seed artifact.",
    "consolidate": "Consolidate duplicate episodes into one summary. Requires --allow-cache-write.",
    "verify_attempt": (
        "Run a real sandboxed check against a proposed patch. Requires "
        "--allow-cache-write, --allow-artifact-write, --allow-build plus declared checks."
    ),
    "prepare": "Prepare bounded repair evidence for a failing task; executes no commands.",
    "resume": "Resume bounded repair evidence for a failing task; executes no commands.",
    "intent": (
        "Create, confirm, supersede or check confirmed user intent. Mutating actions "
        "require --allow-cache-write."
    ),
    "recipe": (
        "Record, resolve, or record an outcome for a reusable recipe. record/outcome "
        "require --allow-cache-write."
    ),
    "plan_checks": "Rank required checks by evidence without dropping required membership.",
    "last_success_diagnose": "Compare a current failure to the last successful behavior.",
    "handoff": (
        "Prepare a bounded cross-tool memory handoff (action=prepare). Requires "
        "--allow-cache-write. dispatch/status report E_UNAVAILABLE (not yet implemented)."
    ),
    "receive": "Receive a bounded delta as a restricted handoff receiver.",
    "delete": (
        "Batch-delete memory artifacts by id/revision/scope (preview by default). "
        "Apply requires --allow-cache-write, plus --allow-artifact-write to also remove "
        "a Rush-owned handoff-packet blob."
    ),
    "edit": (
        "Edit one memory artifact's content under compare-and-swap (preview by default). "
        "Apply requires --allow-cache-write; demotes a promoted (STATED) artifact's trust "
        "back to an unpromoted candidate."
    ),
    "archive": (
        "Set or clear an archived marker on one memory artifact (preview by default, "
        "archived=true by default). Apply requires --allow-cache-write. Retains content "
        "and history; only excludes the row from normal recall."
    ),
}


def _memory_input_request(input_file: Path) -> dict[str, Any]:
    """MC14: parse a memory operation's JSON request body from --input FILE once, shared
    by every new memory CLI leaf (Phase 63 plan §9.1's per-operation request schema)."""
    try:
        data = json.loads(input_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"--input must be valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise click.ClickException("--input JSON must decode to an object.")
    return data


def _build_memory_operation_command(operation: str):
    """MC14: build one `rush memory <leaf>` Click command for `operation`."""

    def _cmd(
        input_file: Path,
        session_allowlist: tuple[str, ...],
        allow_network: bool,
        allow_download: bool,
        allow_cache_write: bool,
        allow_build: bool,
        allow_slow: bool,
        allow_artifact_write: bool,
        allow_browser: bool,
        as_json: bool,
    ) -> None:
        request = _memory_input_request(input_file)
        _run_tool(
            "memory",
            Path.cwd(),
            as_json=as_json,
            permissions=_extract_permissions(
                allow_network=allow_network,
                allow_download=allow_download,
                allow_cache_write=allow_cache_write,
                allow_build=allow_build,
                allow_slow=allow_slow,
                allow_artifact_write=allow_artifact_write,
                allow_browser=allow_browser,
            ),
            extra_kwargs={
                "operation": operation,
                "request": request,
                "session_allowlist": list(session_allowlist) or None,
            },
        )

    _cmd.__name__ = f"memory_{operation}_cmd"
    _cmd.__doc__ = _MEMORY_OPERATION_HELP[operation]
    _cmd = click.option(
        "--json", "as_json", is_flag=True, help="Print raw ToolResult JSON."
    )(_cmd)
    _cmd = permission_options(_cmd)
    _cmd = click.option(
        "--session",
        "session_allowlist",
        multiple=True,
        help=(
            "Source to scope this operation to; repeat for multiple. Only consulted by "
            "operations that read session_allowlist (expand/related/consolidate/prepare/"
            "resume); ignored otherwise."
        ),
    )(_cmd)
    _cmd = click.option(
        "--input",
        "input_file",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
        required=True,
        help=f"JSON file containing the {operation} request body (Phase 63 plan §9.1).",
    )(_cmd)
    return _cmd


for _memory_op, _memory_cli_name in (
    ("expand", "expand"),
    ("link", "link"),
    ("related", "related"),
    ("consolidate", "consolidate"),
    ("verify_attempt", "verify-attempt"),
    ("prepare", "prepare"),
    ("resume", "resume"),
    ("intent", "intent"),
    ("recipe", "recipe"),
    ("plan_checks", "plan-checks"),
    ("last_success_diagnose", "last-success-diagnose"),
    ("handoff", "handoff"),
    ("receive", "receive"),
    ("delete", "delete"),
    ("edit", "edit"),
    ("archive", "archive"),
):
    memory_group.command(name=_memory_cli_name)(
        _build_memory_operation_command(_memory_op)
    )
del _memory_op, _memory_cli_name


# P65-03.3 CONNECT (Phase 65 §3.2): CLI surface over `rush.workflows.projects` via
# `ProjectTool`. `select` binds a project to one explicit `--session` ID -- never a
# global cwd guessed by this interface -- matching the plan's "session-specific
# selection" contract.
@cli.group(name="project")
def project_group() -> None:
    """Register, discover, select, and configure Rush projects."""


@project_group.command(name="add")
@click.argument(
    "path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path("."),
)
@click.option("--name", default=None, help="Display name; defaults to the folder name.")
@permission_options
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def project_add_cmd(
    path: Path,
    name: str | None,
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
    as_json: bool,
) -> None:
    """Register an existing folder as a Rush project. Requires --allow-cache-write."""
    from .tools.project import ProjectTool

    result = ProjectTool().run(
        path,
        action="add",
        name=name,
        permissions=_extract_permissions(
            allow_network=allow_network,
            allow_download=allow_download,
            allow_cache_write=allow_cache_write,
            allow_build=allow_build,
            allow_slow=allow_slow,
            allow_artifact_write=allow_artifact_write,
            allow_browser=allow_browser,
        ),
    )
    _render_session_result(dict(result), as_json)


@project_group.command(name="list")
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def project_list_cmd(as_json: bool) -> None:
    """List every registered Rush project."""
    from .tools.project import ProjectTool

    result = ProjectTool().run(Path("."), action="list")
    _render_session_result(dict(result), as_json)


@project_group.command(name="show")
@click.argument("path", type=click.Path(path_type=Path), default=Path("."))
@click.option(
    "--project-id", default=None, help="Resolve by project ID instead of PATH."
)
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def project_show_cmd(path: Path, project_id: str | None, as_json: bool) -> None:
    """Show one registered project's identity, languages, and readiness."""
    from .tools.project import ProjectTool

    result = ProjectTool().run(path, action="show", project_id=project_id)
    _render_session_result(dict(result), as_json)


@project_group.command(name="snapshot")
@click.option("--project-id", default=None, help="Resolve by project ID.")
@click.option("--session", "session_id", default=None, help="Interface/session ID.")
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def project_snapshot_cmd(
    project_id: str | None, session_id: str | None, as_json: bool
) -> None:
    """P65-07.2: one shared evidence view -- overview, runs/coverage/findings, memory
    summary, token totals, Git summary, and categorized artifact references."""
    from .tools.project import ProjectTool

    result = ProjectTool().handle_request(
        {
            "schema_version": 1,
            "operation": "snapshot",
            "project": project_id,
            "session_id": session_id,
        }
    )
    _render_session_result(dict(result), as_json)


@project_group.command(name="artifacts")
@click.option("--project-id", default=None, help="Resolve by project ID.")
@click.option("--session", "session_id", default=None, help="Interface/session ID.")
@click.option(
    "--category",
    "categories",
    multiple=True,
    help="Keep only this artifact category; repeat for multiple.",
)
@click.option("--limit", type=int, default=100, help="Max items per list (1-1000).")
@click.option("--offset", type=int, default=0, help="Items to skip per list.")
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def project_artifacts_cmd(
    project_id: str | None,
    session_id: str | None,
    categories: tuple[str, ...],
    limit: int,
    offset: int,
    as_json: bool,
) -> None:
    """P65-07.2/.3: categorized, provenance-carrying artifact references (scan outputs,
    handoffs, memory) -- generic passthrough so a future output category is never
    invisible until a bespoke widget exists."""
    from .tools.project import ProjectTool

    result = ProjectTool().handle_request(
        {
            "schema_version": 1,
            "operation": "artifacts",
            "project": project_id,
            "session_id": session_id,
            "categories": list(categories) or None,
            "limit": limit,
            "offset": offset,
        }
    )
    _render_session_result(dict(result), as_json)


@project_group.command(name="select")
@click.argument("project_id")
@click.option(
    "--session",
    "session_id",
    required=True,
    help="Explicit interface/session ID to bind this project to; never a guessed cwd.",
)
@permission_options
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def project_select_cmd(
    project_id: str,
    session_id: str,
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
    as_json: bool,
) -> None:
    """Bind a registered project to one explicit session. Requires --allow-cache-write."""
    from .tools.project import ProjectTool

    result = ProjectTool().run(
        Path("."),
        action="select",
        project_id=project_id,
        session_id=session_id,
        permissions=_extract_permissions(
            allow_network=allow_network,
            allow_download=allow_download,
            allow_cache_write=allow_cache_write,
            allow_build=allow_build,
            allow_slow=allow_slow,
            allow_artifact_write=allow_artifact_write,
            allow_browser=allow_browser,
        ),
    )
    _render_session_result(dict(result), as_json)


@project_group.command(name="configure")
@click.argument("project_id")
@click.option(
    "--settings", default=None, help="JSON-encoded settings object to merge in."
)
@click.option(
    "--expected-revision",
    type=int,
    default=None,
    help="Current registry revision; required with --apply, ignored for preview.",
)
@click.option(
    "--plan-id",
    default=None,
    help="Plan ID from a prior preview run; required with --apply.",
)
@click.option(
    "--apply",
    is_flag=True,
    help="Apply --plan-id at --expected-revision instead of previewing.",
)
@permission_options
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def project_configure_cmd(
    project_id: str,
    settings: str | None,
    expected_revision: int | None,
    plan_id: str | None,
    apply: bool,
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
    as_json: bool,
) -> None:
    """Preview (default) or apply one project's scan/memory/agent settings.

    --apply requires --plan-id, --expected-revision, --allow-cache-write, and
    --allow-artifact-write.
    """
    import json as _json

    from .tools.project import ProjectTool

    result = ProjectTool().handle_request(
        {
            "schema_version": 1,
            "operation": "configure",
            "project": project_id,
            "settings": _json.loads(settings) if settings else None,
            "expected_revision": expected_revision,
            "apply": apply,
            "plan_id": plan_id,
            "allow_network": allow_network,
            "allow_download": allow_download,
            "allow_cache_write": allow_cache_write,
            "allow_build": allow_build,
            "allow_slow": allow_slow,
            "allow_artifact_write": allow_artifact_write,
            "allow_browser": allow_browser,
        }
    )
    _render_session_result(dict(result), as_json)


@project_group.command(name="create")
@click.argument("name")
@click.option(
    "--parent",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path("."),
    help="Parent directory for the new project folder.",
)
@click.option("--init-git", is_flag=True, help="Run `git init` in the new folder.")
@permission_options
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def project_create_cmd(
    name: str,
    parent: Path,
    init_git: bool,
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
    as_json: bool,
) -> None:
    """Create NAME at --parent and register it. Requires --allow-cache-write."""
    from .tools.project import ProjectTool

    result = ProjectTool().run(
        parent,
        action="create",
        name=name,
        init_git=init_git,
        permissions=_extract_permissions(
            allow_network=allow_network,
            allow_download=allow_download,
            allow_cache_write=allow_cache_write,
            allow_build=allow_build,
            allow_slow=allow_slow,
            allow_artifact_write=allow_artifact_write,
            allow_browser=allow_browser,
        ),
    )
    _render_session_result(dict(result), as_json)


@project_group.command(name="relink")
@click.argument("project_id")
@click.argument("path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--expected-revision",
    type=int,
    required=True,
    help="Current registry revision for this project; a stale value fails REVISION_CONFLICT.",
)
@permission_options
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def project_relink_cmd(
    project_id: str,
    path: Path,
    expected_revision: int,
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
    as_json: bool,
) -> None:
    """Repoint a registered project at its new PATH after a move.

    Requires --allow-cache-write and --allow-artifact-write.
    """
    from .tools.project import ProjectTool

    result = ProjectTool().handle_request(
        {
            "schema_version": 1,
            "operation": "relink",
            "project": project_id,
            "path": str(path),
            "expected_revision": expected_revision,
            "allow_network": allow_network,
            "allow_download": allow_download,
            "allow_cache_write": allow_cache_write,
            "allow_build": allow_build,
            "allow_slow": allow_slow,
            "allow_artifact_write": allow_artifact_write,
            "allow_browser": allow_browser,
        }
    )
    _render_session_result(dict(result), as_json)


# P65-04.3 CONNECT (Phase 65 §3.2): CLI surface over `rush.workflows.project_run`
# via `ScanTool`, matching `rush project`'s wiring mechanism (T204/T097/T013).
# `--full` builds a plan and immediately executes it (persisting an immutable
# run manifest, plan §6.1); without `--full` this only previews the plan.
# `--install` runs P65-02's provisioning plan for the project before scanning.
#
# P65-06.3 CONNECT (Phase 65 §3.2, F35): reconciles the P65-04 flat `rush
# scan --project ... --full` command into a group with that exact same
# default (no-subcommand) behavior, plus `handoff`/`rescan` subcommands over
# `ScanHandoffTool`/`rush.workflows.project_run.rescan_project_run` -- the
# default invocation and the two subcommands stay unambiguous because the
# group only runs its own body when no subcommand was given
# (`ctx.invoked_subcommand is None`).
@cli.group(name="scan", invoke_without_command=True)
@click.option(
    "--project", default=None, help="Registered project ID or filesystem path."
)
@click.option(
    "--full",
    is_flag=True,
    help="Execute the plan immediately, persisting a run manifest. "
    "Without this flag, only build and preview the plan.",
)
@click.option(
    "--install",
    is_flag=True,
    help="Apply the project's provisioning plan before scanning. "
    "Requires the relevant --allow-* grants.",
)
@permission_options
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
@click.pass_context
def scan_group(
    ctx: click.Context,
    project: str | None,
    full: bool,
    install: bool,
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
    as_json: bool,
) -> None:
    """Plan (and, with --full, execute) a full-project scan for --project, or
    use a scan subcommand (`handoff`, `rescan`)."""
    if ctx.invoked_subcommand is not None:
        return
    if not project:
        raise click.UsageError("--project is required for the default scan invocation.")
    _run_default_scan(
        project,
        full,
        install,
        allow_network=allow_network,
        allow_download=allow_download,
        allow_cache_write=allow_cache_write,
        allow_build=allow_build,
        allow_slow=allow_slow,
        allow_artifact_write=allow_artifact_write,
        allow_browser=allow_browser,
        as_json=as_json,
    )


def _run_default_scan(
    project: str,
    full: bool,
    install: bool,
    *,
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
    as_json: bool,
) -> None:
    from .tools.scan import ScanTool

    permissions = _extract_permissions(
        allow_network=allow_network,
        allow_download=allow_download,
        allow_cache_write=allow_cache_write,
        allow_build=allow_build,
        allow_slow=allow_slow,
        allow_artifact_write=allow_artifact_write,
        allow_browser=allow_browser,
    )

    if install:
        from .tools.setup_wizard import run_setup_wizard
        from .workflows.projects import resolve_project

        record = resolve_project(project)
        run_setup_wizard(
            Path(record["root"]),
            non_interactive=True,
            install=True,
            permissions=permissions,
        )

    scan_tool = ScanTool()
    plan_result = scan_tool.handle_request(
        {"schema_version": 1, "operation": "plan", "project": project, "full": True}
    )
    if not full or plan_result.get("status") != "ok":
        _render_session_result(dict(plan_result), as_json)
        return

    plan_data = (plan_result.get("raw") or {}).get("data") or {}
    run_result = scan_tool.handle_request(
        {
            "schema_version": 1,
            "operation": "run",
            "project": project,
            "plan_id": plan_data.get("plan_id"),
            "install": install,
            "allow_network": allow_network,
            "allow_download": allow_download,
            "allow_cache_write": allow_cache_write,
            "allow_build": allow_build,
            "allow_slow": allow_slow,
            "allow_artifact_write": allow_artifact_write,
            "allow_browser": allow_browser,
        }
    )
    if run_result.get("status") != "ok":
        _render_session_result(dict(run_result), as_json)
        return

    run_data = (run_result.get("raw") or {}).get("data") or {}
    status_result = scan_tool.handle_request(
        {
            "schema_version": 1,
            "operation": "status",
            "project": project,
            "run_id": run_data.get("run_id"),
        }
    )
    status_data = (status_result.get("raw") or {}).get("data") or {}

    combined_data = dict(run_data)
    combined_data["coverage"] = status_data.get("totals")
    combined_data["expansion_links"] = {
        "manifest_path": run_data.get("manifest_path"),
        "status_next_cursor": status_data.get("next_cursor"),
    }
    combined = dict(run_result)
    combined["raw"] = {**(run_result.get("raw") or {}), "data": combined_data}
    _render_session_result(combined, as_json)


@scan_group.command(name="handoff")
@click.argument("run_id")
@click.option(
    "--project", required=True, help="Registered project ID or filesystem path."
)
@click.option("--agent", "agent_id", required=True, help="Receiving agent ID.")
@click.option(
    "--finding",
    "finding_ids",
    multiple=True,
    help="Repeatable: hand off exactly this finding_id. Omit to hand off "
    "every unresolved finding on RUN_ID.",
)
@click.option(
    "--max-tokens", default=2048, type=int, help="Compact packet token budget."
)
@click.option("--max-bytes", default=8192, type=int, help="Compact packet byte budget.")
@permission_options
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def scan_handoff_cmd(
    run_id: str,
    project: str,
    agent_id: str,
    finding_ids: tuple[str, ...],
    max_tokens: int,
    max_bytes: int,
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
    as_json: bool,
) -> None:
    """Prepare a bounded agent handoff of RUN_ID's findings for --agent.

    Requires --allow-cache-write and --allow-artifact-write.
    """
    from .tools.scan_handoff import ScanHandoffTool

    permissions = _extract_permissions(
        allow_network=allow_network,
        allow_download=allow_download,
        allow_cache_write=allow_cache_write,
        allow_build=allow_build,
        allow_slow=allow_slow,
        allow_artifact_write=allow_artifact_write,
        allow_browser=allow_browser,
    )
    result = ScanHandoffTool().run(
        Path(project),
        action="prepare",
        run_id=run_id,
        agent_id=agent_id,
        finding_ids=tuple(finding_ids),
        max_tokens=max_tokens,
        max_bytes=max_bytes,
        permissions=permissions,
    )
    _render_session_result(dict(result), as_json)


# P65-06.3 CONNECT (Phase 65 §3.2, F35): `rush_scan.rescan(project,run_id)`
# (plan §6.1) lives on `ScanTool` (`src/rush/tools/scan.py`), outside this
# packet's allowed files -- calls `rush.workflows.project_run.
# rescan_project_run` directly rather than routing through a tool envelope
# that doesn't own this operation. The `rescan` operation is also reachable
# via `rush_scan`'s MCP `rescan` operation on `ScanTool` -- it is implemented,
# not a gap.
@scan_group.command(name="rescan")
@click.argument("run_id")
@click.option(
    "--project", required=True, help="Registered project ID or filesystem path."
)
@permission_options
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def scan_rescan_cmd(
    run_id: str,
    project: str,
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
    as_json: bool,
) -> None:
    """Re-execute RUN_ID's own staged plan against current source and
    compare fixed/persisting/new/unverified findings against RUN_ID."""
    from .workflows.project_run import ScanError, rescan_project_run

    permissions = _extract_permissions(
        allow_network=allow_network,
        allow_download=allow_download,
        allow_cache_write=allow_cache_write,
        allow_build=allow_build,
        allow_slow=allow_slow,
        allow_artifact_write=allow_artifact_write,
        allow_browser=allow_browser,
    )
    try:
        data = rescan_project_run(project, run_id, permissions=permissions)
    except ScanError as exc:
        _render_session_result(
            {
                "tool": "scan-rescan",
                "status": "error",
                "duration_ms": 0,
                "summary": f"scan rescan: {exc}",
                "findings": [],
                "raw": {
                    "error": {
                        "code": getattr(exc, "code", "INVALID_REQUEST"),
                        "message": str(exc),
                    }
                },
            },
            as_json,
        )
        return

    comparison = data["comparison"]
    summary = (
        f"scan rescan {run_id}: {len(comparison['resolved'])} resolved, "
        f"{len(comparison['persisting'])} persisting, "
        f"{len(comparison['new'])} new, "
        f"{len(comparison['unverified'])} unverified"
    )
    _render_session_result(
        {
            "tool": "scan-rescan",
            "status": "ok",
            "duration_ms": 0,
            "summary": summary,
            "findings": [],
            "raw": data,
        },
        as_json,
    )


@scan_group.command(name="cancel")
@click.argument("run_id")
@click.option(
    "--project", required=True, help="Registered project ID or filesystem path."
)
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def scan_cancel_cmd(run_id: str, project: str, as_json: bool) -> None:
    """Request cooperative cancellation of RUN_ID's in-flight scan.

    P65-08.3 CONNECT (Phase 65 §3.2, F35): `cancel`/`resume`
    (`rush.workflows.project_run.cancel_scan_run`/`resume_scan_run`) live
    outside `ScanTool` (`src/rush/tools/scan.py` is not in this packet's
    allowed files) -- calls the workflow function directly, exactly like
    `scan rescan` above.
    """
    from .workflows.project_run import ScanError, cancel_scan_run

    try:
        data = cancel_scan_run(project, run_id)
    except ScanError as exc:
        _render_session_result(
            {
                "tool": "scan-cancel",
                "status": "error",
                "duration_ms": 0,
                "summary": f"scan cancel: {exc}",
                "findings": [],
                "raw": {
                    "error": {
                        "code": getattr(exc, "code", "INVALID_REQUEST"),
                        "message": str(exc),
                    }
                },
            },
            as_json,
        )
        return

    _render_session_result(
        {
            "tool": "scan-cancel",
            "status": "ok",
            "duration_ms": 0,
            "summary": f"scan cancel {run_id}: requested",
            "findings": [],
            "raw": data,
        },
        as_json,
    )


@scan_group.command(name="resume")
@click.argument("run_id")
@click.option(
    "--project", required=True, help="Registered project ID or filesystem path."
)
@permission_options
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def scan_resume_cmd(
    run_id: str,
    project: str,
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
    as_json: bool,
) -> None:
    """Resume RUN_ID's most recent scan attempt as a new attempt.

    Retains every already-`executed` candidate's evidence and re-attempts
    everything else. Denies a stale resume if the project's source changed
    since the run's last attempt started. Requires --allow-cache-write and
    --allow-artifact-write (same write gate as `scan --full`/`scan rescan`).
    """
    from .workflows.project_run import ScanError, resume_scan_run

    permissions = _extract_permissions(
        allow_network=allow_network,
        allow_download=allow_download,
        allow_cache_write=allow_cache_write,
        allow_build=allow_build,
        allow_slow=allow_slow,
        allow_artifact_write=allow_artifact_write,
        allow_browser=allow_browser,
    )
    try:
        run = resume_scan_run(project, run_id, permissions=permissions)
    except ScanError as exc:
        _render_session_result(
            {
                "tool": "scan-resume",
                "status": "error",
                "duration_ms": 0,
                "summary": f"scan resume: {exc}",
                "findings": [],
                "raw": {
                    "error": {
                        "code": getattr(exc, "code", "INVALID_REQUEST"),
                        "message": str(exc),
                    }
                },
            },
            as_json,
        )
        return

    _render_session_result(
        {
            "tool": "scan-resume",
            "status": "ok",
            "duration_ms": 0,
            "summary": (
                f"scan resume {run_id}: new attempt {run.attempt_id}, "
                f"state={run.run_state}"
            ),
            "findings": [],
            "raw": run.to_dict(),
        },
        as_json,
    )


@cli.group(name="agent")
def agent_group() -> None:
    """Discover, connect, and diagnose local MCP-capable coding agents."""


@agent_group.command(name="list")
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def agent_list_cmd(as_json: bool) -> None:
    """List every known local agent and its current Rush registration state."""
    from .tools.agent_connection import AgentConnectionTool

    result = AgentConnectionTool().run(None, action="list")
    _render_session_result(dict(result), as_json)


@agent_group.command(name="connect")
@click.argument("agent_id")
@click.option(
    "--session",
    "session_id",
    required=True,
    help="Explicit session ID this connection's memory scope binds to.",
)
@click.option(
    "--project",
    "project_path",
    default=None,
    type=click.Path(path_type=Path),
    help="Project root for project-scoped memory; omit for user scope.",
)
@click.option(
    "--rush-binary", default=None, help="Absolute installed rush executable path."
)
@click.option(
    "--consent",
    is_flag=True,
    help="Allow capturing real tool observations for this scope.",
)
@click.option(
    "--acknowledge",
    is_flag=True,
    help="Confirm the agent actually picked up the connection; required for connected=true.",
)
@permission_options
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def agent_connect_cmd(
    agent_id: str,
    session_id: str,
    project_path: Path | None,
    rush_binary: str | None,
    consent: bool,
    acknowledge: bool,
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
    as_json: bool,
) -> None:
    """Register Rush with AGENT_ID and activate its scoped memory.

    Requires --allow-cache-write and --allow-artifact-write.
    """
    from .tools.agent_connection import AgentConnectionTool

    result = AgentConnectionTool().run(
        agent_id,
        action="connect",
        session_id=session_id,
        rush_binary=rush_binary,
        consent=consent,
        acknowledge=acknowledge,
        project_root=project_path,
        permissions=_extract_permissions(
            allow_network=allow_network,
            allow_download=allow_download,
            allow_cache_write=allow_cache_write,
            allow_build=allow_build,
            allow_slow=allow_slow,
            allow_artifact_write=allow_artifact_write,
            allow_browser=allow_browser,
        ),
    )
    _render_session_result(dict(result), as_json)


@agent_group.command(name="doctor")
@click.option(
    "--session", "session_id", default=None, help="Include this session's memory state."
)
@click.option(
    "--project",
    "project_path",
    default=None,
    type=click.Path(path_type=Path),
    help="Project root for project-scoped memory.",
)
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def agent_doctor_cmd(
    session_id: str | None, project_path: Path | None, as_json: bool
) -> None:
    """Diagnose every known agent's connection and memory state."""
    from .tools.agent_connection import AgentConnectionTool

    result = AgentConnectionTool().run(
        None, action="doctor", session_id=session_id, project_root=project_path
    )
    _render_session_result(dict(result), as_json)


# P65-10 (Phase 65 §3.2): one-command bootstrap over InstallTool, composing
# P65-01's release artifacts, P65-05's agent/memory readiness, and (only for
# an explicit --project/--create choice) P65-03's project registry + P65-02's
# provision-plan offer. Running this command at all is the explicit
# authorization for the writes it performs -- no separate --allow-* flags,
# matching the plan's own one-command invocation.
@cli.command(name="install")
@click.option(
    "--agents",
    type=click.Choice(["all", "none"]),
    default="all",
    help="Connect every detected local agent, or skip agent connection entirely.",
)
@click.option(
    "--memory",
    type=click.Choice(["on", "off"]),
    default="on",
    help="Grant connected agents consent to capture tool observations.",
)
@click.option(
    "--project",
    "project_path",
    default=None,
    help="Existing folder path or registered project ID to select; registers "
    "an unregistered folder first. Omit to choose later.",
)
@click.option(
    "--create",
    "create_name",
    default=None,
    help="Create a new project folder named NAME.",
)
@click.option(
    "--parent",
    "create_parent",
    type=click.Path(path_type=Path),
    default=None,
    help="Parent directory for --create; defaults to the current directory.",
)
@click.option("--init-git", is_flag=True, help="Run `git init` in a --create'd folder.")
@click.option(
    "--session",
    "session_id",
    default="install",
    help="Session ID this install's project selection and agent memory scope bind to.",
)
@click.option(
    "--version",
    "version",
    default=None,
    help="Pin an exact release version instead of latest.",
)
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def install_cmd(
    agents: str,
    memory: str,
    project_path: str | None,
    create_name: str | None,
    create_parent: Path | None,
    init_git: bool,
    session_id: str,
    version: str | None,
    as_json: bool,
) -> None:
    """Download/verify/install the release binary, connect agents, and optionally set up a project."""
    from .tools.install import InstallTool

    result = InstallTool().run(
        agents=agents,  # type: ignore[arg-type]
        memory=memory,  # type: ignore[arg-type]
        project=project_path,
        create_name=create_name,
        create_parent=create_parent,
        init_git=init_git,
        session_id=session_id,
        version=version,
        permissions=ExecutionPermissions(
            network=True, download=True, cache_write=True, artifact_write=True
        ),
    )
    _render_session_result(dict(result), as_json)
    if result["status"] != "ok":
        raise click.exceptions.Exit(1)


@cli.group(name="ship")
def ship_group() -> None:
    """Pre-flight release validation and hygiene vectors."""


@ship_group.command(name="clean")
@click.option(
    "--apply", is_flag=True, help="Delete unchanged registered Rush-owned artifacts."
)
@click.option(
    "--allow-artifact-write",
    is_flag=True,
    help="Grant permission to delete registered Rush-owned artifacts.",
)
def ship_clean_cmd(apply: bool, allow_artifact_write: bool) -> None:
    """Preview registered Rush-owned artifacts, or explicitly delete them."""
    from rush.tools.ship.cleaner import ScratchCleaner

    cleaner = ScratchCleaner()
    res = cleaner.clean(
        apply=apply,
        permissions=ExecutionPermissions(artifact_write=allow_artifact_write),
    )
    if res["status"] in {"error", "skipped", "warn"}:
        detail = res.get("error") or f"refused {res['refused_count']} artifacts"
        click.echo(f"Ship Clean: {res['status']}: {detail}", err=True)
        raise click.exceptions.Exit(1)
    mode = "Removed" if apply else "Would remove"
    click.echo(
        f"Ship Clean: {mode} "
        f"{res['removed_count'] if apply else res['preview_count']} items "
        f"({res['bytes_freed'] if apply else res['preview_bytes']} bytes)."
    )


@ship_group.command(name="env")
def ship_env_cmd() -> None:
    """Lint codebase environment variable usage against .env.example."""
    from rush.tools.ship.env_linter import EnvParityLinter

    linter = EnvParityLinter()
    res = linter.lint()
    if res["passed"]:
        click.echo(
            "Ship Env: All codebase environment variables declared in .env.example."
        )
    else:
        click.echo(
            f"Ship Env: FAIL - {len(res['missing_in_example'])} undeclared variables in .env.example:",
            err=True,
        )
        for var in res["missing_in_example"]:
            click.echo(f"  - {var}", err=True)
        sys.exit(1)


@ship_group.command(name="docs")
def ship_docs_cmd() -> None:
    """Audit documentation links and CLI reference parity."""
    from rush.tools.ship.docs_linter import DocsLinter

    linter = DocsLinter()
    res = linter.lint()
    if res["passed"]:
        click.echo(
            f"Ship Docs: Audited {res['checked_docs']} markdown docs. All links valid."
        )
    else:
        click.echo(
            f"Ship Docs: FAIL - {res['broken_links_count']} broken relative links found:",
            err=True,
        )
        for link in res["broken_links"]:
            click.echo(f"  - {link['file']} -> {link['target']}", err=True)
        sys.exit(1)


@ship_group.command(name="gate")
def ship_gate_cmd() -> None:
    """Evaluate 7-vector pre-flight release readiness gate."""
    from rush.tools.ship.cockpit import ShipCockpit

    cockpit = ShipCockpit()
    verdict = cockpit.evaluate_gate()
    status_str = "PASSED" if verdict.all_passed else "FAILED"
    click.echo(f"Ship Gate Verdict: {status_str} ({verdict.score_pct}% score)")
    for v in verdict.vectors:
        mark = "[OK]" if v.passed else "[FAIL]"
        click.echo(f"  {mark} {v.name.upper()}: {v.details} ({v.duration_ms}ms)")
    if not verdict.all_passed:
        sys.exit(1)


@ship_group.command(name="migration")
def ship_migration_cmd() -> None:
    """Lint database migrations for table-locking hazards."""
    from rush.tools.ship.migration_linter import MigrationLinter

    linter = MigrationLinter()
    res = linter.lint_migrations()
    if res["passed"]:
        click.echo("Ship Migration: No dangerous table locks detected.")
    else:
        click.echo(
            f"Ship Migration: FAIL - {res['findings_count']} migration hazards:",
            err=True,
        )
        for item in res["findings"]:
            click.echo(f"  {item['file']}: {', '.join(item['hazards'])}", err=True)
        sys.exit(1)


@ship_group.command(name="semver")
@click.argument("old_file", type=click.Path(exists=True, path_type=Path))
@click.argument("new_file", type=click.Path(exists=True, path_type=Path))
def ship_semver_cmd(old_file: Path, new_file: Path) -> None:
    """Check for breaking API signature changes between file versions."""
    from rush.tools.ship.semver_linter import SemverLinter

    linter = SemverLinter()
    old_code = old_file.read_text(encoding="utf-8", errors="ignore")
    new_code = new_file.read_text(encoding="utf-8", errors="ignore")
    breaking = linter.diff_apis(old_code, new_code)
    if not breaking:
        click.echo(
            f"Ship SemVer: Public API signatures compatible ({old_file.name} -> {new_file.name})."
        )
    else:
        click.echo(f"Ship SemVer: FAIL - {len(breaking)} breaking changes:", err=True)
        for b in breaking:
            click.echo(f"  - {b}", err=True)
        sys.exit(1)


@ship_group.command(name="pack")
def ship_pack_cmd() -> None:
    """Audit source tree for secret leaks before packaging."""
    from rush.tools.ship.package_linter import PackageLinter

    linter = PackageLinter()
    res = linter.lint()
    if res["passed"]:
        click.echo("Ship Pack: Source package clean of sensitive keys and env files.")
    else:
        click.echo(
            f"Ship Pack: FAIL - {res['leaks_count']} sensitive files detected:",
            err=True,
        )
        for leak in res["leaks"]:
            click.echo(f"  - {leak}", err=True)
        sys.exit(1)


# -----------------------------------------------------------------------------
# Phase 43: CCR, Grounding & Mistake Memory
# -----------------------------------------------------------------------------


@cli.group(name="context")
def context_group() -> None:
    """Context optimization, CCR retrieval, and mistake memory."""


@context_group.command(name="retrieve")
@click.argument("chunk_hash")
@click.option("--json", "as_json", is_flag=True, help="Emit canonical ToolResult JSON.")
def context_retrieve_cmd(chunk_hash: str, as_json: bool) -> None:
    """Retrieve a CCR chunk through the shared continuity contract."""
    from rush.tools.continuity import SessionContinuityTool

    _render_session_result(
        SessionContinuityTool().run(
            Path.cwd(), operation="context_retrieve", context_handle=chunk_hash
        ),
        as_json,
    )


@context_group.command(name="mistakes")
def context_mistakes_cmd() -> None:
    """List historical Git-revert mistake guardrails."""
    from rush.memory.mistake_miner import MistakeMiner

    miner = MistakeMiner()
    mistakes = miner.mine_mistakes()
    if not mistakes:
        click.echo("No historical mistake patterns found in git revert history.")
        return
    click.echo(f"Mistake Guardrails ({len(mistakes)}):")
    for m in mistakes:
        click.echo(f"  - [AVOID] {m.get('reverted_subject')}: {m.get('rationale')}")


@context_group.command(name="pack")
@click.option("--path", "-p", required=True, help="Target file path to pack.")
@click.option("--symbol", "-s", default="", help="Focus symbol to keep verbatim.")
@click.option("--budget", "-b", default=4000, type=int, help="Maximum token budget.")
@click.option(
    "--allow-cache-write",
    is_flag=True,
    help="Explicitly authorize local recovery-cache persistence.",
)
@click.option("--json", "as_json", is_flag=True, help="Emit canonical ToolResult JSON.")
def context_pack_cmd(
    path: str, symbol: str, budget: int, allow_cache_write: bool, as_json: bool
) -> None:
    """Pack bounded context through the shared continuity contract."""
    from rush.tools.continuity import SessionContinuityTool

    _render_session_result(
        SessionContinuityTool().run(
            Path.cwd(),
            operation="context_pack",
            context_path=path,
            target_symbol=symbol,
            token_budget=budget,
            permissions=ExecutionPermissions(cache_write=allow_cache_write),
        ),
        as_json,
    )


@context_group.command(name="align-prompt")
@click.option("--system", "-s", required=True, help="System prompt to align.")
def context_align_prompt_cmd(system: str) -> None:
    """Align prompt prefix above provider cache boundary (>=1024 tokens)."""
    from rush.token_economy.cache_aligner import CacheAligner

    aligner = CacheAligner()
    aligned = aligner.align_prompt(system)
    click.echo(
        f"Aligned tokens: {aligned['system']['aligned_tokens']} (Padded: {aligned['system']['padded']})"
    )


@context_group.command(name="gain")
def context_gain_cmd() -> None:
    """Launch the Rich terminal HUD displaying token compression and dollar savings."""
    from rush.token_economy.tui_gain import render_gain_dashboard

    render_gain_dashboard()


@context_group.command(name="persona")
@click.option(
    "--set",
    "set_persona",
    type=click.Choice(["terse", "default"]),
    default=None,
    help="Set agent response persona style.",
)
def context_persona_cmd(set_persona: str | None) -> None:
    """View or configure agent terse response persona style."""
    from rush.memory.preference_store import PreferenceStore

    prefs = PreferenceStore()
    if set_persona:
        prefs.set("persona_style", set_persona)
        click.echo(f"Persona style set to: {set_persona}")
    else:
        current = prefs.get("persona_style", "terse")
        click.echo(f"Current persona style: {current}")


@cli.command(name="blast-radius")
@click.option("--path", "-p", required=True, help="Changed file path to analyze.")
@click.option("--depth", "-d", default=5, type=int, help="Maximum traversal depth.")
def blast_radius_cmd(path: str, depth: int) -> None:
    """Analyze downstream transitive blast radius and affected tests."""
    from rush.tools.blast_radius import BlastRadiusAnalyzer

    analyzer = BlastRadiusAnalyzer()
    report = analyzer.analyze([Path(path)], max_depth=depth)
    click.echo(f"Blast Radius Impact: Risk={report.risk_score}")
    click.echo(
        f"  Affected Files ({len(report.affected_files)}): {', '.join(report.affected_files) or 'None'}"
    )
    click.echo(
        f"  Affected Routes ({len(report.affected_routes)}): {', '.join(report.affected_routes) or 'None'}"
    )
    click.echo(
        f"  Recommended Tests ({len(report.recommended_tests)}): {', '.join(report.recommended_tests) or 'None'}"
    )


@cli.command(name="arch-guard")
def arch_guard_cmd() -> None:
    """Evaluate codebase against architectural layer boundary rules."""
    from rush.tools.arch_guard import ArchGuard

    guard = ArchGuard()
    res = guard.evaluate_boundaries()
    if res["passed"]:
        click.echo("ArchGuard: All layer boundaries respected.")
    else:
        click.echo(
            f"ArchGuard: FAIL - {res['violations_count']} architectural boundary violations:",
            err=True,
        )
        for v in res["violations"]:
            click.echo(
                f"  {v['source_file']} ({v['source_layer']}) imports illegal layer {v['illegal_target_layer']}",
                err=True,
            )
        sys.exit(1)


@cli.command(name="test-heal")
@click.option("--target", "-t", required=True, help="Target test path to diagnose.")
@click.option(
    "--runs",
    "-r",
    default=20,
    type=click.IntRange(1, 1000),
    show_default=True,
    help="Number of perturbation runs.",
)
@click.option("--seed", default=0, type=int, show_default=True)
@click.option(
    "--dry-run/--apply",
    default=True,
    help="Propose a verified repair or explicitly apply it.",
)
@click.option(
    "--allow-slow", is_flag=True, help="Allow perturbation and verification runs."
)
@click.option(
    "--allow-artifact-write",
    is_flag=True,
    help="Allow isolated verification artifacts.",
)
@click.option(
    "--allow-build",
    is_flag=True,
    help="Allow builds only when target verification requires them.",
)
def test_heal_cmd(
    target: str,
    runs: int,
    seed: int,
    dry_run: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_build: bool,
) -> None:
    """Diagnose flaky test race conditions and suggest stabilization fixes."""
    from rush.tools.test_heal import TestHealer

    healer = TestHealer()
    res = healer(
        target,
        runs=runs,
        seed=seed,
        dry_run=dry_run,
        allow_slow=allow_slow,
        allow_artifact_write=allow_artifact_write,
        allow_build=allow_build,
    )
    if "error" in res or res.get("status") == "error":
        click.echo(
            f"Error: {res.get('error', res.get('summary', 'test healing failed'))}",
            err=True,
        )
        sys.exit(1)
    if res.get("status") == "skipped":
        click.echo(res.get("summary", res.get("diagnosis", "Test healing skipped")))
        return
    click.echo(f"Test Heal Diagnostic: {res['test_path']}")
    click.echo(
        f"  Runs: {res['runs']} (Passes: {res['passes']}, Failures: {res['failures']})"
    )
    click.echo(
        f"  Status: {'FLAKY' if res['is_flaky'] else 'DETERMINISTIC'} - {res['diagnosis']}"
    )
    if res["suggested_fix"]:
        click.echo(f"  Fix:\n{res['suggested_fix']}")


@cli.command(name="api-diff")
@click.option("--base", "-b", default="main", help="Base Git ref to compare against.")
def api_diff_cmd(base: str) -> None:
    """Detect breaking public API signature changes against base Git ref."""
    from rush.tools.api_diff import ApiDiffer

    differ = ApiDiffer()
    res = differ.diff_public_api(base_ref=base)
    if res["passed"]:
        click.echo(
            f"ApiDiff: No breaking public API changes detected against '{base}'."
        )
    else:
        click.echo(
            f"ApiDiff: FAIL - {res['breaking_changes_count']} breaking API changes against '{base}':",
            err=True,
        )
        for b in res["breaking_changes"]:
            click.echo(f"  {b['file']}: [{b['type']}] {b['details']}", err=True)
        sys.exit(1)


@cli.command(name="db-drift")
def db_drift_cmd() -> None:
    """Audit ORM models against SQL migrations to detect unmigrated schema drift."""
    from rush.tools.db_drift import DbDriftAuditor

    auditor = DbDriftAuditor()
    res = auditor.audit_drift()
    if res["passed"]:
        click.echo("DbDrift: All ORM models are synchronized with migrations.")
    else:
        click.echo(
            f"DbDrift: FAIL - {res['drift_count']} schema drift hazards found:",
            err=True,
        )
        for issue in res["drift_issues"]:
            click.echo(f"  {issue['model']}: {issue['details']}", err=True)
        sys.exit(1)


@cli.command(name="simplify")
@click.option(
    "--file",
    "-f",
    "file_path",
    required=True,
    help="File path to analyze for cognitive complexity.",
)
@click.option(
    "--max-complexity",
    "-m",
    default=10,
    type=int,
    help="Maximum allowed cognitive complexity score.",
)
def simplify_cmd(file_path: str, max_complexity: int) -> None:
    """Decompose high-complexity functions into clean helper sub-functions."""
    from rush.tools.simplify import ComplexityDecomposer

    decomposer = ComplexityDecomposer()
    res = decomposer.decompose_file(Path(file_path), max_complexity=max_complexity)
    if "error" in res:
        click.echo(f"Error: {res['error']}", err=True)
        sys.exit(1)
    if not res["needs_simplification"]:
        click.echo(
            f"Simplify: File '{file_path}' has clean complexity (<= {max_complexity})."
        )
    else:
        click.echo(
            f"Simplify: {res['complex_functions_count']} functions exceed complexity threshold ({max_complexity}):"
        )
        for c in res["candidates"]:
            click.echo(
                f"  Line {c['line']} - '{c['function']}' (complexity {c['complexity']}): {c['recommendation']}"
            )


@cli.command(name="strictify")
@click.option(
    "--file",
    "-f",
    "file_path",
    required=True,
    help="File path to analyze for untyped parameters.",
)
def strictify_cmd(file_path: str) -> None:
    """Synthesize runtime type guards for unvalidated function arguments."""
    from rush.tools.strictify import TypeSynthesizer

    synth = TypeSynthesizer()
    res = synth.audit_and_synthesize(Path(file_path))
    if "error" in res:
        click.echo(f"Error: {res['error']}", err=True)
        sys.exit(1)
    click.echo(
        f"Strictify: Found {res['untyped_count']} untyped parameters in '{file_path}':"
    )
    for u in res["untyped_arguments"]:
        click.echo(
            f"  Line {u['line']} - '{u['function']}' arg '{u['argument']}' -> Guard: {u['suggested_guard']}"
        )


@cli.command(name="trace")
def trace_cmd() -> None:
    """Scan codebase and specs to output requirement-to-test traceability matrix."""
    from rush.tools.trace import TraceScanner

    scanner = TraceScanner()
    res = scanner.scan_traceability()
    click.echo(
        f"Traceability Matrix: {res['total_requirements']} requirements tracked."
    )
    for item in res["matrix"]:
        click.echo(
            f"  {item['requirement']}: [{item['status']}] Impls={len(item['implementations'])} Tests={len(item['tests'])}"
        )


@cli.command(name="flight-recorder")
@click.option(
    "--replay", "-r", "session_id", default=None, help="Replay a specific session ID."
)
def flight_recorder_cmd(session_id: str | None) -> None:
    """Record and replay agent JSON-RPC sessions."""
    from rush.tools.flight_recorder import FlightRecorder

    recorder = FlightRecorder()
    if session_id:
        events = recorder.replay_session(session_id)
        click.echo(
            f"Flight Recorder: Replaying session '{session_id}' ({len(events)} events):"
        )
        for e in events:
            click.echo(f"  [{e['timestamp']}] {e['event_type']}: {e['payload']}")
    else:
        click.echo("Flight Recorder: Active (recording to .rush/sessions/flights/).")


@cli.command(name="swarm-merge")
@click.option("--base", required=True, help="Path to base file.")
@click.option("--ours", required=True, help="Path to ours file.")
@click.option("--theirs", required=True, help="Path to theirs file.")
def swarm_merge_cmd(base: str, ours: str, theirs: str) -> None:
    """Execute 3-way AST merge conflict resolution across concurrent agent changes."""
    from rush.tools.swarm_merge import SwarmMergeSolver

    solver = SwarmMergeSolver()
    b_code = Path(base).read_text(encoding="utf-8")
    o_code = Path(ours).read_text(encoding="utf-8")
    t_code = Path(theirs).read_text(encoding="utf-8")
    res = solver.merge_3way(b_code, o_code, t_code)
    if res["success"]:
        click.echo(
            f"SwarmMerge: Success - reconciled {res['functions_merged']} functions cleanly."
        )
    else:
        click.echo(f"SwarmMerge: FAIL - {res['error']}", err=True)
        sys.exit(1)


@cli.command(name="simulate-ci")
@click.option(
    "--workflow",
    "-w",
    default="ci.yml",
    help="GitHub Actions workflow file to emulate.",
)
def simulate_ci_cmd(workflow: str) -> None:
    """Emulate local GitHub Actions CI workflow execution."""
    from rush.tools.simulate_ci import SimulateCi

    sim = SimulateCi()
    res = sim.run_workflow(workflow_name=workflow)
    if res["passed"]:
        click.echo(
            f"SimulateCI: Workflow '{workflow}' passed ({res['steps_executed']} steps)."
        )
    else:
        click.echo(
            f"SimulateCI: FAIL at step '{res['failed_step']}': {res['error']}", err=True
        )
        sys.exit(1)


@cli.command(name="attest")
@click.argument(
    "path",
    type=click.Path(exists=True, path_type=Path),
    default=Path("."),
    required=False,
)
@click.option(
    "--artifact-path",
    "-a",
    type=click.Path(path_type=Path),
    default=None,
    help="Target artifact path to attest.",
)
@click.option(
    "--out",
    "-o",
    "output_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Contained output path for in-toto provenance JSON.",
)
@click.option(
    "--builder-id",
    default="https://rush-cli.org/builder/v1",
    help="Builder ID URI.",
)
@click.option(
    "--verify",
    "verify_envelope",
    type=click.Path(path_type=Path),
    default=None,
    help="Verify signed provenance envelope against policy.",
)
@click.option(
    "--trusted-root",
    "trusted_roots",
    multiple=True,
    help="Trusted root public key for verification.",
)
@click.option(
    "--allowed-signer",
    "allowed_signers",
    multiple=True,
    help="Allowed signer ID for verification.",
)
@permission_options
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def attest_cmd(
    path: Path,
    artifact_path: Path | None,
    output_path: Path | None,
    builder_id: str,
    verify_envelope: Path | None,
    trusted_roots: tuple[str, ...],
    allowed_signers: tuple[str, ...],
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
    as_json: bool,
) -> None:
    """Generate in-toto Statement v1 / SLSA Provenance v1 draft attestations."""
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
        "attest",
        path,
        as_json=as_json,
        permissions=perms,
        extra_kwargs={
            "artifact_path": str(artifact_path) if artifact_path else None,
            "output_path": str(output_path) if output_path else None,
            "builder_id": builder_id,
            "verify": str(verify_envelope) if verify_envelope else None,
            "trusted_roots": tuple(trusted_roots) if trusted_roots else (),
            "allowed_signers": tuple(allowed_signers) if allowed_signers else (),
        },
    )


@cli.command(name="license-matrix")
@click.argument(
    "path",
    type=click.Path(exists=True, path_type=Path),
    default=Path("."),
    required=False,
)
@permission_options
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def license_matrix_cmd(
    path: Path,
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
    as_json: bool,
) -> None:
    """Audit project dependencies for copyleft and license risks."""
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
        "license-matrix",
        path,
        as_json=as_json,
        permissions=perms,
    )


@cli.command(name="iam-audit")
@click.argument(
    "path",
    type=click.Path(exists=True, path_type=Path),
    default=Path("."),
    required=False,
)
@click.option(
    "--output",
    "-o",
    "output_policy_file",
    type=click.Path(path_type=Path),
    default=None,
    help="Contained output path for synthesized IAM policy JSON.",
)
@permission_options
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def iam_audit_cmd(
    path: Path,
    output_policy_file: Path | None,
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
    as_json: bool,
) -> None:
    """Audit AWS SDK calls in source code and synthesize least-privilege IAM policy."""
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
        "iam-audit",
        path,
        as_json=as_json,
        permissions=perms,
        extra_kwargs={
            "output_policy_file": (
                str(output_policy_file) if output_policy_file else None
            ),
        },
    )


@cli.command(name="hallu-guard")
def hallu_guard_cmd() -> None:
    """Audit codebase for hallucinated or phantom package imports."""
    from rush.tools.hallu_guard import HalluGuard

    guard = HalluGuard()
    res = guard.audit_codebase()
    if res["passed"]:
        click.echo(
            "HalluGuard: All AST imports grounded in installed packages or stdlib."
        )
    else:
        click.echo(
            f"HalluGuard: FAIL - {res['findings_count']} hallucinated import findings:",
            err=True,
        )
        for f in res["findings"]:
            click.echo(f"  {f['file']}: {', '.join(f['violations'])}", err=True)
        sys.exit(1)


@click.group(name="lock")
def lock_cmd_group() -> None:
    """Manage multi-agent swarm file locks with protected capability tokens."""


def _resolve_cli_capability(
    agent_id: str,
    capability_argv: str | None,
    descriptor: int | None,
    from_stdin: bool,
) -> tuple[Any, str]:
    """Resolve lock capability from protected input channels, strictly rejecting argv and env."""
    import os
    import sys

    # 1. Reject argv capability token
    if capability_argv is not None:
        click.echo(
            "Error: Passing capabilities via argv (--capability) is rejected. "
            "Capabilities must only be supplied via protected channels (stdin or descriptor).",
            err=True,
        )
        sys.exit(2)

    # 2. Reject environment variables
    env_cap = os.environ.get("RUSH_LOCK_CAPABILITY") or os.environ.get("CAPABILITY")
    if env_cap:
        click.echo(
            "Error: Passing capabilities via environment variables is rejected. "
            "Capabilities must only be supplied via protected channels (stdin or descriptor).",
            err=True,
        )
        sys.exit(2)

    from rush.mcp_mesh.capabilities import LockCapabilityInput, create_capability

    # 3. Read from descriptor if supplied
    if descriptor is not None:
        try:
            token = os.read(descriptor, 1024).decode("utf-8").strip()
            return (
                LockCapabilityInput(
                    token=token, agent_id=agent_id, channel_type="descriptor"
                ),
                token,
            )
        except OSError as exc:
            click.echo(
                f"Error: Failed to read capability from descriptor {descriptor}: {exc}",
                err=True,
            )
            sys.exit(2)

    # 4. Read from stdin if flag is set or stdin is not a tty
    if from_stdin or not sys.stdin.isatty():
        try:
            token = sys.stdin.read().strip()
            if token:
                return (
                    LockCapabilityInput(
                        token=token, agent_id=agent_id, channel_type="stdin"
                    ),
                    token,
                )
        except OSError as exc:
            click.echo(f"Error: Failed to read capability from stdin: {exc}", err=True)
            sys.exit(2)

    # 5. If no channel provided, generate new capability
    return create_capability(agent_id=agent_id, channel_type="stdin")


def _resolve_project_root(path: Path) -> Path:
    target_p = Path(path).resolve()
    curr = target_p if target_p.is_dir() else target_p.parent
    for parent in [curr, *curr.parents]:
        if (
            (parent / ".rush").exists()
            or (parent / "rush.toml").exists()
            or (parent / ".git").exists()
        ):
            return parent
    return curr


@lock_cmd_group.command(name="acquire")
@click.argument("path", type=click.Path(path_type=Path))
@click.option("--agent-id", required=True, help="Agent identifier.")
@click.option(
    "--capability",
    "capability_argv",
    default=None,
    help="FORBIDDEN: passing capabilities via argv is rejected.",
)
@click.option(
    "--descriptor",
    type=int,
    default=None,
    help="File descriptor to read capability token from.",
)
@click.option(
    "--stdin",
    "from_stdin",
    is_flag=True,
    help="Read capability token from stdin.",
)
@click.option(
    "--timeout",
    "timeout_s",
    type=float,
    default=5.0,
    help="Acquisition timeout in seconds.",
)
@click.option(
    "--ttl",
    "ttl_s",
    type=float,
    default=60.0,
    help="Lock time-to-live in seconds.",
)
def lock_acquire_cmd(
    path: Path,
    agent_id: str,
    capability_argv: str | None,
    descriptor: int | None,
    from_stdin: bool,
    timeout_s: float,
    ttl_s: float,
) -> None:
    """Acquire a coordination lock lease with protected caller capability."""
    from rush.mcp_mesh.lock_manager import MeshLockManager

    cap_input, _raw_token = _resolve_cli_capability(
        agent_id, capability_argv, descriptor, from_stdin
    )
    root = _resolve_project_root(path)
    mgr = MeshLockManager(project_root=root)
    ok = mgr.acquire(
        path, agent_id=agent_id, capability=cap_input, timeout_s=timeout_s, ttl_s=ttl_s
    )
    if ok:
        click.echo(f"Lock acquired for {path}")
        sys.exit(0)
    else:
        click.echo(f"Failed to acquire lock for {path}", err=True)
        sys.exit(1)


@lock_cmd_group.command(name="release")
@click.argument("path", type=click.Path(path_type=Path))
@click.option("--agent-id", required=True, help="Agent identifier.")
@click.option(
    "--capability",
    "capability_argv",
    default=None,
    help="FORBIDDEN: passing capabilities via argv is rejected.",
)
@click.option(
    "--descriptor",
    type=int,
    default=None,
    help="File descriptor to read capability token from.",
)
@click.option(
    "--stdin",
    "from_stdin",
    is_flag=True,
    help="Read capability token from stdin.",
)
def lock_release_cmd(
    path: Path,
    agent_id: str,
    capability_argv: str | None,
    descriptor: int | None,
    from_stdin: bool,
) -> None:
    """Release a coordination lock lease using protected caller capability."""
    from rush.mcp_mesh.lock_manager import MeshLockManager

    cap_input, _raw_token = _resolve_cli_capability(
        agent_id, capability_argv, descriptor, from_stdin
    )
    root = _resolve_project_root(path)
    mgr = MeshLockManager(project_root=root)
    ok = mgr.release(path, capability=cap_input, agent_id=agent_id)
    if ok:
        click.echo(f"Lock released for {path}")
        sys.exit(0)
    else:
        click.echo(f"Failed to release lock for {path}", err=True)
        sys.exit(1)


@lock_cmd_group.command(name="renew")
@click.argument("path", type=click.Path(path_type=Path))
@click.option("--agent-id", required=True, help="Agent identifier.")
@click.option(
    "--capability",
    "capability_argv",
    default=None,
    help="FORBIDDEN: passing capabilities via argv is rejected.",
)
@click.option(
    "--descriptor",
    type=int,
    default=None,
    help="File descriptor to read capability token from.",
)
@click.option(
    "--stdin",
    "from_stdin",
    is_flag=True,
    help="Read capability token from stdin.",
)
@click.option(
    "--ttl",
    "ttl_s",
    type=float,
    default=60.0,
    help="Lock time-to-live extension in seconds.",
)
def lock_renew_cmd(
    path: Path,
    agent_id: str,
    capability_argv: str | None,
    descriptor: int | None,
    from_stdin: bool,
    ttl_s: float,
) -> None:
    """Renew a coordination lock lease using protected caller capability."""
    from rush.mcp_mesh.lock_manager import MeshLockManager

    cap_input, _raw_token = _resolve_cli_capability(
        agent_id, capability_argv, descriptor, from_stdin
    )
    root = _resolve_project_root(path)
    mgr = MeshLockManager(project_root=root)
    ok = mgr.renew(path, capability=cap_input, ttl_s=ttl_s)
    if ok:
        click.echo(f"Lock renewed for {path}")
        sys.exit(0)
    else:
        click.echo(f"Failed to renew lock for {path}", err=True)
        sys.exit(1)


@lock_cmd_group.command(name="inspect")
@click.argument("path", type=click.Path(path_type=Path))
def lock_inspect_cmd(path: Path) -> None:
    """Inspect lock status for target resource without acquiring or modifying."""
    from rush.mcp_mesh.lock_manager import MeshLockManager

    root = _resolve_project_root(path)
    res = MeshLockManager.inspect(root, path)
    click.echo(json.dumps(res, indent=2))


if __name__ == "__main__":
    cli()
