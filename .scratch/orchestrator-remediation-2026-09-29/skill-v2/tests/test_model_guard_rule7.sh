#!/usr/bin/env bash
# Plan B1/H11/F4: the real ~/.claude/hooks/orchestrator-model-guard.js (rule 7) accepts a prompt file that
# dispatch-prompt.sh generated and the Agent input references, and denies the other three shapes:
# the generator's stdout pasted as the prompt, a saved file edited afterwards, a hand-written file.
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
script="$here/../scripts/dispatch-prompt.sh"
guard="$HOME/.claude/hooks/orchestrator-model-guard.js"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
pass=0 fail=0
check() { if [ "$2" -eq 0 ]; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL: $1"; fi; }

[ -f "$guard" ]; check "the installed model guard exists at $guard" $?
wt="$tmp/wt"; mkdir -p "$wt/.orchestrator/prompts"
echo '{}' > "$wt/.orchestrator/run.json"
cat > "$tmp/map.md" <<'EOF'
src/rush/tools/lint.py:40-88 run_lint | builds the engine command
scout: a1b2c3d4
EOF
export DISPATCH_PROMPT_NO_GRAFT_BUILD=1
prompt="$wt/.orchestrator/prompts/T9-scout.md"
bash "$script" --role scout --task T9 --worktree "$wt" --map "$tmp/map.md" > "$prompt" 2>/dev/null
[ -s "$prompt" ]; check "dispatch-prompt.sh wrote the saved prompt file" $?

# The guard finds the run from input.cwd; the model comes from the agent definition, so pass it explicitly.
verdict() { # $1 = prompt text for the Agent input
  python3 - "$wt" "$1" <<'PY' | node "$guard"
import json, sys
print(json.dumps({"cwd": sys.argv[1], "tool_name": "Agent", "transcript_path": "",
                  "tool_input": {"subagent_type": "orch-scout", "model": "haiku", "prompt": sys.argv[2]}}))
PY
}
out="$(verdict "Your packet is $prompt. Read it once with rtk read, then follow it exactly.")"
[ -z "$out" ]; check "a reference to the saved generator output is allowed" $?

out="$(verdict "$(cat "$prompt")")"
[[ "$out" == *'"permissionDecision":"deny"'* ]]; check "the generator's stdout pasted as the prompt is denied (no file reference)" $?

cp "$prompt" "$tmp/orig.md"; sed -i '' '1s/^/EDITED /' "$prompt"
out="$(verdict "Your packet is $prompt.")"
[[ "$out" == *"sha256 mismatch"* ]]; check "a saved prompt whose body was edited afterwards is denied (sha256 mismatch)" $?
cp "$tmp/orig.md" "$prompt"; echo "extra line" >> "$prompt"
out="$(verdict "Your packet is $prompt.")"
[[ "$out" == *'"permissionDecision":"deny"'* ]]; check "a line appended after the marker is denied" $?
cp "$tmp/orig.md" "$prompt"

echo "hand written packet" > "$wt/.orchestrator/prompts/T9-hand.md"
out="$(verdict "Your packet is $wt/.orchestrator/prompts/T9-hand.md.")"
[[ "$out" == *"no valid sha256 marker"* ]]; check "a hand-written file is denied" $?

echo "passed $pass, failed $fail"
[ "$fail" -eq 0 ]
