#!/usr/bin/env bash
# hook-dry-run.sh <draft-file> <target-doc>
# Feeds the draft text to the two doc-write hooks in the JSON shape a real Edit would send,
# BEFORE the Edit. This runs your hooks; it never replaces them. Exit 0 = both would allow.
set -u
draft="${1:?draft file}"; doc="${2:?target doc}"; rc=0
for h in unverified-negative-claim-guard.sh coverage-denominator-guard.sh; do
  out=$(jq -n --arg f "$doc" --rawfile s "$draft" \
        '{tool_name:"Edit",tool_input:{file_path:$f,old_string:"x",new_string:$s}}' \
        | bash "$HOME/.claude/hooks/$h" 2>&1); code=$?
  if [ "$code" != 0 ]; then rc=1; echo "BLOCK $h (exit $code)"; echo "$out" | sed -n '1,6p'; else echo "ALLOW $h"; fi
done
exit $rc
