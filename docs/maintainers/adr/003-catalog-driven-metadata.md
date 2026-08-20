# ADR-003: catalog-driven metadata

**Status:** accepted

## Context

Hand-maintained CLI, MCP, config, and documentation inventories drift easily.

## Decision

Keep canonical ToolSpec/EngineSpec metadata and enforce parity with executable registries/tests. Generate ordinary CLI commands and MCP instructions from registered tool objects.

## Consequences

Every tool receives an honest maturity classification. Catalog presence is not proof of executable capability, so docs and tests must expose maturity.
