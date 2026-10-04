#!/usr/bin/env bash
# Fixture test for decisions.sh: pattern matches every member of its class,
# `pending` excludes members already marked applied.
set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../scripts" && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

git -C "$tmp" init -q
git -C "$tmp" config user.email test@test.com
git -C "$tmp" config user.name test

echo "OLD_PATTERN one" > "$tmp/a.txt"
echo "OLD_PATTERN two" > "$tmp/b.txt"
echo "unrelated" > "$tmp/c.txt"
git -C "$tmp" add -A
git -C "$tmp" commit -q -m init

cd "$tmp"
fail=0

"$SCRIPTS_DIR/decisions.sh" add D1 "OLD_PATTERN" "rename to NEW_PATTERN"
out="$("$SCRIPTS_DIR/decisions.sh" pending)"
[[ "$out" == *"D1 a.txt"* ]] || { echo "FAIL: expected D1 a.txt pending, got: $out"; fail=1; }
[[ "$out" == *"D1 b.txt"* ]] || { echo "FAIL: expected D1 b.txt pending, got: $out"; fail=1; }
[[ "$out" == *"c.txt"* ]] && { echo "FAIL: c.txt should not match pattern"; fail=1; }

"$SCRIPTS_DIR/decisions.sh" applied D1 a.txt
out="$("$SCRIPTS_DIR/decisions.sh" pending)"
[[ "$out" == *"D1 a.txt"* ]] && { echo "FAIL: D1 a.txt should be excluded once applied"; fail=1; }
[[ "$out" == *"D1 b.txt"* ]] || { echo "FAIL: D1 b.txt should still be pending"; fail=1; }

if [ "$fail" -eq 0 ]; then
  echo "test_decisions.sh: PASS"
else
  echo "test_decisions.sh: FAIL"
  exit 1
fi
