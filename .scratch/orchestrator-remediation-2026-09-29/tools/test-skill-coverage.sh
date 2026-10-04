#!/usr/bin/env bash
# Plan J22/F31: coverage is exact path + sha256 + span. A file name mentioned in a doc is not review.
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
sc="$here/skill-coverage.sh"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
pass=0 fail=0
check() { if [ "$2" -eq 0 ]; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL: $1"; fi; }
export REVIEW_LEDGER="$tmp/reviewed.tsv" SKILL_DIR="$tmp/skill" USER_AGENTS="$tmp/uagents" REPO_AGENTS="$tmp/ragents"
mkdir -p "$tmp/skill/scripts" "$tmp/uagents" "$tmp/ragents"
printf 'a\nb\nc\n' > "$tmp/skill/scripts/monitor.py"
printf 'a\nb\n' > "$tmp/uagents/orch-scout.md"
printf 'x\ny\n' > "$tmp/ragents/orch-scout.md"     # same basename, different file

out="$(bash "$sc" list)"
[ "$(echo "$out" | grep -c '^UNREVIEWED')" = 3 ]; check "nothing marked: three files, all UNREVIEWED (the two orch-scout.md are separate rows)" $?

bash "$sc" mark "$tmp/skill/scripts/monitor.py" 1-2 > /dev/null
out="$(bash "$sc" list)"; echo "$out" | grep -q "^UNREVIEWED.*monitor.py"; check "a partial span is not review" $?
bash "$sc" mark "$tmp/skill/scripts/monitor.py" 3-3 > /dev/null
out="$(bash "$sc" list)"; echo "$out" | grep -q "^REVIEWED.*monitor.py"; check "spans that cover every line make it REVIEWED" $?

bash "$sc" mark "$tmp/uagents/orch-scout.md" 1-2 > /dev/null
out="$(bash "$sc" list)"
echo "$out" | grep "^REVIEWED" | grep -q "uagents/orch-scout.md" && echo "$out" | grep "^UNREVIEWED" | grep -q "ragents/orch-scout.md"; check "reviewing the user-level copy does not cover the repo-level copy with the same name" $?

echo more >> "$tmp/skill/scripts/monitor.py"
out="$(bash "$sc" list)"; echo "$out" | grep -q "^STALE.*monitor.py"; check "a changed file is STALE, not REVIEWED" $?

bash "$sc" list --require > /dev/null; [ $? -eq 1 ]; check "--require exits 1 while any file is not REVIEWED" $?
bash "$sc" mark "$tmp/skill/scripts/monitor.py" 1-9 > /dev/null 2>&1; [ $? -eq 2 ]; check "a span outside the file is refused" $?
bash "$sc" mark "$tmp/skill/scripts/nope.py" 1-1 > /dev/null 2>&1; [ $? -eq 2 ]; check "a path that is not a file is refused" $?

echo "passed $pass, failed $fail"
[ "$fail" -eq 0 ]
