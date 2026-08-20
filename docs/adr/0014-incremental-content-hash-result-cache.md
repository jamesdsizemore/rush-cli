# ADR-0014: Incremental Content-Hash Result Caching and Git Scoping

## Status
Accepted

## Context
Running thirty-five quality tools across large monorepositories introduces scan latency when inspecting unmodified files. Binary-resolution LRU caching optimizes executable discovery but does not eliminate redundant scanner invocations on unchanged source code.

## Decision
1. Implement a persistent SQLite-backed incremental content-hash cache in `.rush/cache.db`.
2. Compute composite cache keys derived from file SHA-256 content hashes, engine version strings, CLI arguments, and tool configuration tables.
3. Introduce Git-aware execution scoping flags (`--staged`, `--changed`, `--since <ref>`) to restrict scanner execution to modified files.
4. Provide explicit cache governance via `--no-cache`, `rush cache clean`, and `rush cache stats`.

## Consequences
- Sub-second quality validation cycles on large workspaces.
- Complete reproducibility and deterministic invalidation when file contents or engine configurations change.
- Native integration with pre-commit hooks and continuous integration workflows.
