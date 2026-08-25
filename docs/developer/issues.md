# Rush Platform Issue & Bug Tracker

> **Repository:** `jamesdsizemore/rush-cli`  
> **Status:** All Known Issues Resolved & Closed (v0.3.0 Flagship)  

---

## 1. Resolved Issues (Phases 20–50)

| Issue ID | Phase | Component | Summary | Resolution | Status |
|---|---|---|---|---|:---:|
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
| **ISS-029-01** | Phase 29 | AI Patch Sandbox | Git worktree isolation and circuit breaker for patch loop | Implemented `PatchSandboxManager`, `PatchApplier`, `PatchMemoryStore` | **Closed** |
| **ISS-030-01** | Phase 30 | Packaging & Release | SemVer and SHA-pinned GitHub Actions packaging validation | Implemented `SemVerValidator`, `CIWorkflowGenerator`, `ArtifactProvenanceVerifier` | **Closed** |
| **ISS-031-01** | Phase 31 | Worktree Sandboxing | Isolated git worktree environment for autonomous agents | Implemented `AgentSafetyGuard`, `DangerousCommandInterceptor`, `SecretRedactor` | **Closed** |
| **ISS-032-01** | Phase 32 | Token Economy | BPE tokenizer and AST code outline compression | Implemented `FastBPETokenCounter`, `PythonAstOutlineCompressor`, `PromptCompressor` | **Closed** |
| **ISS-033-01** | Phase 33 | Full-Stack Sync | Static AST route extraction and schema type safety | Implemented `OpenApiContractChecker`, `TypeScriptContractGenerator`, `FastApiAstExtractor` | **Closed** |
| **ISS-034-01** | Phase 34 | Codebase Hygiene | Dead code detection and 3-way AST merge solver | Implemented `PolyglotDeadCodeDetector`, `AstImportMerger`, `ASTConflictMerger` | **Closed** |
| **ISS-035-01** | Phase 35 | Polyglot AST Slicing | Tree-Sitter based code property graph slicing | Implemented `CodeGraphStore`, `PythonCodeGraphBuilder`, `VerbatimAstSlicer` | **Closed** |
| **ISS-036-01** | Phase 36 | Asset Optimization | Bundle budget checking and dead asset auditing | Implemented `BundleChunkCalculator`, `PerformanceBudgetGate`, `OrphanedAssetScanner` | **Closed** |
| **ISS-037-01** | Phase 37 | Git Hotspots | Code velocity, churn, and bus-factor analysis | Implemented `GitChurnExtractor`, `CyclomaticComplexityCalculator`, `RiskMatrixCalculator` | **Closed** |
| **ISS-038-01** | Phase 38 | Agent Governance | Centralized AGENTS.md compiler and repo scaffolding | Implemented `AgentsMdSynchronizer`, `RuleParityChecker`, `SubagentHierarchyValidator` | **Closed** |
| **ISS-039-01** | Phase 39 | Hook Intelligence | Pre-commit intelligence and hook guard verification | Implemented `StagedFileScanner`, `FastIncrementalAstLinter`, `HookTamperDetector` | **Closed** |
| **ISS-040-01** | Phase 40 | Consensus & Scorecard | Multi-model consensus reconciliation and 6-pillar score | Implemented `CompositeScorecardCalculator`, `MultiModelConsensusReconciler`, `SarifExporter` | **Closed** |
| **ISS-041-01** | Phase 41 | Command Distillers | Subprocess distillation token truncation | Handled BPE boundaries with exact sub-token slices | **Closed** |
| **ISS-042-01** | Phase 42 | TOON Serializer | Deeply nested AST dictionaries | Implemented recursive indent-safe TOON v4.1 emitter | **Closed** |
| **ISS-043-01** | Phase 43 | GroundingVerifier | Invariant graph hallucination edge cases | Added AST symbol extraction to `GroundingVerifier` | **Closed** |
| **ISS-044-01** | Phase 44 | Prompt Cache Alignment | Sub-1024 token prompts bypassing provider KV cache | Implemented `CacheAligner` automatic padding | **Closed** |
| **ISS-045-01** | Phase 45 | Gain TUI | SQLite database lock collisions | Implemented WAL mode in `TelemetryStore` | **Closed** |
| **ISS-046-01** | Phase 46 | Blast Radius | Circular imports causing recursion loop in analyzer | Added visited set memoization in `BlastRadiusAnalyzer` | **Closed** |
| **ISS-047-01** | Phase 47 | Flaky Test Healer | Pytest collecting `TestHealer` class as test suite | Added `__test__ = False` to `TestHealer` | **Closed** |
| **ISS-048-01** | Phase 48 | DB Schema Drift | Case-insensitive SQL column name mismatch | Normalized column names to lowercase in `DbDriftAuditor` | **Closed** |
| **ISS-049-01** | Phase 49 | Swarm AST Merge | Function ordering conflicts during 3-way reconciliation | Implemented sorted union merge strategy in `SwarmMergeSolver` | **Closed** |
| **ISS-050-01** | Phase 50 | SLSA Attestation | Reproducibility timestamp format mismatch | Standardized on ISO-8601 UTC in `SLSAAttestationGenerator` | **Closed** |
| **ISS-BENCH-01** | Benchmark | Provider Subprocess | Subprocess execution missing check=False in provider probe | Added explicit `check=False` to `subprocess.run` in `providers.py` | **Closed** |
| **ISS-BENCH-02** | Benchmark | Context Budgeting | Skeletonizer stripping AST comments containing facts | Preserved docstrings and added explicit target_symbol support | **Closed** |
| **ISS-BENCH-03** | Benchmark | Local Model Security | Ollama runtime and in-repo cache containment violations | Implemented strict rejection in `validate_local_runtime_command` | **Closed** |

---

## 2. Implementation Milestones (Phases 41–50 & Benchmarks)
* [x] **Phase 41**: BPE token accounting, command distillers (pytest/cargo/ruff/vitest), session checkpoint journal, base ship linters.
* [x] **Phase 42**: TOON v4.1 serializer, AST skeletonizer, Merkle invalidator, 7-vector Ship Gate Cockpit.
* [x] **Phase 43**: CCR chunk store, GroundingVerifier / HalluGuard, InvariantGraph, FailureLedger, MistakeMiner.
* [x] **Phase 44**: Context pack, prompt cache alignment, and stale read sweeping.
* [x] **Phase 45**: GAIN TUI telemetry dashboard, SQLite token ledger, and terse persona output shaper.
* [x] **Phase 46**: Blast radius reachability analyzer and declarative architecture boundary guard.
* [x] **Phase 47**: Autonomous flaky test healer and public API breaking change contract detector.
* [x] **Phase 48**: ORM schema drift auditor, cognitive complexity decomposer, and runtime type guard synthesizer.
* [x] **Phase 49**: Spec-to-code traceability scanner, agent flight recorder, and swarm 3-way AST merge solver.
* [x] **Phase 50**: SLSA Level 3 cryptographic build attestation, copyleft license scanner, least-privilege IAM synthesizer, and flagship v0.3.0 release.
* [x] **Benchmark Harness (B1–B6)**: Typed contracts, atomic reporting, 40 declared fixtures, provider descriptors, privacy secret redactions, ContextPacker/CCR probes, multi-agent lock mesh verification, and consumer hardware profiling.

---

## 3. Continuity implementation records

| Issue ID | Title | Status | Severity / impact | Discovery phase/task | Evidence | Affected files / capabilities | Owner role | Blocking status | Proposed resolution | Related backlog | Test coverage | Resolution commit / deferral |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ISS-P1-00 | No canonical tracker state for continuity work | Resolved | High — implementation state was untracked | P1-T00 | Legacy trackers listed historical milestones only; no BL-P*/ISS-P* records | `docs/developer/backlog.md`, `docs/developer/issues.md` | Implementation agent | Non-blocking after this record | Add program fields and P1 records while preserving historical rows | BL-P1-00, BL-P1-03 | Documentation review in P1 verification | Pending P1 commit |
| ISS-P1-01 | Session save/list/restore lacks CLI/MCP ToolResult parity | Resolved | High — transport-specific output and missing MCP list/restore prevent safe handoff continuity | P1-T00/P1-T01 | `SessionContinuityTool` is catalogued and registered by `ALL_TOOLS`; focused CLI and live stdio-MCP lifecycle tests pass | Session continuity, CLI, MCP, catalog, permissions | Implementation agent | Non-blocking | One shared `continuity` ToolFn; CLI session adapters and the generated `rush_continuity` MCP tool call it | BL-P1-01, BL-P1-02 | `tests/test_cli_registry.py`, `tests/test_mcp.py`, config/permission regression suite | Phase 1 commit |
| ISS-P1-DOC-COUNT | Current documentation exposed stale catalog and MCP counts | Resolved | Medium — users and contributors would discover an incomplete tool surface | P1-DOC | Review found current operational docs describing 37 tools or 34 MCP tools after `continuity` registration | Documentation, CI, MCP setup, developer registration guidance | Documentation agent | Non-blocking | Update affected current docs and amend §3A/§8 P1 pack; historical reports remain review-only | BL-P1-03 | Docs diff and full suite catalog-maturity assertion | Phase 1 commit |
| ISS-P1-VERIFY | Benchmark runner test relied on ignored local evidence | Resolved | Medium — clean phase worktrees could not satisfy the full-suite gate | P1-V | `generate_and_write_decisions` intentionally keeps evidence in caller-selected output, while `test_runner_generates_all_decisions_and_handoff` also required pre-existing ignored repository artifacts | Benchmark verification test only | Verification agent | Non-blocking | Assert the selected output contract; do not require ignored repository result directories | BL-P1-03 | Full suite in clean P1 worktree: 797 passed, 4 skipped | Phase 1 commit |
| ISS-PROGRAM-GATES | P2–P5 required benchmark gate records are absent or inconsistent | Open | Critical — later persistence, context, coordination, and provider work is forbidden until evidence is reconciled | P1-T03 | `docs/reports/final-handoff.md` links missing B1–B6 artifacts; required BG-AUTH/BG-PRIV/BG-CTX/BG-COORD and route records are not canonical | Phase 2–5 schemas and approved provider routes | Program owner | Blocks P2–P5; does not block P1 | Reconcile committed decision records, exact gate IDs, and OmniRoute naming before each phase begins | BL-P2-00, BL-P3-00, BL-P4-00, BL-P5-00 | Gate-record audit before each phase T00 | No deferral decision recorded |
| ISS-BG-PRIV | Canonical privacy gate was absent despite passed B-D03 baseline | Resolved | High — P2 needs durable, scoped redaction evidence | P2 gate reconciliation | `docs/reports/continuity-gates/BG-PRIV.json`; B-D03 pass; deterministic privacy suite 4 passed | P2 persistence boundary | Program owner | Non-blocking | Track B-D03 as a narrow parser/redaction baseline; P2-T01 proves persisted-envelope behavior separately | BL-P2-00, BL-P2-01 | `tests/test_benchmark_privacy.py` | Gate reconciliation commit |
| ISS-BG-AUTH | Existing benchmark evidence does not prove handoff authority semantics | Open | Critical — historic instruction, replay, tombstone, and freshness behavior must be evidenced before receipt integration | P2 gate reconciliation | B-D01 is inconclusive and B1 unblocks no product task; `BG-AUTH.json` specifies required P2-T01 evidence | P2 handoff authority contract | Implementation agent | Blocks P2-T02 only | Produce BG-AUTH after P2-T01 red/green evidence; do not promote B-D01 | BL-P2-00, BL-P2-01, BL-P2-02 | `tests/test_session_memory.py`, `tests/test_phase41_memory_ship.py` | Pending P2 commit |
