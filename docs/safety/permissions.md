# Permissions

## Provider continuation permission

`provider_resume` requires explicit network permission (`--allow-network`) before Rush invokes a supported user-owned CLI or fixed-loopback provider route. `9router_cli` may read `RUSH_9ROUTER_API_KEY` only to set `OPENAI_API_KEY` in its single Codex child process; it does not grant OAuth/browser access, automatic fallback, automatic retry, or direct `9router_api` use.

Rush distinguishes ordinary local inspection from expensive or mutating work. The table describes intended gate semantics, not universally enforced behavior: AI eval can launch without required grants (F08). `fix --dry-run` is bounded Ruff preview; `ship clean` previews registered artifacts and requires `--apply --allow-artifact-write` to delete. See [Known issues](../KNOWN_ISSUES.md).

| Boundary | CLI flag | Intended effect | Default |
|---|---|---|---|
| network access | `--allow-network` | Permit live network calls (e.g. k6, Lychee URL checks, Semgrep registry) | skip/refuse |
| vulnerability downloads | `--allow-download` | Permit downloading vulnerability feeds or schemas | skip/refuse |
| rules cache write | `--allow-cache-write` | Permit writing local tool caches | skip/refuse |
| compilation / DB build | `--allow-build` | Permit compiling project code or CodeQL databases | skip/refuse |
| long-running work | `--allow-slow` | Permit long-running test suites, mutation, fuzz, contract, or drift runs | skip/refuse |
| baseline / artifact write | `--allow-artifact-write` | Permit mutating or generating report/baseline artifacts | skip/refuse |
| browser runtime | `--allow-browser` | Permit launching browser engines (Playwright, Chromium/WebKit/Firefox) | skip/refuse |

## Execution Metadata

Gated routes may return execution metadata. The following shape is illustrative; version-only mutation/fuzz/load/contract paths can currently report simulated execution (F11), so inspect actual child evidence:

```json
{
  "metadata": {
    "execution": {
      "mode": "executed",
      "requested_permissions": {
        "network": false,
        "download": false,
        "cache_write": false,
        "build": false,
        "slow": true,
        "artifact_write": false,
        "browser": false
      },
      "granted_permissions": {
        "network": false,
        "download": false,
        "cache_write": false,
        "build": false,
        "slow": true,
        "artifact_write": false,
        "browser": false
      },
      "producer": "mutmut",
      "report_path": null
    }
  }
}
```

Consent is specific to each invocation and target. Rush never encodes blanket browser/network/publication permission in an assistant prompt or shared config.

## Physical Containment on Artifact Writes (Phase 55)

Writers that use `PhysicalRoot` enforce a containment boundary. Current checkpoint/governance paths bypass required physical checks (F03/F04), pending P64-03. Attempts to write artifacts through symlinks or parent directory escapes (`..`) raise `ContainmentError` and write zero bytes to disk.

### Plugin Execution Permissions (Phase 56)
Subprocesses spawned for plugin execution inherit user permissions. They execute strictly from byte-copied snapshot directories under `rush.io.PhysicalRoot` and receive secrets via protected pipes or stdin.

## Permission Snapshots in Invocation Context (Phase 57)

Permissions granted via `PermissionManager` are captured as an immutable tuple within `InvocationContext.permissions`. Mutating permissions during execution cannot alter the active context.

## Phase 58 Architecture: Capability Locks, CAS Memory, and Fail-Closed Patch Verification

The following component contracts are not whole-application guarantees. Checkpoint/governance symlink escapes, sandbox fallback, destructive cleanup and custom-output redaction defects remain open; see [Known issues](../KNOWN_ISSUES.md).

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
   - Patch-sandbox rollback still uses broad reset/clean and can discard unrelated work. Patch-sandbox restoration remains planned in [P64-04](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md); [F43](../reports/phase-64-66-application-review.md) remains open.

5. **Runtime Output Boundary Adapter Enforcement (`rush.contracts.operations`)**:
   - 100% of public operations declared in `governance/public-operations.toml` enforce their target adapters (`ToolOperationAdapter`, `AdminOperationAdapter`, `ServiceOperationAdapter`) at runtime boundaries while preserving native JSON-RPC service protocol messages.
