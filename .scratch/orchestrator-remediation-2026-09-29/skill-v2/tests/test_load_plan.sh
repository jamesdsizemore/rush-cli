#!/usr/bin/env bash
# Plan C1/F13/F14: load-plan.py builds the graph, records the shared files each task holds, refuses to
# overwrite run state, keeps statuses with --keep and migrates merged nodes from git.
set -uo pipefail
LP="$(cd "$(dirname "${BASH_SOURCE[0]}")/../scripts" && pwd)/load-plan.py"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
pass=0 fail=0
check() { if [ "$2" -eq 0 ]; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL: $1"; fi; }
repo="$tmp/repo"; mkdir -p "$repo"
git -C "$repo" init -q; git -C "$repo" config user.email t@t; git -C "$repo" config user.name t
cat > "$repo/plan.md" <<'EOF'
One writer at a time for `cli.py`, `mcp.py`, shared tests, and documentation. Parallel agents may audit.

Execution order:
T1 → T2
T3

#### T1 — a
**Deliverables:** `src/x/cli.py`
#### T2 — b
**Deliverables:** `src/x/mcp.py`, `src/x/other.py`
#### T3 — c
**Deliverables:** `src/x/cli.py`, `src/x/my_cli.py`
EOF
git -C "$repo" add plan.md; git -C "$repo" commit -q -m init
T="$tmp/tasks.tsv"
python3 "$LP" "$repo/plan.md" "$T" > /dev/null; check "fresh load succeeds" $?
[ "$(awk -F'\t' '$1=="T1"{print $2"|"$3"|"$4}' "$T")" = "|pending|cli.py" ]; check "T1: no deps, pending, holds cli.py" $?
[ "$(awk -F'\t' '$1=="T2"{print $2"|"$3"|"$4}' "$T")" = "T1|pending|mcp.py" ]; check "T2: depends on T1, holds mcp.py only (other.py is not shared)" $?
[ "$(awk -F'\t' '$1=="T3"{print $4}' "$T")" = "cli.py" ]; check "T3: my_cli.py does not count as cli.py" $?
python3 "$LP" "$repo/plan.md" "$T" > /dev/null 2>&1; [ $? -eq 1 ]; check "a second load without --keep refuses to overwrite" $?
awk -F'\t' 'BEGIN{OFS="\t"} $1=="T1"{$3="merged"} {print}' "$T" > "$T.x" && mv "$T.x" "$T"
printf 'T2.a\t\trunning\tmcp.py\n' >> "$T"
python3 "$LP" "$repo/plan.md" "$T" --keep > /dev/null; check "--keep succeeds" $?
[ "$(awk -F'\t' '$1=="T1"{print $3}' "$T")" = merged ]; check "--keep keeps a merged status" $?
grep -q '^T2.a' "$T"; check "--keep keeps a split child row that is not a plan heading" $?
rm -f "$T"
git -C "$repo" commit -q --allow-empty -m "Merge branch 'phase/p1-t1' into phase/p1"
git -C "$repo" commit -q --allow-empty -m "feat(x): T3 summary"
python3 "$LP" "$repo/plan.md" "$T" --merged-from-git "HEAD~2..HEAD" > /dev/null; check "--merged-from-git runs" $?
[ "$(awk -F'\t' '$1=="T1"{print $3}' "$T")" = merged ]; check "a first-parent Merge subject naming T1 marks it merged" $?
[ "$(awk -F'\t' '$1=="T3"{print $3}' "$T")" = pending ]; check "a plain commit subject naming T3 does not" $?

echo "passed $pass, failed $fail"
[ "$fail" -eq 0 ]
