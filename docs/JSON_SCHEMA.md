# JSON Schema & Output Specification

Rush produces standardized, machine-readable JSON output for all 37 tools when invoked with `--json` or via FastMCP.

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
