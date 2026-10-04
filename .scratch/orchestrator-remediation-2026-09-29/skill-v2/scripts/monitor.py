#!/usr/bin/env python3
"""Watch active agents + repo health for an orchestrator run, alert on the
first unseen problem. Kinds and exit codes are in EXIT_CODE. Re-reads the
agents-active file every pass so agents can be added without a restart.
Already-alerted (id, kind) pairs are recorded in .orchestrator/alerts.seen and
not repeated; a kind in RECURRING is dropped from it once its condition clears,
so a later episode alerts again.

Usage: monitor.py <run_dir> <transcripts_dir> [--session-pid PID]
                   [--ci-branch BRANCH] [--once]
"""

import argparse
from datetime import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time

QUIET_SECS = 480
ORIENT_TOKENS = 40_000
DISK_MIN_GIB = 8
LONG_SHELL_SECS = 60 * 60

# One table for every alert kind; a test fails if two kinds share a code.
EXIT_CODE = {
    "DISK": 1,
    "ORIENTING": 3,
    "QUIET": 4,
    "LONG-SHELL": 5,
    "CI-RED": 6,
    "IDLE-TASK": 7,
    "TOOLSTACK": 8,
    "READY-LOW": 10,
    "SPLIT": 11,
    "HANDED-BACK-OPEN": 12,
    "RESUME": 13,
    "ORCH-RESEARCH": 14,
    "SUITE-SLOW": 15,
    "SCRIPT-EDIT": 16,
}
# A condition that clears and returns is a new episode: its (id, kind) key is dropped from alerts.seen
# on the first pass where the check runs and finds it clear, so it can alert again.
RECURRING = {"DISK", "QUIET", "LONG-SHELL", "CI-RED", "TOOLSTACK", "IDLE-TASK", "HANDED-BACK-OPEN",
             "SCRIPT-EDIT", "READY-LOW", "SUITE-SLOW", "ORCH-RESEARCH"}
HANDED_BACK_SECS = 300
SCRIPT_EDIT_MIN = 3
READY_LOW_SECS = 120
SPLIT_MAX_AGENTS = 6
SUITE_SLOW_FACTOR = 1.5
RESEARCH_WINDOW = 100
RESEARCH_LIMIT = 0.25
_RESEARCH_LEAD = {"rtk read", "rtk grep", "rtk find", "rtk ls", "cat", "sed", "head", "tail", "grep", "rg", "find", "ls", "graft", "repowise"}


def state_dir(run_dir: str) -> str:
    # F34: accept the state dir itself; never read a nested empty one.
    run_dir = os.path.normpath(run_dir)
    if os.path.basename(run_dir) == ".orchestrator":
        return run_dir
    d = os.path.join(run_dir, ".orchestrator")
    os.makedirs(d, exist_ok=True)
    return d


def read_agents_active(path: str) -> list[tuple[str, int, str]]:
    """Lines: agent_id budget role"""
    out = []
    if not os.path.exists(path):
        return out
    with open(path) as f:
        for line in f:
            parts = line.split()
            if len(parts) < 3:
                continue
            out.append((parts[0], int(parts[1]), parts[2]))
    return out


def scan_transcript(path: str) -> tuple[int, bool, int]:
    """Returns (last_tokens, edited, first_tokens)."""
    last, edited, first = 0, False, 0
    with open(path) as f:
        for line in f:
            if '"usage"' not in line and '"tool_use"' not in line:
                continue
            try:
                msg = json.loads(line)["message"]
            except (ValueError, KeyError, TypeError):
                continue
            u = msg.get("usage")
            if u:
                last = (
                    u.get("input_tokens", 0)
                    + u.get("cache_read_input_tokens", 0)
                    + u.get("cache_creation_input_tokens", 0)
                )
                first = first or last
            for block in msg.get("content") or []:
                if isinstance(block, dict) and block.get("name") in ("Edit", "Write"):
                    edited = True
                # F34: agents edit through exact-match Python scripts via Bash.
                if isinstance(block, dict) and block.get("name") == "Bash" and any(
                    w in str((block.get("input") or {}).get("command", ""))
                    for w in _SCRIPT_WRITE
                ):
                    edited = True
    return last, edited, first


_SCRIPT_WRITE = ("write_text(", ".write(", "write_bytes(")


def scripted_edits(path: str) -> int:
    """Bash commands that write a file from a script: the read-guard bypass."""
    n = 0
    with open(path) as f:
        for line in f:
            if '"Bash"' not in line:
                continue
            try:
                msg = json.loads(line)["message"]
            except (ValueError, KeyError, TypeError):
                continue
            for block in msg.get("content") or []:
                if isinstance(block, dict) and block.get("name") == "Bash" and any(
                    w in str((block.get("input") or {}).get("command", "")) for w in _SCRIPT_WRITE
                ):
                    n += 1
    return n


def finished(path: str) -> bool:
    """The agent has handed back: its last line is a SubagentStop record, or its last assistant
    message is an end_turn with no tool call pending. One definition for the monitor and the hooks."""
    with open(path) as f:
        lines = f.read().rstrip("\n").split("\n")
    if lines and "SubagentStop" in lines[-1]:
        return True
    last = None
    for line in lines:
        if '"assistant"' in line or '"user"' in line:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("type") in ("assistant", "user"):
                last = row
    if not last or last.get("type") != "assistant":
        return False
    return (last.get("message") or {}).get("stop_reason") == "end_turn" and pending_since(path) is None


PENDING_OK_SECS = 3600


def pending_since(path: str) -> float | None:
    """Epoch seconds of the oldest tool call with no result yet, or None."""
    open_calls: dict[str, float] = {}
    with open(path) as f:
        for line in f:
            if '"tool_use"' not in line and '"tool_result"' not in line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            stamp = row.get("timestamp")
            when = (
                datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
                if stamp else time.time()
            )
            for block in (row.get("message") or {}).get("content") or []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use" and block.get("id"):
                    open_calls[block["id"]] = when
                elif block.get("type") == "tool_result":
                    open_calls.pop(block.get("tool_use_id", ""), None)
    return min(open_calls.values()) if open_calls else None


def read_seen(path: str) -> set[tuple[str, str]]:
    seen = set()
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                parts = line.split()
                if len(parts) == 2:
                    seen.add((parts[0], parts[1]))
    return seen


def append_seen(path: str, agent_id: str, kind: str) -> None:
    with open(path, "a") as f:
        f.write(f"{agent_id} {kind}\n")


def check_ci_red(branch: str, acked_path: str) -> str | None:
    try:
        out = subprocess.run(
            ["gh", "run", "list", "--branch", branch, "--limit", "1",
             "--json", "conclusion,databaseId"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        runs = json.loads(out.stdout or "[]")
    except (subprocess.SubprocessError, ValueError, OSError):
        return None
    if not runs:
        return None
    run = runs[0]
    if run.get("conclusion") != "failure":
        return None
    run_id = str(run.get("databaseId"))
    acked = set()
    if os.path.exists(acked_path):
        acked = {ln.strip() for ln in open(acked_path)}
    if run_id in acked:
        return None
    return f"CI-RED {branch} run {run_id} failed"


def check_long_shell(session_pid: str) -> str | None:
    try:
        out = subprocess.run(
            ["ps", "-eo", "pid,ppid,etime,comm"],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except OSError:
        return None
    for line in out.stdout.splitlines()[1:]:
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        pid, ppid, etime, comm = parts
        if ppid != session_pid:
            continue
        # Exact shell names only: a substring test matched "sh" inside
        # ".../Rush/bin/rush" (the session's own MCP server).
        if os.path.basename(comm.strip()).lstrip("-") not in ("bash", "zsh", "sh"):
            continue
        secs = parse_etime(etime)
        if secs >= LONG_SHELL_SECS:
            return f"LONG-SHELL pid {pid} running {secs}s"
    return None


def parse_etime(etime: str) -> int:
    """ps etime: [[dd-]hh:]mm:ss"""
    days = 0
    if "-" in etime:
        d, etime = etime.split("-", 1)
        days = int(d)
    bits = [int(x) for x in etime.split(":")]
    while len(bits) < 3:
        bits.insert(0, 0)
    h, m, s = bits
    return days * 86400 + h * 3600 + m * 60 + s


def check_idle_tasks(tasks_path: str) -> list[str]:
    """Mirrors run-state.sh task-graph logic: unblocked (all deps merged)
    tasks not running or merged are idle."""
    if not os.path.exists(tasks_path):
        return []
    status = {}
    deps = {}
    order = []
    with open(tasks_path) as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            tid, dep_csv, st = parts[0], parts[1], parts[2]
            deps[tid] = [d for d in dep_csv.split(",") if d]
            status[tid] = st
            order.append(tid)
    idle = []
    for tid in order:
        unblocked = all(status.get(d) == "merged" for d in deps[tid])
        if unblocked and status[tid] == "pending":
            idle.append(tid)
    return idle


def check_ready_low(sd: str, running: int, now: float | None = None) -> str | None:
    """Ready nodes waiting while fewer agents run than min(ready, 6) for 120 s."""
    now = time.time() if now is None else now
    marker = os.path.join(sd, "ready-low.since")
    idle = check_idle_tasks(os.path.join(sd, "tasks.tsv"))
    if not idle or running >= min(len(idle), 6):
        if os.path.exists(marker):
            os.remove(marker)
        return None
    if not os.path.exists(marker):
        with open(marker, "w") as f:
            f.write(str(now))
        return None
    since = float(open(marker).read())
    if now - since >= READY_LOW_SECS:
        return f"READY-LOW running={running} ready={len(idle)}: " + " ".join(idle[:6])
    return None


def _session_tool_uses(path: str):
    with open(path, errors="ignore") as f:
        for line in f:
            if '"tool_use"' not in line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            for b in (e.get("message") or {}).get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    yield b


def check_split(session_transcript: str) -> list[str]:
    """A plan task that has spawned more than 6 agents (task id read from the Agent description)."""
    per: dict[str, int] = {}
    for b in _session_tool_uses(session_transcript):
        if b["name"] == "Agent":
            m = re.search(r"\b(T\d+)\b", (b.get("input") or {}).get("description", ""))
            if m:
                per[m.group(1)] = per.get(m.group(1), 0) + 1
    return [f"SPLIT {t} has {n} agents" for t, n in sorted(per.items()) if n > SPLIT_MAX_AGENTS]


def check_resume(session_transcript: str) -> list[str]:
    """Any agent id that received more than one SendMessage that does not start with SCOPE:."""
    per: dict[str, int] = {}
    for b in _session_tool_uses(session_transcript):
        if b["name"] == "SendMessage":
            inp = b.get("input") or {}
            if not str(inp.get("message", "")).lstrip().startswith("SCOPE:"):
                to = inp.get("to", "")
                per[to] = per.get(to, 0) + 1
    return [f"RESUME {to} received {n} messages" for to, n in sorted(per.items()) if n > 1]


def check_suite_slow(sd: str) -> str | None:
    """The last gate suite run took more than 1.5x the median of the five before it (suite-times.tsv col 2)."""
    path = os.path.join(sd, "suite-times.tsv")
    if not os.path.exists(path):
        return None
    walls = [float(line.split("\t")[1]) for line in open(path) if line.count("\t") >= 4]
    if len(walls) < 4:
        return None
    prev = sorted(walls[-6:-1])
    median = prev[len(prev) // 2]
    if walls[-1] > SUITE_SLOW_FACTOR * median:
        return f"SUITE-SLOW last run {walls[-1]:.0f}s, median of the previous {len(prev)} is {median:.0f}s"
    return None


def _lead(cmd: str) -> str:
    s = cmd.strip()
    while True:
        m = re.match(r"(cd\s+\S+\s*(&&|;)\s*|\w+=\S+\s+|rtk proxy\s+|env\s+)", s)
        if not m:
            break
        s = s[m.end():]
    w = s.split()
    return "" if not w else ("rtk " + w[1] if w[0] == "rtk" and len(w) > 1 else w[0])


def check_orch_research(session_transcript: str) -> str | None:
    """More than 25% of the orchestrator's last 100 tool calls are reads, searches or graft/repowise queries."""
    uses = list(_session_tool_uses(session_transcript))[-RESEARCH_WINDOW:]
    if len(uses) < RESEARCH_WINDOW:
        return None
    research = sum(
        1 for b in uses
        if b["name"] in ("Read", "Grep", "Glob")
        or (b["name"] == "Bash" and _lead((b.get("input") or {}).get("command", "")) in _RESEARCH_LEAD)
    )
    if research / len(uses) > RESEARCH_LIMIT:
        return f"ORCH-RESEARCH {research} of the last {len(uses)} orchestrator tool calls are research: dispatch orch-scout"
    return None


_RAW_READ = re.compile(
    r"rtk proxy (sed|cat|head|tail|grep|rg|awk|wc)\b|(^|[;&|]\s*)sed -n\b"
    r"|\brtk (grep|find|ls)\b"
)
# A read of a file the agent goes on to Edit or Write is the read the guard requires, not exploration.
_RTK_READ = re.compile(r"\brtk read(?! --tail-lines)\s+(\S+)")
_SAVER = re.compile(
    r"\bgraft (ask|grep|skeleton|callers|map)\b|\brepowise (distill|expand|ask|context|why)\b"
    r"|\brtk (log|read --tail-lines)\b"
)
TOOLSTACK_WINDOW = 30
TOOLSTACK_MIN_RAW = 10


def tool_stack(path: str) -> tuple[int, int]:
    """(raw reads, saver calls) over the last TOOLSTACK_WINDOW tool calls.

    Raw reads: `rtk proxy sed/cat/head/tail/grep/rg/awk/wc` and `sed -n` in Bash,
    plus native Read with no limit or a limit over 40. Savers: graft and
    context-mode MCP calls, and graft/repowise/`rtk log` CLI calls."""
    uses: list[tuple[str, dict]] = []
    with open(path) as f:
        for line in f:
            if '"tool_use"' not in line:
                continue
            try:
                msg = json.loads(line)["message"]
            except (ValueError, KeyError, TypeError):
                continue
            for block in msg.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    uses.append((block.get("name", ""), block.get("input") or {}))
    edited = {str(a.get("file_path", "")) for n, a in uses if n in ("Edit", "Write")}
    calls: list[tuple[int, int]] = []
    for name, args in uses:
        raw = saver = 0
        if name == "Bash":
            cmd = str(args.get("command", ""))
            raw = len(_RAW_READ.findall(cmd))
            raw += sum(1 for p in _RTK_READ.findall(cmd) if p not in edited)
            saver = len(_SAVER.findall(cmd))
        elif name == "Read":
            limit = args.get("limit")
            raw = 1 if not limit or int(limit) > 40 else 0
        elif name.startswith(("mcp__graft", "mcp__plugin_context-mode")):
            saver = 1
        calls.append((raw, saver))
    recent = calls[-TOOLSTACK_WINDOW:]
    return sum(r for r, _ in recent), sum(s for _, s in recent)


def _toolstack_alert(label: str, path: str) -> str | None:
    raw, saver = tool_stack(path)
    if raw >= TOOLSTACK_MIN_RAW and raw > 3 * saver:
        return (f"TOOLSTACK {label}: {raw} raw reads vs {saver} graft/ctx/repowise "
                f"calls in the last {TOOLSTACK_WINDOW} tool calls")
    return None


def run_pass(run_dir: str, transcripts_dir: str, session_pid: str | None,
             ci_branch: str | None,
             session_transcript: str | None = None) -> list[tuple[str, str, str]]:
    """Returns list of (id, kind, message) for currently-firing alerts."""
    sd = state_dir(run_dir)
    seen_path = os.path.join(sd, "alerts.seen")
    seen = read_seen(seen_path)
    found: list[tuple[str, str, str]] = []
    evaluated: set[tuple[str, str]] = set()
    firing: set[tuple[str, str]] = set()

    def check(subject: str, kind: str, msg: str | None) -> None:
        """msg is the alert text when the condition holds, None when it is clear."""
        key = (subject, kind)
        evaluated.add(key)
        if msg is None:
            return
        firing.add(key)
        if key not in seen:
            found.append((subject, kind, msg))

    agents = read_agents_active(os.path.join(sd, "agents.active"))
    running = 0
    for agent_id, _turns, role in agents:
        path = os.path.join(transcripts_dir, f"agent-{agent_id}.jsonl")
        if not os.path.exists(path):
            running += 1            # dispatched, transcript not written yet
            continue
        if not finished(path):
            running += 1
        if finished(path):
            handed_back = time.time() - os.stat(path).st_mtime >= HANDED_BACK_SECS
            check(agent_id, "HANDED-BACK-OPEN",
                  f"HANDED-BACK-OPEN {agent_id} handed back and is still registered: close it out"
                  if handed_back else None)
            continue
        tokens, edited, base = scan_transcript(path)
        if role == "impl" and not edited and tokens - base >= ORIENT_TOKENS:
            check(agent_id, "ORIENTING",
                  f"ORIENTING {agent_id} {tokens - base} work tokens, no Edit/Write")
        scripted = scripted_edits(path)
        check(agent_id, "SCRIPT-EDIT",
              f"SCRIPT-EDIT {agent_id} wrote files through {scripted} Bash scripts (bypasses the read guard)"
              if scripted >= SCRIPT_EDIT_MIN else None)
        quiet = time.time() - os.stat(path).st_mtime
        pending = pending_since(path)
        # An agent waiting on a running tool call (a test suite) is working;
        # it is stalled only when nothing is pending or the call has run 60+ min.
        waiting = pending is not None and time.time() - pending < PENDING_OK_SECS
        check(agent_id, "QUIET",
              f"QUIET {agent_id} {int(quiet)}s at {tokens} tokens"
              if quiet > QUIET_SECS and not waiting else None)
        check(agent_id, "TOOLSTACK", _toolstack_alert(agent_id, path))

    if session_transcript and os.path.exists(session_transcript):
        check("orchestrator-session", "TOOLSTACK",
              _toolstack_alert("orchestrator-session", session_transcript))

    free = shutil.disk_usage("/").free / 2**30
    check("disk", "DISK", f"DISK {free:.1f} GiB" if free < DISK_MIN_GIB else None)

    if session_pid:
        check(session_pid, "LONG-SHELL", check_long_shell(session_pid))

    if ci_branch:
        check(ci_branch, "CI-RED", check_ci_red(ci_branch, os.path.join(sd, "ci-acked")))

    idle_now = check_idle_tasks(os.path.join(sd, "tasks.tsv"))
    for tid in idle_now:
        check(tid, "IDLE-TASK", f"IDLE-TASK {tid} unblocked, idle")
    for subject, kind in list(seen):
        if kind == "IDLE-TASK" and subject not in idle_now:
            evaluated.add((subject, kind))

    check("ready", "READY-LOW", check_ready_low(sd, running))
    check("suite", "SUITE-SLOW", check_suite_slow(sd))
    if session_transcript and os.path.exists(session_transcript):
        for msg in check_split(session_transcript):
            check(msg.split()[1], "SPLIT", msg)
        for msg in check_resume(session_transcript):
            check(msg.split()[1], "RESUME", msg)
        check("orchestrator-session", "ORCH-RESEARCH", check_orch_research(session_transcript))

    cleared = {k for k in seen if k in evaluated and k[1] in RECURRING and k not in firing}
    if cleared:
        with open(seen_path, "w") as f:
            for subject, kind in sorted(seen - cleared):
                f.write(f"{subject} {kind}\n")

    for agent_id, kind, msg in found:
        print(msg)
        append_seen(seen_path, agent_id, kind)
    if found:
        # One closing line naming every alert, so a tail read never drops one.
        print(f"ALERTS {len(found)}: " + "; ".join(f"{a} {k}" for a, k, _ in found))
    return found


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("run_dir")
    p.add_argument("transcripts_dir")
    p.add_argument("--session-pid")
    p.add_argument("--ci-branch")
    p.add_argument("--session-transcript")
    p.add_argument("--once", action="store_true")
    p.add_argument("--status", action="store_true", help="print registered/running/finished-open agent counts and exit")
    args = p.parse_args()

    if args.status:
        agents = read_agents_active(os.path.join(state_dir(args.run_dir), "agents.active"))
        done = sum(1 for a, _t, _r in agents
                   if os.path.exists(os.path.join(args.transcripts_dir, f"agent-{a}.jsonl"))
                   and finished(os.path.join(args.transcripts_dir, f"agent-{a}.jsonl")))
        print(f"registered={len(agents)} running={len(agents) - done} finished-open={done}")
        return 0

    if args.once:
        alerts = run_pass(args.run_dir, args.transcripts_dir, args.session_pid,
                          args.ci_branch, args.session_transcript)
        return 1 if alerts else 0

    while True:
        alerts = run_pass(args.run_dir, args.transcripts_dir, args.session_pid,
                          args.ci_branch, args.session_transcript)
        if alerts:
            return EXIT_CODE.get(alerts[0][1], 1)
        time.sleep(60)


if __name__ == "__main__":
    sys.exit(main())
