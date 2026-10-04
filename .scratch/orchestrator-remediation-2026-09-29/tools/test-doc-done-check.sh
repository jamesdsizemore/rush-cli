#!/usr/bin/env bash
# Plan J2/F30: doc-done-check.sh is structural lint. Negative fixtures from the Codex review:
# a fix that names a file that does not exist fails, a missing document fails, an empty one fails.
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
chk="$here/doc-done-check.sh"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
pass=0 fail=0
check() { if [ "$2" -eq 0 ]; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL: $1"; fi; }

printf '# t\n\n## 4. x\n\n#### A1. real\n\n**Fix.** Run `doc-done-check.sh` before saying done.\n' > "$tmp/ok.md"
out="$(bash "$chk" "$tmp/ok.md")"; [ $? -eq 0 ] && [[ "$out" == "DOC-DONE-CHECK PASS 1 entries"* ]]; check "an entry naming an existing script passes" $?

printf '# t\n\n#### A1. fake\n\n**Fix.** Think about `does-not-exist.sh`.\n' > "$tmp/fake.md"
out="$(bash "$chk" "$tmp/fake.md")"; [ $? -eq 1 ] && [[ "$out" == *"NO-ARTIFACT A1"* ]]; check "a fix naming a file that does not exist fails" $?

printf '# t\n\n#### A1. prose\n\n**Fix.** Be more careful next time.\n' > "$tmp/prose.md"
out="$(bash "$chk" "$tmp/prose.md")"; [ $? -eq 1 ] && [[ "$out" == *"NO-ARTIFACT A1"* ]]; check "a prose fix with no backticked name fails" $?

printf '# t\n\n#### A1. nofix\n\nEvidence only.\n' > "$tmp/nofix.md"
out="$(bash "$chk" "$tmp/nofix.md")"; [ $? -eq 1 ] && [[ "$out" == *"NO-FIX A1"* ]]; check "an entry with no Fix marker fails" $?

bash "$chk" "$tmp/missing.md" > /dev/null 2>&1; [ $? -eq 2 ]; check "a missing document exits 2, not a pass" $?
: > "$tmp/empty.md"; bash "$chk" "$tmp/empty.md" > /dev/null 2>&1; [ $? -eq 2 ]; check "an empty document exits 2" $?
printf '# t\n\nno entries here\n' > "$tmp/none.md"; bash "$chk" "$tmp/none.md" > /dev/null 2>&1; [ $? -eq 2 ]; check "a document with no entries exits 2" $?

printf '# t\n\n#### A1. real\n\n**Fix.** Run `doc-done-check.sh`. TBD later.\n' > "$tmp/ban.md"
out="$(bash "$chk" "$tmp/ban.md")"; [ $? -eq 1 ] && [[ "$out" == *"BANNED"* ]]; check "a banned placeholder fails" $?

echo "passed $pass, failed $fail"
[ "$fail" -eq 0 ]
