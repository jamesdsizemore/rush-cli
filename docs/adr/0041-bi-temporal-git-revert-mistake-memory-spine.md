# ADR-0041: Bi-Temporal Git-Revert Mistake Memory Spine

## Status
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
