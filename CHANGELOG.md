# Changelog

All notable changes to Rush are documented here.

## Unreleased — 0.2.0

### Added

- A complete audience-separated documentation system covering installation,
  first run, user workflows, tutorials, command/result/configuration/engine/MCP
  references, integrations, safety/privacy, contributor development, maintainer
  runbooks, ADRs, examples, troubleshooting, and release operations.
- Explicit capability-maturity documentation for all 33 commands and 27 engine
  entries, including guarded placeholders and incomplete CLI permission/input
  surfaces.
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
- Contained Phase 04 test-quality report importers for coverage (coverage.py
  JSON, LCOV, Cobertura XML), mutation, property, flaky JUnit, Pact contract,
  snapshot, fuzz, and load evidence, with truthful importer-only documentation.
- Contained Phase 05 CodeQL SARIF 2.1.0 import: explicit local report evidence
  only, with engine identity, malformed-report, and target-containment checks;
  Rush never runs CodeQL, builds a database, or downloads query packs.

### Changed

- Reworked the root README into product onboarding and corrected stale result
  field names, configuration-consumer claims, model-review claims, and advanced
  command examples against the implementation and generated CLI help.
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
