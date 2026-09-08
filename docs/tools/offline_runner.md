# Offline Local LLM Review Tool (`rush offline-review`)

## Overview
`rush offline-review` runs local air-gapped code quality and security reviews using externally installed local LLM runners (`ollama` or `llama-cli`). In accordance with repository invariants, this tool bundles zero model weights, has zero network egress, requires no heavy external machine learning packages, and returns a structured `status='skipped'` when no local runner daemon is running or installed.

**Status: planned correction — implementation [Phase 64, P64-17](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md#p64-17--project-relative-discovery-and-valid-coverage-f2021).** Current discovery can exclude all files when the selected project is under a hidden parent directory. Zero evaluated files is unavailable evidence.

## Usage

### CLI
```bash
uv run rush offline-review PATH [--json]
```

### MCP
- **Tool Name:** `rush_offline_review`
- **Parameters:** required `path` (str), required opaque `options` object, `model` (str; default `codellama`), `runner_path` (path or null; default null), and common permission booleans defaulting to false. Current CLI exposes no `--runner-path`, `--model`, or `--model-path` option.

## Behavior & Guarantees
- **Zero Network Egress**: Strictly offline, local-only execution without external network calls.
- **Fail-Closed Engine Discovery**: Discovers `ollama` or `llama-cli` on `PATH`. Verifies that Ollama daemon is actively listening on `127.0.0.1:11434`. If absent or not running, returns canonical structured `status='skipped'` with installation instructions.
- **Model Path Verification**: Local runner/model availability determines execution. Current CLI provides no explicit model-path selector.
- **Finding Extraction**: Parses line-oriented or structured JSON review findings emitted by the local runner.

## Output Schema
Emits canonical `ToolResult`:
```json
{
  "tool": "offline-review",
  "engine": "offline-runner",
  "engine_version": "1.0.0",
  "status": "ok",
  "duration_ms": 35,
  "summary": "offline-review: Evaluated 2 file(s) with local runner 'ollama', 1 finding(s)",
  "findings": [
    {
      "path": "app/main.py",
      "line": 10,
      "column": 1,
      "rule": "offline-review/detected-issue",
      "severity": "warn",
      "message": "Potential SQL injection vulnerability in query construction."
    }
  ],
  "metrics": {
    "files_evaluated": 2,
    "model_findings_count": 1,
    "runner_type": "ollama"
  }
}
```

## Security & Permissions
- Strictly offline, local-only evaluation.
- No network, download, or write permissions required.
