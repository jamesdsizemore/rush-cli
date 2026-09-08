# Prompt Evaluation Tool (`rush prompt-eval`)

## Overview
`rush prompt-eval` evaluates recorded golden task execution records against deterministic acceptance criteria (action sequence match, patch match, token/cost budgets, pass rates, and baseline deltas). Per D50-10, live model execution is deferred to a future AI evaluation phase; this tool provides a fast, deterministic offline evaluation matrix for coding agents.

## Usage

### CLI
```bash
uv run rush prompt-eval PATH [--json]
```

### MCP
- **Tool Name:** `rush_prompt_eval`
- **Parameters:** required `path` (str), required opaque `options` object, and common permission booleans defaulting to false. Current CLI exposes no threshold options, and current MCP schema does not expose their inner names.

## Evaluation Criteria
1. **Sequence Match**: Exact ordered matching of executed tool/step names against golden expectations.
2. **Patch Match**: Comparison of generated code patches/diffs against golden patch fixtures.
3. **Budget Verification**: Enforcement of token and cost bounds across runs.
4. **Pass Rate Matrix**: Calculation of pass rate percentage and baseline deltas.

## Output Schema
Emits canonical `ToolResult` with metrics:
```json
{
  "tool": "prompt-eval",
  "engine": "prompt-eval",
  "engine_version": "1.0.0",
  "status": "ok",
  "duration_ms": 12,
  "summary": "prompt-eval: 5/5 golden task(s) passed (100.0%), 1250 tokens, $0.0150",
  "findings": [],
  "metrics": {
    "total_runs": 5,
    "passed_runs": 5,
    "failed_runs": 0,
    "pass_rate": 1.0,
    "total_tokens": 1250,
    "total_cost": 0.015
  }
}
```

## Security & Permissions
- Zero network access required.
- Operates entirely offline on recorded fixtures.
