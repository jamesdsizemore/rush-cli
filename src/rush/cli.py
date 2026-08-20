"""click CLI entrypoint — 5 subcommands + `mcp serve`.

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
from .theme import render_result
from .tools import ALL_TOOLS
from .tools.base import ToolFn


def _run_tool(
    tool_name: str, path: Path, *, as_json: bool, extra_kwargs: dict | None = None
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
    # Use the .run() entry point so the CLI can pass config without
    # leaking it into the MCP-exposed __call__ signature.
    result = tool.run(path, config=config, **kwargs)
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
    @click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
    def command(path: Path, as_json: bool) -> None:
        _run_tool(tool.name, path, as_json=as_json)

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

    result = inspect_capabilities(path)
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
    except ValueError as error:
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
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def review(path, use_llm: bool, use_graft: bool, as_json: bool) -> None:
    """Review code for deterministic heuristics. Maturity: real adapter."""
    _run_tool(
        "review",
        path,
        as_json=as_json,
        extra_kwargs={"use_llm": use_llm, "use_graft": use_graft},
    )


@cli.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--check", "check_only", is_flag=True, help="Only check; don't modify files."
)
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON.")
def format(path, check_only: bool, as_json: bool) -> None:
    """Format Python and JS/TS safely. Maturity: real adapter."""
    _run_tool(
        "format",
        path,
        as_json=as_json,
        extra_kwargs={"check": check_only} if check_only else None,
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


for _catalog_tool in ALL_TOOLS:
    if _catalog_tool.name not in {"review", "format"}:
        cli.add_command(build_catalog_path_command(_catalog_tool))


if __name__ == "__main__":
    cli()
