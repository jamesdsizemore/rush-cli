# Changelog

All notable changes to Rush are documented here.

## 0.1.0-alpha — 2026-08-17

### Added

- `rush` CLI commands for deterministic `review`, engine-backed `lint`,
  check-only `format`, `test`, and `security`.
- Local stdio MCP server via `rush mcp serve`, exposing the same five canonical
  tool implementations as the CLI.
- Python engines: Ruff, pytest, and pip-audit; JS/TS engines: ESLint, Prettier,
  Vitest, and npm audit.
- Structured ToolResult output and `--json` CLI output.
- MCP setup guide, real stdio protocol integration test, and NDJSON stderr
  diagnostics controlled by `RUSH_LOG_LEVEL`.

### Fixed

- Venv-local engine resolution takes precedence over polluted PATH entries.
- External engines cannot inherit or consume MCP JSON-RPC stdin.
- pip-audit 2.10 `dependencies` JSON envelopes normalize into security
  findings.
