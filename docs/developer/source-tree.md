# Source tree responsibilities

| Path | Responsibility |
|---|---|
| `src/rush/catalog.py` | declarative tool/engine metadata, maturity, parser-fixture ownership |
| `src/rush/cli.py` | Click options, catalog command generation, output/exit mapping |
| `src/rush/mcp.py` | stdio server construction and registration |
| `src/rush/config.py` | discovery and typed TOML parse |
| `src/rush/theme.py` | Rich CLI rendering |
| `src/rush/logging.py` | NDJSON stderr logging/redaction |
| `src/rush/tools/base.py` | ToolFn, ToolResult, Finding contracts |
| `src/rush/tools/common.py` | subprocess, normalization, error/skip helpers, exit mapping |
| `src/rush/tools/routing.py` | language detection and deterministic aggregation |
| `src/rush/tools/*.py` | one intent-focused tool implementation each |
| `src/rush/engines/base.py` | adapter contract |
| `src/rush/engines/*.py` | executable argv and parser normalization |
| `tests/test_*reference.py` | promoted adapter invocation/parser contracts |
| `tests/fixtures/engine_reports/` | bounded native reports, including malformed cases |
| `tests/test_cli_registry.py`, `test_mcp.py` | transport and parity evidence |
| `.github/workflows/ci.yml` | locked quality/package and representative-engine jobs |
| `docs/getting-started`, `user-guide`, `tutorials`, `reference` | user documentation |
| `docs/developer`, `maintainers` | implementation and operations documentation |
