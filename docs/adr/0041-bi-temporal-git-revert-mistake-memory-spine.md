Current status: historical decision; The storage-layer supersession remains [ADR-0049](0049-typed-artifact-memory-schema-and-trust-tiers.md). Revert-derived records are heuristic evidence, not proof of causal truth or guaranteed regression prevention; [mistake-memory workflow](../workflows/bi-temporal-mistake-pre-mortem.md) documents current behavior and [Phase 63](../phase-plans/phase-63-memory-capabilities-vibecoder-plan.md) governs remaining memory capabilities.

# ADR-0041: Bi-Temporal Git-Revert Mistake Memory Spine

## Status
Superseded by [ADR-0049](0049-typed-artifact-memory-schema-and-trust-tiers.md) for the
shared `.rush/memory.db` storage layer this ADR's mistake-guard rows now live in; the
mistake-mining decision itself remains in force.
Accepted (v0.3.0 / Phase 43)

## Context
Autonomous agents and newly onboarded developers frequently re-introduce bugs that were already diagnosed, fixed, and reverted in past development cycles.

## Decision
1. Implement a **Bi-Temporal Git-Revert Mistake Memory Miner** in `src/rush/memory/mistake_miner.py` that parses repository `git log --grep="Revert"` commits.
2. Extract bi-temporal mistake triplets (`then you believed` -> `found false` -> `truth now`) and associate them with modified AST symbol ranges.
3. Store mistake guards in `.rush/memory.db` and query them automatically during `rush context pack`, `rush context mistakes`, and FastMCP tool invocations.

## Consequences
- **Positive**: Prevents repetitive historical bug regressions before code edits are committed.
- **Negative**: Requires Git history parsing on repository initialization.
- **Safety**: Read-only Git history inspection; zero network calls.
