#!/usr/bin/env bash
# task-gate.sh <task-id> <commit-message> [--check]
# Run from the worktree root: cd $WT && bash task-gate.sh T9 "feat(scope): T9 summary" [--check]
# --check does steps 2 and 3 (allowed files, task tests, lint) and stops before any git write, so it can
# run after the implementer and after each fix round. Without --check it does the same checks and then
# steps 7 and 8 (stage exactly the changed paths, commit, log): run it once, after review and docs.
# Prints at most 14 lines.
# Reads .orchestrator/maps/<task>-implementer.md: `write:` lines = allowed files, `test:` lines = test ids.
set -uo pipefail
t="${1:?task id}"; msg="${2:?commit message}"; mode="${3:-commit}"
map=.orchestrator/maps/$t-implementer.md
log=.orchestrator/gate-$t.log
fail() { echo "GATE FAIL $t: $1"; shift; for l in "$@"; do echo "$l"; done; exit "${CODE:-1}"; }
[ -f "$map" ] || CODE=2 fail "no map $map"
docsmap=.orchestrator/maps/$t-docs.md   # docs written for this task are part of its commit
allowed=$(sed -n 's/^write: *//p' "$map" $( [ -f "$docsmap" ] && echo "$docsmap" ) | sort -u)
tests=$(sed -n 's/^test: *//p' "$map")
[ -n "$allowed" ] || CODE=2 fail "map has no write: line"
[ -n "$tests" ] || CODE=2 fail "map has no test: line"
changed=$(git status --porcelain -uall | cut -c4- | sort -u)
[ -n "$changed" ] || fail "no changes in the worktree"
outside=$(comm -13 <(echo "$allowed") <(echo "$changed"))
[ -z "$outside" ] || fail "changed outside the write: list (revert these):" $(echo "$outside" | head -10)
# shellcheck disable=SC2086
${TEST_CMD:-python -m pytest -q -x -p no:cacheprovider} $tests > "$log" 2>&1 \
  || fail "task tests failed (log $log):" "$(tail -8 "$log")"
pyfiles=$(echo "$changed" | grep '\.py$' || true)
if [ -n "$pyfiles" ]; then
  # shellcheck disable=SC2086
  ${CHECK_CMD:-ruff check} $pyfiles >> "$log" 2>&1 \
    || fail "lint failed (log $log):" "$(tail -8 "$log")"
fi
if [ "$mode" = "--check" ]; then
  echo "GATE CHECK PASS $t files=$(echo "$changed" | wc -l | tr -d ' ') tests=$(echo "$tests" | wc -l | tr -d ' ')"
  exit 0
fi
# shellcheck disable=SC2086
git add -- $changed
staged=$(git diff --cached --name-only | sort -u)
[ "$staged" = "$changed" ] || fail "staged list differs from changed list" "$(diff <(echo "$changed") <(echo "$staged") | head -6)"
git commit -q -m "$msg" || fail "git commit failed"
sha=$(git rev-parse --short HEAD)
if [ -n "${RUN_STATE:-}" ] && [ -f "$RUN_STATE" ]; then bash "$RUN_STATE" log "$t committed $sha" > /dev/null; fi
echo "GATE PASS $t $sha files=$(echo "$changed" | wc -l | tr -d ' ') tests=$(echo "$tests" | wc -l | tr -d ' ')"
