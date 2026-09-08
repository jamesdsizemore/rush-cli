# Maintainers/Release Playbook

## Pre-Release Gate Verification (Phases 41–43)
Before publishing a release:
```bash
rush ship clean
rush ship env
rush ship docs
rush ship migration
rush ship semver
rush ship pack
rush ship gate
```

## Pre-Release Architecture & Blast Radius Checks
1. Run `rush arch-guard` to ensure clean architectural boundaries.
2. Run `rush blast-radius` across all modified core modules.



## Pre-Release API Diff Verification
Verify public API contract compatibility using `rush api-diff --base main`.



## Pre-Release Database Audit
Execute `rush db-drift` to guarantee zero unmigrated schema changes before tagging releases.



## Pre-Release Traceability Verification
Run `rush trace` and `rush simulate-ci` to verify full specification compliance prior to tagging releases.



## Flagship v0.3.0 Release Checklist
1. Execute `rush license-matrix` and `rush iam-audit`.
2. Run `rush attest --target-artifact dist/*.whl --export-path dist/release.intoto.json --allow-artifact-write`.
3. Verify all 52 catalog tools and 73 FastMCP tools pass test suites.

## Pre-Release Installed Artifact & Governance Probes (Phases 51 & 52: Findings R-001 & R-012 Closed)
Before publishing any release or pushing tags:
1. Verify first-party coverage manifest sync: `python scripts/build_remediation_manifests.py`
2. Verify public operations inventory sync: `python scripts/build_remediation_manifests.py --operations`
3. Execute clean isolated artifact probes outside the checkout:
   ```bash
   uv build
   python scripts/probe_installed_artifacts.py --json
   ```
4. Verify Package Identity & Version Authority contract suites:
   ```bash
   pytest tests/test_phase52_package_identity.py tests/test_phase52_version_contract.py tests/test_phase52_installed_artifacts.py -v
   ```
5. Confirm `governance/remediation-phase-52.toml` status is `completed` and R-001 and R-012 in `governance/remediation-contracts.toml` are marked `completed`.

## Pre-Release Sanitization & Diagnostic Probes (Phase 53: Findings R-002 & R-008 Closed)
Before finalizing any release candidate:
1. Verify deep recursive sanitization and pre-truncation contracts:
   ```bash
   pytest tests/test_phase53_sanitizer_contract.py tests/test_phase53_output_boundaries.py tests/test_phase53_governance_writers.py tests/test_phase53_state_writers.py -v
   ```
2. Verify exception diagnostics and stderr logging invariants:
   ```bash
   pytest tests/test_phase53_logging_diagnostics.py -v
   ```
3. Confirm `governance/remediation-phase-53.toml` status is `completed` and R-002 and R-008 in `governance/remediation-contracts.toml` are marked `completed`.

## Pre-Release Tool Result Schema & Operation Probes (Phase 54: Finding R-011 Closed)
Before finalizing any release candidate:
1. Verify ToolResultV1 schema kernel and operation adapter contract suites:
   ```bash
   pytest tests/test_phase54_result_schema.py tests/test_phase54_operation_adapters.py -v
   ```
2. Confirm 100% operation reconciliation (146 operations) across Click leaves and FastMCP routes:
   ```bash
   pytest tests/test_phase51_public_operations.py -v
   ```
3. Confirm `governance/remediation-phase-54.toml` status is `completed` and R-011 in `governance/remediation-contracts.toml` is marked `completed`.

## Pre-Release Physical Containment & Verifier Probes (Phase 55: Foundations for R-003, R-009, R-010, R-016)
Before finalizing any release candidate:
1. Verify Phase 55 contract suites:
   ```bash
   pytest tests/test_phase55_atomic_file.py tests/test_phase55_physical_containment.py tests/test_phase55_verifier_record.py -v
   ```
2. Confirm `governance/remediation-phase-55.toml` status is `completed`.

### Phase 56 Pre-Release Verification
- Verify all 16 Phase 56 contract tests pass.
- Verify user ledger authority operates outside git repositories.
- Verify plugin output conforms to `ToolResultV1`.

## Phase 57 Release Gates

Prior to release:
1. Verify all 48 Phase 57 tests pass (`pytest tests/test_phase57_*.py`).
2. Verify full test suite passes with >= 1,134 tests.
3. Verify public operations manifest reconciles with 100% of declared operations.

## Phase 61 Release Gates

Prior to release:
1. Verify all 39 Phase 61 contract tests pass (`pytest tests/test_phase61_*.py -v`).
2. Verify `PRAGMA journal_mode` on `.rush/memory.db` returns `"wal"`.
3. Verify no `STATED` row exists that bypassed `evaluate_promotion()` (every `STATED` row has a non-null `signature`).
4. Verify all 8 satellite sources' data is queryable through `TypedArtifactStore`, and their old files are `.migrated`, never deleted.
5. Verify `MemoryTool` is present in `ALL_TOOLS`/`TOOL_SPECS` and has a `@cli.group(name="memory")`.
6. Verify `governance/remediation-phase-61.toml` documents all 39 contract tests.

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
### Release Verification Gates (Phase 59)
1. Run `python scripts/probe_installed_artifacts.py` on wheel and sdist.
2. Verify `mypy --version` and `mypy src/rush` execute with exit code 0 (mandatory non-skipped release gate).
3. Generate and verify unsigned provenance draft with real artifact digests.
4. Run full test suite (1,189+ tests passing with 0 warnings).
