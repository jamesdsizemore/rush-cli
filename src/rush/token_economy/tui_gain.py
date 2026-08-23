"""Rich TUI Dashboard for real-time Context Gain and Token Telemetry."""

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.rush.token_economy.telemetry import TelemetryStore


def render_gain_dashboard(
    project_root: Path | None = None, console: Console | None = None
) -> None:
    """Renders the Rich terminal HUD displaying token savings and dollar economy metrics."""
    store = TelemetryStore(project_root)
    stats = store.get_summary()
    console = console or Console()

    table = Table(title="Rush Context Intelligence Gain HUD", expand=True)
    table.add_column("Metric", style="cyan", justify="left")
    table.add_column("Value", style="green", justify="right")

    table.add_row("Total Events Logged", str(stats["events_count"]))
    table.add_row("Gross Raw Tokens", f"{stats['total_raw_tokens']:,}")
    table.add_row("Compressed Tokens Sent", f"{stats['total_compressed_tokens']:,}")
    table.add_row("Net Tokens Saved", f"{stats['net_tokens_saved']:,}")
    table.add_row("Compression Efficiency", f"{stats['compression_ratio'] * 100:.1f}%")
    table.add_row(
        "Est. Dollar Savings (Blended)", f"${stats['dollar_savings_est']:.4f}"
    )

    panel = Panel(
        table,
        title="[bold green]Context Gain Telemetry[/bold green]",
        subtitle="[dim]Powered by TOON, Skeletons & Distillers[/dim]",
    )
    console.print(panel)
