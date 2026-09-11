# MC00.md evidence file was never created

Status: needs-triage

## Observed evidence

`docs/phase-plans/phase-63-memory-capabilities-vibecoder-plan.md` line 271 (MC00.5) requires: "Record baseline command/corpus hash/results in MC00.md." MC00 is committed at HEAD (`386a272`, "feat: benchmark actual memory payloads through isolated public scenarios"). No `MC00.md` exists anywhere in the repo (`find` returns nothing under `docs/phase-plans/` or elsewhere).

MC01's own required evidence file, `docs/phase-plans/MC01.md`, was created by T001 of the `phases-64-63-65-66` goal board and follows the same bare-filename convention the plan uses -- confirming the plan intends these files to exist per-workstream, colocated with the other phase-plan docs.

## Intervention assessment

MC00's evidence requirement was skipped by whichever agent implemented it, prior to this goal board's existence. Recreating it retroactively requires re-deriving MC00's actual baseline command, corpus hash, and results from the committed MC00 diff and its tests (`tests/test_benchmark_memory.py`, `tests/test_benchmark_runner.py`) -- this is real, non-trivial work, not a one-line fix.

## Scope

Outside MC01's (T001-T003) allowed_files and outside every other currently-defined task's allowed_files on the `phases-64-63-65-66` board. Needs its own bounded Worker task (read-only source inspection + write `docs/phase-plans/MC00.md`) before Phase 63's final MC15 acceptance audit (T126/T127), since MC15.4 reviews R01-R20 evidence across the whole phase and would otherwise find this gap itself. Flagging now so it isn't rediscovered cold at the end.
