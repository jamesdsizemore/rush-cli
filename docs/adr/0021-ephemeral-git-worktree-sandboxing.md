# ADR-0021: Ephemeral Git Worktree Sandboxing

## Status
Accepted

## Context
When autonomous agents attempt speculative code fixes or run experimental tests, they risk dirtying the developer's working tree, creating merge conflicts, or leaving uncommitted broken syntax.

## Decision
1. Implement an automated ephemeral Git worktree manager (`rush git-worktree`) storing isolated workspaces under `.rush/worktrees/<task-id>`.
2. Provide detached HEAD branch isolation, execution health tracking, and automated garbage collection.
3. Require multi-agent tasks and destructive remediation evaluations to execute within dedicated worktree sandboxes before applying changes to the active working branch.

## Consequences
- Complete isolation of speculative agent edits from the active developer workspace.
- Safe parallel execution of multiple autonomous agents on the same repository.
