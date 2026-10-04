#!/usr/bin/env bash
# Tests for scripts/dispatch-prompt.sh. Run: bash tests/test-dispatch-prompt.sh
set -uo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
script="$here/../scripts/dispatch-prompt.sh"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
pass=0 fail=0

check() { # name, condition exit code
  if [ "$2" -eq 0 ]; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL: $1"; fi
}
has() { grep -qF -- "$1" "$tmp/out"; }

wt="$tmp/wt"
mkdir -p "$wt"
cat > "$tmp/map.md" <<'EOF'
write: src/rush/tools/lint.py
write: tests/test_lint.py
src/rush/tools/lint.py:40-88 run_lint | builds the engine command
src/rush/cli.py:212 lint_cmd | caller of run_lint
change: src/rush/tools/lint.py:52 pass --no-cache to the engine argv
test: tests/test_lint.py::test_no_cache_flag
keep: tests/test_lint.py::test_default_run -- lint of a clean file stays ok
scout: a1b2c3d4
done: python -m pytest tests/test_lint.py::test_no_cache_flag exits 0
done: src/rush/tools/lint.py:52 passes --no-cache to the engine argv
EOF

: > "$tmp/red.log"
# 1. map present: prompt builds with every required section
bash "$script" --role implementer --task T9 --worktree "$wt" --map "$tmp/map.md" \
  --spec docs/phase-plans/p70-plan.md:120-160 --test-cmd "pytest -q" --red-log "$tmp/red.log" > "$tmp/out" 2> "$tmp/err"
check "map present exits 0" $?
for s in "## Worktree and write targets" "## Spec spans" "## Code map" "## Exact changes" \
  "## Exact test ids" "## Done when" "## Tool rules" "## Turn limit" "## Required clauses" "## Report"; do
  has "$s"; check "section: $s" $?
done
has "Worktree: $wt"; check "worktree path" $?
has "- src/rush/tools/lint.py"; check "write target listed" $?
has "docs/phase-plans/p70-plan.md lines 120-160"; check "spec span listed" $?
has "src/rush/cli.py:212 lint_cmd | caller of run_lint"; check "map line copied" $?
has "src/rush/tools/lint.py:52 pass --no-cache to the engine argv"; check "change listed" $?
has "tests/test_lint.py::test_no_cache_flag"; check "test id listed" $?
has "at most 100 turns"; check "turn limit for the implementer role" $?
has "- [ ] python -m pytest tests/test_lint.py::test_no_cache_flag exits 0"; check "done item rendered as a checkbox" $?
! has "Budget:"; check "no token budget paragraph" $?
has "$wt/.orchestrator/"; check "output-to-file dir" $?
for c in "Never kill a process you did not start" "git stash" "Do not commit" \
  "TemporaryDirectory" "~/.claude.json" "~/.codex" "never create a virtual environment" "xfail" '"not expressible"' \
  "graft" "codegraph" "repowise" "200 lines" "50 lines"; do
  has "$c"; check "clause: $c" $?
done
last="$(tail -n 1 "$tmp/out")"
body_hash="$(sed '$d' "$tmp/out" | shasum -a 256 | cut -d' ' -f1)"
[ "$last" = "<!-- dispatch-prompt v1 sha256:$body_hash -->" ]; check "marker line matches body hash" $?

# 2. map missing: exit 2
bash "$script" --role implementer --red-log "$tmp/red.log" --task T9 --worktree "$wt" --map "$tmp/nope.md" \
  --spec docs/p.md:1-5 --test-cmd "pytest -q" > "$tmp/out" 2> "$tmp/err"
[ $? -eq 2 ]; check "missing map exits 2" $?
[ ! -s "$tmp/out" ]; check "missing map prints no prompt" $?

# 3. map with no path:line entries: exit 2
printf 'write: src/x.py\nlook around the lint module, meeting at 10:30\n' > "$tmp/bare.md"
bash "$script" --role reviewer --review-of T9 --task T9 --worktree "$wt" --map "$tmp/bare.md" \
  --spec docs/p.md:1-5 > "$tmp/out" 2> "$tmp/err"
[ $? -eq 2 ]; check "no path:line exits 2" $?
[ ! -s "$tmp/out" ]; check "no path:line prints no prompt" $?

# 4. implementer map without change/test lines: exit 2
printf 'write: src/x.py\nsrc/x.py:10 f | target\n' > "$tmp/nochange.md"
bash "$script" --role implementer --red-log "$tmp/red.log" --task T9 --worktree "$wt" --map "$tmp/nochange.md" \
  --spec docs/p.md:1-5 --test-cmd "pytest -q" > "$tmp/out" 2> "$tmp/err"
[ $? -eq 2 ]; check "implementer without change/test exits 2" $?

# 5. bad spec span, bad role, removed --budget flag: exit 2
bash "$script" --role implementer --red-log "$tmp/red.log" --task T9 --worktree "$wt" --map "$tmp/map.md" \
  --spec docs/x.md --test-cmd "pytest -q" > /dev/null 2>&1
[ $? -eq 2 ]; check "malformed --spec exits 2" $?
bash "$script" --role fork --task T9 --worktree "$wt" --map "$tmp/map.md" > /dev/null 2>&1
[ $? -eq 2 ]; check "unknown role exits 2" $?
bash "$script" --role reviewer --review-of T77 --task T77 --worktree "$wt" --map "$tmp/map.md" --spec docs/p.md:1-5 --budget 150000 > /dev/null 2>&1
[ $? -eq 2 ]; check "the removed --budget argument exits 2" $?
(cd "$tmp" && bash "$script" --role reviewer --review-of T9 --task T9 --worktree wt --map map.md --spec docs/p.md:1-5) > /dev/null 2>&1
[ $? -eq 2 ]; check "relative worktree exits 2" $?

# 6. read-only role: no write targets, orch- prefix accepted
bash "$script" --role orch-reviewer --review-of T9 --task T9 --worktree "$wt" --map "$tmp/map.md" \
  --spec docs/p.md:1-5 > "$tmp/out" 2> /dev/null
check "orch-reviewer builds" $?
has "none: read-only role"; check "reviewer has no write targets" $?

# 7. new required arguments and sections
bash "$script" --role implementer --red-log "$tmp/red.log" --task T9 --worktree "$wt" --map "$tmp/map.md" \
  --spec docs/p.md:1-5 > /dev/null 2>&1
[ $? -eq 2 ]; check "implementer without --test-cmd exits 2" $?
bash "$script" --role implementer --red-log "$tmp/red.log" --task T9 --worktree "$wt" --map "$tmp/map.md" \
  --test-cmd "pytest -q" > /dev/null 2>&1
[ $? -eq 2 ]; check "implementer without --spec exits 2" $?
bash "$script" --role reviewer --review-of T9 --task T9 --worktree "$wt" --map "$tmp/map.md" \
  > /dev/null 2>&1
[ $? -eq 2 ]; check "reviewer without --spec exits 2" $?
bash "$script" --role implementer --red-log "$tmp/red.log" --task T9 --worktree "$wt" --map "$tmp/map.md" \
  --spec docs/p.md:1-5 --test-cmd "pytest -q" > "$tmp/out" 2> /dev/null
check "implementer with spec and test-cmd builds" $?
has "write the failing test first"; check "red-first rule for implementer" $?
has "## Test command"; check "test command section" $?
has "pytest -q <test files>"; check "test command listed" $?
has "docs/p.md lines 1-5"; check "spec listed" $?

# F30: two reviewer prompts per worktree (task), the third is refused.
capwt="$tmp/capwt"; mkdir -p "$capwt"
for n in 1 2; do
  DISPATCH_PROMPT_NO_GRAFT_BUILD=1 bash "$script" --role reviewer --review-of T9 --task T9 --worktree "$capwt" \
    --map "$tmp/map.md" --spec docs/p.md:1-5 > /dev/null 2>&1
  check "review round $n builds" $?
done
DISPATCH_PROMPT_NO_GRAFT_BUILD=1 bash "$script" --role reviewer --review-of T9 --task T9 --worktree "$capwt" \
  --map "$tmp/map.md" --spec docs/p.md:1-5 > "$tmp/out3" 2> "$tmp/out"
[ $? -eq 2 ]; check "third review round exits 2" $?
has "review cap reached"; check "third review names the cap" $?
[ ! -s "$tmp/out3" ]; check "third review prints no prompt" $?
[ "$(cat "$capwt/.orchestrator/review-rounds-T9")" = 2 ]; check "refused round is not counted" $?
DISPATCH_PROMPT_NO_GRAFT_BUILD=1 bash "$script" --role adversarial-reviewer --task T9 --worktree "$capwt" \
  --map "$tmp/map.md" --spec docs/p.md:1-5 > /dev/null 2>&1
check "adversarial review is not capped" $?

# F32: an implementer prompt maps every failing test to a change line.
printf 'FAILED tests/test_lint.py::test_no_cache_flag - a\nFAILED tests/test_lint.py::test_unmapped[x] - b\n' > "$tmp/red2.log"
DISPATCH_PROMPT_NO_GRAFT_BUILD=1 bash "$script" --role implementer --task T9 --worktree "$wt" --map "$tmp/map.md" \
  --spec docs/p.md:1-5 --test-cmd "pytest -q" --red-log "$tmp/red2.log" > /dev/null 2> "$tmp/out"
[ $? -eq 2 ]; check "unmapped failing test exits 2" $?
has "test_unmapped"; check "names the unmapped test" $?
DISPATCH_PROMPT_NO_GRAFT_BUILD=1 bash "$script" --role implementer --task T9 --worktree "$wt" --map "$tmp/map.md" \
  --spec docs/p.md:1-5 --test-cmd "pytest -q" > /dev/null 2> "$tmp/out"
[ $? -eq 2 ]; check "implementer without --red-log exits 2" $?

# F30: rounds are counted per task, so another task in the same worktree starts at 0.
DISPATCH_PROMPT_NO_GRAFT_BUILD=1 bash "$script" --role reviewer --review-of T10 --task T10 --worktree "$capwt" \
  --map "$tmp/map.md" --spec docs/p.md:1-5 > /dev/null 2>&1
check "other task in the same worktree is not capped" $?
DISPATCH_PROMPT_NO_GRAFT_BUILD=1 bash "$script" --role reviewer --task T9 --worktree "$capwt" \
  --map "$tmp/map.md" --spec docs/p.md:1-5 > /dev/null 2>&1
[ $? -eq 2 ]; check "reviewer without --review-of exits 2" $?

# F33: an implementer map states the behavior to keep.
grep -v '^keep:' "$tmp/map.md" > "$tmp/nokeep.md"
DISPATCH_PROMPT_NO_GRAFT_BUILD=1 bash "$script" --role implementer --red-log "$tmp/red.log" --task T9 --worktree "$wt" \
  --map "$tmp/nokeep.md" --spec docs/p.md:1-5 --test-cmd "pytest -q" > /dev/null 2> "$tmp/out"
[ $? -eq 2 ]; check "implementer map without keep: exits 2" $?
has "keep:"; check "names the missing keep: lines" $?
DISPATCH_PROMPT_NO_GRAFT_BUILD=1 bash "$script" --role implementer --red-log "$tmp/red.log" --task T9 --worktree "$wt" \
  --map "$tmp/map.md" --spec docs/p.md:1-5 --test-cmd "pytest -q" > "$tmp/out" 2>/dev/null
has "Existing behavior to keep"; check "keep section rendered" $?

# F34: an implementer packet holds at most 3 changes; bigger work is split
# into parallel dispatches, one worktree each.
{ cat "$tmp/map.md"; printf 'change: a.py:1 two\nchange: a.py:2 three\nchange: a.py:3 four\n'; } > "$tmp/map4.md"
DISPATCH_PROMPT_NO_GRAFT_BUILD=1 bash "$script" --role implementer --red-log "$tmp/red.log" --task T9 --worktree "$wt" \
  --map "$tmp/map4.md" --spec docs/p.md:1-5 --test-cmd "pytest -q" > /dev/null 2> "$tmp/out"
[ $? -eq 2 ]; check "implementer map with 4 change: lines exits 2" $?
has "split"; check "names the split into parallel dispatches" $?
# F34: each RED test's current failure is rendered, so a wrong-reason RED is
# visible before dispatch and the agent never has to rerun to learn it.
printf 'FAILED tests/test_lint.py::test_no_cache_flag - AssertionError: argv lacks --no-cache\n' > "$tmp/red3.log"
{ cat "$tmp/map.md"; echo "change: src/rush/tools/lint.py:60 fixes test_no_cache_flag"; } > "$tmp/map3.md"
DISPATCH_PROMPT_NO_GRAFT_BUILD=1 bash "$script" --role implementer --red-log "$tmp/red3.log" --task T9 --worktree "$wt" \
  --map "$tmp/map3.md" --spec docs/p.md:1-5 --test-cmd "pytest -q" > "$tmp/out" 2>/dev/null
has "Current RED failure"; check "RED failure section rendered" $?
has "argv lacks --no-cache"; check "RED failure reason rendered" $?
# F34: session transcripts are off limits.
has ".claude/projects"; check "prompt forbids reading session transcripts" $?

# Plan edits: scout:, done:, model-reason:, test-authoring mode, no budget.
export DISPATCH_PROMPT_NO_GRAFT_BUILD=1
grep -v '^scout:' "$tmp/map.md" > "$tmp/noscout.md"
bash "$script" --role implementer --red-log "$tmp/red.log" --task T9 --worktree "$wt" --map "$tmp/noscout.md" \
  --spec docs/p.md:1-5 --test-cmd "pytest -q" > /dev/null 2> "$tmp/out"
[ $? -eq 2 ]; check "implementer map without scout: exits 2" $?
has "scout:"; check "names the missing scout: line" $?
grep -v '^done:' "$tmp/map.md" > "$tmp/nodone.md"
bash "$script" --role implementer --red-log "$tmp/red.log" --task T9 --worktree "$wt" --map "$tmp/nodone.md" \
  --spec docs/p.md:1-5 --test-cmd "pytest -q" > /dev/null 2> "$tmp/out"
[ $? -eq 2 ]; check "implementer map without done: exits 2" $?
has "done:"; check "names the missing done: lines" $?
grep -v -E '^(scout|done):' "$tmp/map.md" > "$tmp/bare-scout.md"
bash "$script" --role scout --task T9 --worktree "$wt" --map "$tmp/bare-scout.md" > /dev/null 2>&1
check "scout role needs no scout: or done: line (bootstrap exemption)" $?
bash "$script" --role docs --task T9 --worktree "$wt" --map "$tmp/bare-scout.md" > /dev/null 2>&1
check "docs role needs no scout: line" $?

printf 'write: tests/test_new.py\nscout: a1b2c3d4\ndone: tests/test_new.py fails on an assertion naming the flag\nsrc/rush/tools/lint.py:40-88 run_lint | builds the engine command\n' > "$tmp/tmap.md"
bash "$script" --role implementer --mode tests --task T9 --worktree "$wt" --map "$tmp/tmap.md" \
  --spec docs/p.md:1-5 --test-cmd "pytest -q" > "$tmp/out" 2> /dev/null
check "test-authoring dispatch builds with no --red-log" $?
has "Mode: test authoring"; check "test-authoring mode is stated in the prompt" $?
printf 'write: src/rush/tools/lint.py\nscout: a1b2c3d4\ndone: x\nsrc/rush/tools/lint.py:40-88 f | g\n' > "$tmp/tmap-bad.md"
bash "$script" --role implementer --mode tests --task T9 --worktree "$wt" --map "$tmp/tmap-bad.md" \
  --spec docs/p.md:1-5 --test-cmd "pytest -q" > /dev/null 2> "$tmp/out"
[ $? -eq 2 ]; check "test-authoring dispatch with a source write target exits 2" $?
has "under tests/"; check "names the tests/ rule" $?
bash "$script" --role implementer --mode tests --red-log "$tmp/red.log" --task T9 --worktree "$wt" --map "$tmp/tmap.md" \
  --spec docs/p.md:1-5 --test-cmd "pytest -q" > /dev/null 2>&1
[ $? -eq 2 ]; check "test-authoring dispatch refuses a --red-log" $?

bash "$script" --role design-gate --task T9 --worktree "$wt" --map "$tmp/bare-scout.md" \
  --spec docs/p.md:1-5 > "$tmp/out" 2> /dev/null
check "design-gate role builds from a scout map and a spec span" $?
has "at most 80 turns"; check "design-gate has 80 turns" $?
bash "$script" --role design-gate --task T9 --worktree "$wt" --map "$tmp/bare-scout.md" > /dev/null 2>&1
[ $? -eq 2 ]; check "design-gate without --spec exits 2" $?

{ cat "$tmp/map.md"; echo "model: opus"; } > "$tmp/mopus.md"
bash "$script" --role implementer --red-log "$tmp/red.log" --task T9 --worktree "$wt" --map "$tmp/mopus.md" \
  --spec docs/p.md:1-5 --test-cmd "pytest -q" > /dev/null 2> "$tmp/out"
[ $? -eq 2 ]; check "model other than the role default without model-reason: exits 2" $?
has "model-reason"; check "names model-reason" $?
{ cat "$tmp/mopus.md"; echo "model-reason: docs/design/T9.md:12"; } > "$tmp/mopus2.md"
bash "$script" --role implementer --red-log "$tmp/red.log" --task T9 --worktree "$wt" --map "$tmp/mopus2.md" \
  --spec docs/p.md:1-5 --test-cmd "pytest -q" > /dev/null 2>&1
check "model-reason with a file:line is accepted" $?

echo "passed $pass, failed $fail"
[ "$fail" -eq 0 ]
