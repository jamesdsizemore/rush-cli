# Disposition of the 38 Codex findings

Plan: `docs/reports/orchestrator-and-phase-70-remediation-plan-2026-09-29.md` (untracked, not committed).
Findings: `findings-raw.md` in this directory (Codex exit 0, `codex-exit.txt`; verdict NOT_READY).
Nothing was applied to the skill, agents, hooks, settings, CLAUDE.md or the repo. All patches and scripts are in
`.scratch/orchestrator-remediation-2026-09-29/` (`MANIFEST.sha256` lists the sha256 of each file).

Each finding was checked against the primary source (the live skill, the hook files, the phase-70 worktree, the
plan text) before the plan was changed. Findings that could be reproduced were reproduced with a fixture; the
answer is the plan entry named below plus the tested artifact.

| # | Sev | Finding | Plan entry changed | Evidence (run 2026-09-29) |
|---|---|---|---|---|
| 1 | critical | disk cleanup without ownership or inactivity | D2 step 4, J21 | `skill-v2/tests/test_disk_clean.sh` 8 checks |
| 2 | critical | gate basetemp under a worktree-local lock | T5, D7 | `skill-v2/tests/test_gate_lock.sh` 7 checks |
| 3 | major | budget removal left references | A4, I1 | `skill-v2/tests/test_skill_text.sh` 41 checks; `--budget` exits 2 in `test-dispatch-prompt.sh` |
| 4 | major | dispatch text fails model-guard rule 7 | H11, B1 | `skill-v2/tests/test_model_guard_rule7.sh` 7 checks against `~/.claude/hooks/orchestrator-model-guard.js` |
| 5 | major | read-only scout told to create files | B4 | `skill-v2/scripts/save-map.sh`, `tests/test_save_map.sh` 6 checks |
| 6 | major | tests-first dispatch needs a RED log first | F2 item 4 | `dispatch-prompt.sh --mode tests`, `tests/test-dispatch-prompt.sh` 92 checks |
| 7 | major | generator edits omit `scout:`/`done:` enforcement | B4, B6 | `tests/test-dispatch-prompt.sh` |
| 8 | major | `task-gate.sh` lifecycle | I1 | `tests/test_task_gate.sh` 10 checks |
| 9 | major | shared environment vs worktree-local environment | A5, F2 item 2, D2 | `run.json` `python`; `tests/test_run_state_graph.sh` 32 checks |
| 10 | major | CI required for an unpushed commit | F1 item 4, I3 | `task merged` needs local `gate-ok`; `tests/test_run_state_graph.sh` |
| 11 | major | CI edits omit the lock and the collection guard's authorization | T4, T8, D6 | patches `pytest-xdist-pin-and-lock` and `t2-t3-t5-t8-home-cleanup-npm-cache-run-guard`; 1,501-test fixture exits 4 without `RUSH_GATE`/`CI`, passes with either |
| 12 | major | task graph cannot hold split and parked nodes | C1 item 6, D1 | `tests/test_run_state_graph.sh` |
| 13 | major | loader overwrites progress | C1 item 5 | `tests/test_load_plan.sh` 11 checks |
| 14 | major | shared-file policy contradicts the plan | C1 item 7, C3 | `tests/test_load_plan.sh`, `tests/test_run_state_graph.sh` |
| 15 | major | contradictory model matrices, no binding | A2, D1 | `tests/test_patch_agents.sh` 17 checks, `tests/test_probe_agents.sh` 11 checks |
| 16 | major | throttle hides listing failures | T2 step 1, D8 | patch `conftest-throttled-probe-with-final-check` |
| 17 | major | retention setting does not delete the gate basetemp | T5, D7 | `tests/test_gate_lock.sh` |
| 18 | major | npm cache shown as caching every fixture | T4 step 2 | text corrected |
| 19 | major | probe passes missing results, skips installed agents | A5 step 4, H14 | live per-agent probe (installed definitions fail, patched pass); `tests/test_probe_agents.sh` |
| 20 | major | ask guard allows blocking questions, lookup error approves | D1 item 3 | `hooks/test-hooks.js` 21 checks |
| 21 | major | hooks act in unrelated sessions | D4 | `hooks/test-hooks.js` (session-bound marker) |
| 22 | major | unlock reader takes hook feedback for your message | D4 | `hooks/test-hooks.js` |
| 23 | major | resume guard blocks every role | C4 | `hooks/test-hooks.js` |
| 24 | major | TaskStop guard and monitor disagree | C5 | `hooks/test-hooks.js`, `tests/test_monitor.py` |
| 25 | major | monitor one-shot, permanent suppression, duplicate exit code | E4 | `tests/test_monitor.py` |
| 26 | major | raw-read detector flags read-then-Edit | E4 item 4 | `tests/test_monitor.py` |
| 27 | major | assertion-prefix classification | F2 items 1, 3 | `tests/test_test_acceptance.py` |
| 28 | major | status does not deliver live status | E3 | `tests/test_run_state_graph.sh`, `tests/test_monitor.py` (`--status`) |
| 29 | major | usage and suite timing disconnected | A6, T6 | `tests/test_run_state_graph.sh`, `tests/test_monitor.py` |
| 30 | major | doc checker passes fake artifacts and missing input | J2 | `tools/test-doc-done-check.sh` 8 checks |
| 31 | major | coverage checker equates a name with a review | J22 | `tools/test-skill-coverage.sh` 8 checks |
| 32 | major | behavior fixes were reminders | J1, J6, J14, J15, H5, H13, H16, G2 | `tools/test-ledger-check.sh` 7 checks, `hooks/test-behavior-hooks.js` 44 checks, G2 register |
| 33 | major | J-series hooks had no install path | X12, D9, D10 | registration block; `hooks/test-behavior-hooks.js` |
| 34 | major | keyword triggers | J4, J10, J12, J22, X12 | fixtures using the review's counterexamples |
| 35 | major | reviewer wording weakened caller review | B7 item 2 | `tests/test_patch_agents.sh` |
| 36 | major | T7 remedy risked removing assertions | T7 | patch `t7-wrap-and-truncation-notice` |
| 37 | major | overlapping edits, no canonical order | 8.0, banners on X1 to X11 | `MANIFEST.sha256` |
| 38 | minor | stop lacked cleanup | C6 | `tests/test_run_state_graph.sh` |

## Runs on 2026-09-29 (after the last edit to the tree)

- `bash skill-v2/tests/run.sh`: ALL PASS (decisions, disk_clean 8, gate, gate_lock 7, load_plan 11, model_guard_rule7 7,
  patch_agents 17, probe_agents 11, run_state_graph 32, run_state, save_map 6, skill_text 41, task_gate 10,
  worktree_add 8, test-dispatch-prompt 92, test_monitor.py, test_test_acceptance.py).
- `node hooks/test-hooks.js`: 21 checks, ALL PASS. `node hooks/test-behavior-hooks.js`: 44 checks, ALL PASS.
- `tools/test-doc-done-check.sh` 8, `test-ledger-check.sh` 7, `test-refs-check.sh` 8, `test-skill-coverage.sh` 8: all pass.
- The plan: `doc-done-check.sh` PASS 85 entries (structural lint), `ledger-check.sh` PASS 11 sentences and 11 rows,
  `refs-check.sh` PASS.
- Four patches in `test-suite-patches/`: each `git apply --check` clean against the phase-70 HEAD (66c6c79), and the four apply
  in sequence to a copy. On that copy: the 1,501-test guard fixture exits 4 without `RUSH_GATE`/`CI` and runs 1,501 with
  either; `test_real_home_guard.py`, `test_phase70_t27.py`, `test_import_order.py` 1,009 passed in 150 s; the full serial suite
  `6348 passed, 3 deselected in 987.25s`, no failures, no skips. The copy, its basetemp and the test engine cache were deleted.
- The phase-70 worktree `git status --porcelain` is empty; the main checkout shows only untracked `.scratch/` and `docs/` files and
  the `AGENTS.md` change that was there before this work.

Not exercised: remote CI (needs an authorised push); `posix-import-check.py` and `ci-triage.sh` (code in X11, not run);
the D4 and D9 hooks through the real hook pipeline (need your go and registration); the agents line of
`run-state.sh report` on a real orchestrator session.
