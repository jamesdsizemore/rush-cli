# Phase 60 implementation plan — non-release maintainability hotspot reduction

## 1. Purpose and status

- **Operation:** Create the implementation plan for remediation Phase 9.
- **Planning status:** Implementation-ready after §4 admission passes.
- **Implementation status:** Not authorized.
- **Authority:** governing roadmap R-015 and its locked non-release disposition.
- **Predecessor:** accepted Phase 59 release-readiness handoff closing R-001-R-014 and R-016, plus the current Phase 51 coverage manifest.
- **Release relationship:** Not a release prerequisite; required only for “remediation program complete.”
- **Behavior boundary:** No product behavior, public contract, operation identity, output, permission, compatibility, packaging, or release-policy change.
- **Protected:** dependencies/lockfile, public-operation and result contracts, release evidence, historical plans, and every path not named by a task.
- **Amendment rule:** A different metric/version/threshold, new destination, exemption, deletion, dependency, observable change, or path outside a card requires amendment before work continues.
- **Lifecycle boundary:** No commit, push, merge, tag, publish, release, hook installation, or history rewrite.

## 2. Authority, evidence, conflicts, and decisions

Authority order: user → `AGENTS.md` → governing roadmap → accepted Phase 51-59 contracts/evidence → this plan → current source/tests/docs.

Current evidence captured 2026-08-28 with `.venv/Scripts/ruff.exe 0.16.3` and `C901` at maximum complexity `10` identifies: `SessionContinuityTool.run` (14), `SessionContinuityTool._provider_resume` (13), `ReviewTool.run` (16), `LintTool.run` (12), `BlastRadiusAnalyzer.analyze` (15), `discover_workspaces` (23), and `DbDriftAuditor.audit_drift` (21). `src/rush/cli.py` and `src/rush/tools/common.py` are roadmap-named central modules but produce no top-level C901 finding; their completion contract is exact module ownership, not an invented metric.

Closed decisions:

- Metric is Ruff McCabe `C901`; executable is `.venv/Scripts/ruff.exe`; version is `0.16.3`; every retained and extracted target function must be `<= 10`.
- Exact metric command is `.venv/Scripts/ruff.exe check --select C901 --config "lint.mccabe.max-complexity = 10" --output-format concise` followed by the §8 production paths.
- Characterization tests pass before refactoring and remain unchanged through GREEN cards; they are evidence, not fake RED tests.
- Every extraction first receives an ordinary failing module-boundary/threshold test in a separate RED card. Skip, XFAIL, XPASS, commented, or non-executed tests never count.
- The eight existing target modules remain compatibility facades at their current import paths.
- No dead-code deletion is authorized. Any later deletion needs an amended card naming each symbol and its Phase 51 manifest, call-graph, and installed-probe evidence.
- No exemption is preapproved. `governance/maintainability-exemptions.toml` starts empty; adding one requires amendment with exact symbol, value, owner, rationale, compensating test, and expiry.

Open decisions: None.

## 3. Goals, outcomes, exclusions, and invariants

Outcomes: pin an immutable baseline; preserve behavior; reduce the seven Ruff findings to zero at threshold 10; move the named CLI/common concerns behind exact compatibility facades; retain green artifact, parity, security, persistence, provenance, engine, and release evidence; close R-015.

Exclusions: features, public renames, output/schema changes, dependency changes, release work, dead-code deletion, broad formatting, unrelated hotspot cleanup, and targets outside §6.

Invariants: CLI remains the Click composition root; stdio stdout remains JSON-RPC only; tools remain transport-independent; existing public imports/callables remain compatible; characterization compares structured behavior rather than private call order; each GREEN satisfies only its preceding RED; any correctness/release regression stops work.

## 4. Admission and predecessor gate

P60.0.1 starts only when Phase 59 records release readiness, installed wheel/sdist and all required release gates are green, `governance/first-party-coverage.toml` matches the revision, `.venv/Scripts/ruff.exe --version` returns exactly `ruff 0.16.3`, and unrelated worktree changes are inventoried. Otherwise no file may be written. A Ruff version mismatch requires amendment; the baseline may not be silently refreshed.

## 5. Requirement-ownership ledger

| Requirement | Tasks | Closure |
|---|---|---|
| Admission and immutable targets | P60.0.1, P60.1.2-P60.1.3 | exact C901 baseline and empty exemptions |
| Pre-refactor behavior oracle | P60.1.1 | characterization green before every move |
| CLI registration/options/rendering | P60.2.1-P60.2.2 | absent-module RED; installed CLI/parity GREEN |
| Continuity orchestration | P60.3.1-P60.3.2 | exact ownership and C901 GREEN |
| Review pipeline | P60.4.1-P60.4.2 | exact ownership/provider/result GREEN |
| Common runtime helpers | P60.5.1-P60.5.2 | compatibility re-export and subprocess/result GREEN |
| Traversal/state/lint | P60.6.1-P60.6.2 | exact ownership, deterministic behavior, zero C901 |
| Docs/program handoff | P60.7.1 | current ownership docs and R-015 closure |

## 6. Shared contracts and handoff

### 6.1 Exact metric targets

Final Ruff output has no finding for `SessionContinuityTool.run`, `SessionContinuityTool._provider_resume` if retained, `ReviewTool.run`, `LintTool.run`, `BlastRadiusAnalyzer.analyze`, `discover_workspaces`, or `DbDriftAuditor.audit_drift`. Every moved implementation function created below has the same threshold.

### 6.2 Exact ownership

- CLI: `src/rush/cli_support/options.py` owns `_extract_permissions` and `permission_options`; `catalog_commands.py` owns `build_catalog_path_command` and its callback construction; `rendering.py` owns `_run_tool` and `_render_session_result`; `src/rush/cli.py` imports/re-exports these names and remains composition root.
- Continuity: `context.py` owns `_context_pack`/`_context_retrieve`; `coordination.py` owns `_coordination_check`/`_coordination_merge_preview`/`_coordination_recovery`; `providers.py` owns `_provider_resume`/`_omniroute_resume`/`_provider_handoff`/`_windows_cmd_command`/`_provider_command`/`_provider_prompt`; `receipts.py` owns `_save_handoff_receipt`/`_restore_handoff_receipt`; `SessionContinuityTool` remains in `src/rush/tools/continuity.py`.
- Review: `collection.py` owns `_collect_reviewable_files`, `_read_file_safely`, all six existing heuristic/exclusion functions; `llm.py` owns `_maybe_call_llm`; `results.py` owns new `assemble_review_result`; `ReviewTool` remains in `src/rush/tools/review.py`.
- Runtime: `binaries.py` owns `_venv_scripts_dir`, `_resolve_binary_cached`, `clear_binary_cache`, `resolve_binary`, `engine_on_path`; `subprocesses.py` owns `_bounded_redacted_output`, `run_subprocess`, `run_engine`, `_install_hint`; `result_helpers.py` owns `skipped_result`, `error_result`, `_redact_finding_message`, `finding_fingerprint`, `normalize_findings`, `exit_code_for`, `now_ms`, `elapsed_ms`; `src/rush/tools/common.py` only re-exports compatibility names.
- Traversal/state/lint: `blast_radius_graph.py` owns new `build_reverse_import_graph`/`walk_impacted_paths`; `workspace_graph.py` owns new `discover_workspace_packages`/`topological_sort_workspace_packages`; `db_drift_rules.py` owns new `collect_models`/`collect_migrations`/`evaluate_drift`; `lint.py` gains private `_select_engines`/`_run_selected_engines`/`_assemble_lint_result`. Existing public facades remain in place.

Handoff records exact before/after C901 output, characterization/release-gate identities, zero exemptions, docs updated, and no product behavior change.

## 7. Contract-test inventory

| Contract | RED/evidence | GREEN | Exact ordinary tests |
|---|---|---|---|
| Characterization | P60.1.1 | retained throughout | `test_cli_catalog_options_rendering_characterization`; `test_continuity_dispatch_provider_receipt_characterization`; `test_review_collection_provider_result_characterization`; `test_common_subprocess_result_characterization`; `test_lint_and_traversal_state_characterization` |
| Baseline | P60.1.2 | P60.1.3 | `test_every_target_has_pinned_ruff_version_command_value_and_threshold`; `test_exemption_schema_requires_symbol_value_owner_rationale_test_and_expiry`; `test_phase60_starts_with_no_exemptions` |
| CLI | P60.2.1 | P60.2.2 | `test_cli_support_modules_own_exact_symbols`; `test_cli_compatibility_names_resolve_to_extracted_implementations` |
| Continuity | P60.3.1 | P60.3.2 | `test_continuity_modules_own_exact_symbols`; `test_continuity_facade_meets_c901_threshold` |
| Review | P60.4.1 | P60.4.2 | `test_review_modules_own_exact_symbols`; `test_review_facade_meets_c901_threshold` |
| Runtime/common | P60.5.1 | P60.5.2 | `test_runtime_modules_own_exact_symbols`; `test_common_is_compatibility_reexport_without_duplicate_definitions` |
| Traversal/state/lint | P60.6.1 | P60.6.2 | `test_traversal_state_modules_own_exact_symbols`; `test_all_phase60_facades_and_extracted_symbols_meet_c901_threshold` |

## 8. File, dependency, and documentation governance

New production/governance: `governance/maintainability-baseline.toml`, `governance/maintainability-exemptions.toml`, `src/rush/cli_support/__init__.py`, `src/rush/cli_support/catalog_commands.py`, `src/rush/cli_support/options.py`, `src/rush/cli_support/rendering.py`, `src/rush/continuity/__init__.py`, `src/rush/continuity/context.py`, `src/rush/continuity/coordination.py`, `src/rush/continuity/providers.py`, `src/rush/continuity/receipts.py`, `src/rush/review/__init__.py`, `src/rush/review/collection.py`, `src/rush/review/llm.py`, `src/rush/review/results.py`, `src/rush/runtime/__init__.py`, `src/rush/runtime/binaries.py`, `src/rush/runtime/subprocesses.py`, `src/rush/runtime/result_helpers.py`, `src/rush/tools/blast_radius_graph.py`, `src/rush/discovery/workspace_graph.py`, `src/rush/tools/db_drift_rules.py`.

New tests: `tests/test_phase60_characterization.py`, `tests/test_phase60_module_boundaries.py`, `tests/test_phase60_complexity_thresholds.py`.

Existing production/governance: `src/rush/cli.py`, `src/rush/tools/continuity.py`, `src/rush/tools/review.py`, `src/rush/tools/common.py`, `src/rush/tools/lint.py`, `src/rush/tools/blast_radius.py`, `src/rush/discovery/workspace.py`, `src/rush/tools/db_drift.py`, `src/rush/tools/__init__.py`, `src/rush/mcp.py`, `governance/remediation-contracts.toml`.

Existing tests: `tests/test_cli.py`, `tests/test_cli_registry.py`, `tests/test_mcp.py`, `tests/test_review.py`, `tests/test_subprocess_contract.py`, `tests/test_phase46_blast_radius_arch.py`, `tests/test_phase48_db_simplify_strict.py`, `tests/test_workspace.py`.

Docs owned only by P60.7.1: `docs/ARCHITECTURE.md`, `docs/developer/architecture.md`, `docs/developer/source-tree.md`, `docs/developer/coding-standards.md`, `docs/developer/tool-development.md`, `docs/maintainers/architecture-lifecycle.md`, `docs/KNOWN_ISSUES.md`.

All other writes prohibited. Dependency changes: None. Required existing tooling/contracts: `ruff==0.16.3`, the Phase 51 coverage manifest, and the accepted Phase 59 installed-artifact/parity/security/persistence/provenance/engine gates. `pyproject.toml` and `uv.lock` are prohibited.

## 9. Ordered workstreams and atomic task cards

### P60.0 — Admission

#### P60.0.1 — EVIDENCE: freeze predecessor state and targets

- **Task ID and binary outcome:** P60.0.1; every §4 gate and §6 target has one recorded identity/value/owner.
- **Start goal:** Prove correctness state and scope before writes.
- **Prerequisites:** §4.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** Phase 60 admission fields in `governance/remediation-contracts.toml`.
- **Allowed reads:** `governance/first-party-coverage.toml`, `governance/remediation-contracts.toml`, `docs/phase-plans/phase-59-provenance-engine-conformance-plan.md`, `src/rush/cli.py`, `src/rush/tools/continuity.py`, `src/rush/tools/review.py`, `src/rush/tools/common.py`, `src/rush/tools/lint.py`, `src/rush/tools/blast_radius.py`, `src/rush/discovery/workspace.py`, `src/rush/tools/db_drift.py`, `tests/test_cli.py`, `tests/test_cli_registry.py`, `tests/test_mcp.py`, `tests/test_review.py`, `tests/test_subprocess_contract.py`, `tests/test_phase46_blast_radius_arch.py`, `tests/test_phase48_db_simplify_strict.py`, `tests/test_workspace.py`, Git status/diff, Ruff version/output.
- **Prohibited:** source/tests/docs/dependencies/baseline/refactoring.
- **Actions:** 1. Inspect predecessor identities, overlap, §6 symbols, and public imports. 2. Record revision, Ruff version, exact seven values, CLI/common no-finding observation, and owners. 3. Re-run the exact command and compare the target set with the record.
- **Evidence:** admission record and exact target table.
- **Stop:** failed/missing gate, coverage/version/target drift, or overlapping edit.
- **Verified outcome:** P60.1.1 may start.

### P60.1 — Behavior oracle and metric governance

#### P60.1.1 — CHARACTERIZATION: freeze behavior before movement

- **Task ID and binary outcome:** P60.1.1; five characterization tests pass against unchanged production.
- **Start goal:** Create the behavior-preservation oracle.
- **Prerequisites:** P60.0.1.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase60_characterization.py`.
- **Allowed reads:** `src/rush/cli.py`, `src/rush/tools/continuity.py`, `src/rush/tools/review.py`, `src/rush/tools/common.py`, `src/rush/tools/lint.py`, `src/rush/tools/blast_radius.py`, `src/rush/discovery/workspace.py`, `src/rush/tools/db_drift.py`, `tests/test_cli.py`, `tests/test_cli_registry.py`, `tests/test_mcp.py`, `tests/test_review.py`, `tests/test_subprocess_contract.py`, `tests/test_phase46_blast_radius_arch.py`, `tests/test_phase48_db_simplify_strict.py`, `tests/test_workspace.py`.
- **Prohibited:** production/governance/docs/dependencies/XFAIL/bypassed assertions.
- **Actions:** 1. Inspect fixtures and behavior for each §7 row. 2. Add exactly five named tests with injected fakes and structured success/empty/error/denied assertions. 3. Run the new test plus all eight existing §8 tests and record green pre-refactor evidence.
- **Evidence:** green matrix tied to revision.
- **Stop:** nondeterministic or unobservable behavior; repair fixture scope before refactoring.
- **Verified outcome:** Every later GREEN retains this oracle.

#### P60.1.2 — RED: define baseline and exemption governance

- **Task ID and binary outcome:** P60.1.2; three tests fail because the governance files are absent.
- **Start goal:** Make completion immutable and machine-readable.
- **Prerequisites:** P60.1.1.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase60_complexity_thresholds.py` with only the three baseline tests.
- **Allowed reads:** Phase 60 admission fields in `governance/remediation-contracts.toml` and Phase 9 completion text in `docs/developer/repository-remediation-plan.md`.
- **Prohibited:** production/governance/docs/dependencies/XFAIL/skips/commented assertions.
- **Actions:** 1. Arrange exact expected version/command/targets/threshold and empty exemptions. 2. Add exactly three named tests and strict exemption fields. 3. Run focused and record missing-artifact failures.
- **Evidence:** ordinary RED output for all three.
- **Stop:** any test passes without both artifacts.
- **Verified outcome:** P60.1.3 may create only the governance files.

#### P60.1.3 — GREEN: commit immutable baseline

- **Task ID and binary outcome:** P60.1.3; baseline tests pass with exact values and zero exemptions.
- **Start goal:** Satisfy P60.1.2 only.
- **Prerequisites:** recorded P60.1.2 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `governance/maintainability-baseline.toml`, create `governance/maintainability-exemptions.toml`, modify `tests/test_phase60_complexity_thresholds.py`.
- **Allowed reads:** Phase 60 admission fields in `governance/remediation-contracts.toml` and `tests/test_phase60_complexity_thresholds.py`.
- **Prohibited:** production/docs/dependencies/exemption entries/version or threshold drift.
- **Actions:** 1. Reinspect expected schema/output. 2. Record revision, Ruff 0.16.3, exact command, symbols, values, threshold 10, owners, and empty exemptions. 3. Parse files, run focused tests and metric command, preserving current hotspot failures for later cards.
- **Evidence:** green governance tests and unchanged hotspot output.
- **Stop:** any recorded value differs from admission.
- **Verified outcome:** P60.2.1 may start.

### P60.2 — CLI boundary

#### P60.2.1 — RED: require exact CLI support ownership

- **Task ID and binary outcome:** P60.2.1; two tests fail because three support modules/owners do not exist.
- **Start goal:** Pin registration/options/rendering destinations and compatibility.
- **Prerequisites:** P60.1.3.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase60_module_boundaries.py` with only the two CLI tests.
- **Allowed reads:** `src/rush/cli.py`, `tests/test_cli.py`, `tests/test_cli_registry.py`, `tests/test_mcp.py`, `governance/public-operations.toml`.
- **Prohibited:** production/governance/docs/dependencies/XFAIL.
- **Actions:** 1. Arrange exact CLI modules/symbols/imports. 2. Add two tests asserting defining module, compatibility identity, command names/options/defaults, and no duplicate implementation. 3. Run focused and record absent-module/ownership failures.
- **Evidence:** two-test RED and symbol table.
- **Stop:** test asserts private registration order instead of public behavior.
- **Verified outcome:** P60.2.2 may create support modules/edit facade.

#### P60.2.2 — GREEN: extract registration, options, and rendering

- **Task ID and binary outcome:** P60.2.2; boundary, characterization, installed CLI, registry, and parity tests pass.
- **Start goal:** Satisfy P60.2.1 only.
- **Prerequisites:** recorded P60.2.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `src/rush/cli_support/__init__.py`, `src/rush/cli_support/catalog_commands.py`, `src/rush/cli_support/options.py`, `src/rush/cli_support/rendering.py`; modify `src/rush/cli.py`, `tests/test_phase60_module_boundaries.py`, `tests/test_cli.py`, `tests/test_cli_registry.py`, `tests/test_mcp.py`.
- **Allowed reads:** `tests/test_phase60_module_boundaries.py`, `tests/test_phase60_characterization.py`, `src/rush/tools/__init__.py`, `src/rush/mcp.py`, `governance/public-operations.toml`.
- **Prohibited:** other callback moves, observable/public changes, docs/dependencies.
- **Actions:** 1. Reinspect exact four definitions/callers. 2. Move only §6 CLI definitions and import/re-export them from CLI. 3. Run boundary/characterization/registry/parity/installed probes and metric command.
- **Evidence:** green ownership and unchanged snapshots/probes.
- **Stop:** command, option, default, exit, stdout/stderr, permission, operation ID, or installed import differs.
- **Verified outcome:** P60.3.1 may start.

### P60.3 — Continuity boundary

#### P60.3.1 — RED: require exact continuity ownership and threshold

- **Task ID and binary outcome:** P60.3.1; two tests fail on absent modules/current findings.
- **Start goal:** Pin context/coordination/provider/receipt ownership.
- **Prerequisites:** P60.2.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** modify `tests/test_phase60_module_boundaries.py`, modify `tests/test_phase60_complexity_thresholds.py` with only two continuity tests.
- **Allowed reads:** `src/rush/tools/continuity.py`, `tests/test_phase60_characterization.py`, `tests/test_phase58_lock_capabilities.py`, `tests/test_phase58_checkpoint_journals.py`, `governance/remediation-contracts.toml`.
- **Prohibited:** production/governance/docs/dependencies/XFAIL.
- **Actions:** 1. Arrange every exact continuity symbol and threshold. 2. Add ownership/compatibility/C901 tests. 3. Run focused and record failures.
- **Evidence:** ordinary RED and ownership table.
- **Stop:** unspecified destination or uncovered behavior.
- **Verified outcome:** P60.3.2 may create continuity modules/edit facade.

#### P60.3.2 — GREEN: extract continuity orchestration

- **Task ID and binary outcome:** P60.3.2; ownership/threshold tests pass with unchanged behavior.
- **Start goal:** Satisfy P60.3.1 only.
- **Prerequisites:** recorded P60.3.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `src/rush/continuity/__init__.py`, `src/rush/continuity/context.py`, `src/rush/continuity/coordination.py`, `src/rush/continuity/providers.py`, `src/rush/continuity/receipts.py`; modify `src/rush/tools/continuity.py`, `tests/test_phase60_module_boundaries.py`, `tests/test_phase60_complexity_thresholds.py`.
- **Allowed reads:** `tests/test_phase60_module_boundaries.py`, `tests/test_phase60_complexity_thresholds.py`, `tests/test_phase60_characterization.py`, `tests/test_phase58_lock_capabilities.py`, `tests/test_phase58_checkpoint_journals.py`, `tests/test_cli.py`, `tests/test_mcp.py`.
- **Prohibited:** provider/origin/permission/receipt/persistence/public-import changes, docs/dependencies.
- **Actions:** 1. Reinspect helper inputs/results/side effects. 2. Move only exact continuity behavior with explicit dependencies; retain facade/result assembly and meet threshold. 3. Run boundary/threshold/characterization/Phase 58/CLI/MCP/metric.
- **Evidence:** green ownership/C901 and unchanged results/receipts.
- **Stop:** permission, provider command, receipt bytes, status, finding, artifact, or transport output differs.
- **Verified outcome:** P60.4.1 may start.

### P60.4 — Review boundary

#### P60.4.1 — RED: require exact review ownership and threshold

- **Task ID and binary outcome:** P60.4.1; two tests fail on absent review package/current finding.
- **Start goal:** Pin collection/LLM/result destinations.
- **Prerequisites:** P60.3.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** modify `tests/test_phase60_module_boundaries.py`, modify `tests/test_phase60_complexity_thresholds.py` with only two review tests.
- **Allowed reads:** `src/rush/tools/review.py`, `tests/test_review.py`, `tests/test_phase60_characterization.py`, `tests/test_phase57_provider_egress.py`, `tests/test_phase54_result_schema.py`, `governance/public-operations.toml`.
- **Prohibited:** production/governance/docs/dependencies/XFAIL.
- **Actions:** 1. Arrange exact review symbols/outcomes/fields. 2. Add defining-module, compatibility, and threshold tests. 3. Run focused and record failures.
- **Evidence:** ordinary RED and ownership table.
- **Stop:** provider/result behavior lacks characterization.
- **Verified outcome:** P60.4.2 may create review modules/edit facade.

#### P60.4.2 — GREEN: extract collection, LLM, and result assembly

- **Task ID and binary outcome:** P60.4.2; ownership/C901/provider/result tests pass.
- **Start goal:** Satisfy P60.4.1 only.
- **Prerequisites:** recorded P60.4.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `src/rush/review/__init__.py`, `src/rush/review/collection.py`, `src/rush/review/llm.py`, `src/rush/review/results.py`; modify `src/rush/tools/review.py`, `tests/test_phase60_module_boundaries.py`, `tests/test_phase60_complexity_thresholds.py`, `tests/test_review.py`.
- **Allowed reads:** `tests/test_phase60_module_boundaries.py`, `tests/test_phase60_complexity_thresholds.py`, `tests/test_phase60_characterization.py`, `tests/test_phase53_sanitizer_contract.py`, `tests/test_phase54_result_schema.py`, `tests/test_phase57_provider_egress.py`, `governance/public-operations.toml`.
- **Prohibited:** heuristic/provider/output/permission behavior changes, docs/dependencies.
- **Actions:** 1. Reinspect collection, heuristic, provider, and result branches. 2. Move exact definitions, add pure `assemble_review_result`, retain facade, meet threshold. 3. Run boundary/threshold/characterization/review/provider/sanitizer/result/parity/metric.
- **Evidence:** green ownership/C901/provider/result matrix.
- **Stop:** ordering, finding/fingerprint, review_kind, origin, status, or serialized result differs.
- **Verified outcome:** P60.5.1 may start.

### P60.5 — Runtime/common boundary

#### P60.5.1 — RED: require exact runtime ownership and compatibility

- **Task ID and binary outcome:** P60.5.1; two tests fail because runtime owners do not exist.
- **Start goal:** Pin binary/subprocess/result destinations without changing imports.
- **Prerequisites:** P60.4.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** modify `tests/test_phase60_module_boundaries.py` with only two runtime/common tests.
- **Allowed reads:** `src/rush/tools/common.py`, `tests/test_subprocess_contract.py`, `tests/test_static_tools.py`, `tests/test_phase53_sanitizer_contract.py`, `tests/test_phase54_result_schema.py`, `tests/test_phase57_cache_policy.py`.
- **Prohibited:** production/governance/docs/dependencies/XFAIL.
- **Actions:** 1. Arrange every runtime symbol/caller/import. 2. Add defining-module, re-export identity, and zero-duplicate-body assertions. 3. Run focused and record failures.
- **Evidence:** ordinary RED and caller/import table.
- **Stop:** any dynamic/public caller cannot preserve import behavior.
- **Verified outcome:** P60.5.2 may create runtime modules/edit common.

#### P60.5.2 — GREEN: extract binary, subprocess, and result helpers

- **Task ID and binary outcome:** P60.5.2; ownership and every common import behave identically.
- **Start goal:** Satisfy P60.5.1 only.
- **Prerequisites:** recorded P60.5.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `src/rush/runtime/__init__.py`, `src/rush/runtime/binaries.py`, `src/rush/runtime/subprocesses.py`, `src/rush/runtime/result_helpers.py`; modify `src/rush/tools/common.py`, `src/rush/tools/__init__.py`, `tests/test_phase60_module_boundaries.py`, `tests/test_subprocess_contract.py`.
- **Allowed reads:** `tests/test_phase60_module_boundaries.py`, `tests/test_phase60_characterization.py`, `tests/test_subprocess_contract.py`, `tests/test_static_tools.py`, `tests/test_phase53_sanitizer_contract.py`, `tests/test_phase54_result_schema.py`, `tests/test_phase57_cache_policy.py`, `graft/INDEX.md`.
- **Prohibited:** caller-wide rewrites, sanitizer/result/engine changes, docs/dependencies.
- **Actions:** 1. Reinspect each helper/caller using Graft/CodeGraph evidence. 2. Move exact definitions and re-export identical objects without duplicate bodies. 3. Run boundary/characterization/subprocess/engine/sanitizer/result/cache/full tests and metric.
- **Evidence:** green ownership/import identity, subprocess/result matrix, no cycle.
- **Stop:** resolution, environment, timeout, redaction, status, normalization, fingerprint, cache identity, or import differs.
- **Verified outcome:** P60.6.1 may start.

### P60.6 — Traversal, state, and lint

#### P60.6.1 — RED: require exact ownership and zero C901 findings

- **Task ID and binary outcome:** P60.6.1; two tests fail on absent modules/current findings.
- **Start goal:** Pin graph/workspace/drift/lint decomposition.
- **Prerequisites:** P60.5.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** modify `tests/test_phase60_module_boundaries.py`, modify `tests/test_phase60_complexity_thresholds.py` with only two traversal/state tests.
- **Allowed reads:** `src/rush/tools/blast_radius.py`, `src/rush/discovery/workspace.py`, `src/rush/tools/db_drift.py`, `src/rush/tools/lint.py`, `tests/test_phase46_blast_radius_arch.py`, `tests/test_phase48_db_simplify_strict.py`, `tests/test_workspace.py`, `tests/test_static_tools.py`, `tests/test_phase60_characterization.py`.
- **Prohibited:** production/governance/docs/dependencies/XFAIL.
- **Actions:** 1. Arrange exact symbols and deterministic empty/error/order cases. 2. Add ownership and all-target threshold tests. 3. Run focused and record missing-module/C901 failures.
- **Evidence:** ordinary RED with exact symbol/finding list.
- **Stop:** any output/order/error branch lacks characterization.
- **Verified outcome:** P60.6.2 may create three modules/refactor four facades.

#### P60.6.2 — GREEN: decompose traversal/state and lint

- **Task ID and binary outcome:** P60.6.2; metric reports zero findings and behavior is unchanged.
- **Start goal:** Satisfy P60.6.1 only.
- **Prerequisites:** recorded P60.6.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `src/rush/tools/blast_radius_graph.py`, `src/rush/discovery/workspace_graph.py`, `src/rush/tools/db_drift_rules.py`; modify `src/rush/tools/blast_radius.py`, `src/rush/discovery/workspace.py`, `src/rush/tools/db_drift.py`, `src/rush/tools/lint.py`, `tests/test_phase60_module_boundaries.py`, `tests/test_phase60_complexity_thresholds.py`, `tests/test_phase46_blast_radius_arch.py`, `tests/test_phase48_db_simplify_strict.py`, `tests/test_workspace.py`.
- **Allowed reads:** `tests/test_phase60_module_boundaries.py`, `tests/test_phase60_complexity_thresholds.py`, `tests/test_phase60_characterization.py`, `tests/test_phase46_blast_radius_arch.py`, `tests/test_phase48_db_simplify_strict.py`, `tests/test_workspace.py`, `tests/test_static_tools.py`, `governance/public-operations.toml`.
- **Prohibited:** model/output/order/error/engine-selection changes, docs/dependencies/deletion.
- **Actions:** 1. Reinspect every branch/characterized output. 2. Extract exact pure traversal/rule functions, create exact lint helpers, retain facades, meet threshold. 3. Run boundary/threshold/characterization/existing/lint-engine/parity/full tests and metric.
- **Evidence:** zero C901 and unchanged graph/workspace/drift/lint matrices.
- **Stop:** depth/order, workspace identity, drift class, engine selection/aggregation, status, or output differs.
- **Verified outcome:** P60.7.1 may start.

### P60.7 — Documentation and program handoff

#### P60.7.1 — VERIFY/DOCS/HANDOFF: close R-015 and the program

- **Task ID and binary outcome:** P60.7.1; §10 passes, docs name current ownership, and R-015 closes with zero exemptions.
- **Start goal:** Publish only verified maintainability changes/program completion.
- **Prerequisites:** P60.1.1-P60.6.2 green and empty exemptions.
- **Documentation impact:** all seven §8 docs.
- **Dependency impact:** None.
- **Allowed writes:** `docs/ARCHITECTURE.md`, `docs/developer/architecture.md`, `docs/developer/source-tree.md`, `docs/developer/coding-standards.md`, `docs/developer/tool-development.md`, `docs/maintainers/architecture-lifecycle.md`, `docs/KNOWN_ISSUES.md`, and Phase 60/R-015/program evidence fields in `governance/remediation-contracts.toml`.
- **Allowed reads:** `governance/remediation-contracts.toml`, `governance/maintainability-baseline.toml`, `governance/maintainability-exemptions.toml`, `governance/first-party-coverage.toml`, `docs/phase-plans/phase-51-remediation-scope-release-gates-plan.md`, `docs/phase-plans/phase-52-packaging-artifact-version-contract-plan.md`, `docs/phase-plans/phase-53-sanitization-diagnostics-write-boundaries-plan.md`, `docs/phase-plans/phase-54-tool-result-schema-kernel-plan.md`, `docs/phase-plans/phase-55-atomic-file-physical-containment-plan.md`, `docs/phase-plans/phase-56-content-addressed-plugin-trust-plan.md`, `docs/phase-plans/phase-57-invocation-scope-operations-cache-egress-plan.md`, `docs/phase-plans/phase-58-lock-persistence-patch-fail-closed-plan.md`, `docs/phase-plans/phase-59-provenance-engine-conformance-plan.md`, Git diff/status.
- **Prohibited:** source/tests/dependencies/exemptions/release/historical-plan rewrites.
- **Actions:** 1. Compare ownership, Ruff, gates, paths, and exemptions with §§5-8. 2. Update docs, remove R-015 only after closure, and record before/after plus no-behavior-change handoff. 3. Run §10, coverage-scope docs, and map every changed path to one card.
- **Evidence:** docs diff, zero-exemption comparison, verification transcript, program handoff.
- **Stop:** threshold/gate failure, exemption, unowned path, or unsupported claim.
- **Verified outcome:** R-015 and the remediation program are complete; release readiness remains Phase 59 state.

## 10. Final verification and delivery gate

```text
$env:VIRTUAL_ENV=$null
$env:PYTHONPATH=$null
.venv/Scripts/python.exe -m pytest tests/test_phase60_characterization.py tests/test_phase60_module_boundaries.py tests/test_phase60_complexity_thresholds.py -q
.venv/Scripts/python.exe -m pytest tests/test_cli.py tests/test_cli_registry.py tests/test_mcp.py tests/test_review.py tests/test_subprocess_contract.py tests/test_phase46_blast_radius_arch.py tests/test_phase48_db_simplify_strict.py tests/test_workspace.py -q
.venv/Scripts/python.exe -m pytest tests/ -q
.venv/Scripts/ruff.exe check --select C901 --config "lint.mccabe.max-complexity = 10" --output-format concise src/rush/cli.py src/rush/tools/continuity.py src/rush/tools/review.py src/rush/tools/common.py src/rush/tools/lint.py src/rush/tools/blast_radius.py src/rush/discovery/workspace.py src/rush/tools/db_drift.py src/rush/cli_support src/rush/continuity src/rush/review src/rush/runtime src/rush/tools/blast_radius_graph.py src/rush/discovery/workspace_graph.py src/rush/tools/db_drift_rules.py
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/ruff.exe format --check src tests scripts
.venv/Scripts/python.exe scripts/probe_installed_artifacts.py
git diff --check
git diff --name-only
git status --short --branch
```

Reuse accepted Phase 59 installed wheel/sdist, public-operation, semantic parity, sanitizer, security, persistence, provenance, and fixed-PATH engine commands/evidence. If their exact scripts/paths differ from the handoff, stop and amend; do not invent replacements.

## 11. Exit checklist and successor evidence

- [ ] Phase 59 release readiness/current Phase 51 coverage admitted Phase 60.
- [ ] Characterization passed before movement and stayed green.
- [ ] Every extraction has separate ordinary RED then bounded GREEN.
- [ ] No skip/XFAIL/XPASS/comment/non-executed RED evidence.
- [ ] Ruff 0.16.3, exact command, values, threshold 10, zero exemptions recorded.
- [ ] Exact metric reports zero findings for retained/extracted targets.
- [ ] CLI/common ownership passes without duplicate implementation or changed imports.
- [ ] Continuity/review/traversal/state/lint preserve structured behavior.
- [ ] Installed artifacts and accepted correctness/release gates remain green.
- [ ] No dependency, public contract, behavior, deletion, exemption, release, or lifecycle action.
- [ ] Every changed path belongs to exactly one task.
- [ ] R-015/program completion are evidence-backed.
