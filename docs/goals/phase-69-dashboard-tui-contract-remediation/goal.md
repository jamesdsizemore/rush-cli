# Phase 69 — Dashboard and TUI Contract Remediation

## Objective

Implement Phase 69 in full: all 8 TDD packets (P69-01 through P69-08) in
`docs/phase-plans/phase-69-dashboard-tui-contract-remediation-plan.md`, closing
the 23 actionable gaps between Phase 66's shipped `src/rush/dashboard/` /
`src/rush/tui.py` code and Phase 66's own §3 contract. This also unblocks
Phase 68 (`docs/phase-plans/phase-68-one-command-interactive-onboarding-plan.md`),
whose P68-04/05/06/07 packets explicitly depend on Phase 69's P69-01 through
P69-05 landing first (P68-05 specifically depends only on P69-01, and can
proceed the moment that one packet ships).

## Original Request

User ran `/goal-prep Phase 68`. Phase 68's own dependency graph blocks 4 of its
7 packets on unimplemented Phase 69 work (checked via `git log --grep`: zero
implementation commits for Phase 69, only plan-doc citation-fix commits). Asked
the user how to handle that; they redirected with `/goal-prep Phase 69` instead
— i.e., prepare Phase 69 first, as the real prerequisite.

## Intake Summary

- Input shape: `existing_plan` — a fully detailed, multi-round adversarially-reviewed
  641-line TDD plan already exists at
  `docs/phase-plans/phase-69-dashboard-tui-contract-remediation-plan.md`.
- Audience: Rush maintainer (repo owner); the dashboard/TUI's real end users are
  developers running `rush dashboard`/`rush ui`.
- Authority: `requested` — the user asked for this board to be prepared, not for
  execution to start. `/goalbuddy` (or Codex `/goal`) is a separate, later,
  explicit start.
- Proof type: `test` — every packet is TDD (RED test list → GREEN implementation →
  VERIFY pytest command), per the plan's own §4.
- Completion proof: every row in Phase 66's §0 (rows 1-18, 20-24) has a passing
  named test proving the gap closed, per the plan's own §5, with only 3 named
  exceptions (row 19 already closed by Phase 66 itself; row 18's 250ms threshold
  is a sign-off decision, not a fixed target; row 13's Windows-console sub-item is
  a named, accepted blocker in this environment, see Blind Spots below).
- Goal oracle: `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest -q`
  (full suite) green, plus `scripts/sync_docs.py --check` clean of Phase 66/69
  entries (P69-08.3's own VERIFY), plus a final Judge audit mapping every
  packet's receipt back to its owning §0 row(s).
- Likely misfire: treating a packet's own pytest command going green as proof the
  packet is done without confirming the RED tests actually exercised the real gap
  first (many are crash-recovery / concurrent-kill / subprocess-race tests where a
  shallow implementation can pass a shallow test); or silently skipping the
  platform-gated Windows/Linux-only assertions instead of implementing them per
  spec and naming them as unverified-on-this-platform in the receipt.
- Blind spots considered:
  - This session's environment is macOS only, no Windows or Linux target
    machine reachable. Windows/Linux-specific mechanisms (P69-01's Windows
    privilege drop and data-dir ACL check; P69-05's Windows-console item) can
    be implemented per spec and their logic-testable half unit-tested here, but
    their platform-gated assertions cannot be executed on the actual target OS
    in this environment — that gap gets named per packet's receipt, never
    silently assumed passing.
    verified-by: ran `uname -s` this session, printed `Darwin`; no Windows or
    Linux host is reachable from this session to run those platform-gated
    assertions against.
  - P69-04 and P69-05's own VERIFY steps require a real live browser session
    (`browser-qa-agent`/`e2e-runner`, or `mcp__claude-in-chrome__*` directly)
    against a live `rush dashboard` instance — not just a pytest command.
  - Packets are strictly sequential, not parallelizable: 02 depends on 01's new
    primitives (`MutationLedger`, owner-liveness lock, `bump_sequence`, etc.), 03
    depends on 01+02, 04/05 depend on 03's map data, 06 shares files with 01/02/03,
    07 shares files with 01/02. `state.yaml`'s `max_write_workers: 1` already
    enforces this; the packet order itself (§5: "01→02→03→04→05→06→07→08") is a
    hard sequencing constraint from the plan, not just a suggestion.
  - P69-01 is explicitly called out in the plan (§1) as independently shippable
    ahead of the rest — it is the one packet Phase 68's P68-05 actually needs, so
    it's a real, useful milestone on its own, not just "packet 1 of 8."
- Existing plan facts (preserved from the source plan, to validate, not
  rediscover):
  - Packet order and dependency: P69-01 → P69-02 → P69-03 → P69-04 → P69-05 →
    P69-06 → P69-07 → P69-08 (plan §5). 02-07 build on 01's hardened auth/session
    boundary; 08 documents what the others closed.
  - Shared files (`server.py`, `auth.py`, `state.py`, `tui.py`) are touched by
    multiple packets in sequence — each packet's own RED step must re-read the
    current file before editing (plan §2); citations may have shifted from an
    earlier packet's own edits.
  - Baseline test health this session (2026-09-17): ran the 14 dashboard/TUI
    test files that already exist —
    `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/test_dashboard_http_contract.py tests/test_dashboard.py tests/test_subprocess_contract.py tests/test_dashboard_map.py tests/test_dashboard_projects.py tests/test_dashboard_motion_contract.py tests/test_tui.py tests/test_tui_terminal.py tests/test_memory_versions.py tests/test_phase61_memory_tool.py tests/test_dashboard_memory_tokens.py tests/test_dashboard_git_artifacts.py tests/test_dashboard_user_journey.py tests/test_project_run_lifecycle.py -q`
    → 116 passed, 0 failed, 5 pre-existing pty forkpty `DeprecationWarning`s
    (unrelated). Also ran `test -f tests/test_dashboard_missing_routes.py`,
    which reported missing — it's created fresh by P69-02.1's RED step, exactly
    as the plan says.
  - GoalBuddy agents installed: ran `find ~/.claude/agents -iname "goal-scout*" -o -iname "goal-judge*" -o -iname "goal-worker*"` this session, found all three
    (`goal-scout.md`, `goal-judge.md`, `goal-worker.md`).
  - No existing worktree, branch, or goal board for Phase 69 prior to this
    prep: ran `git worktree list` (only the main worktree), `git branch -a --list "*69*"` (empty), and `find docs/goals -iname "*69*"` (no matches) this
    session.

## Goal Oracle

`env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest -q` (full suite)
green, plus `scripts/sync_docs.py --check` clean of Phase 66/69 entries
(P69-08.3), plus a final Judge audit (T999) mapping every packet's receipt back
to Phase 66 §0's rows, per the plan's own §5 completion definition (with the 3
named exceptions above).

The PM must keep comparing task receipts to this oracle. A green packet-scoped
pytest command is progress evidence for that one packet, never a substitute for
the full-suite + `sync_docs.py --check` + final-audit oracle above.

## Goal Kind

`existing_plan`

## Current Tranche

The full Phase 69 phase: all 8 packets, P69-01 through P69-08, executed in the
plan's own required order, each packet's own RED→GREEN→CONNECT→VERIFY completed
and its packet-scoped pytest command green before the next packet starts. This is
not a "pick one packet and stop" tranche — Phase 68 is genuinely blocked on this
whole phase (P68-05 on P69-01 alone; P68-04/06/07 on the rest), so the tranche is
the entire phase.

## Non-Negotiable Constraints

- Follow the plan's own packet order exactly: 01→02→03→04→05→06→07→08. Do not
  reorder or parallelize — later packets depend on earlier packets' new
  primitives existing in the shared files (`server.py`/`auth.py`/`state.py`).
- Before editing any shared file (`server.py`, `auth.py`, `state.py`, `tui.py`),
  re-read the current file first (plan §2) — a prior packet in this same phase
  may have already shifted the cited line numbers.
- Reproduce each gap with a named failing RED test before the production edit,
  per the plan's own TDD discipline. Run Ruff check/format for changed Python.
- Stay off `main` for this goal's own branch (per plan §1's binding constraints)
  — no production release, hooks, paid-provider invocation, or destructive
  user-data action is authorized by planning.
- Root `AGENTS.md`, `docs/templates/task-block-template.md`, Phase 66's own §3
  (except where this plan's own §3 supersedes a specific clause), and Phase 63's
  real `MemoryArtifact`/`MemoryTool` API are binding.
- A platform-gated test (Windows ACL check, Windows-console item) cannot run on
  its target OS in this environment.
    verified-by: ran `uname -s` this session, printed `Darwin`; no Windows or
    Linux host is reachable from this session.
  Implement it per spec and unit-test its logic-testable half locally; name it
  explicitly as unverified-on-that-platform in the packet's receipt — never
  silently skip it or claim it was checked on that platform.
- P69-04/P69-05's VERIFY steps need a real live browser session, not just
  pytest. Confirm the mechanism (`browser-qa-agent`/`e2e-runner` subagent, or
  `mcp__claude-in-chrome__*` tools) is actually usable in the executing session
  before committing to those two packets — this is what the T006 Judge checkpoint
  below exists to confirm.

## Stop Rule

Stop only when the final Judge audit (T999) proves every Phase 66 §0 row is
closed (per §5's own definition, with the 3 named exceptions) and records
`full_outcome_complete: true`.

Do not stop after P69-01 ships just because it independently unblocks Phase
68's P68-05 — the tranche is the full phase; note the milestone in the T003
Judge receipt and continue.

Do not stop because a platform-specific assertion can't run on its target OS
in this environment (macOS only — see the `uname -s` check above). Implement
it per spec, name the gap in the packet's receipt, and continue — this is
exactly the "mark blocked, continue other safe work" case, applied per-test
rather than per-packet, since the surrounding packet itself is not blocked.

## Slice Sizing

One Worker task per packet is wrong — checked empirically (2026-09-17) by
counting distinct named tests and lettered GREEN subsections per packet in
the source plan:

| Packet | Tests | Subsections |
|---|---:|---:|
| P69-01 | 60 | 16 (a-p) |
| P69-02 | 97 | 16 (a-p) |
| P69-03 | 88 | 22 (a-v) |
| P69-04 | 8 | 0 |
| P69-05 | 22 | 0 |
| P69-06 | 49 | 9 (a-i) |
| P69-07 | 48 | 16 (9 contract-rule a-i + 7 GREEN-impl a-g) |
| P69-08 | 2 | 0 |

A single Worker task covering 60-97 tests and 16-22 lettered subsections is
not "the largest safe useful slice" — it is a multi-day mega-task, and a
failure partway through gives no useful checkpoint since nothing forces an
interim verify. P69-01, P69-02, P69-03, P69-06, and P69-07 are each split
into multiple Worker tasks along the plan's own lettered subsection
groupings — these boundaries are read directly off the source document's own
`**a.**`/`**b.**`/... headers (line-numbered and counted above), not
invented. P69-04, P69-05, and P69-08 are genuinely small (0-22 tests, no
lettered subsections) and stay as single tasks. See `state.yaml` for the
exact per-packet split.

## Board Health

Baseline pytest run, executed this session before board creation:

```bash
env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest \
  tests/test_dashboard_http_contract.py tests/test_dashboard.py \
  tests/test_subprocess_contract.py tests/test_dashboard_map.py \
  tests/test_dashboard_projects.py tests/test_dashboard_motion_contract.py \
  tests/test_tui.py tests/test_tui_terminal.py tests/test_memory_versions.py \
  tests/test_phase61_memory_tool.py tests/test_dashboard_memory_tokens.py \
  tests/test_dashboard_git_artifacts.py tests/test_dashboard_user_journey.py \
  tests/test_project_run_lifecycle.py -q
# => 116 passed, 5 warnings (pre-existing pty forkpty DeprecationWarning, unrelated)
```

Full-repo `pytest --collect-only -q` was also run and returned clean: 2288
tests collected, zero collection errors.

If the board looks stale, misleading, offline, or inconsistent, run the
bundled checker:

```bash
node <skill-path>/scripts/check-goal-state.mjs docs/goals/phase-69-dashboard-tui-contract-remediation
```

## Canonical Board

Machine truth lives at:

`docs/goals/phase-69-dashboard-tui-contract-remediation/state.yaml`

If this charter and `state.yaml` disagree, `state.yaml` wins for task status,
active task, receipts, verification freshness, and completion truth.

## Run Command

```text
Codex: /goal Follow docs/goals/phase-69-dashboard-tui-contract-remediation/goal.md.
Claude Code: /goalbuddy Follow docs/goals/phase-69-dashboard-tui-contract-remediation/goal.md.
```

## PM Loop

On every `/goal` continuation:

1. Read this charter, and follow the GoalBuddy execution contract
   (`references/goal-execution.md` in the goal-prep skill) when available.
2. Read `state.yaml`.
3. Run the bundled GoalBuddy update checker when available and mention a newer
   version without blocking.
4. Re-check the intake: original request, input shape, authority, proof, blind
   spots, existing plan facts, and likely misfire.
5. Work only on the active board task.
6. Assign Scout, Judge, Worker, or PM according to the task.
7. Write a compact task receipt.
8. Update the board.
9. If safe local work remains, choose the next largest reversible Worker package
   and continue unless blocked.
10. If a problem, suggestion, or follow-up should become a repo artifact, create
    an approved issue/PR or ask the operator whether to create one.
11. Review at phase, risk, rejected-verification, ambiguity, or
    final-completion boundaries; do not review every small Worker by habit.
12. Before ending the host turn, run
    `node <skill-path>/scripts/check-can-stop.mjs docs/goals/phase-69-dashboard-tui-contract-remediation`.
    A nonzero result means safe work remains and the PM must continue. Finish
    only when this gate passes and a Judge/PM audit receipt maps receipts and
    verification back to the original user outcome with
    `full_outcome_complete: true`, or when the checker validates the exact
    terminal approval-wait shape.

Issue and PR handoffs are supporting artifacts. `state.yaml` remains
authoritative, and every external artifact decision must be recorded in a task
receipt.
