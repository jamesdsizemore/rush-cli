# Phase 55 implementation plan — AtomicFile, physical containment, and verifier records

## 1. Purpose and status

- **Operation:** Create the implementation plan for remediation Phase 4.
- **Planning status:** Implementation-ready after §4 admission passes.
- **Implementation status:** Not authorized.
- **Authority:** roadmap atomic-write/containment/verifier requirements supporting R-003, R-009, R-010, and R-016.
- **Predecessor:** accepted Phase 53 sanitized JSON-safe value contract.
- **Successors:** Phase 56 plugin ledger/snapshots; Phase 58 lock/maps/journals/patch artifacts.
- **Boundary:** Establish one primitive and platform contracts; migrate no existing writer.
- **Protected:** all current persistence/lock/plugin/patch/cache/output writers, sanitizer, roadmap, `pyproject.toml`, `uv.lock`.
- **Amendment rule:** Any dependency, platform relaxation, writer migration, or additional path requires amendment.
- **Lifecycle boundary:** No commit, push, merge, tag, publish, release, hooks, or history rewrite.

## 2. Authority, evidence, and decisions

Authority order: user → `AGENTS.md` → roadmap → Phase 53 sanitizer → current filesystem/writer evidence.

Current evidence: atomic/temp/replace/containment logic is duplicated or absent across writers; lock/plugin/persistence/patch phases need one primitive; supported platforms require symlink/junction/reparse/swap coverage.

Closed decisions: same-directory unique temp; owner-root relative paths; no-follow/reparse inspection; handle identity revalidation where supported; old-valid-or-new-valid destination; cleanup only manager-owned temp; raw authorization values never persisted; protected `unsupported` fails before state change. No dependencies.

Open decisions: None. If stdlib/platform APIs cannot meet the locked guarantee, the relevant GREEN task stops and the plan becomes Blocked.

## 3. Goals, outcomes, exclusions, and invariants

Outcomes: one `AtomicFile`; one `PhysicalRoot`; one non-recoverable `VerifierRecord`; complete link/junction/swap/fault matrix on Windows/POSIX.

Exclusions: existing-writer migration, plugin/lock/persistence/patch behavior, sanitizer changes.

Invariant: destination is old valid or new valid only; outside sentinel is unchanged; unsupported protected action writes nothing.

## 4. Admission and predecessor gate

Require accepted Phase 53 sanitizer/result contract. Inspect existing temp/replace, containment, permission, and verifier-like code using CodeGraph/Graft. Record supported Windows/POSIX primitives and current CI platforms. Stop on overlapping edits. P55.0.1 freezes capability evidence before tests.

## 5. Requirement-ownership ledger

| Requirement | Tasks | Closure |
|---|---|---|
| Sanitized-input/single-owner API | P55.1.1-P55.1.2 | API contract tests |
| Physical containment/platform capability | P55.2.1-P55.2.2 | link/junction/swap/outside matrix |
| Atomic replacement/fault cleanup | P55.3.1-P55.3.2 | injected fault matrix |
| Non-recoverable verifier record | P55.4.1-P55.4.2 | capability policy tests |
| Docs/platform handoff | P55.5.1 | named docs and evidence |

## 6. Shared contracts and handoff

- `PhysicalRoot.open_contained(relative_path, purpose)`: reject absolute, parent traversal, file/directory links and reparse substitution; return stable physical identity or `unsupported/error`.
- `AtomicFile.write_bytes(relative_path, SanitizedBytes)` and `write_json(relative_path, SanitizedJsonValue)`: same-directory temp, permissions/ownership, write/flush/fsync policy, atomic replace, bounded owned cleanup.
- `VerifierRecord.create(raw_ephemeral)`: persist version/salt/algorithm/work factor/verifier only; constant-time `verify(candidate)`; no raw getter.
- Status is exactly `completed|unsupported|error`; protected callers fail closed on the latter two.

## 7. Contract-test inventory

| Contract | RED | GREEN | Exact ordinary tests |
|---|---|---|---|
| API ownership/input | P55.1.1 | P55.1.2 | `test_atomic_file_accepts_only_sanitized_contracts`; `test_atomic_file_has_one_implementation_owner`; `test_raw_secret_wrapper_is_rejected` |
| Containment | P55.2.1 | P55.2.2 | `test_file_and_directory_links_cannot_escape_root`; `test_junction_reparse_and_parent_target_swaps_fail_closed`; `test_unsupported_capability_writes_nothing` |
| Atomic faults | P55.3.1 | P55.3.2 | `test_each_injected_fault_leaves_old_or_new_valid_destination`; `test_cleanup_removes_only_owned_temp_identity` |
| Verifier | P55.4.1 | P55.4.2 | `test_record_contains_no_raw_capability`; `test_wrong_reused_low_entropy_and_stale_values_fail`; `test_metadata_cannot_recover_capability` |

## 8. File, dependency, and documentation governance

New source/tests: `src/rush/io/__init__.py`, `src/rush/io/atomic_file.py`, `src/rush/io/physical_paths.py`, `src/rush/io/verifier_record.py`, `tests/test_phase55_atomic_file.py`, `tests/test_phase55_physical_containment.py`, `tests/test_phase55_verifier_record.py`.

Evidence/docs: foundation fields in `governance/remediation-contracts.toml`; `docs/ARCHITECTURE.md`, `docs/SECURITY.md`, `docs/SAFETY.md`, `docs/developer/architecture.md`, `docs/developer/source-tree.md`, `docs/maintainers/incident-and-security.md`, `docs/safety/security-model.md`.

All other writes prohibited. Dependency changes: None. Required existing dependencies/contracts: Python 3.12 stdlib filesystem, hashing, HMAC, and platform APIs plus the Phase 53 sanitized-value contract.

## 9. Ordered workstreams and atomic task cards

### P55.0 — Admission

#### P55.0.1 — EVIDENCE: record platform and primitive boundaries

- **Task ID and binary outcome:** P55.0.1; one record lists supported primitives, current duplicates, platform jobs, and each later contract owner.
- **Start goal:** Freeze scope/capability assumptions.
- **Prerequisites:** §4.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** Phase 55 foundation fields in `governance/remediation-contracts.toml`.
- **Allowed reads:** existing writer/lock/plugin/patch helpers, workflows, Phase 53 contract.
- **Prohibited:** source/tests/docs/dependencies/migrations.
- **Actions:** 1. Inspect implementations/callers/platform APIs. 2. Record exact symbols, supported guarantees, tests, and ownership. 3. Reconcile all §8 new APIs and reparse TOML.
- **Evidence:** capability/duplicate/platform table.
- **Stop:** required platform lacks known stdlib guarantee.
- **Verified outcome:** P55.1.1-P55.4.1 may start; a missing guarantee blocks only its dependent GREEN task.

### P55.1 — Public API

#### P55.1.1 — RED: define sanitized-input and single-owner API

- **Task ID and binary outcome:** P55.1.1; three tests fail because the API is absent.
- **Start goal:** Pin accepted types and unique implementation ownership.
- **Prerequisites:** P55.0.1.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase55_atomic_file.py`.
- **Allowed reads:** Phase 53 sanitizer types and current filesystem helpers.
- **Prohibited:** source/docs/writer migrations/skip/XFAIL.
- **Actions:** 1. Arrange sanitized byte/JSON wrappers, raw secret wrapper, and module ownership scan. 2. Add exactly three §7 API tests against planned `AtomicFile`. 3. Run focused file and record absent-API failures.
- **Evidence:** red output and fixtures.
- **Stop:** Phase 53 exposes no enforceable sanitized contract type.
- **Verified outcome:** P55.1.2 may create public API shells.

#### P55.1.2 — GREEN: create the single narrow writer API

- **Task ID and binary outcome:** P55.1.2; API tests pass without implementing containment/replacement behavior prematurely.
- **Start goal:** Satisfy P55.1.1 only.
- **Prerequisites:** recorded P55.1.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `src/rush/io/__init__.py`, create `src/rush/io/atomic_file.py`, modify `tests/test_phase55_atomic_file.py` only to retain/strengthen assertions.
- **Allowed reads:** P55.1.1 evidence and sanitizer types.
- **Prohibited:** existing writers, physical/verifier modules, docs.
- **Actions:** 1. Authorize only public types/signatures/status and injected collaborators. 2. Implement type enforcement and one exported owner; unimplemented protected operations return `unsupported` without writes. 3. Run focused and Phase 53 sanitizer tests.
- **Evidence:** green API tests.
- **Stop:** a raw/untyped value can reach serialization.
- **Verified outcome:** P55.2.1/P55.3.1 may target the API.

### P55.2 — Physical containment

#### P55.2.1 — RED: define link, reparse, swap, ownership, and unsupported behavior

- **Task ID and binary outcome:** P55.2.1; containment tests fail on absent PhysicalRoot.
- **Start goal:** Pin contained approved target or no write.
- **Prerequisites:** P55.0.1.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase55_physical_containment.py`.
- **Allowed reads:** platform helpers, workflow platforms, planned API.
- **Prohibited:** source/existing writers/docs/XFAIL.
- **Actions:** 1. Arrange temp owner root/outside sentinel, file+directory symlinks, Windows junction/reparse where supported, parent/target swaps, wrong permissions/owner, forced unsupported capability. 2. Add exactly three §7 containment tests with parameterized cases. 3. Run focused file on current platform and record absent-API failures; CI later supplies other platform.
- **Evidence:** case matrix and red output.
- **Stop:** fixture cannot distinguish unsupported from insecure fallback.
- **Verified outcome:** P55.2.2 may implement containment.

#### P55.2.2 — GREEN: implement PhysicalRoot fail-closed containment

- **Task ID and binary outcome:** P55.2.2; every trap preserves outside sentinel and returns contained identity or no write.
- **Start goal:** Satisfy P55.2.1 only.
- **Prerequisites:** recorded P55.2.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `src/rush/io/physical_paths.py`, modify `src/rush/io/__init__.py`, modify `tests/test_phase55_physical_containment.py` only to retain/strengthen assertions.
- **Allowed reads:** P55.2.1 evidence and stdlib platform APIs.
- **Prohibited:** dependencies/existing writers/atomic replace/docs.
- **Actions:** 1. Reinspect each trap and platform capability. 2. Implement normalized relative rejection, owner root, no-follow/reparse inspection, handle identity revalidation, permission/ownership policy, structured unsupported. 3. Run focused tests, then execute on Windows/POSIX CI jobs without weakening unsupported cases.
- **Evidence:** green platform matrices and unchanged outside digest.
- **Stop:** platform cannot prove physical identity; return unsupported and block protected caller.
- **Verified outcome:** P55.3.2/P56/P58 may consume PhysicalRoot.

### P55.3 — Atomic replacement

#### P55.3.1 — RED: define old-or-new behavior across every fault

- **Task ID and binary outcome:** P55.3.1; fault tests fail because replacement is absent/incomplete.
- **Start goal:** Pin temp-create, permissions, write, partial write, flush, fsync, replace, directory-sync, cleanup faults.
- **Prerequisites:** P55.1.2 and P55.2.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `tests/test_phase55_atomic_file.py`.
- **Allowed reads:** AtomicFile/PhysicalRoot APIs.
- **Prohibited:** production/existing writers/docs/XFAIL.
- **Actions:** 1. Arrange injected filesystem operations and destination old/new payloads. 2. Add exactly two §7 atomic tests parameterized over every named fault; assert cleanup identity and destination validity. 3. Run focused file and record behavior failures.
- **Evidence:** fault matrix and red output.
- **Stop:** injected boundary cannot prove which temp is owned.
- **Verified outcome:** P55.3.2 may implement replacement internals.

#### P55.3.2 — GREEN: implement same-directory atomic replacement

- **Task ID and binary outcome:** P55.3.2; every fault yields old/new valid destination and owned cleanup only.
- **Start goal:** Satisfy P55.3.1 only.
- **Prerequisites:** recorded P55.3.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/io/atomic_file.py`, `src/rush/io/physical_paths.py`, `tests/test_phase55_atomic_file.py`.
- **Allowed reads:** P55.3.1 evidence and public API.
- **Prohibited:** existing-writer migration/verifier/docs/dependencies.
- **Actions:** 1. Reinspect fault injection points. 2. Implement unique same-directory temp, policy application, write/flush/fsync, atomic replace, directory sync policy, identity-bound cleanup. 3. Run atomic+containment tests and Phase 53 sanitizer tests.
- **Evidence:** green fault matrix and outside/temp digests.
- **Stop:** any branch can leave partial destination or clean unowned path.
- **Verified outcome:** AtomicFile is ready for Phases 56/58.

### P55.4 — Verifier records

#### P55.4.1 — RED: define non-recoverable verifier policy

- **Task ID and binary outcome:** P55.4.1; three tests fail because verifier API is absent.
- **Start goal:** Pin one-way storage, entropy/reuse/staleness policy, constant-time verification.
- **Prerequisites:** P55.0.1.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase55_verifier_record.py`.
- **Allowed reads:** existing cryptography dependency usage and roadmap capability requirements.
- **Prohibited:** source/raw capability fixtures/docs/XFAIL.
- **Actions:** 1. Arrange generated ephemeral capabilities, wrong/reused/low-entropy/stale generations, disclosed metadata. 2. Add exactly three §7 verifier tests. 3. Run focused file and record absent-API failures.
- **Evidence:** test matrix and red output with no raw values.
- **Stop:** fixture persists/logs a raw capability.
- **Verified outcome:** P55.4.2 may create verifier module.

#### P55.4.2 — GREEN: implement versioned one-way verifier records

- **Task ID and binary outcome:** P55.4.2; verifier tests pass and records contain no authority.
- **Start goal:** Satisfy P55.4.1 only.
- **Prerequisites:** recorded P55.4.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None; use existing cryptographic primitives or stdlib.
- **Allowed writes:** create `src/rush/io/verifier_record.py`, modify `src/rush/io/__init__.py`, modify `tests/test_phase55_verifier_record.py` only to retain/strengthen assertions.
- **Allowed reads:** P55.4.1 evidence and current cryptography APIs.
- **Prohibited:** dependency/lockfile changes, raw getter/persistence, existing locks/plugins.
- **Actions:** 1. Authorize version/salt/algorithm/work factor/verifier and policy symbols. 2. Implement creation/constant-time verify/generation binding/entropy policy with no raw return. 3. Run focused tests and security-related existing tests.
- **Evidence:** green tests and serialized-key inspection.
- **Stop:** implementation needs a new dependency.
- **Verified outcome:** Phases 56/58 may persist verifier-only authority.

### P55.5 — Documentation and handoff

#### P55.5.1 — VERIFY/DOCS/HANDOFF: close the foundation

- **Task ID and binary outcome:** P55.5.1; named docs and platform handoff cite passing matrices.
- **Start goal:** Publish only proven API/platform guarantees.
- **Prerequisites:** P55.1.2-P55.4.2.
- **Documentation impact:** update all seven §8 docs with owner-root, no-follow/reparse, status, temp/replace/fsync, verifier, unsupported, cleanup.
- **Dependency impact:** None.
- **Allowed writes:** `docs/ARCHITECTURE.md`, `docs/SECURITY.md`, `docs/SAFETY.md`, `docs/developer/architecture.md`, `docs/developer/source-tree.md`, `docs/maintainers/incident-and-security.md`, `docs/safety/security-model.md`, and Phase 55 evidence fields in `governance/remediation-contracts.toml`.
- **Allowed reads:** passing tests and Windows/POSIX results.
- **Prohibited:** source/tests/dependencies/migration claims.
- **Actions:** 1. Map claims to exact cases. 2. Update named docs/evidence and hand off APIs/capabilities to Phases 56/58. 3. Run §10 and compare changed paths to tasks.
- **Evidence:** docs diff, platform matrices, handoff.
- **Stop:** claim exceeds a supported platform result.
- **Verified outcome:** foundation closes and successors may migrate their writers.

## 10. Final verification and delivery gate

```text
$env:VIRTUAL_ENV=$null
$env:PYTHONPATH=$null
.venv/Scripts/python.exe -m pytest tests/test_phase55_atomic_file.py tests/test_phase55_physical_containment.py tests/test_phase55_verifier_record.py -q
.venv/Scripts/python.exe -m pytest tests/ -q
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/ruff.exe format --check src tests scripts
git diff --check
git diff --name-only
git status --short --branch
```

## 11. Exit checklist and successor evidence

- [ ] Ordinary RED precedes GREEN; no skip/XFAIL/XPASS.
- [ ] One AtomicFile owner accepts only sanitized contracts.
- [ ] Link/junction/reparse/swap/permission/unsupported cases are fail closed.
- [ ] Every fault leaves old/new valid destination and owned cleanup only.
- [ ] Verifier records contain no raw/recoverable capability.
- [ ] Windows/POSIX matrices pass; no dependency or writer migration.
- [ ] Every changed path belongs to one task.
