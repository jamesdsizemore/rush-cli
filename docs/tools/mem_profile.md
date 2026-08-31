# Memory Profiler Tool (`rush mem-profile`)

## Overview
`rush mem-profile` audits Python source files for memory leaks and unclosed resource allocations (files, sockets, database handles) via static AST analysis, and optionally executes a dynamic subprocess memory tracing probe guarded by `--allow-slow`.

## Usage

### CLI
```bash
rush mem-profile [PATH] [--allow-slow] [--json]
```

### MCP
- **Tool Name:** `rush_mem_profile`
- **Parameters:**
  - `path` (str): Target Python file or directory to profile.
  - `dynamic` (bool, optional): Enable dynamic subprocess memory tracing.
  - `allow_slow` (bool): Required when `dynamic=True` is requested.

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
