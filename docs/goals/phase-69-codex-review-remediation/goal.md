# Phase 69 — Codex Adversarial Review Remediation

## Objective

Close all 51 findings (35 P1, 16 P2) from the independent Codex adversarial
review at `docs/reports/69-dashboard-tui-codex-implementation-review.md`
against Phase 69's shipped `src/rush/dashboard/`, `src/rush/tui.py`,
`src/rush/workflows/project_run.py`, and related files (implementation
frozen at commit `ea88324eae379c96b4fb2553d7247ea340b3cc16`). The review's
verdict is **NOT COMPLETE / NO-SHIP**: Phase 69's own implementation goal
(`docs/goals/phase-69-dashboard-tui-contract-remediation/`) shows its 8
packets done, but this separate, later adversarial pass found the shipped
behavior does not actually satisfy Phase 66's §3 contract or Phase 69's own
plan in 51 concrete, reproducible ways. This goal is a distinct tranche from
that implementation goal — it remediates defects found *after* Phase 69
shipped, not the original packet work.

Coverage: 51 of 51 findings in the review doc (S01-S16 = 16, M01-M21 = 21,
U01-U11 = 11, D01-D03 = 3) individually extracted, grouped by the review
doc's own §9 repair-boundary table, and assigned to exactly one task below.
verified-by: `rtk grep -c "^### S[0-9]"`, `"^### M[0-9]"`, `"^### U[0-9]"`,
`"^### D[0-9]"` run against the review doc this session, returning 16, 21,
11, 3 (sum 51); task assignment cross-checked against the Slice Sizing table
below, which also sums to 51 with zero gaps and zero duplicates.

## Original Request

Prior session (2026-09-18) ran a full hands-on verification pass against
this review doc, whose own §12 records the result: 51 of 51 findings'
Evidence citations re-checked against live source that session and matched,
the two runnable security probes in §10 executed directly (both reproduced
exactly as documented), and named `test_snake_case` regression-test
identifiers added per finding so a coding agent has literal names to create
rather than inventing its own (verified-by: review doc §12, read in full
this session). The user's explicit, repeated instruction across that
session was to review the entire doc, verify every finding, and fix all
identified issues — not merely document them. `/goal-prep` was re-invoked
this session pointed at the same review doc to turn that already-reviewed
but not-yet-implemented review into an executable board.

## Intake Summary

- Input shape: `existing_plan` — the review doc's §3-§9 give, per finding, an
  Evidence citation, Impact, and a Fix with a named Regression/acceptance
  check; §11 records a second independent fix-design re-review (38 of 51 fix
  blocks corrected/strengthened, 13 retained as-is); §12 adds literal
  `test_snake_case` names for every finding's regression scenario. This is
  a plan that has already been through two independent adversarial passes
  plus this session's own re-verification, not a first draft.
- Audience: Rush maintainer (repo owner); indirectly every `rush dashboard`
  and `rush ui` user, since the findings are user-visible correctness and
  security defects (session-fixation-shaped bootstrap race, orphaned child
  processes after "recovery", secret leakage into finding text, missing
  security headers, etc).
- Authority: `requested` — user asked for this board to be prepared; execution
  starts separately via `/goalbuddy`.
- Proof type: `test` — every S/M/U finding has a named pytest regression test
  (or, for browser-acceptance findings, a named live-browser acceptance
  check); D-series findings use a manual documentation walkthrough as their
  own correct acceptance method (no test surface).
- Completion proof: all 51 of 51 findings closed (see Coverage line above for
  the enumerated set) — each one's cited defect fixed, its named regression/
  acceptance check passing, and its receipt recorded — per the review doc's
  own §9 "Coding-agent handoff and closure criteria": reproduce the defect
  first (RED), implement the shared correction once and update every named
  caller, close only after the exact acceptance assertions pass, record
  changed files/command/exit/platform/new source hash.
- Goal oracle: `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12
  --extra dev python -m pytest tests/ -q` (full suite) green, plus
  `scripts/sync_docs.py --check` clean, plus every browser-acceptance finding
  (U05, U06, U07, U08, U10, U11 — 6 of the 51) actually exercised through a
  live browser session (not an API-only proxy), plus a final Judge audit
  (T999) mapping every one of the 51 findings' receipts back to this review
  doc's own §3-§6 Fix/acceptance text and §12 named tests.
- Likely misfire: treating a finding's named test going green as proof the
  finding is closed without confirming the RED test actually reproduced the
  cited defect first (§9's own point 1) — several findings are races,
  recovery-ordering, or check-then-act defects where a shallow test can pass
  against a shallow fix; or silently treating a Windows-gated test (S03's
  nine platform-gated tests) as closed without ever running it on that
  platform; or closing a browser-acceptance finding via an API probe instead
  of the specified visible-control journey (§9 explicitly forbids this
  substitution).
- Blind spots considered:
  - This session's environment is macOS only. verified-by: `uname -s` run
    this session, printed `Darwin`; no Windows or Linux host is reachable
    from this session. S03's nine Windows-gated tests can be implemented per
    spec and their logic-testable half unit-tested here, but cannot be
    executed on the actual target OS in this environment — name this gap
    explicitly in T003's receipt, never silently skip or claim checked.
  - Six of the 51 findings (U05, U06, U07, U08, U10, U11) are explicitly
    browser-acceptance, not pytest-provable, per the review doc's own U-series
    listing in §12. T011 (a Judge checkpoint) exists specifically to confirm
    `browser-qa-agent`/`e2e-runner`/`mcp__claude-in-chrome__*` is actually
    usable in the executing session before T013 commits to those six
    findings.
  - U09 has an unresolved reproduction discrepancy the review doc itself
    records honestly in §12: the original review session observed one
    failure in `test_no_color_env_suppresses_ansi_color_codes`; a later
    9-for-9 re-run in that same doc's §12 (isolated, full module, focused
    suite, and full 2567-test suite) could not reproduce it once. The
    underlying race (`_collect` not draining/joining the reader thread
    before PTY close, `tests/test_tui_terminal.py:215`) is real by
    construction regardless of reproduction rate — T014 must fix the race,
    not chase the flake.
  - The existing sibling goal `docs/goals/phase-69-dashboard-tui-contract-remediation/`
    (implementation of the original 8 packets) shows `active_task: null`, 36
    tasks done, 4 blocked. verified-by: `rtk grep -c "status: done"` /
    `"status: blocked"` / `"^active_task"` run against that goal's
    `state.yaml` this session, returning 36 / 4 / `active_task: null`. That
    goal is a *different* tranche — it validated the packets shipped; this
    goal validates whether what shipped is actually correct. Do not
    conflate the two boards or treat that board's "done" tasks as evidence
    this goal's findings are already closed.
  - This goal's review-doc citations still target the current tree, not a
    stale one. verified-by: `rtk git log -1 --format="%H %s"` run this
    session on branch `phase/69-dashboard-tui-contract-remediation`,
    returning `ea88324eae379c96b4fb2553d7247ea340b3cc16` — the exact hash
    the review doc froze on.
  - `goal-scout`, `goal-judge`, `goal-worker` agent configs are all
    installed. verified-by: `rtk ls ~/.claude/agents` run this session,
    listing `goal-judge.md`, `goal-scout.md`, `goal-worker.md`.
- Existing plan facts (preserved from the review doc, to validate at each
  task's own RED step, not rediscover):
  - The review doc's §9 "Findings / repair boundary" table groups all 51
    findings by shared existing test files — this goal's Worker task
    boundaries below are read directly off that table, not invented.
  - The review doc's §9 "Repair sequence" (1-5) sets required execution
    order: execution-safety findings first (its own step-1 text literally
    reads "S01-S05, S07-S10,S15/S16, U02/U03, then auth/redaction/header/
    schema gaps" — a dash-range that skips S06 by omission; S06 is included
    here anyway because the §9 repair-boundary table explicitly groups it
    with S04-S10/S16 under one shared-test-file boundary, S06 appears
    nowhere else in the 5-step sequence, and leaving a P1 finding with no
    sequence slot at all would be a worse reading than treating the gap as
    an editorial range-notation artifact — T004 includes S06), then
    provenance/ownership (M01-M09, M12/M13, M15-M21 first, THEN M10/M11/M14
    telemetry — note the explicit ordering: an earlier draft of this board
    had M12 sequenced after telemetry instead of before, caught on a direct
    re-diff against source and fixed), then user-facing browser/terminal
    routes (U01/U04-U08, U10/U11), then U09's harness fix plus one full
    regression run, then documentation reconciliation (D01-D03) and a final
    independent re-review. This goal's task order follows that sequence.
  - The review doc's §9 "Dependencies" paragraph is binding, quoted here
    directly rather than paraphrased (an earlier paraphrase of this exact
    paragraph invented an unstated S09-to-S10 causal link, dropped the
    "without nesting project/run locks" constraint, dropped "authenticated"
    and the M09 clause, and omitted the provisioning/S07/S16 boundary
    entirely — caught only on a direct line-by-line re-diff against source
    after this board was already written once):
    "S04 supplies persisted effect inputs for S05/S16. S02's dead-owner
    fencing is independently repairable; it does not require S09's later
    attempt-schema work. S03 supplies the native Windows owner primitive.
    S09 supplies exact scan attachment identity; S10 supplies durable
    cancellation for U02, including CHECK_SUITE and cross-server delivery.
    S08/M01/M02 must agree on shared publication and never-scanned genesis
    identity without nesting project/run locks. M01 supports M07;
    M02/M03/M13/M15-M21 share one provenance contract. M12 precedes U05's
    lossless downloader. M08 supplies authenticated session-owner exposure
    for U10, while M09 extends maintenance callers. S04/S05/S06/S07/S16
    precede complete U06 handoff: exact source attempt, stable envelope,
    effects, and async recovery must agree. Provisioning uses its own
    durable job identity; S07/S16 do not force it into scan-attachment
    admission. Shared corrections receive one implementation and every
    affected acceptance case." S09 and S10 are grouped in the same task
    (T004) below because they are evidently related (attempt identity feeds
    cancellation resolution), even though the source text states them as
    two separate facts rather than an explicit dependency — do not treat
    that grouping as proof of an ordering requirement the source doesn't
    actually state.
  - Shared files touched by many findings — `src/rush/dashboard/server.py`,
    `src/rush/dashboard/state.py`, `src/rush/dashboard/auth.py`,
    `src/rush/tui.py`, `src/rush/workflows/project_run.py` — must be
    re-read immediately before each edit (review doc §9 handoff instruction
    1's "Reopen the cited source at the implementation checkout before
    editing"): line numbers in the review doc refer to the frozen hash and
    may have shifted after an earlier task in this same goal edits the same
    file.
  - §10's two runnable security probes (S11 bootstrap race, S02 dead-owner
    admission release) were executed directly in the prior session and
    matched the review's claimed output exactly, per the review doc's own
    §12 — they are ready-to-run regression material for T003, not just
    prose.

## Goal Oracle

`rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev
python -m pytest tests/ -q` (full suite) green, `scripts/sync_docs.py --check`
clean, all 6 of the 51 findings that are browser-acceptance
(U05/U06/U07/U08/U10/U11) exercised through a real live browser session with
recorded evidence (not an API-only substitute — the review doc's §9
explicitly forbids that substitution), and a final Judge audit (T999)
mapping all 51 findings' receipts back to this review doc's own §3-§6
Fix/acceptance text and §12 named tests, per the review doc's own §9 closure
criteria.

The PM must keep comparing task receipts to this oracle. A green
task-scoped pytest command is progress evidence for that task's findings
only, never a substitute for the full-suite + `sync_docs.py --check` +
live-browser-evidence + final-audit oracle above.

## Goal Kind

`existing_plan`

## Current Tranche

All 51 findings (see Coverage line in Objective for the enumerated set) from
`docs/reports/69-dashboard-tui-codex-implementation-review.md`, remediated
in the review doc's own required repair-sequence order, each task's own RED
(reproduce the cited defect) → fix → named regression/acceptance check
passing, before the next task starts. This is not a "pick a few findings and
stop" tranche: the review's verdict is NOT COMPLETE / NO-SHIP for the whole
phase, so the tranche is all 51 findings plus the final independent-
re-review closure step the review doc's own §9 repair sequence step 5
requires.

## Non-Negotiable Constraints

- Follow the review doc's own repair-sequence order (§9): execution-safety
  findings first, then provenance/ownership, then user-facing browser/
  terminal routes, then U09's harness fix plus a full regression run, then
  documentation reconciliation and a final independent re-review. Do not
  reorder past what §9's own "Dependencies" paragraph requires.
- Before editing any shared file (`server.py`, `state.py`, `auth.py`,
  `tui.py`, `project_run.py`), re-read the current file first — an earlier
  task in this same goal may have already shifted the review doc's cited
  line numbers.
- Reproduce each finding's cited defect with a named failing regression test
  before the production fix (TDD), using the exact `test_snake_case` names
  the review doc's own §12 already supplies where given. Run `ruff check`
  and `ruff format` on changed Python.
- A finding's named test going green is not itself closure — confirm the RED
  test actually exercised the cited defect (ran red against the pre-fix
  code) before treating the GREEN result as proof, per the review doc's own
  §9 point 1.
- A platform-gated test (S03's nine Windows-gated tests) cannot run on its
  target OS in this environment. verified-by: `uname -s` run this session,
  printed `Darwin`. Implement it per spec and unit-test its logic-testable
  half locally; name it explicitly as unverified-on-that-platform in the
  task's receipt — never silently skip it or claim it was checked on that
  platform.
- A browser-acceptance finding (U05, U06, U07, U08, U10, U11 — 6 of the 51)
  must be closed through a real live browser session (`browser-qa-agent`/
  `e2e-runner` subagent, or `mcp__claude-in-chrome__*` tools directly) —
  never substitute an API-only probe for the specified visible-control
  journey; the review doc's own §9 explicitly forbids this substitution.
  Confirm the mechanism is actually usable in the executing session at the
  T011 Judge checkpoint before committing to these six findings.
- Do not lower the contract, remove an inconvenient assertion, or weaken a
  finding's specified acceptance check to make it pass more easily.
- Stay off `main` for this goal's own branch — no production release, hooks,
  paid-provider invocation, or destructive user-data action is authorized by
  planning.
- Root `AGENTS.md`, `docs/templates/task-block-template.md`, Phase 66's own
  §3, and Phase 63's real `MemoryArtifact`/`MemoryTool` API remain binding
  unless a specific finding's own Fix text explicitly supersedes a clause.
- Do not conflate this goal with the sibling implementation goal
  `docs/goals/phase-69-dashboard-tui-contract-remediation/` — that board
  tracks the original 8 packets (36 done, 4 blocked, distinct tranche); this
  board tracks the 51 post-implementation review findings. Never use that
  board's task statuses, active_task, or receipts to decide anything about
  this goal's own tasks, and never mark any of that board's tasks
  done/not-done from here. The one named exception is T015/D03: the review
  doc's own D03 Fix text requires appending a superseding current-review
  statement to that board's `state.yaml` (its T038/T999 receipts claim
  complete while this review's verdict is NOT COMPLETE — that contradiction
  is itself part of what D03 closes). T015 may only append that statement;
  it may never edit an existing historical receipt's recorded outcome or
  touch that board's `active_task`/task statuses.

## Stop Rule

Stop only when the final Judge audit (T999) proves all 51 of 51 findings
closed — each with its cited defect fixed, its named regression/acceptance
check passing, and a receipt mapping back to the review doc's own §3-§6 Fix
text — plus the full suite green, `scripts/sync_docs.py --check` clean, and
all 6 of the 51 browser-acceptance findings exercised with recorded
live-browser evidence. Record `full_outcome_complete: true` only then.

Do not stop because a Windows-gated test can't run on this macOS
environment — implement it per spec, name the gap in the task's receipt,
and continue (the review doc's own S03 finding already names this as an
expected, not blocking, gap in this environment).

Do not stop because U09's originally-observed failure could not be
reproduced in a later session — fix the underlying race by construction
(drain/join the reader thread before PTY close) regardless of reproduction
rate, per the review doc's own §12 U09 entry.

## Slice Sizing

Task boundaries below are read directly off the review doc's own §9
"Findings / repair boundary" table (which groups findings by shared existing
test files) and its §9 "Repair sequence" (which sets execution order) — not
invented. 51 of 51 findings (see Coverage line in Objective) split into 11
Worker tasks (not 51 tiny tasks, not one mega-task), bounded by 4 Judge
checkpoints (readiness, post-safety, pre-browser, final audit) plus one
Scout readiness-mapping task:

| Task | Findings | Count |
|---|---|---:|
| T003 | S01, S02, S03, S15, U03 | 5 |
| T004 | S04-S10, S16, U02 | 9 |
| T005 | S11-S14 | 4 |
| T007 | M01-M06, M13, M15-M21 | 14 |
| T008 | M07, M08, M09 | 3 |
| T009 | M12 | 1 |
| T010 | M10, M11, M14 | 3 |
| T012 | U01, U04 | 2 |
| T013 | U05, U06, U07, U08, U10, U11 (browser-acceptance) | 6 |
| T014 | U09 (harness fix + full regression run) | 1 |
| T015 | D01, D02, D03 | 3 |

Total: 5+9+4+14+3+3+1+2+6+1+3 = 51 of 51 findings, zero gaps, zero
duplicates. verified-by: sum computed this session and cross-checked
against the 16/21/11/3 = 51 header count in the Coverage line above; every
finding ID S01-S16/M01-M21/U01-U11/D01-D03 appears in exactly one task row.

## Board Health

Baseline this session, before board creation:

- `git log -1` on `phase/69-dashboard-tui-contract-remediation` →
  `ea88324eae379c96b4fb2553d7247ea340b3cc16` — matches the review doc's
  frozen hash exactly.
- `git status --short` → 42 entries, all untracked tooling/config noise
  (`.claude/`, `.codex/`, `.DS_Store` files, `.rush/` runtime dirs, etc) and
  one modified `AGENTS.md` — no source files under `src/rush/` are dirty.
- The review doc's own §12 records: 51 of 51 findings' Evidence citations
  re-checked against live source that session and matched (one correction:
  U01's `terminal_input.py` line numbers); both §10 security probes executed
  directly that session and matched documented output exactly; the full
  suite run that session (`pytest tests/ -q`) returned `2567 passed, 6
  skipped, 16 warnings in 408.35s` — zero failures.

If the board looks stale, misleading, offline, or inconsistent, run the
bundled checker:

```bash
node <skill-path>/scripts/check-goal-state.mjs docs/goals/phase-69-codex-review-remediation
```

## Canonical Board

Machine truth lives at:

`docs/goals/phase-69-codex-review-remediation/state.yaml`

If this charter and `state.yaml` disagree, `state.yaml` wins for task
status, active task, receipts, verification freshness, and completion
truth.

## Run Command

```text
Codex: /goal Follow docs/goals/phase-69-codex-review-remediation/goal.md.
Claude Code: /goalbuddy Follow docs/goals/phase-69-codex-review-remediation/goal.md.
```

## PM Loop

On every `/goal` continuation:

1. Read this charter, and follow the GoalBuddy execution contract
   (`references/goal-execution.md` in the goal-prep skill) when available.
2. Read `state.yaml`.
3. Run the bundled GoalBuddy update checker when available and mention a
   newer version without blocking.
4. Re-check the intake: original request, input shape, authority, proof,
   blind spots, existing plan facts, and likely misfire.
5. Work only on the active board task.
6. Assign Scout, Judge, Worker, or PM according to the task.
7. Write a compact task receipt.
8. Update the board.
9. If safe local work remains, choose the next largest reversible Worker
   package and continue unless blocked.
10. If a problem, suggestion, or follow-up should become a repo artifact,
    create an approved issue/PR or ask the operator whether to create one.
11. Review at phase, risk, rejected-verification, ambiguity, or
    final-completion boundaries; do not review every small Worker by habit.
12. Before ending the host turn, run
    `node <skill-path>/scripts/check-can-stop.mjs docs/goals/phase-69-codex-review-remediation`.
    A nonzero result means safe work remains and the PM must continue.
    Finish only when this gate passes and a Judge/PM audit receipt maps
    receipts and verification back to the original user outcome with
    `full_outcome_complete: true`, or when the checker validates the exact
    terminal approval-wait shape.

Issue and PR handoffs are supporting artifacts. `state.yaml` remains
authoritative, and every external artifact decision must be recorded in a
task receipt.
