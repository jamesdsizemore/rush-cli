Current status: historical decision; The 37-tool count is historical; current catalog authority is the generated inventory in [CLI reference](../../CLI_REFERENCE.md). Caching and scoping remain implemented primitives with command-specific flags, but sub-second latency and staged-byte validation are not universal guarantees ([application review F26](../../reports/phase-64-66-application-review.md)).

# ADR-011: Incremental Content-Hash Result Caching and Git Scoping

## Status
Accepted

## Context
Running 37 tools across large repositories incurs noticeable execution latency when scanning unchanged files.

## Decision
1. Introduce a local SQLite cache storing tool execution findings keyed by file hash, engine binary version, and tool parameters.
2. Add `--staged`, `--changed`, and `--since` scoping flags.
3. Automatically invalidate cache entries when file hashes or configurations drift.

## Consequences
- Fast sub-second re-runs on incremental developer edits.
- Deterministic cache consistency.
