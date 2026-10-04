#!/usr/bin/env bash
# Plan C1/C2/D1/E3/F10/F38: task graph with groups, file reservations, parking, local merge gate,
# start preflight (shadowing definitions, probe, session id, plan coverage), report, next, stop cleanup.
set -uo pipefail
SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../scripts" && pwd)"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
export HOME="$tmp/home"; mkdir -p "$HOME"
mkdir -p "$tmp/bin"
printf '#!/bin/sh\necho '"'"'[{"conclusion":"success","databaseId":1}]'"'"'\n' > "$tmp/bin/gh"; chmod +x "$tmp/bin/gh"
export PATH="$tmp/bin:$PATH"
unset CLAUDE_CODE_SESSION_ID
pass=0 fail=0
check() { if [ "$2" -eq 0 ]; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL: $1"; fi; }
rs() { "$SCRIPTS_DIR/run-state.sh" "$@"; }
next() { rs next | tr '\n' ' '; }

repo="$tmp/repo"; mkdir -p "$repo"
git -C "$repo" init -q; git -C "$repo" config user.email t@t; git -C "$repo" config user.name t
printf '#### T1 - one\n#### T2 - two\n#### T3 - three\n' > "$repo/plan.md"
git -C "$repo" add plan.md; git -C "$repo" commit -q -m init; git -C "$repo" branch -m main
git -C "$repo" checkout -q -b phase/p1-main
mkdir -p "$repo/.git/info"; echo '.orchestrator/' >> "$repo/.git/info/exclude"
cd "$repo"

rs baseline 120 > /dev/null
out="$(rs start p1 plan.md main 2>&1)"; [ $? -ne 0 ] && [[ "$out" == *"tool-probe.json"* ]]; check "start refuses without a passing probe" $?
echo '{"ok":true}' > .orchestrator/tool-probe.json
mkdir -p .claude/agents; : > .claude/agents/orch-scout.md
out="$(rs start p1 plan.md main 2>&1)"; [ $? -ne 0 ] && [[ "$out" == *"shadow"* ]]; check "start refuses while the main checkout carries project-level agent definitions" $?
rm -rf .claude
out="$(rs start p1 plan.md main 2>&1)"; [ $? -ne 0 ] && [[ "$out" == *"CLAUDE_CODE_SESSION_ID"* ]]; check "start refuses without a session id" $?
export CLAUDE_CODE_SESSION_ID=sess-test
mkdir -p "$HOME/.claude/hooks" "$HOME/.claude/agents" "$HOME/.claude/skills/orchestrator"
echo 'hook v1' > "$HOME/.claude/hooks/h.js"; echo '{}' > "$HOME/.claude/settings.json"; echo a > "$HOME/.claude/agents/orch-a.md"
export ORCH_PYTHON="$(command -v python3)"
out="$(rs start p1 plan.md main 2>&1)"; [ $? -ne 0 ] && [[ "$out" == *"no node for: T1 T2 T3"* ]]; check "start refuses while the plan headings have no nodes" $?

rs task add T1 "" src/a.py
rs task add T2 ""
rs task add T2.a "" src/b.py
rs task add T2.b "T2.a" src/b.py
out="$(rs start p1 plan.md main 2>&1)"; [ $? -ne 0 ] && [[ "$out" == *"no node for: T3"* ]]; check "T2.a covers heading T2 but T3 is still missing" $?
rs task add T3 "T1" src/a.py
out="$(ORCH_PYTHON=/nonexistent/python rs start p1 plan.md main 2>&1)"; [ $? -ne 0 ] && [[ "$out" == *"interpreter /nonexistent/python is not executable"* || "$out" == *"only"*"GiB free"* ]]; check "start refuses while the recorded interpreter is not executable" $?
out="$(rs start p1 plan.md main 2>&1)"
if [[ "$out" == *"only"*"GiB free"* ]]; then
  echo "note: the disk preflight refused start on this host; the graph checks that follow still run"
  printf '{"phase":"p1","plan":"plan.md","branch":"phase/p1-main"}\n' > .orchestrator/run.json
  echo "$(date -u +%FT%TZ) run started" > .orchestrator/progress.log
else
  [[ "$out" == *"run started"* ]]; check "start succeeds once probe, session id and task graph are in place" $?
  [ "$(jq -r .session_id "$HOME/.claude/orchestrator/active-session.json")" = sess-test ]; check "active-session.json binds the run to the session" $?
  [ "$(cat "$HOME/.claude/orchestrator/active-run")" = "$(git rev-parse --show-toplevel)" ]; check "active-run stays the plain root path the model guard reads" $?
  [ "$(jq -r .python .orchestrator/run.json)" = "$ORCH_PYTHON" ]; check "run.json records the interpreter every dispatch and the gate use" $?
fi

[ "$(next)" = "T1 T2.a " ]; check "next: T1 and T2.a; the group T2 is not dispatchable, T2.b and T3 wait for dependencies" $?
rs task start T1; rs task start T2.a
[ "$(next)" = "" ]; check "next: nothing while T1 and T2.a run and their dependents wait" $?
rs task merged T1 > /dev/null 2>&1; [ $? -ne 0 ]; check "task merged is refused without a current gate-ok" $?
git rev-parse HEAD > .orchestrator/gate-ok
rs task merged T1; check "task merged succeeds when gate-ok is HEAD" $?
[ "$(next)" = "T3 " ]; check "next: T3 is ready once T1 is merged (T2.b still waits for T2.a)" $?
rs task start T3
rs task add T4 "" src/c.py; rs task add T5 "" src/c.py
[ "$(next)" = "T4 " ]; check "two ready nodes that share src/c.py: only T4 is offered" $?
rs task merged T2.a
[ "$(next)" = "T2.b T4 " ]; check "next: T2.b (T2.a merged, src/b.py free) and T4; T5 stays held behind T4" $?
rs task start T2.b; rs task merged T2.b
[ "$(awk -F'\t' '$1=="T2"{print $3}' .orchestrator/tasks.tsv)" = merged ]; check "the group T2 rolls up to merged when T2.a and T2.b are" $?

rs task parked T5 "grant for src/c.py?"
[ "$(awk -F'\t' '$1=="T5"{print $3}' .orchestrator/tasks.tsv)" = parked ]; check "task parked sets the status" $?
grep -q "T5" .orchestrator/questions.md; check "the parked question is recorded in questions.md" $?
[ "$(next)" = "T4 " ]; check "a parked node is not offered" $?
rs task unpark T5
[ "$(awk -F'\t' '$1=="T5"{print $3}' .orchestrator/tasks.tsv)" = pending ]; check "task unpark returns it to pending" $?

mkdir -p "$HOME/.claude/projects/p"
printf '%s\n' '{"type":"assistant","timestamp":"2099-01-01T00:00:00Z","message":{"id":"m1","model":"claude-opus-5-5","role":"assistant","usage":{"input_tokens":1,"cache_creation_input_tokens":0,"cache_read_input_tokens":3000000,"output_tokens":5},"content":[]}}' \
  > "$HOME/.claude/projects/p/$CLAUDE_CODE_SESSION_ID.jsonl"
rep="$(rs report)"
[[ "$rep" == *"usage orchestrator cache-read="* ]] && [[ "$rep" == *"usage.py]"* ]] && [[ "$rep" != *"COST"* ]]; check "report prints the orchestrator's cache-read from usage.py, within the limit" $?
rep_hot="$(ORCH_COST_LIMIT_M=1 rs report)"; [[ "$rep_hot" == *"COST"* ]]; check "report shows the COST alert when the day's cache-read exceeds the limit" $?
[[ "$rep" == *"elapsed="*"merged=3/"* ]] && [[ "$rep" == *"[run-state.sh report"* ]]; check "report prints elapsed, merged/total and machine tags" $?
[[ "$rep" == *"ready="*"parked="* ]] && [[ "$rep" == *"gate=current"* ]]; check "report prints ready, parked and the gate state" $?

echo 'hook v2' > "$HOME/.claude/hooks/h.js"
git branch phase/p1-t1 phase/p1-main
git worktree add -q "$tmp/wt-t1" phase/p1-t1
echo x > dirty.txt
rs stop > /dev/null 2>&1; [ $? -ne 0 ]; check "stop is refused while the worktree has uncommitted changes" $?
rm -f dirty.txt
out="$(rs stop 2>&1)"; [[ "$out" == *"deleted merged branch phase/p1-t1"* ]]; check "stop deletes the merged task branch" $?
[[ "$out" == *"CHANGED during the run"* ]] && [[ "$out" == *"h.js"* ]]; check "stop names the hook file that changed during the run" $?
[ ! -d "$tmp/wt-t1" ]; check "stop removes the merged branch's clean worktree" $?
git rev-parse --verify -q phase/p1-main > /dev/null; check "stop keeps the phase branch" $?
[ ! -e "$HOME/.claude/orchestrator/active-session.json" ] && [ ! -e .orchestrator/run.json ]; check "stop clears the run and the session binding" $?

echo "passed $pass, failed $fail"
[ "$fail" -eq 0 ]
