# Phase 72: remaining work (handoff)

State as of 2026-10-14. Phase 72 is merged to `main` (PR #3, merge `1f770e4`); `main` is at `3651902`.
CI run on `1f770e4` (failing): https://github.com/jamesdsizemore/rush-cli/actions/runs/38567715397

## 0. Setup

- Branch from `origin/main` in a worktree: `git worktree add ../rush-cli-worktrees/<name> -b <branch> origin/main`.
- Python: `.venv/bin/python` (3.12). Always pass `-m ''` to pytest (default config deselects slow tests). Unset `PYTHONPATH`.
- CI runs on every `pull_request` and on `push` to `main` (`.github/workflows/ci.yml:3-6`). Run Windows and Linux-only checks by opening a PR.
- Read a CI job log: `gh api repos/jamesdsizemore/rush-cli/actions/jobs/<job id>/logs`.
- Phase 72 gate records (logs, scope records, mutation ledger, gate scripts) are in the main checkout's `.git/phase72-archive/`. The ledger is also at ref `refs/wip/phase72-g6-ledger`.

## 1. Failing CI items

| # | Test (def line, failing line) | CI job | Error | Local result on macOS, `main` |
|---|---|---|---|---|
| 1 | `tests/test_phase72_memory_public.py::test_t06_g4_path_and_input_rows` (:6998, :7065) | Tests (shard 6 of 8), Linux | `assert 'policy_missing' in {'project_missing', 'project_not_registered', 'relinked', 'worktree_mismatch'}` | Passes; debug on Linux (PR CI or a Linux container). |
| 2 | `tests/test_tui_terminal.py::test_installed_native_tui_real_terminal` (:1283, :1012) | Tests (shard 0 of 8), Linux | `preview: 1 record(s) selected never happened (exit None)` | Defined only when `RUSH_G8_NATIVE_ARCHIVE` is set (`tests/test_tui_terminal.py:1281`); build steps in section 1a. |
| 3 | `tests/test_benchmark_local.py::test_unverified_cached_model_is_rejected_before_runtime_execution` (:197, :208) | Tests (shard 3 of 8), Linux | `runtime must not run before artifact integrity verification` | Fails in 1 s. |
| 4 | `tests/test_windows_import_safety.py::test_windows_f2_f3_shift_tab_decode_to_named_actions_not_escape` (:970, :976) | Windows runtime and installed contracts | `assert 1 == 0` | Windows-only test; run via PR CI. |
| 5 | `tests/test_windows_import_safety.py::test_windows_installed_tui_real_console_journey` (:2397, :2548) | Windows runtime and installed contracts | `installed TUI left child processes after exit` | Windows-only test; run via PR CI. |
| 6 | `tests/test_phase72_memory_acceptance.py::test_t09_live_windows_console` (:6475) | Windows runtime and installed contracts | `native console journey failed` | Windows-only test; run via PR CI. |
| 7 | `scripts/sync_docs.py --check` (step "Verify documentation parity & links") | Quality and tests | `missing coverage receipt` for 123 files | Fails: `.venv/bin/python scripts/sync_docs.py --check`. Detail in section 1b. |

Test line numbers come from the CI logs of `1f770e4`; `git diff --name-only 1f770e4 3651902 -- tests src` is empty, so they hold on `main`.
Local results for items 1 and 3: `.venv/bin/python -m pytest -m '' <both ids>` on `3651902` gave `1 failed, 1 passed` (item 3 failed).
Shard 7 of 8 was still running when this was written; check it in the run above.
Done when: every job of the CI run on `main` is green.

### 1a. Building the installed artifact (item 2)

CI does this in `.github/workflows/ci.yml`, step "Build native release archive for installed-artifact probes": (steps copied from the workflow; not yet run locally)
1. `uv build`, then `uv pip install pyinstaller`.
2. `pyinstaller --onefile --name rush --paths src ...` (copy the full flag list from that step).
3. `build_release_archive(Path('dist/rush'), Path('dist'), 'rush-linux-x86_64.tar.gz', rush.__version__)` and `write_sha256sums(...)` from `scripts/probe_installed_artifacts.py`.
4. Run the test with `RUSH_G8_NATIVE_ARCHIVE=$PWD/dist/rush-linux-x86_64.tar.gz` (workflow line 207; Windows uses `dist/rush-windows-x86_64.zip`, line 414).

### 1b. Coverage receipts (item 7)

- Failing paths: `docs/phase-plans/worktree-cleanup-plan.md` (on `main` since `a2e8b77`, before PR #3; the pre-PR CI run on `6189ce5` stopped earlier at ruff, 8 errors, so this check did not run there), plus since `3651902`: 120 files under `docs/assets/brand/`, `docs/CORRECT-WORKFLOW-DESIGN.md`, and this file.
- Receipts are entries in the `documents` list (512 entries) inside `docs/reports/phase-64-66-documentation-coverage.md`, read by `read_coverage_receipt` in `scripts/sync_docs.py`.
- Entry keys: `audience`, `authority`, `changed_sections`, `evidence`, `lane_authority`, `lane_receipt`, `media_type`, `owner`, `path`, `referrers`, `sha256`, `source_state`. Copy a template: for an image, the entry whose `path` is `docs/assets/rush-terminal-control-plane-concept.png`; for Markdown, any `docs/phase-plans/` entry.
- `sha256` comes from `document_digest(path)`; mechanical fields from `build_document_inventory(repo_root)` (`scripts/sync_docs.py:504`).
- `sync_docs.py` accepts only `--check`, so add entries with a small script that edits the JSON block. Exclusions are in `_is_excluded_document` (`scripts/sync_docs.py:450`); today only `.DS_Store` and `docs/goals/*/state.yaml`.
  verified-by: `scripts/sync_docs.py:783-787` defines one argument, `--check`, and errors without it.
- Decision for James: add receipts for the 120 brand files, or exclude `docs/assets/brand/`.
- Related: `docs/assets/brand/rush-wordmark-v2/build.py` reports 12 mypy errors with `MYPYPATH=src .venv/bin/mypy <file>`.

## 2. Open product item: 72-T08 hybrid retrieval default is off

- Verdict `unavailable`: the Codex route's overhead is 32,745 tokens against the 16,000-token case budget. The Anthropic route measured `benefit`.
- Code: `HYBRID_DEFAULT_VERDICT: dict[str, str] | None = None` at `src/rush/memory/retrieval.py:90`, read at `src/rush/tools/memory.py:3557`.
- Evidence: `docs/reports/phase-72-memory-eval/hybrid-verdict.json`; report text in `docs/reports/phase-72-memory-acceptance.md` (search `32745`).
- Done when: the Codex route fits the budget (or James changes the budget), the evaluation reruns, and the verdict is recorded.

## 3. Verification never finished

### 3a. Full suite on the final freeze

- The F7 (`b25628e`) full suite was stopped partway. Last complete green run: F6 `511414a`, 13,176 passed, 0 failed, 0 skipped. F7 adds `e6ab3e3` (src fix) and `e309bf4` (test fixes).
- Done when: section 1 is green on `main` (CI runs the full suite).

### 3b. 19 mutation-ledger rows with failing control runs

- Ledger: `.git/phase72-archive/phase72-g6-ledger.json` → `mutants` → key → list of rows. Rows to redo are those with `control_failed > 0`: 15 under `72-T02` (each `control_passed` 683, `control_failed` 248) and 4 under `75-T02/EVALUATOR` (each `control_passed` 26, `control_failed` 9).
- Row fields: `guard` (file:line), `patch` (unified diff that mutates the guard), `killing_test` (pytest id), `guard_test`, `source_sha256`, `control_passed`, `control_failed`.
- Rule (plan `docs/phase-plans/phase-72-memory-correctness-and-user-control-plan.md:482`, G6): run an unmutated control first, never `-x`; a kill counts only when a test that passed in control fails under the mutant; exclude copy-environment failures such as `test_r7_every_checked_in_manifest_record_exists`.
- These 19 rows recorded failing controls (248 and 9 failures), so their kills are unconfirmed. Rows do not record which test set the control ran (72-T02: 931 tests).
- Per row: (1) on clean `main`, run the control test set without the mutant and record pass/fail per test; the `killing_test` must pass. (2) `git apply --check` the `patch`; if it does not apply, re-target it to the current `guard` line. (3) Apply it and run the same set; the `killing_test` must fail. (4) Revert. (5) Write the new `control_passed`/`control_failed` into the row.
- Phase 72 gate scripts, for reference: `.git/phase72-archive/phase72-gates/ledger-append.py`, `pr6-record.py`.

### 3c. Stale report rows

- In `docs/reports/phase-72-memory-acceptance.md`, rows `native-linux-ci`, `native-windows-ci` and `native-macos` say "branch is not pushed", which is now false. After section 1 is green, record the CI run URL and the `PASSED` lines there.

## 4. Open report rows owned by other phases (not Phase 72)

- `portable-route-release`: Phase 73 73-T09.
- `r5b-frame-receipts`: Phase 75 75-T01 (`tests/test_phase75_usage.py::test_memory_event_frame_receipt_columns`).
- `phase70-t28d-g5-g8`: Phase 70 T28-D gates G5 to G8.
- `phase71-p07`: Phase 71 P07 dashboard memory panel.
