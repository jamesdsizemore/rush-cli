# JSON Schema & Output Specification

## Continuity `ToolResult`

`continuity` returns `tool`, `engine`, `engine_version`, `status`, `duration_ms`, `summary`, `findings`, `raw`, `artifacts`, and `metadata`. `metadata.operation` identifies `save`, `list`, or `restore`; `metadata.execution` records requested and granted permissions. A saved or restored receipt appears at `metadata.handoff` with `version`, `current_goal`, `open_work`, `historic_instruction`, `dependencies`, `freshness`, `failure_receipt`, and `redaction_count`. `historic_instruction` is only `{authority: "historical_evidence", state: "quarantined", present}`; receipt failures expose a fingerprint/redacted error or an explicit tombstone, never a failed patch. Empty lists are `ok`; missing checkpoints and denied saves are `skipped`.

For `context_pack` and `context_retrieve`, `metadata.context_envelope` contains `selected_evidence`, `tokens` (`estimated`, `actual`, `budget`), `omissions`, and `recovery`. `actual` is `null` unless a local measurement exists; missing recovery is explicit and an insufficient budget is `skipped`.

For coordination operations, `metadata.coordination` contains a state and only safe receipt fields. A stale lock includes `{state: "stale", owner, action: "manual_recovery_required"}`; an overlapping merge includes `{state: "merge_conflict", conflicts, action: "manual_reconciliation_required"}`. Recovery nests replay counts and a redacted failure receipt; it never includes replay payloads or failed patches.

For `provider_resume`, `metadata.provider_route` is `{provider_id, transport, state}`. Direct CLI completion is `state: "completed"`; a missing profile, checkpoint, permission, unsupported route, or deferred route is structured `skipped`. Provider process output and credential values are never included in the `ToolResult`.

Rush produces standardized, machine-readable JSON output for all 38 tools when invoked with `--json` or via FastMCP.

---

## 1. ToolResult Schema Specification

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ToolResult",
  "type": "object",
  "required": [
    "tool",
    "engine",
    "engine_version",
    "status",
    "duration_ms",
    "summary",
    "findings",
    "raw"
  ],
  "properties": {
    "tool": {
      "type": "string",
      "description": "Name of the Rush tool (e.g. lint, security, ai-eval)"
    },
    "engine": {
      "type": ["string", "null"],
      "description": "Name of the engine or multi-engine aggregate (e.g. ruff+eslint)"
    },
    "engine_version": {
      "type": ["string", "null"],
      "description": "Detected version string of the engine"
    },
    "status": {
      "type": "string",
      "enum": ["ok", "warn", "fail", "error", "skipped"],
      "description": "Overall status of the tool execution"
    },
    "duration_ms": {
      "type": "integer",
      "minimum": 0,
      "description": "Execution duration in milliseconds"
    },
    "summary": {
      "type": "string",
      "description": "Concise, human-readable summary message"
    },
    "findings": {
      "type": "array",
      "items": { "$ref": "#/$defs/Finding" },
      "description": "List of normalized issue findings"
    },
    "raw": {
      "description": "Optional raw engine output for debugging"
    },
    "metrics": {
      "type": "object",
      "description": "Numeric or string metric measurements (e.g. complexity, memory, lines)"
    },
    "artifacts": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Paths to generated or imported artifact files"
    },
    "metadata": {
      "type": "object",
      "description": "Execution context and permission metadata"
    }
  },
  "$defs": {
    "Finding": {
      "type": "object",
      "required": ["fingerprint", "path", "line", "rule", "severity", "message", "provenance", "freshness"],
      "properties": {
        "fingerprint": { "type": "string" },
        "path": { "type": "string" },
        "line": { "type": "integer" },
        "column": { "type": ["integer", "null"] },
        "end_line": { "type": ["integer", "null"] },
        "end_column": { "type": ["integer", "null"] },
        "rule": { "type": "string" },
        "severity": { "type": "string", "enum": ["info", "warn", "error"] },
        "message": { "type": "string" },
        "fix": { "type": ["string", "null"] },
        "provenance": { "type": "string" },
        "freshness": { "type": "string", "enum": ["unknown", "existing", "new"] }
      }
    }
  }
}
```

See [Result Reference](reference/result-reference.md).
