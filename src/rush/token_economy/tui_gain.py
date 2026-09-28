"""Rich TUI Dashboard for real-time Context Gain and Token Telemetry."""

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table


def build_gain_panel(project_root: Path | None = None) -> Panel:
    """Builds the Rich HUD panel from live `TelemetryStore` data. Reused by
    both the one-shot `render_gain_dashboard` CLI print and the persistent
    TUI's memory/gain toggle (P66-03) so both surfaces read the exact same
    real numbers -- never a duplicated, possibly-drifting copy.

    T10: read-only (no telemetry DB is ever created to render the HUD), and a
    missing `project_root` means the logical root of the cwd, never the cwd."""
    if project_root is None:
        from rush.invocation.targets import resolve_logical_root

        project_root = resolve_logical_root(Path.cwd())
    from rush.workflows.projects import root_token_usage

    usage = root_token_usage(project_root)
    stats = usage["estimated_avoided"]

    table = Table(title="Rush Context Intelligence Gain HUD", expand=True)
    table.add_column("Metric", style="cyan", justify="left")
    table.add_column("Value", style="green", justify="right")

    # Actual provider usage and tokenizer counts are measurements; everything
    # below them is the compression estimate. They are never summed together.
    provider = usage["provider_reported"]
    actual = provider["total_tokens"]
    table.add_row(
        "Actual Provider Usage (run manifests)",
        f"{actual:,}" if actual is not None else f"unavailable: {provider['reason']}",
    )
    tokenizer = usage["tokenizer_counted"]
    table.add_row(
        f"Tokenizer Counted ({tokenizer['encoding']})",
        f"{tokenizer['total_tokens']:,}",
    )
    if not stats.get("available", True):
        table.add_row("Compression Estimate", f"unavailable: {stats.get('reason')}")
    table.add_row("Total Events Logged", str(stats["events_count"]))
    table.add_row("Gross Raw Tokens", f"{stats['total_raw_tokens']:,}")
    table.add_row("Compressed Tokens Sent", f"{stats['total_compressed_tokens']:,}")
    table.add_row("Net Tokens Saved", f"{stats['net_tokens_saved']:,}")
    table.add_row("Compression Efficiency", f"{stats['compression_ratio'] * 100:.1f}%")
    table.add_row(
        "Est. Dollar Savings (Blended)", f"${stats['dollar_savings_est']:.4f}"
    )

    return Panel(
        table,
        title="[bold green]Context Gain Telemetry[/bold green]",
        subtitle="[dim]Powered by TOON, Skeletons & Distillers[/dim]",
    )


def render_gain_dashboard(
    project_root: Path | None = None, console: Console | None = None
) -> None:
    """Renders the Rich terminal HUD displaying token savings and dollar economy metrics."""
    console = console or Console()
    console.print(build_gain_panel(project_root))


render_gain_summary = render_gain_dashboard
