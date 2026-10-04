#!/usr/bin/env bash
# Plan F2/F17: one gate run at a time on the machine, a basetemp unique to each run that is removed on a pass
# and kept (and recorded) on a failure, and a stale lock that is reclaimed.
set -uo pipefail
GATE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../scripts" && pwd)/gate.sh"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
export TMPDIR="$tmp/t"; mkdir -p "$TMPDIR"
pass=0 fail=0
check() { if [ "$2" -eq 0 ]; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL: $1"; fi; }
for r in A B; do
  mkdir -p "$tmp/run$r/.orchestrator"
  git -C "$tmp/run$r" init -q; git -C "$tmp/run$r" config user.email t@t; git -C "$tmp/run$r" config user.name t
  echo x > "$tmp/run$r/f"; git -C "$tmp/run$r" add f; git -C "$tmp/run$r" commit -q -m base
done
bts() { ls "$TMPDIR" | grep -c 'rush-gate-bt' || true; }

printf '%s\n' 'mkdir -p "$RUSH_GATE_BT" && echo x > "$RUSH_GATE_BT/f" && sleep 3' > "$tmp/runA/.orchestrator/gate.cmds"
printf '%s\n' 'true' > "$tmp/runB/.orchestrator/gate.cmds"
bash "$GATE" "$tmp/runA" > "$tmp/a.out" 2>&1 & holder=$!
sleep 1
bash "$GATE" "$tmp/runB" > "$tmp/b.out" 2>&1; code=$?
[ "$code" -eq 3 ] && grep -q "a gate run is active" "$tmp/b.out"; check "a second worktree's gate is refused while the first holds the machine-wide lock" $?
wait "$holder"
grep -q "gate ok" "$tmp/a.out"; check "the first gate finishes ok" $?
[ "$(bts)" = 0 ]; check "a passing run removes its unique basetemp" $?

printf '%s\n' 'mkdir -p "$RUSH_GATE_BT" && echo x > "$RUSH_GATE_BT/f" && false' > "$tmp/runA/.orchestrator/gate.cmds"
bash "$GATE" "$tmp/runA" > /dev/null 2>&1; code=$?
[ "$code" -eq 1 ] && [ "$(bts)" = 1 ] && [ -s "$tmp/runA/.orchestrator/gate-keep" ]; check "a failing run keeps its basetemp and records it in gate-keep" $?
printf '%s\n' 'true' > "$tmp/runA/.orchestrator/gate.cmds"
bash "$GATE" "$tmp/runA" > /dev/null 2>&1
[ "$(bts)" = 0 ] && [ ! -e "$tmp/runA/.orchestrator/gate-keep" ]; check "the next gate run removes the kept basetemp" $?

mkdir "$TMPDIR/rush-gate.lock"; echo 99999 > "$TMPDIR/rush-gate.lock/pid"
bash "$GATE" "$tmp/runA" > /dev/null 2>&1; check "a lock held by a dead pid is reclaimed" $?
[ "$(cat "$tmp/runA/.orchestrator/gate-ok")" = "$(git -C "$tmp/runA" rev-parse HEAD)" ]; check "gate-ok holds the HEAD of the gated tree" $?

echo "passed $pass, failed $fail"
[ "$fail" -eq 0 ]
