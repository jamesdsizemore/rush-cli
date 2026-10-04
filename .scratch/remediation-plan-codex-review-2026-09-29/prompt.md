# Adversarial review: orchestrator and Phase 70 remediation plan

Review this plan document adversarially. Read-only: do not edit any file, do not run anything that writes outside a temp directory you create and delete. Do not implement anything.

Document under review:
`/Users/jamesdsizemore/Developer/rush-cli/docs/reports/orchestrator-and-phase-70-remediation-plan-2026-09-29.md`

It is a plan. It proposes edits to a Claude Code skill (`~/.claude/skills/orchestrator/`), its seven agent definitions (`~/.claude/agents/orch-*.md`, plus repo-level copies in `/Users/jamesdsizemore/Developer/rush-cli/.claude/agents/`), the repo's test infrastructure, and a set of proposed hooks. Nothing in it has been applied. Section 0 quotes the user's original demand verbatim; sections 4.H, 4.I and 4.J are the behavior fixes; sections 4.A to 4.G and 4.T are the skill and cost fixes; section 5 lists decisions; section 8 holds exact edits.

## What was already checked, so you do not repeat it

The author already recomputed the document's file:line citations, counts, percentages and signatures from the transcripts and the repo. Do not spend your budget re-counting. Re-check a number only if a proposed fix depends on it and you have a specific reason to doubt it.

## What to review (judgment-level, against the real current source)

1. **Architecture fit.** For each proposed edit, does the anchor text exist exactly once in the real file, does the replacement match how the file actually works, and does it do what the plan says? Check `~/.claude/skills/orchestrator/SKILL.md`, `references/dispatch.md`, `scripts/*` (`dispatch-prompt.sh`, `run-state.sh`, `monitor.py`, `gate.sh`, `decisions.sh`, `test-acceptance.py`), the agent definitions, `~/.claude/hooks/orchestrator-model-guard.js`, `~/.claude/settings.json`, and in the phase-70 worktree `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70` the files `tests/conftest.py`, `tests/test_real_home_guard.py`, `pyproject.toml`.
2. **Breakage risk.** What existing caller, test, hook, script or persisted format breaks if an edit is applied? Examples to check: removing `--budget` from `dispatch-prompt.sh` (who else passes it or parses it: `SKILL.md`, `dispatch.md`, `monitor.py`, `run-state.sh`, `orchestrator-model-guard.js` rule 7 and its sha256 marker); the `monitor.py` changes (`DONE`, `_RAW_READ`, the removed edit detection) against every caller of `monitor.py`; the conftest changes against `tests/test_real_home_guard.py` and any other test that pins them; `pytest-xdist` with `--dist loadfile` against fixtures with session scope or shared temp state; each proposed hook against the existing hooks in `~/.claude/settings.json` (double firing, lockout, an unlock word that does not work in the case it is meant for).
3. **Sequencing.** The edits in sections 4 and 8 touch the same files (`SKILL.md`, `dispatch-prompt.sh`, `monitor.py`, `run-state.sh`, `tests/conftest.py`, the agent definitions). Do they apply in a consistent order? List each pair of edits whose anchors overlap or whose replacements contradict, and say which must go first.
4. **Scope soundness.** Compare against section 0 (the user's demand). Is any demanded item without a fix? Is any fix a prose rule with no mechanism? Does any entry contradict another entry or a source file? Does any proposed fix narrow, defer or drop something the user demanded? Any item marked deferred or out of scope must point to a real artifact.
5. **Test depth.** Entries marked "Tested" or "Tested on a copy": re-run the small fixtures if the scripts exist under `/private/tmp/claude-501/-Users-jamesdsizemore-Developer-rush-cli/f0b0971c-824c-42ba-8db0-e34d0fa85631/scratchpad/x/` (`task-gate.sh`, `doc-done-check.sh`, `monitor-copy.py`, `test-acceptance-copy.py`, `stall-notify.sh` is not part of the plan). Does each test exercise the behavior it is cited for, or would it pass if the fix were wrong?
6. **Behavior fixes (H, I, J).** For each entry: does the artifact named as the fix exist or is it specified precisely enough to build, is its trigger free of obvious false positives, and would it change the behavior it targets? Flag any fix that is a prose reminder to the assistant with no check.

## Transcripts, if you need evidence

The orchestrator session is `/Users/jamesdsizemore/.claude/projects/-Users-jamesdsizemore-Developer-rush-cli/90c5b55d-9e85-4452-9d9f-0ec5c270c759.jsonl`; its subagent transcripts are in the `subagents/` directory beside it. Do not read the Codex sessions. Do not print whole files or large outputs; extract only what you need.

## Output format

At most 40 findings, most severe first, each in this shape:

```
## Finding <n> [critical|major|minor]
Section: <doc section id, e.g. 4.B7 or 8.X4>
Defect: <one sentence>
Failure scenario: <concrete input or state -> wrong result>
Evidence: <file:line, or the command you ran and its decisive output>
Suggested change: <exact change to the plan>
```

End with a line `Sections reviewed: <list with denominators, for example "read 81 of 81 entries in section 4">` and a line `Not reviewed: <anything you did not open, with the reason>`. Do not state a finding you have not backed with evidence you read or ran.
