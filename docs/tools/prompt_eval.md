# Prompt Evaluation Tool (`rush prompt-eval`)

## Overview
`rush prompt-eval` evaluates recorded golden task execution records against deterministic acceptance criteria (action sequence match, patch match, token/cost budgets, pass rates, and baseline deltas). Per D50-10, live model execution is deferred to a future AI evaluation phase; this tool provides a fast, deterministic offline evaluation matrix for coding agents.

## Usage

### CLI
```bash
rush prompt-eval [PATH] [--pass-rate-threshold <float>] [--max-tokens <int>] [--max-cost <float>] [--json]
```

### MCP
- **Tool Name:** `rush_prompt_eval`
- **Parameters:**
  - `path` (str): Path to JSON/JSONL file or directory containing golden evaluation run records.
  - `pass_rate_threshold` (float, optional): Minimum pass rate required (default: 1.0).
  - `max_tokens_threshold` (int, optional): Token budget limit.
  - `max_cost_threshold` (float, optional): Cost budget limit.

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
