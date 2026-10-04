#!/usr/bin/env bash
# Plan H13/J1: ledger-check.sh fixtures. A dropped sentence, a made-up entry, an open row, a paraphrase and a
# missing ledger are all caught.
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
chk="$here/ledger-check.sh"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
pass=0 fail=0
check() { if [ "$2" -eq 0 ]; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL: $1"; fi; }

mk() { # $1 file, $2 row2 quote, $3 row2 entries, $4 row2 status
  cat > "$1" <<EOF
# t

## 0. The ask, verbatim

> Fix the skill. Research every claim. Do not code.

### 0.1 Requirement ledger

| ID | Quote | Entries | Check | Status |
|---|---|---|---|---|
| R01 | Fix the skill. | A1 | run.sh | done |
| R02 | $2 | $3 | grep | $4 |

## 4. Issues

#### A1. one

**Fix.** \`run.sh\`.
EOF
}
mk "$tmp/ok.md" "Research every claim. Do not code." "A1" done
out="$(bash "$chk" "$tmp/ok.md")"; [ $? -eq 0 ] && [[ "$out" == "LEDGER-CHECK PASS 3 sentences, 2 rows" ]]; check "a complete ledger passes" $?

mk "$tmp/drop.md" "Research every claim." "A1" done
out="$(bash "$chk" "$tmp/drop.md")"; [ $? -eq 1 ] && [[ "$out" == *"MISSING sentence 3: Do not code."* ]]; check "a dropped sentence is named" $?

mk "$tmp/para.md" "Verify each claim. Do not code." "A1" done
out="$(bash "$chk" "$tmp/para.md")"; [ $? -eq 1 ] && [[ "$out" == *"MISSING sentence 2"* ]] && [[ "$out" == *"not in the ask"* ]]; check "a paraphrase is missing the real sentence and quotes text that is not in the ask" $?

mk "$tmp/ent.md" "Research every claim. Do not code." "Z9" done
out="$(bash "$chk" "$tmp/ent.md")"; [ $? -eq 1 ] && [[ "$out" == *"R02 names 'Z9'"* ]]; check "an entry that is not a heading is refused" $?

mk "$tmp/open.md" "Research every claim. Do not code." "A1" open
out="$(bash "$chk" "$tmp/open.md")"; [ $? -eq 1 ] && [[ "$out" == *"OPEN 1 ledger rows"* ]]; check "an open row fails" $?

printf '# t\n\n## 0. The ask, verbatim\n\n> Fix it.\n' > "$tmp/noledger.md"
bash "$chk" "$tmp/noledger.md" > /dev/null 2>&1; [ $? -eq 2 ]; check "a document with no ledger exits 2" $?
bash "$chk" "$tmp/none.md" > /dev/null 2>&1; [ $? -eq 2 ]; check "a missing document exits 2" $?

echo "passed $pass, failed $fail"
[ "$fail" -eq 0 ]
