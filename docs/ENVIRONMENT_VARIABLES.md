# Environment Variables Reference

Rush inspects a bounded set of environment variables to configure logging, runtime discovery, and optional helper behaviors.

---

## 1. Supported Environment Variables

| Variable | Type / Values | Default | Purpose & Safety Contract |
|---|---|---|---|
| `RUSH_LOG_LEVEL` | `debug`, `info`, `warn`, `error` | `warn` | Sets default logging level for CLI and MCP stderr diagnostics. MCP stdout is strictly reserved for JSON-RPC. |
| `PATH` | System search path | System | Used by Rush to discover external engine binaries (`ruff`, `eslint`, `pytest`, `semgrep`, etc.). Rush prioritizes venv-local binaries when running inside a virtual environment. |
| `VIRTUAL_ENV` | Filesystem path | None | Standard Python environment marker. Cleared in contributor test suites to prevent foreign dependency leakage. |
| `PYTHONPATH` | Python import paths | None | Cleared in contributor onboarding loops to ensure only local repository packages are loaded. |
| `ANTHROPIC_API_KEY` | API Key string | None | Detected if `rush review --llm` is invoked. `--llm` can make a provider request. Value is never logged or printed. |
| `OPENAI_API_KEY` | API Key string | None | Fallback key detection for `review --llm`. The configured provider can receive findings. Value is never logged or printed. |

No environment variable configures the memory subsystem's database path: `.rush/memory.db` (`TypedArtifactStore`, Phase 61) is a fixed repository-relative path, matching every other `.rush/` satellite path. The now-absorbed satellite files (`.rush/preferences.json`, `.rush/memory/invariants.json`, `.rush/memory/failures.db`, `.rush/hook_signatures.json`) are likewise not independently relocatable via environment variable.

---

## 2. Child Subprocess Environment Sanitization

When Rush launches external engine subprocesses via `run_subprocess()`:
- `PATH` and essential OS variables are preserved to allow child binaries to find their runtime dependencies.
- Sensitive environment credentials are never injected or serialized to log files.
- Child processes are executed with `stdin=DEVNULL`, preventing any inheritance of terminal input.

See [Result Reference](reference/result-reference.md) and [Security Model](safety/security-model.md).

## Invocation & Provider Environment Variables (Phase 57)

- `RUSH_CACHE_DIR`: Directory override for invocation result cache SQLite database.
- `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`: Credentials for AI review providers, validated against approved HTTPS origins.

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
