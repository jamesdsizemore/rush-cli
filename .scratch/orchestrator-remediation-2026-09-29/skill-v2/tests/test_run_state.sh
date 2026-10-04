#!/usr/bin/env bash
# Fixture test for run-state.sh: preflight refusals, baseline, task graph,
# decisions wiring into status. No network (gh is stubbed).
set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../scripts" && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# --- stub gh so no network is used ---
mkdir -p "$tmp/bin"
cat > "$tmp/bin/gh" <<'EOF'
#!/usr/bin/env bash
echo '[{"conclusion":"success","databaseId":1}]'
EOF
chmod +x "$tmp/bin/gh"
export PATH="$tmp/bin:$PATH"

# --- a throwaway git repo ---
repo="$tmp/repo"
mkdir -p "$repo"
git -C "$repo" init -q
git -C "$repo" config user.email test@test.com
git -C "$repo" config user.name test
git -C "$repo" commit --allow-empty -q -m init
git -C "$repo" branch -m main

fail=0
assert_contains() {
  if [[ "$1" != *"$2"* ]]; then
    echo "FAIL: expected to find '$2' in:"
    echo "$1"
    fail=1
  fi
}

cd "$repo"

# 1. start refuses without a recorded baseline
out="$("$SCRIPTS_DIR/run-state.sh" start p1 plan.md main 2>&1)" || true
assert_contains "$out" "no baseline recorded"

# 2. record baseline, then start again (disk preflight is environment-real;
# accept either outcome but check the message matches the code path)
"$SCRIPTS_DIR/run-state.sh" baseline 120
# start also needs (plan edits C1, A5, D1): a plan whose headings all have nodes, a passing probe, a session id.
export HOME="$tmp/home"; mkdir -p "$HOME"; export CLAUDE_CODE_SESSION_ID=test-session
export ORCH_PYTHON="$(command -v python3)"
printf '#### T1 - one\n' > "$repo/plan.md"
"$SCRIPTS_DIR/run-state.sh" task add T1 ""
echo '{"ok":true}' > "$repo/.orchestrator/tool-probe.json"
out="$("$SCRIPTS_DIR/run-state.sh" start p1 plan.md main 2>&1)" || true
if [[ "$out" == *"only"*"GiB free"* ]]; then
  echo "note: disk preflight refused start (real free space < 15GiB on this host) -- expected code path exercised"
else
  assert_contains "$out" "run started"
  assert_contains "$out" "F-items applying to this run"
  assert_contains "$out" "F1"
  assert_contains "$out" "F16"
fi

# 3. task graph: independent of `start`, only needs the repo + state dir
"$SCRIPTS_DIR/run-state.sh" task add A ""
"$SCRIPTS_DIR/run-state.sh" task add B "A"
"$SCRIPTS_DIR/run-state.sh" task start B
status_out="$("$SCRIPTS_DIR/run-state.sh" status 2>&1)" || true
# B depends on unmerged A, and is running -> flagged
assert_contains "$status_out" "running with unmerged dep: B"
# A has no deps, is pending -> unblocked idle
assert_contains "$status_out" "unblocked idle: A"

git rev-parse HEAD > "$repo/.orchestrator/gate-ok"   # task merged needs a gate run on the current HEAD
"$SCRIPTS_DIR/run-state.sh" task merged A
status_out="$("$SCRIPTS_DIR/run-state.sh" status 2>&1)"
if [[ "$status_out" == *"running with unmerged dep: B"* ]]; then
  echo "FAIL: B should no longer be flagged once A is merged"
  fail=1
fi

# 4. decisions.sh wired into status: add a decision matching a pattern
# present in the repo, confirm it shows as pending, then mark applied.
echo "TODO_MARKER" > "$repo/needs-fix.txt"
git -C "$repo" add needs-fix.txt
git -C "$repo" commit -q -m "add marker"
"$SCRIPTS_DIR/decisions.sh" add D1 "TODO_MARKER" "replace markers"
status_out="$("$SCRIPTS_DIR/run-state.sh" status 2>&1)"
assert_contains "$status_out" "D1 needs-fix.txt"
"$SCRIPTS_DIR/decisions.sh" applied D1 needs-fix.txt
status_out="$("$SCRIPTS_DIR/run-state.sh" status 2>&1)"
if [[ "$status_out" == *"D1 needs-fix.txt"* ]]; then
  echo "FAIL: D1 needs-fix.txt should be gone after being marked applied"
  fail=1
fi

if [ "$fail" -eq 0 ]; then
  echo "test_run_state.sh: PASS"
else
  echo "test_run_state.sh: FAIL"
  exit 1
fi
