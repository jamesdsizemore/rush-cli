#!/usr/bin/env bash
# usage: disk-clean.sh <min_mb> <run-start-epoch> [--yes]
# Lists, and with --yes removes, run-owned temp directories: a direct child of $TMPDIR named tmp*
# (never $TMPDIR itself), created after the run started, at least <min_mb> large, with no file written
# in the last 30 minutes anywhere beneath it, no open handle beneath it, and no keep/ directory beneath it.
# Never touches pytest-of-*, worktrees or ~/.cache. Each removal is logged; without --yes nothing is removed.
set -euo pipefail
min="${1:-100}"; start="${2:?run start epoch}"; yes="${3:-}"
root="${TMPDIR:-/tmp}"
for d in "$root"/tmp*; do
  [ -d "$d" ] && [ ! -L "$d" ] || continue
  [ "$(stat -f %B "$d" 2>/dev/null || stat -c %W "$d")" -ge "$start" ] || { echo "disk-clean: skip $d (older than the run)"; continue; }
  [ -z "$(find "$d" -type f -mmin -30 -print -quit)" ] || { echo "disk-clean: skip $d (written in the last 30 minutes)"; continue; }
  [ -z "$(find "$d" -type d -name keep -print -quit)" ] || { echo "disk-clean: skip $d (holds keep/)"; continue; }
  [ -z "$(lsof -t +D "$d" 2>/dev/null | head -1)" ] || { echo "disk-clean: skip $d (open handle)"; continue; }
  mb="$(du -sm "$d" | cut -f1)"
  [ "$mb" -ge "$min" ] || continue
  if [ "$yes" = "--yes" ]; then echo "disk-clean: removed $d ${mb}MB"; rm -rf "$d"; else echo "disk-clean: would remove $d ${mb}MB"; fi
done
