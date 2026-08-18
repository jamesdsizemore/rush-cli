# Changelog

All notable changes to Rush are documented here.

## Unreleased — 0.2.0

### Added

- Catalog-validated per-tool `rush.toml` configuration, example configuration,
  and dedicated configuration, engine, and tool-catalog references.
- Experimental `semantic-drift` detection with explicit browser/slow-run
  execution guards and structured skipped defaults.
- Best-effort deterministic language routing for Go, Rust, Ruby, JVM, Swift,
  PHP, .NET, Elixir, Dart, Scala, and Nix markers across lint/type/test flows.
- Non-mutating developer-workflow tools: `commit-msg`, local `ci` workflow
  inspection, and dry-run-only `release` planning.
- Optional `commitlint` discovery metadata and opt-in pre-commit guidance.
- Catalog metadata, canonical result extensions, deterministic multi-engine
  aggregation, and catalog-driven CLI/MCP transport foundations.
- v0.2 scope, engine-discovery policy, safety guards, and capability
  traceability documentation.

### Changed

- Shared lint/format source discovery and status precedence now use the routing
  module rather than duplicated per-tool helpers.

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
