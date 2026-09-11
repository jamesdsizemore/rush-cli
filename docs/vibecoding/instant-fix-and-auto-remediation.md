# Fix command: bounded Ruff remediation

Nothing ruins a great vibecoding flow state like getting bogged down in trivial formatting errors: missing trailing commas, inconsistent double quotes, unsorted imports, or trailing whitespace.

[`rush fix PATH --dry-run --force`](../phase-plans/phase-64-implementation-evidence.md#p64-01--preserve-checkoutindex-during-fixes-f01) now provides bounded Ruff preview. Apply requires `--allow-artifact-write`; P64-04 patch remediation remains planned.

---

## 1. How `rush fix` Works

```bash
# Preview Ruff changes without writes
uv run rush fix . --dry-run --force
```

The current implementation invokes installed Ruff for selected Python targets. Missing Ruff returns structured `skipped`; apply requires `--allow-artifact-write`.

---

## 2. Safe & Confined by Design

Required safety boundaries for accepted remediation are:

1. **Git state preservation**: dry-run and failed execution preserve staged, unstaged, untracked, and history state.
2. **Strict path confinement**: fixes touch only invocation-owned targets inside the physical project root.
3. **Non-Destructive AST Rules**: Only safe, deterministic transformations are applied; Rush never rewrites complex logic or deletes meaningful code.

---

## 3. Automated Live Remediation with `rush watch`

To make formatting 100% effortless, start the live watcher at the beginning of your coding session:

```bash
uv run rush watch .
```

`rush watch` can trigger checks after file changes. Use `rush fix` apply only with artifact-write permission; P64-04 remains planned.

### Failed-Fix Memory Pairing (Phase 61)

When a patch fails, its `PatchMemoryStore` row (keyed by `error_signature`) and the matching failure record in the unified `TypedArtifactStore` (`subject="failure"`, keyed by `fingerprint`) are linked via the migrated schema — a queryable join, not two disconnected rows. This is what stops `rush fix` from re-proposing a patch shape already known to have failed for the same error.

---

## Next Steps

- Learn how to compress code prompts in [Token Diet for Vibecoders](token-diet-for-vibecoders.md).
- Discover how to generate PR scorecards in [Shipping with Swagger](shipping-with-swagger.md).

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

4. **Contained Patch Verification (`rush.patch`) — current safety repair pending**:
   - `PatchContract` cryptographically binds base commit, tree digest, patch content hash, sandbox directory under `rush.io.PhysicalRoot`, command plans, and policy review classes (`standard`, `policy-changing`, `privileged`).
   - Workspaces must be clean before sandboxing or patch application; dirty checkouts fail closed with `DirtyWorkspaceError`.
   - `PatchVerifier` requires at least one passing executed test command; zero executed commands return `outcome='unavailable'` and `False` (zero commands never verify).
   - Current failure cleanup can run broad `git reset --hard`, `git clean -fd`, and worktree cleanup. Invocation-owned restoration is required by [Phase 64, P64-04](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md#p64-04--real-isolated-patch-application-f05-f2425-f43).

5. **Runtime Output Boundary Adapter Enforcement (`rush.contracts.operations`)**:
   - 100% of public operations declared in `governance/public-operations.toml` enforce their target adapters (`ToolOperationAdapter`, `AdminOperationAdapter`, `ServiceOperationAdapter`) at runtime boundaries while preserving native JSON-RPC service protocol messages.
