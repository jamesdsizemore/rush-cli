# Prep: board review (2026-10-05)

Task: prep (before T001)
Kind: `pm`
Status: `current`

## Summary

The board was reviewed against four sources: the GoalBuddy execution contract (`references/goal-execution.md`, 357 lines), the Phase 72 plan sections §1-§8 (476 lines), the Phase 71 P07 and Phase 73 73-T02 sections it depends on, and the real `07775f1` tree. The review found 10 defects. All 10 are fixed in the regenerated board (50 tasks; checker `ok: true`, 0 errors, 0 warnings; the live board API reports 50 tasks). Three findings need an owner decision and are recorded in `goal.md` as D2-D4. D1 was already open.

Coverage: of the 23 test files named on the cards, 15 exist and 8 are new deliverables (`test_memory_authorization`, `test_phase72_memory_correctness`, `test_phase72_preferences`, `test_phase72_memory_public`, `test_phase72_memory_ui`, `test_phase71_dashboard_integration`, `test_phase72_memory_hybrid`, `test_phase72_memory_acceptance`), plus `test_phase72_portable_memory_policy` added by this review. Of the 41 source, doc and fixture paths named on the cards, 39 exist; 2 are absent: `src/rush/dashboard/panels.js` (plan: optional, do not wait for it) and `tests/fixtures/phase75/task_manifest.json` (a 75-T02 product).

## Details

1. **RED verify could never yield a done receipt.** The contract says the checker rejects a done Worker whose commands include a non-pass status, but the RED cards' verify commands were expected to fail. Fix: each RED verify is now a wrapper that exits 0 only when pytest exits 1 and the summary line shows failures with no pass, skip, xfail, xpass or collection error. It was tested on four fixtures: all-fail gives 0; one-pass, collection-error and skip each give 1.
2. **Collection errors would mask RED.** For example, `authorization.py` is absent, so a module-level import fails the whole file. Fix: RED cards require not-yet-existing symbols to be imported inside test bodies.
3. **Plan §8 PAS was missing from the board.** It brings `tests/test_phase72_portable_memory_policy.py` with 7 required cases, the T06 `apply_import_records` seam, the T07 import-review projections and the T09 live import walkthrough. Fix: §8 is added to the T01/T06/T07/T09 gate inputs, the PAS test file to the T01/T06/T07 RED `allowed_files`, the PAS case runs to the T06/T07 verify, and PAS to the oracle and T999.
4. **73-T09 codec dependency was untracked.** `src/rush/memory/capsule.py` is absent, and plan §8 closes the real import route only through 73-T09. Now open decision D3.
5. **The charter misread Phase 71 P07.** It claimed T07 "must satisfy" P07's full acceptance. P07 (phase-71 plan lines 193-204) needs `panels.js` and the P02 Node command from Phase 71 P01-P02, which are not implemented. Plan §2 says Phase 72 must not wait for `panels.js`, and §7 scopes T07 to P07's memory work and checks. Fix: the charter wording is corrected, T07 builds on the current dashboard, and the P02-dependent check is named open in the T09 report.
6. **Live lanes were folded into the implementation verify.** An unavailable route (credentials, browser, installed client) would have blocked the unit's local work. Fix: separate live-lane Worker tasks T037 (T07), T044 (T08) and T048 (T09).
7. **The T008 gate cited "authorization.py from T015",** which does not exist when the gates run. Fix: it now cites the 73-T02 plan C01 signatures and the T003 POLICY gate note. The T003 gate must also cover the T05 personal-overlay grant.
8. **Up-front gates go stale.** T01 rewrites `store.py` and `tools/memory.py` before the later units' RED tasks. Fix: each RED task first re-checks its gate's code map against HEAD and returns to the PM for a gate delta on drift.
9. **Venv conflict.** The worktree has no `.venv`, the plan's `uv run` would create one, and the owner rule forbids building one per worktree. Now open decision D4, which blocks T001's test commands.
10. **Smaller gaps closed:**
    - T999 inputs lacked "Current dirty diff".
    - There was no rule for the fix-round task id; the next free `T###` is now used.
    - The gate `worker_package` now explicitly supersedes the prep-time card specs.
    - The owner-rule override of the GoalBuddy fewer-Judges default is now stated.
    - Board files are now committed in T001 with an exact pathspec.
    - The T002 Scout checks whether the §2.2 probe writes under the real user data root.
    - EVALUATOR gate inputs now record the absent `--decision-mode`, `--decision-route` and `--task-manifest` flags in `scripts/benchmarks/run.py`.

Checked and found correct:
- The plan bytes are identical in the main checkout and the worktree.
- `66c6c799` is an ancestor of `07775f1`, 18 commits behind.
- `test_t28d_memory_workflows` exists at `tests/test_phase70_tui_usability.py:64`.
- pyproject addopts `-m "not slow"` is overridden by the full suite's `-m ''`.
- `.venv`, `.pytest_cache` and `.mypy_cache` are gitignored.
- The Claude agents (`goal-scout`, `goal-worker`, `goal-judge`) and the Codex agents (`goal_*.toml`) are installed.
- The §2.2 probe uses `tempfile.TemporaryDirectory`.

## Update after owner decisions D3 and D4 (2026-10-05)

- D4 decided: one new `.venv` in the Phase 72 worktree, created in T001.
- D3 decided: a 73-T09/CODEC checkpoint unit was inserted between 72-T06 and 72-T07, so the board has 54 tasks and the task IDs above shifted. The current mapping is the table in `goal.md` § Current Tranche, which was checked against `state.yaml`: 12 of 12 rows match, 0 mismatches. The live-lane tasks named in finding 6 are now T041 (72-T07), T048 (72-T08) and T052 (72-T09).

## Board Receipt Snippet

```yaml
receipt:
  result: done
  note: notes/prep-board-review.md
  summary: "10 board defects fixed; D2-D4 open for owner decision; board 50 tasks, checker ok."
```
