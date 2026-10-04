#!/usr/bin/env bash
# Plan B4/F5: a read-only agent's final message becomes the map file without a Write tool.
set -uo pipefail
SM="$(cd "$(dirname "${BASH_SOURCE[0]}")/../scripts" && pwd)/save-map.sh"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
pass=0 fail=0
check() { if [ "$2" -eq 0 ]; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL: $1"; fi; }
R="$tmp/r"; mkdir -p "$R"; git -C "$R" init -q
S="$tmp/subagents"; mkdir -p "$S"
cat > "$S/agent-abc.jsonl" <<'EOF'
{"type":"user","message":{"role":"user","content":"map T9"}}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"working"}]}}
{"type":"assistant","message":{"role":"assistant","stop_reason":"end_turn","content":[{"type":"text","text":"write: src/x.py\nchange: src/x.py:10 do it\nsrc/x.py:8-20 f | target"}]}}
{"type":"system","hookEvent":"SubagentStop"}
EOF
cd "$R"
export ORCH_SUBAGENTS_DIR="$S"
out="$(bash "$SM" abc T9 implementer scout123)"; check "save-map writes the map" $?
f=".orchestrator/maps/T9-implementer.md"
[ "$(head -1 "$f")" = "write: src/x.py" ]; check "the map starts with the agent's final message, not its earlier text" $?
grep -q '^scout: scout123$' "$f"; check "a scout: line is added when a scout id is given" $?
bash "$SM" abc T9 implementer scout123 > /dev/null; [ "$(grep -c '^scout: scout123$' "$f")" = 1 ]; check "running it twice does not duplicate the scout: line" $?
bash "$SM" nope T9 implementer > /dev/null 2>&1; [ $? -eq 1 ]; check "an unknown agent id fails" $?
cat > "$S/agent-hb.jsonl" <<'EOF'
{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"t1","name":"SubagentHandback","input":{"message":"write: src/y.py\nsrc/y.py:3-9 g | target"}}]}}
{"type":"user","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"t1","content":"{\"success\":true}"}]}}
{"type":"assistant","message":{"role":"assistant","stop_reason":"end_turn","content":[{"type":"text","text":"Report delivered to the caller via SubagentHandback."}]}}
EOF
bash "$SM" hb T8 scout > /dev/null; [ "$(head -1 .orchestrator/maps/T8-scout.md)" = "write: src/y.py" ]; check "the SubagentHandback message is the report, not the closing 'Report delivered' text" $?
echo "passed $pass, failed $fail"
[ "$fail" -eq 0 ]
