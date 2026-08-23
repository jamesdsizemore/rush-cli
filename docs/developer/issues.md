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

---

## 2. Implementation Milestones (Phases 41–50)
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
