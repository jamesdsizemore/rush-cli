# CI dependency installation — stop skipping tests for missing tools

## Objective

Implement the validated plan in `docs/phase-plans/ci-dependency-installation-plan.md`:
add every missing external dependency (`vulture`, `radon`, `sloppylint`, `knip`, `jscpd`,
`prettier`, `promptfoo`, a native PyInstaller archive) to CI so the 9 originally-named
SKIPPED tests actually exercise real tools, without breaking any currently-green CI job.

**SCOPE CORRECTION (2026-09-13, after T999's first audit):** the user's actual, standing
requirement — stated from the start of this app's development, not just this goal — is
**zero SKIPPED tests anywhere in CI, full stop.** The original 9-item scope above was this
PM's own incorrect narrowing of that requirement to only the plan's named items; it was
never approved as "the other skips are fine." The 5 pre-existing `test_executed_modes.py`
real_workload skips (mutation/fuzz/load×2/contract) in the `Quality and tests` job are
NOT acceptable to leave, even though they already run for real in the separate `Executed
workload contracts` job — the `Quality and tests` job's own pytest output must show zero
SKIPPED lines too. This corrected objective supersedes the 9-item framing everywhere else
in this file.

## Original Request

`/goal-prep ci-dependency-installation-plan.md` — prepare a board to execute the
already-written plan at `docs/phase-plans/ci-dependency-installation-plan.md`.

## Intake Summary

- Input shape: `existing_plan`
- Audience: James (repo owner) / future CI reliability
- Authority: `requested`
- Proof type: `test`
- Completion proof: a CI run (on a dedicated branch, not main) shows the new
  `static-tool-acceptance` job green, the `Quality and tests` job green, **zero**
  SKIPPED lines among the 9 tests named in the plan's Problem section, and every
  previously-green job (`engine-contracts`, `windows-contracts`, `artifact-probes`,
  `representative-engines`) still green.
- Goal oracle: `gh run view <run-id> --json jobs` plus the `Run tests` step's own
  `-rs` skip summary — job conclusions alone are not sufficient; the actual skip
  lines must be checked line-by-line against the 9 named in the plan.
- Likely misfire: PM declares success from "job passed" without confirming the
  specific 9 skip lines are gone (a job can go green while still silently skipping),
  or ships `knip`/`jscpd` pinned to `latest` instead of the tested major (already
  flagged in the plan as a real breakage risk to `KnipEngine`/`JscpdEngine` normalizers).
- Blind spots considered: `rush.__version__` accessor was never confirmed in the
  plan — first Judge task must verify it before any Worker touches
  `build_release_archive`. npm has no cache configured on the new job (acceptable,
  not a correctness risk). PyInstaller build adds real wall-clock time to `Quality
  and tests` — Judge should watch for job timeout, not assume it's fine.
- Existing plan facts: preserve `docs/phase-plans/ci-dependency-installation-plan.md`
  verbatim — exact pinned versions (`vulture==2.16`, `radon==6.0.1`,
  `sloppylint==0.5.1`, `knip@5.88.1`, `jscpd@3.5.10`, `prettier@3.9.6`,
  `promptfoo@0.123.0`), the exact new `static-tool-acceptance` job YAML, and the
  exact native-archive build step (reusing `release.yml`'s existing `pyinstaller
  --onefile --name rush --paths src --collect-data license_expression
  rush_entry.py` invocation) added to `Quality and tests` before `Run tests`.

## Goal Oracle

`gh run view <run-id> --json jobs -q '.jobs[] | {name, conclusion}'` for every job, AND
the `Run tests` step log (and `static-tool-acceptance` job's log) grepped for SKIPPED
lines — **zero SKIPPED lines anywhere in the CI run, not just the original 9 named
items**, not just "job passed". The 5 `test_executed_modes.py` real_workload tests must
stop showing SKIPPED in `Quality and tests` (they may continue to actually execute in
the separate `Executed workload contracts` job — that job already runs them for real via
`RUSH_REQUIRE_REAL_ENGINES=1`; the fix is to stop `Quality and tests`' own `pytest`
invocation from hitting their skip guard at all, e.g. by deselecting them there via
marker/keyword instead of letting them fall through to `pytest.skip(...)`).

## Goal Kind

`existing_plan`

## Current Tranche

Validate the existing plan against current repo state (confirm the open
`rush.__version__` item, confirm `.github/workflows/ci.yml` hasn't drifted from what
the plan assumes, confirm pinned versions still resolve), implement it on a dedicated
branch, push, verify the CI run against the oracle above, then stop for the user's
explicit merge decision. Do not merge to main automatically.

## Non-Negotiable Constraints

- All work on a dedicated branch `phase/ci-dependency-installation` — never commit
  this goal's changes directly to `main`.
- Merging that branch into `main` is a separate step gated on explicit user approval;
  the goal's own completion (`full_outcome_complete: true`) is about the CI run
  passing on the branch, not about being merged.
- Do not touch the `engine-contracts`, `windows-contracts`, `artifact-probes`, or
  `representative-engines` jobs' own bodies in `ci.yml`. **Corrected 2026-09-13:** the
  `Quality and tests` job's `Run tests` step (its pytest invocation only, not the rest of
  that job) MAY be touched to deselect the 5 `test_executed_modes.py` real_workload tests
  so they stop emitting SKIPPED there, since they already run for real in `Executed
  workload contracts`. Do not add real-engine installs (mutmut/atheris/pact-python-cli/k6)
  to `Quality and tests` — that would duplicate `Executed workload contracts`'s job for no
  benefit; deselect via marker/keyword instead.
- Do not touch the untracked `docs/goals/mc00-benchmark-review-remediation/`
  directory — unrelated, separate goal.
- Preserve the plan's exact pinned versions; do not substitute `latest` for `knip` or
  `jscpd` (verified breakage risk to existing normalizers).

## Stop Rule

Stop only when a final Judge audit confirms the CI run on the dedicated branch matches
the corrected oracle exactly (**zero SKIPPED lines anywhere in the run, in every job's
log**, no previously-green job regressed), and records `full_outcome_complete: true`.
If the only remaining step is the merge decision, mark the goal blocked on that exact
approval and stop — do not merge without it.

## Slice Sizing

One Worker task implements the whole validated plan (new job + build step) as a
single coherent slice — this is not fragmentable busywork; splitting it into
per-package tasks would violate the "largest safe useful slice" rule for no benefit.

## Board Health

```bash
node ~/.claude/skills/goal-prep/scripts/check-goal-state.mjs docs/goals/ci-dependency-installation
```

## Canonical Board

`docs/goals/ci-dependency-installation/state.yaml`

## Run Command

```text
Claude Code: /goalbuddy Follow docs/goals/ci-dependency-installation/goal.md.
```

## PM Loop

Standard GoalBuddy PM loop per `references/goal-execution.md`. Work only the active
task, one at a time, until the final Judge audit passes or the goal blocks on the
explicit merge-approval decision.
