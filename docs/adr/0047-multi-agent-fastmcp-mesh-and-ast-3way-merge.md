# ADR-0047: Multi-Agent FastMCP Mesh and AST 3-Way Merge

## Status
Accepted (v0.3.0 / Phase 49)

## Context
When multiple autonomous AI agents (Claude Code, Cursor, Windsurf) work concurrently in the same repository, they create file write race conditions, invalidate caches redundantly, and trigger Git merge conflicts.

## Decision
1. Implement a lightweight local **FastMCP Mesh Coordinator** in `src/rush/mcp_mesh/` over local UNIX domain sockets / Windows named pipes.
2. Provide distributed mutual exclusion file locking with TTL leases to prevent simultaneous writes.
3. Implement an **AST 3-Way Merge Solver** in `src/rush/tools/swarm_merge.py` that merges non-overlapping AST syntax nodes cleanly even when line numbers shift.

## Consequences
- **Positive**: Enables conflict-free parallel multi-agent coding sessions without file corruption.
- **Negative**: Adds optional background daemon process.
- **Safety**: Graceful fallback to direct SQLite WAL mode if mesh daemon is not active.
