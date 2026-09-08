# Phase 60 Implementation Plan: Non-Release Maintainability Hotspot Reduction and Remediation Program Completion

## 1. Purpose and Status

- **Operation:** Comprehensive implementation plan for Phase 60 maintainability hotspot reduction and final remediation program completion.
- **Planning Status:** Implementation-ready; deeply reviewed against repo codebase, current development baseline, and governing contracts.
- **Implementation Status:** Authorized for strict TDD execution.
- **Authority:** Governing Roadmap finding R-015 ("Maintainability hotspots in central transport and orchestration modules") in `governance/remediation-contracts.toml` and Phase 9 (Slice 10) in `docs/developer/repository-remediation-plan.md`.
- **Predecessors:** Accepted Phase 59 release-readiness handoff closing all 15 release-blocking findings (R-001 through R-014, and R-016), plus the active Phase 51 coverage manifest (`governance/first-party-coverage.toml`), public operations manifest (`governance/public-operations.toml`), and engine taxonomy (`governance/engine-support.toml`).
- **Release Relationship:** Non-release prerequisite; required exclusively for "remediation program complete" milestone. Release readiness is already established by Phase 59.
- **Behavior Boundary:** Strictly ZERO product behavior, public contract, operation identity, output schema, permission, compatibility, packaging, or release-policy change. Every existing public CLI command, MCP tool, configuration key, and library import path must remain 100% functional via compatibility facades.
- **Protected Boundaries:** Dependencies and lockfile (`pyproject.toml`, `uv.lock`), public-operation contracts (`ToolResultV1`, `FindingV1`), release evidence, historical plans, and all source paths outside the explicit §8 write set.
- **Amendment Rule:** Any alteration to metrics, tooling version, thresholds, destination packages, exemptions, deletions, dependencies, observable behaviors, or paths outside the §8 card inventory requires an explicit plan amendment before work proceeds.
- **Zero-Downscope Invariant:** This plan is the immutable contract. Stubs returning `"unknown"`, `"deferred"`, simulated metric reductions, or permissive assertions (`assert status in (...)`) are strictly prohibited. The algorithmic and structural refactoring must be genuinely implemented.
- **Lifecycle Boundary:** No unprompted commit, push, merge, tag, publish, release, hook installation, or history rewrite.

---

## 2. Authority, Predecessor Artifacts, Concrete Baseline, and Semantic Drift Identification

Authority order: User instructions -> `AGENTS.md` -> Governing Roadmap (`governance/remediation-contracts.toml` / `docs/developer/repository-remediation-plan.md`) -> Accepted Phase 51-59 contracts and evidence -> This implementation plan -> Current source, tests, and documentation.

### 2.1 Concrete Codebase Audit & Baseline Measurement

An audit of the repository as of 2026-09-05/06 using the project environment (`.venv/Scripts/python.exe`, Python 3.12.13) and `.venv/Scripts/ruff.exe 0.16.3` with McCabe `C901` at threshold `10`:
Command:
```bash
.venv/Scripts/ruff.exe check --select C901 --config "lint.mccabe.max-complexity = 10" --output-format concise src/rush/cli.py src/rush/mcp.py src/rush/tools/continuity.py src/rush/tools/review.py src/rush/tools/common.py src/rush/tools/lint.py src/rush/tools/blast_radius.py src/rush/discovery/workspace.py src/rush/tools/db_drift.py
```

Produces the exact starting maintainability hotspot baseline:
1. `src/rush/discovery/workspace.py:28:5: C901 discover_workspaces is too complex (23 > 10)`
2. `src/rush/tools/blast_radius.py:26:9: C901 analyze is too complex (15 > 10)`
3. `src/rush/tools/continuity.py:125:9: C901 run is too complex (18 > 10)`
4. `src/rush/tools/continuity.py:686:9: C901 _provider_resume is too complex (13 > 10)`
5. `src/rush/tools/db_drift.py:15:9: C901 audit_drift is too complex (21 > 10)`
6. `src/rush/tools/lint.py:42:9: C901 run is too complex (12 > 10)`
7. `src/rush/tools/review.py:57:9: C901 run is too complex (16 > 10)`
8. `src/rush/mcp.py:318:5: C901 _register_tools is too complex (16 > 10)`

Additionally:
- `src/rush/cli.py` contains 3,303 lines comprising Click CLI composition, permission extraction, catalog command builders, and terminal rendering.
- `src/rush/tools/common.py` contains 534 lines comprising binary resolution, caching, subprocess execution, engine error mapping, and result normalization helpers.

### 2.2 Semantic Drift Identification & Corrections

A deep review of the prior plan draft against the current codebase identified four significant gaps and semantic drifts:

1. **Drift 1: Missing `src/rush/mcp.py` Transport Deconstruction (R-015 Scope Violation)**:
   - *Issue:* In `governance/remediation-contracts.toml`, finding R-015 specifies `target_seam = "src/rush/cli.py, src/rush/mcp.py"` and title "Maintainability hotspots in central transport and orchestration modules". The prior plan draft omitted `src/rush/mcp.py` from refactoring. In current development, `src/rush/mcp.py:318 (_register_tools)` has a C901 complexity of **16 > 10** due to inline tool wrapper definitions, signature binding, and custom tool handlers added during Phases 57 and 58.
   - *Correction:* Include `src/rush/mcp.py` in the transport boundary workstream (P60.2). Modularize `_register_tools` by extracting tool wrapping, parameter binding, and custom tool registration into `src/rush/mcp_support/tool_registry.py` (or private modular helpers), ensuring `src/rush/mcp.py` achieves C901 <= 10 across all functions while maintaining stdio-only JSON-RPC transport integrity.

2. **Drift 2: Outdated Complexity Baseline for `continuity.py`**:
   - *Issue:* The prior draft recorded `SessionContinuityTool.run` at complexity 14 based on an August 2026 snapshot. In current development, `SessionContinuityTool.run` is complexity **18** due to Phase 58 capability token validation and CAS persistence dispatching.
   - *Correction:* Update baseline evidence to reflect the actual current score of 18, and ensure the extraction of `src/rush/continuity/` modules brings `run()` to <= 10.

3. **Drift 3: Missing R-015 Contract Test File Alignment**:
   - *Issue:* `governance/remediation-contracts.toml` declares:
     `test_file = "tests/test_phase60_refactor.py"`
     `test_function = "test_hotspot_complexity_and_modularity_reduction"`
     The prior plan draft defined three test files (`test_phase60_characterization.py`, `test_phase60_module_boundaries.py`, `test_phase60_complexity_thresholds.py`), but lacked `tests/test_phase60_refactor.py`.
   - *Correction:* Add `tests/test_phase60_refactor.py` (implementing or importing `test_hotspot_complexity_and_modularity_reduction`) to verify the overarching R-015 contract across all 8 target modules/functions, reconciling directly with `governance/remediation-contracts.toml`.

4. **Drift 4: Missing Implementation Evidence & Phase 60 Manifest**:
   - *Issue:* Phases 50 through 59 uniformly produced:
     - `docs/developer/phase-<N>-implementation-evidence.md`
     - `governance/remediation-phase-<N>.toml`
     The prior plan draft omitted both files from allowed writes and deliverables.
   - *Correction:* Add `docs/developer/phase-60-implementation-evidence.md` (started in P60.0.1, finalized in P60.7.1) and `governance/remediation-phase-60.toml` (created in P60.7.1) to formalize program completion.

5. **Drift 5: Incomplete Documentation Audit Scope**:
   - *Issue:* The prior draft listed only 7 documentation files for P60.7.1, ignoring the root governing document (`docs/developer/repository-remediation-plan.md`), phase index (`docs/phase-plans/README.md`), debugging guide, contributor onboarding, and subfolder verification.
   - *Correction:* Identify and categorize ALL 351 markdown documents across `/docs` and all subfolders, establishing an exhaustive 5-group ledger with explicit update specifications.

---

## 3. Goals, Non-Goals, Operational Exclusions, and Invariants

### 3.1 Primary Goals

1. **Characterization Oracle**: Establish a comprehensive, immutable pre-refactoring characterization test suite (`tests/test_phase60_characterization.py`) proving 100% behavior preservation across all target domains before any production code is modified.
2. **Machine-Readable Baseline & Exemption Governance**: Commit `governance/maintainability-baseline.toml` recording the exact current metrics and `governance/maintainability-exemptions.toml` with strictly ZERO exemptions.
3. **Transport Boundary Deconstruction**:
   - Extract CLI permission options, catalog command construction, and terminal rendering from `src/rush/cli.py` into `src/rush/cli_support/`.
   - Extract MCP tool registration and parameter adaptation from `src/rush/mcp.py` into `src/rush/mcp_support/tool_registry.py` (or modular helper functions).
   - Retain `src/rush/cli.py` as the Click composition root and `src/rush/mcp.py` as the FastMCP stdio server root, with full backward compatibility.
4. **Continuity Boundary Deconstruction**: Extract context packing/retrieval, multi-agent coordination, provider resumption, and handoff receipts from `src/rush/tools/continuity.py` into `src/rush/continuity/`, reducing `SessionContinuityTool.run` (18 -> <= 10) and `_provider_resume` (13 -> <= 10).
5. **Review Pipeline Deconstruction**: Extract file collection/heuristics, LLM egress integration, and review result assembly from `src/rush/tools/review.py` into `src/rush/review/`, reducing `ReviewTool.run` (16 -> <= 10).
6. **Runtime & Common Helpers Deconstruction**: Extract binary resolution, subprocess execution, and result normalization from `src/rush/tools/common.py` into `src/rush/runtime/`, retaining `src/rush/tools/common.py` as a 100% compatibility facade re-exporting identical object identities.
7. **Traversal, State, and Lint Deconstruction**:
   - Extract reverse import graph and reachability traversal from `src/rush/tools/blast_radius.py` into `src/rush/tools/blast_radius_graph.py`, reducing `analyze` (15 -> <= 10).
   - Extract monorepo package discovery and topological sorting from `src/rush/discovery/workspace.py` into `src/rush/discovery/workspace_graph.py`, reducing `discover_workspaces` (23 -> <= 10).
   - Extract ORM model scanning, migration column extraction, and drift evaluation from `src/rush/tools/db_drift.py` into `src/rush/tools/db_drift_rules.py`, reducing `audit_drift` (21 -> <= 10).
   - Decompose `LintTool.run` in `src/rush/tools/lint.py` into modular helpers (`_select_engines`, `_run_selected_engines`, `_assemble_lint_result`), reducing `run` (12 -> <= 10).
8. **Final Remediation Program Completion**: Synchronize all documentation, create `governance/remediation-phase-60.toml`, mark R-015 `completed` in `governance/remediation-contracts.toml`, record final evidence in `docs/developer/phase-60-implementation-evidence.md`, and mark the entire remediation program 100% complete in `docs/developer/repository-remediation-plan.md`.

### 3.2 Non-Goals and Operational Exclusions

1. **Zero Product Behavior Changes**: No changes to CLI command syntax, option defaults, exit codes, MCP tool names, parameter schemas, result shapes, or logging formats.
2. **Zero Dependency Changes**: No additions, removals, or updates in `pyproject.toml` or `uv.lock`.
3. **No Dead Code Deletion**: All public and internal symbols remain accessible at their legacy import locations via re-exports.
4. **No Code Formatting Churn**: Formatting changes are strictly bounded to touched files.
5. **No Release Re-scoping**: Release readiness remains anchored to Phase 59. Phase 60 does not alter release status.

### 3.3 Core Invariants

1. **Click Composition Invariant**: `src/rush/cli.py` remains the single composition root for the CLI; all command callbacks remain callable via Click.
2. **Stdio Transport Invariant**: `src/rush/mcp.py` stdout remains strictly JSON-RPC; diagnostics and logs write exclusively to stderr.
3. **Re-Export Identity Invariant**: All symbols re-exported from `src/rush/tools/common.py` and other compatibility facades must satisfy `is` identity checks against their extracted implementations (`assert rush.tools.common.resolve_binary is rush.runtime.binaries.resolve_binary`).
4. **Strict C901 Budget**: Every extracted function and every modified existing function must strictly achieve McCabe cyclomatic complexity <= 10.
5. **Zero Exemptions Invariant**: `governance/maintainability-exemptions.toml` must remain completely empty.

---

## 4. Admission Gate and Predecessor Verification

Workstream P60.0.1 may start only when all of the following conditions are verified:
1. `governance/remediation-phase-59.toml` is present with `status = "completed"` and all 26 contract tests passing.
2. Clean test suite baseline of 1,189 passed tests, 0 warnings (`.venv/Scripts/python.exe -m pytest tests/ -q`).
3. Clean lint and format status across all 732 files (`.venv/Scripts/ruff.exe check src tests scripts` and `ruff format --check`).
4. Installed package artifact probe passes on wheel and sdist (`.venv/Scripts/python.exe scripts/probe_installed_artifacts.py`).
5. Tooling verification: `.venv/Scripts/ruff.exe --version` returns exactly `ruff 0.16.3`.
6. Git working tree is clean on the dedicated feature branch (`phase-60-maintainability-hotspot-reduction`).

---

## 5. Requirement-Ownership Ledger (R-015)

| Requirement ID | Finding Summary | Workstreams | Specific Contract Outcomes |
|---|---|---|---|
| **R-015** | Maintainability hotspots in central transport and orchestration modules | P60.0, P60.1, P60.2, P60.3, P60.4, P60.5, P60.6, P60.7 | 1. Characterization test suite (`tests/test_phase60_characterization.py`) freezing pre-refactor behavior.<br>2. Machine-readable baseline (`governance/maintainability-baseline.toml`) and zero exemptions (`governance/maintainability-exemptions.toml`).<br>3. Modular decomposition of `cli.py` and `mcp.py` into `src/rush/cli_support/` and `src/rush/mcp_support/`.<br>4. Modular decomposition of `continuity.py` into `src/rush/continuity/`.<br>5. Modular decomposition of `review.py` into `src/rush/review/`.<br>6. Modular decomposition of `common.py` into `src/rush/runtime/`.<br>7. Modular extraction of graph/rules for `blast_radius.py`, `workspace.py`, `db_drift.py`, and `lint.py`.<br>8. Zero C901 findings at threshold 10 across all 8 target functions/methods and all extracted symbols.<br>9. Contract test `tests/test_phase60_refactor.py` (`test_hotspot_complexity_and_modularity_reduction`) passing.<br>10. Full remediation program completion and `/docs` synchronization. |

---

## 6. Shared Contracts, Exact Target Inventory, and Destination Mapping

### 6.1 Exact Metric Target Inventory

| Target File | Target Symbol | Baseline C901 | Target C901 | Extracted Destination / Strategy |
|---|---|:---:|:---:|---|
| `src/rush/discovery/workspace.py` | `discover_workspaces` | 23 | <= 10 | Extract `discover_workspace_packages` and `topological_sort_workspace_packages` into `src/rush/discovery/workspace_graph.py`. |
| `src/rush/tools/blast_radius.py` | `BlastRadiusAnalyzer.analyze` | 15 | <= 10 | Extract `build_reverse_import_graph` and `walk_impacted_paths` into `src/rush/tools/blast_radius_graph.py`. |
| `src/rush/tools/continuity.py` | `SessionContinuityTool.run` | 18 | <= 10 | Extract operation dispatch to `src/rush/continuity/` modules (`context.py`, `coordination.py`, `providers.py`, `receipts.py`). |
| `src/rush/tools/continuity.py` | `SessionContinuityTool._provider_resume` | 13 | <= 10 | Extract command assembly, prompt construction, and launcher logic to `src/rush/continuity/providers.py`. |
| `src/rush/tools/db_drift.py` | `DbDriftAuditor.audit_drift` | 21 | <= 10 | Extract `collect_models`, `collect_migrations`, and `evaluate_drift` into `src/rush/tools/db_drift_rules.py`. |
| `src/rush/tools/lint.py` | `LintTool.run` | 12 | <= 10 | Decompose into private helpers `_select_engines`, `_run_selected_engines`, and `_assemble_lint_result`. |
| `src/rush/tools/review.py` | `ReviewTool.run` | 16 | <= 10 | Extract collection to `src/rush/review/collection.py`, LLM egress to `src/rush/review/llm.py`, and result building to `src/rush/review/results.py`. |
| `src/rush/mcp.py` | `_register_tools` | 16 | <= 10 | Extract `_make_tool_wrapper`, `_make_custom_handler`, and `_make_custom_wrapper` into `src/rush/mcp_support/tool_registry.py` (or private modular helpers). |
| `src/rush/cli.py` | Central CLI module (3,303 lines) | N/A | N/A | Extract `options.py`, `catalog_commands.py`, and `rendering.py` into `src/rush/cli_support/`. `cli.py` re-exports all symbols. |
| `src/rush/tools/common.py` | Central runtime module (535 lines) | N/A | N/A | Extract `binaries.py`, `subprocesses.py`, and `result_helpers.py` into `src/rush/runtime/`. `common.py` re-exports all symbols. |

### 6.2 Exact Module Ownership & Symbol Allocation

1. **CLI Transport**:
   - `src/rush/cli_support/options.py`: `_extract_permissions`, `permission_options`.
   - `src/rush/cli_support/catalog_commands.py`: `build_catalog_path_command` and dynamic Click option binding.
   - `src/rush/cli_support/rendering.py`: `_run_tool`, `_render_session_result`.
   - `src/rush/cli.py`: Imports and re-exports all extracted symbols, remaining the composition root.
2. **MCP Transport**:
   - `src/rush/mcp_support/tool_registry.py`: `register_all_tools(server, executor, tools)`, `register_custom_tools(server, executor, custom_tools)`, `make_tool_wrapper(tool, executor)`, `make_custom_wrapper(fn, tool_id, executor)`.
   - `src/rush/mcp.py`: Imports registration functions and invokes them in `_register_tools()`, reducing complexity to <= 5.
3. **Continuity Orchestration**:
   - `src/rush/continuity/context.py`: `pack_context()`, `retrieve_context()`.
   - `src/rush/continuity/coordination.py`: `check_coordination()`, `preview_merge()`, `recover_coordination()`.
   - `src/rush/continuity/providers.py`: `resume_provider()`, `resume_omniroute()`, `build_provider_command()`, `build_provider_prompt()`, `build_windows_cmd()`.
   - `src/rush/continuity/receipts.py`: `save_receipt()`, `restore_receipt()`. **Phase 61 note:** these now write through the unified `TypedArtifactStore` (`.rush/memory.db`), `trust_tier` replacing the earlier binary quarantine flag; public signatures unchanged.
   - `src/rush/tools/continuity.py`: Retains `SessionContinuityTool` facade with `run()` delegating directly to submodules.
4. **Review Pipeline**:
   - `src/rush/review/collection.py`: `collect_reviewable_files()`, `read_file_safely()`, heuristic filters (`check_file_heuristics`, `is_scaffold_file`).
   - `src/rush/review/llm.py`: `maybe_call_llm()`, `format_review_prompt()`, `parse_llm_findings()`.
   - `src/rush/review/results.py`: `assemble_review_result()`.
   - `src/rush/tools/review.py`: Retains `ReviewTool` facade with `run()` acting as a clean, high-level pipeline coordinator.
5. **Runtime & Common Helpers**:
   - `src/rush/runtime/binaries.py`: `_venv_scripts_dir`, `_resolve_binary_cached`, `clear_binary_cache`, `resolve_binary`, `engine_on_path`.
   - `src/rush/runtime/subprocesses.py`: `_bounded_redacted_output`, `run_subprocess`, `run_engine`, `_install_hint`.
   - `src/rush/runtime/result_helpers.py`: `skipped_result`, `error_result`, `_redact_finding_message`, `finding_fingerprint`, `normalize_findings`, `exit_code_for`, `now_ms`, `elapsed_ms`.
   - `src/rush/tools/common.py`: Re-exports all symbols from `rush.runtime` with identical identity.
6. **Traversal, State, and Lint**:
   - `src/rush/tools/blast_radius_graph.py`: `build_reverse_import_graph(root, target_stems)`, `walk_impacted_paths(graph, seeds, max_depth)`.
   - `src/rush/discovery/workspace_graph.py`: `discover_workspace_packages(root)`, `topological_sort_workspace_packages(packages)`.
   - `src/rush/tools/db_drift_rules.py`: `collect_models(project_root)`, `collect_migrations(project_root)`, `evaluate_drift(models, migrations)`.
   - `src/rush/tools/lint.py`: `_select_engines(path, config)`, `_run_selected_engines(engines, path, engine_args)`, `_assemble_lint_result(results, start_time)`.

---

## 7. Contract-Test Inventory (T-60.01 through T-60.26)

| Test ID | Test File | Test Function | Purpose & Contract Under Test |
|---|---|---|---|
| **T-60.01** | `tests/test_phase60_characterization.py` | `test_cli_catalog_options_rendering_characterization` | Freezes CLI command generation, permission flags, and rendering before refactoring. |
| **T-60.02** | `tests/test_phase60_characterization.py` | `test_mcp_registration_characterization` | Freezes MCP tool registration, parameter adaptation, and JSON-RPC dispatch before refactoring. |
| **T-60.03** | `tests/test_phase60_characterization.py` | `test_continuity_dispatch_provider_receipt_characterization` | Freezes continuity operations (save/restore/context_pack/provider_resume) before refactoring. |
| **T-60.04** | `tests/test_phase60_characterization.py` | `test_review_collection_provider_result_characterization` | Freezes review file collection, heuristic filtering, LLM calling, and result output before refactoring. |
| **T-60.05** | `tests/test_phase60_characterization.py` | `test_common_subprocess_result_characterization` | Freezes binary resolution, subprocess execution, redaction, and result helpers before refactoring. |
| **T-60.06** | `tests/test_phase60_characterization.py` | `test_lint_and_traversal_state_characterization` | Freezes blast radius reachability, workspace discovery, DB drift detection, and lint engine runs. |
| **T-60.07** | `tests/test_phase60_complexity_thresholds.py` | `test_every_target_has_pinned_ruff_version_command_value_and_threshold` | Asserts `governance/maintainability-baseline.toml` exists and pins Ruff 0.16.3, command, and exact targets. |
| **T-60.08** | `tests/test_phase60_complexity_thresholds.py` | `test_exemption_schema_requires_symbol_value_owner_rationale_test_and_expiry` | Asserts `governance/maintainability-exemptions.toml` enforces strict 6-field schema if entries exist. |
| **T-60.09** | `tests/test_phase60_complexity_thresholds.py` | `test_phase60_starts_with_no_exemptions` | Asserts `governance/maintainability-exemptions.toml` contains strictly zero approved exemptions. |
| **T-60.10** | `tests/test_phase60_module_boundaries.py` | `test_cli_support_modules_own_exact_symbols` | Asserts `rush.cli_support` owns `options`, `catalog_commands`, and `rendering`. |
| **T-60.11** | `tests/test_phase60_module_boundaries.py` | `test_cli_compatibility_names_resolve_to_extracted_implementations` | Asserts `src/rush/cli.py` re-exports match extracted objects via `is` comparison. |
| **T-60.12** | `tests/test_phase60_module_boundaries.py` | `test_mcp_support_modules_own_exact_symbols` | Asserts `rush.mcp_support` (or modular helpers) owns tool wrapping and custom tool registration. |
| **T-60.13** | `tests/test_phase60_module_boundaries.py` | `test_continuity_modules_own_exact_symbols` | Asserts `rush.continuity` owns context, coordination, providers, and receipts. |
| **T-60.14** | `tests/test_phase60_module_boundaries.py` | `test_review_modules_own_exact_symbols` | Asserts `rush.review` owns collection, llm, and results. |
| **T-60.15** | `tests/test_phase60_module_boundaries.py` | `test_runtime_modules_own_exact_symbols` | Asserts `rush.runtime` owns binaries, subprocesses, and result_helpers. |
| **T-60.16** | `tests/test_phase60_module_boundaries.py` | `test_common_is_compatibility_reexport_without_duplicate_definitions` | Asserts `src/rush/tools/common.py` defines zero duplicate bodies and re-exports exact runtime symbols. |
| **T-60.17** | `tests/test_phase60_module_boundaries.py` | `test_traversal_state_modules_own_exact_symbols` | Asserts graph and rule modules own exact traversal and evaluation symbols. |
| **T-60.18** | `tests/test_phase60_complexity_thresholds.py` | `test_cli_and_mcp_meet_c901_threshold` | Asserts all functions in `src/rush/cli.py`, `src/rush/mcp.py`, and support modules have C901 <= 10. |
| **T-60.19** | `tests/test_phase60_complexity_thresholds.py` | `test_continuity_facade_meets_c901_threshold` | Asserts `SessionContinuityTool.run` and `_provider_resume` have C901 <= 10. |
| **T-60.20** | `tests/test_phase60_complexity_thresholds.py` | `test_review_facade_meets_c901_threshold` | Asserts `ReviewTool.run` has C901 <= 10. |
| **T-60.21** | `tests/test_phase60_complexity_thresholds.py` | `test_runtime_modules_meet_c901_threshold` | Asserts all functions in `src/rush/runtime/` have C901 <= 10. |
| **T-60.22** | `tests/test_phase60_complexity_thresholds.py` | `test_blast_radius_meets_c901_threshold` | Asserts `BlastRadiusAnalyzer.analyze` has C901 <= 10. |
| **T-60.23** | `tests/test_phase60_complexity_thresholds.py` | `test_workspace_discovery_meets_c901_threshold` | Asserts `discover_workspaces` has C901 <= 10. |
| **T-60.24** | `tests/test_phase60_complexity_thresholds.py` | `test_db_drift_meets_c901_threshold` | Asserts `DbDriftAuditor.audit_drift` has C901 <= 10. |
| **T-60.25** | `tests/test_phase60_complexity_thresholds.py` | `test_all_phase60_facades_and_extracted_symbols_meet_c901_threshold` | Runs Ruff C901 across all production files in §8; asserts strictly 0 findings. |
| **T-60.26** | `tests/test_phase60_refactor.py` | `test_hotspot_complexity_and_modularity_reduction` | **Governing R-015 contract test**: Validates that all 8 target hotspots are reduced <= 10 with zero exemptions. |

---

## 8. File, Dependency, and Complete Documentation Governance

### 8.1 Production and Governance Files Created or Modified

**New Production Code**:
- `src/rush/cli_support/__init__.py`
- `src/rush/cli_support/options.py`
- `src/rush/cli_support/catalog_commands.py`
- `src/rush/cli_support/rendering.py`
- `src/rush/mcp_support/__init__.py`
- `src/rush/mcp_support/tool_registry.py`
- `src/rush/continuity/__init__.py`
- `src/rush/continuity/context.py`
- `src/rush/continuity/coordination.py`
- `src/rush/continuity/providers.py`
- `src/rush/continuity/receipts.py`
- `src/rush/review/__init__.py`
- `src/rush/review/collection.py`
- `src/rush/review/llm.py`
- `src/rush/review/results.py`
- `src/rush/runtime/__init__.py`
- `src/rush/runtime/binaries.py`
- `src/rush/runtime/subprocesses.py`
- `src/rush/runtime/result_helpers.py`
- `src/rush/tools/blast_radius_graph.py`
- `src/rush/discovery/workspace_graph.py`
- `src/rush/tools/db_drift_rules.py`

**New Governance Artifacts**:
- `governance/maintainability-baseline.toml`
- `governance/maintainability-exemptions.toml`
- `governance/remediation-phase-60.toml`
- `docs/developer/phase-60-implementation-evidence.md`

**New Test Files**:
- `tests/test_phase60_characterization.py`
- `tests/test_phase60_module_boundaries.py`
- `tests/test_phase60_complexity_thresholds.py`
- `tests/test_phase60_refactor.py`

**Modified Production Code (Facades & Refactored Bodies)**:
- `src/rush/cli.py` (imports and re-exports from `cli_support`)
- `src/rush/mcp.py` (imports and invokes registration from `mcp_support`)
- `src/rush/tools/continuity.py` (delegates to `continuity/` modules)
- `src/rush/tools/review.py` (delegates to `review/` modules)
- `src/rush/tools/common.py` (re-exports from `runtime/` modules)
- `src/rush/tools/lint.py` (decomposed with private helpers)
- `src/rush/tools/blast_radius.py` (delegates to `blast_radius_graph.py`)
- `src/rush/discovery/workspace.py` (delegates to `workspace_graph.py`)
- `src/rush/tools/db_drift.py` (delegates to `db_drift_rules.py`)
- `src/rush/tools/__init__.py` (re-exports preserved)
- `governance/remediation-contracts.toml` (marks R-015 `status = "completed"`)

### 8.2 Comprehensive Documentation Ledger Across `/docs`

All 351 markdown files in `docs/` have been surveyed and classified into 5 operational groups for post-Phase 60 maintenance:

#### Group 1: Core Architecture & Standards (Direct Content Updates Required in P60.7.1)
1. `docs/ARCHITECTURE.md`: Document modular package architecture (`rush.cli_support`, `rush.mcp_support`, `rush.continuity`, `rush.review`, `rush.runtime`, graph/rule helpers) and transport decoupling.
2. `docs/developer/architecture.md`: Detail the maintainability hotspot reduction architecture, module boundaries, C901 threshold <= 10 invariant, and R-015 completion.
3. `docs/developer/source-tree.md`: Update source tree layout to include new packages (`src/rush/cli_support/`, `src/rush/mcp_support/`, `src/rush/continuity/`, `src/rush/review/`, `src/rush/runtime/`, and sub-modules `blast_radius_graph.py`, `workspace_graph.py`, `db_drift_rules.py`).
4. `docs/developer/coding-standards.md`: Add Section 5 defining the McCabe C901 complexity budget (maximum 10 for all functions and methods), cognitive decomposition rules, and zero maintainability exemptions.
5. `docs/developer/tool-development.md`: Document the recommended pattern for complex tools (separating AST/graph traversal and evaluation rules into helper modules) and using `rush.runtime` helpers.
6. `docs/maintainers/architecture-lifecycle.md`: Add maintainability lifecycle section detailing CI enforcement of McCabe complexity and baseline preservation.
7. `docs/KNOWN_ISSUES.md`: Add resolution entry for Finding R-015 documenting the complete decomposition and elimination of maintainability hotspots across central modules.

#### Group 2: Remediation Roadmap & Milestone Reports (Milestone & Program Completion in P60.7.1)
8. `docs/developer/phase-60-implementation-evidence.md`: Record admission baseline evidence, task execution log, AST complexity measurements before/after, and final verification transcript.
9. `docs/developer/repository-remediation-plan.md`: Update status of R-015 and Phase 9 (Slice 10) to **Completed**; record final program completion reflecting all 16 findings closed (100% complete).
10. `docs/developer/repository-remediation-plan.adversarial-review.md`: Synchronize R-015 closure status.
11. `docs/phase-plans/README.md`: Update Phase 60 entry from "Planned" to "Completed", noting that all 10 remediation phases (51–60) are now complete.
12. `docs/phase-plans/phase-60-maintainability-hotspot-reduction-plan.md`: Record execution completion status.
13. `docs/reports/final-handoff.md`: Update program summary recording that all 16 findings (R-001 through R-016) are fully resolved with zero release blockers and zero non-release findings remaining.

#### Group 3: Developer Guides & Operational Manuals (Module Reference Synchronization)
14. `docs/developer/debugging-guide.md`: Note module locations for runtime helpers (`src/rush/runtime/`) and CLI support.
15. `docs/developer/contributor-onboarding.md`: Update source tree orientation and coding standards reference.
16. `docs/developer/testing-guide.md`: Reference characterization tests, boundary tests, and complexity threshold suites.
17. `docs/developer/ci-and-packaging.md`: Verify wheel/sdist packaging probes include the new subpackages.
18. `docs/DEVELOPER_GUIDE.md`: Verify references to central modules align with modular package layout.

#### Group 4: Reference Specifications & Transport Registries (Zero-Drift Verification)
19. `docs/reference/result-reference.md`: Verify `ToolResultV1` helper references align with `rush.runtime.result_helpers`.
20. `docs/reference/cli-reference.md` & `docs/CLI_REFERENCE.md`: Verify 100% command and option parity (zero syntax or semantic drift).
21. `docs/reference/mcp-tool-reference.md` & `docs/MCP_REFERENCE.md`: Verify 100% MCP tool registration and schema parity (zero parameter or schema drift).
22. `docs/ENGINES.md`: Verify engine discovery and execution via `rush.runtime.binaries` and `rush.runtime.subprocesses` preserve exact contracts.
23. `docs/DISTRIBUTION.md`: Verify package building and distribution commands remain fully compatible with new package layout.
24. `docs/VERSIONING.md`: Confirm that internal refactoring without public contract change constitutes a clean patch-compatible maintenance release.
25. `docs/SAFETY.md` & `docs/SECURITY.md`: Confirm that sanitization, permission validation, and subprocess isolation boundaries remain completely intact.

#### Group 5: Subfolder Zero-Drift Audit (Integrity Verification)
26–351. Verify all remaining documentation files in:
- `docs/getting-started/` (installation, first run, glossary)
- `docs/integrations/` (CI, GitHub Actions, MCP client setup)
- `docs/maintainers/` & `docs/maintainers/adr/` (all 15 ADRs)
- `docs/phase-plans/` (Phases 41–59 historical plans remain immutable)
- `docs/reference/` (configuration, environment variables, engine directory)
- `docs/reports/` (historical research reports)
- `docs/safety/` (permissions, privacy, security model)
- `docs/specs/` (all 22 feature specifications)
- `docs/tools/` (all tool guides)
- `docs/tutorials/` (all 8 tutorials)
- `docs/user-guide/` (all 11 user guide chapters)
- `docs/vibecoding/` (all 9 vibecoding guides)
- `docs/workflows/` (all 9 workflow guides)
*Audit Confirmation:* All 326 files in Group 5 describe user-facing or architectural concepts that are preserved with 100% backward compatibility by Phase 60 compatibility facades. Zero behavioral drift occurs.

---

## 9. Ordered Workstreams and Atomic Task Cards

### P60.0 — Admission & Baseline Freeze

#### P60.0.1 — EVIDENCE: Freeze predecessor state and record admission baseline

- **Task ID and Outcome:** P60.0.1; record admission gate verification and exact 8-symbol C901 baseline in `docs/developer/phase-60-implementation-evidence.md`.
- **Start Goal:** Prove repository correctness and freeze metrics before any source writes.
- **Prerequisites:** §4 admission checks pass.
- **Allowed Writes:** create `docs/developer/phase-60-implementation-evidence.md`.
- **Allowed Reads:** `governance/remediation-phase-59.toml`, `governance/remediation-contracts.toml`, `governance/first-party-coverage.toml`, target source files, ruff output.
- **Prohibited:** Any edits to production code, tests, dependencies, or configuration.
- **Actions:**
  1. Verify Phase 59 completion manifest, test suite (1,189 passed), and clean working tree.
  2. Run `.venv/Scripts/ruff.exe check --select C901 --config "lint.mccabe.max-complexity = 10" --output-format concise` against the 8 target files.
  3. Initialize `docs/developer/phase-60-implementation-evidence.md` with git commit hash, Ruff version (0.16.3), exact baseline complexity values, and seam mapping.
- **Verification:** `docs/developer/phase-60-implementation-evidence.md` exists and contains verified admission values.

---

### P60.1 — Behavior Oracle and Metric Governance

#### P60.1.1 — CHARACTERIZATION: Freeze behavior across all 5 target domains

- **Task ID and Outcome:** P60.1.1; create `tests/test_phase60_characterization.py` containing 6 comprehensive characterization tests (T-60.01 through T-60.06) passing against unchanged production code.
- **Start Goal:** Establish the behavior preservation oracle before touching any production file.
- **Prerequisites:** P60.0.1 completed.
- **Allowed Writes:** create `tests/test_phase60_characterization.py`.
- **Allowed Reads:** All target source files in `src/rush/`, existing tests in `tests/`.
- **Actions:**
  1. Author `test_cli_catalog_options_rendering_characterization` (T-60.01): Invokes CLI commands via Click `CliRunner`, asserting exact option parsing, exit codes, and stdout rendering for catalog tools.
  2. Author `test_mcp_registration_characterization` (T-60.02): Initializes FastMCP server and asserts all tools and custom tools register with exact parameter signatures and schemas.
  3. Author `test_continuity_dispatch_provider_receipt_characterization` (T-60.03): Executes `SessionContinuityTool` across `save`, `list`, `restore`, `context_pack`, and `provider_resume`, asserting structured output equivalence and receipt persistence.
  4. Author `test_review_collection_provider_result_characterization` (T-60.04): Runs `ReviewTool` on sample files, asserting file collection, heuristic exclusions, LLM prompt dispatch, and canonical `ToolResultV1` output.
  5. Author `test_common_subprocess_result_characterization` (T-60.05): Calls `resolve_binary`, `run_subprocess`, `run_engine`, and result helpers (`skipped_result`, `error_result`, `exit_code_for`), asserting exact return types, redaction, and error mapping.
  6. Author `test_lint_and_traversal_state_characterization` (T-60.06): Runs `BlastRadiusAnalyzer.analyze`, `discover_workspaces`, `DbDriftAuditor.audit_drift`, and `LintTool.run`, asserting exact graph structures, workspace lists, and drift detections.
- **Verification:** Run `.venv/Scripts/python.exe -m pytest tests/test_phase60_characterization.py -v`; all 6 tests PASS (GREEN) against unchanged production code.

#### P60.1.2 — RED: Define baseline and exemption governance tests

- **Task ID and Outcome:** P60.1.2; create `tests/test_phase60_complexity_thresholds.py` with 3 baseline governance tests (T-60.07 through T-60.09) failing because governance files are absent.
- **Start Goal:** Establish machine-readable maintainability contracts and fail-closed exemption policy.
- **Prerequisites:** P60.1.1 completed.
- **Allowed Writes:** create `tests/test_phase60_complexity_thresholds.py`.
- **Actions:**
  1. Author `test_every_target_has_pinned_ruff_version_command_value_and_threshold` (T-60.07): Reads `governance/maintainability-baseline.toml`; asserts tool is "ruff", version is "0.16.3", command is pinned, threshold is 10, and all 8 target symbols have recorded baseline scores.
  2. Author `test_exemption_schema_requires_symbol_value_owner_rationale_test_and_expiry` (T-60.08): Asserts that if any entry exists in `governance/maintainability-exemptions.toml`, it strictly validates 6 required keys (`symbol`, `value`, `owner`, `rationale`, `compensating_test`, `expires_at`).
  3. Author `test_phase60_starts_with_no_exemptions` (T-60.09): Asserts that `governance/maintainability-exemptions.toml` has `exemptions = []` (count == 0).
- **Verification:** Run `.venv/Scripts/python.exe -m pytest tests/test_phase60_complexity_thresholds.py -q`; fails with `FileNotFoundError` (RED).

#### P60.1.3 — GREEN: Commit maintainability baseline and empty exemptions

- **Task ID and Outcome:** P60.1.3; create `governance/maintainability-baseline.toml` and `governance/maintainability-exemptions.toml` satisfying T-60.07 through T-60.09.
- **Start Goal:** Establish the machine-readable maintainability state.
- **Prerequisites:** P60.1.2 RED verified.
- **Allowed Writes:** create `governance/maintainability-baseline.toml`, create `governance/maintainability-exemptions.toml`.
- **Actions:**
  1. Write `governance/maintainability-baseline.toml` with pinned metadata (ruff 0.16.3, C901, threshold 10) and exact baseline values for the 8 target symbols.
  2. Write `governance/maintainability-exemptions.toml` with `schema_version = "1.0.0"` and empty `exemptions = []`.
- **Verification:** Run `.venv/Scripts/python.exe -m pytest tests/test_phase60_complexity_thresholds.py -v`; all 3 tests PASS (GREEN).

---

### P60.2 — Transport Boundaries (CLI & MCP)

#### P60.2.1 — RED: Require exact CLI and MCP support module ownership

- **Task ID and Outcome:** P60.2.1; create `tests/test_phase60_module_boundaries.py` with tests T-60.10, T-60.11, and T-60.12 failing on missing support modules.
- **Start Goal:** Pin CLI and MCP extraction destinations and compatibility interfaces.
- **Prerequisites:** P60.1.3 completed.
- **Allowed Writes:** create `tests/test_phase60_module_boundaries.py`.
- **Actions:**
  1. Author `test_cli_support_modules_own_exact_symbols` (T-60.10): Asserts `src/rush/cli_support/options.py` defines `_extract_permissions` and `permission_options`; `catalog_commands.py` defines `build_catalog_path_command`; `rendering.py` defines `_run_tool` and `_render_session_result`.
  2. Author `test_cli_compatibility_names_resolve_to_extracted_implementations` (T-60.11): Asserts `src/rush/cli.py` re-exports match extracted functions (`assert rush.cli._extract_permissions is rush.cli_support.options._extract_permissions`).
  3. Author `test_mcp_support_modules_own_exact_symbols` (T-60.12): Asserts `src/rush/mcp_support/tool_registry.py` defines `register_all_tools`, `register_custom_tools`, `make_tool_wrapper`, and `make_custom_wrapper`.
- **Verification:** Run `.venv/Scripts/python.exe -m pytest tests/test_phase60_module_boundaries.py -q`; fails with `ModuleNotFoundError` (RED).

#### P60.2.2 — GREEN: Extract CLI and MCP support modules

- **Task ID and Outcome:** P60.2.2; implement `src/rush/cli_support/` and `src/rush/mcp_support/`, refactor `src/rush/cli.py` and `src/rush/mcp.py`, and achieve C901 <= 10.
- **Start Goal:** Deconstruct central transport modules while preserving Click and stdio MCP behavior.
- **Prerequisites:** P60.2.1 RED verified.
- **Allowed Writes:** create `src/rush/cli_support/__init__.py`, `src/rush/cli_support/options.py`, `src/rush/cli_support/catalog_commands.py`, `src/rush/cli_support/rendering.py`, `src/rush/mcp_support/__init__.py`, `src/rush/mcp_support/tool_registry.py`; modify `src/rush/cli.py`, `src/rush/mcp.py`.
- **Actions:**
  1. Move `_extract_permissions` and `permission_options` into `src/rush/cli_support/options.py`.
  2. Move `build_catalog_path_command` into `src/rush/cli_support/catalog_commands.py`.
  3. Move `_run_tool` and `_render_session_result` into `src/rush/cli_support/rendering.py`.
  4. In `src/rush/cli.py`, import and re-export all moved symbols.
  5. Implement `src/rush/mcp_support/tool_registry.py` extracting `make_tool_wrapper`, `make_custom_wrapper`, `register_all_tools`, and `register_custom_tools`.
  6. In `src/rush/mcp.py`, simplify `_register_tools(server)` to delegate to `register_all_tools` and `register_custom_tools`, reducing C901 from 16 to <= 5.
- **Verification:** Run `.venv/Scripts/python.exe -m pytest tests/test_phase60_module_boundaries.py tests/test_phase60_characterization.py tests/test_cli.py tests/test_mcp.py -v`; all PASS (GREEN). Run Ruff C901 on `src/rush/cli.py` and `src/rush/mcp.py`; 0 findings.

---

### P60.3 — Continuity Orchestration Boundary

#### P60.3.1 — RED: Require exact continuity ownership and C901 threshold

- **Task ID and Outcome:** P60.3.1; add T-60.13 to `tests/test_phase60_module_boundaries.py` and T-60.19 to `tests/test_phase60_complexity_thresholds.py` failing on missing `rush.continuity` modules and current complexity.
- **Start Goal:** Pin continuity submodules and threshold <= 10.
- **Prerequisites:** P60.2.2 completed.
- **Allowed Writes:** modify `tests/test_phase60_module_boundaries.py`, modify `tests/test_phase60_complexity_thresholds.py`.
- **Actions:**
  1. Author `test_continuity_modules_own_exact_symbols` (T-60.13): Asserts `src/rush/continuity/context.py` owns `pack_context`/`retrieve_context`; `coordination.py` owns `check_coordination`/`preview_merge`/`recover_coordination`; `providers.py` owns `resume_provider`/`resume_omniroute`; `receipts.py` owns `save_receipt`/`restore_receipt`.
  2. Author `test_continuity_facade_meets_c901_threshold` (T-60.19): Runs Ruff C901 on `src/rush/tools/continuity.py` and `src/rush/continuity/`; asserts 0 findings.
- **Verification:** Pytest fails due to missing modules and `SessionContinuityTool.run` complexity 18 > 10 (RED).

#### P60.3.2 — GREEN: Extract continuity orchestration modules

- **Task ID and Outcome:** P60.3.2; create `src/rush/continuity/` modules, refactor `src/rush/tools/continuity.py`, and achieve C901 <= 10.
- **Start Goal:** Decompose `src/rush/tools/continuity.py` while preserving `SessionContinuityTool` facade.
- **Prerequisites:** P60.3.1 RED verified.
- **Allowed Writes:** create `src/rush/continuity/__init__.py`, `src/rush/continuity/context.py`, `src/rush/continuity/coordination.py`, `src/rush/continuity/providers.py`, `src/rush/continuity/receipts.py`; modify `src/rush/tools/continuity.py`.
- **Actions:**
  1. Implement `src/rush/continuity/context.py` owning CCR context packing and retrieval logic.
  2. Implement `src/rush/continuity/coordination.py` owning lock checking, 3-way merge preview, and recovery logic.
  3. Implement `src/rush/continuity/providers.py` owning provider resume CLI command assembly and prompt formatting.
  4. Implement `src/rush/continuity/receipts.py` owning handoff receipt persistence and validation.
  5. Refactor `SessionContinuityTool.run` to dispatch directly to these modular handlers, reducing complexity from 18 to <= 8. Refactor `_provider_resume` to <= 8.
- **Verification:** Run `.venv/Scripts/python.exe -m pytest tests/test_phase60_module_boundaries.py tests/test_phase60_complexity_thresholds.py tests/test_phase60_characterization.py -k "continuity" -v`; all PASS (GREEN).

---

### P60.4 — Review Pipeline Boundary

#### P60.4.1 — RED: Require exact review ownership and C901 threshold

- **Task ID and Outcome:** P60.4.1; add T-60.14 to `tests/test_phase60_module_boundaries.py` and T-60.20 to `tests/test_phase60_complexity_thresholds.py` failing on missing `rush.review` modules and current complexity.
- **Start Goal:** Pin review submodules and threshold <= 10.
- **Prerequisites:** P60.3.2 completed.
- **Allowed Writes:** modify `tests/test_phase60_module_boundaries.py`, modify `tests/test_phase60_complexity_thresholds.py`.
- **Actions:**
  1. Author `test_review_modules_own_exact_symbols` (T-60.14): Asserts `src/rush/review/collection.py` owns file collection and heuristics; `llm.py` owns `_maybe_call_llm`; `results.py` owns `assemble_review_result`.
  2. Author `test_review_facade_meets_c901_threshold` (T-60.20): Runs Ruff C901 on `src/rush/tools/review.py` and `src/rush/review/`; asserts 0 findings.
- **Verification:** Pytest fails due to missing modules and `ReviewTool.run` complexity 16 > 10 (RED).

#### P60.4.2 — GREEN: Extract review pipeline modules

- **Task ID and Outcome:** P60.4.2; create `src/rush/review/` modules, refactor `src/rush/tools/review.py`, and achieve C901 <= 10.
- **Start Goal:** Decompose `src/rush/tools/review.py` into collection, LLM, and result assembly.
- **Prerequisites:** P60.4.1 RED verified.
- **Allowed Writes:** create `src/rush/review/__init__.py`, `src/rush/review/collection.py`, `src/rush/review/llm.py`, `src/rush/review/results.py`; modify `src/rush/tools/review.py`.
- **Actions:**
  1. Implement `src/rush/review/collection.py` owning `_collect_reviewable_files`, `_read_file_safely`, and heuristic filtering.
  2. Implement `src/rush/review/llm.py` owning `_maybe_call_llm` and prompt building.
  3. Implement `src/rush/review/results.py` owning `assemble_review_result`.
  4. Refactor `ReviewTool.run` to coordinate these stages cleanly, reducing complexity from 16 to <= 7.
- **Verification:** Run `.venv/Scripts/python.exe -m pytest tests/test_phase60_module_boundaries.py tests/test_phase60_complexity_thresholds.py tests/test_review.py -k "review" -v`; all PASS (GREEN).

---

### P60.5 — Runtime & Common Helpers Boundary

#### P60.5.1 — RED: Require exact runtime ownership and zero duplicate definitions

- **Task ID and Outcome:** P60.5.1; add T-60.15 and T-60.16 to `tests/test_phase60_module_boundaries.py` failing on missing `rush.runtime` modules.
- **Start Goal:** Pin runtime destinations without breaking legacy imports.
- **Prerequisites:** P60.4.2 completed.
- **Allowed Writes:** modify `tests/test_phase60_module_boundaries.py`.
- **Actions:**
  1. Author `test_runtime_modules_own_exact_symbols` (T-60.15): Asserts `src/rush/runtime/binaries.py` owns `resolve_binary`, `engine_on_path`, `_resolve_binary_cached`; `subprocesses.py` owns `run_subprocess`, `run_engine`; `result_helpers.py` owns `skipped_result`, `error_result`, `exit_code_for`, `finding_fingerprint`, `normalize_findings`.
  2. Author `test_common_is_compatibility_reexport_without_duplicate_definitions` (T-60.16): Inspects AST of `src/rush/tools/common.py`; asserts zero `def ` or `class ` definitions exist except import statements and `__all__` re-exports; asserts identity `is` equality for all public symbols.
- **Verification:** Pytest fails due to missing `rush.runtime` modules (RED).

#### P60.5.2 — GREEN: Extract runtime modules and convert common.py to facade

- **Task ID and Outcome:** P60.5.2; create `src/rush/runtime/` modules and convert `src/rush/tools/common.py` to a pure re-export facade.
- **Start Goal:** Cleanly segregate runtime utilities while preserving 100% import compatibility.
- **Prerequisites:** P60.5.1 RED verified.
- **Allowed Writes:** create `src/rush/runtime/__init__.py`, `src/rush/runtime/binaries.py`, `src/rush/runtime/subprocesses.py`, `src/rush/runtime/result_helpers.py`; modify `src/rush/tools/common.py`.
- **Actions:**
  1. Implement `src/rush/runtime/binaries.py` with binary discovery, caching, and PATH resolution.
  2. Implement `src/rush/runtime/subprocesses.py` with bounded redacted execution and engine error mapping.
  3. Implement `src/rush/runtime/result_helpers.py` with result constructors, fingerprinting, and exit code helpers.
  4. Replace implementation bodies in `src/rush/tools/common.py` with re-exports from `src/rush/runtime`.
- **Verification:** Run `.venv/Scripts/python.exe -m pytest tests/test_phase60_module_boundaries.py tests/test_subprocess_contract.py tests/test_static_tools.py -v`; all PASS (GREEN).

---

### P60.6 — Traversal, State, and Lint Boundary

#### P60.6.1 — RED: Require traversal/state graph ownership and zero C901 findings

- **Task ID and Outcome:** P60.6.1; add T-60.17 to `tests/test_phase60_module_boundaries.py` and T-60.22 through T-60.25 to `tests/test_phase60_complexity_thresholds.py` failing on missing modules and current complexity.
- **Start Goal:** Pin graph/rule modular extractions and threshold <= 10.
- **Prerequisites:** P60.5.2 completed.
- **Allowed Writes:** modify `tests/test_phase60_module_boundaries.py`, modify `tests/test_phase60_complexity_thresholds.py`.
- **Actions:**
  1. Author `test_traversal_state_modules_own_exact_symbols` (T-60.17): Asserts `src/rush/tools/blast_radius_graph.py` owns `build_reverse_import_graph`/`walk_impacted_paths`; `src/rush/discovery/workspace_graph.py` owns `discover_workspace_packages`/`topological_sort_workspace_packages`; `src/rush/tools/db_drift_rules.py` owns `collect_models`/`collect_migrations`/`evaluate_drift`.
  2. Author threshold tests T-60.22 (`BlastRadiusAnalyzer.analyze` <= 10), T-60.23 (`discover_workspaces` <= 10), T-60.24 (`DbDriftAuditor.audit_drift` <= 10), and T-60.25 (all Phase 60 production files <= 10).
- **Verification:** Pytest fails due to missing graph modules and high cyclomatic complexity (23, 21, 15, 12 > 10) (RED).

#### P60.6.2 — GREEN: Extract graph and rule modules and refactor lint.py

- **Task ID and Outcome:** P60.6.2; implement graph and rule modules, refactor facades, and achieve C901 <= 10 across all targets.
- **Start Goal:** Eliminate all remaining maintainability hotspots.
- **Prerequisites:** P60.6.1 RED verified.
- **Allowed Writes:** create `src/rush/tools/blast_radius_graph.py`, `src/rush/discovery/workspace_graph.py`, `src/rush/tools/db_drift_rules.py`; modify `src/rush/tools/blast_radius.py`, `src/rush/discovery/workspace.py`, `src/rush/tools/db_drift.py`, `src/rush/tools/lint.py`.
- **Actions:**
  1. Implement `src/rush/tools/blast_radius_graph.py`; refactor `BlastRadiusAnalyzer.analyze` to delegate, reducing complexity from 15 to <= 8.
  2. Implement `src/rush/discovery/workspace_graph.py`; refactor `discover_workspaces` to delegate, reducing complexity from 23 to <= 8.
  3. Implement `src/rush/tools/db_drift_rules.py`; refactor `DbDriftAuditor.audit_drift` to delegate, reducing complexity from 21 to <= 7.
  4. Decompose `LintTool.run` in `src/rush/tools/lint.py` into `_select_engines`, `_run_selected_engines`, and `_assemble_lint_result`, reducing complexity from 12 to <= 7.
- **Verification:** Run `.venv/Scripts/python.exe -m pytest tests/test_phase60_module_boundaries.py tests/test_phase60_complexity_thresholds.py tests/test_phase46_blast_radius_arch.py tests/test_workspace.py tests/test_phase48_db_simplify_strict.py -v; all PASS (GREEN). Run Ruff C901 command across all 8 target files; exactly 0 findings reported.

---

### P60.7 — Documentation, Contract Test, and Program Handoff

#### P60.7.1 — VERIFY/DOCS/HANDOFF: Author R-015 contract test, synchronize docs, and close program

- **Task ID and Outcome:** P60.7.1; create `tests/test_phase60_refactor.py` (T-60.26), synchronize all Group 1, 2, 3, 4, 5 documentation across `/docs`, create `governance/remediation-phase-60.toml`, mark R-015 completed in `governance/remediation-contracts.toml`, finalize `docs/developer/phase-60-implementation-evidence.md`, and record 100% remediation program completion in `docs/developer/repository-remediation-plan.md`.
- **Start Goal:** Prove complete remediation program closure with zero open findings.
- **Prerequisites:** P60.1.1 through P60.6.2 fully passed.
- **Allowed Writes:**
  - `tests/test_phase60_refactor.py`
  - `governance/remediation-phase-60.toml`
  - `governance/remediation-contracts.toml`
  - `docs/developer/phase-60-implementation-evidence.md`
  - `docs/developer/repository-remediation-plan.md`
  - `docs/phase-plans/README.md`
  - `docs/phase-plans/phase-60-maintainability-hotspot-reduction-plan.md`
  - `docs/reports/final-handoff.md`
  - `docs/ARCHITECTURE.md`
  - `docs/developer/architecture.md`
  - `docs/developer/source-tree.md`
  - `docs/developer/coding-standards.md`
  - `docs/developer/tool-development.md`
  - `docs/maintainers/architecture-lifecycle.md`
  - `docs/KNOWN_ISSUES.md`
  - `docs/developer/debugging-guide.md`
  - `docs/developer/contributor-onboarding.md`
- **Actions:**
  1. Author `tests/test_phase60_refactor.py` defining `test_hotspot_complexity_and_modularity_reduction` (T-60.26), verifying that all 8 target modules have C901 <= 10, all support modules exist, and `governance/maintainability-exemptions.toml` has 0 exemptions.
  2. Synchronize all 17 listed documentation files according to the §8.2 ledger.
  3. Generate `governance/remediation-phase-60.toml` detailing all 26 contract tests, requirement R-015 closure, and program completion status.
  4. Update `governance/remediation-contracts.toml`: mark R-015 `status = "completed"`.
  5. Finalize `docs/developer/phase-60-implementation-evidence.md` recording before/after complexity evidence and test run logs.
  6. In `docs/developer/repository-remediation-plan.md`, record that Phase 9 (Slice 10) is complete and the entire remediation program (all 16 findings R-001 through R-016) is 100% COMPLETE.
- **Verification:** Run §10 full delivery gate. All tests pass, lint passes, format passes, probe passes, and working tree is clean.

---

## 10. Final Verification and Delivery Gate

Execute the complete verification sequence:

```bash
# 1. Clear ambient Python environment variables
$env:VIRTUAL_ENV=$null
$env:PYTHONPATH=$null

# 2. Verify all Phase 60 contract suites
.venv/Scripts/python.exe -m pytest tests/test_phase60_characterization.py tests/test_phase60_module_boundaries.py tests/test_phase60_complexity_thresholds.py tests/test_phase60_refactor.py -v

# 3. Verify core regression suites
.venv/Scripts/python.exe -m pytest tests/test_cli.py tests/test_cli_registry.py tests/test_mcp.py tests/test_review.py tests/test_subprocess_contract.py tests/test_phase46_blast_radius_arch.py tests/test_phase48_db_simplify_strict.py tests/test_workspace.py -q

# 4. Verify entire test suite (all 1,189+ tests)
.venv/Scripts/python.exe -m pytest tests/ -q

# 5. Verify zero C901 complexity findings across all target and extracted paths
.venv/Scripts/ruff.exe check --select C901 --config "lint.mccabe.max-complexity = 10" --output-format concise src/rush/cli.py src/rush/mcp.py src/rush/tools/continuity.py src/rush/tools/review.py src/rush/tools/common.py src/rush/tools/lint.py src/rush/tools/blast_radius.py src/rush/discovery/workspace.py src/rush/tools/db_drift.py src/rush/cli_support src/rush/mcp_support src/rush/continuity src/rush/review src/rush/runtime src/rush/tools/blast_radius_graph.py src/rush/discovery/workspace_graph.py src/rush/tools/db_drift_rules.py

# 6. Verify codebase lint and formatting
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/ruff.exe format --check src tests scripts

# 7. Verify installed artifact probes on wheel and sdist
.venv/Scripts/python.exe scripts/probe_installed_artifacts.py

# 8. Check Git status and diff
git diff --check
git status --short --branch
```

---

## 11. Exit Checklist and Successor Evidence

- [ ] Admission verified in `docs/developer/phase-60-implementation-evidence.md` with baseline C901 measurements.
- [ ] Characterization suite (`tests/test_phase60_characterization.py`, T-60.01-T-60.06) passed before movement and remains green.
- [ ] Maintainability baseline committed in `governance/maintainability-baseline.toml`.
- [ ] Exemption policy committed in `governance/maintainability-exemptions.toml` with strictly 0 exemptions.
- [ ] Transport boundaries deconstructed: `src/rush/cli_support/` and `src/rush/mcp_support/` own respective options, commands, and registration helpers.
- [ ] `src/rush/cli.py` and `src/rush/mcp.py` maintain 100% backward-compatible facades and pass all CLI/MCP parity tests.
- [ ] Continuity orchestration deconstructed: `src/rush/continuity/` owns context, coordination, providers, and receipts; `SessionContinuityTool.run` complexity <= 10.
- [ ] Review pipeline deconstructed: `src/rush/review/` owns collection, LLM egress, and result assembly; `ReviewTool.run` complexity <= 10.
- [ ] Runtime helpers deconstructed: `src/rush/runtime/` owns binaries, subprocesses, and result helpers; `src/rush/tools/common.py` is a 100% backward-compatible facade re-exporting identical symbols.
- [ ] Traversal, state, and lint deconstructed: `blast_radius_graph.py`, `workspace_graph.py`, and `db_drift_rules.py` own graph/rule logic; `analyze`, `discover_workspaces`, `audit_drift`, and `LintTool.run` have complexity <= 10.
- [ ] Exact metric command reports strictly 0 C901 findings at threshold 10 across all 8 targets and all new extracted modules.
- [ ] Contract test `tests/test_phase60_refactor.py` (`test_hotspot_complexity_and_modularity_reduction`, T-60.26) passes cleanly.
- [ ] All 351 docs across `/docs` and subfolders verified; all Group 1-4 documentation files synchronized.
- [ ] `governance/remediation-phase-60.toml` created with complete test and requirement closure record.
- [ ] `governance/remediation-contracts.toml` updated with finding R-015 marked `status = "completed"`.
- [ ] `docs/developer/repository-remediation-plan.md` updated with Phase 9 / Slice 10 marked completed and all 16 findings closed (100% complete).
- [ ] Full regression suite (1,189+ tests), ruff lint, ruff format, and installed artifact probe pass with 0 errors and 0 warnings.
