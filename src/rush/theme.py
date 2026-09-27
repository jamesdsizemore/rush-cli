"""Neon palette + rich style helpers.

Architecture §9, requirement C8.
- CYAN   #22D3EE — primary, ok
- GREEN  #22FF88 — secondary, active
- YELLOW #FFE600 — tertiary, review-needed, warn
- PINK   #EC4899 — failed status only (bright, not red)
- GREY   #6B7280 — skipped, muted

Red is banned. Yellow is allowed (review-needed / warnings).
"""

from __future__ import annotations

import re
from typing import Any

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.style import Style
from rich.table import Table
from rich.theme import Theme

CYAN = "#22D3EE"
GREEN = "#22FF88"
YELLOW = "#FFE600"
PINK = "#EC4899"
GREY = "#6B7280"

RUSH_THEME = Theme(
    {
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
    }
)

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


_STATUS_GLYPHS = {
    "ok": "✓",
    "warn": "!",
    "fail": "✗",
    "error": "✗",
    "skipped": "–",
}


def _styled(prefix: str, value: Any) -> str:
    """`value` as literal text, in the theme's `<prefix>.<value>` style only
    when that style exists -- never an unescaped markup tag."""
    text = escape(str(value))
    if f"{prefix}.{value}" in RUSH_THEME.styles:
        return f"[{prefix}.{value}]{text}[/]"
    return text


def render_result(result: dict) -> None:
    """Human-facing rich render of a ToolResult. CLI-only (requirement C4 — MCP returns raw JSON)."""
    tool = result.get("tool", "?")
    status = result.get("status", "?")
    summary = result.get("summary", "")
    findings = result.get("findings", []) or []

    c = console()
    # T9/S9.8: the glyph is derived from status (never a success mark for
    # skipped work), the status word is printed, and every engine- or
    # user-supplied string is escaped so it renders literally.
    c.print(
        f"{_STATUS_GLYPHS.get(status, '•')} {escape(str(tool))} "
        f"{_styled('status', status)} {escape(str(summary))}"
    )

    if findings:
        t = Table(show_header=True, header_style="bold")
        t.add_column("path", style="dim")
        t.add_column("line", justify="right")
        t.add_column("rule")
        t.add_column("severity")
        t.add_column("message")
        has_any_fix = any(bool(f.get("fix")) for f in findings)
        if has_any_fix:
            t.add_column("fix", style="italic dim")

        for f in findings[:50]:  # cap render at 50
            sev = f.get("severity", "info")
            fix_val = f.get("fix")
            fix_str = str(fix_val)[:40] if fix_val else ""
            t.add_row(
                escape(str(f.get("path", ""))),
                escape(str(f.get("line", ""))),
                escape(str(f.get("rule", ""))),
                _styled("severity", sev),
                escape(str(f.get("message", ""))[:120]),
                *([escape(fix_str)] if has_any_fix else []),
            )
        c.print(t)
        if len(findings) > 50:
            c.print(f"[dim]... and {len(findings) - 50} more[/dim]")


def render_dashboard(results: list[dict[str, Any]]) -> None:
    """Render a comprehensive interactive multi-tool execution dashboard."""
    c = console()
    t = Table(
        title="⚡ Rush Quality & Verification Dashboard",
        show_header=True,
        header_style="bold",
    )
    t.add_column("Tool", style="bold")
    t.add_column("Engine", style="dim")
    t.add_column("Status", justify="center")
    t.add_column("Duration", justify="right")
    t.add_column("Findings", justify="right")
    t.add_column("Summary")

    total_findings = 0
    total_duration = 0

    for r in results:
        tool = r.get("tool", "?")
        engine = r.get("engine") or "-"
        status = r.get("status", "ok")
        duration = r.get("duration_ms", 0)
        findings = r.get("findings", []) or []
        summary = r.get("summary", "")

        total_findings += len(findings)
        total_duration += duration

        t.add_row(
            tool,
            engine,
            f"[{status}.{status}]{status.upper()}[/]",
            f"{duration}ms",
            str(len(findings)),
            summary[:80],
        )

    c.print(Panel(t, border_style=CYAN))
    c.print(
        f"[dim]Total tools executed: {len(results)} | Total duration: {total_duration}ms | Total findings: {total_findings}[/dim]"
    )


# X3 (T28): ESC-introduced sequences (CSI, OSC to BEL/ST, and 2-byte ESC
# forms), then any remaining C0/C1 control byte except tab/newline.
_TERMINAL_SEQUENCE = re.compile(
    r"\x1b\[[0-?]*[ -/]*[@-~]"
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)?"
    r"|\x1b[@-_]?"
    r"|[\x00-\x08\x0b-\x1f\x7f-\x9f]"
)


def safe_terminal_text(value: object) -> str:
    """X3: any dynamic value made safe for a terminal -- escape/control
    sequences removed. Callers put the result in a `rich.text.Text` (never
    markup), so `[...]` in the value is shown literally."""
    return _TERMINAL_SEQUENCE.sub("", "" if value is None else str(value))
