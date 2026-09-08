Current status: historical decision; The subprocess-hardening policy remains required. Current worktree and patch cleanup defects show that a list-based Git invocation alone does not prove safe state preservation or universal portability. See [application review F05, F29, and F43](../reports/phase-64-66-application-review.md) and [Phase 64](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md); the absolute portability and compatibility consequences below are historical claims.

# ADR-0024: Hardened Subprocess Git Invocations

## Status
Accepted

## Context
External Python Git libraries like `GitPython` have known CVEs related to argument injection and memory leaks, while `pygit2` requires compiling native C dependencies (`libgit2`).

## Decision
1. Standardize all Git operations across Rush on direct, hardened `run_subprocess(["git", ...])` invocations.
2. Enforce `stdin=DEVNULL`, `shell=False`, strict path resolution, and parameter sanitization on every Git command.
3. Handle detached worktrees, ref-lists, conflict markers, and commit logs with streaming stdout/stderr buffers.

## Consequences
- Zero-overhead, 100% portable Git operations across Windows, macOS, and Linux.
- Guaranteed compatibility with Git 2.25+ without compiling C libraries or introducing third-party Python Git wrappers.
