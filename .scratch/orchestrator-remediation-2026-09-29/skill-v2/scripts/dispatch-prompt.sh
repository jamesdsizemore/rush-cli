#!/usr/bin/env bash
# Build an orch-* dispatch prompt from the fixed template (fix plan F6, F19, F22, F24).
#   dispatch-prompt.sh --role R --task ID --worktree W --map MAPFILE [--mode tests|impl] [--spec FILE:A-B ...]
# MAPFILE is the orchestrator's checked research for this dispatch:
#   write: <path>                     a write target (required for implementer)
#   change: <path:line> <change>      one exact change (required for implementer, impl mode)
#   test: <test id>                   one exact test id (required for implementer, impl mode)
#   done: <fact>                      one checkable done item (required for implementer, both modes)
#   scout: <agent id>                 the scout that mapped this packet (required for implementer only;
#                                     scout, planner, verifier, reviewer, adversarial-reviewer and docs are exempt)
#   model: / model-reason: <file:line> a model other than the role default needs the reason
# --mode tests (implementer only): the test-authoring dispatch; write: lines must all be under tests/,
#   no --red-log yet. --mode impl (default) needs the --red-log that test-acceptance.py accepted.
#   any other line                    code map / role inputs, copied verbatim
# Refuses (exit 2) when MAPFILE is missing or cites no path:line entry.
# The last line is `<!-- dispatch-prompt v1 sha256:H -->`, where H is the sha256 of every
# byte printed before that line.
set -euo pipefail

die() { echo "dispatch-prompt: $*" >&2; exit 2; }

role="" task="" wt="" map="" maxturns="" default_model="" mode="impl" testcmd=""
specs=()
while [ $# -gt 0 ]; do
  [ $# -ge 2 ] || die "missing value for $1"
  case "$1" in
    --role) role="${2#orch-}" ;;
    --task) task="$2" ;;
    --worktree) wt="$2" ;;
    --map) map="$2" ;;
    --mode) mode="$2" ;;
    --spec) specs+=("$2") ;;
    --test-cmd) testcmd="$2" ;;
    --red-log) redlog="$2" ;;
    --review-of) reviewof="$2" ;;
    *) die "unknown argument: $1" ;;
  esac
  shift 2
done

case "$role" in
  scout|design-gate|planner|implementer|verifier|reviewer|adversarial-reviewer|docs) ;;
  *) die "--role must be one of scout design-gate planner implementer verifier reviewer adversarial-reviewer docs" ;;
esac
[ -n "$task" ] || die "--task is required"
case "$role" in
  implementer|verifier) [ -n "$testcmd" ] || die "--test-cmd is required for role $role" ;;
esac
case "$role" in
  implementer|reviewer|adversarial-reviewer|planner|design-gate)
    [ ${#specs[@]} -gt 0 ] || die "--spec is required for role $role" ;;
esac
[[ "$wt" = /* ]] && [ -d "$wt" ] || die "--worktree must be an existing absolute directory"
# The prompt tells the agent to use graft in $wt, so the index must exist there.
if [ ! -d "$wt/graft" ] && [ -z "${DISPATCH_PROMPT_NO_GRAFT_BUILD:-}" ]; then
  (cd "$wt" && graft build >/dev/null 2>&1) || die "graft build failed in $wt"
fi
case "$mode" in impl|tests) ;; *) die "--mode must be impl or tests" ;; esac
[ "$mode" = impl ] || [ "$role" = implementer ] || die "--mode tests applies to role implementer only"
[ -f "$map" ] || die "map file not found: $map"
grep -qE '[A-Za-z0-9_.-]*[./][A-Za-z0-9_./-]*:[0-9]+' "$map" || die "map has no path:line entries: $map"
case "$role" in
  implementer) maxturns=100; default_model=sonnet ;;
  docs) maxturns=135; default_model=sonnet ;;
  reviewer) maxturns=80; default_model=opus ;;
  planner) maxturns=55; default_model=opus ;;
  adversarial-reviewer) maxturns=240; default_model=opus ;;
  design-gate) maxturns=80; default_model=opus ;;
  scout) maxturns=60; default_model=haiku ;;
  verifier) maxturns=30; default_model=haiku ;;
esac
map_model="$(sed -n 's/^model:[[:space:]]*//p' "$map" | head -1)"
map_reason="$(sed -n 's/^model-reason:[[:space:]]*//p' "$map" | head -1)"
if [ -n "$map_model" ] && [ "$map_model" != "$default_model" ]; then
  [[ "$map_reason" =~ [A-Za-z0-9_./-]+:[0-9]+ ]] \
    || die "model $map_model differs from the $role default ($default_model): add 'model-reason: <file:line of the brief's trust-boundary checklist>' to the map"
fi
for s in ${specs[@]+"${specs[@]}"}; do
  [[ "$s" =~ ^.+:[0-9]+-[0-9]+$ ]] || die "--spec must be FILE:A-B, got: $s"
done

# Two review rounds per task, never a third (F30). One worktree is one task.
# After round 2 the orchestrator fixes what is left itself, to green.
if [ "$role" = reviewer ]; then
  [ -n "${reviewof:-}" ] || die "--review-of TASK is required for role reviewer (the task under review)"
  [[ "$reviewof" =~ ^[A-Za-z0-9._-]+$ ]] || die "--review-of must be a plain task id"
  rounds_file="$wt/.orchestrator/review-rounds-$reviewof"
  rounds="$(cat "$rounds_file" 2>/dev/null || echo 0)"
  [[ "$rounds" =~ ^[0-9]+$ ]] || die "unreadable review count in $rounds_file"
  [ "$rounds" -lt 2 ] || die "review cap reached for task $reviewof ($rounds rounds): fix the remaining findings yourself and verify with the full suite, lint and typecheck; no third review"
  mkdir -p "$wt/.orchestrator" && echo $((rounds + 1)) > "$rounds_file"
fi

writes="$(sed -n 's/^write:[[:space:]]*//p' "$map")"
changes="$(sed -n 's/^change:[[:space:]]*//p' "$map")"
tests="$(sed -n 's/^test:[[:space:]]*//p' "$map")"
keeps="$(sed -n 's/^keep:[[:space:]]*//p' "$map")"
scouts="$(sed -n 's/^scout:[[:space:]]*//p' "$map")"
dones="$(sed -n 's/^done:[[:space:]]*//p' "$map")"
syms="$(sed -n 's/^sym:[[:space:]]*//p' "$map")"
codemap="$(grep -vE '^(write|change|test|keep|scout|done|model|model-reason|sym):|^[[:space:]]*$' "$map" || true)"
# F35: the prompt is the full packet. A map never sends the agent off to read
# (a spec, a checkpoint, a plan section "in full"); the orchestrator pastes what
# the agent needs, and this script pastes every cited code span below.
reading="$(grep -inE 'in full|read (it|them) (first|in full|before)|read first|read the (plan|spec|checkpoint|report|doc|file|section)|read \.orchestrator/|read [^ ]*checkpoint' "$map" || true)"
[ -z "$reading" ] || die "map sends the agent to read instead of carrying the content (paste it into the map): $(echo $reading | cut -c1-200)"
# Paste each cited span (path:N -> N-3..N+25, path:A-B -> A..B), 400 lines max.
cited_spans() {
  { grep -oE '[A-Za-z0-9_./-]+\.(py|md|toml|yml|yaml|json|sh|js|ts):[0-9]+(-[0-9]+)?' "$map" || true; } | sort -u |
  while IFS= read -r ref; do
    f="${ref%%:*}"; r="${ref#*:}"
    [ -f "$wt/$f" ] || continue
    if [[ "$r" == *-* ]]; then a="${r%-*}"; b="${r#*-}"; else a=$(( r > 3 ? r - 3 : 1 )); b=$(( r + 25 )); fi
    [ $(( b - a )) -le 120 ] || b=$(( a + 120 ))
    printf '\n### %s (lines %s-%s)\n```\n' "$f" "$a" "$b"
    sed -n "${a},${b}p" "$wt/$f" | awk -v n="$a" '{printf "%d\t%s\n", n++, $0}'
    printf '```\n'
  done | awk 'NR <= 400'
}
spans="$(cited_spans)"
if [ "$role" = implementer ]; then
  [ -n "$writes" ] || die "implementer map needs write: lines"
  [ -n "$scouts" ] || die "implementer map needs a scout: <agent id> line (the scout that mapped this packet)"
  [ -n "$dones" ] || die "implementer map needs done: lines (the checkable items that mean the task is finished)"
fi
if [ "$role" = implementer ] && [ "$mode" = tests ]; then
  bad_w="$(printf '%s\n' "$writes" | { grep -v '^tests/' || true; })"
  [ -z "$bad_w" ] || die "--mode tests: write: lines must all be under tests/: $(echo $bad_w)"
  [ -z "${redlog:-}" ] || die "--mode tests takes no --red-log: the tests do not exist yet"
elif [ "$role" = implementer ]; then
  # F32: every failing test function in the RED run is mapped to a change.
  [ -n "${redlog:-}" ] || die "--red-log is required for role implementer in --mode impl (the RED run output that test-acceptance.py accepted)"
  [ -f "$redlog" ] || die "red log not found: $redlog"
  unmapped="$({ grep -oE '^FAILED [^ ]+::[A-Za-z0-9_]+' "$redlog" || true; } | sed 's/.*:://' | sort -u |
    while IFS= read -r t; do printf '%s\n' "$changes" | grep -qF -- "$t" || echo "$t"; done)"
  [ -z "$unmapped" ] || die "failing tests with no change: line naming them: $(echo $unmapped)"
  [ -n "$writes" ] || die "implementer map needs write: lines"
  [ -n "$changes" ] || die "implementer map needs change: lines"
  # F34: one packet fits its budget; bigger work is split into parallel
  # dispatches, one worktree each.
  [ "$(printf '%s\n' "$changes" | wc -l)" -le 3 ] || die "implementer map has more than 3 change: lines: split it into parallel dispatches, one worktree each"
  redfail="$({ grep -E '^FAILED [^ ]+ - ' "$redlog" || true; } | sed 's/^FAILED //')"
  [ -n "$tests" ] || die "implementer map needs test: lines"
  # F33: the existing behavior the change must keep, stated so the agent never
  # has to go read it: `keep: <test id or path:line> -- <what it asserts>`.
  [ -n "$keeps" ] || die "implementer map needs keep: lines (existing tests to keep green and what they assert)"
  bad_keep="$(printf '%s\n' "$keeps" | { grep -v -- ' -- ' || true; })"
  [ -z "$bad_keep" ] || die "keep: lines need '<test or path:line> -- <what it asserts>': $bad_keep"
fi

bullets() { if [ -n "$1" ]; then printf '%s\n' "$1" | sed 's/^/- /'; else echo "- $2"; fi; }
case "$role" in
  implementer|planner|docs) write_default="none listed" ;;
  *) write_default="none: read-only role"; writes="" ;;
esac
out="$wt/.orchestrator"
graft_context() {  # skeleton of each write target, callers of each changed symbol
  [ -z "${DISPATCH_PROMPT_NO_GRAFT_BUILD:-}" ] || { echo "none (graft context skipped)"; return; }
  local f s
  while IFS= read -r f; do [ -n "$f" ] || continue
    echo "### skeleton: $f"; (cd "$wt" && graft skeleton "$f" 2>&1 | grep -v '^\[graft\]')
  done <<< "$writes"
  while IFS= read -r s; do [ -n "$s" ] || continue
    echo "### callers: $s"; (cd "$wt" && graft callers "$s" 2>&1 | grep -v '^\[graft\]')
  done <<< "$syms"
}

body="$(
cat <<EOF
# orch-$role dispatch: task $task

## Worktree and write targets
Worktree: $wt. Use absolute paths under $wt for every Read/Edit/Write. Start every Bash
command with \`cd $wt && \` (the shell resets to another directory after each call). Never run
git, tests, or edits in any other checkout.
Write targets (edit nothing else):
$(bullets "$writes" "$write_default")

## Spec spans
Read only these line ranges of the spec:
$(if [ ${#specs[@]} -gt 0 ]; then for s in "${specs[@]}"; do r="${s##*:}"; echo "- ${s%:*} lines $r"; done; else echo "- none"; fi)

## Code map
Checked by the orchestrator. Start from these spans; do not re-map what is listed here.
$(bullets "$codemap" "none")

## Cited code (pasted by the dispatch script from current source; do not re-read it)
${spans:-none}

## Exact changes
$(if [ "$role" = implementer ]; then echo "For each change: write the failing test first, run it and record the red failure, then fix and run it green."; fi)
$(bullets "$changes" "none")

## Exact test ids
$(bullets "$tests" "none")

## Done when (tick each in your report, with the command or file:line that shows it)
$(if [ -n "$dones" ]; then printf '%s\n' "$dones" | sed 's/^/- [ ] /'; else echo "- [ ] none listed for this role"; fi)
$(if [ "$role" = implementer ] && [ "$mode" = tests ]; then printf '\nMode: test authoring. Write the failing tests only, under tests/. Each must fail with an assertion that names the behavior; a failure from an import or a typo is rejected by the acceptance step. Change no source file.\n'; fi)

## Existing behavior to keep (already stated; do not re-read these to find out)
$(bullets "$keeps" "none")
$(if [ "$role" = implementer ]; then printf '\n## Current RED failure per test (your fix turns exactly these green)\n'; bullets "${redfail:-}" "none recorded"; fi)

## Test command
$(if [ -n "$testcmd" ]; then echo "Run from $wt: \`$testcmd <test files>\`; plus the repo's lint and typecheck before reporting."; else echo "none: this role does not run the suite"; fi)

## Tool rules (required, not optional)
- Code search and callers: graft, always first. The index is built in $wt (graft/).
  MCP when in your tool list: mcp__graft__graft_find_code, graft_find_all, graft_trace_calls,
  graft_file_api. Otherwise the CLI from $wt: \`graft ask "<question>" --source\`,
  \`graft grep "<literal>"\`, \`graft callers <symbol> --depth 2\`, \`graft skeleton <file>\`.
  Then codegraph_explore, then the \`repowise\` CLI (\`repowise ask\`, \`repowise context\`,
  \`repowise why\`). Hunting with grep/sed through files that graft answers is not allowed.
- Read only the spans cited above plus what those queries return. No whole-file read of any
  file over 200 lines; no whole-diff read. Find a symbol's lines with \`graft grep "<symbol>"\`;
  print only the lines you need with ctx_execute_file (context-mode); right before an Edit, the
  native Read with offset/limit on those lines. Never sed, cat, head or tail to read code.
- Command output (tests, suite, lint, mypy, git log/diff): run it through
  \`repowise distill <command>\` (errors first, exit code kept; \`repowise expand <ref>\` for an
  omitted part), or write it to a file under $out/ and read only the failing lines.
  Never read raw output over 50 lines into your context.
- context-mode, when in your tool list: mcp__plugin_context-mode_context-mode__ctx_batch_execute
  for several commands at once, ctx_execute_file to analyze a file or log without reading it.
- Shell commands use the rtk-prefixed form (\`rtk git\`, \`rtk grep\`, \`rtk find\`, \`rtk log\`).
  Never \`rtk proxy\` to read or trim anything (\`rtk proxy sed/cat/head/tail/grep/awk\`): it runs
  the command raw and saves nothing. Source files: graft. Other files: \`rtk read\` (\`--tail-lines N\`
  for the end of a log) or ctx_execute_file. Command output: \`repowise distill <cmd>\`.
- Edits: \`rtk read <file> --max-lines N\` on the lines you will change, then Edit that file in your
  next call, one file at a time. If the guard denies the Edit, run \`rtk read\` on the file again and
  retry once. Never write a file through a Bash script.

## Command card
| you would type | type this instead |
|---|---|
| \`head -N f\` | \`rtk read f --max-lines N\` |
| \`cat f\` | \`rtk read f\` |
| \`tail -N f\` | \`rtk read f --tail-lines N\` |
| \`wc -l f\` | \`rtk wc -l f\` |
| \`ls\`, \`grep\`, \`find\` | \`rtk ls\`, \`rtk grep\`, \`rtk find\` |
| \`cat > f\` | the Write tool |

## Graft context (pasted by the dispatch script; do not run these again)
$(graft_context)

## Turn limit
You have at most $maxturns turns. Your last step writes $out/checkpoint-$task.md: what is done,
what is left, the next command. If you are stopped at the limit, that file is what the next agent
starts from.

## Required clauses
- Never kill a process you did not start. Leave no background process behind.
- No git stash, checkout, reset, restore, or clean. Do not commit.
- Temp dirs only with cleanup: pytest \`tmp_path\` or a \`TemporaryDirectory\` context manager,
  never a bare \`mkdtemp()\`. Delete any temp HOME before reporting.
- Never touch the real HOME, ~/.claude.json, ~/.codex, or the real data root.
- Never read Claude session transcripts (~/.claude/projects) or any other worktree.
- Use the interpreter named in the Test command; never create a virtual environment or run \`uv sync\`.
- No skip, xfail, or weakened assertions.
- "not expressible" and "out of scope" are not outcomes. Do the full task, or stop and report
  exactly what is unfinished and why.
- Absolute rules: do not descope, do not degrade, do not report incomplete work as done.

## Report
At most 60 lines. Put detail in a file under $out/ and give its path.
EOF
)"

printf '%s\n' "$body"
hash="$(printf '%s\n' "$body" | shasum -a 256 | cut -d' ' -f1)"
printf '<!-- dispatch-prompt v1 sha256:%s -->\n' "$hash"
