#!/usr/bin/env python3
"""Usage report for a run, and the tool-mix line for one agent.
usage: usage.py <orchestrator-session.jsonl> [--since ISO] [--cost-limit-m N]
       usage.py --agent <agent-*.jsonl>
Counts each API message once (message.id, largest output_tokens). The run report covers the session and
every transcript in <session>/subagents/: messages, cache-create, cache-read and output per model, agent type,
task id (from the agent description) and day, the largest context, and the questions I asked."""
import datetime
import glob
import json
import os
import re
import sys
from collections import defaultdict

DENIAL = re.compile(r"rtk-enforce|rtk-context-guard|readme-require-first|No native Read of this exact file|has not gone through rtk|File has not been read yet|hook error")
QUESTION = re.compile(r"^\s*(?:\d+[.)]\s*|[-*]\s*)?(?:\*\*)?(?:Should|Shall|Do you want|Would you (?:like|prefer)|Which|Want me to|Can I|May I)\b[^\n]*\?\s*$", re.I | re.M)


def lead_words(cmd):
    out = []
    for seg in re.split(r"&&|\|\||;|\n", cmd):
        s = re.sub(r"^(\w+=\S+\s+)+", "", seg.strip())
        if not s or s.startswith(("cd ", "#")):
            continue
        w = s.split()
        if w[0] == "rtk" and len(w) > 1:
            out.append(w[2] if w[1] == "proxy" and len(w) > 2 else "rtk " + w[1])
        else:
            out.append(w[0])
    return out


def text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict))
    return ""


def messages(path):
    """message.id -> (timestamp, model, input, cache_create, cache_read, output)."""
    recs = {}
    for line in open(path, errors="ignore"):
        if '"usage"' not in line:
            continue
        try:
            o = json.loads(line)
        except ValueError:
            continue
        m = o.get("message")
        if o.get("type") != "assistant" or not isinstance(m, dict) or m.get("model") == "<synthetic>":
            continue
        u, mid = m.get("usage"), m.get("id")
        if not u or not mid:
            continue
        out = u.get("output_tokens", 0)
        if mid in recs:
            recs[mid][5] = max(recs[mid][5], out)
        else:
            recs[mid] = [o.get("timestamp", ""), m.get("model", ""), u.get("input_tokens", 0),
                         u.get("cache_creation_input_tokens", 0), u.get("cache_read_input_tokens", 0), out]
    return recs


def day(ts):
    return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().strftime("%m-%d")


def tool_mix(path):
    c = dict(graft=0, ctx=0, rtk_read=0, read=0, cat=0, edit_write=0, denials=0)
    turns, first_edit, seen = 0, None, set()
    for line in open(path, errors="ignore"):
        try:
            o = json.loads(line)
        except ValueError:
            continue
        m = o.get("message")
        if not isinstance(m, dict) or not isinstance(m.get("content"), list):
            continue
        if o.get("type") == "assistant" and m.get("id") not in seen:
            seen.add(m.get("id"))
            turns += 1
        for b in m["content"]:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use":
                name, inp = b["name"], b.get("input", {})
                if name in ("Edit", "Write", "MultiEdit"):
                    c["edit_write"] += 1
                    first_edit = first_edit or turns
                elif name == "Read":
                    c["read"] += 1
                elif name.startswith("mcp__graft"):
                    c["graft"] += 1
                elif "context-mode" in name:
                    c["ctx"] += 1
                elif name == "Bash":
                    for w in lead_words(inp.get("command", "")):
                        c["graft"] += w == "graft"
                        c["rtk_read"] += w == "rtk read"
                        c["cat"] += w == "cat"
                        c["ctx"] += w.startswith("ctx_")
            elif b.get("type") == "tool_result" and b.get("is_error") and DENIAL.search(text(b.get("content"))):
                c["denials"] += 1
    agent = os.path.basename(path).replace("agent-", "").replace(".jsonl", "")
    return f"tool-mix {agent} turns={turns} " + " ".join(f"{k}={v}" for k, v in c.items()) + f" first_edit_turn={first_edit}"


def run_report(session, since, cost_limit):
    groups = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0]))
    biggest = 0
    files = [("orchestrator", session, "orchestrator")]
    for f in sorted(glob.glob(os.path.join(session[:-6], "subagents", "*.jsonl"))):
        meta = json.load(open(f[:-6] + ".meta.json"))
        files.append((meta.get("agentType", "?"), f, meta.get("description", "")))
    for role, path, desc in files:
        task = (re.search(r"\bT\d+\b", desc) or [None])[0] or "none"
        for ts, model, i, cc, cr, out in messages(path).values():
            if since and ts < since:
                continue
            biggest = max(biggest, i + cc + cr) if role == "orchestrator" else biggest
            for kind, key in (("model", model), ("role", role), ("task", task), ("day", day(ts))):
                g = groups[kind][key]
                g[0] += 1; g[1] += cc; g[2] += cr; g[3] += out
    print("kind\tkey\tmessages\tcache_create_M\tcache_read_M\toutput_M")
    for kind in ("model", "role", "task", "day"):
        for key, (n, cc, cr, out) in sorted(groups[kind].items()):
            print(f"{kind}\t{key}\t{n}\t{cc/1e6:.1f}\t{cr/1e6:.0f}\t{out/1e6:.2f}")
            if kind == "day" and cost_limit and cr / 1e6 > cost_limit:
                print(f"COST\t{key}\t{cr/1e6:.0f}M cache-read exceeds {cost_limit}M")
    asks = replies = stops = 0
    for line in open(session, errors="ignore"):
        try:
            o = json.loads(line)
        except ValueError:
            continue
        m = o.get("message")
        if not isinstance(m, dict):
            continue
        if o.get("type") == "assistant" and isinstance(m.get("content"), list):
            for b in m["content"]:
                if b.get("type") == "tool_use" and b["name"] == "AskUserQuestion":
                    asks += 1
                if b.get("type") == "text" and QUESTION.search(b.get("text", "")):
                    replies += 1
        if o.get("type") == "user" and text(m.get("content")).startswith("Stop hook feedback"):
            stops += 1
    print(f"largest orchestrator context\t{biggest}")
    print(f"questions\tAskUserQuestion={asks}\treply_lines={replies}\tstop_hook_blocks={stops}")


if __name__ == "__main__":
    if "--agent" in sys.argv:
        print(tool_mix(sys.argv[sys.argv.index("--agent") + 1]))
    else:
        since = sys.argv[sys.argv.index("--since") + 1] if "--since" in sys.argv else ""
        limit = float(sys.argv[sys.argv.index("--cost-limit-m") + 1]) if "--cost-limit-m" in sys.argv else 0
        run_report(sys.argv[1], since, limit)
