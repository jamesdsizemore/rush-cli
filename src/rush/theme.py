"""Neon palette + rich style helpers.

Architecture §9, requirement C8.
- CYAN   #22D3EE — primary, ok
- GREEN  #22FF88 — secondary, active
- YELLOW #FFE600 — tertiary, review-needed, warn
- PINK   #EC4899 — failed status only (bright, not red)
- GREY   #6B7280 — skipped, muted

Red is banned. Yellow is allowed (review-needed / warnings).
"""

from rich.console import Console
from rich.style import Style
from rich.theme import Theme

CYAN = "#22D3EE"
GREEN = "#22FF88"
YELLOW = "#FFE600"
PINK = "#EC4899"
GREY = "#6B7280"

RUSH_THEME = Theme({
    "status.ok": Style(color=CYAN),
    "status.warn": Style(color=YELLOW),
    "status.fail": Style(color=PINK, bold=True),
    "status.error": Style(color=PINK, bold=True),
    "status.skipped": Style(color=GREY),
    "severity.info": Style(color=CYAN),
    "severity.warn": Style(color=YELLOW),
    "severity.error": Style(color=PINK),
    "tool.review": Style(color=GREEN),
    "tool.lint": Style(color=CYAN),
    "tool.format": Style(color=GREEN),
    "tool.test": Style(color=CYAN),
    "tool.security": Style(color=YELLOW),
})

_shared_console: Console | None = None


def console() -> Console:
    """Return a shared Console wired to the rush theme.

    NB: stdout-bound by default. For MCP contexts, call with ``force_terminal=False``
    and capture output via rich's file= argument — never write to stdout except
    the final ToolResult JSON.
    """
    global _shared_console
    if _shared_console is None:
        _shared_console = Console(theme=RUSH_THEME)
    return _shared_console


def render_result(result: dict) -> None:
    """Human-facing rich render of a ToolResult. CLI-only (requirement C4 — MCP returns raw JSON).

    Phase 3 stub: prints one summary line + a findings table if any.
    Phase 4/5 will expand this to per-tool glyphs and richer formatting.
    """
    from rich.table import Table

    tool = result.get("tool", "?")
    status = result.get("status", "?")
    summary = result.get("summary", "")
    findings = result.get("findings", []) or []

    c = console()
    glyph = {
        "review": "⚡",
        "lint": "✓",
        "format": "�",
        "test": "▶",
        "security": "⛨",
    }.get(tool, "•")
    c.print(f"{glyph} [{tool}.{tool}] [{status}.{status}] {summary}")

    if findings:
        t = Table(show_header=True, header_style="bold")
        t.add_column("path", style="dim")
        t.add_column("line", justify="right")
        t.add_column("rule")
        t.add_column("severity")
        t.add_column("message")
        for f in findings[:50]:  # cap render at 50
            sev = f.get("severity", "info")
            t.add_row(
                str(f.get("path", "")),
                str(f.get("line", "")),
                str(f.get("rule", "")),
                f"[severity.{sev}]{sev}[/]",
                str(f.get("message", ""))[:120],
            )
        c.print(t)
        if len(findings) > 50:
            c.print(f"[dim]... and {len(findings) - 50} more[/dim]")
