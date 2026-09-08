# Cross-LLM Memory System: Phase 61 + Phase 62

## Objective

Implement Phase 61 (typed-artifact memory schema, trust tiers, transport dispatcher) and Phase 62 (memory integration layer: cache front-end, review/dev hooks, maintenance sub-agent, handoff diffs, attribution trail, API-diff staleness, per-type expiry, decision-record schema reuse) of rush-cli's cross-LLM memory redesign, exactly as specified in the two accepted, implementation-ready plans. Phase 62 is hard-blocked on Phase 61's exit checklist being 100% satisfied (Phase 62 plan §4).

## Original Request

> /Users/jamesdsizemore/Developer/rush-cli/docs/phase-plans/phase-61-cross-llm-memory-typed-artifact-schema-plan.md and /Users/jamesdsizemore/Developer/rush-cli/docs/phase-plans/phase-62-memory-integration-layer-plan.md — Ensure that you create a new worktree to do this work. Ensure that the agents are installed for goalbuddy. Ensure that you enable and activate the local goal board in the browser. Review your goalprep plan decomposition prior to handoff - address all issues.

## Intake Summary

- Input shape: `existing_plan`
- Audience: rush-cli maintainer (repo owner); future cross-LLM tool integrations that will read/write rush's memory subsystem
- Authority: `approved` — both plan documents self-declare "Implementation-ready" / "Authorized for strict TDD execution once accepted," and are already committed to `main` (commits `cda58a6`, `d933c15`, `9783f29`) as accepted planning artifacts, not drafts
- Proof type: `test`
- Completion proof: `python -m pytest tests/ -q` passes at (pre-goal baseline) + 65 (39 Phase 61 + 26 Phase 62) named contract tests; every checkbox in both plans' §11 Exit Checklists is checked; both plans' §10 delivery-gate commands all pass
- Goal oracle: see below
- Likely misfire: executing tasks out of the plans' own Prerequisites order (e.g. building `MemoryTool` before trust tiers exist); silently downscoping a task's Binary Outcome; starting any Phase 62 task before Phase 61's exit checklist is 100% checked (Phase 62's own §4 admission gate hard-blocks this); a Worker re-deriving a design decision from memory instead of opening the cited plan section, and drifting from a corrected signature/invariant the plan already fixed (e.g. reusing `MultiModelConsensusReconciler` for corroboration counting, which the plan explicitly corrects against; reusing `GroundingVerifier` for symbol grounding, same correction).
- Blind spots considered:
  - P62.7's TTL durations were an open decision at Phase 62's first draft — already resolved (14/30/90 days for DERIVED/EXTERNAL_WRITE/IMPORTED, grounded in `src/rush/hotspots/time_decay.py:12`'s 90-day precedent) and recorded in the plan itself before this board was built. No Worker task needs to invent this number.
  - Both phases mandate zero new third-party dependencies — Python 3.12 standard library only (`sqlite3`, `hashlib`, `json`, `re`, `dataclasses`, `pathlib`, `time`, `uuid`, `typing`).
  - Both plans carry an explicit **Lifecycle Boundary: no commit, push, merge, tag, publish, or release without explicit user instruction** (Phase 61 plan §1, Phase 62 plan §1) — this is the plans' own authored constraint, more specific than GoalBuddy's general branch-per-tranche default. Worker tasks in this board edit files only; they do not commit. The dedicated worktree/branch (below) already gives this tranche git isolation without needing per-task commits.
  - Phase 61's §3.2 explicitly triages the synthesis doc's 35 enhancement-idea bullets: 9 already inside Phase 61's own task cards, 2 folded into P61.2 as integrity gaps, 8 are this board's Phase 62 scope, 16 remain a genuinely unranked backlog (Phase 61 plan §3.2.4) — not part of this goal, not silently claimed as covered.
  - Both plans were adversarially reviewed this session (Codex, multiple passes): 33 findings from the first review round were independently verified against live source and applied, then a follow-up critical-review round found 7 blockers, all 7 fixed and verified — see `docs/phase-plans/phase-61-cross-llm-memory-typed-artifact-schema-plan.md` and the `phase-62-*` equivalent for the full corrected text (corrections are inline in the plan prose, not a separate errata file).
- Existing plan facts: preserved in full — the two plan documents themselves remain the canonical spec for every task below. This board does not re-author their content; each task card here cites the exact plan file + task-card ID(s) it implements. Task-ID correspondence:
  - Phase 61 (`docs/phase-plans/phase-61-cross-llm-memory-typed-artifact-schema-plan.md` §9): P61.0.1, P61.1.{1,2}, P61.2.{1,2}, P61.3.{1,2}, P61.4.{1,2}, P61.5.{1,2}, P61.6.{1,2}, P61.7.{1,2}, P61.8.{1,2}, P61.9.{1,2}, P61.10.{1,2}, P61.11.{1,2}, P61.12.{1,2}, P61.13.1 — plus §10 Final Verification/§11 Exit Checklist.
  - Phase 62 (`docs/phase-plans/phase-62-memory-integration-layer-plan.md` §9): P62.0.1, P62.1.{1,2}, P62.2.{1,2}, P62.3.{1,2}, P62.4.{1,2}, P62.5.{1,2}, P62.6.{1,2}, P62.7.{1,2}, P62.8.{1,2}, P62.9.{1,2} — plus §10 Final Verification/§11 Exit Checklist.

## Goal Oracle

The oracle for this goal is:

`python -m pytest tests/ -q` reports (pre-goal baseline count) + 65 passing, with all 39 Phase 61 contract tests (T-61.01–T-61.39) and all 26 Phase 62 contract tests (T-62.01–T-62.26) passing by name, both plans' §10 delivery-gate command blocks all succeed, and every box in both plans' §11 Exit Checklists is checked — verified by a Judge/PM audit (T016 for Phase 61, T028 for Phase 62), never assumed from a clean-looking diff or a partial test run.

## Goal Kind

`existing_plan`

## Current Tranche

Both phases, in order: Phase 61's 14 workstreams (P61.0–P61.13) first, then Phase 62's 8 integration workstreams (P62.1–P62.8) plus its own admission/baseline and doc-sync tasks — Phase 62 does not start until Phase 61's exit checklist is 100% checked (Phase 62 plan §4). This is a continuous-execution tranche: discover nothing new (both plans are already fully task-carded), execute each workstream's RED-then-GREEN pair as one coherent Worker package, verify per the plan's own named test commands, review only at the two phase-boundary/final-audit checkpoints (T016, T028), and advance immediately to the next workstream otherwise.

## Non-Negotiable Constraints

- Every task's Binary Outcome (as stated in the cited plan section) must be met exactly — no downscoping a RED/GREEN pair, no special-casing a test instead of implementing the real invariant (both plans' own Zero-Downscope Invariant, §1).
- Zero new third-party dependencies in either phase — Python 3.12 standard library only.
- No commit, push, merge, tag, publish, or release without explicit user instruction (both plans' §1 Lifecycle Boundary). Worker tasks edit files only.
- `governance/remediation-contracts.toml`'s existing 16/16 `completed` rows are never touched by this goal.
- Existing ADRs are never edited in place — superseding ADR-0030 means writing new ADR-0049 and adding pointer notes to 0030/0018/0020/0041, never rewriting their substance (Phase 61 plan §3.2 item 6, §8.1 item 9).
- `.rush/cache.db` is never renamed, moved, or deleted during Phase 61's migration (P61.3.2) — only its `patch_memory` table's data moves; `ResultCache` shares that physical file for an unrelated cache table.
- Satellite files migrated off of in Phase 61 (flights JSONL, hook signatures, preference/invariant/checkpoint JSON, `session_memory.json`) are renamed with a `.migrated` suffix, never deleted (Phase 61 §6.3 Invariant 5).
- Phase 62's cache-gate write-back and transport-dispatcher tier-3 writes stay behind their named `ExecutionPermissions` flags (`cache_write`, `artifact_write`) — never unconditional.
- All work happens in this goal's dedicated worktree/branch (below) — never directly on `main`.

## Stop Rule

Stop only when T028's final Judge/PM audit proves both phases' full outcome is complete (`full_outcome_complete: true`) — both plans' §11 Exit Checklists 100% checked, full pytest suite at baseline+65, both §10 delivery-gate blocks green.

Do not stop after Phase 61 completes without immediately continuing into Phase 62 (T017) unless T016's audit finds a real blocker.

Do not stop after a single workstream's Worker task passes its own tests if the broader phase still has queued workstreams — advance to the next workstream in board order.

## Slice Sizing

Each Worker task below merges one phase-plan workstream's RED task-card and GREEN task-card into one coherent TDD package (author the failing tests per the plan's Contract Test Inventory, confirm the stated failure reason, then implement to green) — this is the largest safe useful slice each workstream represents, per the plans' own atomic task-card boundaries. No task below splits a RED and its paired GREEN into two separate Worker dispatches; no task below bundles more than one workstream into a single dispatch.

## File Conflict Ordering

Restated explicitly per the plan-review skill's Pass 2 (both source plans do the same in their own §8.4/§8.2b, even though the board's strict one-active-task-at-a-time execution already makes concurrent conflicts impossible). Files touched by more than one board task, in required order:

| File | Tasks (in required order) |
|---|---|
| `src/rush/memory/store.py` | T003 (create) → T004 (wire `evaluate_conflict()`) → T009 (add `search()`) → T011 (add recall allowlist) → T023 (add API-diff staleness check) → T024 (add expiry columns/field) |
| `docs/phase-plans/phase-61-implementation-evidence.md` | T002 (create) → T005 (migration evidence note) → T008 (pairing-check result) → T015 (finalize) |
| `docs/phase-plans/phase-62-implementation-evidence.md` | T017 (create) → T024 (TTL resolution note) → T026 (frozen doc-sweep list) |
| `src/rush/tools/flight_recorder.py` | T005 (migration compatibility view) → T007 (episodic forward-write wiring) |
| `src/rush/memory/checkpoint_journal.py` | T005 (migration compatibility view) → T006 (handoff-family row write) |
| `src/rush/memory/migration.py` | T005 (create, 8 migration fns) → T007 (add `migrate_session_memory`) |
| `src/rush/memory/mistake_miner.py` | T008 (pure shaping fn) → T025 (extend with `DecisionRecordFields`) |
| `src/rush/tools/memory.py` | T014 (create `MemoryTool`) → T020 (wire `maintain` dispatch) |
| `src/rush/tools/continuity.py` | T005 (`_run_restore` fix) → T021 (`provider_id` merge in `run()`) |
| `src/rush/session_memory.py` | T007 (episodic forward-write) → T022 (attribution wiring) |
| `src/rush/continuity/receipts.py` | T006 (`trust_tier` field) → T021 (`target_provider` persistence) |
| `docs/phase-plans/README.md` | T015 (Phase 61 row) → T027 (Phase 62 row) |
| `docs/developer/backlog.md` | T015 (Phase 61 row) → T027 (Phase 62 row) |
| `docs/adr/0030-unified-dual-layer-agent-context-memory-subsystem.md` | T013 only |

Every ordering above already matches the board's linear task sequence (`rules.max_write_workers: 1`, `one_active_task: true` in `state.yaml` forbid two tasks ever writing concurrently) — this table documents that the sequence was chosen correctly, not a separate constraint the PM must additionally enforce.

## Board Health

If the board looks stale, misleading, offline, or inconsistent, run:

```bash
node <skill-path>/scripts/check-goal-state.mjs docs/goals/cross-llm-memory-61-62
```

Repair only GoalBuddy control files unless an active Worker or PM task explicitly allows product-file edits.

## Canonical Board

Machine truth lives at:

`docs/goals/cross-llm-memory-61-62/state.yaml`

If this charter and `state.yaml` disagree, `state.yaml` wins for task status, active task, receipts, verification freshness, and completion truth.

## Workspace

This goal executes in a dedicated git worktree, not the main `rush-cli` checkout:

- Worktree: `/Users/jamesdsizemore/Developer/rush-cli-worktrees/feat-phase-61-62-cross-llm-memory`
- Branch: `feat/phase-61-62-cross-llm-memory` (branched from local `main` at `9783f29`, which already carries both plan documents — `origin/main` does not yet have them, so this branch is intentionally not based on `origin/main`)
- Merging into `main` is a separate, explicitly-approved step after both phases' audits pass — not automatic on goal completion.

## Run Command

```text
Codex: /goal Follow docs/goals/cross-llm-memory-61-62/goal.md.
Claude Code: /goalbuddy Follow docs/goals/cross-llm-memory-61-62/goal.md.
```

Run this from inside the worktree above (or have the harness enter it first) — the plan files and every task's `allowed_files` are worktree-relative.

## PM Loop

On every `/goalbuddy` continuation:

1. Read this charter, and follow the GoalBuddy execution contract (`references/goal-execution.md` in the goal-prep skill) when available.
2. Read `state.yaml`.
3. Run the bundled GoalBuddy update checker when available and mention a newer version without blocking.
4. Re-check the intake: original request, input shape, authority, proof, blind spots, existing plan facts, and likely misfire.
5. Work only on the active board task.
6. Assign Scout, Judge, Worker, or PM according to the task.
7. Write a compact task receipt.
8. Update the board.
9. If safe local work remains, choose the next largest reversible Worker package and continue unless blocked.
10. Review at phase, risk, rejected-verification, ambiguity, or final-completion boundaries — T016 (Phase 61 exit) and T028 (Phase 62 exit / full outcome) are the two mandatory review points; do not add ad hoc reviews between every workstream.
11. Before ending the host turn, run `node <skill-path>/scripts/check-can-stop.mjs docs/goals/cross-llm-memory-61-62`. A nonzero result means safe work remains and the PM must continue. Finish only when this gate passes and T028's audit records `full_outcome_complete: true`.
