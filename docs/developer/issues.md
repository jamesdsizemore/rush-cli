# Rush Platform Issue & Bug Tracker

> **Repository:** `jamesdsizemore/rush-cli`  
> **Status:** Active Issue Log  

---

## 1. Resolved Issues (Phases 20–25)

| Issue ID | Phase | Component | Summary | Resolution | Status |
|---|---|---|---|---|---|
| **ISS-020-01** | Phase 20 | AST Slop Sensor | AST parser crashed on empty Python files | Added empty-file guard in `AislopEngine` | **Closed** |
| **ISS-020-02** | Phase 20 | TDD Guard | Missing test file raised unhandled exception | Handled missing test files gracefully returning structured finding | **Closed** |
| **ISS-021-01** | Phase 21 | Cache SQLite | Corrupt `.rush/cache.db` crashed CLI execution | Added self-healing recovery and auto-rebuild in `ResultCache` | **Closed** |
| **ISS-021-02** | Phase 21 | Git Scoping | Argument injection risk via invalid git refs | Implemented `validate_git_ref` regex safety filter | **Closed** |
| **ISS-022-01** | Phase 22 | Auto-Remediation | AST syntax errors introduced by aggressive fixers | Implemented `validate_ast` and atomic `SnapshotJournal.rollback_all()` | **Closed** |
| **ISS-022-02** | Phase 22 | Path Confinement | Target path outside repository boundary | Enforced `assert_safe_workspace_path` and symlink escape checks | **Closed** |
| **ISS-023-01** | Phase 23 | Setup Wizard | Arbitrary package names passed to installer | Added `SAFE_PACKAGE_NAME` regex sanitization in `install_engine_package` | **Closed** |
| **ISS-024-01** | Phase 24 | Environment Doctor | CWD binary shadowing project virtualenv | Implemented `resolve_binary_secure` with strict PATH filtering | **Closed** |
| **ISS-025-01** | Phase 25 | Watcher | High CPU during rapid batch file saves | Added `PathFilter` ignore engine and debounced snapshot coalescing | **Closed** |
| **ISS-026-01** | Phase 26 | Monorepo Boundaries | Support multi-package dependency graphs across pnpm/cargo/uv workspaces | Implemented `WorkspaceDiscovery`, `DependencyGraphBuilder`, `WorkspaceBoundaryGuard` | **Closed** |
| **ISS-027-01** | Phase 27 | TUI / Dashboard | Session token expiry handling for Starlette local server | Implemented `SessionAuthManager` with CSPRNG bearer token validation | **Closed** |
| **ISS-028-01** | Phase 28 | Trust Store | SHA-256 trust verification for third-party agent skills | Implemented `PluginTrustStore` and `PreExecutionHashVerifier` | **Closed** |

---

## 2. Active & Upcoming Issues (Phases 29+)

| Issue ID | Phase | Component | Summary | Target Milestone | Status |
|---|---|---|---|---|---|
| **ISS-029-01** | Phase 29 | AI Patch Sandbox | Git worktree isolation and circuit breaker for patch loop | Phase 29 | Open |
| **ISS-030-01** | Phase 30 | Packaging & Release | SemVer and SHA-pinned GitHub Actions packaging validation | Phase 30 | Open |
| **ISS-031-01** | Phase 31 | Worktree Sandboxing | Isolated git worktree environment for autonomous agents | Phase 31 | Open |



