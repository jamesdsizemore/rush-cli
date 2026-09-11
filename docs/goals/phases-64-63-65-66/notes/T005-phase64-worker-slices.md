# T005 — Phase 64 gap: sequenced Worker slices (Judge output)

## Corrections to T004's Scout findings (verified live this session, read-only)

T004 mischaracterized two things. Both re-verified directly before writing this task list:

1. **P64-04 CLI registration is NOT missing.** `src/rush/cli.py:1303-1345` has `@cli.group(name="patch")` / `@patch_group.command(name="apply")` — a real, wired, fully-tested command. `tests/test_patch_apply_cli.py` (5 tests) passes live against real isolated git checkouts (rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_patch_apply_cli.py -q -> `5 passed`). `src/rush/catalog.py:477` also already registers a `"patch-apply"` ToolSpec. T004's grep pattern (`patch_apply_cmd|@.*command.*patch|add_command.*patch`) missed the real decorator (`@patch_group.command(name="apply")`) because "patch" appears before "command" in that literal string, not after. Live sync_docs.py --check still reports `contracts.cli: missing registered command rush patch apply` and `contracts.catalog: missing registered command patch-apply` — but `_check_contracts()`'s message direction (`sorted(set(expected_commands) - set(saved_commands))` -> "missing registered command") means the ACTUAL live introspection has it and the RECORDED coverage-receipt doc does not. This is `stale_recorded_contract`, not `missing_feature`, for CLI and catalog.
2. **MCP registration IS genuinely missing.** `grep -n "patch" src/rush/mcp.py` -> zero hits. `contracts.mcp: missing registered command rush_patch_apply` is a true `missing_feature` gap. Governance already declares the mapping (`src/rush/governance/public_operations.py:210-215`: `"patch apply": ("rush_patch_apply", "rush.tools.patch_apply:PatchApplyTool", "stateful-mutation", "rush patch apply --help", "tool")`), so only the runtime MCP tool-manager wiring is missing, following the existing `rush_ship_clean` pattern (`src/rush/mcp.py:54-61,318,357-358`).
3. **rush_media_opt IS implemented**, resolving T004's "unresolved... do not classify with confidence" flag. `src/rush/tools/media_opt.py:20,60` has `_DTD_ENTITY_PATTERN` rejecting DOCTYPE/ENTITY before parsing, plus `_is_javascript_uri`/`_has_javascript_animation_value` stripping active content — exactly P64-16.2's GREEN requirement. Classify `rush_media_opt`'s MCP param mismatch as `stale_recorded_contract`, not `missing_feature`.
4. **P64-07, P64-15, P64-16, P64-17, P64-18, P64-20 are ALL implemented and passing**, not "unknown/unevidenced" as T004's budget-limited sampling left them. Verified live this session with a batched rtk-proxied pytest run across tests/test_media_opt.py, tests/test_license_matrix.py, tests/test_tools.py, tests/test_phase48_db_simplify_strict.py, tests/test_iam_audit.py, tests/test_offline_runner.py, tests/test_coverage_importer.py, tests/test_checkov_reference.py, tests/test_phase52_installed_artifacts.py, tests/test_providers.py, tests/test_ci_contract.py -> `148 passed`.
   - Named RED tests from the plan all exist: `test_db_drift_keeps_table_identity` (tests/test_phase48_db_simplify_strict.py:53), `test_strictify_preserves_valid_sequence_inputs` (:511), `test_locked_typescript_grammar_loads` (tests/test_error_catalog.py:170).
   - Exact license fixture cases from the plan exist verbatim in tests/test_license_matrix.py:232-246 (`(MIT OR Apache-2.0) AND GPL-3.0-only` -> strong-copyleft/HIGH/fail, etc).
   - P64-20's CI wiring is already done: `.github/workflows/ci.yml` has a build step before typecheck/tests (:40), a release-gate typecheck step (:46), the doc-sync checker wired into CI (:49), plus `engine-contracts` (:85) and `windows-contracts` (:119) jobs already exist.
5. **P64-02 is also fully done, not provisional.** All three named tests (`test_ship_clean_default_is_preview`, `test_ship_clean_requires_grant`, `test_ship_clean_preserves_unowned_and_symlink_targets`, tests/test_phase41_memory_ship.py:333,349,361) exist and pass in the full suite run below.
6. Full baseline re-confirmed live via rtk-proxied commands this session: full test suite -> `1696 passed, 5 skipped` (the 5 named real-engine skips only); lint check -> clean; format check -> clean; type check -> clean (442 files). Only failing oracle gate right now: the doc-sync checker (56 findings) and the 5 real-engine skips.

**Net effect: no packet needs new implementation except P64-04's MCP half. Everything else is evidence-writing + contract-schema regeneration + local tool installation.** This eliminates the need for a separate "investigate P64-07/15/16/17/20" Scout or Worker task — I resolved that ambiguity directly instead of creating another investigative slice.

## Pre-existing uncommitted drift (risk flag for T009)

`git status` shows `docs/CLI_REFERENCE.md`, `docs/KNOWN_ISSUES.md` (MM), `docs/SAFETY.md` (MM), `docs/safety/permissions.md` (MM), `docs/safety/safety-overview.md` (MM), `docs/phase-plans/phase-64-implementation-evidence.md`, `docs/vibecoding/the-vibecoder-workflow.md`, and `docs/reports/phase-64-66-documentation-coverage.md` already carry uncommitted edits (not from this session — pre-existing working-tree state, e.g. `phase-64-implementation-evidence.md`'s diff is exactly the already-cited P64-02 provisional section). T009 must read each file's existing diff before overwriting, not assume a clean slate. ~19 other docs are also modified but already staged and NOT in the sync-check stale-sha finding list, meaning their receipts are already consistent with on-disk content — out of scope for T009.

## Sequencing and worker tasks (append as T006-T010)

Order: T006 -> T007 -> T008 -> T009 -> T010. `rules.one_active_task: true` serializes all writes regardless of file overlap, so parallel-safety analysis is not applicable — this is a strict serial queue, not parallel dispatch. None of T006-T010 touch `src/rush/memory/{store,migration,expiry,maintenance}.py` (confirmed via allowed_files below) so the MC01/T001-T003 constraint is trivially satisfied.

### T006 (worker) — Real-engine acceptance
Install mutmut 3.7.0, atheris 3.1.0, pact-python-cli 2.6.0.1 via uv pip install; install k6 v2.2.0 from its official release archive with SHA-256 verification (per plan lines matching "Real-engine acceptance dependencies"), on PATH for this shell. Then run with RUSH_REQUIRE_REAL_ENGINES=1 against tests/test_executed_modes.py -k real_workload; every named real-workload test must pass for real (no skip). Fix whatever the adapters in src/rush/tools/{mutation,fuzz,load,contract}.py actually need to make these pass against real installed engines — this may surface real bugs the tests exist to catch (e.g. wrong CLI args, wrong report path parsing). Never weaken an assertion to fake a pass.
- allowed_files: `tests/test_executed_modes.py`, `src/rush/tools/mutation.py`, `src/rush/tools/fuzz.py`, `src/rush/tools/load.py`, `src/rush/tools/contract.py`
- verify:
  - `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -c "import atheris"` (module import proof)
  - `rtk proxy which mutmut pact-provider-verifier k6`
  - `RUSH_REQUIRE_REAL_ENGINES=1 rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_executed_modes.py -q -k "real_workload or required_engine_absence or required_atheris_module_absence"`
  - `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/ruff check src/rush/tools tests/test_executed_modes.py`
  - `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/ruff format --check src/rush/tools tests/test_executed_modes.py`
  - `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m mypy src/rush`
  - `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/ -q` (full-suite regression, no RUSH_REQUIRE_REAL_ENGINES)
- stop_if:
  - k6's release archive cannot be downloaded because this environment has no network egress to GitHub releases -- that is a genuine named external blocker per the plan's own text, not something to route around; report it exactly, do not fake success.
  - mutmut/atheris/pact-python-cli fail to install via PyPI access for the same reason.
  - A real_workload test fails for a reason other than the named engine being absent (a real product bug) and a fix isn't obviously safe within these files.
  - Need to touch a file outside allowed_files.
  - Verification fails twice after a genuine fix attempt.

### T007 (worker) — P64-04: MCP registration for patch-apply
Register rush_patch_apply in src/rush/mcp.py following the exact existing wrapper pattern used for rush_ship_clean (src/rush/mcp.py:54-61,318,357-358), wrapping rush.tools.patch_apply.PatchApplyTool per governance's existing mapping (src/rush/governance/public_operations.py:210-215, read-only reference, no edit expected). Add/extend MCP-level test coverage in tests/test_mcp.py exercising the new tool route. Append P64-04's own evidence.md section (RED/GREEN/VERIFY, frozen source+test SHA-256, following the exact format already used for the existing P64-00/P64-01/P64-02 sections) documenting that CLI (rush patch apply) and catalog registration were already implemented and tested pre-existing (cite tests/test_patch_apply_cli.py, 5 passing), and that this task adds the MCP half.
- allowed_files: `src/rush/mcp.py`, `tests/test_mcp.py`, `docs/phase-plans/phase-64-implementation-evidence.md`
- verify:
  - `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_mcp.py tests/test_patch_apply_cli.py -q`
  - `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/ruff check src/rush/mcp.py tests/test_mcp.py`
  - `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/ruff format --check src/rush/mcp.py tests/test_mcp.py`
  - `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m mypy src/rush`
  - `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/ -q` (full-suite regression)
- stop_if:
  - Governance (public_operations.py/public-operations.toml) needs an actual edit to gate the new tool correctly -- both are outside allowed_files; stop and report instead of expanding scope.
  - PatchApplyTool's constructor/call signature doesn't fit the rush_ship_clean-style wrapper without a design decision (e.g. different permission-argument shape).
  - Verification fails twice after a genuine fix attempt.

### T008 (worker) — Evidence-writing pass (all remaining implemented-but-unevidenced packets)
Depends on T006 and T007 being done first (needed for accurate P64-08-11 and cross-references). For each of P64-02 (finalize -- replace the "provisional... does not mark complete" caveat now that its three named tests pass), P64-03, P64-05, P64-06, P64-07, P64-08, P64-09, P64-10, P64-11, P64-13, P64-14, P64-15, P64-16, P64-17, P64-18, P64-19, P64-20: read that packet's own numbered VERIFY step in docs/phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md, run its exact command(s), compute SHA-256 for every source/test file its GREEN step names, and append one evidence.md section per packet in the exact format already used for the existing P64-00/P64-01/P64-02 entries (frozen source/test SHA-256 line, RED/GREEN/VERIFY command lines with real pass counts, one-paragraph requirement mapping). P64-08 through P64-11's sections must cite T006's real-workload results (now passing under RUSH_REQUIRE_REAL_ENGINES=1), not the old skip caveat. Do not touch or duplicate P64-04's section (owned by T007). Do not alter existing P64-00/P64-01 content. Never write a passing claim without having actually run the cited command this task.
- allowed_files: `docs/phase-plans/phase-64-implementation-evidence.md`
- verify:
  - `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/ -q` (full-suite regression -- confirms nothing broke while gathering evidence)
  - `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_media_opt.py tests/test_license_matrix.py tests/test_tools.py tests/test_phase48_db_simplify_strict.py tests/test_iam_audit.py tests/test_offline_runner.py tests/test_coverage_importer.py tests/test_checkov_reference.py tests/test_phase52_installed_artifacts.py tests/test_providers.py tests/test_ci_contract.py tests/test_ai_eval.py tests/test_prompt_eval.py tests/test_provenance_ai.py tests/test_cold_start.py tests/test_mem_profile.py tests/test_staged_scan_bytes.py tests/test_phase41_memory_ship.py tests/test_agent_governance.py tests/test_mutation.py tests/test_fuzz.py tests/test_load.py tests/test_contract.py tests/test_error_catalog.py -q` (spot-check every packet's own test file)
- stop_if:
  - A named VERIFY command from the plan fails for any packet -- that packet is NOT actually done; stop and report exactly which one, never write a false evidence claim.
  - T006 or T007's changes are not present in the working tree yet.
  - Verification fails twice after a genuine fix attempt.

### T009 (worker) — Contract-drift repair + coverage-receipt regeneration + P64-00 re-freeze (final content slice)
Depends on T006, T007, T008 all done (this must run last so document SHA-256 values are computed against final content). Regenerate the embedded rush-doc-coverage-v1 JSON block in docs/reports/phase-64-66-documentation-coverage.md: (1) recompute the contracts object (cli/mcp/catalog) to exactly match live collect_runtime_contracts() output -- this closes ship-clean, test-heal, patch-apply (CLI+catalog+MCP), media_opt, and every other MCP param mismatch (rush_benchmark, rush_cold_start, rush_contract, rush_fuzz, rush_load, rush_mem_profile, rush_mutation, rush_prompt_eval, rush_ship_clean, rush_tui_diff); (2) for every docs/ file whose on-disk content changed this Stage-1 tranche (docs/CLI_REFERENCE.md, docs/MCP_REFERENCE.md, docs/SAFETY.md, docs/safety/permissions.md, docs/safety/safety-overview.md, docs/vibecoding/the-vibecoder-workflow.md, docs/KNOWN_ISSUES.md, docs/phase-plans/phase-64-implementation-evidence.md) -- read each file's existing git diff first, reconcile rather than blindly overwrite -- update its sha256/immutable_body_sha256 entry to match on-disk bytes; (3) append a final P64-00 note to phase-64-implementation-evidence.md confirming the doc-sync checker now exits 0. Do not touch any doc's receipt entry for a file this task did not itself modify unless the doc-sync checker still names it stale after (1) and (2).
- allowed_files: `docs/reports/phase-64-66-documentation-coverage.md`, `docs/phase-plans/phase-64-implementation-evidence.md`, `docs/CLI_REFERENCE.md`, `docs/MCP_REFERENCE.md`, `docs/SAFETY.md`, `docs/safety/permissions.md`, `docs/safety/safety-overview.md`, `docs/vibecoding/the-vibecoder-workflow.md`, `docs/KNOWN_ISSUES.md`
- verify:
  - `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python scripts/sync_docs.py --check` (must exit 0)
  - `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/ -q` (full-suite regression)
  - `RUSH_REQUIRE_REAL_ENGINES=1 rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_executed_modes.py -q -k real_workload` (confirms T006's fix still holds)
- stop_if:
  - Any of the pre-existing uncommitted edits in the listed docs conflict with what the doc-sync checker demands -- stop and report the conflict rather than guessing which version is authoritative.
  - The doc-sync checker still fails after (1) and (2) for a reason that isn't a simple sha/contract sync (e.g. a genuine missing link or genuinely missing coverage entry for a file outside this task's scope).
  - Verification fails twice after a genuine fix attempt.

### T010 (judge) — Stage-1 Phase-64 gap-closure review (before Stage 1's final gate)
Adversarially review T006-T009 together before Stage 1's oracle is declared green: independently re-run goal.md's full oracle signal block verbatim (its own stored command chain: full test suite, lint check, format check, type check, doc-sync checker), plus a separate RUSH_REQUIRE_REAL_ENGINES=1 pytest tests/test_executed_modes.py -k real_workload pass to confirm zero real-engine skips remain (or, if T006 hit a genuine named external blocker such as no network egress for k6, confirm that blocker is honestly documented rather than faked past). Verify every evidence.md section T007/T008 added cites real, independently-reproducible command output -- not fabricated pass counts. Verify docs/reports/phase-64-66-documentation-coverage.md's contracts JSON exactly matches live collect_runtime_contracts(). Verify no assertion anywhere was weakened to manufacture a pass. Decision: integrated | needs_fix, with an exact objective for a fix task if needed.
- inputs: T006/T007/T008/T009 receipts, `docs/phase-plans/phase-64-implementation-evidence.md`, `docs/reports/phase-64-66-documentation-coverage.md`, goal.md's oracle block.
- receipt: null (to be filled by Judge at execution time)

## File-conflict ordering

| file | order |
|---|---|
| docs/phase-plans/phase-64-implementation-evidence.md | T007 -> T008 -> T009 |
| docs/reports/phase-64-66-documentation-coverage.md | T009 (sole writer) |
| src/rush/mcp.py, tests/test_mcp.py | T007 (sole writer) |
| tests/test_executed_modes.py, src/rush/tools/{mutation,fuzz,load,contract}.py | T006 (sole writer) |
| docs/CLI_REFERENCE.md, docs/MCP_REFERENCE.md, docs/SAFETY.md, docs/safety/permissions.md, docs/safety/safety-overview.md, docs/vibecoding/the-vibecoder-workflow.md, docs/KNOWN_ISSUES.md | T009 (sole writer) |

No task in this set touches `src/rush/memory/{store.py,migration.py,expiry.py,maintenance.py}` -- confirmed by allowed_files above containing none of those paths.

## Blocked or deferred

None dropped silently. One real open contingency, not a defect: T006 may discover k6's release archive (GitHub) or PyPI access for mutmut/atheris/pact-python-cli is blocked by this sandbox's network policy. That is a genuine named external blocker per the plan's own acceptance text ("unavailable installation/network permission is an explicit external blocker, not a skipped acceptance") -- T006's stop_if covers it explicitly; if it triggers, T008/T009/T010 must document it as a named blocker rather than treat Stage 1 as fully green.
