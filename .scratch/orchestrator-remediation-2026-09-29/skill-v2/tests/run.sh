#!/usr/bin/env bash
# Runs every orchestrator script fixture test. One command, no network.
set -uo pipefail
dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fail=0

for t in "$dir"/test[-_]*.sh; do
  echo "== $t =="
  bash "$t" || fail=1
done

for t in "$dir"/test_*.py; do
  echo "== $t =="
  python3 "$t" || fail=1
done

if [ "$fail" -eq 0 ]; then
  echo "ALL PASS"
else
  echo "SOME FAILED"
fi
exit "$fail"
