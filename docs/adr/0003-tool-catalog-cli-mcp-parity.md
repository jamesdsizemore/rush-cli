# ADR 0003: Tool catalog, CLI, and MCP parity

## Context
Catalog presence must not be mistaken for a live integration.

## Decision
One `TOOL_SPECS` record maps every registered tool to a truthful maturity. CLI and stdio MCP derive their catalog information from the same registry and disclose maturity.

## Rejected alternatives
Separate transport registries and implicit maturity based on an engine name were rejected.

## Consequences
`src/rush/catalog.py`, `cli.py`, `mcp.py`, and `config.py` share the contract. Tests: `test_catalog.py`, `test_cli_registry.py`, `test_mcp.py`, and `test_phase00_catalog_maturity.py`.

## Compatibility and operations
Catalog-only, guarded, and browser-runtime tools cannot be promoted without fixture-backed adapter evidence.
