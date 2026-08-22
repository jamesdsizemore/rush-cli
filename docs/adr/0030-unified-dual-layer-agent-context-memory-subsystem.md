# ADR-0030: Unified Dual-Layer Agent Context Memory Subsystem

## Status
Accepted (v0.2.0 / Phase 41A-41B)

## Context
AI coding agents (Claude Code, Cursor Composer, Windsurf, Cline) suffer from context amnesia across prompt turns, lose track of architectural decisions, repeatedly attempt previously failed patches, and thrash token budgets with redundant whole-file context dumps.

## Decision
1. Implement a **Unified Dual-Layer Memory Engine** in `src/rush/memory/engine.py` using local-first SQLite WAL storage (`.rush/memory.db`).
2. **Layer 1 (Traditional Memory Layer)**: Provide a 4-tier taxonomy (Working, Policy, World, Skills), persistent developer preferences (`preferences.json`), named session checkpoints (`rush session`), local SQLite FTS5 / BM25 lexical keyword search, and an append-only JSONL audit event stream (`events.jsonl`).
3. **Layer 2 (Cognitive Innovation Memory Layer)**: Implement AST-Merkle reactive cache invalidation (marking memories stale when underlying AST code changes), an architectural decision causal invariant graph, a negative knowledge failure ledger (recording failed patch AST hashes to intercept repeated errors), and token-budgeted adaptive XML prompt compilation (`<rush_context_memory>`).
4. Support multi-agent concurrent access via SQLite WAL mode and FastMCP stdio bindings.

## Consequences
- **Positive**: Eliminates agent context amnesia, prevents repeated buggy patch attempts, provides sub-millisecond local memory recall, reduces prompt token bloat.
- **Negative**: Adds local SQLite database `.rush/memory.db` requiring schema migrations and gitignore handling.
- **Safety**: 100% offline and local-first execution; zero API keys or external network dependencies required.
