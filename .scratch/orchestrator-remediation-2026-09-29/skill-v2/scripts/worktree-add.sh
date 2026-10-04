#!/usr/bin/env bash
# usage: worktree-add.sh <task-id>          (run from the phase worktree, the run's root)
# Adds a sibling worktree <parent of the phase worktree>/phase-<id>-<task> on branch phase/<id>-<task>, cut from the
# phase branch; refuses below 8 GiB free. No per-worktree environment: tests use the interpreter recorded in
# run.json (the shared virtual environment) with PYTHONPATH=<worktree>/src. Prints the new worktree path.
set -euo pipefail
task="${1:?usage: worktree-add.sh <task-id>}"
root="$(git rev-parse --show-toplevel)"
run="$root/.orchestrator/run.json"
[ -f "$run" ] || { echo "no active run at $run" >&2; exit 1; }
phase="$(jq -r .phase "$run")"
free="$(df -g "$root" | awk 'NR==2{print $4}')"
[ "$free" -ge 8 ] || { echo "refusing: ${free} GiB free (need 8)" >&2; exit 1; }
wt="$(dirname "$root")/phase-$phase-$task"
git worktree add -b "phase/$phase-$task" "$wt" "$(jq -r .branch "$run")" >&2
echo "$wt"
