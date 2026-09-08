# Incident & Security Handling Protocol

This runbook defines the operational protocol for handling security vulnerabilities, credential leaks, and safety boundaries in Rush CLI.

---

## 1. Security Sensitivity Classifications

The following events are treated as high-priority security incidents:
- **Credential Disclosure / Leakage**: Raw secrets, tokens, or private keys appearing unredacted in findings or logs.
- **Subprocess Escape / Injection**: Arbitrary shell execution or path traversal outside project boundaries.
- **MCP Protocol Pollution**: Engine stdout polluting FastMCP stdio transport frames.
- **Unauthorized Side Effects**: Any engine performing remote downloads, network writes, or git mutations without explicit `--allow-*` flags.

---

## 2. 7-Step Security Response Workflow

1. **Private Triage**: Move issue to a private advisory; do not ask for public reproduction data.
2. **Containment**: If vulnerability is reproducible, isolate the affected engine adapter.
3. **Synthetic Reproduction**: Create sanitized unit tests that reproduce the vulnerability without real credentials.
4. **Fix & Redaction Verification**: Implement fix using strict subprocess isolation and regex redaction.
5. **Regression Testing**: Run `uv run --python 3.12 --extra dev python -m pytest tests/ -q` and verify all security reference test suites.
6. **Security Advisory & CVE**: Prepare a private advisory with remediation steps; publish only with explicit authorization.
7. **Release Patch**: Verify the patch and release artifacts. Version changes and publication require explicit authorization.

See [Security Policy](../SECURITY.md) and [Permissions](../safety/permissions.md).

---

## 3. Sanitization & Diagnostic Invariants (Phase 53)

Maintainers must verify that all newly added tools, exports, and logging calls comply with Phase 53 invariants:
- **Zero Unredacted Persistent Writes**: Any write to `.rush/` or exported files (SARIF, HTML, attestation statements, IAM policies) must pass through `sanitize_value` or `SecretRedactor.redact_text`.
- **Zero Raw Exceptions to Logs**: Exceptions logged to stderr must format tracebacks safely and redact secrets from messages and stack traces.
- **Fail-Safe Logging Fallback**: `NdjsonHandler` must never raise unhandled exceptions or drop log records silently.
- **Strict Stdout Purity**: Subprocesses, background threads, and logging handlers must never write directly to `sys.stdout`.

## 4. Physical Containment & Verifier Security Invariants (Phase 55)
- **Zero Path Traversal / Symlink Escapes**: Disk operations targeting repository workspaces must use `PhysicalRoot.open_contained()` (`src/rush/io/physical_paths.py`), which fail-closed blocks absolute paths, parent traversals (`..`), symlinks across all parent directories, and Windows reparse points.
- **Fail-Closed Atomic Replacement**: File writes must use `AtomicFile` (`src/rush/io/atomic_file.py`) with same-directory unique temporary files (`.rush_tmp_`), explicit `flush()` and `os.fsync()`, and owned-temp cleanup only. Target files must never be corrupted by partial writes.
- **Non-Recoverable Capability Storage**: Stored tokens, locks, or trust credentials must never persist raw secrets. All capability verification must use `VerifierRecord` (`src/rush/io/verifier_record.py`) storing only PBKDF2-HMAC-SHA256 salted hashes with constant-time verification.

### Plugin Trust Breach Triage (Phase 56)
If a malicious plugin closure is detected, preserve incident evidence and run `rush trust --plugin PLUGIN_NAME --revoke`, replacing `PLUGIN_NAME` with the affected plugin. Verify the resulting trust state; do not assume revocation deletes every plugin snapshot or running process.

## Cache & Egress Incident Procedures (Phase 57)

If cache poisoning is suspected:
1. Preserve the suspected cache as incident evidence, then run `rush cache clean` from the affected repository. This clears the result cache; do not delete the separate `.rush/memory.db` memory store as a cache remedy.
2. Verify provider API keys and review egress logs for unauthorized redirect attempts.

## Memory Store Incident Triage (Phase 61)

If a `STATED` record's checksum mismatch is reported: this catches accidental corruption (partial write, bit rot, a hand-edited row), not necessarily malicious tampering — the checksum is unkeyed SHA-256 stored in the same row it hashes, so it is not tamper evidence against an attacker with `UPDATE` access to `memory_artifacts` (`docs/safety/security-model.md`). Triage as a data-integrity incident: identify the affected row(s) via `origin_kind`/`origin_id`, check for a concurrent-writer bug before assuming compromise, and re-derive the record from its source (a `.migrated` satellite file, if the row came from migration) rather than trusting the mismatched content. If a promoted record is suspected to have bypassed `evaluate_promotion()` entirely (a `STATED` row that never had a genuine screen/pre-filter/schema/grounding/corroboration pass), treat it as a code-level incident in `trust.py`, not a data one — the write-promotion rule is the only path to `STATED`.

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
   - Failed promotion can invoke destructive Git cleanup. Exact preservation of arbitrary working-tree state is not established: review the open rollback and dry-run findings in the [application review](../reports/phase-64-66-application-review.md), preserve incident evidence, and verify the Phase 64 repair before relying on rollback.

5. **Runtime Output Boundary Adapter Enforcement (`rush.contracts.operations`)**:
   - Reconcile live registrations with `governance/public-operations.toml` and exercise `ToolOperationAdapter`, `AdminOperationAdapter` and `ServiceOperationAdapter` at their runtime boundaries. Manifest declarations alone do not establish enforcement; stdio output must preserve JSON-RPC service messages.
### Supply Chain & Provenance Incidents (Phase 59)
Invalid signatures, duplicate key attempts, or untrusted builders raise `ProvenanceError` and abort execution.
