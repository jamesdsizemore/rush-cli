Current status: historical decision; Local stale-result and continuity-hash utilities cannot themselves rewrite an external agent's existing conversation history. The automatic sweeping and 60–80% savings consequences below require integration and measurement; [token economy and context](../agentic-rush/token-economy-and-context.md) and [Phase 63](../phase-plans/phase-63-memory-capabilities-vibecoder-plan.md) define current limits and remaining work.

# ADR-0043: Stale Tool Result Deduplication and Continuity Hashes

## Status
Accepted (v0.3.0 / Phase 44)

## Context
In multi-turn agent conversations, prior file reads and tool results remain in the prompt context indefinitely, causing quadratic token accumulation and exhausting context limits.

## Decision
1. Implement **Stale Read Sweeping (`TokenTamer` pattern)** in `src/rush/token_economy/stale_sweeper.py`.
2. As new turns occur, automatically collapse earlier file reads to compact 1-line skeleton signatures while preserving the active turn's read in full fidelity.
3. Implement `known_pack_hash` / `not_modified` deduplication headers for memory recall queries, returning HTTP 304-style status when memory state has not changed.

## Consequences
- **Positive**: Yields 60–80% token savings in multi-turn agent sessions; eliminates context bloat.
- **Negative**: Requires tracking turn index in session memory state.
- **Safety**: Preserves active turn verbatim; prior turns restorable via CCR.
