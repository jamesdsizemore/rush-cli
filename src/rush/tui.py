"""Rich Interactive Terminal UI for Finding Exploration.

Architecture §8, Phase 27.
"""

from __future__ import annotations

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from rush.tools.base import ToolResult


def build_tui_layout(results: list[ToolResult]) -> Layout:
    """Construct a full-screen Rich Layout hierarchy for results exploration."""
    layout = Layout()

    # Split top-level into Header, Main, Footer
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="main", ratio=1),
        Layout(name="footer", size=3),
    )

    # Header
    header_text = Text("⚡ Rush Interactive Quality Explorer", style="bold cyan")
    layout["header"].update(Panel(header_text, style="cyan"))

    # Split Main into Left (Tool Tree) and Right (Finding Feed)
    layout["main"].split_row(
        Layout(name="tree", ratio=1),
        Layout(name="details", ratio=2),
    )

    # Tool Tree
    tree = Tree("📋 [bold]Evaluation Results[/bold]")
    for r in results:
        status_style = (
            "green"
            if r["status"] == "ok"
            else ("yellow" if r["status"] == "warn" else "red")
        )
        tool_branch = tree.add(
            f"[{status_style}]{r['tool']}[/{status_style}] ({r['status']})"
        )
        for f in (r.get("findings") or [])[:5]:
            tool_branch.add(
                f"[dim]{f.get('file', '')}:{f.get('line', '')}[/dim] - {f.get('message', '')}"
            )
    layout["tree"].update(Panel(tree, title="Tools", style="blue"))

    # Finding Table
    table = Table(expand=True)
    table.add_column("Tool", style="cyan", width=12)
    table.add_column("File:Line", style="dim", width=24)
    table.add_column("Severity", style="bold", width=10)
    table.add_column("Message", style="white")

    for r in results:
        for f in r.get("findings") or []:
            sev = f.get("severity", "info")
            sev_style = (
                "red" if sev == "error" else ("yellow" if sev == "warn" else "blue")
            )
            table.add_row(
                r["tool"],
                f"{f.get('file', '')}:{f.get('line', '')}",
                f"[{sev_style}]{sev}[/{sev_style}]",
                f.get("message", ""),
            )

    layout["details"].update(Panel(table, title="Finding Stream", style="green"))

    # Footer
    footer_text = Text("Press Ctrl+C or 'q' to exit | Rush v0.2.0", style="dim")
    layout["footer"].update(Panel(footer_text, style="grey50"))

    return layout


def launch_interactive_tui(results: list[ToolResult]) -> None:
    """Render the interactive Rich TUI to stdout."""
    console = Console()
    layout = build_tui_layout(results)
    console.print(layout)
