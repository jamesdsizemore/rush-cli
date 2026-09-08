# Semantic-drift detection

`rush semantic-drift <path>` is a correctness-analysis surface for browser locator, accessibility, and DOM drift detection.

## Safety contract

- It is **skipped by default** without explicit permissions.
- Both `--allow-browser` and `--allow-slow` are required to execute local analysis.
- Rush runs Playwright and axe-core in headless mode with detached process boundaries (`stdin=DEVNULL`, process kill on timeout).
- Without a configured local .NET or Playwright target, the enabled path returns a structured `skipped` result with an installation/configuration hint.

Normal CI uses parser and safety contracts; it never requires a browser unless explicitly authorized.

### Phase 56: Plugin Trust & Execution Semantic Alignment
- **Reconciliation**: Demoted repository `.rush/trust.json` from authority to non-authorizing evidence; established user-owned ledger `~/.rush/plugin_trust_ledger.json` via `rush.io.AtomicFile` and `rush.io.PhysicalRoot`.
- **Closure Discovery**: Replaced single-file SHA-256 checks with complete transitive closure manifest.
- **TOCTOU Elimination**: Replaced in-place workspace execution with immutable byte snapshots.
- **Secret Exposure**: Replaced environment variable leakage with protected descriptor/stdin channels.
- **Bypass Removal**: Deprecated `loader.execute_plugin()` and removed `allow_untrusted` flag.

## Reconciliation of Invocation Semantic Drift (Phase 57)

Phase 57 resolved seven core semantic drifts: transport divergence, scope widening, TypeError retries, public route drift, cache key incompleteness, misleading LLM labeling, and dual-transport parity deficits.

## Phase 58 Architecture: Capability Locks, CAS Memory, and Fail-Closed Patch Verification

These Phase 58 component contracts are not whole-application safety guarantees. Checkpoint symlink reads, governance symlink writes, sandbox fallback and patch cleanup remain open ([application review](reports/phase-64-66-application-review.md) F03–F05/F43; [Phase 64 runtime plan](phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md) P64-03/P64-04).

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
   - Current rollback uses broad `git reset --hard`/`git clean -fd` and can destroy unrelated changes. It does not restore an exact pre-invocation index/worktree. Status: planned — bounded restoration in P64-01/P64-04, [Phase 64 runtime plan](phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md); [application review](reports/phase-64-66-application-review.md) F01/F43.

5. **Runtime Output Boundary Adapter Enforcement (`rush.contracts.operations`)**:
   - 100% of public operations declared in `governance/public-operations.toml` enforce their target adapters (`ToolOperationAdapter`, `AdminOperationAdapter`, `ServiceOperationAdapter`) at runtime boundaries while preserving native JSON-RPC service protocol messages.
### Phase 59 Semantic Drift Reconciled
- **R-013 Reconciled:** Default attestation output is strictly an unsigned draft (`assurance: unsigned_draft`); real artifact package digests used as subjects; strict parser rejects duplicate keys; signed policy verifier added.
- **R-014 Reconciled:** Pinned engine taxonomy in `engine-support.toml`; fixed-PATH isolation; supported engines prohibited from passing all-skipped; mandatory non-skipped `mypy` release gate.

### Phase 61 Semantic Drift Reconciled
- **Drift 1:** `transactions.py`'s `CASMapTransaction` was already CAS-versioned, not primitive flat JSON — Phase 61's `TypedArtifactStore` supersedes it with one SQLite WAL database, not "primitive JSON files" as an earlier synthesis-doc draft implied.
- **Drift 2:** `session_memory.py` lives at `src/rush/session_memory.py`, one level up from the other memory-subsystem files under `src/rush/memory/` — no `engine.py` exists or ever existed.
- **Drift 3:** A SQLite WAL precedent already existed (`src/rush/cache.py`'s `ResultCache`) before Phase 61's `TypedArtifactStore` — not the first WAL-mode connection in the codebase; `_init_db()` reuses `ResultCache`'s initialization/failure-policy pattern, not its schema.
- **Drift 4:** ADR-0030 (`Accepted`, Phase 41A-41B) described a Working/Policy/World/Skills taxonomy and `src/rush/memory/engine.py` that were never built. Phase 61 supersedes ADR-0030 with ADR-0049, describing the actually-built 7-subject/4-tier-trust design.
- **Drift 5:** The mesh lock manager the earlier synthesis doc cited as `continuity/coordination.py`'s is actually implemented in `src/rush/mcp_mesh/lock_manager.py` (`MeshLockManager`); `coordination.py` is only a consumer.
- **Drift 6:** `src/rush/continuity/providers.py`'s `provider_command()` dict is bounded, permission-gated session-resume CLI dispatch, not cross-LLM memory transport — Phase 61's `src/rush/memory/transport.py` is wholly new code and never touches `provider_command()`'s call sites.
