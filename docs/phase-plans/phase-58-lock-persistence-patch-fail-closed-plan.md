# Phase 58 implementation plan — capability locks, contained persistence, and fail-closed patch verification

## 1. Purpose and status

- **Operation:** Create the implementation plan for remediation Phase 7.
- **Planning status:** Implementation-ready after §4 admission passes.
- **Implementation status:** Not authorized.
- **Authority:** governing roadmap R-009, R-010, R-011 runtime migration, and R-016.
- **Predecessors:** accepted Phases 53-57 contracts and evidence.
- **Successor:** Phase 59 release evidence.
- **Protected:** roadmap, dependencies/lockfile, provenance/engine behavior, unrelated operations.
- **Amendment rule:** Any capability channel, state file, transaction rule, patch identity, verifier command, output boundary, or additional path requires amendment.
- **Lifecycle boundary:** No commit, push, merge, tag, publish, release, hooks, history rewrite, live secret/network, or direct uncontrolled patch application.

## 2. Authority, evidence, and decisions

Authority order: user → `AGENTS.md` → roadmap → Phases 53-57 contracts → current lock/memory/patch/public-boundary evidence.

Current evidence: lock logic is duplicated in daemon/manager; raw authority lifecycle is not caller-retained/verifier-only; maps/journals conflate absent/corrupt/error and risk lost updates; patch verifier can succeed with zero executed commands; patch claims do not bind every state/policy identity; eligible output migration is incomplete.

Closed decisions: caller generates/retains raw capability and supplies it through declared protected input; lock persists verifier metadata only; one generation owner; maps use CAS/retry semantics; journals retain corrupt evidence and distinguish outcomes; patch work starts from clean target and binds base/patch/sandbox/result/command/config/ignored inputs; verified success requires ≥1 bound required command executed/passed; every eligible boundary uses Phase 54 adapter.

Open decisions: None.

## 3. Goals, outcomes, exclusions, and invariants

Outcomes: secret capability locks; atomic generation-safe metadata; truthful concurrent maps/journals; state/policy-bound patch verification and contained rollback; complete eligible output contract enforcement.

Exclusions: provenance/engine conformance, dependencies, live network/credentials, Git history operations.

Invariants: stale authority cannot affect renewed generation; corrupt is never empty/absent/skipped; failed patch verification leaves checkout unchanged; service/stdio protocol messages are never ToolResult-wrapped.

## 4. Admission and predecessor gate

Require accepted predecessor API/platform matrices, public-operation manifest, invocation context, plugin adapter, and installed artifact evidence. Inspect all lock metadata, memory maps/journals, patch state/command/cleanup paths, and eligible output boundaries. Record worktree overlap. P58.0.1 assigns every state/output seam before RED work.

## 5. Requirement-ownership ledger

| Requirement | Tasks | Closure |
|---|---|---|
| Caller capability channels | P58.1.1-P58.1.2 | CLI/MCP custody matrix |
| Atomic verifier-only locks | P58.2.1-P58.2.2 | contention/generation/platform matrix |
| CAS maps | P58.3.1-P58.3.2 | lost-update/corruption matrix |
| Atomic journals | P58.4.1-P58.4.2 | same-name/replace/corrupt evidence matrix |
| Patch identity/policy | P58.5.1-P58.5.2 | dirty/drift/mutation matrix |
| Verification/recovery | P58.6.1-P58.6.2 | command execution/failure/cleanup matrix |
| Output migration | P58.7.1-P58.7.2 | manifest-wide malformed output matrix |
| Docs/release handoff | P58.8.1 | named docs and release evidence |

## 6. Shared contracts and handoff

`LockCapabilityInput` accepts caller-generated high-entropy value through protected stdin/descriptor/MCP sensitive field; acquire never returns it. `MeshLockManager` stores AtomicFile verifier record plus owner/lease/generation/physical identity.

Map transaction: load exact version or typed absent/corrupt/io error → transform → compare-and-swap through AtomicFile → bounded retry/conflict. Journal: per-record identity, explicit same-name policy, atomic replace, retained corrupt bytes and separate listing.

`PatchContract` binds clean base digest, patch digest, sandbox identity, result tree/diff, required command plan, test/config/generated/ignored-input digests, review class. `PatchVerifier` returns `completed|unavailable|failed` plus executed commands.

## 7. Contract-test inventory

| Contract | RED | GREEN | Exact ordinary tests |
|---|---|---|---|
| Capability custody | P58.1.1 | P58.1.2 | `test_caller_retains_only_raw_capability`; `test_cli_uses_protected_input_not_argv_or_environment`; `test_mcp_sensitive_value_is_never_rendered_or_persisted` |
| Lock metadata | P58.2.1 | P58.2.2 | `test_simultaneous_acquire_has_one_generation_owner`; `test_wrong_guessed_stale_capability_cannot_renew_or_release`; `test_link_swap_expiry_and_crash_recovery_fail_closed` |
| Maps | P58.3.1 | P58.3.2 | `test_invariant_preference_and_merkle_maps_preserve_concurrent_updates`; `test_map_absent_corrupt_invalid_io_are_distinct` |
| Journals | P58.4.1 | P58.4.2 | `test_checkpoint_same_name_policy_and_replace_are_atomic`; `test_corrupt_journal_bytes_are_retained_and_listed` |
| Patch binding | P58.5.1 | P58.5.2 | `test_dirty_or_changed_base_refuses_before_sandbox`; `test_patch_sandbox_result_and_command_policy_drift_refuses`; `test_policy_changing_patch_cannot_receive_ordinary_verified_success` |
| Patch verify/recovery | P58.6.1 | P58.6.2 | `test_zero_selected_or_executed_commands_never_verify`; `test_unavailable_failed_verifier_leaves_checkout_unchanged`; `test_rollback_and_cleanup_are_contained_and_manager_owned` |
| Output migration | P58.7.1 | P58.7.2 | `test_every_eligible_manifest_boundary_rejects_malformed_output`; `test_service_and_stdio_protocol_responses_are_not_tool_results` |

## 8. File, dependency, and documentation governance

New: `src/rush/mcp_mesh/capabilities.py`, `src/rush/memory/transactions.py`, `src/rush/patch/contracts.py`, `tests/test_phase58_lock_capabilities.py`, `tests/test_phase58_map_transactions.py`, `tests/test_phase58_checkpoint_journals.py`, `tests/test_phase58_patch_verification.py`, `tests/test_phase58_output_migration.py`.

Existing task-owned: `src/rush/mcp_mesh/__init__.py`, `src/rush/mcp_mesh/daemon.py`, `src/rush/mcp_mesh/lock_manager.py`, `src/rush/memory/checkpoint_journal.py`, `src/rush/memory/invariant_graph.py`, `src/rush/memory/merkle_invalidator.py`, `src/rush/memory/preference_store.py`, `src/rush/patch/__init__.py`, `src/rush/patch/applier.py`, `src/rush/patch/circuit_breaker.py`, `src/rush/patch/diff_parser.py`, `src/rush/patch/memory.py`, `src/rush/patch/promoter.py`, `src/rush/patch/sandbox.py`, `src/rush/patch/syntax_guard.py`, `src/rush/patch/verifier.py`, `src/rush/core/git_sandbox.py`, `src/rush/tools/continuity.py`, `src/rush/tools/fix.py`, `src/rush/cli.py`, `src/rush/mcp.py`, `src/rush/contracts/operations.py`, `src/rush/contracts/results.py`, `src/rush/invocation/models.py`, `src/rush/invocation/executor.py`, `src/rush/io/atomic_file.py`, `src/rush/io/physical_paths.py`, `src/rush/io/verifier_record.py`, `src/rush/safety/redactor.py`, `governance/public-operations.toml`, `governance/remediation-contracts.toml`, `tests/test_phase41_memory_ship.py`, `tests/test_phase42_toon_skeleton.py`, `tests/test_phase43_mistake_memory.py`, `tests/test_phase49_trace_swarm_recorder.py`, `tests/test_fix.py`, `tests/test_mcp.py`, `tests/test_cli.py`.

Docs owned only by P58.8.1: `docs/CLI_REFERENCE.md`, `docs/MCP_REFERENCE.md`, `docs/SECURITY.md`, `docs/SAFETY.md`, `docs/PRIVACY.md`, `docs/API_REFERENCE.md`, `docs/reference/result-reference.md`, `docs/safety/permissions.md`, `docs/safety/security-model.md`, `docs/vibecoding/instant-fix-and-auto-remediation.md`, `docs/maintainers/incident-and-security.md`.

All other writes prohibited. Tests write only injected temporary roots. Dependency changes: None. Required existing dependencies/contracts: Python 3.12 cryptographic randomness/HMAC, Phase 53 sanitizer, Phase 54 output adapters, Phase 55 containment/atomic/verifier APIs, Phase 56 protected-channel pattern, and Phase 57 invocation context.

## 9. Ordered workstreams and atomic task cards

### P58.0 — Admission

#### P58.0.1 — EVIDENCE: map lock, state, patch, and output seams

- **Task ID and binary outcome:** P58.0.1; every persistent/output boundary maps to one task and predecessor contract.
- **Start goal:** Freeze exact migration scope.
- **Prerequisites:** §4.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** R-009/R-010/R-011/R-016 admission fields in `governance/remediation-contracts.toml`.
- **Allowed reads:** `src/rush/mcp_mesh/daemon.py`, `src/rush/mcp_mesh/lock_manager.py`, `src/rush/memory/checkpoint_journal.py`, `src/rush/memory/invariant_graph.py`, `src/rush/memory/merkle_invalidator.py`, `src/rush/memory/preference_store.py`, `src/rush/patch/applier.py`, `src/rush/patch/circuit_breaker.py`, `src/rush/patch/diff_parser.py`, `src/rush/patch/memory.py`, `src/rush/patch/promoter.py`, `src/rush/patch/sandbox.py`, `src/rush/patch/syntax_guard.py`, `src/rush/patch/verifier.py`, `src/rush/core/git_sandbox.py`, `src/rush/tools/continuity.py`, `src/rush/tools/fix.py`, `src/rush/cli.py`, `src/rush/mcp.py`, `src/rush/contracts/operations.py`, `src/rush/contracts/results.py`, `src/rush/invocation/models.py`, `src/rush/invocation/executor.py`, `src/rush/io/atomic_file.py`, `src/rush/io/physical_paths.py`, `src/rush/io/verifier_record.py`, `src/rush/safety/redactor.py`, `governance/public-operations.toml`, `governance/remediation-contracts.toml`, `tests/test_phase41_memory_ship.py`, `tests/test_phase42_toon_skeleton.py`, `tests/test_phase43_mistake_memory.py`, `tests/test_phase49_trace_swarm_recorder.py`, `tests/test_fix.py`, `tests/test_mcp.py`, `tests/test_cli.py`.
- **Prohibited:** source/tests/docs/dependencies.
- **Actions:** 1. Inspect callers, state paths, errors, cleanup, output adapters. 2. Record exact symbol/path/contract/task/current defect. 3. Reconcile every manifest-eligible boundary and reparse TOML.
- **Evidence:** complete seam/migration table.
- **Stop:** any state/output boundary lacks ownership.
- **Verified outcome:** P58.1.1-P58.7.1 may start.

### P58.1 — Capability custody

#### P58.1.1 — RED: define caller-retained protected capability input

- **Task ID and binary outcome:** P58.1.1; three tests fail on current authority delivery/output.
- **Start goal:** Pin custody, channels, entropy/reuse/guess policy.
- **Prerequisites:** P58.0.1.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase58_lock_capabilities.py`.
- **Allowed reads:** CLI/MCP lock routes, daemon/manager, Phase 55 verifier and Phase 56 channel patterns.
- **Prohibited:** production/raw secret fixture/docs/XFAIL.
- **Actions:** 1. Arrange caller capability, stdin/descriptor/MCP sensitive input, argv/env/output/log spies, low-entropy/reuse/guess cases. 2. Add exactly three §7 custody tests plus policy cases. 3. Run focused with MCP tests and record failures.
- **Evidence:** red output and zero-secret fixture record.
- **Stop:** test persists/renders raw capability.
- **Verified outcome:** P58.1.2 may create capability input.

#### P58.1.2 — GREEN: accept but never return caller authority

- **Task ID and binary outcome:** P58.1.2; caller alone retains raw value and public routes expose no secret.
- **Start goal:** Satisfy P58.1.1 only.
- **Prerequisites:** recorded P58.1.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `src/rush/mcp_mesh/capabilities.py`; modify `src/rush/mcp_mesh/__init__.py`, `src/rush/cli.py`, `src/rush/mcp.py`, `src/rush/safety/redactor.py`, `tests/test_phase58_lock_capabilities.py`, `tests/test_mcp.py`.
- **Allowed reads:** P58.1.1 evidence and predecessor secret/verifier contracts.
- **Prohibited:** lock metadata implementation, argv/env fallback, docs.
- **Actions:** 1. Reinspect public acquire/renew/release parsing. 2. Implement policy/type and protected input adapters; acquire accepts but never returns/persists value. 3. Run focused, MCP, sanitizer tests and sentinel scan.
- **Evidence:** green custody matrix.
- **Stop:** any raw value enters ordinary artifact/channel.
- **Verified outcome:** P58.2.1 may test metadata.

### P58.2 — Lock metadata

#### P58.2.1 — RED: define atomic verifier-only generation semantics

- **Task ID and binary outcome:** P58.2.1; contention/generation/platform cases fail.
- **Start goal:** Pin one owner, renewal, expiry/recovery, stale authority, physical containment.
- **Prerequisites:** P58.1.2 and Phase 55.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `tests/test_phase58_lock_capabilities.py`, `tests/test_phase49_trace_swarm_recorder.py`.
- **Allowed reads:** daemon/manager and Phase 55 APIs.
- **Prohibited:** production/docs/XFAIL.
- **Actions:** 1. Arrange acquisition barrier, renew/release, direct disclosure, owner/permission, links/junction/swaps, expiry/crash, old holder. 2. Add exactly three §7 metadata tests with parameterized cases. 3. Run focused files and record failures.
- **Evidence:** red race/platform matrix.
- **Stop:** fixture cannot identify generation owner.
- **Verified outcome:** P58.2.2 may consolidate lock manager.

#### P58.2.2 — GREEN: centralize locks in AtomicFile verifier records

- **Task ID and binary outcome:** P58.2.2; one contender owns a generation and stale capability cannot affect renewal.
- **Start goal:** Satisfy P58.2.1 only.
- **Prerequisites:** recorded P58.2.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/mcp_mesh/daemon.py`, `src/rush/mcp_mesh/lock_manager.py`, `src/rush/mcp_mesh/capabilities.py`, `src/rush/io/atomic_file.py`, `physical_paths.py`, `verifier_record.py`, `tests/test_phase58_lock_capabilities.py`, `tests/test_phase49_trace_swarm_recorder.py`.
- **Allowed reads:** P58.2.1 evidence.
- **Prohibited:** memory/patch/output/docs.
- **Actions:** 1. Reinspect duplicated metadata writes. 2. Make `MeshLockManager` sole owner; bind verifier/lease/generation/physical identity; atomic acquire/renew/release/recovery. 3. Run focused, Phase 55 platform, and mesh tests.
- **Evidence:** green contention/platform matrices and verifier-only record.
- **Stop:** stale/raw authority can affect new generation.
- **Verified outcome:** R-009 lock contract closes.

### P58.3 — CAS maps

#### P58.3.1 — RED: define concurrent map transactions and truthful errors

- **Task ID and binary outcome:** P58.3.1; map cases fail on lost updates/error conflation.
- **Start goal:** Pin invariant/preference/merkle map semantics.
- **Prerequisites:** P58.0.1 and Phase 55.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase58_map_transactions.py`.
- **Allowed reads:** `src/rush/memory/invariant_graph.py`, `src/rush/memory/preference_store.py`, `src/rush/memory/merkle_invalidator.py`, `tests/test_phase41_memory_ship.py`, `tests/test_phase43_mistake_memory.py`, `tests/test_phase49_trace_swarm_recorder.py`.
- **Prohibited:** production/journal/patch/docs/XFAIL.
- **Actions:** 1. Arrange two-writer barrier, absent/corrupt/invalid/I-O, link/junction/swap/fault cases. 2. Add exactly two §7 map tests across all three stores. 3. Run focused file and record per-store failures.
- **Evidence:** red transaction/error matrix.
- **Stop:** a store has undocumented conflict semantics.
- **Verified outcome:** P58.3.2 may create transactions/migrate maps.

#### P58.3.2 — GREEN: migrate maps to contained CAS transactions

- **Task ID and binary outcome:** P58.3.2; concurrent updates survive and outcomes stay distinct.
- **Start goal:** Satisfy P58.3.1 only.
- **Prerequisites:** recorded P58.3.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `src/rush/memory/transactions.py`; modify `src/rush/memory/invariant_graph.py`, `preference_store.py`, `merkle_invalidator.py`, `src/rush/io/atomic_file.py`, `physical_paths.py`, `tests/test_phase58_map_transactions.py`, `tests/test_phase41_memory_ship.py`, `tests/test_phase43_mistake_memory.py`.
- **Allowed reads:** P58.3.1 evidence and AtomicFile.
- **Prohibited:** journals/patch/output/docs.
- **Actions:** 1. Reinspect each load-transform-store sequence. 2. Implement typed load and versioned CAS/retry helper; migrate only three maps and all their temp/read/write/cleanup paths. 3. Run focused and existing memory tests plus Phase 55 faults.
- **Evidence:** green concurrency/error matrix.
- **Stop:** corrupt/error becomes empty/absent/skipped.
- **Verified outcome:** map portion of R-010 closes.

### P58.4 — Checkpoint journals

#### P58.4.1 — RED: define atomic journal and corrupt-evidence behavior

- **Task ID and binary outcome:** P58.4.1; same-name/replace/corruption tests fail.
- **Start goal:** Pin checkpoint record identity and truthful listing.
- **Prerequisites:** P58.0.1 and Phase 55.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase58_checkpoint_journals.py`.
- **Allowed reads:** `src/rush/memory/checkpoint_journal.py`, continuity callers/tests.
- **Prohibited:** production/maps/patch/docs/XFAIL.
- **Actions:** 1. Arrange same-name writes, per-record replace faults, corrupt bytes, links/junction/swaps. 2. Add exactly two §7 journal tests plus absent/invalid/I-O distinctions. 3. Run focused and continuity tests; record failures.
- **Evidence:** red journal matrix and retained corrupt digest.
- **Stop:** same-name policy is undefined by current authority.
- **Verified outcome:** P58.4.2 may migrate journal.

#### P58.4.2 — GREEN: make journal records atomic and corruption-visible

- **Task ID and binary outcome:** P58.4.2; record replacement is atomic and corrupt bytes remain listed/evidenced.
- **Start goal:** Satisfy P58.4.1 only.
- **Prerequisites:** recorded P58.4.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/memory/checkpoint_journal.py`, `src/rush/tools/continuity.py`, `src/rush/io/atomic_file.py`, `physical_paths.py`, `tests/test_phase58_checkpoint_journals.py`, `tests/test_phase42_toon_skeleton.py`.
- **Allowed reads:** P58.4.1 evidence.
- **Prohibited:** maps/patch/output/docs.
- **Actions:** 1. Reinspect record naming/list/load/write. 2. Implement explicit same-name policy, AtomicFile per-record replace, typed outcomes, retained corrupt evidence. 3. Run focused, continuity, Phase 55 tests.
- **Evidence:** green journal matrix.
- **Stop:** corrupt bytes are deleted/interpreted as authority.
- **Verified outcome:** journal portion of R-010 closes.

### P58.5 — Patch identities

#### P58.5.1 — RED: define clean-state and command-policy binding

- **Task ID and binary outcome:** P58.5.1; three patch tests fail on unbound state/policy.
- **Start goal:** Pin dirty/untracked/base/patch/sandbox/result/command/config/generated/ignored identities and privileged review.
- **Prerequisites:** P58.0.1 and Phase 57 context.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase58_patch_verification.py`.
- **Allowed reads:** patch modules, git sandbox, fix tool/tests, invocation context.
- **Prohibited:** production/direct apply/docs/XFAIL.
- **Actions:** 1. Arrange each dirty/drift/mutation state and sandbox/result mismatch. 2. Add exactly three §7 binding tests through public fix path. 3. Run focused file and record failures.
- **Evidence:** red identity matrix.
- **Stop:** a required identity has no canonical digest.
- **Verified outcome:** P58.5.2 may create PatchContract.

#### P58.5.2 — GREEN: bind patch work to clean state and complete policy

- **Task ID and binary outcome:** P58.5.2; every drift refuses and policy-changing patches cannot get ordinary verified success.
- **Start goal:** Satisfy P58.5.1 only.
- **Prerequisites:** recorded P58.5.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `src/rush/patch/contracts.py`; modify `src/rush/patch/__init__.py`, `applier.py`, `diff_parser.py`, `memory.py`, `promoter.py`, `sandbox.py`, `syntax_guard.py`, `src/rush/core/git_sandbox.py`, `src/rush/tools/fix.py`, `src/rush/invocation/models.py`, `tests/test_phase58_patch_verification.py`, `tests/test_fix.py`.
- **Allowed reads:** P58.5.1 evidence.
- **Prohibited:** verifier execution/recovery/output migration/docs.
- **Actions:** 1. Reinspect public patch flow before sandbox. 2. Reject dirty target; build/revalidate PatchContract at sandbox/apply/verify boundaries; assign privileged review for policy change. 3. Run focused, fix, git sandbox tests.
- **Evidence:** green identity matrix.
- **Stop:** claim would transfer across changed identity.
- **Verified outcome:** P58.6.1 may test verifier/recovery.

### P58.6 — Verification and recovery

#### P58.6.1 — RED: define required command execution and contained recovery

- **Task ID and binary outcome:** P58.6.1; command/failure/cleanup cases fail on current fail-open behavior.
- **Start goal:** Pin zero/unavailable/failed worktree/direct apply/rollback/temp/link cleanup.
- **Prerequisites:** P58.5.2 and Phase 55.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `tests/test_phase58_patch_verification.py`, `tests/test_fix.py`.
- **Allowed reads:** verifier/circuit breaker/applier/promoter/sandbox and AtomicFile.
- **Prohibited:** production/output/docs/XFAIL.
- **Actions:** 1. Arrange zero selected/executed, missing runner, unavailable/failed verifier, failed worktree/direct apply, rollback, temp collision, link/junction escape. 2. Add exactly three §7 verify/recovery tests. 3. Run focused files and record failures.
- **Evidence:** red execution/recovery matrix and checkout digest.
- **Stop:** fixture cannot prove checkout unchanged/cleanup ownership.
- **Verified outcome:** P58.6.2 may implement verifier/recovery.

#### P58.6.2 — GREEN: require executed passing commands and contained rollback

- **Task ID and binary outcome:** P58.6.2; verified success contains ≥1 bound passed command; failures preserve checkout and contained cleanup.
- **Start goal:** Satisfy P58.6.1 only.
- **Prerequisites:** recorded P58.6.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/patch/verifier.py`, `circuit_breaker.py`, `applier.py`, `promoter.py`, `sandbox.py`, `src/rush/core/git_sandbox.py`, `src/rush/io/atomic_file.py`, `physical_paths.py`, `tests/test_phase58_patch_verification.py`, `tests/test_fix.py`.
- **Allowed reads:** P58.6.1 evidence and PatchContract.
- **Prohibited:** output migration/docs.
- **Actions:** 1. Reinspect every success/failure/cleanup return. 2. Return exact verifier outcomes/executed evidence; require bound command count/pass; AtomicFile/PhysicalRoot rollback/temp/cleanup; fail closed. 3. Run focused, Phase 55 faults, and fix tests.
- **Evidence:** green matrix, command records, unchanged checkout/outside digests.
- **Stop:** any success with zero/unbound commands or escaped cleanup.
- **Verified outcome:** R-016 closes.

### P58.7 — Output migration

#### P58.7.1 — RED: enumerate malformed output at every eligible boundary

- **Task ID and binary outcome:** P58.7.1; manifest-wide tests fail where adapters are missing.
- **Start goal:** Pin exact tool/admin enforcement and protocol exclusions.
- **Prerequisites:** P58.2.2-P58.6.2 and Phases 54/56/57.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase58_output_migration.py`, modify `tests/test_mcp.py`, `tests/test_cli.py`.
- **Allowed reads:** public-operation manifest, contracts, invocation executor, plugin/lock/persistence/patch boundaries.
- **Prohibited:** production/manifest/docs/XFAIL.
- **Actions:** 1. Generate table from literal manifest operation IDs and target contracts. 2. Add exactly two §7 tests injecting malformed output through each invoked boundary. 3. Run focused CLI/MCP files and record missing-adapter failures.
- **Evidence:** red operation/boundary matrix.
- **Stop:** operation is unclassified.
- **Verified outcome:** P58.7.2 may enforce adapters.

#### P58.7.2 — GREEN: enforce each declared output contract

- **Task ID and binary outcome:** P58.7.2; every eligible boundary converts malformed output to canonical contract error; protocols stay native.
- **Start goal:** Satisfy P58.7.1 only.
- **Prerequisites:** recorded P58.7.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/invocation/executor.py`, `src/rush/contracts/operations.py`, `results.py`, `src/rush/cli.py`, `src/rush/mcp.py`, `src/rush/mcp_mesh/lock_manager.py`, `src/rush/tools/continuity.py`, `src/rush/tools/fix.py`, `governance/public-operations.toml`, `tests/test_phase58_output_migration.py`, `tests/test_mcp.py`, `tests/test_cli.py`.
- **Allowed reads:** P58.7.1 evidence and Phase 54/56 contracts.
- **Prohibited:** wrapping service/stdio protocol, unrelated behavior/docs.
- **Actions:** 1. Reinspect each failing boundary. 2. Invoke exact adapter after sanitizer and before transport serialization; leave service/liveness/initialize/list native. 3. Run focused, Phase 54 adapter, plugin, lock, persistence, patch, installed operation probes.
- **Evidence:** green manifest-wide matrix.
- **Stop:** adapter target differs from manifest.
- **Verified outcome:** R-011 runtime migration closes.

### P58.8 — Documentation and handoff

#### P58.8.1 — VERIFY/DOCS/HANDOFF: close release-critical state contracts

- **Task ID and binary outcome:** P58.8.1; named docs and Phase 59 handoff cite passing race/fault/installed evidence.
- **Start goal:** Document only proven custody/state/patch/output behavior.
- **Prerequisites:** P58.1.2-P58.7.2.
- **Documentation impact:** all eleven §8 docs.
- **Dependency impact:** None.
- **Allowed writes:** `docs/CLI_REFERENCE.md`, `docs/MCP_REFERENCE.md`, `docs/SECURITY.md`, `docs/SAFETY.md`, `docs/PRIVACY.md`, `docs/API_REFERENCE.md`, `docs/reference/result-reference.md`, `docs/safety/permissions.md`, `docs/safety/security-model.md`, `docs/vibecoding/instant-fix-and-auto-remediation.md`, `docs/maintainers/incident-and-security.md`, and R-009/R-010/R-011/R-016 evidence fields in `governance/remediation-contracts.toml`.
- **Allowed reads:** passing tests, platform/fault/installed results.
- **Prohibited:** source/tests/dependencies/provenance claims.
- **Actions:** 1. Map every claim to evidence. 2. Update named docs and record Phase 59 release-gate handoff. 3. Run §10 and compare changed paths to tasks.
- **Evidence:** docs diff, matrices, handoff.
- **Stop:** unowned path or source-tree-only proof.
- **Verified outcome:** R-009/R-010/R-011/R-016 close.

## 10. Final verification and delivery gate

```text
$env:VIRTUAL_ENV=$null
$env:PYTHONPATH=$null
.venv/Scripts/python.exe -m pytest tests/test_phase58_lock_capabilities.py tests/test_phase58_map_transactions.py tests/test_phase58_checkpoint_journals.py tests/test_phase58_patch_verification.py tests/test_phase58_output_migration.py -q
.venv/Scripts/python.exe -m pytest tests/ -q
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/ruff.exe format --check src tests scripts
.venv/Scripts/python.exe scripts/probe_installed_artifacts.py
git diff --check
git diff --name-only
git status --short --branch
```

## 11. Exit checklist and successor evidence

- [ ] Ordinary RED precedes GREEN; no skip/XFAIL/XPASS.
- [ ] Caller-retained capabilities never appear in ordinary channels/artifacts.
- [ ] Lock generation is atomic/verifier-only/stale-safe.
- [ ] Maps preserve concurrent updates; journals retain truthful corruption evidence.
- [ ] Patch success binds clean state/policy and ≥1 executed passing required command.
- [ ] Failure leaves checkout unchanged and cleanup physically contained.
- [ ] Every eligible boundary enforces its declared adapter; protocols remain native.
- [ ] No dependency/live secret/network/history operation.
- [ ] Every changed path belongs to one task.
