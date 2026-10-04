#!/usr/bin/env bash
# Plan I1/F8: task-gate.sh --check runs steps 2 and 3 and never commits; the one commit comes last and
# includes the docs agent's files; a stray file, a failing test or a clean tree stops it.
set -uo pipefail
GATE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../scripts" && pwd)/task-gate.sh"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
pass=0 fail=0
check() { if [ "$2" -eq 0 ]; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL: $1"; fi; }
R="$tmp/r"; mkdir -p "$R/.orchestrator/maps" "$R/docs" "$R/.git"
git -C "$R" init -q; git -C "$R" config user.email t@t; git -C "$R" config user.name t
echo base > "$R/a.txt"; git -C "$R" add a.txt; git -C "$R" commit -q -m base
mkdir -p "$R/.git/info"; echo '.orchestrator/' > "$R/.git/info/exclude"
printf 'write: a.txt\nwrite: t_ok.txt\ntest: t_ok.txt\n' > "$R/.orchestrator/maps/T1-implementer.md"
printf 'write: docs/T1.md\n' > "$R/.orchestrator/maps/T1-docs.md"
export TEST_CMD="grep -q OK" CHECK_CMD=true
cd "$R"
commits() { git rev-list --count HEAD; }

echo OK > t_ok.txt; echo v1 >> a.txt
out="$(bash "$GATE" T1 "feat: T1" --check)"; [[ "$out" == "GATE CHECK PASS T1 files=2 tests=1" ]]; check "--check passes after the implementer" $?
[ "$(commits)" = 1 ]; check "--check made no commit" $?
echo BAD > t_ok.txt
out="$(bash "$GATE" T1 "feat: T1" --check)"; [ $? -eq 1 ] && [[ "$out" == *"task tests failed"* ]]; check "--check fails when a task test fails (a review found a bug)" $?
echo OK > t_ok.txt; echo v2 >> a.txt
bash "$GATE" T1 "feat: T1" --check > /dev/null; check "--check passes again after the fix round" $?
echo doc > docs/T1.md
out="$(bash "$GATE" T1 "feat: T1" --check)"; [[ "$out" == *"files=3"* ]]; check "the docs agent's file is inside the allowed list" $?
out="$(bash "$GATE" T1 "feat: T1")"; [[ "$out" == GATE\ PASS\ T1\ * ]] && [ "$(commits)" = 2 ]; check "the final call commits once" $?
[ "$(git show --stat --format= HEAD | grep -c '|')" = 3 ]; check "the commit holds exactly the three changed files" $?
bash "$GATE" T1 "feat: T1" > /dev/null 2>&1; [ $? -eq 1 ]; check "a second final call fails: no changes" $?
echo x > stray.txt
out="$(bash "$GATE" T1 "feat: T1" --check 2>&1)"; [ $? -eq 1 ] && [[ "$out" == *"stray.txt"* ]]; check "a file outside the write lists is named and refused" $?
rm -f stray.txt
bash "$GATE" T2 "feat: T2" --check > /dev/null 2>&1; [ $? -eq 2 ]; check "a task with no map exits 2" $?

echo "passed $pass, failed $fail"
[ "$fail" -eq 0 ]
