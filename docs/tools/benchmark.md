# Benchmark Regression Guard Tool (`rush benchmark check`)

## Overview
`rush benchmark` provides sample comparison against performance baselines recorded in `.rush/baselines.json` with percentage threshold enforcement per D50-17. Recording baseline metrics requires explicit `--allow-cache-write` authorization.

## Usage

### CLI
```bash
# Check current samples against baseline
uv run rush benchmark check [PATH] [--threshold <percentage>] [--json]

# Record new baseline into .rush/baselines.json
uv run rush benchmark check [PATH] --record --allow-cache-write [--json]
```

### MCP
- **Tool Name:** `rush_benchmark`
- **Parameters:** required `path` (str), required opaque `options` object, and common permission booleans defaulting to false. Current MCP schema does not expose or document inner `options` fields; do not invent them.

## Capabilities
1. **Descriptive Sample Comparison**: Computes mean, median, min, max of current run samples vs baseline mean.
2. **Threshold Guard**: Emits finding `benchmark/performance-regression` if percentage degradation exceeds `--threshold`.
3. **Contained Baseline Persistence**: Writes `.rush/baselines.json` with `--allow-cache-write`.

## Output Schema
Emits canonical `ToolResult`:
```json
{
  "tool": "benchmark",
  "engine": "benchmark",
  "engine_version": "1.0.0",
  "status": "ok",
  "duration_ms": 11,
  "summary": "benchmark: Evaluated 5 sample(s) against 'default' baseline: +1.20% delta (PASS)",
  "findings": [],
  "metrics": {
    "current_mean": 101.2,
    "baseline_mean": 100.0,
    "regression_pct": 1.2,
    "threshold_percent": 5.0
  }
}
```

## Security & Permissions
- Evaluation runs read-only against existing baselines.
- Persisting baseline changes to `.rush/baselines.json` strictly requires `--allow-cache-write` permission.
