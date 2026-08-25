# Result and exit-code reference

## Provider-resume outcomes

Provider resume returns canonical `ToolResult`: `ok` only for a successful supported CLI process; `skipped` for deferred, unavailable, or denied routes; and `error` for a failed process. The result metadata names only provider ID, transport, and state; it never includes provider stdout/stderr, credentials, or full historical handoff content.

## Continuity outcome rules

The `continuity` tool uses `ok` for successful save/list/restore and empty lists, `skipped` for a denied save or absent checkpoint, and `error` for invalid operations or checkpoint names. `metadata.execution` shows that only the save operation requested cache-write permission. Save/restore additionally return `metadata.handoff`: redacted current goal/open work, `historic_instruction` as quarantined `historical_evidence`, dependency snapshots with `freshness`, and a failure receipt or tombstone; CLI and MCP use the same statuses and fields.

Context operations use `ok` for a bounded pack or recovered handle and `skipped` for insufficient budget or a missing handle. Their `metadata.context_envelope` identifies selected evidence, local token values, omissions, and recovery state.

Coordination uses `ok` only for available ownership, conflict-free preview, or available recovery evidence. It uses `skipped` for held/stale ownership, overlapping merge edits, and missing/corrupt replay evidence. `metadata.coordination` is receipt data only and contains no source merge, failed patch, or executable replay event.

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
      "fingerprint": "stable-derived-sha256",
      "path": "src/app.py",
      "line": 8,
      "column": 1,
      "end_line": null,
      "end_column": null,
      "rule": "F401",
      "severity": "warn",
      "message": "imported but unused",
      "fix": null,
      "provenance": "lint/ruff",
      "freshness": "unknown"
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
| `metadata` | optional execution context such as dry-run, Graft state, or `execution` metadata (`mode`: `imported`/`executed`/`skipped`, `requested_permissions`, `granted_permissions`, `producer`, `report_path`). Review aggregation records serial mode, child tool/engine/status summaries, and whether skipped/error children make the result partial; it never substitutes a clean status for those child states. |
| `review_kind`, `review_provider` | review-only fields; provider remains null unless the stub path is activated. |

## Finding fields

A finding always has path, line, rule, severity, and message values after normalization. It may include column/end coordinates, a fix description, provenance, a deterministic redaction-safe SHA-256 `fingerprint`, and `freshness`. Direct review findings also carry a local `evidence` source-location packet when no engine/Graft evidence exists; it contains only the already-reported path and line. Direct review evidence is `unknown` unless an internal caller supplies an explicit in-memory fingerprint baseline; then review aggregation labels it `existing` or `new`. Rush exposes no baseline-file write/update command in this release. Messages are redacted for obvious secret assignments and output is bounded.

## Status versus finding severity

Result status describes the whole operation. Finding severity (`info`, `warn`, `error`) describes one record. An advisory review can return `warn` while containing informational findings.

## Exit codes

| Result | Exit code | Automation meaning |
|---|---:|---|
| `ok` | 0 | completed cleanly |
| `warn` | 1 | completed with advisory evidence |
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
