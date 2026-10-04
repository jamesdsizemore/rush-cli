#!/usr/bin/env python3
"""behavior-scan.py <session.jsonl>
Reads only the assistant's tool_use and tool_result records (never the user's messages) and prints
CANDIDATES for me to open: result volume by tool, repeated identical Bash commands, tool-call mix,
and how quickly I reacted to finished-agent notifications. Output is capped at 30 lines.
Output goes in doc section 2.1 / H17; a candidate is not a finding until I open it.
A second run on the same transcript is refused (it repeats work the doc already holds); --again allows it.
The refusal is recorded in ~/.claude/orchestrator/scans.tsv: transcript, size, time."""
import collections, datetime as dt, json, os, re, sys

path = sys.argv[1]
scans = os.path.expanduser("~/.claude/orchestrator/scans.tsv")
key = f"{os.path.abspath(path)}\t{os.path.getsize(path)}"
if "--again" not in sys.argv and os.path.exists(scans):
    for row in open(scans):
        if row.startswith(key + "\t"):
            sys.exit(f"behavior-scan: already run on this transcript at {row.split(chr(9))[2].strip()}; "
                     "its results are in the remediation doc (section 2.1, H17). Pass --again to repeat.")
os.makedirs(os.path.dirname(scans), exist_ok=True)
with open(scans, "a") as f:
    f.write(f"{key}\t{dt.datetime.now().isoformat(timespec='seconds')}\n")
recs = []
for line in open(path, errors="ignore"):
    try:
        r = json.loads(line)
    except ValueError:
        continue
    if r.get("isSidechain") or not r.get("timestamp"):
        continue
    recs.append(r)
T = lambda r: dt.datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00"))
uses, calls, cmds = {}, collections.Counter(), collections.Counter()
for r in recs:
    c = r.get("message", {}).get("content")
    if r["type"] == "assistant" and isinstance(c, list):
        for b in c:
            if b.get("type") == "tool_use":
                uses[b["id"]] = b["name"]
                calls[b["name"]] += 1
                if b["name"] == "Bash":
                    cmds[re.sub(r"\s+", " ", b["input"].get("command", ""))[:100]] += 1
size, n = collections.Counter(), collections.Counter()
for r in recs:
    c = r.get("message", {}).get("content")
    if r["type"] == "user" and isinstance(c, list):
        for b in c:
            if b.get("type") == "tool_result" and b.get("tool_use_id") in uses:
                x = b.get("content")
                s = len(x) if isinstance(x, str) else sum(len(y.get("text", "")) for y in x if isinstance(y, dict))
                size[uses[b["tool_use_id"]]] += s
                n[uses[b["tool_use_id"]]] += 1
tot = sum(size.values()) or 1
print(f"CANDIDATE result-volume by tool (listed {min(6, len(size))} of {len(size)} tools):")
for name, s in size.most_common(6):
    print(f"  {name[:40]:40s} calls={n[name]:5d} share={100 * s // tot}%")
print(f"CANDIDATE repeated Bash commands (listed 5 of {sum(1 for k in cmds.values() if k > 1)} that repeat):")
for cmd, k in cmds.most_common(5):
    print(f"  x{k}  {cmd}")
print("CANDIDATE tool-call mix:", dict(calls.most_common(6)))
lat = []
for i, r in enumerate(recs):
    if r["type"] == "user" and "task-notification" in str(r.get("message", {}).get("content", ""))[:200]:
        for j in range(i + 1, min(i + 40, len(recs))):
            if recs[j]["type"] == "assistant":
                lat.append((T(recs[j]) - T(r)).total_seconds())
                break
lat.sort()
if lat:
    print(f"CANDIDATE reaction to finished agents: median {lat[len(lat) // 2]:.0f}s over {len(lat)} notifications")
