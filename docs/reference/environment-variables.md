# Environment Variables Specification

Exhaustive reference of environment variables recognized, inspected, or sanitized by Rush CLI.

---

## 1. Recognized Environment Variables

| Variable | Type / Format | Default | Purpose & Behavioral Contract |
|---|---|---|---|
| `RUSH_LOG_LEVEL` | `debug`, `info`, `warn`, `error` | `warn` | Controls log filtering on `stderr`. `stdout` remains pure JSON-RPC for FastMCP. |
| `ANTHROPIC_API_KEY` | String | None | Detected when `rush review --llm` is requested. Note: `--llm` is a development stub making zero network requests. Values are never printed or logged. |
| `OPENAI_API_KEY` | String | None | Detected as fallback for `rush review --llm`. Development stub making zero network requests. |
| `PATH` | System Search Path | System | Used for dynamic discovery of all 77 engine binaries (`ruff`, `eslint`, `semgrep`, `trivy`, etc.). |
| `VIRTUAL_ENV` | Filesystem Path | None | Standard Python environment marker. |
| `PYTHONPATH` | Filesystem Paths | None | Standard Python import search path. |

No environment variable configures the memory subsystem's database path: `.rush/memory.db` (`TypedArtifactStore`, Phase 61) is a fixed repository-relative path, matching every other `.rush/` satellite path. The now-absorbed satellite files (`.rush/preferences.json`, `.rush/memory/invariants.json`, `.rush/memory/failures.db`, `.rush/hook_signatures.json`) are likewise not independently relocatable via environment variable.

---

## 2. Child Process Environment Sanitization

When external engines are invoked:
- Engine executions receive a clean child environment inheriting necessary runtime paths (`PATH`, `HOME`, `TEMP`, `USERPROFILE`).
- Discovered credentials, access tokens, and secret parameters are automatically redacted from all output findings and diagnostic logs as `[REDACTED]`.

See [Engine Directory](engine-directory.md) and [Result Reference](result-reference.md).

### Plugin Subprocess Environment Variables (Phase 56)
Plugin subprocesses run with scrubbed environments (`SandboxedEnvironment.get_sanitized_env()`). Only explicit non-secret variables declared in `allowed_env` and minimal system variables (`PATH`, `SYSTEMROOT`) are retained.

## Environment Variables in Invocation Context (Phase 57)

The `environment_digest` captures environment variables influencing tool behavior (e.g., `RUSH_*`, `PATH`, provider keys), ensuring environment changes invalidate stale cache entries.

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
### Provenance & Engine Environment Variables (Phase 59)
- `RUSH_BUILDER_ID`: Override default builder URI.
- `RUSH_ENGINE_PATH`: Explicit path prefix for isolated engine discovery.
