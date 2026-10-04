#!/usr/bin/env bash
# Owner-decision ledger: each decision carries a grep pattern that finds
# every member of its class. `pending` lists members not yet marked applied.
set -euo pipefail

root="$(git rev-parse --show-toplevel)"
state_dir="$root/.orchestrator"
decisions="$state_dir/decisions.tsv"
applied="$state_dir/decisions-applied.tsv"
mkdir -p "$state_dir"
touch "$decisions" "$applied"

case "${1:-}" in
  add)
    [ $# -ge 4 ] || { echo "usage: decisions.sh add <id> <pattern> <decision text>" >&2; exit 2; }
    id="$2"; pattern="$3"; shift 3
    printf '%s\t%s\t%s\n' "$id" "$pattern" "$*" >> "$decisions"
    ;;
  applied)
    [ $# -eq 3 ] || { echo "usage: decisions.sh applied <id> <path>" >&2; exit 2; }
    printf '%s\t%s\n' "$2" "$3" >> "$applied"
    ;;
  pending)
    while IFS=$'\t' read -r id pattern _rest || [ -n "$id" ]; do
      [ -z "$id" ] && continue
      while IFS= read -r f; do
        [ -z "$f" ] && continue
        if ! grep -qF "$(printf '%s\t%s' "$id" "$f")" "$applied"; then
          echo "$id $f"
        fi
      done < <(git -C "$root" grep -lE "$pattern" -- . 2>/dev/null || true)
    done < "$decisions"
    ;;
  *)
    echo "usage: decisions.sh add <id> <pattern> <text> | applied <id> <path> | pending" >&2
    exit 2
    ;;
esac
