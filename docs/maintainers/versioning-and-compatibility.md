# Maintainer Versioning & Compatibility Contracts

Guidelines for maintaining backward compatibility across CLI commands, FastMCP registrations, configuration files, and ToolResult schemas.

---

## 1. Stable Compatibility Contracts

1. **CLI Commands and Arguments**: Registered command names, each command's own options and required arguments, and exit codes. Flags such as `--check` and `--allow-*` are not universal; compare the specific command's help and runtime contract.
2. **FastMCP Registration Contracts**: Tool names (`rush_<name>`), parameter types, and docstrings.
3. **Canonical ToolResult**: Preserve the quality-tool result contract, including `tool`, `engine`, `engine_version`, `status`, `duration_ms`, `summary` and `findings`, with `raw` where supplied. Administrative operations and service transports have separate contracts; do not wrap JSON-RPC service messages as quality-tool results.
4. **Configuration Syntax**: `rush.toml` schema and table names.

---

## 2. Breaking Change Deprecation Policy

If a breaking change is unavoidable:
1. Announce deprecation in minor release notes (`0.X.0`) with actionable migration guidance.
2. Maintain backward-compatible fallback for at least one minor release cycle.
3. Remove deprecated behavior only in the subsequent major version release.

---

## 3. Version Resolution & Package Identity Architecture (Phase 52)

- **Single Version Source**: All runtime modules must consume `rush.__version__`. Never hardcode static version literals (e.g. `"0.2.0"`, `"0.3.0"`) in headers, templates, or exporters.
- **Distribution Metadata Resolution**: `rush.__version__` resolves dynamically via `importlib.metadata.version("rush-cli")`. When running uninstalled, it falls back to `"0.3.0"`.
- **Strict Root Namespace**: All internal imports across `src/` and `tests/` must use canonical `rush` or relative imports. `src.rush` imports are strictly prohibited.

---

## 4. Result Schema Evolution & Compatibility (Phase 54)

- **Schema Version Header**: Every serialized tool result includes `schema_version = "1.0.0"`. SemVer rules apply to schema changes:
  - Patch updates: Non-breaking metadata additions.
  - Minor updates: Optional additive fields.
  - Major updates: Field deprecation, name changes, or structural alterations.
- **Legacy Adapter Compatibility**: The schema kernel provides backward compatibility through `adapt_legacy_tool_result()` and `adapt_legacy_finding()`. Legacy severities (`notice`, `suggestion`, `fatal`) map deterministically to canonical levels (`info`, `warning`, `error`).
- **Standard Library Invariant**: Schema models are implemented in pure standard library dataclasses (`src/rush/contracts/results.py`) without external schema dependencies (e.g. Pydantic).

See [Versioning Policy](../VERSIONING.md) and [Release Process](../developer/release-process.md).

---

## 5. File I/O Primitives Compatibility (Phase 55)

- **`rush.io` Primitives**: `PhysicalRoot`, `AtomicFile`, and `VerifierRecord` are canonical internal primitives.
- **Sanitized Contracts**: `write_bytes` and `write_json` strictly enforce sanitized wrappers (`SanitizedBytes`, `SanitizedJsonValue`, `SanitizationResult`).
- **One-Way Verifier Compatibility**: `VerifierRecord` maintains backward-compatible verification across schema versions via explicit `version = "1.0.0"` records.

### Plugin Closure & Manifest Compatibility (Phase 56)
Plugin manifest schema versioning (`schema_version = "1.0.0"`) ensures backward compatibility for declared configuration tables and secret reference descriptors.

## Invocation Contract Compatibility (Phase 57)

Changes to `InvocationContext` fields must preserve backwards compatibility with existing CLI and FastMCP callers. Cache key format changes automatically invalidate previous entries without manual migration.

## Unified Memory Store Compatibility (Phase 61)

`MemoryArtifact`'s field set ([Architecture](../ARCHITECTURE.md), "Phase 61 Architecture") defines the `.rush/memory.db` `memory_artifacts` table contract; adding a column must preserve existing meanings. Preserve compatibility entrypoints in `preference_store.py`, `invariant_graph.py`, `merkle_invalidator.py`, `checkpoint_journal.py` and `failure_ledger.py`. Migration behavior differs by satellite: migrated JSON inputs may retain a `.migrated` copy, but `FailureLedger` continues reading and writing `.rush/memory/failures.db`; its migration copies rows into the unified store and does not rename that database. Do not assume every satellite is read-only or automatically synchronized after migration. The [Phase 63 plan](../phase-plans/phase-63-memory-capabilities-vibecoder-plan.md) retains the connected-memory requirements.

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
   - Failed promotion can invoke destructive Git cleanup; exact working-tree restoration is not a verified compatibility guarantee. The [application review](../reports/phase-64-66-application-review.md) records unresolved rollback and dry-run defects assigned to Phase 64.

5. **Runtime Output Boundary Adapter Enforcement (`rush.contracts.operations`)**:
   - Verify live operation coverage and boundary adapters (`ToolOperationAdapter`, `AdminOperationAdapter`, `ServiceOperationAdapter`) against the candidate. A saved manifest does not establish full runtime enforcement; preserve native JSON-RPC service protocol messages.
### Engine Support Taxonomy (Phase 59)
Engine support classes (`mandatory`, `supported-optional`, `best-effort`) are versioned in `governance/engine-support.toml`.
