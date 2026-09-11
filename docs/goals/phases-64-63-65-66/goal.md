# Repair and Complete Phases 63-66

## Objective

Repair the breakage left on `codex/phases64-63-65-66-implementation` by the prior (Astra/Codex) session, then carry Phases 63-66 to full completion against their approved plans, with zero descoping.

## Original Request

"The new model from Codex, Astra, is a piece of shit and fucked up this project and app... Start on stage 1 using TDD, testing, error logs, and updating backlog/issues docs for any problems. Complete stage 1 fully and comprehensively before starting on the remaining work. Use subagents to complete this work faster. Review and address all issues in subagent work before integration. Scope your work tight to prevent drift and working off plan. Do not descope or degrade anything you are asked to do in the plans, implement them fully and completely. Do not stop until all phases are complete. Do not work on main."

## Intake Summary

- Input shape: `existing_plan` (four numbered phase plans + a coding-agent handoff doc, all already read and independently verified against live repo state this session)
- Audience: James (repo owner)
- Authority: `approved` — explicit "Start on stage 1" after a full review-and-wait checkpoint
- Proof type: `test` (pytest/ruff/mypy/sync_docs) + `review` (Judge audits at phase/risk boundaries)
- Completion proof: Stage 1 — full pytest suite + `ruff check`/`ruff format --check` + `mypy src/rush` + `python scripts/sync_docs.py --check` all green with zero exclusions/skips beyond a genuinely unavailable external engine, each named exactly. Stage 2 — MC02-MC14, Phase 65 (P65-01..10), Phase 66 (P66-01..07) each implemented and verified against their own plan's acceptance criteria.
- Goal oracle: the four commands above (pytest/ruff/format/mypy/sync_docs), plus each phase plan's own named acceptance tests and evidence-file requirements. A Judge audit maps every "done" task back to these before the goal (or a stage) is marked complete.
- Likely misfire: declaring Stage 1 "done" on a partial or self-authored-test-only basis (the exact failure mode the outgoing agent already committed once — Phase 64 evidence shows only P64-00/P64-01 finished while later work was implied complete). Guard: every Worker receipt must cite the actual command run and its output, not "should pass."
- Blind spots considered: MC01 touches four shared modules with real transaction/concurrency semantics — no parallel writers allowed on `store.py`/`migration.py`/`expiry.py`/`maintenance.py` (`max_write_workers: 1` enforced). Phase 64's true remaining scope is undercounted by its own evidence doc (only 2 of many packets have evidence recorded) — Stage 1 must Scout the real gap, not trust the evidence doc's silence as "done."
- Existing plan facts: see `## Existing Plan Facts` below.

## Existing Plan Facts

Verified live against the repo this session (not taken from the handoff doc alone):

- Branch `codex/phases64-63-65-66-implementation`, HEAD `386a272`. Never touch `main`.
- `tests/test_memory_versions.py` (untracked) fails collection: `ImportError: cannot import name 'VersionConflictError' from 'rush.memory.store'`. Confirmed via direct pytest run.
- Confirmed via `grep` on `src/rush/memory/{store,migration,expiry,maintenance}.py`: none of `VersionConflictError`, `open_readonly`, `_write_version`, `artifact_version`, `memory_artifact_versions`, `memory_changes`, `upgrade`, `_backfill_legacy_row` exist. `write`/`update_content`/`promote`/`delete` exist but with no `expected_version` parameter. MC01 is 0% implemented.
- MC01 authoritative spec: `docs/phase-plans/phase-63-memory-capabilities-vibecoder-plan.md` lines 207 (owned files), 273-283 (MC01.1-MC01.5 task list), plus the shared requirements in that plan's earlier sections. 5 named required tests already exist in `tests/test_memory_versions.py`: `test_legacy_migration_preserves_ids_origins_and_trust`, `test_read_only_open_creates_no_files`, `test_content_promotion_expiry_and_delete_advance_sequence`, `test_migration_failure_rolls_back`, `test_concurrent_expected_version_rejects_lost_update`. Required compatibility check: `tests/test_memory_compatibility_regressions.py`.
- `ruff format --check src tests scripts`: fails only on `tests/test_memory_versions.py`; 799 other files already clean. Confirmed by direct run.
- `python scripts/sync_docs.py --check`: reproduced with a longer list than the handoff's 3 examples. Confirmed drift: `rush ship clean` (missing `allow_artifact_write`/`apply`, stale `dry_run`), `rush test-heal` (missing `allow_artifact_write`/`allow_build`/`allow_slow`/`dry_run`/`seed`, `runs` default/type mismatch), `rush patch apply` / `rush_patch_apply` unregistered in recorded contracts, `rush memory {ask,list,promote,recall,write}.subject` recorded as `string` but implemented as a `choice[...]` enum, plus MCP-side mismatches on `rush_benchmark`, `rush_contract`, `rush_cold_start`, `rush_fuzz`, `rush_load`, `rush_media_opt`, `rush_mem_profile`, `rush_mutation`, `rush_prompt_eval`, `rush_ship_clean`, `rush_test_heal`, `rush_tui_diff`. Also stale-sha docs: `docs/CLI_REFERENCE.md`, `docs/KNOWN_ISSUES.md`, `docs/MCP_REFERENCE.md`, `docs/SAFETY.md`, `docs/phase-plans/phase-64-implementation-evidence.md`, `docs/safety/permissions.md`, `docs/safety/safety-overview.md`, `docs/vibecoding/the-vibecoder-workflow.md`. `docs/developer/phase-63-66-coding-agent-handoff.md` itself is missing a coverage receipt (an untracked new doc — Stage 1 must decide whether it needs one or is exempt as a handoff artifact, not a user-facing doc).
- Diagnostic pytest (`--ignore=tests/test_memory_versions.py`): 1689 passed, 7 skipped (was 1684/12 at handoff time — confirms James's dependency install already fixed 5 skips). Remaining skip reasons, confirmed via `-rs`: `prettier not installed`, `knip not installed` (2 static-tool skips), and 5 tests gated by `RUSH_REQUIRE_REAL_ENGINES != "1"` in `tests/test_executed_modes.py` (mutation, fuzz, load x2, contract) — an explicit opt-in env flag, not a missing dependency.
- `docs/phase-plans/phase-64-implementation-evidence.md` (read in full, 43 lines): only P64-00 and P64-01 have completed evidence. P64-02 is explicitly "provisional... does not mark P64-02 complete." Everything else "remains planned." Phase 64's true remaining scope must be Scouted against `docs/phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md` directly — the evidence doc under-reports what's actually implemented-but-unrecorded vs genuinely unimplemented.
- 24 doc files already staged/unstaged before this goal started (listed in the handoff) must not be bulk-touched or rewritten as part of this work — only edit the exact files a Stage 1 task requires (contract/sha drift repair), never a broad pass.
- Untracked non-doc surfaces (`.claude/`, `.codegraph/`, `.gemini/`, `.kiro/`, `.mcp.json`, `GEMINI.md`, `opencode.json`, `repos/`, `.DS_Store` files) are user-owned tooling, not Rush implementation scope. `repos/` in particular holds cloned reference repos — never scan it as if it were this codebase.
- Incidental issues (anything found but out of the current task's exact scope) go to `.scratch/phases-64-63-65-66/issues/<NN>-<slug>.md` per `docs/agents/issue-tracker.md` — that feature-slug is already in use by the prior agent (see the FastMCP warning issue referenced from the Phase 64 evidence doc); reuse it, don't create a second one.

## Goal Oracle

The oracle for this goal is:

`env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python -m pytest tests/ -q && ruff check src tests scripts && ruff format --check src tests scripts && mypy src/rush && python scripts/sync_docs.py --check`

— all five commands exit 0, with no test collection errors, no unresolved skips beyond a named, genuinely-external blocker, and no contract/sha drift — AND each of Phase 63's MC02-MC14, Phase 65's P65-01..10, and Phase 66's P66-01..07 individually verified against its own plan's named acceptance tests/evidence requirements (not just "the suite is green," since a task can be unimplemented and still not break existing tests).

The PM must keep comparing task receipts to this oracle. A clean-looking board or a passing tiny slice is not enough. Stage 1 completes only when a Judge/PM audit maps every Stage 1 receipt to the command block above and confirms zero exclusions. The full goal (`full_outcome_complete: true`) completes only when Stage 2's four plans are each independently verified the same way.

## Goal Kind

`existing_plan`

## Current Tranche

**Tranche 1 (this board's immediate scope): Stage 1 repair.** Finish MC01 via TDD (RED tests already exist, write the implementation to pass them for real), review it, Scout the true remaining Phase 64 gap and remediate it, repair the sync_docs contract drift, enable and pass real-engine acceptance (`RUSH_REQUIRE_REAL_ENGINES=1`), then run a final Stage 1 Judge audit against the full oracle command block with zero exclusions.

Stage 1 must pass before any Stage 2 task starts. No exceptions, no "start Stage 2 in parallel to save time."

**Tranche 2 (queued, expanded by the PM once Tranche 1's audit passes, not pre-drafted here):** MC02 through MC14 per `docs/phase-plans/phase-63-memory-capabilities-vibecoder-plan.md` §9, then Phase 65 (`docs/phase-plans/phase-65-project-provisioning-scan-and-agent-workflow-plan.md`), then Phase 66 (`docs/phase-plans/phase-66-interactive-tui-and-local-web-plan.md`), each read in full by a Scout/Judge pair before its Worker tasks are cut, exactly like Tranche 1 was.

Do not stop after Tranche 1. Once its audit passes, the PM adds Tranche 2 tasks to this same `state.yaml` and continues without a new user prompt.

## File Conflict Ordering

Coverage: 6 of 6 files currently assigned to more than one task on this board (T001-T005 are the only tasks that exist; T006+ are not yet created). All 6 listed below, in required order:

| File | Order |
|---|---|
| `src/rush/memory/store.py` | T001 → T003 (T002 is read-only review) |
| `src/rush/memory/migration.py` | T001 → T003 |
| `src/rush/memory/expiry.py` | T001 → T003 |
| `src/rush/memory/maintenance.py` | T001 → T003 |
| `tests/test_memory_versions.py` | T001 → T003 |
| `docs/phase-plans/MC01.md` (new file, path resolved by this goal — the plan names it as a bare filename with no precedent; `MC00.md` was never created either, so there is no existing convention to match beyond colocating with other phase-plan docs) | T001 → T003 |

Forward constraint for Tranche 1's not-yet-created tasks (T006+, defined by T005's Judge output): none of them may touch `src/rush/memory/{store,migration,expiry,maintenance}.py` until T001-T003 are fully done (stated in T005's objective). T005 must itself produce a file-conflict-ordering table for whatever T006+ slices it defines, covering the sync_docs contract-drift repair files and any Phase 64 packet files that overlap across slices.

`src/rush/memory/transactions.py` (existing `CASMapTransaction`/`VersionedSnapshot`/`CASConflictError`) is a pre-existing JSON-file compare-and-swap primitive, a different subsystem from MC01's SQLite version schema. It is not one of MC01's owned files and MC01's mutations must not be redirected through it — noted so a Worker doesn't mistake it for infrastructure to reuse or extend.

## Non-Negotiable Constraints

- Stay off `main`. Work happens on `codex/phases64-63-65-66-implementation` only.
- No reset, clean, bulk staging (`git add -A`/`.`), worktree removal, push, or release action by inference.
- `max_write_workers: 1` on `src/rush/memory/{store,migration,expiry,maintenance}.py` — MC01's shared transaction changes need one coherent implementation owner, never parallel Worker writes to these four files.
- TDD RED-then-GREEN evidence required for every implementation task. A collection failure alone, an import fix alone, or a self-authored test with no adversarial review is not acceptance evidence.
- Never replace an exact assertion with a permissive success condition to make a test pass.
- Preserve the 24 already-staged/unstaged doc files exactly as-is except where a Stage 1 task's own contract-drift repair requires touching one of them; no unrelated rewrite, no reformat pass.
- No broad documentation cleanup. Record incidental issues in `.scratch/phases-64-63-65-66/issues/` instead of expanding any task's scope.
- Never descope, weaken, or silently reduce any requirement in the four phase plans. If a requirement looks wrong or infeasible, surface it as a blocked receipt with the exact reason — do not quietly drop it.
- Follow repository `AGENTS.md` and prefix real shell commands with `rtk` per its convention.
- Use additional agents only for bounded independent work; do not spin up scouting/documentation/review loops merely to demonstrate orchestration.
- Do not use premium models for routine chores or concurrent writers for shared storage files.

## Stop Rule

Stop only when a final audit proves Stage 1 AND Stage 2 (all four plans) are complete against the oracle above.

Do not stop after MC01 alone, after a single passing focused test run, after one commit, or after producing another status document — these are the exact anti-patterns the handoff doc calls out as what the outgoing agent did wrong.

Do not stop after planning or Scout/Judge selection if a safe Worker task can be activated.

Do not create one Worker/Judge pair per repeated file, table, route, or helper. MC01's four-module transaction work is one Worker package, reviewed as a whole.

Do not stop because a slice needs owner input, credentials, or a policy decision — mark that exact slice blocked with a receipt (e.g., a genuinely unavailable real-engine dependency), create the smallest safe follow-up, and continue all other local work.

If an exact human approval phrase is the only remaining blocker and no safe local work remains, ask once and stop, per the terminal-wait shape in `references/goal-execution.md`.

## Slice Sizing

Safe means bounded, explicit, verified, and reversible. It does not mean tiny. MC01 (all four modules, all five tests, one coherent transaction mechanism) is one slice, not four. Phase 64's remaining packets should be grouped into coherent vertical slices by the Judge, not one task per packet ID, unless a packet is independently large enough to warrant it.

## Board Health

If the board looks stale, misleading, or inconsistent, run:

```bash
node /Users/jamesdsizemore/.claude/skills/goal-prep/scripts/check-goal-state.mjs docs/goals/phases-64-63-65-66
```

## Canonical Board

Machine truth lives at:

`docs/goals/phases-64-63-65-66/state.yaml`

If this charter and `state.yaml` disagree, `state.yaml` wins for task status, active task, receipts, verification freshness, and completion truth.

## Run Command

```text
Claude Code: /goalbuddy Follow docs/goals/phases-64-63-65-66/goal.md.
```

## PM Loop

On every `/goalbuddy` continuation:

1. Read this charter, and follow the GoalBuddy execution contract (`references/goal-execution.md` in the goal-prep skill).
2. Read `state.yaml`.
3. Re-check the intake: original request, input shape, authority, proof, blind spots, existing plan facts, and likely misfire.
4. Work only on the active board task.
5. Assign Scout, Judge, Worker, or PM according to the task. Attempt the real dispatched agent every time before falling back to PM-direct; a stall on one task is not license to self-execute the rest.
6. Write a compact task receipt citing the exact command run and its output — never "should pass."
7. Update the board.
8. If safe local work remains, choose the next largest reversible Worker package and continue unless blocked.
9. Route incidental findings to `.scratch/phases-64-63-65-66/issues/` rather than expanding task scope.
10. Review at phase, risk, rejected-verification, ambiguity, or final-completion boundaries.
11. Before ending the host turn, run `node /Users/jamesdsizemore/.claude/skills/goal-prep/scripts/check-can-stop.mjs docs/goals/phases-64-63-65-66`. A nonzero result means safe work remains and the PM must continue. Finish only when this gate passes and a Judge/PM audit receipt maps receipts and verification back to the goal oracle with `full_outcome_complete: true`, or when the checker validates the exact terminal approval-wait shape.
