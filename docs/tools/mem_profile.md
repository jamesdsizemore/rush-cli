# Memory Profiler Tool (`rush mem-profile`)

## Overview
`rush mem-profile` audits Python source files for memory leaks and unclosed resource allocations (files, sockets, database handles) via static AST analysis, and optionally executes a dynamic subprocess memory tracing probe guarded by `--allow-slow`.

**Status: planned correction — implementation [Phase 64, P64-14](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md#p64-14--failed-target-profiles-are-failures-f15).** Current dynamic path can report success when the target process fails. Inspect child exit evidence; do not treat failed target execution as a completed profile.

## Usage

### CLI
```bash
uv run rush mem-profile PATH [--allow-slow] [--json]
```

### MCP
- **Tool Name:** `rush_mem_profile`
- **Parameters:** required `path` (str), required opaque `options` object, and common permission booleans defaulting to false. Current MCP schema exposes no top-level `dynamic` parameter.

## Inspection Scope
1. **Static AST Analysis**: Detects `open()`, `socket.socket()`, `sqlite3.connect()`, `urllib.request.urlopen()` called without a `with` context manager or without subsequent `.close()`.
2. **Dynamic Subprocess Probe**: Runs `tracemalloc` to measure peak memory footprint and allocation counts under live execution.

## Output Schema
Emits canonical `ToolResult`:
```json
{
  "tool": "mem-profile",
  "engine": "mem-profile",
  "engine_version": "1.0.0",
  "status": "ok",
  "duration_ms": 18,
  "summary": "mem-profile: Audited 12 file(s), 0 unclosed resource finding(s)",
  "findings": [],
  "metrics": {
    "files_audited": 12,
    "unclosed_resources_count": 0,
    "peak_memory_bytes": 0
  }
}
```

## Security & Permissions
- Static analysis executes purely in-process with read-only filesystem access.
- Dynamic subprocess execution is strictly gated behind `--allow-slow` permission.
