# Developer guide

This guide is for contributors. User help begins at [Documentation home](README.md).

## Local verification loop

```bash
uv sync --all-extras --frozen
unset VIRTUAL_ENV PYTHONPATH
.venv/Scripts/python.exe -m pytest tests/ -q
.venv/Scripts/ruff.exe check src tests
.venv/Scripts/ruff.exe format --check src tests
git diff --check
```

On macOS/Linux, use `.venv/bin/python` and `.venv/bin/ruff`. See [Contributor onboarding](developer/contributor-onboarding.md).

## System map

- `catalog.py`: canonical tool/engine metadata and maturity.
- `cli.py`: Click transport and result rendering only.
- `mcp.py`: stdio FastMCP registration only.
- `config.py`: bounded discovery, typed parse, catalog validation.
- `tools/`: implementation and routing; one shared path for CLI/MCP.
- `engines/`: binary discovery, argv, parsing, normalization.
- `logging.py`: stderr NDJSON and redaction.
- `tests/fixtures/engine_reports/`: engine-native parser contracts.

Read [Architecture](developer/architecture.md) and [Source tree](developer/source-tree.md).

## Canonical contracts

Tool and engine metadata must agree with executable registries and tests. Do not duplicate logic in transports. MCP-callable signatures cannot leak `config` and must remain JSON-schema-compatible. Missing binaries produce `skipped`. Subprocesses use captured output and detached stdin. ToolResult and Finding fields must stay stable and redacted.

## Extension recipes

- [Add a tool](developer/tool-development.md)
- [Add an engine](developer/engine-development.md)
- [Add a language route](developer/routing-development.md)
- [Add a config field](developer/configuration-development.md)
- [Change MCP](developer/mcp-development.md)
- [Add a safety-gated operation](developer/tool-development.md#safety-review)

Each change starts with a failing contract test, includes parser fixtures instead of requiring every runtime, updates CLI/MCP parity and docs, then runs full gates.

## Testing and delivery

[Test guide](developer/testing-guide.md) defines unit, parser, routing, CLI, real stdio MCP, installed-engine, package, clean-clone, and CI layers. [CI and packaging](developer/ci-and-packaging.md) and [Release process](developer/release-process.md) keep tags and publication separate from validation.

## Contributor checklist

- [ ] Scope and safety boundary are explicit.
- [ ] RED test captured the missing contract.
- [ ] Tool/catalog/engine/CLI/MCP/config parity is preserved.
- [ ] Missing-engine, malformed report, timeout, and redaction paths are tested.
- [ ] User docs describe outcomes; developer docs describe internals.
- [ ] Ruff, format, tests, link validation, whitespace, and graph checks pass.
- [ ] No commit, tag, publish, or push without authorization.
