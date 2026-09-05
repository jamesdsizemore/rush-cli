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

Rush implements closed-loop resilience, fail-closed security, and physical containment across multi-agent concurrency, persistent memory, and AI-driven patch remediation (Findings R-009, R-010, R-011, R-016):

1. **Capability Locks & Verifier Custody (`rush.mcp_mesh`)**:
   - Callers retain high-entropy capability tokens (`LockCapabilityInput`) delivered exclusively via protected channels (`stdin`, `descriptor`, or sensitive MCP parameters); argv and environment leakage are rejected fail-closed.
   - `MeshLockManager` stores verifier-only records (`LockLeaseRecord`) generated via `rush.io.VerifierRecord` (PBKDF2-HMAC-SHA256, 100k rounds) with monotonic generation counters and `rush.io.PhysicalRoot` containment under `.rush/locks`.
   - Renewal and release verify caller capability in constant time (`hmac.compare_digest`); wrong, low-entropy, or stale tokens fail closed.

2. **CAS Map Transactions & Persistent Memory (`rush.memory`)**:
   - `CASMapTransaction` enforces optimistic concurrency with monotonic version numbers and atomic file replacement (`rush.io.AtomicFile`) using sanitized JSON payloads (`SanitizedJsonValue`).
   - Store states are truthfully separated into distinct typed exceptions: `StoreNotFoundError`, `StoreCorruptionError` (retaining raw bytes and SHA-256 digest), `StoreValidationError`, `StoreIOError`, and `CASConflictError` (exhausted retries fail closed).
   - `PreferenceStore`, `InvariantGraph`, and `MerkleInvalidator` eliminate silent empty dict fallbacks.

3. **Atomic Checkpoint Journals & Corrupt Evidence (`rush.memory.checkpoint_journal`)**:
   - Session checkpoints are written via `rush.io.AtomicFile` using explicit schema version `1.0.0`.
   - Corrupted or unparseable checkpoint files are preserved on disk, cryptographically digested with SHA-256, and surfaced in `list_checkpoints()` with status `corrupt`.

4. **Contained Patch Verification & Atomic Rollback (`rush.patch`)**:
   - `PatchContract` cryptographically binds base commit, tree digest, patch content hash, sandbox directory under `rush.io.PhysicalRoot`, command plans, and policy review classes (`standard`, `policy-changing`, `privileged`).
   - Workspaces must be clean before sandboxing or patch application; dirty checkouts fail closed with `DirtyWorkspaceError`.
   - `PatchVerifier` requires at least one passing executed test command; zero executed commands return `outcome='unavailable'` and `False` (zero commands never verify).
   - Failed promotion or verification triggers automatic atomic rollback (`git reset --hard`, `git clean -fd`) restoring the working directory to its exact pre-patch commit and state.

5. **Runtime Output Boundary Adapter Enforcement (`rush.contracts.operations`)**:
   - 100% of public operations declared in `governance/public-operations.toml` enforce their target adapters (`ToolOperationAdapter`, `AdminOperationAdapter`, `ServiceOperationAdapter`) at runtime boundaries while preserving native JSON-RPC service protocol messages.
