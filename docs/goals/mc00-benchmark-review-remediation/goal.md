# MC00 Benchmark Review Remediation

## Objective

Execute the already-written, already-verified remediation plan at
`docs/phase-plans/MC00-benchmark-review-remediation-plan.md` — resolve 9 of 9 findings from
`/ultrareview 386a272` in `scripts/benchmarks/memory.py` and `scripts/benchmarks/fixtures.py`
(Findings 1-7 and 9 as code changes, Finding 8 as a verified no-op — see Coverage below) — under
strict TDD (new-test red proof before the fix, green after), a mandatory adversarial code-review
pass (CR1 + CR2) after every Worker slice with all findings addressed before moving on, zero
scope drift beyond the plan's named files and findings, and doc updates reflecting the real
outcome.

**Coverage**: the plan doc enumerates exactly 9 findings from the ultrareview (Findings 1-9,
numbered in the plan's own text); this goal's scope is those 9 and no others. 7 of 9 are direct
code edits (Task A covers 1, 2, 3, 5, 6, 7; Task B covers 4 and 9), 1 of 9 (Finding 8) is a
verified no-op requiring no code change, 0 of 9 are out of scope or deferred.

## Original Request

"docs/phase-plans/MC00-benchmark-review-remediation-plan.md - Ensure that after each task
completion, you complete an adversarial review of the developed code, and address all fixes.
Ensure that the goal board does not include any semantic drift and is scoped to the tasks and
allowed files. Ensure that docs are updated. Ensure you use TDD with explicit red/green cross
testing."

## Intake Summary

- Input shape: `existing_plan`
- Audience: repo maintainer (James), future readers of the benchmark harness
- Authority: `requested`
- Proof type: `test`
- Completion proof: 9 of 9 findings from the plan resolved in the real diff (see Coverage
  above for the breakdown); the 5 new tests named in the plan's Task D exist, were captured
  failing (RED) against pre-fix source, and pass (GREEN) after the fix; the full existing suite
  (baseline 2264 passed per most recent session record) still passes; `ruff`/`mypy` clean on
  both touched files; CR1 and CR2 both return clean (zero unresolved findings) for each Worker
  slice; the plan doc itself is updated to reflect actual outcome; no file outside the 4-file
  touch-list named in Non-Negotiable Constraints below is touched.
- Goal oracle: `rtk pytest tests/test_benchmark_memory.py tests/test_benchmark_contracts.py -v`
  all green, plus `rtk pytest -q` full-suite green, plus `rtk ruff check` and `rtk mypy` clean
  on `scripts/benchmarks/memory.py` and `scripts/benchmarks/fixtures.py`, plus a CR1/CR2 receipt
  pair with zero open findings per touched file, plus a diff review confirming M01/M05 behavior
  and every file outside the touch-list are byte-identical to `git show 386a272` + this plan's
  own prior verification pass.
- Likely misfire: marking done after tests go green but skipping the mandated CR1/CR2 pass;
  writing the 5 new tests already passing (no real RED baseline, so "TDD" is theater not proof);
  scope-creeping into redesigning M01/M05 or touching `scripts/benchmarks/run.py`,
  `src/rush/tools/memory.py`, or any other file the plan doesn't name; silently declaring
  Finding 8 "fixed" (the plan already resolved it as a documented no-op — re-opening it is
  drift, not diligence).
- Blind spots considered: the plan's Task A bundles 6 sub-edits (A1-A6) in one function — kept
  as ONE Worker slice (not six) per Slice Sizing Policy, since they're the same-shape edit
  landing in the same ~90-line function and splitting them would just be six tiny-task
  wrappers around one coherent rewrite. TDD-first ordering means the 5 new tests are written
  and proven RED *before* Task A's implementation, not after — this reorders the plan doc's own
  Task A → Task D sequence into Task D-tests → Task A-impl for execution purposes; the plan doc
  itself is not wrong, its written order just isn't the required *execution* order for
  red/green proof.
- Existing plan facts (preserve, validate before executing): the full remediation plan at
  `docs/phase-plans/MC00-benchmark-review-remediation-plan.md`, written and independently
  verified against live source in this same session (file:line citations for every claim,
  including two corrections to the original review's own findings — Finding 8's guard is kept,
  not removed, because a real test depends on it; Finding 9's duplicate count was corrected
  from 3 to 2 occurrences). That plan is the spec. Task T001 below re-validates it has not
  drifted since (git status on the target files was clean/untouched at goal-prep time) before
  any Worker task starts.

## Goal Oracle

`rtk pytest tests/test_benchmark_memory.py tests/test_benchmark_contracts.py -v` and
`rtk pytest -q` both green, `rtk ruff check` and `rtk mypy` clean on the two touched files, and
a CR1+CR2 receipt pair with zero open findings per Worker slice.

The PM must keep comparing task receipts to this oracle, including the RED evidence captured
before each fix. A green test suite with no captured RED baseline does not satisfy this oracle.

## Goal Kind

`existing_plan`

## Current Tranche

Execute Tasks A, B, C (no-op), and D from the plan, in TDD order: write the 5 new tests first
and capture them failing against current source, implement `scripts/benchmarks/memory.py`'s
fixes to turn them green (plan Task A, A1-A6 as one slice), CR1+CR2 that slice, implement
`scripts/benchmarks/fixtures.py`'s dedupe (plan Task B), CR1+CR2 that slice, update docs (the
plan file's own status plus any stale docstrings in the two touched files), then a final audit
against the plan's own Verification section (5 numbered checks, all 5 required). This tranche
is complete when every one of those 5 checks passes and the plan doc reflects the real outcome
— this is a bounded tranche, not a continuous/open-ended goal.

## Non-Negotiable Constraints

- Follow `docs/phase-plans/MC00-benchmark-review-remediation-plan.md` exactly. Do not
  re-derive, re-argue, or redesign any of the 9 findings' fixes — the plan already verified
  every claim against live source this session. If live source has drifted since (check at
  T001), stop and re-verify only the drifted part, don't restart from scratch.
- Touch only these 4 files: `scripts/benchmarks/memory.py`, `scripts/benchmarks/fixtures.py`,
  `tests/test_benchmark_memory.py`, `docs/phase-plans/MC00-benchmark-review-remediation-plan.md`.
  `tests/test_benchmark_contracts.py` is read/verify-only (the plan explicitly says its two
  assertions are unaffected) — no Worker task may edit it. No task may touch
  `scripts/benchmarks/run.py`, `scripts/benchmarks/reporting.py`, any other
  `scripts/benchmarks/*.py` probe module, or anything under `src/rush/`. `src/rush/tools/memory.py`
  and `src/rush/memory/*` are reference-only reads for grounding the fix, never edit targets.
- M01 and M05 case behavior must stay byte-identical to current source — the plan is explicit
  that only M03/M06/M09/M10 (4 of the 6 fixture cases) grow new behavior. A diff on M01/M05's
  code paths is scope drift and must be reverted.
- Finding 8 (path-traversal guard on `scenario_id`) is already resolved by the plan as a
  documented no-op (kept, not removed — a real test depends on it). No task may "fix" it again.
- TDD is mandatory and must be evidenced, not asserted: the Worker task that adds the 5 new
  tests must run them against pre-fix source and paste the actual failing pytest output into
  its receipt (RED) before any implementation task starts; the Worker task that implements the
  fix must paste the actual passing pytest output (GREEN) into its receipt. A receipt claiming
  "tests pass" with no RED evidence attached fails T999's audit.
- Adversarial review is mandatory and must address findings, not just log them: after each
  implementation Worker slice, a CR1 Judge task (dispatched via the `cr-dispatch` skill's
  templated pattern, `pre-cr-audit` run first) reviews the diff; if it returns findings, a
  Worker fix task addresses them inside the same `allowed_files` as the slice it's fixing; a
  CR2 Judge task then independently re-verifies the fix (not the CR1 marker) and checks for new
  regressions. A slice is not done until CR2 is clean.
- Git workflow (hard gate, confirmed with the user 2026-09-11 — branch + commits on that branch,
  never main, never an autonomous merge): before T004 (the first file-writing Worker task) makes
  its first commit, verify the current branch is NOT `main`/`master` (it should be
  `codex/phases64-63-65-66-implementation`; if it is `main`/`master`, stop immediately — do not
  create the branch or commit anything), then create and switch to a dedicated branch
  `phase/mc00-benchmark-review-remediation` off it. Every Worker/fix commit for this goal
  (T004, T006, T008, T010, T012) lands on that branch, never on `main`, `master`, or
  `codex/phases64-63-65-66-implementation` directly. No task in this goal may run `git checkout
  main`, `git switch main`, `git merge`, or `git push` at any point — merging
  `phase/mc00-benchmark-review-remediation` back into `codex/phases64-63-65-66-implementation`
  (and that branch into `main`, separately, later) is 100% out of this goal's scope and requires
  the user to do it, or explicitly ask for it, outside this board. T999's final audit verifies
  `git branch --show-current` is `phase/mc00-benchmark-review-remediation` (not `main`, not
  `master`, not `codex/phases64-63-65-66-implementation`) and that no merge commit into any other
  branch exists. (Checked at goal-prep time: this repo's installed `goal-prep` skill does not
  currently auto-enforce branch-per-tranche or a no-merge gate in its templates — grepped
  `references/goal-execution.md`, `templates/goal.md`, and `SKILL.md` for "branch"; zero hits on
  a git-branch-default mechanism. This constraint is hand-encoded here.)
- Docs must be updated as part of this tranche, not deferred: the plan file itself gets a
  status update per task (not left describing a future/unstarted state once the work is done),
  and any docstring in the two touched files that describes now-stale behavior (e.g.
  `run_memory_probe`'s "Measure actual legacy MemoryTool writes and defended recall" line, if
  it undersells the new per-case behavior) gets corrected in the same Worker slice that changes
  the behavior it describes — not punted to a separate cleanup pass.

## Stop Rule

Stop only when T999's final audit confirms all 5 of the 5 checks in the plan's own
Verification section pass, CR1+CR2 are clean for both Worker slices, the plan doc is updated,
and no file outside the 4-file touch-list in Non-Negotiable Constraints differs from its
pre-goal state.

Do not stop after the tests go green if CR1/CR2 have not yet run on that slice. Do not stop
after CR1 finds nothing to fix and skip CR2 — CR2 runs regardless, to independently confirm
"nothing to fix" was actually correct, not assumed.

## Design Correction (confirmed with user 2026-09-11, mid-execution at T004)

The plan's Task A6 table specified deriving M06's `payload_truncated` from `recall_page`'s
`complete` field (`not data["complete"]`) and M10's pagination from a tight `max_tokens` budget
forcing repeated compact `ask` calls. Both are structurally unreachable given `recall_page`'s
real behavior: `complete` only reflects the internal 512-row scan cap (`_SCAN_CAP`), never
`max_bytes`/`max_tokens` truncation — confirmed via a full read of `recall_page`'s loop
(`src/rush/memory/retrieval.py:308-452`), the function's own docstring (ties `complete` only to
the scan cap), and an existing passing test (`tests/test_memory_retrieval.py::test_serialized_payload_obeys_both_caps`)
that already exercises budget truncation on a 20-record store without ever asserting
`complete is False`. This is pre-existing, deliberately tested, documented behavior, not a bug —
and `_compact_query` (`src/rush/tools/memory.py:626`) passes it straight through to every real
compact-ask consumer, so changing it would be a production behavior change affecting callers
outside this benchmark, not a one-line fix. The user was asked and explicitly declined touching
`src/rush/` for this (two corrected rounds — an initial "grow the fixture" framing was itself
incomplete, since `budget_full` breaks `recall_page`'s scan loop within ~8-15 records regardless
of total record count, so the scan cap can never be reached under M06/M10's tight budgets no
matter the fixture size).

**Approved correction, entirely within `scripts/benchmarks/memory.py` (no `src/rush/` touch, no
test-file changes beyond what T002 already landed):**
- M06 (`_probe_oversized_payload`): `payload_truncated` is computed by comparing the compact
  ask's returned item count against the known total records the benchmark itself wrote (passed
  in as `total_records`), not from `data["complete"]`.
- M10 (`_probe_cache_budget`): writes ~450 extra records isolated to that probe only (on top of
  the shared 100-record baseline, which stays untouched for every other case), then uses a loose
  byte/token budget so the real 512-row scan cap genuinely triggers — reproducing authentic
  multi-page continuation via the exact same `next_cursor`/`hit_cap` mechanism
  `tests/test_memory_retrieval.py::test_scan_cap_returns_continuation` already exercises and
  trusts, rather than a simulated/computed pagination count.

T002's already-CR1-approved test assertions (`payload_truncated is True`,
`compact_items_returned < 100`, `compact_paginated is True`, `compact_pages > 1`) all still hold
under this corrected mechanism unchanged — only the internal computation changed. T012 (doc
update) must record this correction in the plan doc itself, in the same style as the plan's own
existing "Corrections to the review's own findings" section for Findings 8/9.

## Slice Sizing

Task A's six sub-edits (A1-A6) are one Worker slice: same function, same file, same commit,
already scoped as a single coherent unit in the plan doc. Do not split them into six tasks.

Task B is a second, independent slice (different file, no dependency on Task A's edits) — kept
sequential on this board only because the default board model runs one active task at a time,
not because the two slices are coupled.

The 5 new tests (plan's Task D) are their own slice specifically because TDD requires them to
exist and fail *before* Task A's implementation exists — they cannot be folded into the Task A
slice without destroying the red/green proof.

## Board Health

```bash
node /Users/jamesdsizemore/.claude/skills/goal-prep/scripts/check-goal-state.mjs docs/goals/mc00-benchmark-review-remediation
```

## Canonical Board

`docs/goals/mc00-benchmark-review-remediation/state.yaml`

## Run Command

```text
Claude Code: /goalbuddy Follow docs/goals/mc00-benchmark-review-remediation/goal.md.
```

## PM Loop

On every `/goalbuddy` continuation:

1. Read this charter and `references/goal-execution.md` in the `goal-prep` skill.
2. Read `state.yaml`.
3. Re-check the intake and Non-Negotiable Constraints, especially the touch-list and the
   RED-before-GREEN requirement.
4. Work only on the active board task.
5. Assign Scout, Judge, Worker, or PM per the task's `type`.
6. Write a compact task receipt — for Worker test/impl tasks, the receipt must include the
   actual pytest output (RED or GREEN), not a paraphrase.
7. Update the board.
8. After every implementation Worker slice, run CR1 then (after any fix) CR2 before advancing —
   never skip straight to the next slice on a clean-looking diff.
9. Before ending the host turn, run
   `node /Users/jamesdsizemore/.claude/skills/goal-prep/scripts/check-can-stop.mjs docs/goals/mc00-benchmark-review-remediation`.
   Finish only when that gate passes and T999 records `full_outcome_complete: true`.
