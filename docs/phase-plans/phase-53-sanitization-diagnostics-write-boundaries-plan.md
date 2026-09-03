# Phase 53 implementation plan — complete sanitization and failure diagnostics

## 1. Purpose and status

- **Operation:** Create the implementation plan for remediation Phase 2.
- **Planning status:** Implementation-ready after §4 admission passes.
- **Implementation status:** Not authorized.
- **Authority:** governing roadmap R-002 and R-008.
- **Predecessor:** accepted Phase 51 & Phase 52 package identity, installed artifacts, and version authority (revision `d2307a8`, baseline 986 passing tests, `governance/remediation-phase-52.toml`, R-001/R-012 completed).
- **Successors:** Phases 54-59 inherit the sanitizer/output contract.
- **Protected:** roadmap, adversarial review, `pyproject.toml`, `uv.lock`.
- **Amendment rule:** A newly discovered writer must be added to one literal RED/GREEN pair before edit.
- **Lifecycle boundary:** No commit, push, merge, tag, publish, release, hooks, or history rewrite.

## 2. Authority, evidence, and decisions

Authority order: user → `AGENTS.md` → roadmap → Phase 51/52 records → current writer/source/test evidence.

Current evidence: `src/rush/safety/redactor.py` does not cover the complete recursive/key/collision contract; `src/rush/tools/common.py` owns separate secret-assignment logic (`_SECRET_ASSIGNMENT`); public serializers and persistent writers apply inconsistent redaction; `src/rush/logging.py` does not guarantee one complete redacted exception record. Baseline test count is 986 passing tests with zero `src.rush` imports and isolated `pythonpath = ["src"]`.

Closed decisions: sanitize JSON-safe copies before formatting/truncation/serialization/write; never mutate authorized execution inputs; sanitize mapping keys and expose collisions; unsupported objects fail closed; MCP diagnostics remain stderr-only. No dependencies.

Open decisions: None. An unowned writer stops for amendment.

## 3. Goals, outcomes, exclusions, and invariants

Outcomes: one recursive sanitizer; subprocess/public outputs sanitized before bounds; all named persisted/temp/backup/rollback bytes sanitized; one complete redacted NDJSON exception record; no MCP stdout contamination.

Exclusions: atomicity/physical containment (Phase 55), output-schema migration (Phases 54/58), plugin trust (Phase 56), behavior changes to executed inputs.

Invariant: a fresh runtime sentinel must be absent from every observable/retained artifact while the exact unsanitized semantic value reaches only the already-authorized action.

## 4. Admission and predecessor gate

Require accepted Phase 51 coverage and Phase 52 package identity records (revision `d2307a8`, 986 baseline tests). Create `governance/remediation-phase-53.toml` documenting admission, baseline seams, and findings R-002/R-008 ownership. Inventory every current call to redaction, serialization, `write_text`, `write_bytes`, `atomic_write_bytes`, temp/backup/rollback creation, cache persistence, and logger exception formatting. Record overlapping worktree edits and stop on overlap. P53.0.1 closes the literal writer inventory before RED work.

## 5. Requirement-ownership ledger

| Requirement | Tasks | Closure |
|---|---|---|
| Recursive values/keys/collisions/URLs/errors | P53.1.1-P53.1.2 | sanitizer contract suite |
| Subprocess and public output boundaries | P53.2.1-P53.2.2 | output-boundary matrix |
| Governance/config/mesh writers | P53.3.1-P53.3.2 | completed/aborted artifact scan |
| Memory/patch/plugin/release writers | P53.4.1-P53.4.2 | state/security artifact scan |
| Exception diagnostics and MCP stdout | P53.5.1-P53.5.2 | stderr/stdout integration suite |
| Documentation/handoff | P53.6.1 | named docs and sanitizer contract |

## 6. Shared contracts and handoff

`sanitize_value(value) -> SanitizationResult` returns JSON-safe value, redaction count, and secret-free collision metadata. Keys and values recurse. Collision output is deterministic and loss-visible. Unsupported values return canonical sanitizer error, never raw `repr`. `redact_text` is a compatibility adapter to the same engine. Sanitization precedes truncation and every output/write; execution input is a separate object.

## 7. Contract-test inventory

| Contract | RED | GREEN | Exact tests |
|---|---|---|---|
| Core sanitizer | P53.1.1 | P53.1.2 | `test_fresh_sentinel_is_removed_from_values_and_keys`; `test_key_collision_is_loss_visible`; `test_url_and_exception_forms_are_sanitized`; `test_execution_input_is_unchanged` |
| Subprocess/public outputs | P53.2.1 | P53.2.2 | `test_subprocess_sanitizes_before_truncation`; `test_cli_mcp_html_sarif_cache_outputs_remove_fresh_sentinel` |
| Governance/config/mesh writes | P53.3.1 | P53.3.2 | `test_governance_config_hook_and_mesh_artifacts_are_sanitized_on_success_and_abort` |
| State/security/release writes | P53.4.1 | P53.4.2 | `test_memory_patch_plugin_release_artifacts_are_sanitized_on_success_and_abort` |
| Logging | P53.5.1 | P53.5.2 | `test_exception_emits_one_complete_redacted_ndjson_record`; `test_formatter_failure_emits_one_safe_fallback`; `test_mcp_stdout_remains_json_rpc_only` |

## 8. File, dependency, and documentation governance

Core/output writes: `src/rush/safety/redactor.py`, `src/rush/safety/__init__.py`, `src/rush/tools/common.py`, `src/rush/logging.py`, `src/rush/cli.py`, `src/rush/mcp.py`, `src/rush/html_export.py`, `src/rush/sarif.py`, `src/rush/score/html_report.py`, `src/rush/score/sarif_export.py`, `src/rush/cache.py`.

Governance/config/mesh writer group: `src/rush/governance/mcp_configs.py`, `src/rush/governance/scaffolder.py`, `src/rush/governance/synchronizer.py`, `src/rush/hook/tamper_detector.py`, `src/rush/mcp_mesh/daemon.py`, `src/rush/mcp_mesh/lock_manager.py`.

State/security/release writer group: `src/rush/memory/checkpoint_journal.py`, `src/rush/memory/failure_ledger.py`, `src/rush/memory/invariant_graph.py`, `src/rush/memory/merkle_invalidator.py`, `src/rush/memory/preference_store.py`, `src/rush/patch/applier.py`, `src/rush/patch/memory.py`, `src/rush/patch/promoter.py`, `src/rush/patch_generator.py`, `src/rush/plugins/trust.py`, `src/rush/plugins/trust_store.py`, `src/rush/release/ci_generator.py`, `src/rush/release/docker_generator.py`, `src/rush/release/provenance.py`, `src/rush/safety/audit_logger.py`, `src/rush/session_memory.py`, `src/rush/tools/attest.py`, `src/rush/tools/continuity.py`, `src/rush/tools/fix.py`, `src/rush/tools/flight_recorder.py`, `src/rush/tools/iam_audit.py`, `src/rush/tools/pr_synthesize.py`, `src/rush/tools/dead_asset.py`, `src/rush/tools/error_catalog.py`, `src/rush/tools/benchmark.py`.

New tests: `tests/test_phase53_sanitizer_contract.py`, `tests/test_phase53_output_boundaries.py`, `tests/test_phase53_governance_writers.py`, `tests/test_phase53_state_writers.py`, `tests/test_phase53_logging_diagnostics.py`.

Docs and governance owned by P53.6.1: `docs/SECURITY.md`, `docs/PRIVACY.md`, `docs/SAFETY.md`, `docs/MCP.md`, `docs/JSON_SCHEMA.md`, `docs/developer/debugging-guide.md`, `docs/maintainers/incident-and-security.md`, `docs/safety/privacy-and-data-handling.md`, `docs/safety/security-model.md`, `README.md`, `CHANGELOG.md`, `governance/remediation-phase-53.toml`, `governance/remediation-contracts.toml`, `governance/first-party-coverage.toml`, `docs/developer/phase-53-implementation-evidence.md`, `docs/developer/backlog.md`, `docs/developer/issues.md`, `docs/developer/testing-guide.md`, `docs/maintainers/release-playbook.md`.

All other writes prohibited. Dependency changes: None. Required existing dependencies/contracts: Python 3.12 stdlib serialization/URL/exception APIs, Phase 51/52 coverage and package identity records, and the existing Rush logging/export/cache writers.

## 9. Ordered workstreams and atomic task cards

### P53.0 — Admission

#### P53.0.1 — EVIDENCE: freeze the writer/boundary inventory

- **Task ID and binary outcome:** P53.0.1; every Phase 51 R-002/R-008 boundary maps to one §8 file and one RED/GREEN pair.
- **Start goal:** Close write ownership.
- **Prerequisites:** §4.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** Create `governance/remediation-phase-53.toml` and update Phase 53 evidence section in `governance/remediation-contracts.toml`.
- **Allowed reads:** coverage record and bounded repository writer/redactor call paths.
- **Prohibited:** source/tests/docs/dependencies.
- **Actions:** 1. Inspect each writer and caller. 2. Record boundary, serializer, temp/backup behavior, task owner, and current leak. 3. Reconcile every §8 file exactly once and reparse TOML.
- **Evidence:** complete inventory.
- **Stop:** unowned writer or overlapping edit.
- **Verified outcome:** P53.1.1-P53.5.1 may start.

### P53.1 — Sanitizer kernel

#### P53.1.1 — RED: define recursive sanitizer behavior

- **Task ID and binary outcome:** P53.1.1; four ordinary tests fail on missing behavior.
- **Start goal:** Pin recursive/key/collision/encoded/error and input-separation contracts.
- **Prerequisites:** P53.0.1.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase53_sanitizer_contract.py`.
- **Allowed reads:** current redactor/common tests and source.
- **Prohibited:** production/writers/docs/skip/XFAIL.
- **Actions:** 1. Arrange fresh per-test sentinels in values, keys, URLs, exceptions, identifiers, and unsupported objects. 2. Add exactly §7 core tests against `sanitize_value`; assert collision structure and unchanged action object. 3. Run focused file and record assertion/absent-API failures only.
- **Evidence:** fixtures and red output.
- **Stop:** test needs undefined collision semantics.
- **Verified outcome:** P53.1.2 may edit sanitizer seams.

#### P53.1.2 — GREEN: create one recursive sanitizer

- **Task ID and binary outcome:** P53.1.2; core tests pass through one policy engine.
- **Start goal:** Satisfy P53.1.1 only.
- **Prerequisites:** recorded P53.1.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/safety/redactor.py`, `src/rush/safety/__init__.py`, `src/rush/tools/common.py`, and `tests/test_phase53_sanitizer_contract.py` only to retain or strengthen its original assertions.
- **Allowed reads:** P53.1.1 evidence and existing compatibility callers.
- **Prohibited:** output/writer migration, docs, dependencies.
- **Actions:** 1. Authorize `SanitizationResult`, `sanitize_value`, compatibility `redact_text`, and removal of independent assignment policy. 2. Implement recursive JSON-safe behavior and deterministic collision/error forms. 3. Run focused tests, `tests/test_agent_safety_guard.py`, and `tests/test_subprocess_contract.py`.
- **Evidence:** green output and one policy source.
- **Stop:** raw `repr`, last-write-wins collision, or action-input mutation.
- **Verified outcome:** later boundary GREEN tasks may call the sanitizer.

### P53.2 — Subprocess and public outputs

#### P53.2.1 — RED: expose pre-truncation and serializer leaks

- **Task ID and binary outcome:** P53.2.1; named output tests fail with fresh sentinels.
- **Start goal:** Pin subprocess, CLI, MCP, HTML, SARIF, score, and cache boundaries.
- **Prerequisites:** P53.1.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase53_output_boundaries.py`; modify `tests/test_subprocess_contract.py` only for fresh-sentinel cases.
- **Allowed reads:** `src/rush/safety/redactor.py`, `src/rush/tools/common.py`, `src/rush/cli.py`, `src/rush/mcp.py`, `src/rush/html_export.py`, `src/rush/sarif.py`, `src/rush/score/html_report.py`, `src/rush/score/sarif_export.py`, `src/rush/cache.py`, and their existing tests.
- **Prohibited:** production/writers/docs/XFAIL.
- **Actions:** 1. Arrange fake subprocess outcomes and public serializers with sentinel keys/values/exceptions. 2. Add exactly §7 output tests, asserting sanitization precedes bounds and cache defensive reads. 3. Run both test files and record contract assertion failures.
- **Evidence:** boundary matrix and red output.
- **Stop:** test bypasses public serializer or execution seam.
- **Verified outcome:** P53.2.2 may edit core/output paths.

#### P53.2.2 — GREEN: sanitize subprocess and public serialization

- **Task ID and binary outcome:** P53.2.2; every named output contains no sentinel and action input remains exact.
- **Start goal:** Satisfy P53.2.1 only.
- **Prerequisites:** recorded P53.2.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/tools/common.py`, `src/rush/cli.py`, `src/rush/mcp.py`, `src/rush/html_export.py`, `src/rush/sarif.py`, `src/rush/score/html_report.py`, `src/rush/score/sarif_export.py`, `src/rush/cache.py`, `tests/test_phase53_output_boundaries.py`, and `tests/test_subprocess_contract.py`.
- **Allowed reads:** P53.2.1 evidence and serializer callers.
- **Prohibited:** persistent-writer migration, schema redesign, docs/dependencies.
- **Actions:** 1. Reinspect exact pre-bound/pre-serialization points. 2. Pass output copies through `sanitize_value` immediately before each boundary; cache sanitizes before set and after get without changing execution input. 3. Run focused files, `tests/test_mcp.py`, `tests/test_cache.py`, static-tool tests, and Ruff on changed files.
- **Evidence:** green matrix and exact action-spy values.
- **Stop:** sanitizer error falls back to raw output.
- **Verified outcome:** public/subprocess boundaries are closed.

### P53.3 — Governance/config/mesh persistence

#### P53.3.1 — RED: expose governance/config/mesh retained leaks

- **Task ID and binary outcome:** P53.3.1; one table-driven test fails for each named writer on completed or aborted artifacts.
- **Start goal:** Pin only the §8 governance/config/mesh group.
- **Prerequisites:** P53.1.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase53_governance_writers.py`.
- **Allowed reads:** `src/rush/governance/mcp_configs.py`, `src/rush/governance/scaffolder.py`, `src/rush/governance/synchronizer.py`, `src/rush/hook/tamper_detector.py`, `src/rush/mcp_mesh/daemon.py`, `src/rush/mcp_mesh/lock_manager.py`, `tests/test_phase53_governance_writers.py`, `src/rush/safety/redactor.py`.
- **Prohibited:** production, other writer group, docs, XFAIL.
- **Actions:** 1. Arrange temp roots and forced serialize/write/replace failures for each writer. 2. Add the exact table test named in §7 and assert completed/temp/backup artifacts lack key/value/exception sentinels. 3. Run focused file and record per-writer failures.
- **Evidence:** writer-case table and red output.
- **Stop:** a writer has unlisted helper ownership.
- **Verified outcome:** P53.3.2 may edit only this writer group.

#### P53.3.2 — GREEN: sanitize governance/config/mesh records before writes

- **Task ID and binary outcome:** P53.3.2; all group artifacts are sentinel-free on success/abort.
- **Start goal:** Satisfy P53.3.1 only.
- **Prerequisites:** recorded P53.3.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/governance/mcp_configs.py`, `src/rush/governance/scaffolder.py`, `src/rush/governance/synchronizer.py`, `src/rush/hook/tamper_detector.py`, `src/rush/mcp_mesh/daemon.py`, `src/rush/mcp_mesh/lock_manager.py`, and `tests/test_phase53_governance_writers.py`.
- **Allowed reads:** P53.3.1 evidence and sanitizer API.
- **Prohibited:** atomicity redesign, other writers, docs.
- **Actions:** 1. Locate each final serialization input. 2. Sanitize a record copy immediately before serialization; preserve action/config inputs. 3. Run focused test and existing governance/hook/mesh tests.
- **Evidence:** green matrix and unchanged action spies.
- **Stop:** behavior requires Phase 55 atomicity/containment.
- **Verified outcome:** this writer family is closed.

### P53.4 — State/security/release persistence

#### P53.4.1 — RED: expose state/security/release retained leaks

- **Task ID and binary outcome:** P53.4.1; table cases fail for each named writer.
- **Start goal:** Pin only the §8 state/security/release group.
- **Prerequisites:** P53.1.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase53_state_writers.py`.
- **Allowed reads:** `src/rush/memory/checkpoint_journal.py`, `src/rush/memory/failure_ledger.py`, `src/rush/memory/invariant_graph.py`, `src/rush/memory/merkle_invalidator.py`, `src/rush/memory/preference_store.py`, `src/rush/patch/applier.py`, `src/rush/patch/memory.py`, `src/rush/patch/promoter.py`, `src/rush/patch_generator.py`, `src/rush/plugins/trust.py`, `src/rush/plugins/trust_store.py`, `src/rush/release/ci_generator.py`, `src/rush/release/docker_generator.py`, `src/rush/release/provenance.py`, `src/rush/safety/audit_logger.py`, `src/rush/session_memory.py`, `src/rush/tools/attest.py`, `src/rush/tools/continuity.py`, `src/rush/tools/fix.py`, `src/rush/tools/flight_recorder.py`, `src/rush/tools/iam_audit.py`, `src/rush/tools/pr_synthesize.py`, `src/rush/tools/dead_asset.py`, `src/rush/tools/error_catalog.py`, `src/rush/tools/benchmark.py`, `tests/test_phase53_state_writers.py`, `src/rush/safety/redactor.py`.
- **Prohibited:** production, other group, docs, XFAIL.
- **Actions:** 1. Arrange injected temp roots and aborts. 2. Add the §7 state-writer test with one case per file and completed/temp/backup/rollback scans. 3. Run focused file and retain per-writer red results.
- **Evidence:** case table and red output.
- **Stop:** an unlisted shared helper is required.
- **Verified outcome:** P53.4.2 may edit only this writer group.

#### P53.4.2 — GREEN: sanitize state/security/release records before writes

- **Task ID and binary outcome:** P53.4.2; all group artifacts are sentinel-free and actions unchanged.
- **Start goal:** Satisfy P53.4.1 only.
- **Prerequisites:** recorded P53.4.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/memory/checkpoint_journal.py`, `src/rush/memory/failure_ledger.py`, `src/rush/memory/invariant_graph.py`, `src/rush/memory/merkle_invalidator.py`, `src/rush/memory/preference_store.py`, `src/rush/patch/applier.py`, `src/rush/patch/memory.py`, `src/rush/patch/promoter.py`, `src/rush/patch_generator.py`, `src/rush/plugins/trust.py`, `src/rush/plugins/trust_store.py`, `src/rush/release/ci_generator.py`, `src/rush/release/docker_generator.py`, `src/rush/release/provenance.py`, `src/rush/safety/audit_logger.py`, `src/rush/session_memory.py`, `src/rush/tools/attest.py`, `src/rush/tools/continuity.py`, `src/rush/tools/fix.py`, `src/rush/tools/flight_recorder.py`, `src/rush/tools/iam_audit.py`, `src/rush/tools/pr_synthesize.py`, `src/rush/tools/dead_asset.py`, `src/rush/tools/error_catalog.py`, `src/rush/tools/benchmark.py`, and `tests/test_phase53_state_writers.py`.
- **Allowed reads:** P53.4.1 evidence and sanitizer API.
- **Prohibited:** trust/atomicity/schema redesign, other writers, docs.
- **Actions:** 1. Locate final record serialization per writer. 2. Sanitize record copies at those points only. 3. Run focused file and existing memory/patch/plugin/release/safety tests.
- **Evidence:** green matrix and action-spy equality.
- **Stop:** changing execution semantics or Phase 55 responsibilities.
- **Verified outcome:** all persistent writer families are closed.

### P53.5 — Exception diagnostics

#### P53.5.1 — RED: define complete redacted stderr diagnostics

- **Task ID and binary outcome:** P53.5.1; three ordinary integration tests fail on current formatting/fallback behavior.
- **Start goal:** Pin one NDJSON exception record and clean MCP stdout.
- **Prerequisites:** P53.1.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase53_logging_diagnostics.py`.
- **Allowed reads:** `src/rush/logging.py`, MCP startup/error tests.
- **Prohibited:** production/docs/XFAIL.
- **Actions:** 1. Arrange exception and formatter-failure sentinels with captured stdout/stderr. 2. Add exactly three §7 logging tests. 3. Run focused file plus `tests/test_mcp.py` and record assertion failures.
- **Evidence:** red streams and test IDs.
- **Stop:** test does not exercise real logging handler.
- **Verified outcome:** P53.5.2 may edit logging only.

#### P53.5.2 — GREEN: emit one safe exception record

- **Task ID and binary outcome:** P53.5.2; logging tests pass with exactly one stderr record and JSON-RPC-only stdout.
- **Start goal:** Satisfy P53.5.1 only.
- **Prerequisites:** recorded P53.5.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/logging.py` and `tests/test_phase53_logging_diagnostics.py` only to retain or strengthen its original assertions.
- **Allowed reads:** P53.5.1 evidence and sanitizer API.
- **Prohibited:** MCP protocol behavior, other serializers, docs.
- **Actions:** 1. Reinspect formatter/handler exception path. 2. Format complete `LogRecord` including `exc_info`, sanitize before NDJSON, emit one bounded stderr fallback without recursive logging. 3. Run focused and MCP tests.
- **Evidence:** green output and captured stream counts.
- **Stop:** fallback can include raw exception or write stdout.
- **Verified outcome:** R-008 diagnostic contract is closed.

### P53.6 — Documentation and handoff

#### P53.6.1 — DOCS/HANDOFF: publish sanitizer boundaries

- **Task ID and binary outcome:** P53.6.1; named docs and Phase 54/55 handoff cite passing behavior.
- **Start goal:** Document only proven sanitizer/output semantics.
- **Prerequisites:** P53.1.2-P53.5.2.
- **Documentation impact:** `docs/SECURITY.md`, `docs/PRIVACY.md`, `docs/SAFETY.md`, `docs/MCP.md`, `docs/JSON_SCHEMA.md`, `docs/developer/debugging-guide.md`, `docs/maintainers/incident-and-security.md`, `docs/safety/privacy-and-data-handling.md`, `docs/safety/security-model.md`, `README.md`, `CHANGELOG.md`, `governance/remediation-phase-53.toml`, `governance/remediation-contracts.toml`, `governance/first-party-coverage.toml`, `docs/developer/phase-53-implementation-evidence.md`, `docs/developer/backlog.md`, `docs/developer/issues.md`, `docs/developer/testing-guide.md`, and `docs/maintainers/release-playbook.md`; document recursive/key/collision behavior, action separation, stderr-only diagnostics, and Phase 55 residual atomicity.
- **Dependency impact:** None.
- **Allowed writes:** `docs/SECURITY.md`, `docs/PRIVACY.md`, `docs/SAFETY.md`, `docs/MCP.md`, `docs/JSON_SCHEMA.md`, `docs/developer/debugging-guide.md`, `docs/maintainers/incident-and-security.md`, `docs/safety/privacy-and-data-handling.md`, `docs/safety/security-model.md`, `README.md`, `CHANGELOG.md`, `governance/remediation-phase-53.toml`, `governance/remediation-contracts.toml`, `governance/first-party-coverage.toml`, `docs/developer/phase-53-implementation-evidence.md`, `docs/developer/backlog.md`, `docs/developer/issues.md`, `docs/developer/testing-guide.md`, `docs/maintainers/release-playbook.md`.
- **Allowed reads:** passing tests and writer inventory.
- **Prohibited:** source/tests/dependencies or atomicity/schema claims.
- **Actions:** 1. Map claims to tests. 2. Update only named docs and record handoff API/error contract. 3. Run §10 and compare changed paths to task ownership.
- **Evidence:** docs diff, commands, handoff.
- **Stop:** unowned path or unsupported claim.
- **Verified outcome:** R-002/R-008 close; successors may consume sanitizer contract.

## 10. Final verification and delivery gate

```text
$env:VIRTUAL_ENV=$null
$env:PYTHONPATH=$null
.venv/Scripts/python.exe -m pytest tests/test_phase53_sanitizer_contract.py tests/test_phase53_output_boundaries.py tests/test_phase53_governance_writers.py tests/test_phase53_state_writers.py tests/test_phase53_logging_diagnostics.py -q
.venv/Scripts/python.exe -m pytest tests/ -q
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/ruff.exe format --check src tests scripts
git diff --check
git diff --name-only
git status --short --branch
```

## 11. Exit checklist and successor evidence

- [ ] All ordinary RED tests were recorded before their GREEN tasks; no skip/XFAIL/XPASS.
- [ ] Fresh sentinels are absent from values, keys, exceptions, public outputs, cache, completed and aborted artifacts.
- [ ] Semantic action inputs are byte/value identical.
- [ ] Exception logging emits one redacted stderr record; MCP stdout is JSON-RPC only.
- [ ] No dependency, roadmap, atomicity, or schema migration change.
- [ ] Every changed path belongs to one task.
