#!/usr/bin/env bash
# save-map.sh <agent-id> <task> <role> [scout-agent-id]
# Run from the worktree root. Writes the final message of a finished read-only agent (an orch-scout table or an
# orch-design-gate brief) to .orchestrator/maps/<task>-<role>.md, so a read-only agent needs no Write tool and
# the orchestrator does not retype 60 lines. With a scout id, a `scout: <id>` line is added to the map.
# The agent's transcript is <session>/subagents/agent-<id>.jsonl (ORCH_SUBAGENTS_DIR overrides the lookup).
set -euo pipefail
id="${1:?agent id}"; task="${2:?task id}"; role="${3:?role}"; scout="${4:-}"
root="$(git rev-parse --show-toplevel)"
dir="${ORCH_SUBAGENTS_DIR:-$(compgen -G "$HOME/.claude/projects/*/${CLAUDE_CODE_SESSION_ID:?CLAUDE_CODE_SESSION_ID is not set}/subagents" | head -1)}"
file="$dir/agent-$id.jsonl"
[ -f "$file" ] || { echo "save-map: no transcript for agent $id at $file" >&2; exit 1; }
mkdir -p "$root/.orchestrator/maps"
out="$root/.orchestrator/maps/$task-$role.md"
python3 - "$file" "$out" "$scout" <<'PY'
import json, sys
src, out, scout = sys.argv[1:4]
text = handback = ""
for line in open(src, errors="ignore"):
    try:
        r = json.loads(line)
    except ValueError:
        continue
    if r.get("type") == "assistant":
        c = (r.get("message") or {}).get("content")
        if not isinstance(c, list):
            continue
        # The report of an orch-* agent is the `message` of its SubagentHandback call; its last text
        # block is only "Report delivered". Prefer the hand-back, fall back to the last text.
        for b in c:
            if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "SubagentHandback":
                m = (b.get("input") or {}).get("message", "")
                if m.strip():
                    handback = m.strip()
        t = "\n".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
        if t.strip():
            text = t.strip()
text = handback or text
if not text:
    sys.exit("save-map: the agent's transcript holds no final message")
if scout and f"scout: {scout}" not in text:
    text += f"\nscout: {scout}"
open(out, "w").write(text + "\n")
print(f"save-map: wrote {out} ({len(text.splitlines())} lines)")
PY
