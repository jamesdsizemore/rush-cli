# TUI Diff Tool (`rush tui-diff`)

## Overview
`rush tui-diff` computes finding regressions and resolutions across Git commits and tool execution runs, rendering a structured Rich terminal table for human developers and raw JSON delta structures over FastMCP per D50-16.

## Usage

### CLI
```bash
rush tui-diff [PATH] [--base-ref <git_ref>] [--json]
```

### MCP
- **Tool Name:** `rush_tui_diff`
- **Parameters:**
  - `path` (str): Target repository path.
  - `base_ref` (str, optional): Git base ref (default: `HEAD~1`).
  - `base_findings` (list, optional): Previous findings list to diff against.
  - `current_findings` (list, optional): Current findings list.

## Delta Computation
1. **New Findings / Regressions**: Findings in current run that were not present in base. Emits findings with rule `tui-diff/new-finding-regression`.
2. **Resolved Findings**: Findings in base that have been fixed in the current run.
3. **Unchanged Findings**: Persistent findings present across both revisions.

## Output Schema
Emits canonical `ToolResult`:
```json
{
  "tool": "tui-diff",
  "engine": "tui-diff",
  "engine_version": "1.0.0",
  "status": "ok",
  "duration_ms": 19,
  "summary": "tui-diff: 0 new regression(s), 2 resolved, 5 unchanged finding(s)",
  "findings": [],
  "metrics": {
    "new_findings_count": 0,
    "resolved_findings_count": 2,
    "unchanged_findings_count": 5
  },
  "raw": {
    "new_findings": [],
    "resolved_findings": [...],
    "unchanged_findings": [...],
    "diff_stat": "..."
  }
}
```

## Security & Permissions
- Read-only Git execution and in-memory diff calculation.
