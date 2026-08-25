# Agentic Rush/Token Efficiency

## Recover instead of re-expanding

An insufficient context budget yields a recoverable redacted CCR handle, not an unbounded prompt retry. This preserves token discipline: the agent starts with the bounded envelope and deliberately retrieves omitted evidence only when its current task requires it.

## Token Efficiency Architecture (Phases 41–43)
* **Command Distillation / TOON / AST Skeletons**: local transformations whose measured token counts depend on the concrete input.
* **CCR Caching**: SQLite chunking with `<!-- ccr:chunk:HASH -->`.

## Context Packing & Stale Sweeping Efficiency
* `ContextPacker`: a bounded target-file skeleton envelope; it reports estimated local tokens and fails closed for an insufficient budget.
* `StaleSweeper`: deterministic local history pruning, not a measured provider saving.
* `CacheAligner`: local prefix padding only; it does not measure or guarantee a provider cache-hit rate.



## Test Healing Efficiency
`TestHealer` avoids dumping dozens of failed test tracebacks into agent context by isolating and summarizing root causes.



## Simplified Function Context Efficiency
Small, decomposed helper functions fit perfectly into subagent context windows without requiring entire module dumps.



## Multi-Agent AST Merge Efficiency
AST-based conflict resolution completely bypasses costly LLM re-prompting loops when merging parallel subagent branches.



## Complete Token Economy Architecture
Rush CLI v0.3.0 achieves an aggregate 75–90% reduction in token consumption across multi-turn AI coding workflows through AST skeletonization, Merkle caching, stale sweeping, and terse personas.

