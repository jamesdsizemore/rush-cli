# Phase 72: Memory correctness and user control

## Objective

Implement every task packet in `docs/phase-plans/phase-72-memory-correctness-and-user-control-plan.md` (72-T01 through 72-T09) to full acceptance, plus the three cross-phase producer checkpoints the plan consumes (73-T02/POLICY, 73-T09/CODEC and 75-T02/EVALUATOR), on branch `phase/72-memory-correctness-and-user-control` in worktree `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72`.

## Original Request

`/goal-prep Phase 72`

Owner decisions recorded during intake (2026-10-05):

1. Base the Phase 72 branch on the `phase/70-agent-adoption-and-usability` tip `07775f1`, so it carries forward the Phase 70 repairs as the plan requires. Phase 70 stays unmerged.
2. Build the cross-phase checkpoints 73-T02/POLICY and 75-T02/EVALUATOR on this board, in this worktree. They keep their original task identities, so Phase 73 and Phase 75 later consume them rather than rebuild them.
3. (D3) Build a 73-T09/CODEC checkpoint on this board, after 72-T06 and before 72-T07, keeping the 73-T09 identity. The rest of 73-T09 stays with Phase 73.
4. (D4) T001 creates one new `.venv` in the Phase 72 worktree.
5. (D1) The 72-T08 raw paired-eval output is committed under `docs/reports/phase-72-memory-eval/{current,hybrid}/`, not `.scratch/`.

## Intake Summary

- Input shape: `existing_plan`
- Audience: Rush users and the coding agents that read and correct Rush memory
- Authority: `approved` (implementation on the phase branch). Merging into `main` is NOT approved and remains a separate owner-gated step.
- Proof type: `test` plus `artifact` (live acceptance report)
- Completion proof: each of the 12 units' named RED→GREEN tests and regression commands pass on frozen bytes; the full suite, ruff, ruff format and mypy show no new failures and zero skipped tests compared with the T001 baseline; `docs/reports/phase-72-memory-acceptance.md` records the actual CLI, stdio MCP, PTY and desktop/mobile browser evidence; each unavailable live lane is named as open with one exact blocker.
- Goal oracle: see below.
- Likely misfire: green unit tests on helper functions while a read path (review citations, cache selection, compact query, hybrid, relations, TUI, dashboard) still serves archived, expired, foreign-owner, tampered or revoked memory. A second misfire: implementing against `main`'s older helpers and overwriting Phase 70 repairs. A third: labeling the lexical fallback as hybrid, or reporting an unexecuted live lane as passed.
- Blind spots considered:
  - `src/rush/memory/authorization.py` does not exist on `07775f1`. 73-T02/POLICY must be built before 72-T01 final acceptance.
  - The Phase 75 plan never defines a checkpoint named `75-T02/EVALUATOR`; only whole task 75-T02 exists (`phase-75-context-and-token-efficiency-plan.md:145`). The T012 design gate must define it from 75-T02's text before anything consumes it.
  - 74-T01 qualified symbols and 75-T01 usage receipts are not produced by this board. Per plan §3, the affected displays show `unavailable` with a reason until those producers exist. This is the plan's own instruction, not a descope.
  - Shared `store.py`, `tools/memory.py` and `cli.py` edits need one writer at a time (`max_write_workers: 1`).
  - Plan §7: T06 + T07 implement Phase 70 T28-D's terminal memory administration (its broader T28-F gates are not implied), and T07 performs Phase 71 P07's memory work against T06 on the CURRENT dashboard, keeping P07's owner/version, promote, hostile-content and reload checks. `panels.js` does not exist and plan §2 says Phase 72 must not wait for it. P07's check that needs Phase 71's P02 Node command cannot run until Phase 71 P01-P02 exist, so the T09 report names it open.
  - Plan §8 (PAS) extends T01/T06/T07/T09. It adds `tests/test_phase72_portable_memory_policy.py` (7 required cases), the `TypedArtifactStore.apply_import_records` seam in T06, and live PAS/Rush-capsule import walkthroughs. Real capsule-route closure consumes 73-T09's codec, which does not exist on `07775f1` (`src/rush/memory/capsule.py` absent). Decision D3 builds a 73-T09/CODEC checkpoint here.
  - Plan reviewed at phase-70 `66c6c799`; base `07775f1` is 18 commits later and changes 9 plan-touched files (store.py +62, tools/memory.py +113, tui.py +454). T002 reconciles every claim.
  - Gates run up front, before earlier units rewrite shared files, so each RED task first re-checks its gate note's code map against current HEAD and returns to the PM for a gate delta on drift.
- Existing plan facts: listed in `state.yaml` under `goal.intake.existing_plan_facts`; the plan file itself is binding.

## Goal Oracle

The oracle for this goal is:

`The named Phase 72 test files (tests/test_phase72_memory_correctness.py, test_phase72_preferences.py, test_phase72_memory_public.py, test_phase72_memory_ui.py, test_phase72_memory_hybrid.py, test_phase72_memory_acceptance.py, test_phase72_portable_memory_policy.py, test_memory_authorization.py) and each packet's regression commands pass on frozen worktree bytes. The full suite (pytest tests/ -q -m ''), ruff check, ruff format --check and mypy src/rush show no failures beyond the T001 recorded baseline and zero SKIPPED tests. docs/reports/phase-72-memory-acceptance.md maps the 9 requirement-ledger rows of plan §4 and the 7 required plan §8 PAS cases to actual executed evidence, including live CLI, stdio MCP, PTY keyboard and browser desktop 1280x800 and mobile 390x844 walkthroughs.`

The PM must keep comparing task receipts to this oracle. Planning, discovery, a passing tiny slice, or a clean-looking board is not enough. The goal finishes only when a final Judge/PM audit maps receipts and verification back to this oracle and records `full_outcome_complete: true`.

## Goal Kind

`existing_plan`

## Current Tranche

The entire Phase 72 plan: 73-T02/POLICY, 72-T01 through 72-T09, 73-T09/CODEC and 75-T02/EVALUATOR (12 units), to full acceptance. Work runs continuously in this order: baseline (T001-T002), then design gates for the 12 units up front (T003-T014), then per unit RED tests → implementation → live lane (only 72-T07, 72-T08, 72-T09) → full-attack review (T015-T053), then the final audit (T999).

| Unit | Gate | RED | Implement | Live lane | Review |
|---|---|---|---|---|---|
| 73-T02/POLICY | T003 | T015 | T016 | - | T017 |
| 72-T01 | T004 | T018 | T019 | - | T020 |
| 72-T02 | T005 | T021 | T022 | - | T023 |
| 72-T03 | T006 | T024 | T025 | - | T026 |
| 72-T04 | T007 | T027 | T028 | - | T029 |
| 72-T05 | T008 | T030 | T031 | - | T032 |
| 72-T06 | T009 | T033 | T034 | - | T035 |
| 73-T09/CODEC | T010 | T036 | T037 | - | T038 |
| 72-T07 | T011 | T039 | T040 | T041 | T042 |
| 75-T02/EVALUATOR | T012 | T043 | T044 | - | T045 |
| 72-T08 | T013 | T046 | T047 | T048 | T049 |
| 72-T09 | T014 | T050 | T051 | T052 | T053 |

Live lanes are separate Worker tasks so an unavailable route (credentials, browser, installed client) blocks only that lane and never the unit's local work. RED verify commands pass only when every selected new test fails with no pass, skip or collection error, because a done Worker receipt may list only passing commands. Each gate returns `worker_package` specs that supersede the prep-time `allowed_files`/`verify` on that unit's cards. A failed review makes the PM create the fix Worker task with the next free `T###` id.

## Non-Negotiable Constraints

- **Worktree only.** Git, test and edit commands target `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72` explicitly (`cd <worktree> && rtk ...`, absolute paths for file tools). Never use `EnterWorktree`. Never cut or switch a branch in the main checkout `/Users/jamesdsizemore/Developer/rush-cli`.
- **Commits on the phase branch only.** Never merge into `main` or push without an explicit owner go.
- **Design gate before each implementation task** (owner standing rule). The read-only design gate for the 12 units runs up front (T003-T014). It produces testable behavior, a complete code and caller map including files missing from the packet, the exact design of the hard parts, cross-task conflicts, and the full test matrix, with no open decisions. A separate test author writes that matrix, and each new test must be shown to FAIL by execution before the implementer runs.
- **Opus for trust-boundary implementers:** POLICY, T01, T02, T03, T04, T05, T06, CODEC and T07 (paths, containment, permissions, consent, user-file writes, hostile content).
- **Each implementation round** runs the full suite, ruff check, ruff format --check and mypy, plus one full-attack review. This owner rule overrides the GoalBuddy default of reviewing only at phase or risk boundaries.
- **Hard cap of two fix rounds per unit.** Errors left after round 2 are the PM's failure: the PM finds what the gate brief or tests missed and finishes the fix directly, to fully green. No third round, and no report-and-wait.
- **Zero skipped tests,** in CI or locally, for any reason.
- **Python and environment:** Python 3.12 with `PYTHONPATH` cleared, using the plan's literal commands (`rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev ...`). T001 creates exactly one `.venv` in the Phase 72 worktree (decision D4), and agents use only that one. Agents never build their own venv. The venv is deleted when the worktree is removed after merge.
- **Disk.** A background monitor on `rtk proxy df -g /Users` alerts below 8 GiB and is restarted whenever it exits. Free space is checked before each Agent dispatch. Temp dirs only via pytest `tmp_path` or `TemporaryDirectory`, never bare `mkdtemp()`. Any temp HOME is deleted before reporting.
- **Never write to `.scratch/`.** This includes agents and benchmark output (decision D1).
- **Never touch another repo.** No reads, searches or live tests outside this worktree. The main checkout is used only for read-only git state checks.
- **Policy ownership.** `authorization.py`'s policy loader and writers are owned by the 73-T02/POLICY unit. 72-T01 through T06 only import and consume `load_policy_readonly` and `resolve_memory_scope`.
- **No fabrication.** No simulated metrics, no inferred user approval, and no `unavailable` turned into `passed`. User memory is never deleted for recovery, and permissions are never weakened to make a demo work.
- **Re-dispatch per task.** Each Worker, Scout and Judge task gets a real `goal-worker`/`goal-scout`/`goal-judge` dispatch. A stall licenses PM fallback for that task only.
- Run `rush_check` (Rush MCP) on changed code before each unit's commit.

## Decisions (D1, D3 and D4 decided; D2 pending owner review of the T012 note)

- **D1 — T08 benchmark output path.** Plan 72-T08 writes paired-eval output to `.scratch/phase-72-memory-eval/{current,hybrid}`. That conflicts with the owner rule "never write to .scratch". **Decided 2026-10-05 (owner answer "1"):** T048 writes the raw output to `docs/reports/phase-72-memory-eval/{current,hybrid}/`, records its size, and commits it on the phase branch. `phase-72-memory-acceptance.md` cites those files. T048's `allowed_files` include that directory.
- **D2 — 75-T02/EVALUATOR checkpoint scope.** This checkpoint is undefined in the Phase 75 plan. Checked at prep: `scripts/benchmarks/run.py` has `--suite/--variant/--seeds/--allow-live-route` but not the `--decision-mode`, `--decision-route` or `--task-manifest` flags that 72-T08 uses, and `tests/fixtures/phase75/task_manifest.json` does not exist. T012 drafts the exact boundary from 75-T02's text. **The owner reviews the T012 note before T043 (EVALUATOR RED tests) runs.**
- **D3 — 73-T09 portable-capsule codec.** Plan §8 closes the real PAS/Rush-capsule import route only through 73-T09's codec and public operation. `src/rush/memory/capsule.py` does not exist on `07775f1`. T01 and T06 can build their parts on canonical record fixtures, but the live import walkthroughs (T041 and T052) need the codec. 73-T09 imports through 72-T06's `apply_import_records`, so the two phases depend on each other. **Decided 2026-10-05 (owner answer "1"):** a 73-T09/CODEC checkpoint unit on this board (gate T010, RED T036, implement T037, review T038), between 72-T06 and 72-T07. Its gate pins the boundary: Rush-capsule and PAS schema-1 codecs, loss manifest, read-only preview, export policy, import only through `apply_import_records`, and the `rush memory capsule` CLI/MCP route. The rest of 73-T09 stays with Phase 73: agent hooks, the agent-connection journey, its user views, real-host and offline-machine acceptance, and its adoption report.
- **D4 — which venv.** The owner rule says reuse an existing venv and never build one per worktree. The worktree has none, and the plan's `uv run` commands would create `phase-72/.venv` (the Phase 70 worktree's venv is 409 MB). Pointing `UV_PROJECT_ENVIRONMENT` at another worktree's venv would make `uv` re-sync that venv's editable install to Phase 72 sources. **Decided 2026-10-05 (owner answer "1"):** one new `.venv` in the Phase 72 worktree, created once in T001, the only venv agents use, and deleted with the worktree after merge.

### Decisions raised by the design gates (2026-10-05)

Each item names the task it gates. A task does not start while its decision is open, and the PM checks this before every activation. The full text of each decision is in the cited gate note.

**Decided:**
- **T004 OD-1:** rows with no write-time integrity binding stay usable in ordinary recall. They are labelled `backfilled` or `unbound`.
- **T004 OD-3:** the five raw read sites in `experience.py`, `intent.py` and `verification.py` are fixed in 72-T01, in T019.
- **T003 relink row:** amended by the PM after T015. This was an internal spec correction, not an owner decision.

**Open:**

| Decision | Topic | Gates | Gate note |
|---|---|---|---|
| T004 OD-2 | API-diff baseline: `main` or the repo's default branch | Not blocking. Defaults to `main` | T004 |
| T006 | Trust-tier ordering for derived summaries | T024 | T006 |
| T008 OD-1 | What counts as user confirmation of a preference | T030 | T008 |
| T008 OD-2 | Authority of legacy un-promoted preferences | T030 | T008 |
| T011 D-T07-1 | Consent path for "denied" screens. It also affects 72-T04 maintain usability (T007) | T039 | T011 |
| T010 OD1-OD3 | CODEC decisions | T036 | T010 |
| T012 D2 (OD1-OD13) | EVALUATOR boundary | T043, and through it T046 | T012 |
| T013 OD-T08-1 to OD-T08-7 | Hybrid evaluation | T046 | T013 |
| T014 OD1-OD3 | Release artifact, live models, push | T052 lanes only | T014 |

**Open, outside the units:** the operator decides whether to file each of these as an issue or a board task.
- The baseline failure `tests/test_phase70_tui_usability_ef.py::test_t28e_tokens_git_artifacts`, a Phase 70 artifacts view.
- The `PluginTrustStore` repo-local ledger risk (T007).

**PM amendments due before the RED task of the named unit:**
- **T010 A1-A6 to the 72-T06 packages,** before T033.
- **T007 and T008 required board updates to T06 and T07,** before T033 and T039:
  - operation counts move 22→23→25;
  - content-level applicability;
  - corroboration independence for imports;
  - the TUI shared predicate.
- **T006/T003 grant-op mapping:** `link` and `consolidate` map to `write`, and `related` maps to `ask`. Applies to T024.

**Shared-file order.** `store.py`, `tools/memory.py`, `retrieval.py`, `request_models.py`, `cli.py` and the operation-count tests are edited by several units. Edits happen only in unit order (POLICY, T01, T02, T03, T04, T05, T06, CODEC, T07, EVALUATOR, T08, T09), with one writer at a time (`max_write_workers: 1`). Every RED task first re-checks its gate's code map against HEAD.

## Stop Rule

Stop only when a final audit proves the full original outcome is complete.

Do not stop after planning, discovery, or Judge selection if the user asked for working software or automation and a safe Worker task can be activated.

Do not stop after one Worker package passes its checks when the broader owner outcome still has safe local follow-up work. Advance the board to the next highest-leverage safe Worker package and continue unless a phase, risk, rejected-verification, ambiguity, or final-completion review is due.

Do not create one Worker/Judge pair per repeated file, table, route, or helper. Put repeated same-shape work into one Worker package and review the package as a whole.

## Slice Sizing

Safe means bounded, explicit, checked, and reversible. It does not mean tiny.

A good task is the largest safe useful slice. Here, one slice is one plan packet.

A Worker should finish the whole assigned slice. A Judge should judge the whole assigned slice. A PM should reorient the board when tasks are safe but not moving the outcome.

Do not stop because a slice needs owner input, credentials, production access, destructive operations, or policy decisions. Mark that exact slice blocked with a receipt, create the smallest safe follow-up or workaround task, and continue local, non-destructive work that can still move the goal toward the full outcome. Live-provider lanes (for example `openai-codex-oauth-cli-live`) block only their named lane.

If an exact human approval phrase is the only remaining blocker and no safe local work remains, ask once and stop. Preserve the exact phrase in the blocked receipt as `required_reply`, set `waiting_for_user_approval: true`, set `goal.status: blocked`, and set `active_task: null`.

## Board Health

```bash
node /Users/jamesdsizemore/.claude/skills/goal-prep/scripts/check-goal-state.mjs docs/goals/phase-72-memory-correctness
```

Run from the worktree root. Repair only GoalBuddy control files unless an active Worker or PM task explicitly allows product-file edits.

## Canonical Board

Machine truth lives at:

`docs/goals/phase-72-memory-correctness/state.yaml` (inside the phase-72 worktree)

If this charter and `state.yaml` disagree, `state.yaml` wins for task status, active task, receipts, verification freshness, and completion truth.

## Run Command

Run from `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72`:

```text
Codex: /goal Follow docs/goals/phase-72-memory-correctness/goal.md.
Claude Code: /goalbuddy Follow docs/goals/phase-72-memory-correctness/goal.md.
```

## PM Loop

On each `/goal` continuation:

1. Read this charter, and follow the GoalBuddy execution contract (`references/goal-execution.md` in the goal-prep skill).
2. Read `state.yaml`.
3. Run the bundled GoalBuddy update checker and mention a newer version without blocking.
4. Re-check the intake: original request, input shape, authority, proof, blind spots, existing plan facts, likely misfire, and the open decisions D1-D4.
5. Work only on the active board task. Check disk before each dispatch.
6. Assign Scout, Judge, Worker, or PM according to the task.
7. Write a compact task receipt.
8. Update the board.
9. If safe local work remains, choose the next task and continue unless blocked.
10. If a problem, suggestion, or follow-up should become a repo artifact, ask the operator whether to create it.
11. Review at the per-unit review task and at the final audit.
12. Before ending the host turn, run `node /Users/jamesdsizemore/.claude/skills/goal-prep/scripts/check-can-stop.mjs docs/goals/phase-72-memory-correctness`. A nonzero result means safe work remains. Finish only when this gate passes and a Judge/PM audit receipt records `full_outcome_complete: true`, or when the checker validates the exact terminal approval-wait shape.
