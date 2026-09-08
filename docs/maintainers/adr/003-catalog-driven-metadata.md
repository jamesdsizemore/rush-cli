Current status: historical decision; The metadata decision remains required. Current CLI paths, MCP registrations, and catalog entries are distinct generated inventories in [CLI reference](../../CLI_REFERENCE.md) and [MCP reference](../../MCP_REFERENCE.md). [Application review F06 and F11](../../reports/phase-64-66-application-review.md) records dispatch/workload defects that catalog presence does not resolve.

# ADR-003: catalog-driven metadata

**Status:** accepted

## Context

Hand-maintained CLI, MCP, config, and documentation inventories drift easily.

## Decision

Keep canonical ToolSpec/EngineSpec metadata and enforce parity with executable registries/tests. Generate ordinary CLI commands and MCP instructions from registered tool objects.

## Consequences

Every tool receives an honest maturity classification. Catalog presence is not proof of executable capability, so docs and tests must expose maturity.
