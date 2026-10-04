#!/usr/bin/env bash
# Plan A2/A3/A4/A5/B7/F15: patch-agents.py on a snapshot of the seven live definitions.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PA="$here/../scripts/patch-agents.py"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
pass=0 fail=0
check() { if [ "$2" -eq 0 ]; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL: $1"; fi; }
cp "$here"/fixtures/agents/orch-*.md "$tmp/"

python3 "$PA" "$tmp" > "$tmp/dry.diff"; check "dry run succeeds" $?
[ -s "$tmp/dry.diff" ] && ! grep -q 'omitClaudeMd' "$tmp/orch-scout.md"; check "a dry run prints a diff and changes nothing" $?
python3 "$PA" "$tmp" --write > /dev/null; check "--write succeeds" $?
ls "$tmp"/orch-*.md | wc -l | grep -q '^ *8$'; check "eight definitions exist: the seven and orch-design-gate" $?
for role in implementer docs reviewer planner adversarial-reviewer design-gate scout verifier; do
  f="$tmp/orch-$role.md"
  grep -q '^omitClaudeMd: true$' "$f" && grep -q '^maxTurns: [0-9]*$' "$f" && grep -q '^model: claude-' "$f" && grep -q 'ToolSearch' "$f" \
    && grep -q 'mcp__graft__graft_find_code' "$f" && grep -q 'ctx_execute_file' "$f"
  check "orch-$role: full model id, maxTurns, omitClaudeMd, ToolSearch, graft and context-mode tools" $?
done
grep -q '^effort: high$' "$tmp/orch-adversarial-reviewer.md" && ! grep -q 'xhigh' "$tmp"/orch-*.md; check "no agent runs at xhigh; the adversarial reviewer is high" $?
grep -q '^maxTurns: 80$' "$tmp/orch-design-gate.md" && grep -q '^model: claude-opus-5-5$' "$tmp/orch-design-gate.md"; check "the design gate is Opus, 80 turns" $?
! grep -q -E 'Run the relevant tests|Read the callers of every|Read a doc in full|Read the real modules|and the code it calls' "$tmp"/orch-*.md; check "the B7 reading and running sentences are gone" $?
grep -q 'Call graft only for a symbol they do' "$tmp/orch-implementer.md"; check "the implementer's Method 1 is the replacement" $?
cp "$tmp/orch-implementer.md" "$tmp/before.md"; python3 "$PA" "$tmp" --write > /dev/null
cmp -s "$tmp/before.md" "$tmp/orch-implementer.md"; check "running the patch twice changes nothing" $?

echo "passed $pass, failed $fail"
[ "$fail" -eq 0 ]
