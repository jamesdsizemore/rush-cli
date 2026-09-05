# Phase 58 Implementation Plan: Capability Locks, Contained Persistence, and Fail-Closed Patch Verification

## 1. Purpose and Status

- **Operation:** Comprehensive implementation plan for Phase 58 remediation.
- **Planning Status:** Implementation-ready; fully verified against repo codebase and active development.
- **Implementation Status:** Authorized for strict TDD execution.
- **Authority:** Governing Roadmap findings R-009, R-010, R-011 (runtime migration), and R-016 (`governance/remediation-contracts.toml`).
- **Predecessors:** Accepted Phase 51 operation manifest, Phase 52 package identity, Phase 53 sanitizer (`rush.safety.redactor`), Phase 54 result schema kernel (`rush.contracts.results.ToolResultV1`), Phase 55 physical containment and verifier primitives (`rush.io.PhysicalRoot`, `rush.io.AtomicFile`, `rush.io.VerifierRecord`), Phase 56 user-owned plugin trust, and Phase 57 invocation context and cryptographic cache.
- **Successor:** Phase 59 (SLSA Provenance, Attestation, and Engine Conformance).
- **Security Boundary:**
  1. Coordination locks must never persist raw caller capabilities; verifier-only records generated via `rush.io.VerifierRecord` with generation counters.
  2. Persistent memory stores (`PreferenceStore`, `InvariantGraph`, `MerkleInvalidator`) must execute atomic Compare-And-Swap (CAS) transactions via `rush.io.AtomicFile` with distinct error states (`StoreNotFound`, `StoreCorruptionError`, `StoreValidationError`, `StoreIOError`).
  3. Session journals (`CheckpointJournal`) must write atomic records with explicit schema versioning (`1.0.0`) and retain corrupt records as verifiable cryptographic evidence.
  4. Patch workspaces must be strictly contained under `rush.io.PhysicalRoot` and refuse dirty checkouts; verified success requires executing at least one bound passing verification command (zero commands never verifies); promotion failure triggers automatic atomic rollback.
  5. All public operations must enforce their declared target adapters (`ToolOperationAdapter`, `AdminOperationAdapter`, `ServiceOperationAdapter`) at runtime boundaries while preserving unwrapped JSON-RPC service protocol messages.
- **Protected Boundaries:** Roadmap requirements, dependency lockfile, engine taxonomy, and release versioning.
- **Zero-Downscope Invariant:** This plan is the immutable contract. Stubs returning 'unknown', permissive test assertions (`assert status in (...)`), or skipping verification commands are strictly prohibited. Every covered failure mode must fail closed.
- **Lifecycle Boundary:** No commit, push, merge, tag, publish, release, hooks, history rewrite, live secrets, or live network calls without explicit user instructions.

---

## 2. Authority, Predecessor Artifacts, and Concrete Evidence

Authority order: User instructions → `AGENTS.md` → Roadmap (`governance/remediation-contracts.toml`) → Phases 51-57 contracts → Current mesh/memory/patch source and test suites.

### 2.1 Concrete Codebase Audit & Semantic Drift Identification

An exhaustive audit of the existing codebase against findings R-009, R-010, R-011, and R-016 identified seven critical vulnerabilities and architectural drifts:

1. **Drift 1: Lock Ownership & Raw Capability Leakage (R-009)**:
   - *Existing Code:* `src/rush/mcp_mesh/lock_manager.py` implements `acquire()` and `release()` keyed by an arbitrary string `agent_id`. It performs direct `lock_p.write_text()` without TOCTOU protection or cryptographic verification. Anyone who knows the `agent_id` or lock path can steal or release the lock.
   - *Vulnerability:* Unauthenticated lock theft, TOCTOU race conditions between concurrent agents, and lack of capability custody.
   - *Remediation (R-009):* Introduce `src/rush/mcp_mesh/capabilities.py`. The caller generates and retains a high-entropy capability token delivered via protected channels (protected stdin, descriptor, or sensitive MCP parameter). `MeshLockManager` stores verifier-only metadata generated via `rush.io.VerifierRecord` (PBKDF2-HMAC-SHA256, 100k rounds, 32-byte salt). `acquire` never persists or returns the raw capability. Renewal and release require presenting the caller capability verified in constant time. Every acquisition increments a monotonic `generation: int`. Stale capabilities fail closed.

2. **Drift 2: Map Persistence Conflation & Lost Updates (R-010)**:
   - *Existing Code:* `PreferenceStore` (`src/rush/memory/preference_store.py`), `InvariantGraph` (`src/rush/memory/invariant_graph.py`), and `MerkleInvalidator` (`src/rush/memory/merkle_invalidator.py`) read and write raw JSON files directly (`read_text` / `write_text`). They catch `Exception` and return `{}` or default objects.
   - *Vulnerability:* Lost updates on concurrent writes (no Compare-And-Swap or versioning); silent destruction of corrupt data (corrupt file parsed as empty `{}`); partial writes on crashes.
   - *Remediation (R-010):* Introduce `src/rush/memory/transactions.py`. Stores must use CAS (Compare-And-Swap) with version checks (`version: int`) and `rush.io.AtomicFile` with `SanitizedJsonValue`. Absent file (`StoreNotFoundError`), corrupt file (`StoreCorruptionError`), schema invalid (`StoreValidationError`), and I/O error (`StoreIOError`) must be distinct exceptions and states. Corrupt files are NEVER treated as empty or absent.

3. **Drift 3: Checkpoint Journal Atomic Replacement & Corruption Evidence (R-010)**:
   - *Existing Code:* `src/rush/memory/checkpoint_journal.py` writes checkpoints via `dest.write_text()`. When listing checkpoints, it catches `Exception` and silently skips corrupt entries with `continue`.
   - *Vulnerability:* Corrupt session checkpoints vanish from developer visibility, masking disk failures, truncation, or tampering.
   - *Remediation (R-010):* `CheckpointJournal` must use `rush.io.AtomicFile` for all record writes with schema version `1.0.0`. Corrupt JSON files must be retained, cryptographically digested (SHA-256), and explicitly listed in `list_checkpoints` as corrupt entries with status `corrupt` and digest evidence.

4. **Drift 4: Uncontained Patch Workspaces & Missing Rollback (R-016)**:
   - *Existing Code:* `GitSandbox` (`src/rush/core/git_sandbox.py`) and `PatchSandboxManager` (`src/rush/patch/sandbox.py`) create worktrees at `.rush/worktrees/sandbox-...` without `PhysicalRoot` containment checks. If git worktree creation fails, `PatchSandboxManager` creates an empty folder. `PatchPromoter` (`src/rush/patch/promoter.py`) runs `git apply` directly on `repo_root` without pre-checking for dirty state, and on failure leaves the repository corrupted with no rollback.
   - *Vulnerability:* Uncontained filesystem writes, corruption of developer worktrees, and lack of rollback on failed patch application.
   - *Remediation (R-016):* Worktree creation and all patch operations must be strictly contained under `rush.io.PhysicalRoot`. Target workspace must be verified clean before sandboxing (`is_clean()` / dirty check). If dirty, patch workflow fails closed with `DirtyWorkspaceError`. If promotion or application fails at any point, automatic atomic rollback restores the repository to its exact pre-patch commit and state.

5. **Drift 5: Patch Verifier Succeeding with Zero Executed Commands (R-016)**:
   - *Existing Code:* `PatchVerifier.verify_patch()` (`src/rush/patch/verifier.py`) checks for `pytest`, `npm`, `cargo`. If none of these binaries are found or if the project has no recognizable config, it returns `True, 'All automated tests and quality checks passed cleanly in sandbox.'`.
   - *Vulnerability:* A patch can be declared 'verified safe' having executed ZERO test commands, masking regressions.
   - *Remediation (R-016):* Verified success requires executing at least one declared or detected verification command and confirming it passed (`returncode == 0`). Zero selected or executed commands must return `unavailable` or `failed` with reason `NO_VERIFICATION_COMMANDS_EXECUTED`, never verified success.

6. **Drift 6: Incomplete Patch Identity Binding (R-016)**:
   - *Existing Code:* Patch execution only checks git diff without binding clean base commit, patch hash, sandbox path, test command plan, configuration digest, and review class.
   - *Vulnerability:* Patches verified in one context can be applied to differing states, creating semantic drift and test evasion.
   - *Remediation (R-016):* Introduce `PatchContract` in `src/rush/patch/contracts.py`. It cryptographically binds: clean base digest, patch content digest, sandbox identity, expected result tree/diff, required command plan, config digest, and review class. Any drift between planned and actual state refuses execution.

7. **Drift 7: Manifest-Wide Output Contract Enforcement (R-011 Runtime Migration)**:
   - *Existing Code:* Certain runtime boundaries (mesh daemon, fix promoter, continuity restore) return unadapted dictionaries or catch exceptions loosely.
   - *Vulnerability:* Schema violations leaking across runtime boundaries without `ToolResultV1` validation or proper exit codes.
   - *Remediation (R-011):* Every public operation boundary in `governance/public-operations.toml` must enforce its declared adapter (`ToolOperationAdapter`, `AdminOperationAdapter`, `ServiceOperationAdapter`) immediately after sanitization and before transport return. Stdio and JSON-RPC service messages (`initialize`, `tools/list`) remain unwrapped protocol frames.

---

## 3. Goals, Non-Goals, Operational Exclusions, and Security Boundaries

### 3.1 Primary Goals
1. Implement `LockCapabilityInput` and verifier-only `MeshLockManager` using `rush.io.VerifierRecord` and `rush.io.AtomicFile` (R-009).
2. Implement CAS map transactions (`CASMapTransaction`) for `PreferenceStore`, `InvariantGraph`, and `MerkleInvalidator` with truthful error states (R-010).
3. Implement atomic `CheckpointJournal` with schema versioning (`1.0.0`) and retained corrupt evidence (R-010).
4. Implement `PatchContract` binding clean base, patch, sandbox, command plan, and policy identities (R-016).
5. Implement fail-closed `PatchVerifier` requiring >= 1 executed passing command (zero commands never verify) and atomic rollback engine (R-016).
6. Enforce manifest-wide output adapter compliance across all runtime boundaries while preserving native service protocol frames (R-011).
7. Synchronize all 46 documentation files across `/docs` and all 22 subfolders.

### 3.2 Non-Goals and Operational Exclusions
1. **No Dependency Additions:** 100% pure Python 3.12 standard library.
2. **No Live Network or External Credentials:** All tests use local fixtures, mocks, and spies.
3. **No Migration of Phase 59 Internals:** SLSA cryptographic signatures and engine conformance belong to Phase 59.

---

## 4. Admission Gate and Predecessor Verification

The following criteria must be verified prior to initiating Phase 58 development:
1. `governance/remediation-phase-57.toml` is present with status `completed` (all 25 Phase 57 contract tests passed).
2. Clean test baseline of 1,134 passed tests.
3. Phase 51 public operations manifest (`governance/public-operations.toml`) is present with 146 operations mapped.
4. Phase 54 operation adapters (`ToolOperationAdapter`, `AdminOperationAdapter`, `ServiceOperationAdapter`) and `ToolResultV1` operational.
5. Phase 55 physical containment primitives (`rush.io.PhysicalRoot`, `rush.io.AtomicFile`, `rush.io.VerifierRecord`) operational.
6. Phase 56 plugin trust ledger and protected secret channels operational.
7. Phase 57 unified `InvocationContext` and cryptographic cache policy operational.
8. Execution of P58.0.1 maps every lock, persistence, patch, and output seam before RED tasks begin.

---

## 5. Requirement-Ownership Ledger (R-009, R-010, R-011, R-016)

| Requirement ID | Finding Summary | Workstreams | Specific Contract Outcomes |
|---|---|---|---|
| **R-009** | Coordination lock acquisition and release lack verified identity and cleanup | P58.1, P58.2 | Caller-retained capabilities; verifier-only `MeshLockManager` using `VerifierRecord`; generation counters; physical containment; fail-closed recovery. |
| **R-010** | Persistence operations bypass AtomicFile and lack schema migration | P58.3, P58.4 | CAS map transactions (`CASMapTransaction`) with versioning; distinct absent/corrupt/invalid/io errors; atomic `CheckpointJournal` with schema 1.0.0 and retained corrupt evidence. |
| **R-011** | ToolResult schema kernel is not enforced across all engines and normalizers (Runtime Migration) | P58.7 | Runtime enforcement of `ToolOperationAdapter`, `AdminOperationAdapter`, and `ServiceOperationAdapter` across 100% of public operation boundaries. |
| **R-016** | Patch workflow creates uncontained workspaces and lacks atomic rollback | P58.5, P58.6 | `PatchContract` identity binding; clean base verification; `PatchVerifier` requiring >= 1 executed passing command (0 commands never verify); atomic rollback engine under `PhysicalRoot`. |

---

## 6. Shared Architecture, State Invariants, and Data Structures

### 6.1 Capability Locks (`src/rush/mcp_mesh/capabilities.py`)

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

LockState = Literal['available', 'held', 'expired', 'corrupted']

@dataclass(frozen=True)
class LockCapabilityInput:
    """Represents caller-provided capability token delivered via protected channels."""
    token: str  # High-entropy secret token (>= 16 chars, >= 2.5 entropy)
    agent_id: str
    channel_type: Literal['stdin', 'descriptor', 'mcp_sensitive']

@dataclass(frozen=True)
class LockLeaseRecord:
    """Verifier-only metadata persisted to disk via AtomicFile. Never contains raw token."""
    resource_path: str
    owner_agent_id: str
    generation: int
    verifier_record: dict[str, Any]  # PBKDF2 verifier from rush.io.VerifierRecord
    acquired_at: float
    expires_at: float
    physical_root: str
```

### 6.2 CAS Map Transactions (`src/rush/memory/transactions.py`)

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generic, TypeVar

T = TypeVar('T')

class StoreError(Exception):
    """Base exception for transactional storage errors."""
    pass

class StoreNotFoundError(StoreError):
    """Raised when persistent store file does not exist."""
    pass

class StoreCorruptionError(StoreError):
    """Raised when persistent store contains unparseable or tampered bytes."""
    def __init__(self, message: str, raw_bytes: bytes, digest: str):
        super().__init__(message)
        self.raw_bytes = raw_bytes
        self.digest = digest

class StoreValidationError(StoreError):
    """Raised when persistent store schema validation fails."""
    pass

class StoreIOError(StoreError):
    """Raised on underlying I/O or filesystem failure."""
    pass

class CASConflictError(StoreError):
    """Raised when compare-and-swap detects a concurrent version conflict."""
    pass

@dataclass(frozen=True)
class VersionedSnapshot(Generic[T]):
    version: int
    data: T
    content_hash: str
```

### 6.3 Patch Contracts & Verification (`src/rush/patch/contracts.py`)

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

PatchOutcome = Literal['completed', 'unavailable', 'failed']

@dataclass(frozen=True)
class VerifierCommandPlan:
    command: tuple[str, ...]
    cwd_relative: str
    expected_exit_code: int = 0
    timeout_seconds: float = 60.0

@dataclass(frozen=True)
class PatchContract:
    base_commit: str
    base_tree_digest: str
    patch_content_digest: str
    sandbox_path: Path
    required_commands: tuple[VerifierCommandPlan, ...]
    config_digest: str
    review_class: str = 'standard'  # 'standard', 'policy-changing', 'privileged'

@dataclass(frozen=True)
class PatchVerificationResult:
    outcome: PatchOutcome
    executed_commands: tuple[dict[str, Any], ...]
    passed_count: int
    summary: str
    rollback_applied: bool = False
```

### 6.4 State Invariants
1. **Zero Raw Lock Authority Invariant:** The lock manager must never persist, return, or log raw caller capability tokens. Persistence is strictly verifier-only (`VerifierRecord`).
2. **Monotonic Generation Invariant:** Every lock lease acquisition increments generation; tokens from expired or prior generations fail closed.
3. **Truthful Storage Invariant:** Persistent stores must never return empty/default dicts on corruption or I/O failure. Corrupt bytes must be retained and digested.
4. **Verified Command Invariant:** Patch verification succeeds if and only if >= 1 bound verification command executed and exited with code 0. Zero executed commands yields `unavailable` or `failed`.
5. **Clean Base & Atomic Rollback Invariant:** Patch sandboxing refuses dirty checkouts. If any stage of application or promotion fails, the working directory is restored to its exact pre-patch commit and state.

---

## 7. Contract Test Inventory (T-58.01 to T-58.26)

| Test ID | Test File | Test Function | Target Contract & Non-Permissive Assertion |
|---|---|---|---|
| **T-58.01** | `tests/test_phase58_lock_capabilities.py` | `test_caller_retains_only_raw_capability` | Asserts raw capability token is generated/retained by caller and never appears in lock record, repr, or return value. |
| **T-58.02** | `tests/test_phase58_lock_capabilities.py` | `test_cli_uses_protected_input_not_argv_or_environment` | Verifies lock CLI commands reject capabilities in argv/env and accept only protected stdin/descriptor. |
| **T-58.03** | `tests/test_phase58_lock_capabilities.py` | `test_mcp_sensitive_value_is_never_rendered_or_persisted` | Verifies MCP lock tools mark capability as sensitive, redact in logs, and omit from tool results. |
| **T-58.04** | `tests/test_phase58_lock_capabilities.py` | `test_simultaneous_acquire_has_one_generation_owner` | Runs concurrent acquisition races; asserts exactly one winner acquires generation N with valid verifier. |
| **T-58.05** | `tests/test_phase58_lock_capabilities.py` | `test_wrong_guessed_stale_capability_cannot_renew_or_release` | Asserts wrong token, low-entropy token, or token from prior generation fails renewal/release fail-closed. |
| **T-58.06** | `tests/test_phase58_lock_capabilities.py` | `test_link_swap_expiry_and_crash_recovery_fail_closed` | Injects symlink/junction swaps and crash simulations; asserts lock manager recovers or fails closed without corruption. |
| **T-58.07** | `tests/test_phase58_locks.py` | `test_lock_acquisition_requires_caller_capability` | **R-009 Governance Test:** Asserts lock acquisition fails closed without verified caller capability. |
| **T-58.08** | `tests/test_phase58_map_transactions.py` | `test_invariant_preference_and_merkle_maps_preserve_concurrent_updates` | Performs parallel CAS updates across all 3 stores; asserts zero lost updates via monotonic versioning. |
| **T-58.09** | `tests/test_phase58_map_transactions.py` | `test_map_absent_corrupt_invalid_io_are_distinct` | Injects missing file, garbage bytes, invalid schema, and disk fault; asserts 4 distinct typed exceptions. |
| **T-58.10** | `tests/test_phase58_map_transactions.py` | `test_cas_conflict_retries_and_fails_closed` | Injects CAS version collision; verifies bounded retry and fail-closed `CASConflictError` on exhaustion. |
| **T-58.11** | `tests/test_phase58_checkpoint_journals.py` | `test_checkpoint_same_name_policy_and_replace_are_atomic` | Writes identical checkpoint names; verifies atomic replacement via `AtomicFile` without partial writes. |
| **T-58.12** | `tests/test_phase58_checkpoint_journals.py` | `test_corrupt_journal_bytes_are_retained_and_listed` | Injects corrupted JSON into checkpoint dir; asserts `list_checkpoints` returns corrupt entry with SHA-256 digest evidence. |
| **T-58.13** | `tests/test_phase58_persistence.py` | `test_persistence_uses_atomic_file_with_schema_version` | **R-010 Governance Test:** Asserts persistence operations use `AtomicFile` and include schema version `1.0.0`. |
| **T-58.14** | `tests/test_phase58_patch_verification.py` | `test_dirty_or_changed_base_refuses_before_sandbox` | Dirty working tree before patch sandbox; asserts `PatchSandboxManager` raises `DirtyWorkspaceError` fail-closed. |
| **T-58.15** | `tests/test_phase58_patch_verification.py` | `test_patch_sandbox_result_and_command_policy_drift_refuses` | Mutates base commit or command plan after contract construction; asserts execution refused fail-closed. |
| **T-58.16** | `tests/test_phase58_patch_verification.py` | `test_policy_changing_patch_cannot_receive_ordinary_verified_success` | Injects security-sensitive patch (modifying permissions/auth); asserts ordinary verifier refuses promotion. |
| **T-58.17** | `tests/test_phase58_patch_verification.py` | `test_zero_selected_or_executed_commands_never_verify` | Simulates project with 0 test runners; asserts verifier returns `outcome='unavailable'` (zero commands never verify). |
| **T-58.18** | `tests/test_phase58_patch_verification.py` | `test_unavailable_failed_verifier_leaves_checkout_unchanged` | Simulates test runner failure; asserts working tree retains original pre-patch state and hash. |
| **T-58.19** | `tests/test_phase58_patch_verification.py` | `test_rollback_and_cleanup_are_contained_and_manager_owned` | Injects promotion fault; asserts manager automatically cleans temp worktrees and restores working copy. |
| **T-58.20** | `tests/test_phase58_patch.py` | `test_patch_sandbox_enforces_physical_containment_and_rollback` | **R-016 Governance Test:** Asserts physical containment under `PhysicalRoot` and atomic rollback on failure. |
| **T-58.21** | `tests/test_phase58_output_migration.py` | `test_every_eligible_manifest_boundary_rejects_malformed_output` | **R-011 Governance Test:** Probes all 146 public operations with malformed payloads; asserts strict adapter validation. |
| **T-58.22** | `tests/test_phase58_output_migration.py` | `test_service_and_stdio_protocol_responses_are_not_tool_results` | Verifies MCP service methods (`initialize`, `tools/list`) emit unwrapped JSON-RPC protocol frames. |
| **T-58.23** | `tests/test_phase58_output_migration.py` | `test_admin_boundaries_emit_unwrapped_exit_codes` | Asserts admin commands emit native integer exit codes conforming to `ClickExitCode` contract. |
| **T-58.24** | `tests/test_phase58_output_migration.py` | `test_daemon_mesh_routes_conform_to_operation_adapters` | Asserts mesh daemon RPC responses conform to declared service and admin contracts. |
| **T-58.25** | `tests/test_phase58_output_migration.py` | `test_remediation_phase58_manifest_integrity` | Verifies `governance/remediation-phase-58.toml` registers all 26 contract tests and closes R-009, R-010, R-016. |
| **T-58.26** | `tests/test_phase58_output_migration.py` | `test_no_undocumented_persistence_or_lock_seams` | AST scan asserting no direct uncontained `write_text` or raw lock implementations remain. |

---

## 8. File, Dependency, and Documentation Governance

### 8.1 File Write Inventory

#### New Files
1. `src/rush/mcp_mesh/capabilities.py`: `LockCapabilityInput`, `LockLeaseRecord`, protected channel adapters.
2. `src/rush/memory/transactions.py`: `CASMapTransaction`, `VersionedSnapshot`, distinct store exceptions.
3. `src/rush/patch/contracts.py`: `PatchContract`, `VerifierCommandPlan`, `PatchVerificationResult`.
4. `tests/test_phase58_lock_capabilities.py`: Contract tests T-58.01 through T-58.06.
5. `tests/test_phase58_locks.py`: R-009 governance bridge test (T-58.07).
6. `tests/test_phase58_map_transactions.py`: Contract tests T-58.08, T-58.09, T-58.10.
7. `tests/test_phase58_checkpoint_journals.py`: Contract tests T-58.11, T-58.12.
8. `tests/test_phase58_persistence.py`: R-010 governance bridge test (T-58.13).
9. `tests/test_phase58_patch_verification.py`: Contract tests T-58.14 through T-58.19.
10. `tests/test_phase58_patch.py`: R-016 governance bridge test (T-58.20).
11. `tests/test_phase58_output_migration.py`: Contract tests T-58.21 through T-58.26.
12. `governance/remediation-phase-58.toml`: Phase 58 completion manifest.
13. `docs/developer/phase-58-implementation-evidence.md`: Evidence and execution logs.

#### Modified Files
1. `src/rush/mcp_mesh/lock_manager.py`: Centralize in verifier-only records, generation counters, physical containment.
2. `src/rush/mcp_mesh/daemon.py`: Adapt to protected capability input channels and verifier checks.
3. `src/rush/memory/checkpoint_journal.py`: AtomicFile writes, schema 1.0.0, corrupt record retention.
4. `src/rush/memory/preference_store.py`: Migrate to `CASMapTransaction` with versioning.
5. `src/rush/memory/invariant_graph.py`: Migrate to `CASMapTransaction` with versioning.
6. `src/rush/memory/merkle_invalidator.py`: Migrate to `CASMapTransaction` with versioning.
7. `src/rush/core/git_sandbox.py`: Enforce `PhysicalRoot` containment and clean base verification.
8. `src/rush/patch/sandbox.py`: Enforce `PhysicalRoot` containment, dirty check, and managed cleanup.
9. `src/rush/patch/verifier.py`: Require >= 1 executed passing command; reject zero-command verification.
10. `src/rush/patch/promoter.py`: Enforce clean state pre-check and atomic rollback on failure.
11. `src/rush/patch/applier.py`: Physical containment and syntax validation.
12. `src/rush/tools/fix.py`: Connect to `PatchContract`, verifier outcomes, and atomic rollback.
13. `src/rush/tools/continuity.py`: Align session checkpoint handling with atomic journal.
14. `src/rush/cli.py`: Wire lock, fix, and memory CLI commands through adapters and protected inputs.
15. `src/rush/mcp.py`: Wire lock, fix, and memory MCP tools through adapters and sensitive inputs.
16. `src/rush/contracts/operations.py`: Runtime adapter enforcement across 100% of operation boundaries.
17. `governance/remediation-contracts.toml`: Mark R-009, R-010, R-011, R-016 completed.

---

### 8.2 Comprehensive `/docs` Synchronization Inventory (46 Files across 4 Groups)

#### Group 1: Core Specifications & Public Contracts (16 files)
1. `docs/ARCHITECTURE.md`: Mesh lock manager, CAS map persistence, atomic journals, fail-closed patch verification, and rollback engine.
2. `docs/SECURITY.md`: Control 8 (Capability Lock Security & Verifier Records), atomic persistence, patch sandboxing, and containment.
3. `docs/SAFETY.md`: Single lock ownership, atomic rollback on patch failure, zero-command verification prohibition.
4. `docs/PRIVACY.md`: Caller capability custody, redaction of sensitive lock inputs, sanitized memory persistence.
5. `docs/API_REFERENCE.md`: Public APIs for `rush.mcp_mesh`, `rush.memory`, `rush.patch`, and `rush.core.git_sandbox`.
6. `docs/CLI_REFERENCE.md`: Lock CLI commands (`rush lock`), memory commands, and patch commands (`rush fix`).
7. `docs/MCP.md`: FastMCP mesh locks, session checkpoints, and patch verification tools.
8. `docs/MCP_REFERENCE.md`: Tool definitions for `lock_acquire`, `lock_release`, `checkpoint_save`, `checkpoint_restore`, `patch_verify`.
9. `docs/CONFIGURATION.md`: Lock timeouts, session storage paths, patch sandbox configurations.
10. `docs/CONFIG_SCHEMA.md`: Schema for `[mesh]`, `[memory]`, and `[patch]` sections in `rush.toml`.
11. `docs/GLOSSARY.md`: Glossary terms for `Caller Capability`, `VerifierRecord`, `CAS Transaction`, `Checkpoint Journal`, `PatchContract`, `Atomic Rollback`.
12. `docs/TOOL_CATALOG.md`: Catalog entries for `tool.fix`, `tool.continuity`, `admin.lock_*`, `service.mesh_*`.
13. `docs/JSON_SCHEMA.md`: JSON schemas for LockLeaseRecord, CheckpointRecord, PatchContract, and CAS Transaction records.
14. `docs/SEMANTIC_DRIFT.md`: Reconciliation of lock capability leakage, lost updates in maps, corrupt checkpoint erasure, uncontained worktrees, and zero-command patch verification.
15. `docs/SCOPE.md`: Physical containment of worktrees, session journals, and lock files under `rush.io.PhysicalRoot`.
16. `docs/ENVIRONMENT_VARIABLES.md`: Lock directory overrides, session storage directory, worktree location overrides.

#### Group 2: Developer, Safety & Maintainer Guides (16 files)
17. `docs/developer/architecture.md`: Section on mesh locks, memory CAS transactions, and patch rollback architecture.
18. `docs/developer/source-tree.md`: Add `src/rush/mcp_mesh/capabilities.py`, `src/rush/memory/transactions.py`, `src/rush/patch/contracts.py`.
19. `docs/developer/testing-guide.md`: Section on Phase 58 contract test suites (`tests/test_phase58_*.py`).
20. `docs/developer/debugging-guide.md`: Troubleshooting lock contention, CAS conflicts, corrupt session recovery, and patch verification failures.
21. `docs/developer/tool-development.md`: Writing tools that utilize capability locks, transactional memory, and safe patch generation.
22. `docs/developer/backlog.md`: Milestone table update marking Phase 58 Complete.
23. `docs/developer/issues.md`: Resolution of ISS-058-01 (Lock Capability Leakage & TOCTOU), ISS-058-02 (Memory CAS Lost Updates), and ISS-058-03 (Uncontained Patch & Zero-Command Verification).
24. `docs/developer/phase-58-implementation-evidence.md`: Baseline and contract test evidence.
25. `docs/safety/security-model.md`: Threat model for multi-agent lock contention, capability forgery, and malicious patch promotion.
26. `docs/safety/permissions.md`: Lock capability permission model, filesystem write containment, and git worktree isolation.
27. `docs/safety/privacy-and-data-handling.md`: Sanitized checkpoint persistence, prompt scrub in patches, and secret redaction.
28. `docs/safety/safety-overview.md`: Summary of atomic rollback, verifier-only locks, and truthful corruption retention.
29. `docs/maintainers/release-playbook.md`: Pre-release verification gates for Phase 58.
30. `docs/maintainers/versioning-and-compatibility.md`: Checkpoint journal schema versioning (v1.0.0) and backwards compatibility.
31. `docs/maintainers/incident-and-security.md`: Lock deadlocks, stolen capabilities, corrupt memory triage, and failed patch recovery.
32. `docs/maintainers/adr/010-tdd-guard-and-continuous-sensors.md`: Integration with patch verifier and CAS memory.

#### Group 3: Reference, User Guide & Agentic Integration (9 files)
33. `docs/agentic-rush/plugins-and-agent-skills.md`: Agent skills utilizing mesh locks and safe patch execution.
34. `docs/reference/cli-reference.md`: Reference for `rush lock`, `rush fix`, and session checkpoint commands.
35. `docs/reference/configuration-reference.md`: Configuration reference for locks, sessions, and sandboxes.
36. `docs/reference/result-reference.md`: Reference for `ToolResultV1` output shapes from patch verification and memory tools.
37. `docs/reference/environment-variables.md`: Reference for environment variables in locks and patch execution.
38. `docs/getting-started/glossary.md`: Beginner terms for Locks, Checkpoints, and Patches.
39. `docs/user-guide/security-and-supply-chain.md`: User guide for safe AI patch remediation, sandboxing, and containment.
40. `docs/user-guide/advanced-checks.md`: Advanced options for multi-agent locks and worktree sandboxing.
41. `docs/vibecoding/instant-fix-and-auto-remediation.md`: Comprehensive guide to safe AI code patching with atomic rollback.

#### Group 4: Governance, Evidence & Release Tracking (5 files)
42. `governance/remediation-phase-58.toml`: Phase 58 completion manifest.
43. `governance/remediation-contracts.toml`: Mark R-009, R-010, R-011, R-016 completed.
44. `README.md`: Update test badge (1,134 to 1,160 passed).
45. `CHANGELOG.md`: Log Phase 58 additions under `[0.3.0]`.
46. `docs/adr/0018-closed-loop-ai-agent-patch-remediation-and-session-memory.md`: Align ADR with fail-closed patch verification and CAS memory.

---

### 8.3 Dependency Constraints
- Zero third-party dependencies introduced.
- Strict reliance on Python 3.12 standard library (`hashlib`, `secrets`, `json`, `pathlib`, `dataclasses`, `time`, `shutil`, `subprocess`).

---

## 9. Ordered Workstreams and Atomic Task Cards

### P58.0 — Admission Gate & Baseline Evidence

#### P58.0.1 — EVIDENCE: Map Lock, State, Patch, and Output Seams
- **Task ID:** P58.0.1
- **Binary Outcome:** Clean baseline evidence recorded in `docs/developer/phase-58-implementation-evidence.md`; full test suite passes (1,134 passed); all seams mapped.
- **Prerequisites:** Admission gate §4 passed.
- **Allowed Writes:** `docs/developer/phase-58-implementation-evidence.md`.
- **Actions:**
  1. Run `.venv/Scripts/python.exe -m pytest tests/ -q` and record 1,134 passing tests.
  2. Inspect `MeshLockManager`, `daemon.py`, memory stores, checkpoint journal, patch sandbox, verifier, promoter, and output adapters.
  3. Map call paths and divergence points to tasks P58.1 through P58.7.

---

### P58.1 — Caller Capability Custody

#### P58.1.1 — RED: Define Caller-Retained Protected Capability Input Contract Tests
- **Task ID:** P58.1.1
- **Binary Outcome:** Create `tests/test_phase58_lock_capabilities.py` containing contract tests T-58.01, T-58.02, T-58.03; tests fail (RED).
- **Prerequisites:** P58.0.1.
- **Allowed Writes:** `tests/test_phase58_lock_capabilities.py`.
- **Actions:**
  1. Author T-58.01 (`test_caller_retains_only_raw_capability`).
  2. Author T-58.02 (`test_cli_uses_protected_input_not_argv_or_environment`).
  3. Author T-58.03 (`test_mcp_sensitive_value_is_never_rendered_or_persisted`).
  4. Run `pytest tests/test_phase58_lock_capabilities.py -q` and confirm failures.

#### P58.1.2 — GREEN: Implement Protected Capability Input & Redaction
- **Task ID:** P58.1.2
- **Binary Outcome:** Implement `src/rush/mcp_mesh/capabilities.py`; tests in `tests/test_phase58_lock_capabilities.py` pass (GREEN).
- **Prerequisites:** P58.1.1 RED.
- **Allowed Writes:** `src/rush/mcp_mesh/capabilities.py`, `src/rush/mcp_mesh/__init__.py`, `src/rush/cli.py`, `src/rush/mcp.py`.
- **Actions:**
  1. Define `LockCapabilityInput` and protected input adapters (stdin, descriptor, MCP sensitive).
  2. Ensure raw capabilities are never returned, rendered in CLI stdout, or persisted to ordinary logs.
  3. Run `pytest tests/test_phase58_lock_capabilities.py -v` and confirm GREEN.

---

### P58.2 — Atomic Verifier-Only Locks

#### P58.2.1 — RED: Define Atomic Verifier-Only Generation Semantics Contract Tests
- **Task ID:** P58.2.1
- **Binary Outcome:** Add contract tests T-58.04, T-58.05, T-58.06 to `tests/test_phase58_lock_capabilities.py` and T-58.07 to `tests/test_phase58_locks.py`; tests fail (RED).
- **Prerequisites:** P58.1.2.
- **Allowed Writes:** `tests/test_phase58_lock_capabilities.py`, `tests/test_phase58_locks.py`.
- **Actions:**
  1. Author T-58.04 (`test_simultaneous_acquire_has_one_generation_owner`).
  2. Author T-58.05 (`test_wrong_guessed_stale_capability_cannot_renew_or_release`).
  3. Author T-58.06 (`test_link_swap_expiry_and_crash_recovery_fail_closed`).
  4. Author T-58.07 (`test_lock_acquisition_requires_caller_capability` - R-009).
  5. Run `pytest tests/test_phase58_lock_capabilities.py tests/test_phase58_locks.py -q` and confirm failures.

#### P58.2.2 — GREEN: Implement MeshLockManager with VerifierRecord and AtomicFile
- **Task ID:** P58.2.2
- **Binary Outcome:** Refactor `src/rush/mcp_mesh/lock_manager.py` and `src/rush/mcp_mesh/daemon.py`; tests pass (GREEN).
- **Prerequisites:** P58.2.1 RED.
- **Allowed Writes:** `src/rush/mcp_mesh/lock_manager.py`, `src/rush/mcp_mesh/daemon.py`, `src/rush/mcp_mesh/capabilities.py`.
- **Actions:**
  1. Centralize lock management in `MeshLockManager`.
  2. Persist `LockLeaseRecord` via `rush.io.AtomicFile` and `rush.io.PhysicalRoot`.
  3. Generate and verify capabilities via `rush.io.VerifierRecord` (constant-time `hmac.compare_digest`).
  4. Enforce monotonic generation counters and fail-closed crash recovery.
  5. Run `pytest tests/test_phase58_lock_capabilities.py tests/test_phase58_locks.py -v` and confirm GREEN.

---

### P58.3 — CAS Map Transactions

#### P58.3.1 — RED: Define Concurrent Map Transactions & Error Contract Tests
- **Task ID:** P58.3.1
- **Binary Outcome:** Create `tests/test_phase58_map_transactions.py` containing contract tests T-58.08, T-58.09, T-58.10; tests fail (RED).
- **Prerequisites:** P58.0.1.
- **Allowed Writes:** `tests/test_phase58_map_transactions.py`.
- **Actions:**
  1. Author T-58.08 (`test_invariant_preference_and_merkle_maps_preserve_concurrent_updates`).
  2. Author T-58.09 (`test_map_absent_corrupt_invalid_io_are_distinct`).
  3. Author T-58.10 (`test_cas_conflict_retries_and_fails_closed`).
  4. Run `pytest tests/test_phase58_map_transactions.py -q` and confirm failures.

#### P58.3.2 — GREEN: Implement CASMapTransaction and Migrate Persistent Stores
- **Task ID:** P58.3.2
- **Binary Outcome:** Implement `src/rush/memory/transactions.py`, refactor `PreferenceStore`, `InvariantGraph`, and `MerkleInvalidator`; tests pass (GREEN).
- **Prerequisites:** P58.3.1 RED.
- **Allowed Writes:** `src/rush/memory/transactions.py`, `src/rush/memory/preference_store.py`, `src/rush/memory/invariant_graph.py`, `src/rush/memory/merkle_invalidator.py`.
- **Actions:**
  1. Implement `CASMapTransaction` with optimistic concurrency, version incrementing, and `rush.io.AtomicFile`.
  2. Enforce typed exceptions (`StoreNotFoundError`, `StoreCorruptionError`, `StoreValidationError`, `StoreIOError`, `CASConflictError`).
  3. Migrate `PreferenceStore`, `InvariantGraph`, and `MerkleInvalidator` to `CASMapTransaction`.
  4. Run `pytest tests/test_phase58_map_transactions.py -v` and confirm GREEN.

---

### P58.4 — Atomic Checkpoint Journals & Corrupt Evidence

#### P58.4.1 — RED: Define Atomic Journal & Corrupt Evidence Contract Tests
- **Task ID:** P58.4.1
- **Binary Outcome:** Create `tests/test_phase58_checkpoint_journals.py` and `tests/test_phase58_persistence.py` containing contract tests T-58.11, T-58.12, T-58.13; tests fail (RED).
- **Prerequisites:** P58.0.1.
- **Allowed Writes:** `tests/test_phase58_checkpoint_journals.py`, `tests/test_phase58_persistence.py`.
- **Actions:**
  1. Author T-58.11 (`test_checkpoint_same_name_policy_and_replace_are_atomic`).
  2. Author T-58.12 (`test_corrupt_journal_bytes_are_retained_and_listed`).
  3. Author T-58.13 (`test_persistence_uses_atomic_file_with_schema_version` - R-010).
  4. Run `pytest tests/test_phase58_checkpoint_journals.py tests/test_phase58_persistence.py -q` and confirm failures.

#### P58.4.2 — GREEN: Implement Atomic CheckpointJournal with Retained Evidence
- **Task ID:** P58.4.2
- **Binary Outcome:** Refactor `src/rush/memory/checkpoint_journal.py` and `src/rush/tools/continuity.py`; tests pass (GREEN).
- **Prerequisites:** P58.4.1 RED.
- **Allowed Writes:** `src/rush/memory/checkpoint_journal.py`, `src/rush/tools/continuity.py`.
- **Actions:**
  1. Refactor `save_checkpoint` to use `rush.io.AtomicFile` with schema version `1.0.0`.
  2. Implement corrupt checkpoint retention and listing: calculate SHA-256 digest of unparseable files and emit structured corrupt records in `list_checkpoints()`.
  3. Run `pytest tests/test_phase58_checkpoint_journals.py tests/test_phase58_persistence.py -v` and confirm GREEN.

---

### P58.5 — Patch Contract & Identity Binding

#### P58.5.1 — RED: Define Clean-State & Command-Policy Binding Contract Tests
- **Task ID:** P58.5.1
- **Binary Outcome:** Create `tests/test_phase58_patch_verification.py` containing contract tests T-58.14, T-58.15, T-58.16; tests fail (RED).
- **Prerequisites:** P58.0.1.
- **Allowed Writes:** `tests/test_phase58_patch_verification.py`.
- **Actions:**
  1. Author T-58.14 (`test_dirty_or_changed_base_refuses_before_sandbox`).
  2. Author T-58.15 (`test_patch_sandbox_result_and_command_policy_drift_refuses`).
  3. Author T-58.16 (`test_policy_changing_patch_cannot_receive_ordinary_verified_success`).
  4. Run `pytest tests/test_phase58_patch_verification.py -k 'dirty or drift or policy' -q` and confirm failures.

#### P58.5.2 — GREEN: Implement PatchContract & Clean State Enforcement
- **Task ID:** P58.5.2
- **Binary Outcome:** Implement `src/rush/patch/contracts.py` and update patch managers; tests pass (GREEN).
- **Prerequisites:** P58.5.1 RED.
- **Allowed Writes:** `src/rush/patch/contracts.py`, `src/rush/patch/__init__.py`, `src/rush/patch/sandbox.py`, `src/rush/core/git_sandbox.py`.
- **Actions:**
  1. Define `PatchContract`, `VerifierCommandPlan`, and `PatchVerificationResult` in `contracts.py`.
  2. Implement pre-sandbox dirty check: if repo is dirty, raise `DirtyWorkspaceError` fail-closed.
  3. Enforce cryptographic binding of base commit, patch digest, command plan, and policy class.
  4. Run `pytest tests/test_phase58_patch_verification.py -k 'dirty or drift or policy' -v` and confirm GREEN.

---

### P58.6 — Fail-Closed Verification & Atomic Rollback

#### P58.6.1 — RED: Define Command Execution & Atomic Rollback Contract Tests
- **Task ID:** P58.6.1
- **Binary Outcome:** Add contract tests T-58.17, T-58.18, T-58.19 to `tests/test_phase58_patch_verification.py` and T-58.20 to `tests/test_phase58_patch.py`; tests fail (RED).
- **Prerequisites:** P58.5.2.
- **Allowed Writes:** `tests/test_phase58_patch_verification.py`, `tests/test_phase58_patch.py`.
- **Actions:**
  1. Author T-58.17 (`test_zero_selected_or_executed_commands_never_verify`).
  2. Author T-58.18 (`test_unavailable_failed_verifier_leaves_checkout_unchanged`).
  3. Author T-58.19 (`test_rollback_and_cleanup_are_contained_and_manager_owned`).
  4. Author T-58.20 (`test_patch_sandbox_enforces_physical_containment_and_rollback` - R-016).
  5. Run `pytest tests/test_phase58_patch_verification.py tests/test_phase58_patch.py -q` and confirm failures.

#### P58.6.2 — GREEN: Implement Command-Gated Verifier & Atomic Rollback
- **Task ID:** P58.6.2
- **Binary Outcome:** Refactor `src/rush/patch/verifier.py`, `src/rush/patch/promoter.py`, and `src/rush/tools/fix.py`; tests pass (GREEN).
- **Prerequisites:** P58.6.1 RED.
- **Allowed Writes:** `src/rush/patch/verifier.py`, `src/rush/patch/promoter.py`, `src/rush/tools/fix.py`, `src/rush/core/git_sandbox.py`.
- **Actions:**
  1. Refactor `PatchVerifier.verify_patch()`: require at least one executed test command; if 0 commands executed, return `outcome='unavailable'` and `False` (zero commands never verify).
  2. In `PatchPromoter` and `fix.py`: implement automatic atomic rollback on failure; if promotion or tests fail, roll back working tree to pre-patch state and clean up worktrees under `PhysicalRoot`.
  3. Run `pytest tests/test_phase58_patch_verification.py tests/test_phase58_patch.py -v` and confirm GREEN.

---

### P58.7 — Runtime Output Adapter Migration

#### P58.7.1 — RED: Define Manifest-Wide Output Contract Tests
- **Task ID:** P58.7.1
- **Binary Outcome:** Create `tests/test_phase58_output_migration.py` containing contract tests T-58.21 through T-58.26; tests fail (RED).
- **Prerequisites:** P58.2.2 through P58.6.2.
- **Allowed Writes:** `tests/test_phase58_output_migration.py`.
- **Actions:**
  1. Author T-58.21 (`test_every_eligible_manifest_boundary_rejects_malformed_output` - R-011).
  2. Author T-58.22 (`test_service_and_stdio_protocol_responses_are_not_tool_results`).
  3. Author T-58.23 (`test_admin_boundaries_emit_unwrapped_exit_codes`).
  4. Author T-58.24 (`test_daemon_mesh_routes_conform_to_operation_adapters`).
  5. Author T-58.25 (`test_remediation_phase58_manifest_integrity`).
  6. Author T-58.26 (`test_no_undocumented_persistence_or_lock_seams`).
  7. Run `pytest tests/test_phase58_output_migration.py -q` and confirm failures.

#### P58.7.2 — GREEN: Enforce Operation Adapters at All Runtime Boundaries
- **Task ID:** P58.7.2
- **Binary Outcome:** Update runtime boundaries across CLI, MCP, mesh, and memory; all tests in `tests/test_phase58_output_migration.py` pass (GREEN).
- **Prerequisites:** P58.7.1 RED.
- **Allowed Writes:** `src/rush/contracts/operations.py`, `src/rush/cli.py`, `src/rush/mcp.py`, `src/rush/mcp_mesh/lock_manager.py`, `src/rush/tools/continuity.py`, `src/rush/tools/fix.py`.
- **Actions:**
  1. Enforce `ToolOperationAdapter`, `AdminOperationAdapter`, and `ServiceOperationAdapter` at every public operation boundary.
  2. Preserve unwrapped JSON-RPC frames for service protocol methods (`mcp.initialize`, `mcp.tools_list`).
  3. Run `pytest tests/test_phase58_output_migration.py -v` and confirm GREEN.

---

### P58.8 — Comprehensive Documentation & Governance Sync

#### P58.8.1 — VERIFY/DOCS: Synchronize All 46 Documentation and Governance Files
- **Task ID:** P58.8.1
- **Binary Outcome:** All 46 documentation and governance files listed in §8.2 are updated and synchronized with zero drift.
- **Prerequisites:** P58.1.2 through P58.7.2 GREEN.
- **Allowed Writes:** All 46 files listed in §8.2.
- **Actions:**
  1. Create `governance/remediation-phase-58.toml` documenting phase completion, 26 contract tests, and closure of R-009, R-010, R-011, R-016.
  2. Update `governance/remediation-contracts.toml` marking R-009, R-010, R-011, R-016 completed.
  3. Update `docs/developer/phase-58-implementation-evidence.md` with final gate runs.
  4. Update `README.md` test badge (1,134 to 1,160 passed); update `CHANGELOG.md` under `[0.3.0]`.
  5. Update all 42 technical docs across `/docs` with capability locks, CAS memory transactions, atomic journals, and patch rollback mechanics.
  6. Verify zero whitespace defects with `git diff --check`.

---

## 10. Final Verification and Delivery Gate

Execute the following commands in sequence to verify Phase 58 delivery:

```powershell
$env:VIRTUAL_ENV=$null
$env:PYTHONPATH=$null

# 1. Run all 26 focused Phase 58 contract tests
.venv/Scripts/python.exe -m pytest tests/test_phase58_lock_capabilities.py tests/test_phase58_locks.py tests/test_phase58_map_transactions.py tests/test_phase58_checkpoint_journals.py tests/test_phase58_persistence.py tests/test_phase58_patch_verification.py tests/test_phase58_patch.py tests/test_phase58_output_migration.py -v

# 2. Run regression suites
.venv/Scripts/python.exe -m pytest tests/test_mcp.py tests/test_cache.py tests/test_review.py tests/test_phase55_*.py tests/test_phase56_*.py tests/test_phase57_*.py -q

# 3. Run complete test suite (expecting 1,160 passed tests: 1,134 baseline + 26 contract tests)
.venv/Scripts/python.exe -m pytest tests/ -q

# 4. Run Ruff lint check across entire codebase
.venv/Scripts/ruff.exe check src tests scripts

# 5. Run Ruff format check across entire codebase
.venv/Scripts/ruff.exe format --check src tests scripts

# 6. Verify Git diff whitespace and status hygiene
git diff --check
git diff --name-only
git status --short --branch
```

---

## 11. Exit Checklist and Successor Evidence

- [ ] Ordinary RED evidence precedes every GREEN task; zero skip, xfail, or permissive assertions.
- [ ] Caller-retained capabilities never appear in ordinary channels, logs, or persisted files.
- [ ] Lock generation is atomic, verifier-only (`VerifierRecord`), and stale-safe via monotonic generation counter.
- [ ] `MeshLockManager` enforces physical containment under `rush.io.PhysicalRoot`.
- [ ] Persistent stores (`PreferenceStore`, `InvariantGraph`, `MerkleInvalidator`) use CAS transactions with versioning.
- [ ] Absent, corrupt, invalid, and I/O store states are distinct typed errors (never silently treated as empty).
- [ ] `CheckpointJournal` uses `AtomicFile` with schema version `1.0.0` and retains corrupt records with SHA-256 evidence.
- [ ] `PatchContract` cryptographically binds base commit, patch digest, sandbox path, command plan, and policy class.
- [ ] Patch sandboxing refuses dirty target checkouts fail-closed (`DirtyWorkspaceError`).
- [ ] `PatchVerifier` requires >= 1 executed passing command; zero executed commands returns `unavailable` or `failed`.
- [ ] Patch promotion failure triggers automatic atomic rollback restoring pre-patch commit and state.
- [ ] All 146 public operations enforce declared adapters at runtime; service protocol frames remain unwrapped.
- [ ] Zero third-party dependencies introduced; 100% pure Python 3.12 standard library.
- [ ] All 26 contract tests in `tests/test_phase58_*.py` pass.
- [ ] Full pytest suite passes with 1,160 tests (1,134 baseline + 26 Phase 58 contract tests).
- [ ] All 46 documentation and governance files updated and synchronized across `/docs` and repo root.
- [ ] `governance/remediation-phase-58.toml` created with complete test and requirement records.
- [ ] Requirements R-009, R-010, R-011, and R-016 reconciled in `governance/remediation-contracts.toml` as completed.
- [ ] Successor phase (Phase 59 SLSA provenance, attestation, and engine conformance) unblocked with stable locking, storage, and patch interfaces.
