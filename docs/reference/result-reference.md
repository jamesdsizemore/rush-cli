# Result and exit-code reference

Every CLI and MCP operation returns the same canonical ToolResult shape.

```json
{
  "tool": "lint",
  "engine": "ruff+eslint",
  "engine_version": null,
  "status": "warn",
  "duration_ms": 41,
  "summary": "lint [ruff+eslint]: 2 finding(s)",
  "findings": [
    {
      "id": "stable-derived-id",
      "path": "src/app.py",
      "line": 8,
      "column": 1,
      "end_line": null,
      "end_column": null,
      "rule": "F401",
      "severity": "warn",
      "message": "imported but unused",
      "fix": null,
      "provenance": "lint/ruff"
    }
  ],
  "raw": null
}
```

## ToolResult fields

| Field | Meaning |
|---|---|
| `tool` | Rush command name. |
| `engine` | Producing helper or `+`-joined aggregate; may be `null`. |
| `engine_version` | Detected version when available; may be `null`. |
| `status` | `ok`, `warn`, `fail`, `error`, or `skipped`. |
| `duration_ms` | measured elapsed milliseconds. |
| `summary` | concise explanation intended for people and automation logs. |
| `findings` | normalized issue objects in deterministic order. |
| `raw` | bounded engine-native detail or `null`; do not build stable automation around engine-specific raw shapes. |
| `metrics` | optional numeric/string measurements. |
| `artifacts` | optional paths to generated/imported artifacts. |
| `metadata` | optional execution context such as dry-run or Graft state. |
| `review_kind`, `review_provider` | review-only fields; provider remains null unless the stub path is activated. |

## Finding fields

A finding always has path, line, rule, severity, and message values after normalization. It may include column/end coordinates, a fix description, provenance, and a stable derived ID. Messages are redacted for obvious secret assignments and output is bounded.

## Status versus finding severity

Result status describes the whole operation. Finding severity (`info`, `warn`, `error`) describes one record. An advisory review can return `warn` while containing informational findings.

## Exit codes

| Result | Exit code | Automation meaning |
|---|---:|---|
| `ok` | 0 | completed cleanly |
| `warn` | 0 | completed with advisory evidence |
| `skipped` | 0 | did not run or had nothing applicable; inspect JSON |
| `fail` | 1 | completed and failed criteria |
| `error` | 2 | execution/reporting failure |

Example strict check:

```bash
result="$(rush lint . --json)"
printf '%s\n' "$result"
python -c 'import json,sys; s=json.load(sys.stdin)["status"]; raise SystemExit(0 if s=="ok" else 1)' <<<"$result"
```

Adapt shell syntax to your platform. Preserve the JSON in CI artifacts when it helps debugging, but never publish sensitive raw scanner output.
