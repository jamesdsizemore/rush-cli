# Contributor Debugging & Diagnostics Guide

A comprehensive guide for debugging engine discovery, subprocess execution, MCP transport hangs, parser errors, and platform-specific behaviors.

For continuity, run a JSON save/restore and inspect only `metadata.handoff`: it is deliberately redacted and reports dependency `freshness`, a quarantined historic-instruction marker, and a failure receipt/tombstone. Diagnose a stale receipt by comparing declared paths, then save a fresh checkpoint; never add raw secrets, transcripts, or provider credentials to debugging output.

---

## 1. Structured Debugging Workflow

1. **Isolate stdout from stderr**: Run the problematic command with `--json` and inspect stdout (pure JSON result) and stderr (diagnostics).
   ```bash
   rush security . --json 2> debug.log
   ```
2. **Inspect Engine Discovery**: Run capabilities discovery to verify whether Rush locates external binaries:
   ```bash
   rush capabilities . --json
   ```
3. **Verify Environment Sanitation**: On Windows, foreign virtualenvs or global `PYTHONPATH` can leak into subprocesses. Always verify with:
   ```bash
   unset VIRTUAL_ENV PYTHONPATH
   ```

---

## 2. Common Failure Modes & Diagnostics

### Symptom: MCP Server Hangs Indefinitely
- **Root Cause**: An external engine was invoked without `stdin=subprocess.DEVNULL`, causing it to consume FastMCP's JSON-RPC standard input stream.
- **Resolution**: Ensure all command executions go through `run_subprocess()` in `src/rush/tools/common.py`.

### Symptom: Tool Returns `status: "error"`
- **Root Cause**: The engine emitted invalid JSON/XML/SARIF or exited with an unexpected crash code.
- **Resolution**: Inspect `raw` in the JSON result or check `tests/fixtures/engine_reports/<engine>/` to ensure parser handles malformed outputs gracefully.

### Symptom: Stale Finding Fingerprints
- **Root Cause**: Fingerprint calculation algorithm drifted or paths were not normalized with forward slashes.
- **Resolution**: Ensure finding paths are normalized relative to project root with forward slashes before hashing.

### Symptom: `error-catalog` or `iam-audit` Returns `status: "skipped"` on Export
- **Root Cause**: Writing output artifacts to disk requires explicit authorization.
- **Resolution**: Pass `--allow-artifact-write` in the CLI or set `allow_artifact_write=True` in MCP invocations.

### Symptom: `ToolConfig.options` Mutation Raises `TypeError`
- **Root Cause**: Tool configuration options are wrapped in immutable `types.MappingProxyType` to prevent concurrency corruption.
- **Resolution**: Call `resolve_tool_options(tool_name, config_options, invocation_options)` from `rush.config` to compute a merged dictionary.

See [Testing Guide](testing-guide.md) and [Tool Development](tool-development.md).


### Phase 50b Troubleshooting
- **`provenance-ai` returns `shallow_history: True`**: The repository is a shallow clone (`.git/shallow` exists or `git rev-parse --is-shallow-repository` is true). Historical commit trailers prior to clone depth are omitted.
- **`dead-asset` unreferenced warnings**: Assets are flagged if neither filename nor relative path appears in source files. Check for dynamic string interpolation in templates.
- **`pr-synthesize` CODEOWNERS matching**: Rules are matched against relative file paths from repository root using standard `fnmatch` patterns.

### Phase 50c Troubleshooting
- **`attest` subject is `source-tree` instead of package**: No built distribution file (`.whl` or `.tar.gz`) was found in `dist/`. Run `uv build` first, or specify `--artifact-path`.
- **`mem-profile` returns `skipped` for dynamic mode**: Dynamic profiling requires explicit `--allow-slow` permission.
- **`cold-start` heavy import warnings**: Move heavy package imports (`torch`, `pandas`, `boto3`) inside the function or method where they are used.
- **`offline-review` returns `skipped`**: The ONNX model `.rush/models/review.onnx` or the `onnxruntime` package is not present.
- **`benchmark` returns `skipped`**: No baseline was found in `.rush/baselines.json`. Run `rush benchmark check . --record --allow-cache-write` to establish a baseline.

### Phase 53 Troubleshooting: Diagnostics & Write Boundaries
- **Disappearing exception tracebacks (R-008)**: Previously, logging an exception with `exc_info` failed silently inside `NdjsonHandler.emit` due to tuple formatting. This is resolved: all exceptions emit complete single-line redacted NDJSON to stderr with a fallback JSON emitter on formatting failure.
- **Sanitized dictionary keys & collision suffixing**: If two dictionary keys contain distinct secrets that both redact to `"[REDACTED — secret-like value]"`, the second key is deterministically suffixed with `__collision_1` and recorded in collision metadata rather than overwriting the first key.
- **Strict stderr logging**: MCP JSON-RPC requires that stdout contain zero logging output. Logging must always go through `get_logger()` or `NdjsonHandler` to ensure only stderr is used.

### Phase 54 Troubleshooting: ToolResultV1 Schema Validation
- **`ValidationErrorV1` failure codes**:
  - `MISSING_REQUIRED_KEY`: One of the 8 canonical fields (`schema_version`, `tool`, `engine`, `status`, `duration_ms`, `timestamp`, `summary`, `findings`) was missing from output.
  - `INVALID_TYPE`: Field type does not conform (e.g. `duration_ms` is negative or float, `findings` is not a list).
  - `INVALID_STATUS`: Status is not one of `ok`, `warn`, `fail`, `error`, `skipped`.
  - `INVALID_TIMESTAMP`: Timestamp is not a valid ISO 8601 UTC string ending in `Z`.
  - `FINDING_MISSING_REQUIRED_KEY`: Finding is missing `id`, `path`, `line`, `message`, or `severity`.
  - `INVALID_SEVERITY`: Finding severity is not one of `info`, `warning`, `error`.
  - `SERVICE_TOOL_RESULT_PROHIBITED`: A service-kind operation (e.g. MCP protocol handler) attempted to return a wrapped `ToolResultV1`.

### Phase 55 Troubleshooting: Physical Containment & Atomic Write Errors
- **`ContainmentError` codes**:
  - `ABSOLUTE_PATH_DISALLOWED`: Target path starts with `/`, `\\`, or a drive letter. Ensure relative paths are passed.
  - `PARENT_TRAVERSAL_DISALLOWED`: Path contains `..` components. Use normalized relative paths within the workspace.
  - `SYMLINK_DISALLOWED`: A component along the path is a symlink. Symlinks within contained workspaces are forbidden.
  - `REPARSE_POINT_DISALLOWED`: Path target or parent is a Windows directory junction or reparse point.
  - `PATH_ESCAPE_DISALLOWED`: Resolved target path escapes the physical root directory.
- **`AtomicWriteError` codes**:
  - `WRITE_FAILED`: An injected or filesystem fault interrupted writing. Check that the destination filesystem is writable and has free space. On failure, `AtomicFile` cleans up its `.rush_tmp_*` file and leaves the original destination intact.
- **`VerifierError`**:
  - Raised when attempting to create a `VerifierRecord` from a capability with length < 16 characters or Shannon entropy < 2.5 bits/symbol.

### Troubleshooting Plugin Trust & Execution (Phase 56)
- `UntrustedPluginError`: The plugin closure has not been granted trust in the user ledger. Run `rush trust plugin <name>` to authorize.
- `RECEIPT_NOT_AUTHORIZING`: In-repo `.rush/trust.json` detected from a clone. Must run explicit user grant.
- `ClosureTamperedError`: Source code or snapshot files were modified after trust grant. Run `rush trust plugin <name>` to re-approve the new closure.
- `SecretChannelError`: Declared secret channel is unsupported on the platform. Use `stdin` channel or verify OS descriptor support.

## Debugging Invocation & Cache Issues (Phase 57)

- **Cache Misses**: Verify all required identity fields (`tool_revision`, `normalizer_revision`, `environment_digest`) are populated in `InvocationContext`.
- **`ScopeWideningError`**: Check whether target paths navigate through symlinks or junctions outside the workspace root.
- **`ProviderEgressError`**: Verify remote endpoint matches `APPROVED_PROVIDER_ORIGINS` and does not issue cross-origin redirects.

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
### Provenance & Engine Troubleshooting (Phase 59)
- `DuplicateKeyError`: Duplicate key detected in provenance JSON.
- `AmbiguousKeyError`: Unicode NFKC collision detected.
- `UntrustedSignerError`: Signer key not in allowlist.
- `AllSkippedViolationError`: Supported engine returned all-skipped results.

### Memory Subsystem Troubleshooting (Phase 61)
- **WAL lock contention**: `.rush/memory.db` is SQLite WAL mode; a concurrent long-running writer can block another writer. `TypedArtifactStore` opens its connection with the same timeout pattern as `ResultCache._init_db()` (`cache.py:103`) — a stuck lock past that timeout raises rather than hanging silently.
- **`stale: true` on a recalled record**: the `symbol_ref`+`content_hash` pair no longer matches the current AST content-hash of that symbol (Invariant 6) — the underlying code changed since the record was written. Not an error; re-verify before trusting the content.
- **Signature mismatch on recall**: `recall()` recomputes `hashlib.sha256(content_bytes).hexdigest()` against the row's current `content` and compares it to the stored `signature`; a mismatch raises. This is a corruption-detection checksum (accidental corruption, partial write, bit rot, a hand-edited row), not cryptographic tamper evidence against a malicious database writer — see `docs/safety/security-model.md`.
- **`recall()` returns zero rows unexpectedly**: check the session allowlist — an empty/absent allowlist fails closed (returns no rows), it never falls back to "allow all" (T-61.38).
- **A migrated record appears missing**: check for the source's `.migrated`-suffixed satellite file (e.g. `.rush/hook_signatures.json.migrated`) — Invariant 5 renames rather than deletes; re-running the migration function is idempotent and safe.
- `ReleaseGateFailureError`: Release-gate engine (mypy) unavailable or failing.
