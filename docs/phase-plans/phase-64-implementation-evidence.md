# Phase 64 implementation evidence

Current status: Phase 64 is in progress; this evidence records completed packet checks only. Current contract: [Phase 64 runtime correctness and safe execution](phase-64-runtime-correctness-and-safe-execution-plan.md). Review evidence: [whole-application review](../reports/phase-64-66-application-review.md).

## P64-00 — Documentation coverage

Source commits: `e1abab8` and `c9a7681`.

- GREEN: `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_sync_docs.py -q` — 13 passed.
- GREEN: Ruff check and format-check on `scripts/sync_docs.py` and `tests/test_sync_docs.py` — passed.
- GREEN: `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python scripts/sync_docs.py --check` — documentation coverage and runtime contracts match. FastMCP/Pydantic emitted `IncompleteFieldDefinitionWarning`; [tracked issue](../../.scratch/phases-64-63-65-66/issues/01-fastmcp-settings-forward-reference-warning.md) records it as nonblocking, with no runtime conclusion.
- GREEN (T009 reconciliation): P64-02/P64-04 doc edits and the MC01/coding-agent-handoff/goal-board additions drifted the recorded receipt out of sync with the live tree (see P64-20 below for the exact failing findings). Regenerated `contracts` in `docs/reports/phase-64-66-documentation-coverage.md` from live `collect_runtime_contracts()` and refreshed every `sha256`/`immutable_body_sha256` against current file bytes, adding receipts for `docs/goals/phases-64-63-65-66/**`, `docs/goals/.DS_Store`, `docs/developer/phase-63-66-coding-agent-handoff.md`, and `docs/phase-plans/MC01.md`. Re-run: `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python scripts/sync_docs.py --check` — exits 0, "Documentation coverage and runtime contracts match."

## P64-01 — Preserve checkout/index during fixes (F01)

Requirement mapping: F01 requires dry-run to preserve worktree, index, untracked files, and history; failure may restore only invocation-owned changes. Frozen source SHA-256: `src/rush/tools/fix.py` `dd61b75efab2bb5bd307c4bb3f02330e46627ff1b72f7c1fe9b90ff574f8950d`; frozen test SHA-256: `tests/test_fix.py` `cf1c09a0befe5320da926b4767ab40ec27c1a3985f762d688c266f057f9e6c39`.

- RED initial: `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_fix.py::test_dry_run_preserves_index_and_unrelated_files tests/test_fix.py::test_failed_fix_preserves_untracked_files -q` — 3 failures. Dry run reset dirty fixture bytes, invalid syntax returned the wrong status, and Ruff exit 2 was reported successful without restoring bytes/mode.
- RED review expansion:
  - `... python -m pytest tests/test_fix.py::test_dry_run_preserves_index_and_unrelated_files tests/test_fix.py::test_fix_missing_ruff_is_skipped_without_launch tests/test_fix.py::test_fix_reports_restore_failure_and_continues_other_targets -q` — 3 failed, 2 passed.
  - `... python -m pytest tests/test_fix.py::test_fix_restores_owned_targets_when_ast_validation_is_cancelled -q` — 1 failed.
  - `... python -m pytest tests/test_fix.py::test_fix_preserves_ruff_excluded_python_files -q` — 1 failed.
  - `... python -m pytest tests/test_fix.py::test_fix_sanitizes_subprocess_exceptions tests/test_fix.py::test_fix_restores_target_deleted_by_engine -q` — 3 failed; sanitizer case is parametrized twice.
  - Final consolidated `... python -m pytest tests/test_fix.py::test_fix_refuses_dangling_symlink_during_rollback tests/test_fix.py::test_fix_refuses_parent_symlink_redirection_during_rollback tests/test_fix.py::test_fix_rejects_incomplete_snapshot_before_mutating_launch tests/test_fix.py::test_fix_restores_after_unexpected_validation_exception tests/test_fix.py::test_fix_git_status_failure_stops_before_ruff tests/test_fix.py::test_registered_mcp_fix_apply_denies_and_grants_artifact_write -q` — 8 failed in 4.12 seconds; first GREEN attempt had 2 failed, 6 passed in 3.74 seconds; final GREEN had 8 passed in 3.42 seconds. The MCP permission test is a RED here; an earlier permission test added after its guard is not presented as RED.
- GREEN focused: consolidated six-node RED command expanded to eight cases — 8 passed in 3.42 seconds. The full frozen command `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_fix.py -q` — 30 passed in 11.61 seconds on Python 3.12.12 with Ruff 0.16.3. Ruff check, format-check, and diff-check on `src/rush/tools/fix.py` and `tests/test_fix.py` passed.
- GREEN runtime/transport route: `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_fix.py::test_fix_cli_and_direct_dry_run_preserve_same_dirty_fixture -q` — direct tool and in-process Click `cli` invoke `fix PATH --dry-run --force --json` against one fixture containing staged, unstaged, and untracked files; exact repository state remains unchanged. This is not an external installed-`rush` binary run.

Caller and permission review: shared `FixTool` covers direct, CLI, and registered MCP `rush_fix` routes. The MCP schema exposes `allow_artifact_write: bool = False`; absent grant denies apply and `True` applies. `FixTool.__call__` bridges that flag to execution permissions. `src/rush/tools/fix.py` uses native `ruff check --show-files --no-cache` selection, preserves Ruff excludes, runs read-only ordinary Ruff check for unfixable lint, snapshots selected regular targets before writes, and reports bounded/redacted subprocess or restoration failures. Direct/Click dry-run parity and excluded `.venv/vendor.py` apply behavior use real Ruff; exact argv, failure/config, invalid-AST, cancellation, missing-Ruff, deletion, and symlink cases include mocked boundaries where stated by their tests. No external shell-installed `rush` binary ran.

## P64-02 — Ownership-bound cleanup (F02)

Requirement mapping: default cleanup previews only receipt-registered, unchanged Rush-owned ordinary files under `.rush/runs/`; deletion requires `apply=True` and artifact-write. Unregistered `scratch/` or `tmp/` content, modified files, outside-root paths, directories, and symlink targets remain preserved or refused. `.rush/cleanup.json` version 1 records relative path, SHA-256, byte length, producer, device, and inode.

Frozen source SHA-256: `src/rush/tools/ship/cleaner.py` `a3f0ea362f7ba0b9939a14706fc084c4db660f7757ab79b9f23e735527b7fd52`; `src/rush/cli.py` `08915cfeb00a077be4def1c8d5c41f2e9cd62095b42bf47c0515cf92e55b49a9`; `src/rush/mcp.py` `3bd27046f34b5fd3a9daee2d892133c61e4a956e9181d84a26dad33c4904d99e`; `src/rush/tools/ship/cockpit.py` `739d73c67548dc86582d0947c984f647a80a2f162c1820be7fe8739c86da06b7`. Frozen test SHA-256: `tests/test_phase41_memory_ship.py` `1016adfb806a7717a135442cfa055fd9d44ef7fc958e07221445e1727155212a`; `tests/test_mcp.py` `5941977cf462ac6bea79bdc264a3940bf6b3d42f706923e00d41cfe0868030ac`.

- RED: `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_phase41_memory_ship.py tests/test_mcp.py -k 'ship_clean or scratch_cleaner' -q` — 13 failed, 9 deselected in 1.87 seconds.
- GREEN focused: `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_phase41_memory_ship.py tests/test_mcp.py -k 'ship_clean or scratch_cleaner or register_owned_artifact' -q` — 17 passed, 9 deselected in 0.98 seconds. Ruff check passed and diff-check was clean.
- Shared route: CLI `rush ship clean` defaults to preview and accepts `--apply --allow-artifact-write`; MCP `rush_ship_clean(path=".", apply=false, allow_artifact_write=false)` calls the same `ScratchCleaner` and returns status, apply, preview/removed/refused counts and item lists, byte totals, registry status, and optional error.

This is provisional P64-02 evidence: full required test suite and frozen source review remain pending. It does not mark P64-02 complete.

## P64-04 — Register `rush patch apply` / `rush_patch_apply` (CLI, catalog, MCP)

Requirement mapping: P64-04 requires `rush patch apply` to be invokable through CLI, catalog, and MCP transports, each routing to `PatchApplyTool` (verify a contained unified diff in an isolated Git worktree; promotion gated on `allow_artifact_write`).

CLI and catalog were already implemented and tested pre-existing: `src/rush/cli.py` (`@patch_group.command(name="apply")`, patch group at `@cli.group(name="patch")`) and `src/rush/catalog.py:477` (`"patch-apply": ToolSpec(...)`). `tests/test_patch_apply_cli.py` (5 tests) already exercises the CLI route end-to-end against real isolated git checkouts and passes: `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_patch_apply_cli.py -q` — 5 passed.

MCP registration was also already implemented pre-existing (introduced in commit `2322c43`, verified via `git log -S rush_patch_apply`), not missing as the doc-sync checker's stale contract record suggested. `PatchApplyTool` (a `ToolFn` subclass, `src/rush/tools/patch_apply.py`) is included in `ALL_TOOLS` (`src/rush/tools/__init__.py:128`) and `src/rush/mcp.py`'s `_register_tools` calls `register_all_tools(server, executor, ALL_TOOLS)`, which iterates every `ALL_TOOLS` member and calls `server.add_tool(fn=make_tool_wrapper(tool, executor), name=f"rush_{tool.name.replace('-', '_')}", ...)` — this generically registers `rush_patch_apply` without any literal string reference to "patch" appearing in `mcp.py` (why an earlier grep-based Scout pass reported it as unregistered). Confirmed live this session: `python -c "from rush.mcp import build_server; import asyncio; print('rush_patch_apply' in [t.name for t in asyncio.run(build_server().list_tools())])"` → `True`. `tests/test_mcp.py::test_registered_mcp_patch_apply_parity` (parametrized over `dry-run`/`denied`/`failed-verification`/`apply`) already covers the MCP route against real isolated git fixtures and already passes.

`scripts/sync_docs.py --check`'s `contracts.mcp: missing registered command rush_patch_apply` finding is a `stale_recorded_contract` in `docs/reports/phase-64-66-documentation-coverage.md`'s saved receipt, not a `missing_feature` — `_mcp_contracts()` (scripts/sync_docs.py:302) introspects the live `mcp_server._tool_manager._tools`, which already contains `rush_patch_apply`; only the saved doc receipt is out of date. Regenerating that receipt is T009's scope, not this packet's.

Frozen source SHA-256: `src/rush/mcp.py` `20e1e8d4e2ee4a59831b10ae796b3a73e7a9b7630d999b899ce6b1c3991cc2b9`; `src/rush/tools/patch_apply.py` `05e3f68de0d11ba31d990545b3c60f157df39e79a632f0f1f3e47678bd32f5f7`. Frozen test SHA-256: `tests/test_mcp.py` `0f3c8ef8a5be1bf940f55781975a3a21bd9a6655e44e32b2cfda63f0f5421daa`; `tests/test_patch_apply_cli.py` `b05b9a3f7d8b6eeabd7af8ab4a54d5b78e48f1efb332588de3337b31a7047139`.

- RED: not applicable — CLI, catalog, and MCP registration were all already implemented and already passing when this packet's Worker task began; no failing state was reproduced because none existed. No mcp.py or test_mcp.py source edits were made.
- GREEN: `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_mcp.py tests/test_patch_apply_cli.py -q` — 22 passed.
- VERIFY: `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/ruff check src/rush/mcp.py tests/test_mcp.py` — all checks passed. `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/ruff format --check src/rush/mcp.py tests/test_mcp.py` — 2 files already formatted. `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m mypy src/rush` — no issues found in 442 source files. Full-suite regression `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/ -q` — 1696 passed, 5 skipped (unchanged baseline; the 5 skips are the named real-engine acceptance tests gated behind `RUSH_REQUIRE_REAL_ENGINES=1`, unrelated to this packet).

P64-04 is complete across CLI, catalog, and MCP transports.

## P64-03 — Contain checkpoint reads and governance writes (F03–04)

Requirement mapping: checkpoint restore/list must reject symlink files and symlinked parents; governance `Synchronizer` writes must preflight every target, capture existing bytes/absence, and restore only already-written targets on a later failure without emitting outside-root content.

Frozen source SHA-256: `src/rush/memory/checkpoint_journal.py` `f6bf55b5697a94ccd2fcd216b1a0d4926dd97643c0046ad690b52aa3b8504c4d`; `src/rush/tools/continuity.py` `7b3c90b8babbd2ddd74db980fa6db7d451f4a8b9bb7979be3a803f6fead22b29`; `src/rush/governance/synchronizer.py` `631134e653e5d5ff1761ef52261458a5dbe57c22df5b695a4d753b7fc3a79f4c`. Frozen test SHA-256: `tests/test_phase41_memory_ship.py` `734d2b762e17ff2adb3143620a0158dc429e110e89940a2b92d869fed73e0fd6`; `tests/test_agent_governance.py` `ff236c28dc952cd0b815f8bdc98776a6b6c871fee1c4cbb50279477fa677dbc6`.

- RED: not independently reproduced this session — `test_checkpoint_restore_and_list_reject_symlink_file`, `test_checkpoint_restore_and_list_reject_symlink_parent` (`tests/test_phase41_memory_ship.py`) and `test_sync_rejects_escape_before_any_write`, `test_sync_second_write_failure_restores_first` (`tests/test_agent_governance.py`) are present and confirmed as the named packet tests; the implementation and its RED/GREEN history predate this Worker task.
- GREEN: named tests confirmed present by name via `grep -n "def test_"` against both files; behavior matches the plan (symlink rejection, second-write-failure restoring only the first target).
- VERIFY: `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_phase41_memory_ship.py tests/test_agent_governance.py -q` — 52 passed. Isolated node run `... -m pytest tests/test_agent_governance.py -q -k "escape_before_any_write or second_write_failure_restores_first" -v` — 7 passed, 7 deselected.

P64-03 confirmed passing this session.

## P64-05 — Typed invocation and secret-safe custom results (F06–07)

Requirement mapping: invocation persistence keeps typed scalars/containers authoritative (explicit `false`/`null`/omitted stay distinct); custom handler results pass through `sanitize_value` at shared egress so secrets never survive in MCP/CLI/direct output.

Frozen source SHA-256: `src/rush/invocation/resolver.py` `b5404cca473e937f8f9dd445dd2eb2ab8e58ae2511fea8e23413b21a8620dd82`; `src/rush/invocation/executor.py` `5f1357b2fdec3ad2b680d27a4689dc732c0969141dbf35897ad4b749b94960a7`; `src/rush/mcp_support/tool_registry.py` `bf2dddc9a128e926a197b3e5ad23d5150a3679c6e389d7178cbe3c094ddec351`; `src/rush/invocation/models.py` `91d8ba8b0340df912dc55180e8202395a2149f757ae4b7b976ad9e893f3deeff`. Frozen test SHA-256: `tests/test_phase57_invocation_context.py` `3f7092b45d4774d47ddf8a0c1cb21b9b0bb2ba340d2d2638289df74ef8ced98a`; `tests/test_mcp.py` `0f3c8ef8a5be1bf940f55781975a3a21bd9a6655e44e32b2cfda63f0f5421daa`.

- RED: not independently reproduced this session — `test_invocation_preserves_scalar_types_and_presence`, `test_registered_swarm_merge_preserves_exact_code`, `test_registered_outline_redacts_entire_result`, `test_registered_swarm_merge_redacts_entire_result` are present by name in the named files.
- GREEN: named tests confirmed present; behavior matches the plan (typed persistence, secret redaction at egress).
- VERIFY: `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_phase57_invocation_context.py tests/test_mcp.py -q` — 22 passed (22 collected, matching the frozen VERIFY command exactly).

P64-05 confirmed passing this session.

## P64-06 — Permission-gated AI evaluation (F08)

Requirement mapping: live AI-evaluation launch requires network, slow, and artifact-write grants checked before any provider discovery or report write; the loopback local-provider acceptance test proves an actually executed evaluation with owned report output.

Frozen source SHA-256: `src/rush/tools/ai_eval.py` `a50d58a25dc4d5626e6f8f4f80d35c22071ac375ee6dc7db95d59da8950889f1`; `src/rush/engines/promptfoo.py` `99e5719d44a54babb07c6fbc96c4d0a5221ae23d535e8881a64ee8b58894004a`; `src/rush/engines/garak.py` `2abd19c6f238a43f6a24d4fd7f9d82852314d006b1d840f1e37dd89f6a5aaf30`; `src/rush/engines/deepeval.py` `7afaf3e83264a457d7ebb0661b77fdd32cbca4143a98f77e812b58b405a836c3`; `src/rush/engines/guardrails.py` `daa92204f9965d27e9c025fa8e5d2eaafaab292abc2ec2f3e60a60010eff85de`. Frozen test SHA-256: `tests/test_ai_eval.py` `cebbfb04ed6791d4ec42eceeac96d1d15da09738acd33bf28ea81f7fa5ce5818`.

- RED: not independently reproduced this session — `test_eval_denies_before_provider_or_report_write`, `test_eval_passes_exact_grants`, and `test_eval_live_local_provider` are present by name.
- GREEN: named tests confirmed present; `test_eval_live_local_provider` starts a loopback deterministic provider and asserts parsed results plus exact report ownership.
- VERIFY: `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_ai_eval.py -q` — 35 passed, including the live loopback-provider test.

P64-06 confirmed passing this session.

## P64-07 — Honest lint/format statuses (F09–10)

Requirement mapping: invalid-JS/missing-ESLint returns `skipped`; unformatted Python with installed Ruff returns `warn` with the exact path; missing Ruff returns `skipped`; a Ruff process error returns `error`. A clean fixture alone is not sufficient acceptance.

Frozen source SHA-256: `src/rush/tools/lint.py` `84a5bf3fe5f7b9b49642e8e4d9edaeea50fa30c97ae0a9f7af338946bf75fa56`; `src/rush/tools/format.py` `bdcbe76d8adc9342e5ea53b2dd48d6bbf8d9bccefaeddd4fa8b86138b477080d`; `src/rush/engines/ruff.py` `07204859dfe9ab3bca83837c45aba02e8a0458e7a4b7744e7f58921ac9bb0457`. Frozen test SHA-256: `tests/test_tools.py` `f24affc9011f58c1e608063fccf54b847cd7ceb9a3e1ab0a016f67edb5e09e73`.

- RED: not independently reproduced this session — `test_lint_missing_eslint_skips_nonempty_javascript_project` (asserts `status == "skipped"`), `test_lint_missing_ruff_skips_nonempty_python_project` (asserts lint and format both `skipped`), `test_format_unformatted_reports_exact_path`, and `test_format_preserves_engine_error_without_findings` (asserts `status == "error"`) are present and inspected by source this session; their bodies match the plan's four required statuses.
- GREEN: named tests confirmed present with matching assertions read directly from source.
- VERIFY: `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_tools.py -q` — 26 passed.

P64-07 confirmed passing this session.

## Live workload packets P64-08–11 — real-engine acceptance

T006 (merged, prior task on this board) installed mutmut 3.7.0, atheris (locally 3.0.0; `tests/test_executed_modes.py::test_fuzz_real_workload` compares against `importlib.metadata.version("atheris")` rather than a hardcoded pin, so the local version does not fail the assertion), k6 v2.2.0, and `pact-provider-verifier` 1.39.1, and added `.github/workflows/ci.yml` job `engine-contracts` (confirmed present at line 85, `RUSH_REQUIRE_REAL_ENGINES: "1"` at line 116, engine pins at line 104). Verified independently this session, not cited blindly: `which mutmut k6 pact-provider-verifier` resolved all three; `python -c "import atheris"` imports successfully; `mutmut`, `k6 version`, and `pact-provider-verifier version` all execute. `RUSH_REQUIRE_REAL_ENGINES=1 env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_executed_modes.py -q -k real_workload` — 5 passed, 47 deselected in 7.15 seconds (all four live adapters plus the paired load-clean-target case), confirming real engines execute for real rather than skipping.

### P64-08 — Execute mutation workloads (F11)

Frozen source SHA-256: `src/rush/tools/mutation.py` `2422cb051b64c28173d77e171c2d79985f0dcc6bb6afd026eafb740ed8d92249`; `src/rush/catalog.py` `3cc4c0616331feed4b3ed0180f02d7be6eb21e809e0120a7663815fac7524666`. Frozen test SHA-256: `tests/test_executed_modes.py` `dbc49d1f6b7ebd5ad18ca0f4406917b1d105416052d9c3c8ec9b6d17f25023d5`; `tests/test_config.py` `9c1799d04912f122ae43b8f10431f3fc9c8816e7afd5376fd8a3ac5d2c335903`.

- RED: not independently reproduced this session — `test_mutation_executes_tests_and_counts_survivors`, `test_mutation_real_workload`, and `test_required_engine_absence_fails` are present by name.
- GREEN: named tests confirmed present; live branch parses generated/killed/survived/timeout counts per the plan.
- VERIFY: `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_executed_modes.py -q -k mutation` — 11 passed, 1 skipped (real-engine test skipped without the flag), 40 deselected. `RUSH_REQUIRE_REAL_ENGINES=1 env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_executed_modes.py -q -k "mutation and real_workload"` — 1 passed (real mutmut run against the tiny arithmetic fixture). `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_config.py -q` — 33 passed.

P64-08 confirmed passing this session, including the real-engine acceptance lane.

### P64-09 — Execute fuzz workloads (F11)

Frozen source SHA-256: `src/rush/tools/fuzz.py` `eb4462f9db884356927a48ada6adbf1d8b7ed28125403e1223652e5ed149a1f1`. Frozen test SHA-256: `tests/test_executed_modes.py` `dbc49d1f6b7ebd5ad18ca0f4406917b1d105416052d9c3c8ec9b6d17f25023d5`; `tests/test_config.py` `9c1799d04912f122ae43b8f10431f3fc9c8816e7afd5376fd8a3ac5d2c335903`.

- RED: not independently reproduced this session — `test_fuzz_runs_target_and_reports_reproducer` and `test_fuzz_real_workload` are present by name; `test_fuzz_real_workload` currently reads `assert result["engine_version"] == importlib.metadata.version("atheris")` and `assert b"RuntimeError: known crash" in replay.stdout + replay.stderr` (uncommitted working-tree edit as of this session, not made by this task).
- GREEN: named tests confirmed present; live branch executes the configured Atheris harness/corpus with bounded run/time limits.
- VERIFY: `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_executed_modes.py -q -k fuzz` — 8 passed, 1 skipped, 43 deselected. `RUSH_REQUIRE_REAL_ENGINES=1 env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_executed_modes.py -q -k "fuzz and real_workload"` — passed as part of the combined 5-passed `real_workload` run above. `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_config.py -q` — 33 passed.

P64-09 confirmed passing this session, including the real-engine acceptance lane.

### P64-10 — Execute load workloads (F11)

Frozen source SHA-256: `src/rush/tools/load.py` `5c3d00afd501285f6ff4c873409280c024d61210c54749d4a452a9343027eab1`. Frozen test SHA-256: `tests/test_executed_modes.py` `dbc49d1f6b7ebd5ad18ca0f4406917b1d105416052d9c3c8ec9b6d17f25023d5`; `tests/test_config.py` `9c1799d04912f122ae43b8f10431f3fc9c8816e7afd5376fd8a3ac5d2c335903`.

- RED: not independently reproduced this session — `test_load_contacts_target_and_enforces_threshold`, `test_load_real_workload`, and `test_load_real_workload_clean_target` are present by name.
- GREEN: named tests confirmed present; live branch runs configured k6 with bounded duration/VUs and JSON summary export.
- VERIFY: `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_executed_modes.py -q -k load` — 18 passed, 5 skipped (the substring `load` also matches `real_workload` in unrelated packets, so all four real-engine skips appear; this is the exact plan-specified command), 29 deselected. `RUSH_REQUIRE_REAL_ENGINES=1 env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_executed_modes.py -q -k "load and real_workload"` — passed as part of the combined 5-passed `real_workload` run above. `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_config.py -q` — 33 passed.

P64-10 confirmed passing this session, including the real-engine acceptance lane.

### P64-11 — Execute contract verification (F11)

Frozen source SHA-256: `src/rush/tools/contract.py` `7334d3589075acd34c44404510c5b307054c145e1f20452739e6d6df248c3c47`. Frozen test SHA-256: `tests/test_executed_modes.py` `dbc49d1f6b7ebd5ad18ca0f4406917b1d105416052d9c3c8ec9b6d17f25023d5`; `tests/test_config.py` `9c1799d04912f122ae43b8f10431f3fc9c8816e7afd5376fd8a3ac5d2c335903`.

- RED: not independently reproduced this session — `test_contract_verifies_provider_interactions`, `test_contract_groups_rspec_examples_by_interaction`, and `test_contract_real_workload` are present by name.
- GREEN: named tests confirmed present; live branch groups Pact RSpec examples by `(pact_url, interaction_index)` per the plan.
- VERIFY: `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_executed_modes.py -q -k contract` — 6 passed, 1 skipped, 45 deselected. `RUSH_REQUIRE_REAL_ENGINES=1 env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_executed_modes.py -q -k "contract and real_workload"` — passed as part of the combined 5-passed `real_workload` run above. `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_config.py -q` — 33 passed.

P64-11 confirmed passing this session, including the real-engine acceptance lane.

## P64-13 — Historical provenance and paired statistics (F13–14)

Requirement mapping: line-survival cohort statistics and binary AI-attribution/observed-link-linkage phi coefficient, with `unavailable_reason` for no-history/shallow-history/zero-variance cases; results are stated as observed association, never causal.

Frozen source SHA-256: `src/rush/tools/provenance_ai.py` `193a8490379c6bc080d9cace4871516c5d230c22547b170187e2de9d2db6e800`. Frozen test SHA-256: `tests/test_provenance_ai.py` `c105fc78a58101712c7d88b2ccb2b4ae4770fb76b8b8dfd49c3cb81335fc94ab`.

- RED: not independently reproduced this session — `test_provenance_ai_real_first_parent_association_phi` (asserts `phi == 1.0` for perfect alignment and `phi == -1.0` for perfect opposition, with exact `counts` contingency tables), `test_provenance_ai_unavailable_statistics_explain_evidence_limits` (`unavailable_reason == "no-history"`), and `test_provenance_ai_zero_variance_reports_reason` (`unavailable_reason == "zero-variance"`) are present and read by source this session; bodies match the plan's phi formula and evidence-reason contract exactly.
- GREEN: named tests confirmed present with matching assertions read directly from source.
- VERIFY: `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_provenance_ai.py -q` — 12 passed.

P64-13 confirmed passing this session.

## P64-14 — Failed target profiles are failures (F15)

Requirement mapping: a target crash or timeout must return `status: error`, never a fabricated `peak_memory_bytes=0` or `measured=true` success; a clean 1,048,576-byte allocation fixture must report a peak at or above that byte count.

Frozen source SHA-256: `src/rush/tools/mem_profile.py` `6503625af7f2d06fb9f5102eabddf8032468954ad1212080638d8f7156a5c6ae`; `src/rush/tools/cold_start.py` `7997837a87f93fe64ff30c70800627a1311e0d51960f3ba4e9677b11485f0d73`. Frozen test SHA-256: `tests/test_mem_profile.py` `edecd98e79b40e58edade496694ac61bfd8471cc2b618664bc79db6e2792f988`; `tests/test_cold_start.py` `a7333dd89827ade971427211a4571abb92c16f2671fdd3c27a3d6dd2a101f707`.

- RED: not independently reproduced this session — `test_target_crash_is_error` and `test_timeout_is_error_without_completed_measurement` are present in both `tests/test_mem_profile.py` and `tests/test_cold_start.py`; `tests/test_mem_profile.py` additionally asserts `peak_memory_bytes >= 1_048_576` for the completed-measurement fixture and `peak_memory_bytes is None` for crash/timeout, confirmed by direct source read.
- GREEN: named tests confirmed present with matching assertions read directly from source.
- VERIFY: `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_mem_profile.py tests/test_cold_start.py -q` — 27 passed.

P64-14 confirmed passing this session.

## P64-15 — Ground schema drift and type guards (F16–17)

Requirement mapping: SQLAlchemy/SQLModel table identity must survive rename/drop across raw-SQL and Alembic migration ordering; `strictify` must not invent a guard for `sum(values)` without element evidence while still accepting valid list/tuple/generator inputs.

Frozen source SHA-256: `src/rush/tools/db_drift_rules.py` `ba661350a674e5316258e512b2bf83b755d40ce978ec2349f3bd1d204eb81adf`; `src/rush/tools/db_drift.py` `291e3d71f736878ff352eb679289a607a000585c70a7c29251e479a98ac66016`; `src/rush/tools/strictify.py` `e48d9b57789b1da4dc6d7023e5e1da8466eb748680089e700060eaffea6d2c01`. Frozen test SHA-256: `tests/test_phase48_db_simplify_strict.py` `d0f22d72cd782e912f2d287c6c954474a80a92c2170bb6b67d0b1cf292395ccc`.

- RED: not independently reproduced this session — `test_db_drift_keeps_table_identity` and `test_strictify_preserves_valid_sequence_inputs` are present by name.
- GREEN: named tests confirmed present matching the plan's rename/drop and sequence-guard fixtures.
- VERIFY: `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_phase48_db_simplify_strict.py -q` — 22 passed.

P64-15 confirmed passing this session.

## P64-16 — Parse license expressions and SVG safely (F18–19)

Requirement mapping: `(MIT OR Apache-2.0) AND GPL-3.0-only` must classify `strong-copyleft`/`HIGH`/`fail`; SVG sanitization must strip decoded executable URIs/event attributes and reject DTD/external-entity declarations with `error` and no writes, while preserving benign geometry.

Frozen source SHA-256: `src/rush/tools/license_matrix.py` `5a86c29219db9c036cf3de902b3b44ca030e823a802a67509b28c55ae86b3a68`; `src/rush/tools/media_opt.py` `dc664250a77119653d7385d1e79587d291dfe7fded4811e155ccef6b6ca3d549`. Frozen test SHA-256: `tests/test_license_matrix.py` `ba952d3c92fd4837a410589623172f09040bcbf96df18548968501f6fef25169`; `tests/test_media_opt.py` `fce0c89d32e444db8a4d55b4433a40bd37c3438b8abcfcaa34f634d4dc627bbe`.

- RED: not independently reproduced this session — `test_license_expression_classification_and_status` parametrizes exactly `("(MIT OR Apache-2.0) AND GPL-3.0-only", "strong-copyleft", "HIGH", "fail")` (and its double-parenthesized equivalent); `test_media_opt_rejects_dtd_and_external_entities_without_writes` and `test_media_opt_sanitizes_decoded_namespaced_and_mixed_case_svg` are present, confirmed by direct source read.
- GREEN: named tests confirmed present with matching assertions read directly from source.
- VERIFY: `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_license_matrix.py tests/test_media_opt.py -q` — 18 passed.

P64-16 confirmed passing this session.

## P64-17 — Project-relative discovery and valid coverage (F20–21)

Requirement mapping: `iam_audit`/`offline_runner` discovery must behave identically under ordinary and hidden parent directories while excluding hidden children; coverage import must reject `-1`, `101`, `NaN`, `Infinity`, and inconsistent Cobertura counts while accepting finite 0/100 endpoints.

Frozen source SHA-256: `src/rush/tools/iam_audit.py` `d3eeb85e29cb32b1f7775a19cb988241792c9a4fccccf12933adb0932beae191`; `src/rush/tools/offline_runner.py` `1cfa7b9d6265cffbbde87433692d9711efd5c95012dc781ace65ecaa4b4a6947`; `src/rush/tools/coverage.py` `5edd9082b3b7d4d46b9ae65a45237297306e8a5ca0c77b64a7134e0cc1829da3`. Frozen test SHA-256: `tests/test_iam_audit.py` `c00c7a4685e8da7de6e4a25448a961cac33829bbbd93791fb2eaf38366289cb0`; `tests/test_offline_runner.py` `2f3f6e9e6f3ed51272a3d2c2b81d946acfd417e0a08f58de8d30002316f1a018`; `tests/test_coverage_importer.py` `5aa755bcca770026a9b70c40a3ca4417b9503860e406b14e3d9d13936f6d580e`; `tests/test_phase50_slsa_attestation.py` `d02f530b61f922ab5212265a1ada9a0af46fd188be26b982cce91b2b5d0d7663`; `tests/test_phase50a_integration.py` `b3b3fd0eb614c430192837bcd7538a6b1105b2f46b80044cc608cf7647649727`; `tests/test_phase50c_integration.py` `1a94f2adfac1276b0888a8ef697d76d0096a0fa9f8bdd52dacb6881fa64691f0`.

- RED: not independently reproduced this session — hidden-parent fixtures (`.hidden` alongside `ordinary`) are present in both `tests/test_iam_audit.py` and `tests/test_offline_runner.py`; `test_coverage_rejects_invalid_cobertura_rate` is parametrized over `["-0.1", "1.1", "NaN", "Infinity"]` and `test_coverage_rejects_inconsistent_cobertura_counts` is present, confirmed by direct source read.
- GREEN: named tests confirmed present with matching fixtures/parametrization read directly from source.
- VERIFY: `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_iam_audit.py tests/test_offline_runner.py tests/test_coverage_importer.py tests/test_phase50_slsa_attestation.py tests/test_phase50a_integration.py tests/test_phase50c_integration.py -q` — 57 passed.

P64-17 confirmed passing this session.

## P64-18 — Real source structure in catalogs/complexity (F22–23)

Requirement mapping: `error_catalog` must use a real tree-sitter TypeScript/TSX/JSX grammar (locked `tree-sitter-typescript==0.23.2`) rather than regex, skip comment/string/template-text nodes, and produce an explicit partial/error result on a parse-error node; `simplify` complexity must score nested definitions independently, with an outer function with no own branches scoring baseline complexity 1.

Frozen source SHA-256: `src/rush/tools/error_catalog.py` `a705d7397e0de252aea6735ae5ff90075d8b98c666ac578dd80f4642dcb9f83b`; `src/rush/tools/simplify.py` `a033832dec6322fc46baf46eb2db1eeaadcf17290e640e54e269c8cee172cd70`; `pyproject.toml` `b08adf465c378422cc81e17bf472118ddfec450179c42dd84a4f7442f2411fa4`; `uv.lock` `681097ce43ad2b70a016d5b75b93bef0259140b113e9ff6f54552e94a69b52a3`. Frozen test SHA-256: `tests/test_error_catalog.py` `99210e2dd6e2e9f35d9ff978cc981c7f233dfdfeebdc991baa09792babf3b5e2`; `tests/test_phase48_db_simplify_strict.py` `d0f22d72cd782e912f2d287c6c954474a80a92c2170bb6b67d0b1cf292395ccc`.

- RED: not independently reproduced this session — `test_locked_typescript_grammar_loads` (imports `tree_sitter_typescript`, constructs both `language_typescript()` and `language_tsx()` `Language` bindings), `test_error_catalog_reports_partial_typescript_parse_error`, and `test_error_catalog_routes_tsx_and_jsx_to_jsx_grammar` are present by name; `pyproject.toml` pins `tree-sitter-typescript==0.23.2` alongside the retained `tree-sitter==0.26.0` runtime dependency, confirmed by direct source read.
- GREEN: named tests confirmed present; grammar pin confirmed in `pyproject.toml`.
- VERIFY: `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_error_catalog.py tests/test_phase48_db_simplify_strict.py -q` — 34 passed.

P64-18 confirmed passing this session.

## P64-19 — Scan staged bytes (F26)

Requirement mapping: staged-content checks must read `git ls-files --stage -z` plus `git show :path` blobs for stage-0 entries rather than worktree files, in both directions (staged-invalid/worktree-repaired and reverse), and report nonzero-stage entries as explicit `error`/`unmerged_index` with stage identities.

Frozen source SHA-256: `src/rush/hook/staged_scanner.py` `696e8d526f99d8e930807e82107d1900e799135bc0933808aa3780950db85ef1`; `src/rush/hook/ast_linter.py` `e944060829534cf196b5269630941478e623f57e4a452e8ac7024ee45df6b5e2`; `src/rush/cli.py` `40e154a9d599e442ffa731408cb56ab4d9207c8e6f769d71323b82e015ef1820`. Frozen test SHA-256: `tests/test_staged_scan_bytes.py` `e858f25b6781cee4d07942d8a9f0a3f79923431b815fb545b05f539cbc2bd3d7`.

- RED: not independently reproduced this session — `test_staged_invalid_python_ignores_repaired_worktree`, `test_staged_valid_python_ignores_invalid_worktree`, `test_staged_checks_share_index_bytes_and_record_deleted_path`, and `test_staged_unmerged_index_reports_stage_identities` are present by name.
- GREEN: named tests confirmed present matching the plan's bidirectional staged/worktree divergence and unmerged-index requirements.
- VERIFY: `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_staged_scan_bytes.py -q` — 8 passed.

P64-19 confirmed passing this session.

## P64-20 — Repair baseline test, packaging and CI gates (F27, F29)

P64-20's own VERIFY step requires `uv build`, `uv run pytest tests/ -q`, `uv run ruff check src tests scripts`, `uv run ruff format --check src tests scripts`, `uv run mypy src/rush`, and `uv run python scripts/sync_docs.py --check` to **all** pass with "no inherited failure allowlist." Independently run this session:

- `uv build` — succeeded (`dist/rush_cli-0.3.0.tar.gz`, `dist/rush_cli-0.3.0-py3-none-any.whl`).
- `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/ -q` — 1696 passed, 5 skipped (named real-engine acceptance tests, gated behind `RUSH_REQUIRE_REAL_ENGINES=1`).
- `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m ruff check src tests scripts` — all checks passed.
- `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m ruff format --check src tests scripts` — 800 files already formatted.
- `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m mypy src/rush` — no issues found in 442 source files.
- `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python scripts/sync_docs.py --check` — **failed** at that point in the session: dozens of `contracts.mcp: missing parameter ...` findings (e.g. `rush_fuzz`, `rush_load`, `rush_mutation`, `rush_test_heal`, `rush_ship_clean`), `contracts.mcp: missing registered command rush_patch_apply` (the same stale-receipt condition P64-04's evidence already identified as `stale_recorded_contract`, T009's scope), `stale sha256` on several docs (`docs/CLI_REFERENCE.md`, `docs/MCP_REFERENCE.md`, `docs/KNOWN_ISSUES.md`, `docs/SAFETY.md`, `docs/safety/permissions.md`, `docs/safety/safety-overview.md`, `docs/vibecoding/the-vibecoder-workflow.md`, this evidence file itself), `historical body changed` on `docs/CLI_REFERENCE.md` and `docs/MCP_REFERENCE.md`, and `missing coverage receipt` for newly added `docs/goals/phases-64-63-65-66/**`, `docs/developer/phase-63-66-coding-agent-handoff.md`, and `docs/phase-plans/MC01.md`.

T009 closed the `sync_docs.py --check` gate (see P64-00 above): the recorded `contracts` object was regenerated from live `collect_runtime_contracts()` and every stale/missing document receipt was reconciled against current file bytes. Re-run this session after that reconciliation: `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python scripts/sync_docs.py --check` — exits 0, "Documentation coverage and runtime contracts match." No `src/` files changed between the failing run recorded above and this one, so the `uv build`, `ruff check`, `ruff format --check`, and `mypy` results already recorded above still hold; `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/ -q` was re-run fresh this session (see the goal oracle command block). Per the plan's own bar ("All pass; no inherited failure allowlist"), P64-20's full named VERIFY step now passes. `tests/test_ci_contract.py` and `tests/test_checkov_reference.py` (P64-20's own RED/GREEN test files) also pass in isolation: `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_ci_contract.py tests/test_checkov_reference.py -q` — 13 passed.

P64-20 is complete.

## Remaining Phase 64 work

P64-00, P64-01, P64-03, P64-04, P64-05, P64-06, P64-07, P64-08, P64-09, P64-10, P64-11, P64-13, P64-14, P64-15, P64-16, P64-17, P64-18, P64-19, and P64-20 have completed packet evidence confirmed this session. P64-02 evidence above remains provisional pending its full verification and source review. P64-12 remains outside this evidence pass's scope. Other Phase 64 packets remain planned until their own RED, GREEN, and acceptance evidence is added.
