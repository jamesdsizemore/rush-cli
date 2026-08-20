"""Single-file interactive HTML report exporter for Rush results.

Generates self-contained, zero-dependency HTML artifacts suitable for human inspection,
AI coding agent review packets, and CI artifact archiving.
"""

from __future__ import annotations

import html

from .tools.base import ToolResult


def export_to_html(
    results: ToolResult | list[ToolResult],
    *,
    title: str = "Rush Quality & Verification Report",
    project_name: str = "rush-cli",
) -> str:
    """Render ToolResult(s) into a complete, standalone, self-contained HTML document."""
    if isinstance(results, dict):
        results_list = [results]
    else:
        results_list = list(results)

    total_tools = len(results_list)
    total_findings = sum(len(r.get("findings", []) or []) for r in results_list)
    total_duration = sum(r.get("duration_ms", 0) for r in results_list)

    # Status counts
    status_counts: dict[str, int] = {}
    for r in results_list:
        st = r.get("status", "ok")
        status_counts[st] = status_counts.get(st, 0) + 1

    findings_rows = []
    for r in results_list:
        tool_name = r.get("tool", "?")
        engine_name = r.get("engine") or "-"
        findings = r.get("findings", []) or []
        for f in findings:
            sev = f.get("severity", "info")
            path = html.escape(str(f.get("path", "")))
            line = f.get("line") or 0
            rule = html.escape(str(f.get("rule", "")))
            msg = html.escape(str(f.get("message", "")))
            fix = html.escape(str(f.get("fix", ""))) if f.get("fix") else ""

            sev_badge = f'<span class="badge badge-{sev}">{sev.upper()}</span>'
            fix_cell = (
                f"<code>{fix}</code>" if fix else '<span class="text-muted">-</span>'
            )

            findings_rows.append(
                f"""<tr>
                    <td><strong>{tool_name}</strong><br><small class="text-muted">{engine_name}</small></td>
                    <td>{sev_badge}</td>
                    <td><code>{path}:{line}</code></td>
                    <td><code>{rule}</code></td>
                    <td>{msg}</td>
                    <td>{fix_cell}</td>
                </tr>"""
            )

    tools_rows = []
    for r in results_list:
        t_name = html.escape(str(r.get("tool", "?")))
        e_name = html.escape(str(r.get("engine") or "-"))
        status = r.get("status", "ok")
        dur = r.get("duration_ms", 0)
        f_count = len(r.get("findings", []) or [])
        summary = html.escape(str(r.get("summary", "")))

        status_badge = f'<span class="badge badge-{status}">{status.upper()}</span>'
        tools_rows.append(
            f"""<tr>
                <td><strong>{t_name}</strong></td>
                <td><code>{e_name}</code></td>
                <td>{status_badge}</td>
                <td>{dur}ms</td>
                <td>{f_count}</td>
                <td>{summary}</td>
            </tr>"""
        )

    findings_table_html = (
        "".join(findings_rows)
        if findings_rows
        else "<tr><td colspan='6' class='text-center text-muted'>No findings recorded across all tool executions.</td></tr>"
    )
    tools_table_html = "".join(tools_rows)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title)}</title>
    <style>
        :root {{
            --bg: #0b0f19;
            --surface: #111827;
            --surface-hover: #1f2937;
            --border: #374151;
            --text: #f9fafb;
            --text-muted: #9ca3af;
            --cyan: #22d3ee;
            --green: #22ff88;
            --yellow: #ffe600;
            --pink: #ec4899;
            --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background: var(--bg);
            color: var(--text);
            font-family: var(--font);
            line-height: 1.5;
            padding: 2rem;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        header {{
            border-bottom: 1px solid var(--border);
            padding-bottom: 1.5rem;
            margin-bottom: 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        h1 {{ font-size: 1.8rem; color: var(--cyan); display: flex; align-items: center; gap: 0.5rem; }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        .stat-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 1.25rem;
        }}
        .stat-value {{ font-size: 2rem; font-weight: bold; color: var(--cyan); }}
        .stat-label {{ color: var(--text-muted); font-size: 0.875rem; text-transform: uppercase; letter-spacing: 0.05em; }}
        .card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            margin-bottom: 2rem;
            overflow: hidden;
        }}
        .card-header {{
            background: rgba(255, 255, 255, 0.03);
            border-bottom: 1px solid var(--border);
            padding: 1rem 1.5rem;
            font-size: 1.1rem;
            font-weight: 600;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            text-align: left;
        }}
        th, td {{
            padding: 0.75rem 1rem;
            border-bottom: 1px solid var(--border);
            font-size: 0.9rem;
        }}
        th {{
            background: rgba(0, 0, 0, 0.2);
            color: var(--text-muted);
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.75rem;
            letter-spacing: 0.05em;
        }}
        tr:hover {{ background: var(--surface-hover); }}
        code {{
            background: rgba(255, 255, 255, 0.08);
            padding: 0.15rem 0.35rem;
            border-radius: 4px;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            font-size: 0.85em;
        }}
        .badge {{
            display: inline-block;
            padding: 0.2rem 0.5rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 700;
            text-transform: uppercase;
        }}
        .badge-ok {{ background: rgba(34, 211, 238, 0.15); color: var(--cyan); border: 1px solid var(--cyan); }}
        .badge-warn {{ background: rgba(255, 230, 0, 0.15); color: var(--yellow); border: 1px solid var(--yellow); }}
        .badge-fail, .badge-error {{ background: rgba(236, 72, 153, 0.15); color: var(--pink); border: 1px solid var(--pink); }}
        .badge-skipped {{ background: rgba(156, 163, 175, 0.15); color: var(--text-muted); border: 1px solid var(--text-muted); }}
        .badge-info {{ background: rgba(34, 211, 238, 0.15); color: var(--cyan); }}
        .text-muted {{ color: var(--text-muted); }}
        .text-center {{ text-align: center; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1>⚡ {html.escape(title)}</h1>
                <p class="text-muted">Target: <code>{html.escape(project_name)}</code> · Generated by Rush CLI v0.2</p>
            </div>
            <div>
                <span class="badge badge-ok">Single-File Artifact</span>
            </div>
        </header>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{total_tools}</div>
                <div class="stat-label">Tools Executed</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{total_findings}</div>
                <div class="stat-label">Total Findings</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{total_duration}ms</div>
                <div class="stat-label">Execution Time</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{status_counts.get("ok", 0)}</div>
                <div class="stat-label">Clean Passes</div>
            </div>
        </div>

        <div class="card">
            <div class="card-header">Tool Execution Overview</div>
            <table>
                <thead>
                    <tr>
                        <th>Tool</th>
                        <th>Engine</th>
                        <th>Status</th>
                        <th>Duration</th>
                        <th>Findings</th>
                        <th>Summary</th>
                    </tr>
                </thead>
                <tbody>
                    {tools_table_html}
                </tbody>
            </table>
        </div>

        <div class="card">
            <div class="card-header">Detailed Findings & Suggested Fixes</div>
            <table>
                <thead>
                    <tr>
                        <th>Tool</th>
                        <th>Severity</th>
                        <th>Location</th>
                        <th>Rule ID</th>
                        <th>Message</th>
                        <th>Suggested Fix</th>
                    </tr>
                </thead>
                <tbody>
                    {findings_table_html}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""
