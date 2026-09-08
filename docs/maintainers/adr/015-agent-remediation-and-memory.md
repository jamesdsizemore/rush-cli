# ADR-015: Closed-Loop AI Agent Patch Remediation and Session Context Memory

## Status
Superseded by [ADR-0049](../../adr/0049-typed-artifact-memory-schema-and-trust-tiers.md)
for its session-memory storage specifics; the patch-remediation decisions remain in
force.
Accepted

## Context
AI agents benefit from explicit machine-readable patch suggestions and persistent context memory across multi-turn refactoring sessions.

## Decision
1. Add `patch` field to `ToolFinding` data contract.
2. Record session execution history and architecture decisions in `.rush/session_memory.json`.
3. Provide MCP endpoints `rush_get_patch`, `rush_apply_fix`, and `rush_session_context`.

## Consequences
- Single-turn automated remediation for AI agents over MCP.
- Context retention across long-running agent workflows.
