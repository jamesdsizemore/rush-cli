Current status: historical decision; Lock and merge components are documented in [multi-agent mesh and traceability](../workflows/multi_agent_mesh_and_traceability.md). Their existence does not establish conflict-free concurrent coding, universal platform transport support, or safe rollback across callers; [application review F05 and F43](../reports/phase-64-66-application-review.md) and [Phase 64](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md) govern current preservation defects.

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
