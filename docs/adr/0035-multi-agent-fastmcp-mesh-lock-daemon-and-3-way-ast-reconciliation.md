# ADR-0035: Multi-Agent FastMCP Mesh Lock Daemon and 3-Way AST Reconciliation

## Status
Accepted (v0.2.0 / Phase 46)

## Context
When multiple AI agents (e.g. Claude Code, Cursor Composer, Windsurf) execute concurrently on the same workspace, they produce file write race conditions, cache invalidation thrashing, and corrupted Git conflict markers.

## Decision
1. Implement `rush mcp mesh` (`src/rush/mcp/mesh.py`) as a local domain socket / named pipe background daemon.
2. Provide a federated SQLite cache shared across all connected agent instances.
3. Enforce mutual exclusion file locks when an agent begins applying an AST patch.
4. Implement `rush swarm-merge` (`src/rush/tools/swarm_merge.py`) using a 3-way AST merge solver to reconcile concurrent subagent worktrees at the semantic syntax level without text marker conflicts.

## Consequences
- **Positive**: Enables 3x-5x concurrent agent development velocity without file overwrites or merge collisions.
- **Negative**: Adds local socket communication layer for multi-agent processes.
- **Safety**: Local-first socket communication (`127.0.0.1`); no external port exposure.
