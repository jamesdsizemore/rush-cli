# Agentic Rush/Token Efficiency

## Token Efficiency Architecture (Phases 41–43)
* **Command Distillation**: 50–90% reduction on test outputs (`PytestDistiller`, `CargoDistiller`, `VitestDistiller`).
* **TOON v4.1 Serialization**: 40–65% reduction on tabular findings (`--format toon`).
* **AST Skeletons**: 85%+ reduction on module reading (`rush token outline`).
* **CCR Caching**: SQLite chunking with `<!-- ccr:chunk:HASH -->`.

## Context Packing & Stale Sweeping Efficiency
* `ContextPacker`: 70–85% token reduction via PageRank-prioritized skeletons.
* `StaleSweeper`: 60–80% savings in multi-turn sessions by pruning stale file reads.
* `CacheAligner`: $\ge 85\%$ KV prompt cache hit rate.



## Test Healing Efficiency
`TestHealer` avoids dumping dozens of failed test tracebacks into agent context by isolating and summarizing root causes.



## Simplified Function Context Efficiency
Small, decomposed helper functions fit perfectly into subagent context windows without requiring entire module dumps.



## Multi-Agent AST Merge Efficiency
AST-based conflict resolution completely bypasses costly LLM re-prompting loops when merging parallel subagent branches.



## Complete Token Economy Architecture
Rush CLI v0.3.0 achieves an aggregate 75–90% reduction in token consumption across multi-turn AI coding workflows through AST skeletonization, Merkle caching, stale sweeping, and terse personas.

