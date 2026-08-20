# ADR-012: Extensible Plugin Architecture and AI Agent Plugin Skills

## Status
Accepted

## Context
Custom analyzers and organizational linters require an extensible registration mechanism outside static engine definitions.

## Decision
1. Support `[plugins.<name>]` in `rush.toml` and `.rush/plugins/`.
2. Enforce standard `ToolResult` JSON output from all plugin executables.
3. Provide AI agent skills for automated plugin creation and installation.

## Consequences
- Clean extensibility for custom rulesets and proprietary compliance scanners.
