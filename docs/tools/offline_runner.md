# Offline Local LLM Review Tool (`rush offline-review`)

## Overview
`rush offline-review` runs local air-gapped code quality and security reviews using externally installed local LLM runners (`ollama` or `llama-cli`). In accordance with repository invariants, this tool bundles zero model weights, has zero network egress, requires no heavy external machine learning packages, and returns a structured `status='skipped'` when no local runner daemon is running or installed.

## Usage

### CLI
```bash
rush offline-review [PATH] [--runner-path <path>] [--model <name>] [--model-path <gguf_path>] [--json]
```

### MCP
- **Tool Name:** `rush_offline_review`
- **Parameters:**
  - `path` (str): Target codebase path to evaluate.
  - `runner_path` (str, optional): Explicit path or command name of local runner executable.
  - `model` (str, optional): Name of local Ollama model (default: `llama3:latest`).
  - `model_path` (str, optional): Path to local GGUF model file for `llama-cli`.

## Behavior & Guarantees
- **Zero Network Egress**: Strictly offline, local-only execution without external network calls.
- **Fail-Closed Engine Discovery**: Discovers `ollama` or `llama-cli` on `PATH`. Verifies that Ollama daemon is actively listening on `127.0.0.1:11434`. If absent or not running, returns canonical structured `status='skipped'` with installation instructions.
- **Model Path Verification**: When using `llama-cli`, checks `--model-path` or `.rush/models/*.gguf`. If missing, returns structured `status='skipped'`.
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
