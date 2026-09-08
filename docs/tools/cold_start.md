# Cold Start Tool (`rush cold-start`)

## Overview
`rush cold-start` inventories top-level module imports via static AST analysis to identify heavy dependencies that degrade CLI startup latency. It also supports dynamic `-X importtime` tracing when authorized with `--allow-slow` per D50-14.

**Status: planned correction — implementation [Phase 64, P64-14](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md#p64-14--failed-target-profiles-are-failures-f15).** Current dynamic path can report success when the target process fails. Inspect child exit evidence; do not treat failed target execution as completed import timing.

## Usage

### CLI
```bash
uv run rush cold-start PATH [--allow-slow] [--json]
```

### MCP
- **Tool Name:** `rush_cold_start`
- **Parameters:** required `path` (str), required opaque `options` object, and common permission booleans defaulting to false. Current MCP schema does not expose a top-level `dynamic` parameter.

## Inspection Scope
1. **Static AST Analysis**: Detects heavy libraries (e.g. `torch`, `pandas`, `transformers`, `playwright`, `boto3`, `google.cloud`) imported at module top-level and recommends moving them to lazy function-level imports.
2. **Wildcard Detection**: Detects `from module import *` patterns.
3. **Dynamic Importtime**: Executes Python `-X importtime` to measure cumulative and self import latency per module.

## Output Schema
Emits canonical `ToolResult`:
```json
{
  "tool": "cold-start",
  "engine": "cold-start",
  "engine_version": "1.0.0",
  "status": "ok",
  "duration_ms": 14,
  "summary": "cold-start: Audited 8 file(s), 42 import(s), 0 heavy top-level import(s)",
  "findings": [],
  "metrics": {
    "files_audited": 8,
    "total_imports": 42,
    "heavy_imports_count": 0
  }
}
```

## Security & Permissions
- Static analysis is strictly read-only and in-process.
- Dynamic `-X importtime` subprocess runs require `--allow-slow` permission.
