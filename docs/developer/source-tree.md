# Source tree responsibilities

| Path | Responsibility |
|---|---|
| `src/rush/catalog.py` | declarative tool/engine metadata, maturity, parser-fixture ownership |
| `src/rush/cli.py` | Click options, commands, and compatibility facade (delegating to `rush.cli_support`) |
| `src/rush/cli_support/` | CLI options decorators, catalog command builders, and result rendering |
| `src/rush/mcp.py` | stdio FastMCP server construction and compatibility facade |
| `src/rush/mcp_support/` | FastMCP tool registration, tool wrappers, and custom handler adapters |
| `src/rush/config.py` | discovery and typed TOML parse |
| `src/rush/theme.py` | Rich CLI rendering |
| `src/rush/logging.py` | NDJSON stderr logging/redaction |
| `src/rush/continuity/` | Context Chunk Retrieval (CCR), coordination, providers, and receipts |
| `src/rush/review/` | Review file collection, safe reading, heuristics, LLM egress, results assembly |
| `src/rush/runtime/` | Runtime binaries resolution/caching, subprocess execution, result helpers |
| `src/rush/tools/base.py` | ToolFn, ToolResult, Finding contracts |
| `src/rush/tools/common.py` | Zero-definition compatibility re-export facade for `rush.runtime` |
| `src/rush/tools/routing.py` | language detection and deterministic aggregation |
| `src/rush/tools/blast_radius_graph.py` | Reverse import graph construction and impact traversal |
| `src/rush/discovery/workspace_graph.py` | Workspace package discovery and topological sorting |
| `src/rush/tools/db_drift_rules.py` | Model and migration AST extraction and schema drift evaluation |
| `src/rush/tools/*.py` | one intent-focused tool implementation each |
| `src/rush/engines/base.py` | adapter contract |
| `src/rush/engines/*.py` | executable argv and parser normalization |
| `tests/test_*reference.py` | promoted adapter invocation/parser contracts |
| `tests/fixtures/engine_reports/` | bounded native reports, including malformed cases |
| `tests/test_cli_registry.py`, `test_mcp.py` | transport and parity evidence |
| `.github/workflows/ci.yml` | locked quality/package and representative-engine jobs |
| `docs/getting-started`, `user-guide`, `tutorials`, `reference` | user documentation |
| `docs/developer`, `maintainers` | implementation and operations documentation |

## Token Economy & Memory Source Layout (Phases 41–43)

```
src/rush/
├── token_economy/          # Context intelligence and compression
│   ├── router.py           # ContentRouter and ContentType classification
│   ├── ast_skeletonizer.py # Polyglot AST outline compressor
│   ├── ccr_store.py        # SQLite LRU chunk cache (.rush/cache/ccr.db)
│   ├── distillers/         # Output distillers (pytest, cargo, ruff, vitest)
│   └── toon/               # TOON v4.1 table encoder and decoder
├── memory/                 # Persistent memory and history tracking
│   ├── store.py            # TypedArtifactStore, MemoryArtifact — unified SQLite WAL store (.rush/memory.db, Phase 61)
│   ├── trust.py            # TrustTier, default_entry_tier, evaluate_promotion, evaluate_conflict (Phase 61)
│   ├── migration.py        # Idempotent migration functions, one per absorbed source (Phase 61)
│   ├── transport.py        # Per-tool cross-tool memory transport dispatcher (Phase 61)
│   ├── preference_store.py # Developer preferences — thin view over TypedArtifactStore (formerly .rush/preferences.json)
│   ├── checkpoint_journal.py # Session snapshots — thin view over TypedArtifactStore (family="handoff"); still writes .rush/sessions/*.json
│   ├── merkle_invalidator.py # AST node hash tracking — thin view over TypedArtifactStore (formerly .rush/cache/merkle.json)
│   ├── invariant_graph.py  # Architectural decision graph — thin view over TypedArtifactStore (formerly .rush/memory/invariants.json)
│   ├── failure_ledger.py   # Negative knowledge failure ledger — thin view over TypedArtifactStore (formerly .rush/memory/failures.db)
│   ├── mistake_miner.py    # Bi-temporal Git revert miner (pure; shapes failure candidates, does not persist)
│   ├── maintenance.py      # run_maintenance_cycle() — promotion/staleness/skill-admission/expiry sweeps (Phase 62)
│   ├── expiry.py           # ExpiryPolicy, DEFAULT_POLICIES, sweep_expired() — per-trust_tier TTL expiry (Phase 62)
│   └── decision_schema.py  # DecisionRecordFields — remediation-shaped fields reused by mistake_miner.py (Phase 62)
└── tools/
    ├── ship/               # Pre-flight ship vectors and 7-vector cockpit
    │   ├── cleaner.py      # Scratch directory cleaner
    │   ├── env_linter.py   # AST environment variable parity linter
    │   ├── docs_linter.py  # Markdown link parity auditor
    │   ├── migration_linter.py # SQL table-lock migration hazard detector
    │   ├── semver_linter.py # Public API breaking change contract differ
    │   ├── package_linter.py # Sensitive key / secret leak auditor
    │   └── cockpit.py      # Unified 7-vector parallel Ship Cockpit
    └── hallu_guard.py      # Real-time AST grounding and phantom package guard
```

## Context Packing & Blast Radius Modules
```
src/rush/
├── codegraph/
│   └── context_packer.py  # PageRank context packing
├── token_economy/
│   ├── stale_sweeper.py   # Multi-turn history sweeper
│   ├── cache_aligner.py   # Prompt cache boundary aligner
│   ├── telemetry.py       # SQLite token ledger (.rush/telemetry/tokens.db)
│   ├── output_shaper.py   # Terse persona output filter
│   ├── tui_gain.py        # Rich terminal gain dashboard
│   └── memory_cache_gate.py # check_memory_before_pack() — defended cache lookup wired into pack_context() (Phase 62)
└── tools/
    ├── blast_radius.py    # Downstream reachability analyzer
    └── arch_guard.py       # Architectural layer boundary guard
```



## Test Healing & API Diff Modules
```
src/rush/
├── core/
│   └── git_sandbox.py     # Ephemeral worktree sandbox manager
└── tools/
    ├── test_heal.py       # Autonomous flaky test healer
    └── api_diff.py        # Public API signature differ
```



## DB Drift & Simplification Modules
```
src/rush/tools/
├── db_drift.py    # ORM-to-migration schema drift auditor
├── simplify.py    # Cognitive complexity refactoring decomposer
└── strictify.py   # Runtime type guard synthesizer
```



## Traceability & Mesh Modules
```
src/rush/
├── mcp_mesh/
│   ├── __init__.py
│   ├── daemon.py          # Lock daemon
│   └── lock_manager.py    # Local file-based mutex client
└── tools/
    ├── trace.py           # Spec-to-code traceability scanner
    ├── flight_recorder.py # Session recorder & replayer — episodic writes via TypedArtifactStore (Phase 61)
    ├── memory.py          # MemoryTool: ask|write|promote|list|recall|maintain (Phase 61)
    ├── swarm_merge.py     # 3-way AST merge solver
    └── simulate_ci.py     # Local GHA workflow emulator
```



## Phase 50a Polyglot Quality & Security Modules
```
src/rush/tools/
├── error_catalog.py  # Polyglot AST/regex exception extractor & RFC 7807 problem details generator
├── license_matrix.py # Polyglot copyleft dependency risk auditor (pyproject/package.json/Cargo)
└── iam_audit.py      # Multi-cloud SDK & Terraform least-privilege IAM policy auditor
```

## Phase 50b Attribution, Asset Hygiene & PR Evidence Modules
```
src/rush/tools/
├── provenance_ai.py  # Git commit trailer AI attribution analyzer & survival curve baseline
├── dead_asset.py     # Polyglot static asset reference scanner & disk space savings calculator
└── pr_synthesize.py  # Semantic PR card synthesizer, risk tiering & CODEOWNERS router
```

## Phase 50c Performance Profiling, Offline Review & Provenance Modules
```
src/rush/tools/
├── attest.py         # in-toto Statement v1 & SLSA provenance unsigned draft generator
├── mem_profile.py    # Static AST unclosed resource auditor & dynamic tracemalloc sampler
├── cold_start.py     # Static heavy import detector & -X importtime waterfall analyzer
├── offline_runner.py # Air-gapped local ONNX model reviewer
└── benchmark.py      # Performance baseline comparator with stdlib statistics
```

## Benchmark Harness & Verification Modules (Phases B1–B6)
```
scripts/
└── benchmarks/
    ├── contracts.py     # Dataclass models & schema validation
    ├── fixtures.py      # Path-contained JSON fixture loader
    ├── run.py           # CLI runner & real-time terminal reporter
    ├── reporting.py     # Atomic temporary-file-and-replace writer
    ├── providers.py     # Provider route descriptor execution & scrubbing
    ├── protocol.py      # Multi-dialect envelope parser & quarantine
    ├── privacy.py       # Secret redaction & bounded parser limits
    ├── context.py       # ContextPacker & CCRStore retrieval probes
    ├── coordination.py  # MeshLockManager & CheckpointJournal probes
    └── local.py         # Hardware profiling & Ollama exclusion
tests/
└── fixtures/
    └── benchmarks/      # 40 declared scenario & candidate JSON fixtures
```

## File I/O & Containment Layout (Phase 55)

```
src/rush/io/
├── __init__.py           # Public exports (PhysicalRoot, AtomicFile, VerifierRecord, etc.)
├── physical_paths.py     # PhysicalRoot and ContainmentError
├── atomic_file.py        # AtomicFile, SanitizedBytes, SanitizedJsonValue, AtomicWriteError
└── verifier_record.py    # VerifierRecord and VerifierError
```

- `src/rush/plugins/closure.py`: Transitive closure manifest discovery and cryptographic digest calculation.
- `src/rush/plugins/snapshot_store.py`: Content-addressed physical byte snapshot materialization under `rush.io.PhysicalRoot`.
- `src/rush/plugins/secret_channels.py`: Protected secret delivery channels (descriptor pipe, stdin handshake, provider).
- `src/rush/plugins/trust_store.py`: User-owned trust ledger authority and capability verification.

## `src/rush/invocation/` Source Tree Layout (Phase 57)

```
src/rush/invocation/
├── __init__.py         # Public exports (models, resolver, targets, executor, cache_policy)
├── models.py           # InvocationContext, PhysicalTarget, CacheDecision, exceptions
├── resolver.py         # resolve_invocation() authority
├── targets.py          # resolve_target(), build_physical_targets()
├── executor.py         # InvocationExecutor, RegisteredOperation
└── cache_policy.py     # decide_cache() cryptographic key derivation
```

## Phase 58 Architecture: Capability Locks, CAS Memory, and Fail-Closed Patch Verification

Rush implements closed-loop resilience, fail-closed security, and physical containment across multi-agent concurrency, persistent memory, and AI-driven patch remediation (Findings R-009, R-010, R-011, R-016):

1. **Capability Locks & Verifier Custody (`rush.mcp_mesh`)**:
   - Callers retain high-entropy capability tokens (`LockCapabilityInput`) delivered exclusively via protected channels (`stdin`, `descriptor`, or sensitive MCP parameters); argv and environment leakage are rejected fail-closed.
   - `MeshLockManager` stores verifier-only records (`LockLeaseRecord`) generated via `rush.io.VerifierRecord` (PBKDF2-HMAC-SHA256, 100k rounds) with monotonic generation counters and `rush.io.PhysicalRoot` containment under `.rush/locks`.
   - Renewal and release verify caller capability in constant time (`hmac.compare_digest`); wrong, low-entropy, or stale tokens fail closed.

2. **CAS Map Transactions & Persistent Memory (`rush.memory`)**:
   - `CASMapTransaction` enforces optimistic concurrency with monotonic version numbers and atomic file replacement (`rush.io.AtomicFile`) using sanitized JSON payloads (`SanitizedJsonValue`).
   - Store states are truthfully separated into distinct typed exceptions: `StoreNotFoundError`, `StoreCorruptionError` (retaining raw bytes and SHA-256 digest), `StoreValidationError`, `StoreIOError`, and `CASConflictError` (exhausted retries fail closed).
   - `PreferenceStore`, `InvariantGraph`, and `MerkleInvalidator` eliminate silent empty dict fallbacks.

3. **Atomic Checkpoint Journals & Unified Store Persistence (`rush.memory.checkpoint_journal`)**:
   - `checkpoint_journal.py` is a thin compatibility view over `TypedArtifactStore` (`rush.memory.store`, Phase 61): `save_checkpoint()`/`restore_checkpoint()` write/read each checkpoint as one `MemoryArtifact` row (`family="handoff"`, `subject="active_context"`); canonical data lives in `.rush/memory.db`, not a per-checkpoint JSON file.
   - `save_checkpoint()` still writes a physical `.json` artifact via `rush.io.AtomicFile` and returns its `Path` (`dest.exists()` holds), preserving the pre-Phase-61 contract for existing callers; explicit schema version `1.0.0` is unchanged.
   - Corrupted or unparseable checkpoint files are preserved on disk, cryptographically digested with SHA-256, and surfaced in `list_checkpoints()` with status `corrupt` — unchanged by the Phase 61 migration.

4. **Contained Patch Verification & Atomic Rollback (`rush.patch`)**:
   - `PatchContract` cryptographically binds base commit, tree digest, patch content hash, sandbox directory under `rush.io.PhysicalRoot`, command plans, and policy review classes (`standard`, `policy-changing`, `privileged`).
   - Workspaces must be clean before sandboxing or patch application; dirty checkouts fail closed with `DirtyWorkspaceError`.
   - `PatchVerifier` requires at least one passing executed test command; zero executed commands return `outcome='unavailable'` and `False` (zero commands never verify).
   - Failed promotion or verification triggers automatic atomic rollback (`git reset --hard`, `git clean -fd`) restoring the working directory to its exact pre-patch commit and state.

5. **Runtime Output Boundary Adapter Enforcement (`rush.contracts.operations`)**:
   - 100% of public operations declared in `governance/public-operations.toml` enforce their target adapters (`ToolOperationAdapter`, `AdminOperationAdapter`, `ServiceOperationAdapter`) at runtime boundaries while preserving native JSON-RPC service protocol messages.
- `src/rush/release/provenance_policy.py`: In-toto Statement v1 models and strict parser (Phase 59).
- `src/rush/engines/support_policy.py`: Engine support policy and fixed-PATH harness (Phase 59).

## Maintainability & Modular Subsystems Layout (Phase 60)

```
src/rush/
├── cli_support/
│   ├── __init__.py
│   ├── options.py           # Option decorators and permission extraction
│   ├── catalog_commands.py  # Click catalog command factory
│   └── rendering.py         # Subprocess execution and session result rendering
├── mcp_support/
│   ├── __init__.py
│   └── tool_registry.py     # FastMCP registration and tool wrapper factories
├── continuity/
│   ├── __init__.py
│   ├── context.py           # CCR packing and retrieval
│   ├── coordination.py      # Lock checks, merge preview, coordination recovery
│   ├── providers.py         # Provider resume, OmniRoute, command/prompt assembly
│   └── receipts.py          # Handoff receipt persistence and restoration
├── review/
│   ├── __init__.py
│   ├── collection.py        # File collection, safe reading, heuristic filters
│   ├── llm.py               # LLM review egress and review kind labelling
│   └── results.py           # Review findings assembly and verdict computation
├── runtime/
│   ├── __init__.py
│   ├── binaries.py          # Binary resolution and @lru_cache path caching
│   ├── subprocesses.py      # Bounded redacted subprocess runner and engine executor
│   └── result_helpers.py    # Canonical skipped/error results, fingerprinting, timing
├── discovery/
│   └── workspace_graph.py   # Workspace package discovery and topological sorting
└── tools/
    ├── blast_radius_graph.py # Reverse import graph builder and impact traversal
    └── db_drift_rules.py     # Model/migration AST extractors and drift rules
```
