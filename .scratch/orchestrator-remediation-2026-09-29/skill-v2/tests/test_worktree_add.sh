#!/usr/bin/env bash
# Plan C6: a task worktree is a sibling of the phase worktree, on its own branch cut from the phase branch.
set -uo pipefail
WA="$(cd "$(dirname "${BASH_SOURCE[0]}")/../scripts" && pwd)/worktree-add.sh"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
pass=0 fail=0
check() { if [ "$2" -eq 0 ]; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL: $1"; fi; }
main="$tmp/repo"; mkdir -p "$main"
git -C "$main" init -q; git -C "$main" config user.email t@t; git -C "$main" config user.name t
git -C "$main" commit -q --allow-empty -m init; git -C "$main" branch -m main
mkdir -p "$tmp/repo-worktrees"
git -C "$main" worktree add -q -b phase/p1-main "$tmp/repo-worktrees/phase-p1" main
phase="$tmp/repo-worktrees/phase-p1"; mkdir -p "$phase/.orchestrator"
printf '{"phase":"p1","branch":"phase/p1-main"}\n' > "$phase/.orchestrator/run.json"
cd "$phase"
out="$(bash "$WA" T9 2>/dev/null)"; code=$?
[ "$code" -eq 0 ]; check "worktree-add succeeds" $?
want="$(cd "$tmp/repo-worktrees" && pwd -P)/phase-p1-T9"
[ "$(cd "$out" && pwd -P)" = "$want" ]; check "the task worktree is a sibling of the phase worktree, not nested under it" $?
[ "$(git -C "$out" branch --show-current)" = "phase/p1-T9" ]; check "it is on branch phase/p1-T9" $?
[ "$(git -C "$out" rev-parse HEAD)" = "$(git -C "$phase" rev-parse HEAD)" ]; check "it is cut from the phase branch head" $?
bash "$WA" T9 > /dev/null 2>&1; [ $? -ne 0 ]; check "a second worktree for the same task is refused" $?
cd "$tmp"; bash "$WA" T1 > /dev/null 2>&1; [ $? -ne 0 ]; check "outside a run it is refused" $?
# Free-space floor: a stub df reports 3 GiB available, then 50 GiB.
mkdir -p "$tmp/bin"
cat > "$tmp/bin/df" <<'EOF'
#!/usr/bin/env bash
echo "Filesystem 1G-blocks Used Available Capacity Mounted"
echo "/dev/x 500 497 ${STUB_FREE} 99% /"
EOF
chmod +x "$tmp/bin/df"
cd "$phase"
out="$(PATH="$tmp/bin:$PATH" STUB_FREE=3 bash "$WA" T8 2>&1)"; code=$?
[ "$code" -ne 0 ] && [[ "$out" == *"refusing: 3 GiB free (need 8)"* ]] && [ ! -d "$tmp/repo-worktrees/phase-p1-T8" ]; check "below 8 GiB free it refuses and adds no worktree" $?
PATH="$tmp/bin:$PATH" STUB_FREE=50 bash "$WA" T8 > /dev/null 2>&1; [ $? -eq 0 ] && [ -d "$tmp/repo-worktrees/phase-p1-T8" ]; check "at 50 GiB free it adds the worktree" $?
echo "passed $pass, failed $fail"
[ "$fail" -eq 0 ]
