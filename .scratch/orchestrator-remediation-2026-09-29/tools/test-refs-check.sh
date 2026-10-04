#!/usr/bin/env bash
# Plan J17/J23: refs-check.sh catches the broken references found while editing this document: a decision that
# does not exist (D5), a line number past the end of the file, a missing test file, a missing X section.
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
chk="$here/refs-check.sh"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
pass=0 fail=0
check() { if [ "$2" -eq 0 ]; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL: $1"; fi; }
hdr='# t\n\n## 0. The ask, verbatim\n\n> Fix it.\n\n## 5. Decisions\n\n| ID | Decision | Basis |\n|---|---|---|\n| D1 | a | b |\n\n## 8. Edits\n\n### X1. one\n\n'

printf "$hdr"'See Decision D1, X1, `doc-done-check.sh:3` and `test-doc-done-check.sh`.\n' > "$tmp/ok.md"
out="$(bash "$chk" "$tmp/ok.md")"; [ $? -eq 0 ] && [[ "$out" == "REFS-CHECK PASS" ]]; check "resolving references pass" $?

printf "$hdr"'The limit is Decision D5.\n' > "$tmp/d5.md"
out="$(bash "$chk" "$tmp/d5.md")"; [ $? -eq 1 ] && [[ "$out" == *"Decision D5 is not a row"* ]]; check "a decision that does not exist is named" $?

printf "$hdr"'See `doc-done-check.sh:9999`.\n' > "$tmp/line.md"
out="$(bash "$chk" "$tmp/line.md")"; [ $? -eq 1 ] && [[ "$out" == *"past the end"* ]]; check "a line past the end of the file is named" $?

printf "$hdr"'See `nofile-zz.sh:3`.\n' > "$tmp/file.md"
out="$(bash "$chk" "$tmp/file.md")"; [ $? -eq 1 ] && [[ "$out" == *"does not exist under the roots"* ]]; check "a missing file is named" $?

printf "$hdr"'Run `test-nope-zz.sh`.\n' > "$tmp/test.md"
out="$(bash "$chk" "$tmp/test.md")"; [ $? -eq 1 ] && [[ "$out" == *"test file test-nope-zz.sh does not exist"* ]]; check "a missing test file is named" $?

printf "$hdr"'See X9 for the rest.\n' > "$tmp/x.md"
out="$(bash "$chk" "$tmp/x.md")"; [ $? -eq 1 ] && [[ "$out" == *"X9 is not a section heading"* ]]; check "a missing X section is named" $?

printf "$hdr"'```\nsee `nofile-zz.sh:3` and D7\n```\n' > "$tmp/fence.md"
bash "$chk" "$tmp/fence.md" > /dev/null; [ $? -eq 0 ]; check "references inside a code fence are not checked" $?

bash "$chk" "$tmp/none.md" > /dev/null 2>&1; [ $? -eq 2 ]; check "a missing document exits 2" $?

echo "passed $pass, failed $fail"
[ "$fail" -eq 0 ]
