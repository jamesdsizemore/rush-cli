Current status: historical decision; Current public plugin commands are `rush plugin list` and `rush plugin run`; automated creation/installation skills below are accepted design requirements rather than a registered public skills route. The content-addressed trust amendment remains the plugin execution contract. See [plugins and agent skills](../../agentic-rush/plugins-and-agent-skills.md) and [Phase 65](../../phase-plans/phase-65-project-provisioning-scan-and-agent-workflow-plan.md).

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

## Amendments (Phase 56: Content-Addressed Plugin Trust)
- Trust authority moved from in-repository `.rush/trust.json` to user-owned ledger `~/.rush/plugin_trust_ledger.json`.
- Single-file hashing replaced with `PluginClosureManifest` digesting all code, assets, configs, and runtime.
- Subprocesses execute from immutable byte-copied snapshot directories under `rush.io.PhysicalRoot`.
- Secrets delivered via protected descriptor/stdin channels with zero exposure in `argv` or `env`.
