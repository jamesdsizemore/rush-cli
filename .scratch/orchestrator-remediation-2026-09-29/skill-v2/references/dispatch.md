# Dispatch prompts

Each prompt is the full packet the subagent gets. Subagents do not see this conversation, so
every prompt carries the repo root, the exact task, the checkable done items, and the receipt
shape. Fill every `<...>` with real values; never send a placeholder.

Every `orch-*` prompt is built by `scripts/dispatch-prompt.sh`, never hand-written (SKILL.md,
"Before any dispatch"). Per dispatch:
1. The map file `$WT/.orchestrator/maps/<task>-<role>.md`. For a read-only role (scout, design
   gate) it is the input you assemble; for an implementer it is the design gate's report, saved
   with `scripts/save-map.sh <agent-id> <task> implementer [<scout-id>]`. Lines the generator reads:
   `write:`, `change:` (at most 3), `test:`, `done:`, `keep:`, `sym:`, `scout:`, `model:`,
   `model-reason:`, then the `path:line` code map and the role inputs from that role's section below.
2. Build the prompt to a file and send its path, never its text:
   ```bash
   bash <this-skill-dir>/scripts/dispatch-prompt.sh --role <role> --task <id> --worktree $WT \
     --map $WT/.orchestrator/maps/<task>-<role>.md [--mode tests] [--spec <file>:<a>-<b> ...] \
     --test-cmd "env PYTHONPATH=$WT/src $PY -m pytest -q" [--red-log <file>] \
     > $WT/.orchestrator/prompts/<task>-<role>.md
   ```
   Agent prompt: `Your packet is $WT/.orchestrator/prompts/<task>-<role>.md. Read it once with rtk read, then follow it exactly.`
   `PY` is `jq -r .python $WT/.orchestrator/run.json`. Turns per role: SKILL.md, "Roles".

The script emits the worktree block (`WT` is always the run's worktree; absolute paths;
`cd <WT> && ` before every Bash command), the cited code pasted from current source, the exact
changes and test ids, the `## Done when` checklist, the command card, the graft context, the tool
rules, the turn limit and checkpoint rule, the required clauses, the report cap, and the
`dispatch-prompt v1` marker line that `orchestrator-model-guard.js` rule 7 checks. Never repeat or
reword them in the role inputs.

## orch-scout

`--role scout`. Code map: the seed `path:line` entry points from your own graft queries. Its final
message (the hand-back) is the table; persist it with `save-map.sh <agent-id> <task> scout`.
```
Repo root: <path>
Question: <what the design gate needs located or mapped for this task>
Return a table of at most 60 lines: symbol or file | path:line | one-line role. Cover every
symbol the packet changes or calls, every caller or dependent of the symbols the change will
touch, and each failing test's target. Report only what you read.
```

## orch-design-gate

`--role design-gate --spec <the task's plan spans>`. `--map` is the scout's saved table. One agent
per task; its final message is the implementer packet map. Persist it with
`save-map.sh <agent-id> <task> implementer <scout-id>`.
```
Repo root: <path>
Plan: <plan path>, task <task id> (this task only)
Return the packet map: write:, change: (at most 3), test:, done:, keep:, sym:, model:/model-reason:
only for a trust-boundary task, then the complete path:line code map. Resolve every ambiguity to the
design that delivers the full plan scope. A true grant is one GRANT: line.
```

## orch-planner

`--role planner`. `write:` the plan file.
```
Repo root: <path>
Target: <spec path or verbatim user request>
Scout map: <paste scout table>
Base branch: <branch>
Plan file: docs/phase-plans/phase-<id>-<slug>-plan.md
Existing plan convention to follow: <path of newest plan in docs/phase-plans/>
<For a revision: the verified findings to address, each with file:line evidence.>
```

## orch-implementer

`--role implementer`, plus Agent `model: "opus"` and a `model-reason:` line in the map when the
brief flags the task as trust-boundary. Two dispatches per task:

Test authoring: `--mode tests`; `write:` lines all under `tests/`; `done:` lines; no `--red-log`.
Accept the result with `test-acceptance.py`; its output is the RED log.

Implementation: `--mode impl`; `write:` one line per allowed file; `change:` one line per exact
change (`path:line` and the change); `test:` one line per exact test id; `done:` lines; `keep:`
lines; code map: every symbol the task changes or calls, with callers; `--red-log` the accepted
RED log. `--spec` the brief's and plan's spans. A fix round is a fresh agent with a new map
carrying only the evidence.
```
Repo root: <path>
Plan: <plan path>, task <task id>
Objective: <one sentence>
Verify: <exact commands>
stop_if: <conditions>
<For a fix round: the exact failure output or review finding, with file:line.>
```

## orch-verifier

`--role verifier`. Code map: the changed spans the commands exercise; `test:` the test ids being run.
```
Repo root: <path>
Run these commands in order, from the repo root, and report each one:
<command 1>
<command 2>
```

## orch-reviewer

`--role reviewer --review-of <task>`. Reviewers never get a whole diff to read (F22). The code map
is the changed-symbol list: one `path:A-B symbol | change` line per changed symbol, built from
`rtk proxy git diff -U0 <base>` hunk headers (through context-mode) and graft, plus each
changed symbol's callers. `--spec` the design brief's spans.
```
Repo root: <path>
Task packet: <objective, write files, steps, done items, stop_if>
Changed symbols: in the code map above. Read each cited range; for one hunk use
`rtk proxy git diff -U3 <base> -- <path>` written to a file, then read only its cited lines.
Verifier results: <paste, at most 30 lines; full log path under .orchestrator/>
```

## orch-adversarial-reviewer

`--role adversarial-reviewer`. Plan and phase review only; the per-task design gate is `orch-design-gate`.

Plan mode:
```
Mode: plan
Repo root: <path>
Plan: <plan path>
Source spec: <path or verbatim request>
Citation, count, and signature accuracy was already checked by verified-planning. Spend the
review on whether the plan will actually work against this repo.
```

Phase mode:
```
Mode: phase
Repo root: <path>
Plan: <plan path>
Changed symbols: in the code map above (the phase's changed-symbol list from
`rtk proxy git diff -U0 <base-sha>...HEAD` hunk headers and graft). Read each cited range, never
the whole diff.
Verifier results for the full suite: <paste, at most 30 lines; full log path under .orchestrator/>
```

## Codex (phase end)

`codex review --base <branch>` rejects a custom prompt, so the scoped review runs through
`codex exec` in a read-only sandbox. Run from the repo root with Bash `run_in_background: true`:

```bash
mkdir -p .orchestrator/reviews
codex exec -s read-only -C "$(pwd)" -o .orchestrator/reviews/codex-phase-<id>.md \
  "You are an adversarial code reviewer. Do not edit files. Review every change on this branch \
relative to <base-branch> (read it with: git diff <base-sha>...HEAD). Cover: architecture fit \
against the existing code, breakage risk to existing callers, tests, and data, correctness bugs \
with a concrete failing input, security, and whether tests actually exercise the new behavior. \
Skip style nits. For each finding give file:line, the failure scenario, and severity." \
  > .orchestrator/reviews/codex-phase-<id>.log 2>&1
```
The findings are in `codex-phase-<id>.md` (the final message); the `.log` holds the session.

## agy / Gemini (phase end)

```bash
rtk proxy git diff <base-sha>...HEAD > .orchestrator/reviews/phase-<id>.diff
agy --print "You are an adversarial code reviewer. Review the diff in \
.orchestrator/reviews/phase-<id>.diff against the repository at $(pwd). Cover: architecture fit, \
breakage risk to existing callers/tests/data, correctness bugs with a concrete failing input, \
security, test depth. Skip style nits. For each finding give file:line, failure scenario, \
severity." --model gemini-3.1-pro-high --sandbox \
  > .orchestrator/reviews/agy-phase-<id>.md 2>&1
```

Run `agy models` first if `gemini-3.1-pro-high` is rejected, and use the newest Gemini Pro High
id it lists. Never a Claude Fable/Mythos id.

## codex exec (stuck task, independent diagnosis)

```bash
codex exec -s read-only -C <repo-root> -o .orchestrator/reviews/codex-diag-<task>.md \
  "Diagnose why this fails. Do not edit files. Failure: <exact output>. Task: <objective>. \
Relevant files: <paths>. Give the root cause with file:line evidence and the fix."
```

## orch-docs

`--role docs`. `write:` each doc to create or update; code map: the changed spans the docs
describe. The docs map's `write:` lines join the task's allowed files for `task-gate.sh`
(`.orchestrator/maps/<task>-docs.md`).
```
Repo root: <path>
Change summary: <what changed, with commit SHAs>
Docs to create or update: <paths, or "find every affected doc under docs/">
<Handoff mode: write docs/phase-plans/phase-<id>-<slug>-handoff.md with: goal, what now works
and how to try it, branch and commits, verification commands and results, review findings and
their resolutions.>
```
