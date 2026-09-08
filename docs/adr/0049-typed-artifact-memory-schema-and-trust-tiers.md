# ADR-0049: Typed-Artifact Memory Schema and Trust Tiers

## Status
Accepted (Phase 61)

## Context
ADR-0030 committed to a Working/Policy/World/Skills taxonomy and an
src/rush/memory/engine.py that was never built (§2.1 Drift 4). This ADR describes what
was actually built instead: a 7-subject taxonomy on one axis, a 4-tier trust taxonomy
(STATED/DERIVED/EXTERNAL_WRITE/IMPORTED) on an orthogonal axis, backed by one SQLite
WAL database at .rush/memory.db.

## Decision
1. Implement `TypedArtifactStore` (`src/rush/memory/store.py`) — SQLite WAL, one
   `memory_artifacts` table, FTS5 virtual table for lexical search, schema per
   Phase 61 plan §6.1.
2. Implement 4-tier trust taxonomy and write-promotion rule (`src/rush/memory/trust.py`),
   composing an ALLOW/REDACT/BLOCK screen, a regex pre-filter, a schema-completeness
   check, and corroboration-threshold-2 (via new, dedicated `count_corroboration()`
   code, not `MultiModelConsensusReconciler`) — per Phase 61 plan §6.2.
3. Migrate `preference_store.py`, `invariant_graph.py`, `merkle_invalidator.py`,
   `checkpoint_journal.py`, `failure_ledger.py`, `PatchMemoryStore`, `FlightRecorder`,
   and `HookTamperDetector` onto this store as thin compatibility views; old satellite
   files renamed `.migrated`, never deleted.
4. Implement a per-tool transport dispatcher (native SDK → ACP → dedicated-file, never
   `AGENTS.md`/`CLAUDE.md`) and one `MemoryTool` query/write interface registered via the
   real two-part CLI+MCP path (`ALL_TOOLS`/`register_all_tools()` for MCP; `TOOL_SPECS` +
   a bespoke `@cli.group` for CLI — `make_tool_wrapper` alone is MCP-only).

## Consequences
- **Positive:** one relational store instead of eight satellite files/formats; a real
  trust taxonomy replacing a single binary quarantine flag; recall-time tamper and
  injection defense that no prior design in this repo had.
- **Negative:** adds the repo's first WAL-mode SQLite connection (§2.1 Drift 3, no prior
  pattern existed) — new operational surface (lock contention under concurrent writers)
  to monitor.
- **Safety:** 100% offline, local-first, zero new third-party dependencies (§8.3).
