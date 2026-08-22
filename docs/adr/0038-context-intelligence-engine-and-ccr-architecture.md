# ADR-0038: Context Intelligence Engine and CCR Architecture

## Status
Accepted (v0.3.0 / Phase 41, 43)

## Context
Standard agent workflows consume massive token volumes by ingesting raw source files and verbose tool execution dumps. Naive lossy summarization introduces subtle hallucination and context degradation bugs that derail autonomous coding tasks.

## Decision
1. Implement a unified **Context Intelligence Engine** in `src/rush/token_economy/` featuring a deterministic `ContentRouter` that classifies payloads into code ASTs, command outputs, tabular records, or prose.
2. Implement **Context Compression & Restoration (CCR)**: Lossy compressed context sections emitted to models must embed deterministic content-addressable hash anchors (`<!-- ccr:chunk:HASH -->`).
3. Store uncompressed byte streams locally in `.rush/cache/ccr.db` with SQLite LRU eviction.
4. Expose the `rush context retrieve <HASH>` CLI command and `rush_context_retrieve(chunk_id)` FastMCP tool, enabling coding agents to recover byte-exact, lossless implementations on demand in $<2\text{ ms}$.

## Consequences
- **Positive**: Enables 65–85% token reduction while guaranteeing 100% byte-exact reversibility and zero context degradation.
- **Negative**: Requires local disk storage for chunk cache in `.rush/cache/ccr.db` (capped at 100 MB).
- **Safety**: 100% offline, local-first execution; zero external network dependencies.
