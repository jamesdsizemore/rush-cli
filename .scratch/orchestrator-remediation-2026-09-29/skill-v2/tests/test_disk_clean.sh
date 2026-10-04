#!/usr/bin/env bash
# Plan D2/J21/F1: disk-clean.sh is a dry run unless --yes, and it skips a directory the run does not own (created
# before the run started), one written to in the last 30 minutes, one that holds keep/, one with an open handle,
# and a symlink. Fixtures live under a private TMPDIR that the test removes.
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
dc="$here/../scripts/disk-clean.sh"
root="$(mktemp -d)"; bg=""
cleanup() { [ -z "$bg" ] || kill "$bg" 2>/dev/null; rm -rf "$root"; }
trap cleanup EXIT
export TMPDIR="$root"
pass=0 fail=0
check() { if [ "$2" -eq 0 ]; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL: $1"; fi; }
mk() { mkdir -p "$root/$1"; dd if=/dev/zero of="$root/$1/blob" bs=1024 count=2048 2> /dev/null; touch -t 200101010101 "$root/$1/blob" "$root/$1"; }

mk tmpAged
out="$(bash "$dc" 1 0)"; [[ "$out" == *"would remove $root/tmpAged"* ]] && [ -d "$root/tmpAged" ]; check "a dry run names the aged directory and keeps it" $?
out="$(bash "$dc" 1 0 --yes)"; [[ "$out" == *"removed $root/tmpAged"* ]] && [ ! -d "$root/tmpAged" ]; check "--yes removes an aged directory the run owns" $?

mk tmpOld
out="$(bash "$dc" 1 "$(( $(date +%s) + 1000 ))" --yes)"; [[ "$out" == *"older than the run"* ]] && [ -d "$root/tmpOld" ]; check "a directory created before the run started is kept" $?

mkdir -p "$root/tmpFresh"; dd if=/dev/zero of="$root/tmpFresh/blob" bs=1024 count=2048 2> /dev/null
out="$(bash "$dc" 1 0 --yes)"; [[ "$out" == *"written in the last 30 minutes"* ]] && [ -d "$root/tmpFresh" ]; check "a directory written to in the last 30 minutes is kept" $?

mk tmpKeep; mkdir "$root/tmpKeep/keep"
out="$(bash "$dc" 1 0 --yes)"; [[ "$out" == *"holds keep/"* ]] && [ -d "$root/tmpKeep" ]; check "a directory holding keep/ is kept" $?

mk tmpOpen; sleep 60 < "$root/tmpOpen/blob" & bg=$!
sleep 1
out="$(bash "$dc" 1 0 --yes)"; [[ "$out" == *"open handle"* ]] && [ -d "$root/tmpOpen" ]; check "a directory with an open handle is kept" $?
kill "$bg" 2>/dev/null; bg=""

mk tmpTarget; ln -s "$root/tmpTarget" "$root/tmpLink"
bash "$dc" 1 0 --yes > /dev/null; [ -L "$root/tmpLink" ]; check "a symlink is never followed or removed" $?

rm -rf "$root"/tmp*; mk tmpSmall
out="$(bash "$dc" 100 0 --yes)"; [ -d "$root/tmpSmall" ] && [[ "$out" != *"removed"* ]]; check "a directory under the size threshold is kept" $?

echo "passed $pass, failed $fail"
[ "$fail" -eq 0 ]
