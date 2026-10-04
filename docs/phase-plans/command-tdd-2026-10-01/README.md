# Command TDD batch 2026-10-01: Q01-Q10 index

Audit: docs/reports/cli-mcp-command-audit-2026-09-26.md, sha256 8ff7a75c35b8c9794b95725dbe76cf36a0056ef6b5863518065d9669439a077f.
Source revision (audit grounding only): c78e445ba1e575ca373e35840142cd627b055d6a.
Implementation base: branch phase/70-agent-adoption-and-usability at 66c6c799eaa5b6017776d659e9e0de2b4a8878a5, or its merge commit into main once merged.
Start gate: Phase 70 tasks T1-T29 and acceptance G0-G8 complete on the implementation base.
Authorization: planning only. Any next batch requires explicit user approval.
Inputs: the audit and these plans are untracked at the time of writing. They must be committed on the implementation branch, or copied byte-identically into the phase worktree with the sha256 above re-verified, before any packet starts. Paths in the plans are repo-relative.
Worktree: use the Phase 70 worktree named by .claude/CLAUDE.md; paths below are relative to that repository root.

## Roles (each plan uses only these names)
- Foundation owner: the agent executing 00-shared-foundation.md. Sole writer of src/rush/cli.py (including review, format and sbom_cmd), src/rush/catalog.py, src/rush/config.py, src/rush/cli_support/catalog_commands.py, src/rush/cli_support/options.py, src/rush/mcp.py, src/rush/mcp_support/tool_registry.py, src/rush/mcp_support/request_models.py, src/rush/invocation/executor.py, src/rush/tools/routing.py, src/rush/tools/common.py, src/rush/engines/base.py, src/rush/runtime/isolated_process.py, src/rush/runtime/isolated_tests.py, tests/transport_parity.py, tests/test_transport_parity.py, tests/test_isolated_process.py, tests/test_isolated_tests.py, tests/test_cli_registry.py, tests/test_mcp.py, src/rush/tools/sbom.py, tests/test_sbom.py, tests/test_routing.py, src/rush/runtime/subprocesses.py (Q02 selected_targets and Q04 preflight patch rows), tests/conftest.py, tests/test_no_skips.py, pyproject.toml markers, .github/workflows/ci.yml (oci-isolation job), and the shared docs listed in 00-shared-foundation.md F8. This is not the memory program's "integration owner" (docs/phase-plans/memory-program-contract.md:112).
- Command owner (Qnn): sole writer of the files listed in that plan's Deliverables. Q01: src/rush/tools/review.py, src/rush/review/llm.py, src/rush/review/results.py, src/rush/review/probe_harness.py, tests/test_review.py. Q02: src/rush/engines/globstar.py, src/rush/tools/lint.py, src/rush/engines/ruff.py, src/rush/engines/eslint.py, tests/test_lint.py. Q03: src/rush/runtime/filesystem.py, tests/test_format_parity.py, tests/test_prettier_honest.py, tests/test_format_oci.py, src/rush/tools/format.py, src/rush/engines/prettier.py, tests/test_format.py. Q04: src/rush/tools/test.py, src/rush/engines/pytest.py, src/rush/engines/vitest.py, tests/test_test_tool.py. Q05: src/rush/tools/security.py, src/rush/engines/pip_audit.py, npm_audit.py, osv.py, tests/test_security.py. Q06: src/rush/tools/typecheck.py, src/rush/engines/pyrefly.py, src/rush/engines/tsc.py, tests/test_typecheck.py. Q07: src/rush/tools/dead_probe_plugin.py, tests/test_vulture_reference.py, tests/test_knip_reference.py, tests/test_static_tools.py, tests/fixtures/engine_reports/knip-6.35.1.json, tests/fixtures/engine_reports/knip.txt (delete obsolete fixture), src/rush/tools/dead.py, src/rush/engines/vulture.py, src/rush/engines/knip.py, tests/test_dead.py. Q08: src/rush/tools/complexity_evidence.py, src/rush/hotspots/churn.py::extract_window (additive; preserve extract_churn), src/rush/tools/complexity.py, src/rush/engines/radon.py, jscpd.py, clines.py, tests/test_complexity.py. Q09: src/rush/tools/slop.py, src/rush/engines/sloppylint.py, tests/test_slop.py (aislop.py unchanged, regression-only). Q10: src/rush/tools/markdown.py, tests/test_markdown.py. A command owner requests a change to a Foundation file as an exact patch row in 00-shared-foundation.md and never edits it.

## Order
1. 00-shared-foundation.md F1-F3, F6 (option forwarding, result contract, grants and vocabulary, parity helper).
2. Q02 R1 (shared Ruff target protocol: engines/base.py and tools/common.py patch rows, engines/ruff.py); Q03 M2 Ruff format branch is applied by Q02's Command owner after R1.
3. In parallel, one worktree each: Q01, Q03 (repairs), Q04, Q05, Q06, Q07, Q08, Q09, Q10 R/E packets.
4. F4 isolation provider, F5 selected-test helper, F7 SBOM consumer.
5. All X1 packets (Q09 has no X1 OCI dependency).
6. F8 shared docs reconciliation and F9-F11.
ADR numbers: 0050 F4 OCI isolation (F8), 0051 Q01, 0052 Q02, 0053 Q04, 0054 Q05, 0055 Q06, 0056 Q07, 0057 Q10; Q03, Q08 and Q09 add no ADR.
Every shared-file patch row is serialized through its sole writer; separate worktrees do not authorize concurrent shared-file edits. Merge/integration owner for this batch is the Foundation owner.

## Isolation calls
| Plan | timeout_s | entrypoint | image env var |
|---|---|---|---|
| Q01 | 30 | /usr/bin/python3 | RUSH_TEST_PYTHON_IMAGE |
| Q03, Q05, Q08 | 300 | image Python via run_selected_tests_isolated | RUSH_TEST_RUSH_IMAGE |
| Q04 | 180 | image Python | RUSH_TEST_RUSH_IMAGE |
| Q06 | 300 | tsc in compiler image when Q06 X1 selects OCI; otherwise PatchSandboxManager plus run_engine, no OCI call | RUSH_TEST_COMPILER_IMAGE (OCI option only) |
| Q07 | 300 | image Python via run_selected_tests_isolated | RUSH_TEST_RUSH_IMAGE |
| Q10 | 30 | /usr/local/bin/rush in Rush image; workdir_rel = fixture | RUSH_TEST_RUSH_IMAGE |
| Q05, Q08 rescans | 300 | absolute image Python, argv -m rush.cli security or complexity /work --json | RUSH_TEST_RUSH_IMAGE |
Runtime path for all: RUSH_TEST_OCI_RUNTIME (absolute path). Values shown for undecided D2/D4/D5/D6/D9/D10 are the report's proposal, not James's approval. D4 changes only Q03/Q05 selected-test timeouts; rescan timeout remains 300.
Q02 X1 minimizes Ruff without a container; non-Ruff findings return {status: skipped, reason: isolation_unavailable_for_non_ruff, analysis_runs: 0}. No F4/F5 dependency.

## Ownership matrix (resolved)
| File | Writer |
|---|---|
| src/rush/cli.py, catalog.py, config.py, mcp.py | Foundation owner |
| cli_support/catalog_commands.py, cli_support/options.py | Foundation owner |
| mcp_support/tool_registry.py, request_models.py, invocation/executor.py | Foundation owner |
| tools/routing.py, tools/common.py, engines/base.py | Foundation owner (Q02 authors the selected_targets row) |
| runtime/isolated_process.py, isolated_tests.py | Foundation owner |
| tests/test_cli_registry.py, test_mcp.py, test_isolated_process.py, test_transport_parity.py | Foundation owner |
| runtime/project_python.py (Phase 70) | unchanged; Q04 R3 reuses it |
| tools/sbom.py, tests/test_sbom.py, tests/test_routing.py | Foundation owner |
| runtime/subprocesses.py, tests/conftest.py, tests/test_no_skips.py, pyproject.toml, .github/workflows/ci.yml | Foundation owner |
| runtime/filesystem.py, tests/test_format_parity.py, tests/test_prettier_honest.py, tests/test_format_oci.py | Q03 Command owner |
| tools/dead_probe_plugin.py, tests/test_vulture_reference.py, tests/test_knip_reference.py, tests/test_static_tools.py, Knip fixtures | Q07 Command owner |
| each tool file, engine file and tests/test_<tool>.py | the Command owner listed above |
| docs/reference/{cli,mcp-tool,result}-reference.md, docs/reports/phase-64-66-documentation-coverage.md contract block, CHANGELOG.md | the packet that changes the option or route |

## Glossary
- W18: the audit's section ID for Command 45/79 `rush_mem_profile` (audit:13709); its isolation contract is implemented by F4. Phase 70's W1-W4 workstreams are unrelated.
- Ledger IDs: R repair, E ordinary extension, X novel expansion, P preservation. X1 is a plan row, not audit command X01.
- Q18: audit Command 18/79 `rush_sbom`; its consumer contract is F7.
- specialist: a connected agent-side component defined in AGENTS.md and the audit.
- selected_targets: the proposed adapter keyword defined in Q02.
- Phase 70 reconciliation: each plan's section listing requirements already implemented or changed at the implementation base.

## Decisions for James (every option delivers the full scope)
- D1 W18 and Q18 planning: plan the isolation provider and the SBOM consumer inside this batch as 00-shared-foundation.md F4 and F7 (default), or author the same content as two separate plan files W18-isolation-provider.md and Q18-sbom-consumer.md in this directory now.
- D2 Tool-level isolation option names: runtime_path and image_ref (default; matches provider kwargs and audit Q04/Q10), or isolation_runtime and isolation_image (audit Q01/Q03/Q05/Q07/Q08), applied to all ten plans.
- D3 Grant convention: each tool keeps the run() convention it has on the base, tools without grants gain permissions (default; no Phase 70 test changes), or uniform run(permissions) for all ten including migrating TypecheckTool.run and updating tests/test_phase70_t11.py, test_phase70_t12.py, test_static_tools.py, test_language_routing.py and test_subprocess_contract.py.
- D4 Isolation timeouts: Q03 and Q05 timeout_s=300 (default, unstated in the plans), or 180.
- D5 Aggregate rule: adopt Phase 70 T16 (ok plus skipped is warn, CLI exit 1; default), or change routing.aggregate_status and tests/test_phase70_t16.py so ok plus skipped stays skipped (exit 0).
- D6 Missing runtime or image vocabulary: operation block status skipped with reason isolation_unavailable (default; Q01, Q06, Q07, Q08, Q10 already), or block status isolation_unavailable (Q03, Q05 already).
- D7 Q01 R3: Phase 70 e53ea86 already removed the import cycle, so the plan keeps R3's acceptance as a regression packet and does not create src/rush/tools/registry.py (default), or creates registry.py with the same acceptance.
- D8 mypy gate: `mypy src/rush` (CI release gate; default), or `mypy .` (repo CLAUDE.md Commands).
- D9 Q07 plugin transport: F4's `scratch_on_pythonpath=True` (adds --env PYTHONPATH=/out; default), or a bootstrap `python -c` entry that inserts /out into sys.path.
- D10 Runtime acceptance (F4, all plans): (a) POSIX; supplied absolute runtime final component exactly docker or podman; realpath regular executable owned by root/current user, no group/other write bit; supplied directory and realpath outside provider root (report default). (b) same plus nerdctl. (c) runtime_path and image_ref supplied by operator config rather than tool input. Supplied symlink name, not target basename, controls allow-list.
- D11 Rush/compiler image owner: Q10 owns Containerfile, build script and version check (a), or F4 owns them (b). Both preserve full scope. X1 Q03-Q08/Q10 completes only after decision is recorded and OCI CI passes.
- D12 MCP unknown-argument rejection for remaining tools outside the ten and REQUEST_MODEL_TOOLS: extend F1 to all (a), or author separate plan in this directory (b). Both preserve full scope.

## Decision provenance and scope
No default is an approved decision. D1-D12 and command-specific choices remain for James; planning records all options now, implementation selects none implicitly. W18/F4 and Q18/F7 content stays here pending D1; no requirement is removed. Q06 X1 isolation remains open between PatchSandboxManager/run_engine and OCI. No current Phase 70 acceptance is claimed from clean Git or revision identity.
Scanner provisioning, connected specialist local models, selectable voice/live speech and 3D companion remain user-requested baseline. Ten command plans preserve applicable interfaces and grants; they are not relabeled novel expansions.

Binding clarification: C-26's complexity runtime anchoring text conflicts with C-07. F4 absolute-only validation controls: runtime_path excluded from _CWD_RELATIVE_ARGS. C-26 ownership, typed flags and target-relative trial/test inputs remain intact.

## Grounding receipt
Verified main c78e445 and clean Phase70 66c6c79 on 2026-10-01; audit digest matches binding hash. Phase70 make_tool_wrapper public_sig (tool_registry.py:333-335) includes transport fields; request_models.py:52 limits strict models to project/scan/memory; :1025-1076 currently envelopes non-memory operations. F1 adds flat command kind rather than breaking these routes. routing.aggregate_scope:377-395 reads child metadata.scope and child_entry:398-435 reads metadata.error.code; F2/F3 preserve those surfaces. tests/conftest.py:53-74 deselects unavailable engine/platform markers. scripts/sync_docs.py:59-66 preserves immutable historical bodies after leading Current status paragraph. These are source observations, not executed implementation acceptance.

## Implementation baseline exceptions (C-19)
These five reported 66c6c79 nodes require before/after identical-failure evidence if included in an implementation gate: tests/test_phase70_t5.py::test_check_example_warns_with_denied_test_step_and_runs_it_when_granted[core]; same node [full]; tests/test_no_skips.py::test_no_collected_test_carries_a_live_skip_marker; tests/test_phase70_t12.py::test_t12_pyrefly_argv_no_directory_arg_when_explicit_files; tests/test_phase70_t12.py::test_t12_typecheck_config_routes_python_family. They are reported baseline facts, not freshly executed here. Changed/new failures never enter this allow-list.


## Current-behavior verification (executed, 2026-10-01)
Phase70 .venv Python 3.12.12; inherited PYTHONPATH cleared; -B, checkout src explicitly inserted. Actual routing.aggregate_status(['ok','skipped']) returned warn; aggregate_scope complete+unavailable returned partial, only-none returned none; child_entry extracted invalid_argument from metadata.error.code. Actual make_tool_wrapper for all ten command tools retained project/result_view/limit/max_bytes/no_cache/allow_cache_write. REQUEST_MODEL_TOOLS exactly project/scan/memory. Assertions passed. This verifies current shared behavior and strict-model gap; no future command patch, isolated run, parity helper or Phase70 G0-G8 acceptance executed.

## Shared integration rows supplied by command lanes
- Q08-DOC-discovery: Foundation sets actual complexity engine_names and the exact F10 sentence; Q08 command owner supplies radon/jscpd and captured Clines adapter/fixture content. Existing static/workflow test modules are regression gates, not blanket write ownership.
- Q09-DOC-options: Foundation declares rule_config_path with ToolOptionSpec(value_type=str, path_kind="file"), four CLI options from Q09 exact patch, and F1 flat MCP fields. Q09 proposed config route uses existing resolve_tool_options only after this registration; current Q09 has no resolver call.
- Q10-DOC-cli: example_fixture uses identical CLI/MCP cwd anchoring; runtime_path passes unchanged. Q10-DOC-scope: _entry_scope excludes configuration/ignore files from consumed-source counts and retains separate configuration evidence. Q10-DOC-adr: ADR0057 plus historical leading-status/coverage changes through F8.
