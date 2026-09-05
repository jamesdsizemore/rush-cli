# Instant Fix & Auto-Remediation

Nothing ruins a great vibecoding flow state like getting bogged down in trivial formatting errors: missing trailing commas, inconsistent double quotes, unsorted imports, or trailing whitespace.

Instead of typing manual fixes or wasting expensive LLM prompts asking the AI to reformat a file, Rush gives you **one-click automated remediation** with `rush fix`.

---

## 1. How `rush fix` Works

```bash
# Preview what Rush will clean up (safe, non-destructive preview)
rush fix . --dry-run

# Apply the safe fixes automatically across all files
rush fix .
```

When you run `rush fix .`, Rush orchestrates the best automated formatters and fixers installed in your environment:
- **Python**: Invokes `Ruff` to format code, sort imports (`I001`), and clean unused variables.
- **JavaScript & TypeScript**: Invokes `Prettier`, `ESLint`, and `Biome` to standardize style, format JSX/TSX, and resolve linting rules.
- **HTML / Templates**: Invokes `djLint` to tidy template indentation.

---

## 2. Safe & Confined by Design

Automated tools that modify code must be trustworthy. Rush enforces strict safety boundaries during all auto-remediation:

1. **Git Working Tree Protection**: `rush fix` checks that your current Git state is safe before making changes (pass `--force` to override).
2. **Strict Path Confinement**: Fixes are strictly confined inside your repository root—Rush will never touch files outside your workspace.
3. **Non-Destructive AST Rules**: Only safe, deterministic transformations are applied; Rush never rewrites complex logic or deletes meaningful code.

---

## 3. Automated Live Remediation with `rush watch`

To make formatting 100% effortless, start the live watcher at the beginning of your coding session:

```bash
rush watch .
```

Whenever you or your AI agent save a file, Rush instantly runs a fast check. If any minor formatting or import issue is spotted, you can run `rush fix .` in a separate terminal split and be back in your flow in under 2 seconds.

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
