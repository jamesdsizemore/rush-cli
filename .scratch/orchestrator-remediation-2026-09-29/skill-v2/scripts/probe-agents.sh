#!/usr/bin/env bash
# probe-agents.sh <project-dir> <out.json>
# Runs each installed orch-* agent as the session agent (`claude -p --agent`) from <project-dir>, so the
# definition that answers is the one a run would use there (repo-level copies shadow user-level ones),
# with its own model, effort and hooks. One invocation per agent: the model and the three replies belong
# to that agent only. ok=true needs, for every agent, exactly the lines `toolsearch:`, `graft-mcp:` and
# `ctx-mcp:` each `ok`, and modelUsage naming exactly the matrix model.
# PROBE_ROLES limits the roles (default: all eight).
set -uo pipefail
proj="${1:?usage: probe-agents.sh <project-dir> <out.json>}"; out="${2:?out.json}"
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
ctx="$(printf '%s\n' "$HOME"/.claude/plugins/cache/context-mode/context-mode/*/start.mjs | tail -1)"
printf '{"mcpServers":{"graft":{"command":"graft","args":["mcp"]},"plugin_context-mode_context-mode":{"command":"node","args":["%s"]}}}\n' "$ctx" > "$work/mcp.json"
steps="You are a probe. Do nothing else. Step 1: call ToolSearch with query select:mcp__graft__graft_repo_map. Step 2: call mcp__graft__graft_repo_map. Step 3: call mcp__plugin_context-mode_context-mode__ctx_execute with language shell and code 'echo probe-ok'. Reply with exactly three lines: toolsearch: ok or fail; graft-mcp: ok or fail; ctx-mcp: ok or fail."
declare_models() {  # role -> matrix model id (plan X5)
  case "$1" in
    implementer|docs) echo claude-sonnet-5-5 ;;
    reviewer|planner|adversarial-reviewer|design-gate) echo claude-opus-5-5 ;;
    scout|verifier) echo claude-haiku-4-5-20251001 ;;
  esac
}
roles="${PROBE_ROLES:-implementer docs reviewer planner adversarial-reviewer scout verifier design-gate}"
: > "$work/rows.tsv"
for role in $roles; do
  ( cd "$proj" && timeout 300 claude -p "$steps" --agent "orch-$role" --strict-mcp-config --mcp-config "$work/mcp.json" \
      --allowedTools ToolSearch 'mcp__graft__*' 'mcp__plugin_context-mode_context-mode__*' \
      --output-format json --no-session-persistence --max-budget-usd 1 > "$work/$role.json" 2> "$work/$role.err" )
  printf '%s\t%s\t%s\n' "$role" "$(declare_models "$role")" "$work/$role.json" >> "$work/rows.tsv"
done
python3 - "$work/rows.tsv" "$out" <<'PY'
import json, re, sys
rows, out = sys.argv[1], sys.argv[2]
agents, ok = {}, True
for line in open(rows):
    role, want, path = line.rstrip("\n").split("\t")
    try:
        res = json.load(open(path))
    except (OSError, ValueError):
        agents[role] = {"error": "no result"}; ok = False; continue
    lines = [l.strip() for l in (res.get("result") or "").strip().split("\n") if l.strip()]
    got = {}
    for label in ("toolsearch", "graft-mcp", "ctx-mcp"):
        hits = [l for l in lines if l.startswith(label + ":")]
        m = re.fullmatch(label + r": (ok|fail)", hits[0]) if len(hits) == 1 else None
        got[label] = m.group(1) if m else "missing"
    models = sorted((res.get("modelUsage") or {}).keys())
    good = all(v == "ok" for v in got.values()) and len(lines) == 3 and models == [want]
    agents[role] = {**got, "models": models, "want_model": want, "ok": good}
    ok = ok and good
json.dump({"ok": ok, "agents": agents}, open(out, "w"), indent=1)
print(json.dumps({"ok": ok, "failed": [r for r, a in agents.items() if not a.get("ok")]}))
PY
