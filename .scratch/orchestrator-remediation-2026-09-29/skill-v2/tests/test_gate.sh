#!/usr/bin/env bash
# Fixture test for gate.sh: per-step exit codes recorded separately, gate-ok
# only written on all-zero.
set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../scripts" && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

git -C "$tmp" init -q
git -C "$tmp" config user.email test@test.com
git -C "$tmp" config user.name test
git -C "$tmp" commit --allow-empty -q -m init

mkdir -p "$tmp/.orchestrator"
fail=0

# --- run 1: one command fails ---
cat > "$tmp/.orchestrator/gate.cmds" <<'EOF'
true
false
echo hi
EOF

if "$SCRIPTS_DIR/gate.sh" "$tmp"; then
  echo "FAIL: gate.sh should have exited non-zero on a failing step"
  fail=1
fi
[ -e "$tmp/.orchestrator/gate-ok" ] && { echo "FAIL: gate-ok should not exist after a failed run"; fail=1; }
log_content="$(cat "$tmp/.orchestrator/gate-log")"
[[ "$log_content" == *"0 true"* ]] || { echo "FAIL: expected '0 true' in gate-log, got: $log_content"; fail=1; }
[[ "$log_content" == *"1 false"* ]] || { echo "FAIL: expected '1 false' in gate-log, got: $log_content"; fail=1; }
[[ "$log_content" == *"0 echo hi"* ]] || { echo "FAIL: expected '0 echo hi' in gate-log, got: $log_content"; fail=1; }

# --- run 2: all commands pass ---
cat > "$tmp/.orchestrator/gate.cmds" <<'EOF'
true
true
EOF
if ! "$SCRIPTS_DIR/gate.sh" "$tmp"; then
  echo "FAIL: gate.sh should exit 0 when every step is 0"
  fail=1
fi
expected_head="$(git -C "$tmp" rev-parse HEAD)"
actual_head="$(cat "$tmp/.orchestrator/gate-ok")"
[ "$expected_head" = "$actual_head" ] || { echo "FAIL: gate-ok content mismatch"; fail=1; }

# Zero-skip rule: a pytest step whose log reports skipped or xfailed tests fails the gate; one with no log fails too.
rm -f "$tmp/.orchestrator/gate-ok"
cat > "$tmp/.orchestrator/gate.cmds" <<'EOF'
bash -c 'echo "10 passed, 2 skipped in 1.2s"' > out.log 2>&1 && : pytest
EOF
if "$SCRIPTS_DIR/gate.sh" "$tmp" 2>/dev/null; then
  echo "FAIL: gate.sh should fail a pytest step that reported skipped tests"
  fail=1
fi
[[ "$(cat "$tmp/.orchestrator/gate-log")" == *"97 zero-skip rule: pytest reported 2 skipped"* ]] || { echo "FAIL: zero-skip message missing from gate-log"; fail=1; }
[ -e "$tmp/.orchestrator/gate-ok" ] && { echo "FAIL: gate-ok must not exist after a skipped-test run"; fail=1; }
cat > "$tmp/.orchestrator/gate.cmds" <<'EOF'
bash -c 'echo "12 passed in 1.2s"' > out.log 2>&1 && : pytest
EOF
"$SCRIPTS_DIR/gate.sh" "$tmp" > /dev/null 2>&1 || { echo "FAIL: a pytest step with no skips must pass"; fail=1; }
cat > "$tmp/.orchestrator/gate.cmds" <<'EOF'
bash -c 'echo "12 passed in 1.2s"' && : pytest
EOF
if "$SCRIPTS_DIR/gate.sh" "$tmp" 2>/dev/null; then
  echo "FAIL: a pytest step with no log redirect must fail"
  fail=1
fi
[[ "$(cat "$tmp/.orchestrator/gate-log")" == *"98 pytest command has no"* ]] || { echo "FAIL: no-redirect message missing"; fail=1; }

if [ "$fail" -eq 0 ]; then
  echo "test_gate.sh: PASS"
else
  echo "test_gate.sh: FAIL"
  exit 1
fi
