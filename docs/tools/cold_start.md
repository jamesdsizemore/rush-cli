# Cold Start Tool (`rush cold-start`)

## Overview
`rush cold-start` inventories top-level module imports via static AST analysis to identify heavy dependencies that degrade CLI startup latency. It also supports dynamic `-X importtime` tracing when authorized with `--allow-slow` per D50-14.

## Usage

### CLI
```bash
rush cold-start [PATH] [--allow-slow] [--json]
```

### MCP
- **Tool Name:** `rush_cold_start`
- **Parameters:**
  - `path` (str): Target Python file or repository path to audit.
  - `dynamic` (bool, optional): Execute `-X importtime` measurement.
  - `allow_slow` (bool): Required when dynamic timing is requested.

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
