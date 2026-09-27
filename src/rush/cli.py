"""Click CLI entrypoint — 34 canonical subcommands + `mcp serve`.

Architecture §6. Each subcommand calls the same ToolFn.__call__ that the
MCP tool calls (requirement C3 — single source of truth).
"""

from __future__ import annotations

import json
import os
import sys
import warnings
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, get_args

import click
from pydantic_settings.sources.utils import IncompleteFieldDefinitionWarning

# The MCP SDK's own pydantic-settings model has a `lifespan` field with an
# incomplete forward-reference annotation; this is third-party, not ours
# (matches the existing pytest filterwarnings entry in pyproject.toml and
# scripts/sync_docs.py's identical suppression). Must run before any local
# import below pulls in that model.
warnings.filterwarnings("ignore", category=IncompleteFieldDefinitionWarning)

from . import __version__
from .cli_support.catalog_commands import build_catalog_path_command
from .cli_support.options import (
    _extract_permissions,
    permission_options,
    result_view_options,
)
from .cli_support.rendering import (
    TargetPath,
    _path_param_defaulted,
    _render_session_result,
    _run_tool,
    cli_invocation_context,
    collection_route,
    echo,
    echo_json,
    echo_rows,
    exit_code_for,
    exit_with_result,
    secho,
    select_cli_target,
)
from .config import RushConfigError, load_config
from .delivery.compact import ViewOptions
from .invocation.models import InvocationError
from .invocation.targets import RootSelection, assert_contained, select_root
from .logging import setup_logging
from .memory.store import (
    MemorySubject,
    OwnerScope,
    OwnerScopeKind,
    legacy_owner_scope,
)
from .permissions import ExecutionPermissions
from .theme import FINDINGS_CAP
from .tools import ALL_TOOLS

if TYPE_CHECKING:
    from .memory.maintenance import MaintenanceTask
    from .tools.base import ToolResult
    from .tools.memory import SourceKind

_MEMORY_SUBJECTS = get_args(MemorySubject)
_JSON_LIST_HELP = "Print the full, untruncated list as JSON."

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


@click.group(
    cls=RushGroup,
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(__version__, "--version", "-V", message="%(version)s")
@click.option(
    "--log-level",
    envvar="RUSH_LOG_LEVEL",
    default="warn",
    type=click.Choice(["debug", "info", "warn", "error"], case_sensitive=False),
    help="Log verbosity (stderr NDJSON). Env: RUSH_LOG_LEVEL. Default: warn.",
)
@click.pass_context
def cli(ctx: click.Context, log_level: str) -> None:
    """rush — agentic code-quality tools for coding agents.

    \b
    Five tools: review, lint, format, test, security.
    Pairs well with `npx @nanonets/graft` for context-graph queries.
    """
    setup_logging(log_level)
    # T23: bare `rush` is exactly `rush status` for the invocation cwd.
    if ctx.invoked_subcommand is None:
        ctx.invoke(status_cmd)


@cli.command(name="status")
@click.argument("path", type=TargetPath(path_type=Path), required=False)
@click.option(
    "--session",
    "session_id",
    default=None,
    help="Show the project bound to this interface session (explicit PATH wins).",
)
@click.option(
    "--result",
    "result_handle",
    default=None,
    help="Read a stored result by handle, as `rush context retrieve --view`.",
)
@click.option(
    "--view",
    type=click.Choice(["result", "bytes"]),
    default=None,
    help="With --result: a findings page (result, default) or a byte slice.",
)
@click.option("--cursor", default=None, help="With --result: next_cursor.")
@click.option("--offset", type=int, default=None, help="With --result: start.")
@click.option("--limit", type=int, default=None, help="With --result: 1-50.")
@click.option("--max-bytes", "max_bytes", type=int, default=None, help="With --result.")
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def status_cmd(
    path: Path | None,
    session_id: str | None,
    result_handle: str | None,
    view: str | None,
    cursor: str | None,
    offset: int | None,
    limit: int | None,
    max_bytes: int | None,
    as_json: bool,
) -> None:
    """Show the project's status without changing anything."""
    from rush.tools.status import render_status, run_status_cli

    if path is not None and result_handle is None and not path.exists():
        from .invocation.executor import target_error_result

        exit_with_result(
            target_error_result(
                "status",
                "TARGET_NOT_FOUND",
                f"target not found: {path}",
                target=str(path),
                reason="target_not_found",
            ),
            as_json=as_json,
        )
    result = run_status_cli(
        path,
        session_id=session_id,
        result_handle=result_handle,
        view=view,
        cursor=cursor,
        offset=offset,
        limit=limit,
        max_bytes=max_bytes,
    )
    if result_handle is not None:
        _render_session_result(result, as_json)
    if as_json:
        exit_with_result(result, as_json=True)
    echo(render_status(result), nl=False)
    sys.exit(exit_code_for(result))


@collection_route("tools")
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
        echo(json.dumps(result, indent=2, default=str))
        return
    echo_rows(
        list(result["tools"].items()),
        lambda item: f"{item[0]}: {item[1]['state']} ({item[1]['reason']})",
        empty="no tools are declared in the catalog",
    )


@collection_route("steps")
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
        echo(json.dumps(result, indent=2, default=str))
        return
    echo_rows(
        result["steps"],
        lambda step: f"{step['tool']}: {step['state']} ({step['reason']})",
        empty="the selected profile plans no steps",
    )


def _benchmark_default_root() -> Path:
    """Return the durable user-local benchmark root, never a repository path.
    Resolved at call time (a Click callable default), never at import."""
    from .setup.provision import default_data_root

    return default_data_root() / "benchmarks"


def _benchmark_default_output() -> Path:
    return _benchmark_default_root() / "run"


def _benchmark_default_model_cache() -> Path:
    """Return the durable user-local model cache, never a repository path."""
    from .setup.provision import default_data_root

    return default_data_root() / "benchmark-model-cache"


@cli.group()
def benchmark() -> None:
    """Run and inspect durable local benchmark artifacts."""


@benchmark.command("run")
@click.option("--scenario", type=str, default=None, help="One declared scenario ID.")
@click.option("--all", "run_all", is_flag=True, help="Run every declared scenario.")
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=_benchmark_default_output,
    show_default="<data root>/benchmarks/run",
)
@click.option(
    "--model-cache",
    type=click.Path(path_type=Path),
    default=_benchmark_default_model_cache,
    show_default="<data root>/benchmark-model-cache",
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
    echo(
        f"Started {job['job_id']}; durable state: {output.parent / 'jobs' / (job['job_id'] + '.json')}"
    )


def _benchmark_json_files(root: Path, pattern: str) -> list[tuple[Path, Any]]:
    """Parsed `*.json` payloads under `root` (recursive for `**/`), skipping
    unparseable files; empty when `root` is absent."""
    if not root.is_dir():
        return []
    found = root.rglob(pattern[3:]) if pattern.startswith("**/") else root.glob(pattern)
    parsed: list[tuple[Path, Any]] = []
    for path in sorted(found):
        try:
            parsed.append((path, json.loads(path.read_text(encoding="utf-8"))))
        except json.JSONDecodeError:
            continue
    return parsed


@collection_route("jobs", "results")
@benchmark.command("status")
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=_benchmark_default_output,
    show_default="<data root>/benchmarks/run",
)
@click.option("--json", "as_json", is_flag=True, help=_JSON_LIST_HELP)
def benchmark_status(output: Path, as_json: bool) -> None:
    """Print durable job and scenario state without attaching to a worker."""
    ctx = click.get_current_context()
    explicit = (
        ctx.get_parameter_source("output") is not click.core.ParameterSource.DEFAULT
    )
    if explicit and not output.exists():
        # A typed output that does not exist is an invalid target, not an
        # empty history; the default output is absent until the first run.
        raise click.BadParameter(
            f"Path '{output}' does not exist.", param_hint="'--output'"
        )
    jobs = [
        {
            "job_id": payload.get("job_id", path.stem),
            "state": payload.get("state", "unknown"),
        }
        for path, payload in _benchmark_json_files(
            output.parent / "jobs", "benchmark-*.json"
        )
    ]
    results = [
        payload
        for _path, payload in _benchmark_json_files(output, "**/*.json")
        if isinstance(payload, dict)
        and "scenario_id" in payload
        and "outcome" in payload
    ]
    if as_json:
        echo_json({"jobs": jobs, "results": results})
        return
    echo_rows(
        jobs,
        lambda job: f"{job['job_id']}: {job['state']}",
        noun="jobs",
        empty="no benchmark jobs are recorded",
    )
    if output.is_dir() and not results:
        echo("No benchmark scenario results found.")
    echo_rows(
        results,
        lambda r: f"{r['scenario_id']}: {r['outcome']} ({r.get('duration_ms', 0)}ms)",
        noun="scenario results",
        empty="no benchmark scenario results are recorded",
    )


@benchmark.command("check")
@click.argument("path", type=TargetPath(path_type=Path), default=Path("."))
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
@result_view_options
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
    result_view: str | None,
    limit: int | None,
    max_bytes: int | None,
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
        view=ViewOptions(result_view, limit, max_bytes),
    )


# --- Subcommands (one per tool) --------------------------------------------


@cli.command()
@click.argument("path", type=TargetPath(path_type=Path))
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
@result_view_options
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
    result_view: str | None,
    limit: int | None,
    max_bytes: int | None,
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
        view=ViewOptions(result_view, limit, max_bytes),
    )


@cli.command()
@click.argument("path", type=TargetPath(path_type=Path))
@click.option(
    "--check", "check_only", is_flag=True, help="Only check; don't modify files."
)
@permission_options
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
@result_view_options
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
    result_view: str | None,
    limit: int | None,
    max_bytes: int | None,
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
        view=ViewOptions(result_view, limit, max_bytes),
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
@result_view_options
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
    result_view: str | None,
    limit: int | None,
    max_bytes: int | None,
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
        view=ViewOptions(result_view, limit, max_bytes),
    )


@cli.command(name="sbom")
@click.argument("path", type=TargetPath(path_type=Path))
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
@result_view_options
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
    result_view: str | None,
    limit: int | None,
    max_bytes: int | None,
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
        view=ViewOptions(result_view, limit, max_bytes),
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
@result_view_options
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
    result_view: str | None,
    limit: int | None,
    max_bytes: int | None,
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
        view=ViewOptions(result_view, limit, max_bytes),
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
@click.option(
    "--project",
    "project",
    default=None,
    help=(
        "Bind this server to one registered project (ID or registered root): its "
        "root anchors every relative path. Unknown projects fail at startup."
    ),
)
@click.option(
    "--session",
    "session",
    default=None,
    help="Default session_id for project and scan tools when a caller omits it.",
)
@click.option(
    "--profile",
    default=None,
    metavar="[core|full]",
    callback=lambda _ctx, _param, value: _validate_mcp_profile(value),
    help=(
        "Tool set: core (status, check, lint, review, security, test, memory) or "
        "full (every tool). Default: full. Ignored with --memory-session."
    ),
)
def serve(
    memory_session: str | None,
    project: str | None,
    session: str | None,
    profile: str | None,
) -> None:
    """Start the rush MCP server on stdio (for coding agents)."""
    import asyncio

    from .mcp import ServerBindingError, resolve_server_binding, run_stdio

    try:
        binding = resolve_server_binding(project, session)
    except ServerBindingError as exc:
        echo(f"rush mcp serve: {exc}", err=True)
        sys.exit(1)
    asyncio.run(run_stdio(memory_session, binding=binding, profile=profile))


# Mirrors `rush.mcp.PROFILES`; checked here so a bad value never imports
# (and so never constructs) any server.
_MCP_PROFILES = ("core", "full")


def _validate_mcp_profile(value: str | None) -> str | None:
    if value is not None and value not in _MCP_PROFILES:
        raise click.BadParameter(
            f"{value!r} is not a profile; valid profiles: {', '.join(_MCP_PROFILES)}"
        )
    return value


# --- Cache CLI commands ---------------------------------------------------


@cli.group()
def cache() -> None:
    """Manage Rush result cache."""


@cache.command(name="stats")
def cache_stats() -> None:
    """Display cache entry count, file size, and location."""
    from .cache import ResultCache

    # T10 (S10.6): read-only, anchored at the logical root; a missing DB is
    # reported with its path and never created.
    from .memory.store import MemoryStoreUnreadableError

    try:
        stats_data = ResultCache.stats_readonly(_logical_cache_db())
    except MemoryStoreUnreadableError as exc:
        raise click.ClickException(f"{exc.code}: {exc}") from exc
    echo(json.dumps(stats_data, indent=2))


@cache.command(name="clean")
def cache_clean() -> None:
    """Purge all cached results: .rush/cache.db entries and stored compact
    results in .rush/cache/ccr.db (context-pack chunks are kept)."""
    from .cache import ResultCache
    from .delivery.compact import purge_compact_results

    db = _logical_cache_db()
    count = ResultCache(db).clear() if db.is_file() else 0
    # T16 R16.8/finding 28: only T16 storage objects leave ccr.db; a missing
    # database is never created.
    purged, retained = purge_compact_results(db.parent.parent)
    echo(f"Purged {count} cached result(s).")
    echo(
        json.dumps(
            {
                "result_cache": count,
                "compact_results": purged,
                "context_packs_retained": retained,
            }
        )
    )


def _logical_cache_db() -> Path:
    """T10: the result cache under the logical root of the cwd, never the cwd."""
    from .invocation.targets import resolve_logical_root

    return resolve_logical_root(Path.cwd()) / ".rush" / "cache.db"


# --- Setup & Init CLI commands ---------------------------------------------


@cli.command(name="setup")
@click.argument("path", type=click.Path(exists=True, path_type=Path), default=Path("."))
@click.option(
    "--non-interactive/--interactive",
    "non_interactive",
    default=None,
    help=(
        "--non-interactive previews only; --interactive forces the review-and-confirm "
        "flow (needs a terminal on stdin). Default: interactive when stdin and stdout "
        "are terminals, otherwise preview only."
    ),
)
@click.option(
    "--install",
    is_flag=True,
    help=(
        "Accepted for compatibility: engine provisioning is always part of the "
        "reviewed setup plan."
    ),
)
@click.option(
    "--apply",
    "apply_",
    is_flag=True,
    help="Apply a saved setup review without prompting (with --yes, --plan-file, --plan-id).",
)
@click.option("--yes", is_flag=True, help="Confirm a non-interactive --apply.")
@click.option(
    "--plan-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Saved JSON output of `rush setup PATH --json`.",
)
@click.option(
    "--plan-id",
    help="The saved plan's setup_plan_id (or a T24 review's review_id).",
)
@click.option(
    "--agent",
    "host",
    type=click.Choice(["claude", "codex"]),
    default=None,
    help="The LLM CLI to connect to this project (Claude Code or Codex CLI).",
)
@click.option(
    "--save-plan",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help=(
        "Save the complete reviewed setup plan here (needs --allow-artifact-write) "
        "and print the exact --apply command. Saving applies nothing."
    ),
)
@click.option(
    "--install-guidance",
    is_flag=True,
    help="Also write the Rush instruction block into CLAUDE.md/AGENTS.md.",
)
@click.option(
    "--enable-agent-hooks",
    is_flag=True,
    help="Also enable the host's Rush hooks.",
)
@click.option(
    "--verify-host",
    is_flag=True,
    help=(
        "Launch the host once to verify it calls Rush for this project (uses the "
        "network and model tokens on your host account)."
    ),
)
@permission_options
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Print the setup preview or result as JSON; JSON output never prompts.",
)
def setup_cmd(
    path: Path,
    non_interactive: bool | None,
    install: bool,
    apply_: bool,
    yes: bool,
    plan_file: Path | None,
    plan_id: str | None,
    host: str | None,
    save_plan: Path | None,
    install_guidance: bool,
    enable_agent_hooks: bool,
    verify_host: bool,
    allow_network: bool,
    allow_download: bool,
    allow_cache_write: bool,
    allow_build: bool,
    allow_slow: bool,
    allow_artifact_write: bool,
    allow_browser: bool,
    as_json: bool,
) -> None:
    """Preview project setup (config, registration, engines) and apply it after consent."""
    from .tools.setup_wizard import render_setup_result, run_setup_command

    del install  # compatibility flag; provisioning is always reviewed
    permissions = _extract_permissions(
        allow_network=allow_network,
        allow_download=allow_download,
        allow_cache_write=allow_cache_write,
        allow_build=allow_build,
        allow_slow=allow_slow,
        allow_artifact_write=allow_artifact_write,
        allow_browser=allow_browser,
    )
    payload, code = run_setup_command(
        path.resolve(),
        non_interactive=non_interactive,
        apply=apply_,
        yes=yes,
        plan_file=plan_file,
        plan_id=plan_id,
        permissions=permissions,
        as_json=as_json,
        stdin_tty=sys.stdin.isatty(),
        stdout_tty=sys.stdout.isatty(),
        host=host,
        save_plan=save_plan,
        install_guidance=install_guidance,
        enable_hooks=enable_agent_hooks,
        verify_host=verify_host,
    )
    echo(
        json.dumps(payload, indent=2, default=str)
        if as_json
        else render_setup_result(payload)
    )
    if code == 130:
        echo("rush setup: interrupted; nothing was changed", err=True)
    sys.exit(code)


@cli.command(name="init")
@click.argument("path", type=click.Path(exists=True, path_type=Path), default=Path("."))
@click.option("--force", is_flag=True, help="Overwrite existing rush.toml file.")
def init_cmd(path: Path, force: bool) -> None:
    """Generate a starter rush.toml configuration tailored to the repository."""
    from .tools.init_config import generate_initial_config

    root = path.resolve()
    target_cfg = (root if root.is_dir() else root.parent) / "rush.toml"
    if target_cfg.is_file() and not force:
        echo(f"rush.toml already exists at {target_cfg}. Pass --force to overwrite.")
        sys.exit(1)

    cfg_content = generate_initial_config(root)
    from .safety.redactor import sanitize_value

    target_cfg.write_text(sanitize_value(cfg_content).value, encoding="utf-8")
    echo(f"Created rush.toml at {target_cfg}")


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
            echo(f"Valid configuration loaded from {cfg.source}")
        else:
            echo("No rush.toml found; using default built-in configuration.")
    except Exception as exc:  # noqa: BLE001
        echo(f"Configuration error: {exc}", err=True)
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
    # T8: the suite walks the user's own input once from the invocation cwd.
    result = run_workflow_suite(
        suite=suite,
        path=path,
        permissions=perms,
        fail_fast=fail_fast,
        original_requested_targets=None if _path_param_defaulted() else (str(path),),
        invocation_start_cwd=Path.cwd(),
    )
    if as_json:
        echo(json.dumps(result, indent=2))
    else:
        _echo_suite_human(result, suite.name)
    sys.exit(exit_code_for(result["status"]))


def _suite_child_line(item: tuple[int, Mapping[str, Any]]) -> str:
    index, child = item
    line = (
        f"  {index}. {child.get('tool')!s:<9} {child.get('status')!s:<7} "
        f"{child.get('summary') or ''}"
    )
    cause = (child.get("execution") or {}).get("cause")
    return f"{line} ({cause})" if cause else line


def _echo_suite_human(result: Mapping[str, Any], suite_name: str) -> None:
    """The status line and summary, then one line per step (T17 S17.4):
    number, step, status and summary, plus the cause of a step that did not
    execute (not_run/cancelled)."""
    status = result.get("status")
    status_color = (
        "green" if status == "ok" else ("yellow" if status == "warn" else "red")
    )
    secho(f"[{suite_name.upper()}] Status: {status}", fg=status_color, bold=True)
    echo(result.get("summary", ""))
    children = (result.get("metadata") or {}).get("children") or []
    echo_rows(
        list(enumerate(children, start=1)),
        _suite_child_line,
        noun="steps",
        empty="the suite ran no steps",
    )
    echo_rows(
        result.get("findings") or [],
        lambda f: f"  - [{f.get('severity', 'info')}] {f.get('message', '')}",
        cap=FINDINGS_CAP,
        noun="findings",
        empty="no step reported a finding",
    )


def _run_check_cli(
    path: Path,
    permissions: ExecutionPermissions,
    fail_fast: bool,
    view: ViewOptions,
    as_json: bool,
) -> None:
    """T17: `rush check` runs the shared `CheckTool`. The suite walks `path`
    once from the invocation cwd (T8), so a rejected input is each step's
    error child; only the compact view selects the root first, to store the
    full result under it."""
    from .delivery import compact
    from .safety.redactor import sanitize_value
    from .tools.check import CheckTool

    anchor = Path.cwd()
    original = None if _path_param_defaulted() else (str(path),)

    def run() -> Any:
        return CheckTool().run(
            path,
            permissions=permissions,
            fail_fast=fail_fast,
            original_requested_targets=original,
            invocation_start_cwd=anchor,
        )

    def prepare() -> compact.Prepared | dict[str, Any]:
        if not view.compact:
            return anchor, run
        try:
            return select_cli_target(path, anchor=anchor).root, run
        except InvocationError:
            return run()

    result = compact.deliver(
        "check",
        view,
        cache_write=permissions.cache_write,
        prepare=prepare,
        serialize=compact.cli_size,
    )
    clean = sanitize_value(result).value
    if as_json:
        echo(json.dumps(clean, indent=2, default=str))
    else:
        _echo_suite_human(clean, "check")
    sys.exit(exit_code_for(result))


@collection_route("metadata.children", "findings")
@cli.command(name="check")
@click.argument("path", type=TargetPath(path_type=Path), default=Path("."))
@click.option(
    "--fail-fast/--no-fail-fast",
    default=False,
    help="Stop at the first failing step; later steps are reported as not run.",
)
@permission_options
@result_view_options
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
    result_view: str | None,
    limit: int | None,
    max_bytes: int | None,
    as_json: bool,
) -> None:
    """Run the check suite: format (check-only), lint, typecheck, dead, slop, test.

    Every step runs and is reported by default; the test step runs project
    test code and needs --allow-build."""
    perms = _extract_permissions(
        allow_network=allow_network,
        allow_download=allow_download,
        allow_cache_write=allow_cache_write,
        allow_build=allow_build,
        allow_slow=allow_slow,
        allow_artifact_write=allow_artifact_write,
        allow_browser=allow_browser,
    )
    _run_check_cli(
        path, perms, fail_fast, ViewOptions(result_view, limit, max_bytes), as_json
    )


@collection_route("metadata.children", "findings")
@cli.command(name="audit")
@click.argument("path", type=TargetPath(path_type=Path), default=Path("."))
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


@collection_route("metadata.children", "findings")
@cli.command(name="gate")
@click.argument("path", type=TargetPath(path_type=Path), default=Path("."))
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
    # T8: one ROOT-ENTRY walk from the invocation cwd, before anything is
    # watched or run; every later trigger reuses its selection.
    invocation_start_cwd = Path.cwd()
    original = None if _path_param_defaulted() else (str(path),)
    try:
        selection = select_cli_target(path, anchor=invocation_start_cwd)
    except InvocationError as exc:
        echo(str(exc), err=True)
        sys.exit(2)

    def on_change_handler(changed_paths: list[Path]) -> None:
        echo(
            f"\n[WATCH] Changes detected in {len(changed_paths)} file(s). Triggering evaluation..."
        )
        if tool_name:
            tools_map = {t.name: t for t in ALL_TOOLS}
            t = tools_map.get(tool_name)
            if t:
                from .invocation import InvocationExecutor

                try:
                    context = cli_invocation_context(
                        t.name, selection, original=original, permissions=perms
                    )
                except RushConfigError as exc:
                    echo(str(exc), err=True)
                    return
                executor = InvocationExecutor()
                executor.register(t.name, t.__call__)
                res = executor.execute(context)
                echo(res.get("summary", "Done."))
        else:
            suite = suite_map.get(suite_name, CHECK_SUITE)
            res = run_workflow_suite(
                suite=suite,
                path=path,
                permissions=perms,
                fail_fast=False,
                original_requested_targets=original,
                invocation_start_cwd=invocation_start_cwd,
            )
            echo(res.get("summary", "Done."))

    watcher = FileWatcher(
        root=selection.target, debounce_ms=debounce_ms, on_change=on_change_handler
    )
    watcher.watch_blocking()


# --- Interactive TUI & Web Dashboard commands ------------------------------


def _stdout_is_tty() -> bool:
    """Test seam (P69-06a) -- production checks the real stream; tests
    monkeypatch this instead of fighting Click's `CliRunner` output capture,
    which never reports as a tty."""
    return sys.stdout.isatty()


@cli.command(name="ui")
@click.argument("paths", nargs=-1, type=click.Path(exists=True, path_type=Path))
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    default=False,
    help=(
        "Print each project's check-suite result as JSON and exit, "
        "instead of opening the interactive interface."
    ),
)
@permission_options
def ui_cmd(
    paths: tuple[Path, ...],
    json_output: bool,
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
    when none are given. The interface starts immediately and runs each
    project's initial check suite as a background job it attaches to,
    rather than blocking startup on it. With `--json`, or when stdout is
    not a terminal, prints each project's check-suite result and exits
    instead of opening the interface.
    """
    from .tui import ProjectSeed, default_scan_actions, run_interactive_tui

    perms = _extract_permissions(
        allow_network=allow_network,
        allow_download=allow_download,
        allow_cache_write=allow_cache_write,
        allow_build=allow_build,
        allow_slow=allow_slow,
        allow_artifact_write=allow_artifact_write,
        allow_browser=allow_browser,
    )
    # T8 (5.1)/(5.4): one ROOT-ENTRY walk per input from the invocation cwd,
    # in place of `p.resolve()`; with no paths the invocation cwd is the
    # lexical path and the original input is unavailable (None). A rejected
    # input fails before any seed is built or any suite runs.
    anchor = Path.cwd()
    inputs: list[str | None] = [str(p) for p in paths] or [None]
    entries: list[tuple[str | None, RootSelection]] = []
    for typed in inputs:
        try:
            selected = select_root("." if typed is None else typed, anchor=anchor)
            assert_contained(selected)
        except InvocationError as exc:
            echo(str(exc), err=True)
            sys.exit(2)
        entries.append((typed, selected))

    if json_output or not _stdout_is_tty():
        from .workflows.suites import CHECK_SUITE, run_workflow_suite

        snapshots = []
        for raw, selection in entries:
            res = run_workflow_suite(
                suite=CHECK_SUITE,
                path=selection.lexical,
                permissions=perms,
                original_requested_targets=None if raw is None else (raw,),
                invocation_start_cwd=anchor,
            )
            snapshots.append(
                {
                    "project": selection.target.name or str(selection.target),
                    "path": str(selection.target),
                    "result": res,
                }
            )
        if json_output:
            echo(json.dumps(snapshots))
        else:
            for snap in snapshots:
                result = snap["result"] if isinstance(snap["result"], dict) else {}
                echo(f"{snap['project']}: {result.get('summary', 'done')}")
        return

    seeds = [
        ProjectSeed(
            name=selection.target.name or str(selection.target),
            root=selection.target,
            lexical_path=selection.lexical,
            original_input=raw,
        )
        for raw, selection in entries
    ]
    run_interactive_tui(seeds, actions=default_scan_actions(permissions=perms))


def _dashboard_descriptor_path(server_id: str) -> Path:
    from .setup.provision import default_data_root

    return default_data_root() / "dashboard" / f"{server_id}.json"


def _check_windows_data_dir_acl(directory: Path) -> bool:
    """Best-effort check (via `icacls`) that `directory` grants no access
    to a broad principal (Everyone/Authenticated Users/BUILTIN\\Users).
    Fails closed: an unparseable or failing check counts as not private."""
    import subprocess

    try:
        result = subprocess.run(
            ["icacls", str(directory)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, ValueError):
        return False
    if result.returncode != 0:
        return False
    broad_principals = ("Everyone", "BUILTIN\\Users", "Authenticated Users")
    return not any(
        principal in line
        for line in result.stdout.splitlines()
        for principal in broad_principals
    )


def _write_dashboard_descriptor(ctx: Any) -> Path:
    """Private per-instance descriptor for `--reconnect` discovery (plan
    3.7): schema_version, PID, start nonce, bound port, control capability.
    Never a project artifact or browser response. POSIX 0700/0600 modes;
    on Windows the data directory's ACL is checked before the control
    capability is persisted -- launch fails with a privacy error instead
    of silently skipping descriptor creation."""
    from rush.runtime.filesystem import atomic_write_bytes

    path = _dashboard_descriptor_path(ctx.server_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        os.chmod(path.parent, 0o700)
    elif os.name == "nt":
        if not _check_windows_data_dir_acl(path.parent):
            raise click.ClickException(
                "DASHBOARD_DESCRIPTOR_PRIVACY: cannot confirm the dashboard "
                "data directory is private to this user on this filesystem; "
                "refusing to persist the reconnect control capability."
            )
    else:
        return path
    payload = {
        "schema_version": 1,
        "pid": ctx.pid,
        "start_nonce": ctx.start_nonce,
        "bound_host": ctx.bound_host,
        "bound_port": ctx.bound_port,
        "control_capability": ctx.auth.control_capability,
    }
    written = atomic_write_bytes(
        path.parent, Path(path.name), json.dumps(payload).encode("utf-8")
    )
    if os.name == "posix":
        os.chmod(written, 0o600)
    return written


def _remove_dashboard_descriptor(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def _check_descriptor_liveness(descriptor: dict[str, Any]) -> bool | None:
    """Probe whether a descriptor's own recorded server is still the
    process actually listening at that address. Returns True (live,
    identity matches), False (reachable but a different process/pid now
    owns that address -- proven stale ownership), or None (unreachable or
    unparseable -- unknown, never treated as proof of staleness)."""
    import urllib.error
    import urllib.request

    base_url = f"http://{descriptor.get('bound_host')}:{descriptor.get('bound_port')}"
    request = urllib.request.Request(
        f"{base_url}/api/control/health",
        headers={"X-Rush-Control": descriptor.get("control_capability", "")},
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            if response.status != 200:
                return None
            body = json.loads(response.read())
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return body.get("pid") == descriptor.get("pid") and body.get(
        "start_nonce"
    ) == descriptor.get("start_nonce")


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
    for candidate in candidates:
        try:
            descriptor = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        liveness = _check_descriptor_liveness(descriptor)
        if liveness is True:
            return candidate
        if liveness is False:
            # Reachable, but a different process now owns this address --
            # proven stale ownership, safe to remove.
            _remove_dashboard_descriptor(candidate)
    return None


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
        # Never delete on a bare exception here -- only a health check that
        # actually connects and proves a mismatched owner (see
        # `_check_descriptor_liveness`) establishes stale ownership.
        raise click.ClickException(
            f"dashboard server is no longer reachable: {exc}"
        ) from exc

    launch_url = f"{base_url}/#token={new_token}"
    if json_output:
        echo(json.dumps({"ready": True, "url": launch_url}))
    else:
        echo(f"Reconnected: {launch_url}")
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

    from .dashboard.server import (
        bootstrap_launch_url,
        capture_initial_scan_provenance,
        create_dashboard_server,
        publish_check_suite_scan,
    )
    from .workflows.project_run import _capture_artifact_snapshots
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

    # T8 (4)(d): one ROOT-ENTRY walk in place of `path.resolve()`, rejected
    # before registration, server start, or any scan; the registered root is
    # the only root used after it.
    anchor = Path.cwd()
    original = None if _path_param_defaulted() else (str(path),)
    try:
        selection = select_root(str(path), anchor=anchor)
        assert_contained(selection)
    except InvocationError as exc:
        echo(str(exc), err=True)
        sys.exit(2)
    record = register_project(selection.target)
    registered_root = Path(record.root)
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
        echo(json.dumps({"ready": True, "url": launch_url, "server_id": ctx.server_id}))
    else:
        echo(f"Dashboard running at: {launch_url}")
        echo("Press Ctrl+C to stop.")

    if not no_open:
        try:
            webbrowser.open(launch_url)
        except Exception:  # noqa: BLE001, S110
            pass

    def _run_initial_scan() -> None:
        # P69-03k: capture the pre-execution provenance header before a
        # single tool runs -- the same guarantee execute_scan/resume_scan_run/
        # rescan_project_run already give via _write_attempt_header.
        run_id, attempt_id = capture_initial_scan_provenance(
            registered_root, record.project_id
        )
        # P69-03m: this launch's ordering number is allocated here, at
        # acceptance, before a single tool runs -- this bare thread is outside
        # ScanRunTracker and can finish after a faster user-requested scan, so
        # a publish-time number would let it overwrite the newer result.
        scan_generation = ctx.mutations.allocate_scan_generation(record.project_id)
        # P69-06f: this launch is dashboard-owned (it runs inside the
        # dashboard server's own process) -- thread the server's real
        # owner-instance id and this run's minted run_id through, or every
        # subprocess this scan spawns records no owner and Detach's
        # force-exit/recovery reap path (subsection h/i) finds nothing to act
        # on for it, while silently working for every other launch path.
        # M12 Fix item 2: CHECK_SUITE per-child capture parity -- snapshot
        # each child's declared artifact bytes the moment it completes,
        # before the next tool in the suite can run and physically
        # overwrite the same path (mirrors dashboard/server.py's
        # `_dispatch_check_suite`).
        check_suite_snapshots: dict[str, dict[str, dict[str, object]]] = {}

        def _on_tool_complete(child: ToolResult) -> None:
            tool_name = str(child.get("tool") or "")
            if tool_name:
                check_suite_snapshots[tool_name] = _capture_artifact_snapshots(
                    registered_root, run_id, attempt_id, tool_name, child
                )

        aggregate = run_workflow_suite(
            suite=CHECK_SUITE,
            path=registered_root,
            permissions=perms,
            owner_instance_id=ctx.owner_instance_id,
            run_id=run_id,
            on_tool_complete=_on_tool_complete,
            original_requested_targets=original,
            invocation_start_cwd=anchor,
        )
        publish_check_suite_scan(
            ctx,
            record.project_id,
            registered_root,
            aggregate,
            run_id=run_id,
            attempt_id=attempt_id,
            scan_generation=scan_generation,
            artifact_snapshots=check_suite_snapshots,
        )

    scan_thread = threading.Thread(target=_run_initial_scan, daemon=True)
    scan_thread.start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        echo("\nStopping dashboard.")
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
            echo(
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
                echo(f"Revoked trust for plugin: {plugin_name}")
            else:
                echo(f"Plugin '{plugin_name}' was not found in trust ledger.")
        else:
            plugins = discover_plugins(repo_root)
            matched = next((p for p in plugins if p.name == plugin_name), None)
            if not matched:
                echo(f"Plugin '{plugin_name}' not found in configuration.", err=True)
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
            echo(
                f"Approved plugin as trusted: {plugin_name} (digest: {closure.closure_digest[:12]}...)"
            )
    else:
        root = repo_path.resolve()
        if revoke:
            revoke_trust(root)
            echo(f"Revoked trust for repository: {root}")
        else:
            trust_repo(root)
            echo(f"Approved repository as trusted: {root}")


@cli.group(name="plugin")
def plugin_grp() -> None:
    """Manage and execute custom quality plugins."""


@collection_route("rows")
@plugin_grp.command(name="list")
@click.argument("path", type=click.Path(exists=True, path_type=Path), default=Path("."))
@click.option("--json", "as_json", is_flag=True, help=_JSON_LIST_HELP)
def plugin_list(path: Path, as_json: bool) -> None:
    """List all custom plugins configured in rush.toml."""
    from .plugins.loader import discover_plugins

    plugins = discover_plugins(path.resolve())
    if as_json:
        echo_json({"rows": plugins, "total": len(plugins)})
        return
    if not plugins:
        echo("No custom plugins configured.")
    else:
        echo(f"Discovered {len(plugins)} plugin(s):")
    echo_rows(
        plugins,
        lambda p: f"  - {p.name}: {p.description} (cmd: {' '.join(p.command)})",
        empty="no plugins are configured",
    )


@collection_route("findings")
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
        echo(f"Plugin '{plugin_name}' not found in configuration.", err=True)
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
        echo(json.dumps(result.to_dict(), indent=2))
    else:
        status_color = (
            "green"
            if result.status == "ok"
            else ("yellow" if result.status == "warn" else "red")
        )
        secho(f"[{result.tool}] Status: {result.status}", fg=status_color, bold=True)
        echo(result.summary)
        echo_rows(
            result.findings,
            lambda f: f"  - [{f.severity}] {f.message}",
            cap=FINDINGS_CAP,
            noun="findings",
            empty="the plugin reported no findings",
        )

    adapter = AdminOperationAdapter(
        operation_id="cli.plugin_run",
        target_contract_id="ClickExitCode",
    )
    code = exit_code_for(result.status)
    sys.exit(adapter.validate_output(code))


for _catalog_tool in ALL_TOOLS:
    # T17 R17.2: `check` keeps its handwritten command (fail-fast flags).
    if _catalog_tool.name not in {
        "check",
        "review",
        "format",
        "commit-msg",
        "sbom",
        "fix",
        "benchmark",
        "memory",
        "patch-apply",
        "status",
    }:
        cli.add_command(build_catalog_path_command(_catalog_tool))


@cli.group(name="workspace")
def workspace_group() -> None:
    """Monorepo workspace discovery, topological execution, and boundary enforcement."""


@collection_route("rows")
@workspace_group.command(name="list")
@click.argument("path", type=click.Path(exists=True, path_type=Path), default=Path("."))
@click.option("--json", "as_json", is_flag=True, help=_JSON_LIST_HELP)
def workspace_list_cmd(path: Path, as_json: bool) -> None:
    """List discovered monorepo packages."""
    from rush.workspaces.discovery import WorkspaceDiscovery

    discovery = WorkspaceDiscovery(path)
    packages = discovery.discover_all()
    if as_json:
        echo_json({"rows": packages, "total": len(packages)})
        return
    echo(f"Discovered {len(packages)} workspace package(s):")
    echo_rows(
        packages,
        lambda p: f"  - [{p.kind.upper():6}] {p.name} ({p.relative_path})",
        empty="no workspace packages were found",
    )


@collection_route("rows")
@workspace_group.command(name="affected")
@click.argument("path", type=click.Path(exists=True, path_type=Path), default=Path("."))
@click.option("--json", "as_json", is_flag=True, help=_JSON_LIST_HELP)
def workspace_affected_cmd(path: Path, as_json: bool) -> None:
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
    affected = list(calc.get_affected_packages(changed))
    if as_json:
        echo_json({"rows": affected, "total": len(affected)})
        return
    echo(f"Affected package(s) ({len(affected)}):")
    echo_rows(
        affected,
        lambda name: f"  - {name}",
        empty="no workspace package is affected by the changed files",
    )


@collection_route("findings")
@workspace_group.command(name="boundary")
@click.argument("path", type=click.Path(exists=True, path_type=Path), default=Path("."))
@click.option("--json", "as_json", is_flag=True, help=_JSON_LIST_HELP)
def workspace_boundary_cmd(path: Path, as_json: bool) -> None:
    """Check workspace boundaries against illegal cross-package relative imports."""
    from rush.workspaces.boundary import WorkspaceBoundaryGuard
    from rush.workspaces.discovery import WorkspaceDiscovery

    repo_root = path.resolve()
    discovery = WorkspaceDiscovery(repo_root)
    packages = discovery.discover_all()
    guard = WorkspaceBoundaryGuard(repo_root)
    result = guard.check_package_boundaries(packages)
    if as_json:
        echo_json(result)
    else:
        echo(result["summary"])
        echo_rows(
            result.get("findings") or [],
            lambda f: (
                f"  - [{f.get('severity', 'info')}] {f.get('path')}:{f.get('line')} "
                f"{f.get('message')}"
            ),
            cap=FINDINGS_CAP,
            noun="findings",
            empty="no package boundary violations were found",
        )
    if result["status"] == "fail":
        sys.exit(1)


@collection_route("findings")
@workspace_group.command(name="locks")
@click.argument("path", type=click.Path(exists=True, path_type=Path), default=Path("."))
@click.option("--json", "as_json", is_flag=True, help=_JSON_LIST_HELP)
def workspace_locks_cmd(path: Path, as_json: bool) -> None:
    """Validate monorepo lockfile consistency."""
    from rush.workspaces.locks import WorkspaceLockValidator

    validator = WorkspaceLockValidator(path.resolve())
    result = validator.validate_lockfiles()
    if as_json:
        echo_json(result)
        return
    echo(result["summary"])
    echo_rows(
        result.get("findings") or [],
        lambda f: f"  - [{f.get('severity', 'info')}] {f.get('message')}",
        cap=FINDINGS_CAP,
        noun="findings",
        empty="no lockfile issues were found",
    )


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
@click.option(
    "--allow-cache-write",
    is_flag=True,
    help="Explicitly authorize local cache modification (compact result view).",
)
@click.option("--json", "as_json", is_flag=True, help="Print ToolResult JSON.")
@result_view_options
def patch_apply_cmd(
    patch_file: Path,
    dry_run: bool,
    circuit_breaker: bool,
    allow_artifact_write: bool,
    allow_cache_write: bool,
    as_json: bool,
    result_view: str | None,
    limit: int | None,
    max_bytes: int | None,
) -> None:
    """Verify PATH as a unified diff in isolation; explicitly grant promotion."""
    _run_tool(
        "patch-apply",
        Path.cwd(),
        as_json=as_json,
        permissions=ExecutionPermissions(
            artifact_write=allow_artifact_write, cache_write=allow_cache_write
        ),
        extra_kwargs={
            "patch_file": patch_file,
            "dry_run": dry_run,
            "circuit_breaker": circuit_breaker,
        },
        view=ViewOptions(result_view, limit, max_bytes),
    )


@patch_group.command(name="test")
@click.argument("patch_file", type=click.Path(exists=True, path_type=Path))
def patch_test_cmd(patch_file: Path) -> None:
    """Apply and verify a unified diff in an ephemeral worktree sandbox."""
    from rush.io.physical_paths import ContainmentError
    from rush.patch.applier import PatchApplier
    from rush.patch.contracts import DirtyWorkspaceError, PatchVerificationError
    from rush.patch.sandbox import PatchSandboxManager

    repo_root = Path.cwd()
    diff_content = patch_file.read_text(encoding="utf-8")
    mgr = PatchSandboxManager(repo_root)
    try:
        sandbox = mgr.create_sandbox()
        try:
            ok, msg = PatchApplier.apply_patch_to_dir(sandbox, diff_content)
        finally:
            mgr.cleanup_sandbox(sandbox)
    except (DirtyWorkspaceError, PatchVerificationError, ContainmentError) as exc:
        # T27: an unusable sandbox (no git, dirty workspace, failed
        # worktree) is an error outcome with its cause, never a traceback.
        echo(f"[ERROR] {exc}", err=True)
        sys.exit(2)
    if ok:
        echo(f"[PASS] {msg}")
    else:
        echo(f"[FAIL] {msg}", err=True)
        sys.exit(1)


@collection_route("rows")
@patch_group.command(name="memory")
@click.option("--json", "as_json", is_flag=True, help=_JSON_LIST_HELP)
def patch_memory_list_cmd(as_json: bool) -> None:
    """List historical AI patch memory records (read-only; creates nothing)."""
    from rush.patch.memory import PatchMemoryStore

    records = PatchMemoryStore.read_records(Path.cwd())
    unavailable = records if isinstance(records, str) else None
    rows = [] if isinstance(records, str) else records
    if as_json:
        echo_json(
            {
                "status": "skipped" if unavailable else "ok",
                "reason": unavailable,
                "rows": rows,
                "total": len(rows),
            }
        )
        return
    if unavailable:
        echo(f"Patch memory unavailable: {unavailable}")
    else:
        echo(f"Stored Patch Records ({len(rows)}):")
    echo_rows(
        rows,
        lambda r: (
            f"  - [{r.error_signature[:8]}] {r.target_file} (Successes: {r.success_count})"
        ),
        empty="no successful patches are remembered",
    )


@cli.group(name="release")
def release_group() -> None:
    """Packaging, versioning, and release artifact generation."""


@collection_route("rows")
@release_group.command(name="check")
@click.option("--json", "as_json", is_flag=True, help=_JSON_LIST_HELP)
def release_check_cmd(as_json: bool) -> None:
    """Check version parity across manifests."""
    from rush.release.semver import SemVerValidator

    versions = SemVerValidator.check_manifest_parity(Path.cwd())
    rows = [{"manifest": m, "version": v} for m, v in versions.items()]
    if as_json:
        echo_json({"rows": rows, "total": len(rows)})
        return
    echo("Discovered Manifest Versions:")
    echo_rows(
        rows,
        lambda row: f"  - {row['manifest']}: {row['version']}",
        empty="no version manifests were found",
    )


@cli.group(name="ci")
def ci_group() -> None:
    """Hardened CI/CD workflow generator."""


@ci_group.command(name="init")
def ci_init_cmd() -> None:
    """Generate hardened SHA-pinned GitHub Actions workflow."""
    from rush.release.ci_generator import CIWorkflowGenerator

    ci_file = CIWorkflowGenerator.generate_ci_workflow(Path.cwd())
    echo(f"Generated hardened GitHub Actions workflow at {ci_file}")


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
        echo("[SAFE] Command authorized for agent execution.")
    else:
        echo(f"[BLOCKED] {reason}", err=True)
        sys.exit(1)


@guard_group.command(name="check-path")
@click.argument("file_path", type=click.Path())
def guard_check_path(file_path: str) -> None:
    """Validate target path against protected governance file rules."""
    from rush.safety.guard import AgentSafetyGuard

    guard = AgentSafetyGuard(Path.cwd())
    if guard.is_file_protected(file_path):
        echo(
            f"[PROTECTED] Target path '{file_path}' is an immutable governance file.",
            err=True,
        )
        sys.exit(1)
    else:
        echo(f"[ALLOWED] Target path '{file_path}' is safe for modification.")


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
        echo(f"{target_path}: {count} tokens")
    else:
        total = 0
        for p in target_path.rglob("*"):
            if p.is_file() and p.suffix in (".py", ".ts", ".js", ".rs", ".go", ".md"):
                total += FastBPETokenCounter.count_file_tokens(p)
        echo(f"{target_path} (recursive): {total} tokens")


@token_group.command(name="outline")
@click.argument("file_path", type=click.Path(exists=True, path_type=Path))
def token_outline_cmd(file_path: Path) -> None:
    """Generate high-density AST skeleton outline for context compression."""
    from rush.token_economy.compressor import PythonAstOutlineCompressor

    source = file_path.read_text(encoding="utf-8", errors="replace")
    if file_path.suffix == ".py":
        compressed = PythonAstOutlineCompressor.compress_source(source)
        echo(compressed)
    else:
        echo(source)


@token_group.command(name="cache-advisor")
@click.argument("file_path", type=click.Path(exists=True, path_type=Path))
def token_cache_advisor_cmd(file_path: Path) -> None:
    """Analyze prompt prefix cache breakpoints."""
    from rush.token_economy.cache_advisor import PromptCacheAdvisor

    text = file_path.read_text(encoding="utf-8", errors="replace")
    suggestion = PromptCacheAdvisor.analyze_prefix(text)
    echo(
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
        echo(compressed)
    else:
        echo(source)


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
        echo(f"Wrote generated TypeScript interfaces to {output_ts}")
    else:
        echo(ts_code)


@collection_route("rows")
@sync_group.command(name="env")
@click.argument(
    "env_example",
    default=".env.example",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.argument(
    "env_actual",
    default=".env",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option("--json", "as_json", is_flag=True, help=_JSON_LIST_HELP)
def sync_env_cmd(env_example: Path, env_actual: Path, as_json: bool) -> None:
    """Check environment variable synchronization between .env.example and .env."""
    from rush.sync.env_sync import EnvironmentVariableSynchronizer

    missing = list(
        EnvironmentVariableSynchronizer.find_missing_keys(env_example, env_actual)
    )
    if as_json:
        echo_json({"passed": not missing, "rows": missing, "total": len(missing)})
    elif missing:
        echo(f"Missing environment variables in {env_actual} ({len(missing)}):")
    else:
        echo(f"All environment variables in {env_example} are present in {env_actual}.")
    if not as_json:
        echo_rows(missing, lambda k: f"  - {k}", empty="no keys are missing")
    if missing:
        sys.exit(1)


@cli.group(name="hygiene")
def hygiene_group() -> None:
    """Polyglot codebase hygiene and dead code elimination."""


@collection_route("rows")
@hygiene_group.command(name="dead-code")
@click.option("--json", "as_json", is_flag=True, help=_JSON_LIST_HELP)
def hygiene_dead_code_cmd(as_json: bool) -> None:
    """Scan project for unreferenced symbols and dead exports."""
    from rush.hygiene.dead_code import PolyglotDeadCodeDetector

    detector = PolyglotDeadCodeDetector(Path.cwd())
    findings = detector.scan_python()
    if as_json:
        echo_json({"rows": findings, "total": len(findings)})
        return
    echo(f"Dead Code Findings ({len(findings)}):")
    echo_rows(
        findings,
        lambda f: f"  - [{f.file_path}:{f.line_number}] {f.symbol_name}",
        empty="no unreferenced symbols were found",
    )


@hygiene_group.command(name="clean-imports")
@click.argument("target_file", type=click.Path(exists=True, path_type=Path))
def hygiene_clean_imports_cmd(target_file: Path) -> None:
    """Remove unused imports from target Python source file."""
    from rush.hygiene.unused_import_cleaner import UnusedImportCleaner

    cleaned, count = UnusedImportCleaner.clean_file(target_file)
    if count > 0:
        target_file.write_text(cleaned, encoding="utf-8")
        echo(f"Cleaned {count} unused import(s) in {target_file}")
    else:
        echo(f"No unused imports found in {target_file}")


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
        echo(result)
    else:
        echo(f"[MERGE FAILED] {result}", err=True)
        sys.exit(1)


@cli.group(name="codegraph")
def codegraph_group() -> None:
    """Polyglot AST code property graph exploration and verbatim slicing."""


def _codegraph_store() -> Any:
    """The existing code graph index opened read-only, or the reason it is
    unavailable. T27: a read never creates `.codegraph/` or its database."""
    from rush.codegraph.store import CodeGraphStore

    db = Path.cwd() / ".codegraph" / "graph.db"
    if not db.is_file():
        return f"no code graph index at {db}"
    return CodeGraphStore(db, read_only=True)


def _emit_codegraph(
    title: str,
    rows: list[Any],
    unavailable: str | None,
    as_json: bool,
    line: Any,
    empty: str,
) -> None:
    if as_json:
        echo_json(
            {
                "status": "skipped" if unavailable else "ok",
                "reason": unavailable,
                "rows": rows,
                "total": len(rows),
            }
        )
        return
    echo(f"Code graph unavailable: {unavailable}" if unavailable else title)
    echo_rows(rows, line, empty=unavailable or empty)


@collection_route("rows")
@codegraph_group.command(name="slice")
@click.argument("symbol_name")
@click.option("--json", "as_json", is_flag=True, help=_JSON_LIST_HELP)
def codegraph_slice_cmd(symbol_name: str, as_json: bool) -> None:
    """Extract verbatim source code slice for target symbol."""
    from rush.codegraph.slicer import VerbatimAstSlicer

    store = _codegraph_store()
    unavailable = store if isinstance(store, str) else None
    slices = [] if unavailable else VerbatimAstSlicer(store).slice_symbol(symbol_name)
    _emit_codegraph(
        f"Slices of '{symbol_name}' ({len(slices)}):",
        slices,
        unavailable,
        as_json,
        str,
        f"no symbol named '{symbol_name}' is in the code graph",
    )


@collection_route("rows")
@codegraph_group.command(name="callers")
@click.argument("symbol_name")
@click.option("--json", "as_json", is_flag=True, help=_JSON_LIST_HELP)
def codegraph_callers_cmd(symbol_name: str, as_json: bool) -> None:
    """Trace all reverse callers of target symbol."""
    from rush.codegraph.traverser import CallGraphTraverser

    store = _codegraph_store()
    unavailable = store if isinstance(store, str) else None
    steps = [] if unavailable else CallGraphTraverser(store).trace_callers(symbol_name)
    _emit_codegraph(
        f"Callers of '{symbol_name}' ({len(steps)}):",
        steps,
        unavailable,
        as_json,
        lambda s: (
            f"  - [{s.caller.file_path}:{s.caller.start_line}] {s.caller.symbol_name} "
            f"-> calls -> {s.callee.symbol_name} (depth: {s.depth})"
        ),
        f"no callers of '{symbol_name}' are in the code graph",
    )


@cli.group(name="bundle")
def bundle_group() -> None:
    """Frontend asset and build bundle optimization."""


@collection_route("rows")
@bundle_group.command(name="analyze")
@click.argument("dist_dir", type=click.Path(exists=True, path_type=Path))
@click.option("--json", "as_json", is_flag=True, help=_JSON_LIST_HELP)
def bundle_analyze_cmd(dist_dir: Path, as_json: bool) -> None:
    """Measure build chunk transfer sizes (raw, gzip, brotli)."""
    from rush.bundle.chunk_calculator import BundleChunkCalculator

    reports = BundleChunkCalculator.measure_directory(dist_dir)
    if as_json:
        echo_json({"rows": reports, "total": len(reports)})
        return
    echo(f"Analyzed Build Chunks ({len(reports)}):")
    echo_rows(
        reports,
        lambda r: (
            f"  - {r.file_name}: {r.raw_bytes} B (gzip: {r.gzip_bytes} B, "
            f"brotli: ~{r.brotli_est_bytes} B)"
        ),
        empty="no bundle files were found",
    )


@collection_route("rows")
@bundle_group.command(name="dead-assets")
@click.argument("assets_dir", type=click.Path(exists=True, path_type=Path))
@click.option("--json", "as_json", is_flag=True, help=_JSON_LIST_HELP)
def bundle_dead_assets_cmd(assets_dir: Path, as_json: bool) -> None:
    """Scan public/assets directories for unreferenced images and media."""
    from rush.bundle.dead_assets import OrphanedAssetScanner

    assets_root = assets_dir.resolve()
    unused = [
        asset
        for asset in OrphanedAssetScanner(Path.cwd()).find_orphaned_assets()
        if asset.is_relative_to(assets_root)
    ]
    if as_json:
        echo_json({"rows": unused, "total": len(unused)})
        return
    echo(f"Unreferenced Assets ({len(unused)}):")
    echo_rows(unused, lambda u: f"  - {u}", empty="no unused assets were found")


@cli.group(name="hotspots")
def hotspots_group() -> None:
    """Git commit churn, defect risk matrix, and developer velocity analytics."""


@collection_route("rows")
@hotspots_group.command(name="analyze")
@click.option("--json", "as_json", is_flag=True, help=_JSON_LIST_HELP)
def hotspots_analyze_cmd(as_json: bool) -> None:
    """Compute composite defect risk scores across files."""
    from rush.hotspots.risk_matrix import RiskMatrixCalculator

    calculator = RiskMatrixCalculator(Path.cwd())
    scores = calculator.analyze_hotspots()
    if as_json:
        echo_json({"rows": scores, "total": len(scores)})
        return
    echo(f"Analyzed Hotspots ({len(scores)}):")
    echo_rows(
        scores,
        lambda s: (
            f"  - [{s.risk_tier}] {s.file_path}: Risk {s.composite_risk} "
            f"(Churn: {s.churn_score}, Complexity: {s.complexity_score})"
        ),
        empty="no files have git churn to score",
    )


@collection_route("rows")
@hotspots_group.command(name="bus-factor")
@click.option("--json", "as_json", is_flag=True, help=_JSON_LIST_HELP)
def hotspots_bus_factor_cmd(as_json: bool) -> None:
    """Calculate module knowledge distribution and bus factor risks."""
    from rush.hotspots.bus_factor import BusFactorAssessor

    reports = BusFactorAssessor(Path.cwd()).assess_ownership()
    if as_json:
        echo_json({"rows": reports, "total": len(reports)})
        return
    echo(f"Bus Factor Analysis ({len(reports)} files):")
    echo_rows(
        reports,
        lambda r: (
            f"  - {r.file_path}: {r.total_authors} authors, ownership entropy "
            f"{r.author_entropy} (Primary author: {r.primary_owner} {r.ownership_percent}%)"
        ),
        empty="no files have git authorship to report",
    )


@cli.group(name="governance")
def governance_group() -> None:
    """Agent governance and multi-IDE rule synchronization."""


@collection_route("rows")
@governance_group.command(name="sync")
@click.option("--json", "as_json", is_flag=True, help=_JSON_LIST_HELP)
def governance_sync_cmd(as_json: bool) -> None:
    """Compile canonical AGENTS.md to .cursorrules, .clinerules, etc."""
    from rush.governance.synchronizer import AgentsMdSynchronizer

    syncer = AgentsMdSynchronizer(Path.cwd())
    results = syncer.sync_all()
    if as_json:
        echo_json({"rows": results, "total": len(results)})
        return
    echo(f"Synchronized Governance Files ({len(results)}):")
    echo_rows(
        results,
        lambda r: f"  - [{r.action}] {r.target_path} (SHA: {r.sha256[:8]})",
        empty="no IDE rule files needed syncing",
    )


@collection_route("rows")
@governance_group.command(name="check")
@click.option("--json", "as_json", is_flag=True, help=_JSON_LIST_HELP)
def governance_check_cmd(as_json: bool) -> None:
    """Check that multi-IDE rule files are synchronized with AGENTS.md."""
    from rush.governance.parity_checker import RuleParityChecker

    drifted = RuleParityChecker(Path.cwd()).check_parity()
    if as_json:
        echo_json({"passed": not drifted, "rows": drifted, "total": len(drifted)})
    elif not drifted:
        echo("[OK] All multi-IDE governance rule files match AGENTS.md.")
    else:
        echo(
            f"[DRIFT DETECTED] Unsynchronized governance files ({len(drifted)}):",
            err=True,
        )
    if not as_json:
        echo_rows(
            drifted,
            lambda d: f"  - {d.target_path}: {d.reason}",
            err=True,
            empty="no IDE rule files have drifted",
        )
    if drifted:
        sys.exit(1)


@cli.group(name="scaffold")
def scaffold_group() -> None:
    """Repository governance and configuration scaffolding."""


@collection_route("rows")
@scaffold_group.command(name="init")
@click.option("--json", "as_json", is_flag=True, help=_JSON_LIST_HELP)
def scaffold_init_cmd(as_json: bool) -> None:
    """Initialize repository with AGENTS.md and rush.toml templates."""
    from rush.governance.scaffolder import RepoScaffolder

    created = RepoScaffolder.init_repository(Path.cwd())
    if as_json:
        echo_json({"rows": created, "total": len(created)})
        return
    echo(f"Scaffolded Files ({len(created)}):")
    echo_rows(
        created, lambda c: f"  - {c.name}", empty="no scaffold files were created"
    )


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
        echo(f"[HOOK BLOCKED] {err}", err=True)
        sys.exit(1)

    scanner = StagedFileScanner(Path.cwd())
    try:
        entries = scanner.get_staged_entries()
    except RuntimeError:
        echo("[INDEX ERROR] Cannot read staged index.", err=True)
        sys.exit(1)
    if not entries:
        echo("No staged files to check.")
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
            echo(
                f"[INDEX ERROR] {entry.status}: {entry.relative_path} ({stages})",
                err=True,
            )
        sys.exit(1)

    staged = [entry for entry in entries if entry.status == "staged"]
    deleted_count = sum(entry.status == "deleted" for entry in entries)
    ast_errs = FastIncrementalAstLinter.lint_staged_entries(staged)
    if ast_errs:
        echo("\n".join(f"[AST ERROR] {e}" for e in ast_errs), err=True)
        sys.exit(1)

    for entry in staged:
        assert entry.content is not None, "staged entry has no index blob"
        for detector, label in (
            (TrojanSourceDetector, "SECURITY"),
            (ConflictMarkerGuard, "CONFLICT"),
        ):
            errors = detector.inspect_content(entry.path, entry.content)
            if errors:
                echo("\n".join(f"[{label} ERROR] {e}" for e in errors), err=True)
                sys.exit(1)

    echo(
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
    echo(report.summary)

    if export_svg:
        svg = SvgBadgeGenerator.generate_badge_svg(
            report.composite_score, report.letter_grade
        )
        from .safety.redactor import sanitize_value

        _write_export(export_svg, sanitize_value(svg).value)
        echo(f"Wrote SVG badge to {export_svg}")

    if export_html:
        html = HtmlReportGenerator.generate_html_report(report)
        _write_export(export_html, html)
        echo(f"Wrote HTML report to {export_html}")


def _write_export(path: Path, text: str) -> None:
    """Write an export, creating its parent folder; an unwritable path is an
    error outcome (exit 2), never a traceback."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        echo(f"[ERROR] cannot write {path}: {exc.strerror or exc}", err=True)
        sys.exit(2)


@cli.group(name="consensus")
def consensus_group() -> None:
    """Multi-model AI code review reconciliation."""


def _consensus_line(c: Any) -> str:
    return (
        f"  - [{c.severity.upper()}] {c.file_path}:{c.line_number} {c.rule_id} "
        f"({c.description}) [Confidence: {int(c.confidence * 100)}%, "
        f"Models: {', '.join(c.agreeing_models)}]"
    )


@collection_route("rows")
@consensus_group.command(name="reconcile")
@click.argument(
    "findings_files", nargs=-1, type=click.Path(exists=True, path_type=Path)
)
@click.option(
    "--min-agreement", default=0.5, help="Minimum model agreement ratio (0.0 - 1.0)."
)
@click.option("--json", "as_json", is_flag=True, help=_JSON_LIST_HELP)
def consensus_reconcile_cmd(
    findings_files: tuple[Path, ...], min_agreement: float, as_json: bool
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
            echo(f"Warning: Could not parse '{f_path}': {e}", err=True)

    total_models = max(len(models), 1)
    consensus = reconciler.reconcile_findings(all_findings, total_models=total_models)
    if as_json:
        echo_json(
            {
                "min_agreement": min_agreement,
                "total_models": total_models,
                "rows": consensus,
                "total": len(consensus),
            }
        )
        return
    echo(
        f"Consensus Findings ({len(consensus)} agreed by >={int(min_agreement * 100)}% "
        f"of {total_models} models):"
    )
    echo_rows(consensus, _consensus_line, empty="no review findings to reconcile")


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


def _memory_logical_root() -> Path:
    """R20.2: the one project root every `rush memory` command (overview and
    subcommands) reads and writes, chosen by T8's `select_root` walk from the
    cwd (deepest marked or registered directory, else the deepest existing
    one), so a write from a subdirectory lands in the store the project-root
    overview shows."""
    from .invocation.targets import resolve_logical_root

    return resolve_logical_root(".", anchor=Path(os.path.abspath(Path.cwd())))


_MEMORY_OVERVIEW_OPTIONS = ("offset", "generation", "include_internal", "as_json")


def _echo_memory_overview(result: dict[str, Any]) -> None:
    """T20 plain-line rendering (not `render_result`, which drops `raw.data` rows)."""
    from datetime import UTC, datetime

    raw = result.get("raw") or {}
    data = raw.get("data") or {}
    if raw.get("code") != "OK":
        echo(f"memory: {raw.get('code')}: {data.get('message')}")
        return
    rows = data["rows"]
    label = "record(s)" if data["include_internal"] else "useful record(s)"
    shown = (
        f"showing {data['offset'] + 1}-{data['offset'] + len(rows)}"
        if rows
        else "showing none"
    )
    echo(f"memory: {data['total']} {label} in {data['project_root']} ({shown})")
    for row in rows:
        owner = row["owner_scope"]
        created = datetime.fromtimestamp(row["created_at"], tz=UTC).isoformat()
        echo(
            f"{row['id']}  {row['subject']}  {row['source']}  "
            f"owner {owner['kind']}:{owner['id']}  {created}  {row['trust_tier']}"
        )
    if data["next_offset"] is not None:
        echo(
            f"next: rush memory --offset {data['next_offset']} "
            f"--generation {data['generation_token']}"
        )
    if data.get("reason"):
        echo(data["reason"])


@cli.group(name="memory", invoke_without_command=True)
@click.option(
    "--offset",
    type=click.IntRange(min=0),
    default=0,
    help="Overview only: skip this many rows (requires --generation when > 0).",
)
@click.option(
    "--generation",
    default=None,
    help="Overview only: the continuation token the previous page printed.",
)
@click.option(
    "--include-internal",
    is_flag=True,
    help="Overview only: also show internal bookkeeping rows.",
)
@click.option("--json", "as_json", is_flag=True, help="Overview only: print raw JSON.")
@click.pass_context
def memory_group(
    ctx: click.Context,
    offset: int,
    generation: str | None,
    include_internal: bool,
    as_json: bool,
) -> None:
    """Query, write, and promote cross-tool memory artifacts.

    With no subcommand, shows this project's 20 most recent useful memory records
    (newest first, read-only; archived, expired and internal rows hidden)."""
    if ctx.invoked_subcommand is not None:
        given = [
            name
            for name in _MEMORY_OVERVIEW_OPTIONS
            if ctx.get_parameter_source(name) != click.core.ParameterSource.DEFAULT
        ]
        if given:
            raise click.UsageError(
                "--offset/--generation/--include-internal/--json before a memory "
                "subcommand apply only to the bare `rush memory` overview"
            )
        return
    from .tools.memory import memory_overview

    result = dict(
        memory_overview(
            _memory_logical_root(),
            offset=offset,
            generation=generation,
            include_internal=include_internal,
        )
    )
    if as_json:
        echo(json.dumps(result, indent=2, default=str))
    else:
        _echo_memory_overview(result)
    raise click.exceptions.Exit(exit_code_for(result))


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
        _memory_logical_root(),
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
        _memory_logical_root(),
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
        _memory_logical_root(),
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
        _memory_logical_root(),
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
        _memory_logical_root(),
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
@click.option(
    "--owner-kind",
    type=click.Choice(["project", "user", "agent", "session"]),
    default=None,
    help="Explicit owner_scope kind. Defaults to this root's registered project "
    "id, or its legacy path owner if unregistered.",
)
@click.option(
    "--owner-id",
    default=None,
    help="Explicit owner_scope id. Required together with --owner-kind.",
)
def memory_maintain_cmd(
    task: MaintenanceTask,
    batch_size: int,
    as_json: bool,
    allow_cache_write: bool,
    owner_kind: OwnerScopeKind | None,
    owner_id: str | None,
) -> None:
    """Run a bounded memory-store maintenance sweep (Phase 62 §6.2)."""
    from .tools.memory import MemoryTool
    from .workflows.projects import ProjectNotFoundError, resolve_project

    root = _memory_logical_root()
    if owner_kind is not None:
        if not owner_id:
            raise click.UsageError("--owner-kind requires --owner-id")
        owner_scope = OwnerScope(owner_kind, owner_id)
    elif owner_id is not None:
        raise click.UsageError("--owner-id requires --owner-kind")
    else:
        # M09: this CLI entry point's own explicitly-supported legacy fallback
        # (M08 bullet 3) -- an unregistered root still maintains under its
        # path-form owner rather than failing outright.
        try:
            owner_scope = OwnerScope("project", resolve_project(root)["project_id"])
        except ProjectNotFoundError:
            owner_scope = legacy_owner_scope(root)

    result = MemoryTool().run(
        root,
        operation="maintain",
        task=task,
        batch_size=batch_size,
        owner_scope=owner_scope,
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
        result_view: str | None,
        limit: int | None,
        max_bytes: int | None,
    ) -> None:
        request = _memory_input_request(input_file)
        _run_tool(
            "memory",
            _memory_logical_root(),
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
            view=ViewOptions(result_view, limit, max_bytes),
        )

    _cmd.__name__ = f"memory_{operation}_cmd"
    _cmd.__doc__ = _MEMORY_OPERATION_HELP[operation]
    _cmd = click.option(
        "--json", "as_json", is_flag=True, help="Print raw ToolResult JSON."
    )(_cmd)
    _cmd = permission_options(_cmd)
    _cmd = result_view_options(_cmd)
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
    from .workflows.project_run import rescan_project_run
    from .workflows.projects import ProjectError

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
    except ProjectError as exc:  # T27: ScanError and an unknown project
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

    from .tools.scan import executed_work_status

    comparison = data["comparison"]
    status = executed_work_status(data)  # T27: the re-executed run's outcome
    summary = (
        f"scan rescan {run_id}: {status}; {len(comparison['resolved'])} resolved, "
        f"{len(comparison['persisting'])} persisting, "
        f"{len(comparison['new'])} new, "
        f"{len(comparison['unverified'])} unverified"
    )
    _render_session_result(
        {
            "tool": "scan-rescan",
            "status": status,
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
    from .workflows.project_run import cancel_scan_run
    from .workflows.projects import ProjectError

    try:
        data = cancel_scan_run(project, run_id)
    except ProjectError as exc:  # T27: ScanError and an unknown project
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

    from .workflows.project_run import load_run_manifest
    from .workflows.projects import resolve_project

    # T27: an attempt with a terminal manifest has nothing left to stop; the
    # idempotent marker is recorded, but the result says so.
    manifest = load_run_manifest(
        Path(resolve_project(project)["root"]), run_id, attempt_id=data["attempt_id"]
    )
    if manifest is not None:
        state = manifest.get("run_state", "finished")
        summary = f"scan cancel {run_id}: attempt already finished ({state}); nothing to cancel"
        data = {**data, "already_finished": True, "run_state": state}
    else:
        summary = f"scan cancel {run_id}: requested"
        data = {**data, "already_finished": False}
    _render_session_result(
        {
            "tool": "scan-cancel",
            "status": "ok",
            "duration_ms": 0,
            "summary": summary,
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
    from .workflows.project_run import resume_scan_run
    from .workflows.projects import ProjectError

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
    except ProjectError as exc:  # T27: ScanError and an unknown project
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

    from .tools.scan import executed_work_status

    resumed = run.to_dict()
    status = executed_work_status(resumed)  # T27: the attempt's own outcome
    _render_session_result(
        {
            "tool": "scan-resume",
            "status": status,
            "duration_ms": 0,
            "summary": (
                f"scan resume {run_id}: {status}; new attempt {run.attempt_id}, "
                f"state={run.run_state}"
            ),
            "findings": [],
            "raw": resumed,
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
@click.option(
    "--install-guidance",
    is_flag=True,
    help=(
        "Write the Rush instruction block into the project's CLAUDE.md/AGENTS.md "
        "without prompting. Without it, a terminal asks [y/N] and a "
        "non-interactive run leaves guidance pending."
    ),
)
@click.option(
    "--profile",
    default=None,
    metavar="[core|full]",
    callback=lambda _ctx, _param, value: _validate_mcp_profile(value),
    help=(
        "Migrate this agent's existing Rush MCP entry to a server profile. "
        "Always prints a preview; applies only after an explicit y or --yes."
    ),
)
@click.option(
    "--yes",
    "assume_yes",
    is_flag=True,
    help="Apply the previewed --profile migration without prompting.",
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
    install_guidance: bool,
    profile: str | None,
    assume_yes: bool,
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

    Requires --allow-cache-write and --allow-artifact-write. The project
    instruction block is written only with --install-guidance or an explicit
    "y" at the terminal prompt; --consent and --acknowledge never imply it.

    Without --profile an existing Rush entry keeps its args (only a stale
    command path is repaired) and a new one runs `mcp serve --profile core`.
    With --profile the entry's migration is previewed first and applied only
    after "y" at the terminal prompt or --yes.
    """
    from .tools.agent_connection import AgentConnectionTool

    interactive = not as_json and os.isatty(0) and _is_terminal(sys.stdout)
    result = AgentConnectionTool().run(
        agent_id,
        action="connect",
        session_id=session_id,
        rush_binary=rush_binary,
        consent=consent,
        acknowledge=acknowledge,
        install_guidance=install_guidance,
        confirm_guidance=_confirm_guidance if interactive else None,
        project_root=project_path,
        profile=profile,
        confirm_profile=_profile_consent(assume_yes, interactive, as_json),
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
    raw = result.get("raw") or {}
    migration = raw.get("migration")
    if (
        not as_json
        and isinstance(migration, dict)
        and migration.get("state") == "pending"
    ):
        _echo_migration_preview(migration)  # not shown by a consent prompt
    guidance = raw.get("guidance")
    if not as_json and isinstance(guidance, dict):
        echo(f"guidance: {guidance['state']}")
    _render_session_result(dict(result), as_json)


def _profile_consent(
    assume_yes: bool, interactive: bool, as_json: bool
) -> bool | Callable[[dict[str, Any]], bool]:
    """T4: `--yes` applies and a terminal asks [y/N], each after printing the
    preview; any other run answers no, leaving the migration pending."""
    if not (assume_yes or interactive):
        return False

    def consent(preview: dict[str, Any]) -> bool:
        if not as_json:
            _echo_migration_preview(preview)
        if assume_yes:
            return True
        return _ask_yes("Apply this MCP profile migration? [y/N]: ")

    return consent


def _echo_migration_preview(preview: dict[str, Any]) -> None:
    echo(f"Rush MCP profile migration for {preview['agent_id']}:")
    echo(f"  config: {preview['config_path']} ({preview['method']})")
    echo(
        f"  current: {preview['current_command']} {preview['current_args']} "
        f"(profile: {preview['current_profile']})"
    )
    echo(f"  new:     {preview['new_command']} {preview['new_args']}")
    echo(f"  current sha256: {preview['current_sha256']}")


def _is_terminal(stream: Any) -> bool:
    try:
        return os.isatty(stream.fileno())
    except (AttributeError, OSError, ValueError):
        return False


def _confirm_guidance(plan: Any) -> bool:
    """Show the exact target and diff, then ask [y/N]; only y/yes applies.

    The answer is read straight from the terminal on fd 0 (the stream the
    TTY check above inspected), so a replaced `sys.stdin` object cannot
    answer for the user. EOF (Ctrl-D) or Ctrl-C declines.
    """
    echo(f"Rush instruction block for {plan.target_path}:")
    echo(plan.diff)
    return _ask_yes("Write this Rush instruction block? [y/N]: ")


def _ask_yes(question: str) -> bool:
    """Ask `question` on the terminal; only y/yes read from fd 0 is a yes."""
    echo(question, nl=False)
    answer = b""
    try:
        while not answer.endswith(b"\n"):
            chunk = os.read(0, 1024)
            if not chunk:
                break
            answer += chunk
    except KeyboardInterrupt:
        answer = b""
    if not answer.endswith(b"\n"):
        echo("")
        return False  # EOF or Ctrl-C before a complete answer line
    return answer.decode("utf-8", errors="replace").strip().lower() in ("y", "yes")


@agent_group.command(name="disconnect")
@click.argument("agent_id")
@click.option(
    "--project",
    "project_path",
    default=None,
    type=click.Path(path_type=Path),
    help="Project whose connection to remove; omit for the user-scope connection.",
)
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def agent_disconnect_cmd(
    agent_id: str, project_path: Path | None, as_json: bool
) -> None:
    """Remove Rush's own, unchanged components for AGENT_ID.

    Removes the MCP entry, the instruction block (or this agent from a
    shared block), and Rush skill/hook resources recorded as Rush-owned.
    Anything changed since Rush wrote it is kept and reported as a conflict.
    Running it again is a no-op.
    """
    from .tools.agent_connection import AgentConnectionTool

    result = AgentConnectionTool().run(
        agent_id, action="disconnect", project_root=project_path
    )
    _render_session_result(dict(result), as_json)


@agent_group.command(name="hook")
@click.argument("host", type=click.Choice(["claude", "codex"]))
def agent_hook_cmd(host: str) -> None:
    """Post-edit hook entrypoint the Rush Claude Code/Codex plugins run.

    Reads the host's JSON event on stdin. Prints nothing and runs no check
    unless agent hooks are enabled for this host and project; always exits 0
    so a hook never changes the edit's result.
    """
    from .integrations.agent_hooks import MAX_PAYLOAD_BYTES, run_agent_hook

    stdin = click.get_binary_stream("stdin")
    payload = b"" if stdin.isatty() else stdin.read(MAX_PAYLOAD_BYTES + 1)
    output = run_agent_hook(host, payload)
    if output:
        echo(output)


@agent_group.command(name="doctor")
@click.option(
    "--session", "session_id", default=None, help="Include this session's memory state."
)
@click.option(
    "--project",
    "project_path",
    default=None,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
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
@click.option(
    "--install-guidance",
    is_flag=True,
    help=(
        "Write the Rush instruction block into the selected project's "
        "CLAUDE.md/AGENTS.md; without it the block is only previewed."
    ),
)
@click.option(
    "--agent-plugin",
    "agent_plugins",
    multiple=True,
    type=click.Choice(["claude", "codex"]),
    help=(
        "Install (or upgrade) the native Rush plugin for this host through "
        "its own plugin CLI instead of a manual MCP entry. Repeatable."
    ),
)
@click.option(
    "--convert-manual-entry",
    is_flag=True,
    help=(
        "With --agent-plugin: consent to removing an existing 'rush' MCP entry "
        "Rush did not record (shown as a diff in the result) so the plugin is "
        "the only Rush server. Without it that host is left unchanged."
    ),
)
@click.option(
    "--agent",
    "agent",
    type=click.Choice(["claude", "codex"]),
    default=None,
    help=(
        "Connect exactly this LLM CLI (overrides --agents all). With --setup, the "
        "host that guided setup connects to --project."
    ),
)
@click.option(
    "--setup",
    "guided_setup",
    is_flag=True,
    help=(
        "After installing (connecting no agent itself), run `rush setup` for "
        "--project (default: the current directory) and --agent, asking consent "
        "on the terminal."
    ),
)
@click.option(
    "--non-interactive",
    is_flag=True,
    help="With --setup: never prompt; print the full setup preview instead.",
)
@click.option("--handoff-archive", type=click.Path(path_type=Path), hidden=True)
@click.option("--handoff-sums", type=click.Path(path_type=Path), hidden=True)
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
    install_guidance: bool,
    agent_plugins: tuple[str, ...],
    convert_manual_entry: bool,
    agent: str | None,
    guided_setup: bool,
    non_interactive: bool,
    handoff_archive: Path | None,
    handoff_sums: Path | None,
    as_json: bool,
) -> None:
    """Download/verify/install the release binary, connect agents, and optionally set up a project."""
    if agent is not None and agents == "none" and not guided_setup:
        raise click.UsageError(
            "--agent conflicts with --agents none: --agent HOST connects exactly "
            "that host, --agents none connects none"
        )
    from .tools.install import run_install_command

    outcome = run_install_command(
        setup=guided_setup,
        agent=agent,
        project_path=project_path,
        interactive=not (as_json or non_interactive),
        agents=agents,
        memory=memory,
        create_name=create_name,
        create_parent=create_parent,
        init_git=init_git,
        session_id=session_id,
        version=version,
        install_guidance=install_guidance,
        agent_plugins=agent_plugins,
        convert_manual_entry=convert_manual_entry,
        handoff_archive=handoff_archive,
        handoff_sums=handoff_sums,
    )
    try:
        _render_session_result(dict(outcome["install"]), as_json)
    except click.exceptions.Exit as done:
        if outcome["followup"] and not as_json:
            echo(outcome["followup"])
        raise click.exceptions.Exit(done.exit_code or outcome["setup_exit"]) from None


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
        echo(f"Ship Clean: {res['status']}: {detail}", err=True)
        raise click.exceptions.Exit(1)
    mode = "Removed" if apply else "Would remove"
    echo(
        f"Ship Clean: {mode} "
        f"{res['removed_count'] if apply else res['preview_count']} items "
        f"({res['bytes_freed'] if apply else res['preview_bytes']} bytes)."
    )


@collection_route("missing_in_example")
@ship_group.command(name="env")
@click.option("--json", "as_json", is_flag=True, help=_JSON_LIST_HELP)
def ship_env_cmd(as_json: bool) -> None:
    """Lint codebase environment variable usage against .env.example."""
    from rush.tools.ship.env_linter import EnvParityLinter

    res = EnvParityLinter().lint()
    rows = res.get("missing_in_example") or []
    if as_json:
        echo_json(res)
    elif res["passed"]:
        echo("Ship Env: All codebase environment variables declared in .env.example.")
    else:
        echo(
            f"Ship Env: FAIL - {len(res['missing_in_example'])} undeclared variables in .env.example:",
            err=True,
        )
    if not as_json:
        echo_rows(
            rows,
            lambda item: f"  - {item}",
            err=True,
            empty="no environment keys are missing",
        )
    if not res["passed"]:
        sys.exit(1)


@collection_route("broken_links")
@ship_group.command(name="docs")
@click.option("--json", "as_json", is_flag=True, help=_JSON_LIST_HELP)
def ship_docs_cmd(as_json: bool) -> None:
    """Audit documentation links and CLI reference parity."""
    from rush.tools.ship.docs_linter import DocsLinter

    res = DocsLinter().lint()
    rows = res.get("broken_links") or []
    if as_json:
        echo_json(res)
    elif res["passed"]:
        echo(
            f"Ship Docs: Audited {res['checked_docs']} markdown docs. All links valid."
        )
    else:
        echo(
            f"Ship Docs: FAIL - {res['broken_links_count']} broken relative links found:",
            err=True,
        )
    if not as_json:
        echo_rows(
            rows,
            lambda item: f"  - {item['file']} -> {item['target']}",
            err=True,
            empty="no documentation links are stale",
        )
    if not res["passed"]:
        sys.exit(1)


@ship_group.command(name="gate")
def ship_gate_cmd() -> None:
    """Evaluate 7-vector pre-flight release readiness gate."""
    from rush.tools.ship.cockpit import ShipCockpit

    cockpit = ShipCockpit()
    verdict = cockpit.evaluate_gate()
    status_str = "PASSED" if verdict.all_passed else "FAILED"
    echo(f"Ship Gate Verdict: {status_str} ({verdict.score_pct}% score)")
    for v in verdict.vectors:
        mark = "[OK]" if v.passed else "[FAIL]"
        echo(f"  {mark} {v.name.upper()}: {v.details} ({v.duration_ms}ms)")
    if not verdict.all_passed:
        sys.exit(1)


@collection_route("findings")
@ship_group.command(name="migration")
@click.option("--json", "as_json", is_flag=True, help=_JSON_LIST_HELP)
def ship_migration_cmd(as_json: bool) -> None:
    """Lint database migrations for table-locking hazards."""
    from rush.tools.ship.migration_linter import MigrationLinter

    res = MigrationLinter().lint_migrations()
    rows = res.get("findings") or []
    if as_json:
        echo_json(res)
    elif res["passed"]:
        echo("Ship Migration: No dangerous table locks detected.")
    else:
        echo(
            f"Ship Migration: FAIL - {res['findings_count']} migration hazards:",
            err=True,
        )
    if not as_json:
        echo_rows(
            rows,
            lambda item: f"  {item['file']}: {', '.join(item['hazards'])}",
            err=True,
            cap=FINDINGS_CAP,
            noun="findings",
            empty="no dangerous migrations were found",
        )
    if not res["passed"]:
        sys.exit(1)


@collection_route("rows")
@ship_group.command(name="semver")
@click.argument("old_file", type=click.Path(exists=True, path_type=Path))
@click.argument("new_file", type=click.Path(exists=True, path_type=Path))
@click.option("--json", "as_json", is_flag=True, help=_JSON_LIST_HELP)
def ship_semver_cmd(old_file: Path, new_file: Path, as_json: bool) -> None:
    """Check for breaking API signature changes between file versions."""
    from rush.tools.ship.semver_linter import SemverLinter

    linter = SemverLinter()
    old_code = old_file.read_text(encoding="utf-8", errors="ignore")
    new_code = new_file.read_text(encoding="utf-8", errors="ignore")
    breaking = list(linter.diff_apis(old_code, new_code))
    if as_json:
        echo_json({"passed": not breaking, "rows": breaking, "total": len(breaking)})
    elif not breaking:
        echo(
            f"Ship SemVer: Public API signatures compatible ({old_file.name} -> {new_file.name})."
        )
    else:
        echo(f"Ship SemVer: FAIL - {len(breaking)} breaking changes:", err=True)
    if not as_json:
        echo_rows(
            breaking,
            lambda b: f"  - {b}",
            err=True,
            empty="no breaking changes were found",
        )
    if breaking:
        sys.exit(1)


@collection_route("leaks")
@ship_group.command(name="pack")
@click.option("--json", "as_json", is_flag=True, help=_JSON_LIST_HELP)
def ship_pack_cmd(as_json: bool) -> None:
    """Audit source tree for secret leaks before packaging."""
    from rush.tools.ship.package_linter import PackageLinter

    res = PackageLinter().lint()
    rows = res.get("leaks") or []
    if as_json:
        echo_json(res)
    elif res["passed"]:
        echo("Ship Pack: Source package clean of sensitive keys and env files.")
    else:
        echo(
            f"Ship Pack: FAIL - {res['leaks_count']} sensitive files detected:",
            err=True,
        )
    if not as_json:
        echo_rows(
            rows, lambda item: f"  - {item}", err=True, empty="no files were packed"
        )
    if not res["passed"]:
        sys.exit(1)


# -----------------------------------------------------------------------------
# Phase 43: CCR, Grounding & Mistake Memory
# -----------------------------------------------------------------------------


@cli.group(name="context")
def context_group() -> None:
    """Context optimization, CCR retrieval, and mistake memory."""


@context_group.command(name="retrieve")
@click.argument("chunk_hash")
@click.option(
    "--view",
    type=click.Choice(["result", "bytes"]),
    default=None,
    help="Read a stored compact result: a findings page (result) or a byte "
    "slice (bytes). Omit for the legacy full chunk.",
)
@click.option("--cursor", default=None, help="next_cursor from the previous page.")
@click.option(
    "--offset",
    type=int,
    default=None,
    help="Start finding (result) or byte (bytes); not with --cursor.",
)
@click.option("--limit", type=int, default=None, help="Findings per page, 1-50.")
@click.option(
    "--max-bytes",
    "max_bytes",
    type=int,
    default=None,
    help="Size budget of the whole printed page, 4096-65536 bytes.",
)
@click.option("--json", "as_json", is_flag=True, help="Emit canonical ToolResult JSON.")
def context_retrieve_cmd(
    chunk_hash: str,
    view: str | None,
    cursor: str | None,
    offset: int | None,
    limit: int | None,
    max_bytes: int | None,
    as_json: bool,
) -> None:
    """Retrieve a CCR chunk through the shared continuity contract."""
    from rush.tools.continuity import SessionContinuityTool

    _render_session_result(
        SessionContinuityTool().run(
            Path.cwd(),
            operation="context_retrieve",
            context_handle=chunk_hash,
            view=view,
            cursor=cursor,
            offset=offset,
            limit=limit,
            max_bytes=max_bytes,
        ),
        as_json,
    )


@collection_route("rows")
@context_group.command(name="mistakes")
@click.option("--json", "as_json", is_flag=True, help=_JSON_LIST_HELP)
def context_mistakes_cmd(as_json: bool) -> None:
    """List historical Git-revert mistake guardrails."""
    from rush.memory.mistake_miner import MistakeMiner

    mistakes = MistakeMiner().mine_mistakes()
    if as_json:
        echo_json({"rows": mistakes, "total": len(mistakes)})
        return
    if not mistakes:
        echo("No historical mistake patterns found in git revert history.")
    else:
        echo(f"Mistake Guardrails ({len(mistakes)}):")
    echo_rows(
        mistakes,
        lambda m: f"  - [AVOID] {m.get('reverted_subject')}: {m.get('rationale')}",
        empty="no reverted mistakes are recorded",
    )


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
    echo(
        f"Aligned tokens: {aligned['system']['aligned_tokens']} (Padded: {aligned['system']['padded']})"
    )


def _run_gain_live_panel(
    console: Any | None = None,
    *,
    max_updates: int | None = None,
    refresh_seconds: float = 0.5,
) -> None:
    """P69-06b: live-updating Tokens HUD -- re-renders `build_gain_panel` on
    a timer instead of printing one static snapshot. `max_updates` is a test
    seam bounding the loop; production runs until Ctrl+C."""
    import time

    from rich.console import Console
    from rich.live import Live

    from rush.token_economy.tui_gain import build_gain_panel

    console = console or Console()
    if max_updates is None and not console.is_terminal:
        # T27: redirected/piped output cannot host a live HUD and nothing
        # can deliver Ctrl+C to it -- print one read-only snapshot and exit.
        console.print(build_gain_panel())
        return
    with Live(build_gain_panel(), console=console, refresh_per_second=4) as live:
        updates = 0
        try:
            while max_updates is None or updates < max_updates:
                time.sleep(refresh_seconds)
                live.update(build_gain_panel())
                updates += 1
        except KeyboardInterrupt:
            pass


@cli.command(name="gain")
def gain_cmd() -> None:
    """Live-updating Rich HUD of token compression and dollar savings for
    the Tokens section (Ctrl+C to exit)."""
    _run_gain_live_panel()


@context_group.command(name="gain")
def context_gain_cmd() -> None:
    """Alias for `rush gain`: live Rich HUD of token compression and dollar
    savings (Ctrl+C to exit)."""
    _run_gain_live_panel()


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
    from rush.memory.preference_store import PreferenceStore, get_preference_readonly

    if set_persona:
        PreferenceStore().set("persona_style", set_persona)
        echo(f"Persona style set to: {set_persona}")
        return
    rush_dir = Path.cwd().resolve() / ".rush"
    if (
        not (rush_dir / "preferences.json").exists()
        and not (rush_dir / "memory.db").exists()
    ):
        # T27: a read never creates the preference or memory store.
        echo("Current persona style: terse (default; no preference store in .rush/)")
        return
    current = get_preference_readonly(rush_dir.parent, "persona_style", "terse")
    echo(f"Current persona style: {current}")


@cli.command(name="blast-radius")
@click.option("--path", "-p", required=True, help="Changed file path to analyze.")
@click.option("--depth", "-d", default=5, type=int, help="Maximum traversal depth.")
def blast_radius_cmd(path: str, depth: int) -> None:
    """Analyze downstream transitive blast radius and affected tests."""
    from rush.tools.blast_radius import BlastRadiusAnalyzer

    analyzer = BlastRadiusAnalyzer()
    try:
        report = analyzer.analyze([Path(path)], max_depth=depth)
    except ValueError as exc:
        raise click.BadParameter(str(exc), param_hint="'--path'") from exc
    echo(f"Blast Radius Impact: Risk={report.risk_score}")
    echo(
        f"  Affected Files ({len(report.affected_files)}): {', '.join(report.affected_files) or 'None'}"
    )
    echo(
        f"  Affected Routes ({len(report.affected_routes)}): {', '.join(report.affected_routes) or 'None'}"
    )
    echo(
        f"  Recommended Tests ({len(report.recommended_tests)}): {', '.join(report.recommended_tests) or 'None'}"
    )


@collection_route("violations")
@cli.command(name="arch-guard")
@click.option("--json", "as_json", is_flag=True, help=_JSON_LIST_HELP)
def arch_guard_cmd(as_json: bool) -> None:
    """Evaluate codebase against architectural layer boundary rules."""
    from rush.tools.arch_guard import ArchGuard

    res = ArchGuard().evaluate_boundaries()
    rows = res.get("violations") or []
    if as_json:
        echo_json(res)
    elif res["passed"]:
        echo("ArchGuard: All layer boundaries respected.")
    else:
        echo(
            f"ArchGuard: FAIL - {res['violations_count']} architectural boundary violations:",
            err=True,
        )
    if not as_json:
        echo_rows(
            rows,
            lambda item: (
                f"  {item['source_file']} ({item['source_layer']}) imports illegal layer {item['illegal_target_layer']}"
            ),
            err=True,
            empty="no illegal layer imports were found",
        )
    if not res["passed"]:
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
        echo(
            f"Error: {res.get('error', res.get('summary', 'test healing failed'))}",
            err=True,
        )
        sys.exit(1)
    if res.get("status") == "skipped":
        echo(res.get("summary", res.get("diagnosis", "Test healing skipped")))
        return
    echo(f"Test Heal Diagnostic: {res['test_path']}")
    echo(
        f"  Runs: {res['runs']} (Passes: {res['passes']}, Failures: {res['failures']})"
    )
    echo(
        f"  Status: {'FLAKY' if res['is_flaky'] else 'DETERMINISTIC'} - {res['diagnosis']}"
    )
    if res["suggested_fix"]:
        echo(f"  Fix:\n{res['suggested_fix']}")


@collection_route("breaking_changes")
@cli.command(name="api-diff")
@click.option("--base", "-b", default="main", help="Base Git ref to compare against.")
@click.option("--json", "as_json", is_flag=True, help=_JSON_LIST_HELP)
def api_diff_cmd(base: str, as_json: bool) -> None:
    """Detect breaking public API signature changes against base Git ref."""
    from rush.tools.api_diff import ApiDiffer

    res = ApiDiffer().diff_public_api(base_ref=base)
    rows = res.get("breaking_changes") or []
    if as_json:
        echo_json(res)
    elif res["passed"]:
        echo(f"ApiDiff: No breaking public API changes detected against '{base}'.")
    else:
        echo(
            f"ApiDiff: FAIL - {res['breaking_changes_count']} breaking API changes against '{base}':",
            err=True,
        )
    if not as_json:
        echo_rows(
            rows,
            lambda item: f"  {item['file']}: [{item['type']}] {item['details']}",
            err=True,
            empty="no public API changes were found",
        )
    if not res["passed"]:
        sys.exit(1)


@collection_route("drift_issues")
@cli.command(name="db-drift")
@click.option("--json", "as_json", is_flag=True, help=_JSON_LIST_HELP)
def db_drift_cmd(as_json: bool) -> None:
    """Audit ORM models against SQL migrations to detect unmigrated schema drift."""
    from rush.tools.db_drift import DbDriftAuditor

    res = DbDriftAuditor().audit_drift()
    rows = res.get("drift_issues") or []
    if as_json:
        echo_json(res)
    elif res["passed"]:
        echo("DbDrift: All ORM models are synchronized with migrations.")
    else:
        echo(
            f"DbDrift: FAIL - {res['drift_count']} schema drift hazards found:",
            err=True,
        )
    if not as_json:
        echo_rows(
            rows,
            lambda item: f"  {item['model']}: {item['details']}",
            err=True,
            empty="no schema drift was found",
        )
    if not res["passed"]:
        sys.exit(1)


@collection_route("candidates")
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
@click.option("--json", "as_json", is_flag=True, help=_JSON_LIST_HELP)
def simplify_cmd(file_path: str, max_complexity: int, as_json: bool) -> None:
    """Decompose high-complexity functions into clean helper sub-functions."""
    from rush.tools.simplify import ComplexityDecomposer

    decomposer = ComplexityDecomposer()
    res = decomposer.decompose_file(Path(file_path), max_complexity=max_complexity)
    if as_json:
        echo_json(res)
    elif "error" in res:
        echo(f"Error: {res['error']}", err=True)
    elif not res["needs_simplification"]:
        echo(
            f"Simplify: File '{file_path}' has clean complexity (<= {max_complexity})."
        )
    else:
        echo(
            f"Simplify: {res['complex_functions_count']} functions exceed complexity "
            f"threshold ({max_complexity}):"
        )
    if "error" in res:
        sys.exit(1)
    if not as_json:
        echo_rows(
            res.get("candidates") or [],
            lambda c: (
                f"  Line {c['line']} - '{c['function']}' (complexity {c['complexity']}): "
                f"{c['recommendation']}"
            ),
            empty="no functions exceed the complexity threshold",
        )


@collection_route("untyped_arguments")
@cli.command(name="strictify")
@click.option(
    "--file",
    "-f",
    "file_path",
    required=True,
    help="File path to analyze for untyped parameters.",
)
@click.option("--json", "as_json", is_flag=True, help=_JSON_LIST_HELP)
def strictify_cmd(file_path: str, as_json: bool) -> None:
    """Synthesize runtime type guards for unvalidated function arguments."""
    from rush.tools.strictify import TypeSynthesizer

    synth = TypeSynthesizer()
    res = synth.audit_and_synthesize(Path(file_path))
    if as_json:
        echo_json(res)
    elif "error" in res:
        echo(f"Error: {res['error']}", err=True)
    else:
        echo(
            f"Strictify: Found {res['untyped_count']} untyped parameters in '{file_path}':"
        )
    if "error" in res:
        sys.exit(1)
    if not as_json:
        echo_rows(
            res["untyped_arguments"],
            lambda u: (
                f"  Line {u['line']} - '{u['function']}' arg '{u['argument']}' "
                f"-> Guard: {u['suggested_guard']}"
            ),
            empty="no untyped arguments were found",
        )


@collection_route("matrix")
@cli.command(name="trace")
@click.option("--json", "as_json", is_flag=True, help=_JSON_LIST_HELP)
def trace_cmd(as_json: bool) -> None:
    """Scan codebase and specs to output requirement-to-test traceability matrix."""
    from rush.tools.trace import TraceScanner

    res = TraceScanner().scan_traceability()
    if as_json:
        echo_json(res)
        return
    echo(f"Traceability Matrix: {res['total_requirements']} requirements tracked.")
    echo_rows(
        res["matrix"],
        lambda item: (
            f"  {item['requirement']}: [{item['status']}] "
            f"Impls={len(item['implementations'])} Tests={len(item['tests'])}"
        ),
        empty="no requirement IDs were found",
    )


@collection_route("rows")
@cli.command(name="flight-recorder")
@click.option(
    "--replay", "-r", "session_id", default=None, help="Replay a specific session ID."
)
@click.option("--json", "as_json", is_flag=True, help=_JSON_LIST_HELP)
def flight_recorder_cmd(session_id: str | None, as_json: bool) -> None:
    """Record and replay agent JSON-RPC sessions."""
    from rush.invocation.targets import resolve_logical_root
    from rush.tools.flight_recorder import FlightRecorder

    # T10 (S10.5): status and replay are read-only and anchored at the logical root.
    recorder = FlightRecorder(resolve_logical_root(Path.cwd()), create=False)
    events: list[Any] = []
    if session_id:
        from rush.memory.store import MemoryStoreUnreadableError

        try:
            events = recorder.replay_session(session_id)
        except MemoryStoreUnreadableError as exc:
            raise click.ClickException(f"{exc.code}: {exc}") from exc
        title = (
            f"Flight Recorder: Replaying session '{session_id}' ({len(events)} events):"
        )
    elif recorder.flights_dir.is_dir():
        title = f"Flight Recorder: Active (recording to {recorder.flights_dir})."
    else:
        title = f"Flight Recorder: No recordings yet ({recorder.flights_dir} does not exist)."
    if as_json:
        echo_json({"session_id": session_id, "rows": events, "total": len(events)})
        return
    echo(title)
    echo_rows(
        events,
        lambda e: f"  [{e['timestamp']}] {e['event_type']}: {e['payload']}",
        empty="no events are recorded",
    )


@cli.command(name="swarm-merge")
@click.option(
    "--base",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to base file.",
)
@click.option(
    "--ours",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to ours file.",
)
@click.option(
    "--theirs",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to theirs file.",
)
def swarm_merge_cmd(base: str, ours: str, theirs: str) -> None:
    """Execute 3-way AST merge conflict resolution across concurrent agent changes."""
    from rush.tools.swarm_merge import SwarmMergeSolver

    solver = SwarmMergeSolver()
    b_code = Path(base).read_text(encoding="utf-8")
    o_code = Path(ours).read_text(encoding="utf-8")
    t_code = Path(theirs).read_text(encoding="utf-8")
    res = solver.merge_3way(b_code, o_code, t_code)
    if res["success"]:
        echo(
            f"SwarmMerge: Success - reconciled {res['functions_merged']} functions cleanly."
        )
    else:
        echo(f"SwarmMerge: FAIL - {res['error']}", err=True)
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
        echo(
            f"SimulateCI: Workflow '{workflow}' passed ({res['steps_executed']} steps)."
        )
    else:
        echo(
            f"SimulateCI: FAIL at step '{res['failed_step']}': {res['error']}", err=True
        )
        sys.exit(1)


@cli.command(name="attest")
@click.argument(
    "path",
    type=TargetPath(path_type=Path),
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
@result_view_options
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
    result_view: str | None,
    limit: int | None,
    max_bytes: int | None,
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
        view=ViewOptions(result_view, limit, max_bytes),
    )


@cli.command(name="license-matrix")
@click.argument(
    "path",
    type=TargetPath(path_type=Path),
    default=Path("."),
    required=False,
)
@permission_options
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
@result_view_options
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
    result_view: str | None,
    limit: int | None,
    max_bytes: int | None,
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
        view=ViewOptions(result_view, limit, max_bytes),
    )


@cli.command(name="iam-audit")
@click.argument(
    "path",
    type=TargetPath(path_type=Path),
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
@result_view_options
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
    result_view: str | None,
    limit: int | None,
    max_bytes: int | None,
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
        view=ViewOptions(result_view, limit, max_bytes),
    )


@collection_route("findings")
@cli.command(name="hallu-guard")
@click.option("--json", "as_json", is_flag=True, help=_JSON_LIST_HELP)
def hallu_guard_cmd(as_json: bool) -> None:
    """Audit codebase for hallucinated or phantom package imports."""
    from rush.tools.hallu_guard import HalluGuard

    res = HalluGuard().audit_codebase()
    rows = res.get("findings") or []
    if as_json:
        echo_json(res)
    elif res["passed"]:
        echo("HalluGuard: All AST imports grounded in installed packages or stdlib.")
    else:
        echo(
            f"HalluGuard: FAIL - {res['findings_count']} hallucinated import findings:",
            err=True,
        )
    if not as_json:
        echo_rows(
            rows,
            lambda item: f"  {item['file']}: {', '.join(item['violations'])}",
            err=True,
            cap=FINDINGS_CAP,
            noun="findings",
            empty="no ungrounded imports were found",
        )
    if not res["passed"]:
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
        echo(
            "Error: Passing capabilities via argv (--capability) is rejected. "
            "Capabilities must only be supplied via protected channels (stdin or descriptor).",
            err=True,
        )
        sys.exit(2)

    # 2. Reject environment variables
    env_cap = os.environ.get("RUSH_LOCK_CAPABILITY") or os.environ.get("CAPABILITY")
    if env_cap:
        echo(
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
            echo(
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
            echo(f"Error: Failed to read capability from stdin: {exc}", err=True)
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


def _held_lock_manager(path: Path, verb: str) -> Any:
    """T27: release/renew act only on an existing lock store; with none there
    is no lock to act on, so fail without creating `.rush/locks`."""
    from rush.mcp_mesh.lock_manager import MeshLockManager

    root = _resolve_project_root(path)
    locks_dir = root / ".rush" / "locks"
    if not locks_dir.is_dir():
        echo(
            f"Failed to {verb} lock for {path}: no lock store at {locks_dir}", err=True
        )
        sys.exit(1)
    return MeshLockManager(project_root=root)


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
        echo(f"Lock acquired for {path}")
        sys.exit(0)
    else:
        echo(f"Failed to acquire lock for {path}", err=True)
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
    cap_input, _raw_token = _resolve_cli_capability(
        agent_id, capability_argv, descriptor, from_stdin
    )
    mgr = _held_lock_manager(path, "release")
    ok = mgr.release(path, capability=cap_input, agent_id=agent_id)
    if ok:
        echo(f"Lock released for {path}")
        sys.exit(0)
    else:
        echo(f"Failed to release lock for {path}", err=True)
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
    cap_input, _raw_token = _resolve_cli_capability(
        agent_id, capability_argv, descriptor, from_stdin
    )
    mgr = _held_lock_manager(path, "renew")
    ok = mgr.renew(path, capability=cap_input, ttl_s=ttl_s)
    if ok:
        echo(f"Lock renewed for {path}")
        sys.exit(0)
    else:
        echo(f"Failed to renew lock for {path}", err=True)
        sys.exit(1)


@lock_cmd_group.command(name="inspect")
@click.argument("path", type=click.Path(path_type=Path))
def lock_inspect_cmd(path: Path) -> None:
    """Inspect lock status for target resource without acquiring or modifying."""
    from rush.mcp_mesh.lock_manager import MeshLockManager

    root = _resolve_project_root(path)
    res = MeshLockManager.inspect(root, path)
    echo(json.dumps(res, indent=2))


if __name__ == "__main__":
    cli()
