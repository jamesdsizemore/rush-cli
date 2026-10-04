#!/usr/bin/env bash
# Plan G2/I1-I4/F4: the skill's text points at scripts that exist, no longer mentions what the plan removed,
# and every absolute rule and red flag carries an [enforced: ...] tag naming a real script, alert or hook.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S="$here/SKILL.md"; D="$here/references/dispatch.md"
pass=0 fail=0
check() { if [ "$2" -eq 0 ]; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL: $1"; fi; }

for f in "$S" "$D"; do
  for s in $(grep -oE 'scripts/[A-Za-z0-9_.-]+\.(sh|py)' "$f" | sort -u); do
    [ -f "$here/$s" ]; check "$(basename "$f") names $s and it exists" $?
  done
done
for gone in '--budget' 'Context budget' '/compact' 'fix plan applies now' 'xhigh' 'budget per role' 'Budget per role'; do
  ! grep -qF -- "$gone" "$S" "$D"; check "no mention of: $gone" $?
done
HOOKS="ask-guard.js prose-question-stop.js resume-guard.js taskstop-guard.js orchestrator-model-guard.js"
tags="$(grep -oE '\[enforced: [^]]*\]' "$S" | wc -l | tr -d ' ')"
rules="$(awk '/^## Absolute rules/{a=1;next} /^## Correction/{a=0} a && /^[0-9]\. \*\*/' "$S" | wc -l | tr -d ' ')"
flags="$(awk '/^## Red flags/{a=1;next} a && /^- /' "$S" | wc -l | tr -d ' ')"
[ "$tags" -ge $((rules + flags)) ]; check "each of the $rules absolute rules and $flags red flags has an enforced tag ($tags tags)" $?
# every token inside a tag is a script in scripts/, a known hook, a monitor alert, a guard clause or a test-suite file
tagfile="$(mktemp)"; trap 'rm -f "$tagfile"' EXIT
grep -oE '\[enforced: [^]]*\]' "$S" | grep -oE '`[^`]+`' | tr -d '`' | sort -u > "$tagfile"
while IFS= read -r tok; do
  first="${tok%% *}"; base="${first##*/}"
  case " $HOOKS " in *" $base "*) continue ;; esac
  [ -f "$here/scripts/$base" ] && continue
  case "$base" in *.sh|*.py|*.js) ;; *) continue ;; esac     # only script and hook names are checked
  echo "unrecognised tag token: $tok"; false; check "tag token $tok is a script, hook or alert" $?
done < "$tagfile"
# A tag that names a file only shows the file exists. Each named script or hook must also be exercised by a test.
while IFS= read -r tok; do
  first="${tok%% *}"; base="${first##*/}"
  case "$base" in *.sh|*.py|*.js) ;; *) continue ;; esac
  grep -rqF -- "$base" "$here/tests" "$here/../hooks/test-hooks.js" "$HOME/.claude/hooks/test-hooks.js" 2>/dev/null; check "tag token $base is named by a test" $?
done < "$tagfile"
grep -q 'orch-design-gate' "$S" && grep -q 'save-map.sh' "$S" && grep -q 'task-gate.sh' "$S"; check "the packet factory and the task gate are in the skill" $?
[ "$(grep -c '^## ' "$S")" -ge 12 ]; check "the skill still has its sections" $?

echo "passed $pass, failed $fail"
[ "$fail" -eq 0 ]
