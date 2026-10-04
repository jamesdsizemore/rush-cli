#!/usr/bin/env bash
# Runs each command in <run>/.orchestrator/gate.cmds in order, recording each exit code separately (no pipes
# into tail/head, so no exit code is masked). One gate run at a time on the machine (a lock under $TMPDIR, not
# under the run directory, so two worktrees cannot run suites together). Sets RUSH_GATE=1 so the conftest full-run
# guard allows the full suite, exports RUSH_GATE_BT (a basetemp unique to this invocation) for the pytest command,
# removes that basetemp when every command passes and keeps it, recorded in gate-keep, when one fails. Appends one
# row per pytest command to suite-times.tsv: time, wall seconds, passed count, agents running, exit code.
# On all-zero, writes .orchestrator/gate-ok = HEAD. Otherwise removes gate-ok and exits 1.
set -uo pipefail

run="${1:?usage: gate.sh <run-dir>}"
state_dir="$run/.orchestrator"
cmds_file="$state_dir/gate.cmds"
summary="$state_dir/gate-log"
times="$state_dir/suite-times.tsv"
keep="$state_dir/gate-keep"
lock="${TMPDIR:-/tmp}/rush-gate.lock"

[ -f "$cmds_file" ] || { echo "no gate.cmds at $cmds_file" >&2; exit 2; }
if ! mkdir "$lock" 2>/dev/null; then
  owner="$(cat "$lock/pid" 2>/dev/null || true)"
  if [ -n "$owner" ] && kill -0 "$owner" 2>/dev/null; then
    echo "a gate run is active (pid $owner, lock $lock)" >&2; exit 3
  fi
  rm -rf "$lock"; mkdir "$lock" 2>/dev/null || { echo "a gate run is active: $lock" >&2; exit 3; }
fi
echo $$ > "$lock/pid"
trap 'rm -rf "$lock"' EXIT
export RUSH_GATE=1
export RUSH_GATE_BT="${TMPDIR:-/tmp}/rush-gate-bt-$$"
[ -f "$keep" ] && { while IFS= read -r old; do [ -n "$old" ] && rm -rf "$old"; done < "$keep"; rm -f "$keep"; }

: > "$summary"
ok=1
while IFS= read -r cmd || [ -n "$cmd" ]; do
  [ -z "$cmd" ] && continue
  start="$(date +%s)"
  ( cd "$run" && bash -c "$cmd" )
  code=$?
  wall=$(( $(date +%s) - start ))
  echo "$code $cmd" >> "$summary"
  case "$cmd" in
    *pytest*)
      log="$(printf '%s' "$cmd" | sed -n 's/.*> *\([^ ]*\) 2>&1.*/\1/p')"
      passed="$( [ -n "$log" ] && grep -Eo '[0-9]+ passed' "$run/$log" 2>/dev/null | tail -1 | grep -Eo '[0-9]+' || true )"
      # Zero-skip rule (SKILL.md rule 2): a pytest run that reports skipped or xfailed tests fails the gate, and a
      # pytest command that does not redirect its output to a log cannot be checked, so it fails too.
      skipped="$( [ -n "$log" ] && grep -Eo '[0-9]+ (skipped|xfailed)' "$run/$log" 2>/dev/null | tail -1 || true )"
      if [ "$code" -eq 0 ] && [ -z "$log" ]; then code=98; echo "98 pytest command has no '> log 2>&1' redirect, so the zero-skip rule cannot read it: $cmd" >> "$summary"; fi
      if [ "$code" -eq 0 ] && [ -n "$skipped" ]; then code=97; echo "97 zero-skip rule: pytest reported $skipped" >> "$summary"; fi
      agents="$(grep -c . "$state_dir/agents.active" 2>/dev/null || true)"
      printf '%s\t%s\t%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$wall" "${passed:-0}" "${agents:-0}" "$code" >> "$times"
      ;;
  esac
  [ "$code" -eq 0 ] || ok=0
done < "$cmds_file"

if [ "$ok" -eq 1 ]; then
  rm -rf "$RUSH_GATE_BT"
  git -C "$run" rev-parse HEAD > "$state_dir/gate-ok"
  echo "gate ok"
else
  [ -d "$RUSH_GATE_BT" ] && echo "$RUSH_GATE_BT" > "$keep" && echo "kept for the failure: $RUSH_GATE_BT" >> "$summary"
  rm -f "$state_dir/gate-ok"
  echo "gate failed, see $summary" >&2
  exit 1
fi
