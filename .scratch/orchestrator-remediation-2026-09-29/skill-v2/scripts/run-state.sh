#!/usr/bin/env bash
# Orchestrator run state. `.orchestrator/run.json` at the repo root marks an active run;
# ~/.claude/hooks/orchestrator-model-guard.js only enforces while that file exists.
#   run-state.sh start <phase-id> <plan-path> <base-branch>
#   run-state.sh baseline <seconds>   (record the suite's baseline run time; required before start)
#   run-state.sh stop
#   run-state.sh log "<text>"   (append a timestamped line to .orchestrator/progress.log)
#   run-state.sh status
#   run-state.sh report   (the status paragraph: tagged, live lines; use it for every status reply)
#   run-state.sh next     (ids that are ready to dispatch now)
#   run-state.sh task add <id> <deps-csv> [files-csv] | start <id> | merged <id> | parked <id> "<text>" | unpark <id>
#     merged needs .orchestrator/gate-ok == HEAD (a local gate on the merged state); a child id T28.a rolls its
#     parent T28 to merged when every child is. CI on the remote is a separate check made at handoff.
set -euo pipefail

root="$(git rev-parse --show-toplevel)"
state_dir="$root/.orchestrator"
state="$state_dir/run.json"
log="$state_dir/progress.log"
tasks="$state_dir/tasks.tsv"
baseline="$state_dir/baseline.txt"

# F-items this build covers; printed on start (F23).
FITEMS='F1  run-state.sh start preflight: disk, CI, baseline, this list
F3  scripts/monitor.py: alerts on budget/orienting/quiet/disk/long-shell/ci-red/idle-task
F5  scripts/gate.sh: runs gate.cmds, writes gate-ok on all-zero
F11 scripts/test-acceptance.py: AST assert check + bullet map + must-fail
F12 scripts/decisions.sh: decision ledger + pending members
F16 run-state.sh task graph: unblocked-idle / running-with-unmerged-dep
F23 this list: printed at start and expected at every dispatch'

print_task_alerts() {
  [ -e "$tasks" ] || return 0
  awk -F'\t' '
    { id=$1; deps[id]=$2; status[id]=$3; order[NR]=id; n=NR }
    END {
      for (i=1;i<=n;i++) {
        id=order[i]
        unblocked=1
        if (deps[id] != "") {
          split(deps[id], d, ",")
          for (j in d) if (status[d[j]] != "merged") unblocked=0
        }
        if (unblocked==1 && status[id]=="pending") print "unblocked idle: " id
        if (status[id]=="running" && unblocked==0) print "running with unmerged dep: " id
      }
    }' "$tasks"
}

task_set_status() {
  local id="$1" new_status="$2"
  awk -F'\t' -v id="$id" -v st="$new_status" 'BEGIN{OFS="\t"} $1==id{$3=st} {print}' "$tasks" > "$tasks.tmp" && mv "$tasks.tmp" "$tasks"
}

# Pending leaf nodes whose dependencies are merged and whose files (4th column) no running node,
# and no node already listed here, holds. A node with children (T28 with T28.a, T28.b) is a group, not dispatchable.
print_ready() {
  awk -F'\t' '
    { id=$1; deps[id]=$2; st[id]=$3; files[id]=$4; order[NR]=id; n=NR
      p=id; if (sub(/\.[^.]*$/, "", p)) child[p]=1 }
    END {
      for (i=1;i<=n;i++) if (st[order[i]]=="running" && files[order[i]]!="") {
        m=split(files[order[i]], f, ","); for (k=1;k<=m;k++) held[f[k]]=1 }
      for (i=1;i<=n;i++) { id=order[i]; ok=1
        if (deps[id]!="") { m=split(deps[id], d, ","); for (j=1;j<=m;j++) if (st[d[j]]!="merged") ok=0 }
        if (files[id]!="") { m=split(files[id], f, ","); for (k=1;k<=m;k++) if (held[f[k]]) ok=0 }
        if (ok && st[id]=="pending" && !(id in child)) {
          print id
          if (files[id]!="") { m=split(files[id], f, ","); for (k=1;k<=m;k++) held[f[k]]=1 } } } }' "$tasks"
}

# One sha256 line per file that must not change during a run: the user's hooks, this skill, the orch-* agents
# and settings.json. `start` records it; `stop` prints "unchanged" or the difference.
guard_list() {
  { find "$HOME/.claude/hooks" "$HOME/.claude/skills/orchestrator" -type f \( -name '*.js' -o -name '*.sh' -o -name '*.py' -o -name '*.md' -o -name '*.mjs' \) -print0 2>/dev/null \
      | sort -z | xargs -0 shasum -a 256 2>/dev/null
    shasum -a 256 "$HOME/.claude/settings.json" "$HOME"/.claude/agents/orch-*.md 2>/dev/null; } || true
}

case "${1:-}" in
  start)
    [ $# -eq 4 ] || { echo "usage: run-state.sh start <phase-id> <plan-path> <base-branch>" >&2; exit 2; }
    [ -e "$state" ] && { echo "run already active: $state" >&2; exit 1; }
    mkdir -p "$state_dir"

    [ -e "$baseline" ] || { echo "refusing to start: no baseline recorded (run-state.sh baseline <seconds>)" >&2; exit 1; }

    # Agent definitions resolve from the session's project directory, which is the main checkout, not this worktree.
    main_root="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"
    shadow="$(compgen -G "$main_root/.claude/agents/orch-*.md" || true)"
    [ -z "$shadow" ] || { printf 'refusing to start: project-level agent definitions shadow the user-level ones:\n%s\n' "$shadow" >&2; exit 1; }
    jq -e '.ok == true' "$state_dir/tool-probe.json" >/dev/null 2>&1 \
      || { echo "refusing to start: no passing $state_dir/tool-probe.json (run probe-agents.sh $main_root $state_dir/tool-probe.json)" >&2; exit 1; }
    [ -n "${CLAUDE_CODE_SESSION_ID:-}" ] \
      || { echo "refusing to start: CLAUDE_CODE_SESSION_ID is not set, so the run hooks cannot bind to this session" >&2; exit 1; }
    [ -f "$root/$3" ] || { echo "refusing to start: plan not found: $root/$3" >&2; exit 1; }
    missing=""
    for h in $(grep -oE '^#### T[0-9]+' "$root/$3" | sed 's/^#### //'); do
      awk -F'\t' -v h="$h" '$1==h || index($1, h".")==1 {f=1} END{exit !f}' "$tasks" 2>/dev/null || missing="$missing $h"
    done
    [ -z "$missing" ] || { echo "refusing to start: tasks.tsv has no node for:$missing (run load-plan.py)" >&2; exit 1; }

    avail_gb="$(df -g "$root" | awk 'NR==2{print $4}')"
    [ "$avail_gb" -ge 15 ] || { echo "refusing to start: only ${avail_gb}GiB free (need >=15)" >&2; exit 1; }

    ci_json="$(gh run list --branch "$4" --limit 1 --json conclusion,databaseId 2>/dev/null || echo '[]')"
    ci_concl="$(echo "$ci_json" | jq -r '.[0].conclusion // "unknown"')"

    base_sha="$(git rev-parse "$4")"
    mkdir -p "$state_dir/reviews" "$state_dir/maps" "$state_dir/prompts" "$state_dir/design"
    guard_list > "$state_dir/guard.list"
    exclude="$(git rev-parse --git-path info/exclude)"
    mkdir -p "$(dirname "$exclude")"
    grep -qxF '.orchestrator/' "$exclude" 2>/dev/null || echo '.orchestrator/' >> "$exclude"
    py="${ORCH_PYTHON:-$main_root/.venv/bin/python}"
    [ -x "$py" ] || { rm -rf "$state_dir/guard.list"; echo "refusing to start: interpreter $py is not executable (set ORCH_PYTHON to the shared virtual environment's python)" >&2; exit 1; }
    jq -n --arg phase "$2" --arg plan "$3" --arg base "$4" --arg sha "$base_sha" --arg py "$py" \
      --arg branch "$(git branch --show-current)" --arg started "$(date -u +%FT%TZ)" \
      '{phase:$phase, plan:$plan, branch:$branch, base_branch:$base, base_sha:$sha, python:$py, started:$started}' > "$state"
    {
      echo "$(date -u +%FT%TZ) run started: phase $2, plan $3, base $4 ($base_sha)"
      echo "$(date -u +%FT%TZ) base branch $4 latest CI: $ci_concl"
      [ "$ci_concl" = "failure" ] && echo "$(date -u +%FT%TZ) work: base branch $4 CI is red"
    } > "$log"
    # The session cwd is usually the main checkout, not this worktree: tell the model
    # guard where the active run lives.
    mkdir -p "$HOME/.claude/orchestrator"
    printf '%s\n' "$root" > "$HOME/.claude/orchestrator/active-run"
    jq -n --arg root "$root" --arg sid "$CLAUDE_CODE_SESSION_ID" '{root:$root, session_id:$sid}' \
      > "$HOME/.claude/orchestrator/active-session.json"
    echo "run started: $state"
    echo "F-items applying to this run:"
    echo "$FITEMS"
    ;;
  baseline)
    [ $# -eq 2 ] || { echo "usage: run-state.sh baseline <seconds>" >&2; exit 2; }
    mkdir -p "$state_dir"
    echo "$2" > "$baseline"
    echo "baseline recorded: ${2}s"
    ;;
  log)
    [ -e "$state" ] || { echo "no active run" >&2; exit 1; }
    [ $# -eq 2 ] || { echo 'usage: run-state.sh log "<text>"' >&2; exit 2; }
    echo "$(date -u +%FT%TZ) $2" >> "$log"
    ;;
  stop)
    [ -e "$state" ] || { echo "no active run" >&2; exit 1; }
    if [ -n "$(git -C "$root" status --porcelain)" ]; then
      echo "refusing to stop: uncommitted changes in $root" >&2; exit 1
    fi
    phase="$(jq -r .phase "$state")"; phase_branch="$(jq -r .branch "$state")"
    # Delete the run's merged task branches and remove their clean worktrees; the phase branch stays.
    for b in $(git -C "$root" branch --merged "$phase_branch" --format='%(refname:short)' | grep "^phase/$phase-" || true); do
      [ "$b" = "$phase_branch" ] && continue
      wtp="$(git -C "$root" worktree list --porcelain | awk -v b="refs/heads/$b" '/^worktree /{p=$2} $1=="branch" && $2==b{print p}')"
      if [ -n "$wtp" ] && [ "$wtp" != "$root" ]; then
        git -C "$root" worktree remove "$wtp" 2>/dev/null || { echo "kept $b: its worktree $wtp is not clean" >&2; continue; }
      fi
      git -C "$root" branch -d "$b" > /dev/null && echo "deleted merged branch $b"
    done
    if [ -s "$state_dir/guard.list" ]; then
      if guard_list | diff "$state_dir/guard.list" - > "$state_dir/guard.diff"; then
        echo "hooks, settings, skill and agent files unchanged"
      else
        echo "CHANGED during the run:"; cat "$state_dir/guard.diff"
      fi
    fi
    rm -f "$state"
    marker="$HOME/.claude/orchestrator/active-run"
    if [ -f "$marker" ] && [ "$(cat "$marker")" = "$root" ]; then rm -f "$marker" "$HOME/.claude/orchestrator/active-session.json"; fi
    echo "run stopped"
    ;;
  task)
    mkdir -p "$state_dir"; touch "$tasks"
    sub="${2:-}"
    case "$sub" in
      add)
        [ $# -ge 4 ] && [ $# -le 5 ] || { echo "usage: run-state.sh task add <id> <deps-csv> [files-csv]" >&2; exit 2; }
        id="$3"; deps="$4"; files="${5:-}"
        if awk -F'\t' -v id="$id" '$1==id{f=1} END{exit !f}' "$tasks"; then
          echo "task exists: $id" >&2; exit 1
        fi
        printf '%s\t%s\t%s\t%s\n' "$id" "$deps" "pending" "$files" >> "$tasks"
        ;;
      start)
        [ $# -eq 3 ] || { echo "usage: run-state.sh task start <id>" >&2; exit 2; }
        task_set_status "$3" "running"
        ;;
      merged)
        [ $# -eq 3 ] || { echo "usage: run-state.sh task merged <id>" >&2; exit 2; }
        gate_ok="$(cat "$state_dir/gate-ok" 2>/dev/null || true)"
        [ -n "$gate_ok" ] && [ "$gate_ok" = "$(git rev-parse HEAD)" ] \
          || { echo "refusing: gate-ok is not the current HEAD; run gate.sh on the merged state first" >&2; exit 1; }
        task_set_status "$3" "merged"
        case "$3" in
          *.*) parent="${3%.*}"
               if awk -F'\t' -v p="$parent" 'index($1, p".")==1 && $3!="merged"{f=1} END{exit f}' "$tasks"; then
                 task_set_status "$parent" "merged"
               fi ;;
        esac
        ;;
      parked)
        [ $# -eq 4 ] || { echo 'usage: run-state.sh task parked <id> "<question text>"' >&2; exit 2; }
        task_set_status "$3" "parked"
        printf '%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$3" "$4" >> "$state_dir/questions.md"
        ;;
      unpark)
        [ $# -eq 3 ] || { echo "usage: run-state.sh task unpark <id>" >&2; exit 2; }
        task_set_status "$3" "pending"
        ;;
      *)
        echo "usage: run-state.sh task add|start|merged|parked|unpark" >&2; exit 2
        ;;
    esac
    ;;
  next)
    [ -e "$tasks" ] || { echo "no tasks.tsv: run load-plan.py" >&2; exit 1; }
    print_ready
    ;;
  report)
    [ -e "$state" ] || { echo "no active run" >&2; exit 1; }
    now="$(date +%H:%M:%S)"
    start_iso="$(head -1 "$log" | cut -d' ' -f1)"
    start_s="$(date -j -u -f %Y-%m-%dT%H:%M:%SZ "$start_iso" +%s 2>/dev/null || date -u -d "$start_iso" +%s)"
    read -r merged total parked < <(awk -F'\t' '
      { id=$1; st[id]=$3; order[NR]=id; n=NR; p=id; if (sub(/\.[^.]*$/, "", p)) child[p]=1 }
      END { for (i=1;i<=n;i++) { id=order[i]; if (id in child) continue; t++; if (st[id]=="merged") m++; if (st[id]=="parked") k++ }
            print m+0, t+0, k+0 }' "$tasks")
    ready="$(print_ready | wc -l | tr -d ' ')"
    subdir="$(compgen -G "$HOME/.claude/projects/*/${CLAUDE_CODE_SESSION_ID:-none}/subagents" | head -1 || true)"
    if [ -n "$subdir" ]; then
      agents="$(python3 "$(dirname "$0")/monitor.py" "$state_dir" "$subdir" --status)"
    else
      agents="registered=? running=? finished-open=? (no subagents directory for this session)"
    fi
    gate_ok="$(cat "$state_dir/gate-ok" 2>/dev/null || true)"
    if [ -z "$gate_ok" ]; then gate="none"; elif [ "$gate_ok" = "$(git rev-parse HEAD)" ]; then gate="current"; else gate="stale"; fi
    awk -v s="$start_s" -v n="$(date +%s)" -v m="$merged" -v t="$total" -v now="$now" 'BEGIN {
      h=(n-s)/3600; printf "elapsed=%.1fh merged=%d/%d rate=%.2fh per merged task [run-state.sh report %s: progress.log line 1, tasks.tsv]\n", h, m, t, (m ? h/m : 0), now }'
    echo "agents $agents [run-state.sh report $now: agents.active, agent transcripts]"
    echo "ready=$ready parked=$parked [run-state.sh report $now: tasks.tsv]"
    echo "gate=$gate free=$(df -g "$root" | awk 'NR==2{print $4}')GiB [run-state.sh report $now: gate-ok, df]"
    sess="$(compgen -G "$HOME/.claude/projects/*/${CLAUDE_CODE_SESSION_ID:-none}.jsonl" | head -1 || true)"
    if [ -n "$sess" ]; then
      u="$(python3 "$(dirname "$0")/usage.py" "$sess" --since "$start_iso" --cost-limit-m "${ORCH_COST_LIMIT_M:-2500}" 2>/dev/null || true)"
      o="$(printf '%s\n' "$u" | awk -F'\t' '$1=="role" && $2=="orchestrator"{print $5}')"
      c="$(printf '%s\n' "$u" | awk -F'\t' '$1=="COST"{print "COST " $2 " " $3; exit}')"
      echo "usage orchestrator cache-read=${o:-?}M ${c:-within-limit} [run-state.sh report $now: usage.py]"
    fi
    ;;
  status)
    if [ -e "$state" ]; then
      jq . "$state"
      [ -e "$log" ] && sed -n p "$log"
    else
      echo "no active run"
    fi
    print_task_alerts
    "$(dirname "$0")/decisions.sh" pending
    ;;
  *)
    echo "usage: run-state.sh start|baseline|log|stop|status|report|next|task" >&2; exit 2
    ;;
esac
