Current status: historical decision; Session storage is superseded by [ADR-0049](../../adr/0049-typed-artifact-memory-schema-and-trust-tiers.md). The MCP endpoint names below and public patch apply/rollback are not registered; single-turn remediation remains required future behavior. [Application review F25 and F43](../../reports/phase-64-66-application-review.md), [Phase 64](../../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md), and [Phase 63](../../phase-plans/phase-63-memory-capabilities-vibecoder-plan.md) govern patch preservation and remaining memory capabilities.

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
