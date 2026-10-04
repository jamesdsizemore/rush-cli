#!/usr/bin/env python3
"""Fixture test for monitor.py: BUDGET, ORIENTING, QUIET, IDLE-TASK, CI-RED
alerts, dedup via alerts.seen, and the parse_etime helper. No network (gh is
stubbed on PATH).
"""

import json
import os
import subprocess
import sys
import tempfile
import time

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "monitor.py")
sys.path.insert(0, os.path.dirname(SCRIPT))
import monitor  # noqa: E402


def usage_line(tokens: int, edited: bool = False) -> str:
    content = [{"type": "tool_use", "name": "Edit"}] if edited else []
    return json.dumps({"message": {"usage": {"input_tokens": tokens}, "content": content}}) + "\n"


def write_transcript(path: str, lines: list[str]) -> None:
    with open(path, "w") as f:
        f.writelines(lines)


def run_once(run_dir: str, transcripts_dir: str, ci_branch: str | None = None) -> tuple[int, str]:
    cmd = [sys.executable, SCRIPT, run_dir, transcripts_dir, "--once"]
    if ci_branch:
        cmd += ["--ci-branch", ci_branch]
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout


def main() -> int:
    fail = 0

    # parse_etime unit checks
    assert monitor.parse_etime("05:00") == 300
    assert monitor.parse_etime("1:05:00") == 3900
    assert monitor.parse_etime("2-01:00:00") == 2 * 86400 + 3600

    with tempfile.TemporaryDirectory() as run_dir, tempfile.TemporaryDirectory() as tdir:
        agents_active = os.path.join(run_dir, ".orchestrator")
        os.makedirs(agents_active, exist_ok=True)
        with open(os.path.join(agents_active, "agents.active"), "w") as f:
            f.write("agent1 1000 impl\n")
            f.write("agent2 100000 review\n")

        # agent1: impl role, big token jump, no edit -> ORIENTING
        write_transcript(os.path.join(tdir, "agent-agent1.jsonl"), [usage_line(1000), usage_line(60000)])
        # agent2: no edit, but role=review so no ORIENTING
        write_transcript(os.path.join(tdir, "agent-agent2.jsonl"), [usage_line(50000)])

        code, out = run_once(run_dir, tdir)
        if "ORIENTING agent1" not in out:
            print(f"FAIL: expected ORIENTING alert, got: {out!r}")
            fail = 1
        if "agent2" in out:
            print(f"FAIL: a review agent must not alert, got: {out!r}")
            fail = 1
        if code == 0:
            print("FAIL: expected non-zero exit when an alert fires")
            fail = 1
        if "BUDGET" in out:
            print(f"FAIL: the token-budget alerts are gone, got: {out!r}")
            fail = 1

        # second pass: same conditions must not re-alert (dedup via alerts.seen)
        code2, out2 = run_once(run_dir, tdir)
        if "ORIENTING agent1" in out2:
            print(f"FAIL: ORIENTING agent1 should be deduped on second pass, got: {out2!r}")
            fail = 1

    # ORIENTING: impl role, big token jump, no edit
    with tempfile.TemporaryDirectory() as run_dir, tempfile.TemporaryDirectory() as tdir:
        agents_dir = os.path.join(run_dir, ".orchestrator")
        os.makedirs(agents_dir, exist_ok=True)
        with open(os.path.join(agents_dir, "agents.active"), "w") as f:
            f.write("agent3 1000000 impl\n")
        write_transcript(
            os.path.join(tdir, "agent-agent3.jsonl"),
            [usage_line(1000), usage_line(50000)],
        )
        code, out = run_once(run_dir, tdir)
        if "ORIENTING agent3" not in out:
            print(f"FAIL: expected ORIENTING alert, got: {out!r}")
            fail = 1

    # QUIET: old mtime, under budget, edited (so no ORIENTING/BUDGET noise)
    with tempfile.TemporaryDirectory() as run_dir, tempfile.TemporaryDirectory() as tdir:
        agents_dir = os.path.join(run_dir, ".orchestrator")
        os.makedirs(agents_dir, exist_ok=True)
        with open(os.path.join(agents_dir, "agents.active"), "w") as f:
            f.write("agent4 1000000 impl\n")
        path = os.path.join(tdir, "agent-agent4.jsonl")
        write_transcript(path, [usage_line(500, edited=True)])
        old = time.time() - 600
        os.utime(path, (old, old))
        code, out = run_once(run_dir, tdir)
        if "QUIET agent4" not in out:
            print(f"FAIL: expected QUIET alert, got: {out!r}")
            fail = 1

    # Not QUIET: same old mtime, but a tool call started 10 min ago has no
    # result yet (an agent waiting on its test suite is working).
    with tempfile.TemporaryDirectory() as run_dir, tempfile.TemporaryDirectory() as tdir:
        agents_dir = os.path.join(run_dir, ".orchestrator")
        os.makedirs(agents_dir, exist_ok=True)
        with open(os.path.join(agents_dir, "agents.active"), "w") as f:
            f.write("agent4b 1000000 impl\n")
        path = os.path.join(tdir, "agent-agent4b.jsonl")
        started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 600))
        pending = json.dumps({
            "timestamp": started,
            "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Bash"}]},
        }) + "\n"
        write_transcript(path, [usage_line(500, edited=True), pending])
        old = time.time() - 600
        os.utime(path, (old, old))
        code, out = run_once(run_dir, tdir)
        if "QUIET agent4b" in out:
            print(f"FAIL: pending tool call still raised QUIET: {out!r}")
            fail = 1

    # TOOLSTACK: 12 `rtk proxy sed -n` reads and no graft/ctx/repowise call
    # alerts; the same transcript with 4 graft calls added does not.
    with tempfile.TemporaryDirectory() as run_dir, tempfile.TemporaryDirectory() as tdir:
        agents_dir = os.path.join(run_dir, ".orchestrator")
        os.makedirs(agents_dir, exist_ok=True)
        with open(os.path.join(agents_dir, "agents.active"), "w") as f:
            f.write("agent5 1000000 impl\nagent6 1000000 impl\n")

        def bash(cmd: str) -> str:
            return json.dumps({"message": {"content": [
                {"type": "tool_use", "name": "Bash", "input": {"command": cmd}}]}}) + "\n"

        raw = [bash("rtk proxy sed -n 1,50p src/x.py")] * 12
        write_transcript(os.path.join(tdir, "agent-agent5.jsonl"),
                         [usage_line(500, edited=True), *raw])
        write_transcript(os.path.join(tdir, "agent-agent6.jsonl"),
                         [usage_line(500, edited=True), *raw[:6],
                          *[bash('graft ask "where is x" --source')] * 4])
        code, out = run_once(run_dir, tdir)
        if "TOOLSTACK agent5" not in out:
            print(f"FAIL: expected TOOLSTACK alert for agent5, got: {out!r}")
            fail = 1
        if "TOOLSTACK agent6" in out:
            print(f"FAIL: agent6 uses graft and must not alert: {out!r}")
            fail = 1

    # IDLE-TASK: unblocked pending task in tasks.tsv
    with tempfile.TemporaryDirectory() as run_dir, tempfile.TemporaryDirectory() as tdir:
        agents_dir = os.path.join(run_dir, ".orchestrator")
        os.makedirs(agents_dir, exist_ok=True)
        with open(os.path.join(agents_dir, "agents.active"), "w") as f:
            pass
        with open(os.path.join(agents_dir, "tasks.tsv"), "w") as f:
            f.write("A\t\tpending\n")
        code, out = run_once(run_dir, tdir)
        if "IDLE-TASK A" not in out:
            print(f"FAIL: expected IDLE-TASK alert, got: {out!r}")
            fail = 1

    # CI-RED: stub gh on PATH to report a failed run, not yet acked
    with tempfile.TemporaryDirectory() as run_dir, tempfile.TemporaryDirectory() as tdir, \
         tempfile.TemporaryDirectory() as bindir:
        agents_dir = os.path.join(run_dir, ".orchestrator")
        os.makedirs(agents_dir, exist_ok=True)
        with open(os.path.join(agents_dir, "agents.active"), "w") as f:
            pass
        gh_stub = os.path.join(bindir, "gh")
        with open(gh_stub, "w") as f:
            f.write('#!/usr/bin/env bash\necho \'[{"conclusion":"failure","databaseId":42}]\'\n')
        os.chmod(gh_stub, 0o755)
        env = dict(os.environ)
        env["PATH"] = bindir + os.pathsep + env["PATH"]
        p = subprocess.run(
            [sys.executable, SCRIPT, run_dir, tdir, "--once", "--ci-branch", "main"],
            capture_output=True, text=True, env=env,
        )
        if "CI-RED main run 42 failed" not in p.stdout:
            print(f"FAIL: expected CI-RED alert, got: {p.stdout!r}")
            fail = 1
        # ack it, re-run: must not repeat
        with open(os.path.join(agents_dir, "ci-acked"), "w") as f:
            f.write("42\n")
        p2 = subprocess.run(
            [sys.executable, SCRIPT, run_dir, tdir, "--once", "--ci-branch", "main"],
            capture_output=True, text=True, env=env,
        )
        if "CI-RED" in p2.stdout:
            print(f"FAIL: acked CI-RED should not repeat, got: {p2.stdout!r}")
            fail = 1

    # F34: NEAR-BUDGET at 70% of budget, before the overrun; and a run_dir that
    # is itself the .orchestrator state dir is read in place (never nested).
    with tempfile.TemporaryDirectory() as run_dir, tempfile.TemporaryDirectory() as tdir:
        sd = os.path.join(run_dir, ".orchestrator")
        os.makedirs(sd)
        with open(os.path.join(sd, "agents.active"), "w") as f:
            f.write("agent7 100 impl\n")
        write_transcript(os.path.join(tdir, "agent-agent7.jsonl"),
                         [usage_line(52000), usage_line(60000)])
        code, out = run_once(sd, tdir)
        if "ORIENTING" in out:
            print(f"FAIL: ORIENTING below the work-token threshold: {out!r}")
            fail = 1
        write_transcript(os.path.join(tdir, "agent-agent7.jsonl"),
                         [usage_line(52000), usage_line(100000)])
        code, out = run_once(sd, tdir)
        if "ORIENTING agent7" not in out:
            print(f"FAIL: expected ORIENTING alert via the state dir itself, got: {out!r}")
            fail = 1
        if os.path.exists(os.path.join(sd, ".orchestrator")):
            print("FAIL: monitor created a nested .orchestrator/.orchestrator state dir")
            fail = 1

    # F34: a Bash script edit (write_text) counts as an edit for ORIENTING.
    with tempfile.TemporaryDirectory() as run_dir, tempfile.TemporaryDirectory() as tdir:
        sd = os.path.join(run_dir, ".orchestrator"); os.makedirs(sd)
        with open(os.path.join(sd, "agents.active"), "w") as f:
            f.write("agent8 900000 impl\n")
        script = json.dumps({"message": {"usage": {"input_tokens": 100000}, "content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": "python3 -c 'p.write_text(s)'"}}]}}) + "\n"
        write_transcript(os.path.join(tdir, "agent-agent8.jsonl"), [usage_line(10000), script])
        code, out = run_once(run_dir, tdir)
        if "ORIENTING agent8" in out:
            print(f"FAIL: a script edit must count as an edit, got: {out!r}")
            fail = 1

    # Plan E4/F25: one exit-code table, and a finished agent is HANDED-BACK-OPEN, not QUIET or ORIENTING.
    if len(set(monitor.EXIT_CODE.values())) != len(monitor.EXIT_CODE):
        print(f"FAIL: two alert kinds share an exit code: {monitor.EXIT_CODE}")
        fail = 1
    for name, tail in (
        ("h1", json.dumps({"type": "system", "subtype": "hook", "hookEvent": "SubagentStop"}) + "\n"),
        ("h2", json.dumps({"type": "assistant", "message": {"stop_reason": "end_turn", "content": []}}) + "\n"),
    ):
        with tempfile.TemporaryDirectory() as run_dir, tempfile.TemporaryDirectory() as tdir:
            sd = os.path.join(run_dir, ".orchestrator"); os.makedirs(sd)
            with open(os.path.join(sd, "agents.active"), "w") as f:
                f.write(f"{name} 100 impl\n")
            path = os.path.join(tdir, f"agent-{name}.jsonl")
            write_transcript(path, [usage_line(1000), usage_line(90000), tail])
            old = time.time() - 900
            os.utime(path, (old, old))
            code, out = run_once(run_dir, tdir)
            if f"HANDED-BACK-OPEN {name}" not in out:
                print(f"FAIL: finished agent {name} not reported: {out!r}")
                fail = 1
            if "QUIET" in out or "ORIENTING" in out:
                print(f"FAIL: finished agent {name} raised a false alarm: {out!r}")
                fail = 1
            os.utime(path, None)
            code, out = run_once(run_dir, tdir)
            if "HANDED-BACK-OPEN" in out or "QUIET" in out:
                print(f"FAIL: agent that finished a moment ago must not alert yet: {out!r}")
                fail = 1

    # Plan F25: a condition that clears and returns alerts again (episode re-arming).
    with tempfile.TemporaryDirectory() as run_dir, tempfile.TemporaryDirectory() as tdir:
        sd = os.path.join(run_dir, ".orchestrator"); os.makedirs(sd)
        with open(os.path.join(sd, "agents.active"), "w") as f:
            f.write("agent9 100 review\n")
        path = os.path.join(tdir, "agent-agent9.jsonl")
        write_transcript(path, [usage_line(500)])
        old = time.time() - 600
        os.utime(path, (old, old))
        code, out = run_once(run_dir, tdir)
        if "QUIET agent9" not in out:
            print(f"FAIL: first quiet episode not reported: {out!r}")
            fail = 1
        code, out = run_once(run_dir, tdir)
        if "QUIET agent9" in out:
            print(f"FAIL: the same quiet episode repeated: {out!r}")
            fail = 1
        os.utime(path, None)
        code, out = run_once(run_dir, tdir)
        if out.strip():
            print(f"FAIL: a recovered agent alerted: {out!r}")
            fail = 1
        os.utime(path, (old, old))
        code, out = run_once(run_dir, tdir)
        if "QUIET agent9" not in out:
            print(f"FAIL: the second quiet episode was suppressed forever: {out!r}")
            fail = 1

    # Plan F26: a read of a file the agent then edits is not exploration; unrelated reads are.
    with tempfile.TemporaryDirectory() as run_dir, tempfile.TemporaryDirectory() as tdir:
        sd = os.path.join(run_dir, ".orchestrator"); os.makedirs(sd)
        with open(os.path.join(sd, "agents.active"), "w") as f:
            f.write("agentA 100 review\nagentB 100 review\n")

        def call(name: str, **inp: object) -> str:
            return json.dumps({"message": {"content": [
                {"type": "tool_use", "name": name, "input": inp}]}}) + "\n"

        paired: list[str] = []
        for i in range(12):
            paired += [call("Bash", command=f"rtk read /w/f{i}.py --max-lines 20"),
                       call("Edit", file_path=f"/w/f{i}.py")]
        wander = [call("Bash", command=f"rtk read /w/g{i}.py") for i in range(12)]
        write_transcript(os.path.join(tdir, "agent-agentA.jsonl"), [usage_line(500), *paired])
        write_transcript(os.path.join(tdir, "agent-agentB.jsonl"), [usage_line(500), *wander])
        code, out = run_once(run_dir, tdir)
        if "TOOLSTACK agentA" in out:
            print(f"FAIL: reads that precede an Edit of the same file are compliant: {out!r}")
            fail = 1
        if "TOOLSTACK agentB" not in out:
            print(f"FAIL: unpaired whole-file reads must alert: {out!r}")
            fail = 1

    # Plan X6/X11 alerts folded into the one monitor: READY-LOW, SPLIT, RESUME, SUITE-SLOW, ORCH-RESEARCH.
    def call(name: str, **inp: object) -> str:
        return json.dumps({"message": {"content": [{"type": "tool_use", "name": name, "input": inp}]}}) + "\n"

    def run_with_session(run_dir: str, tdir: str, session: str) -> str:
        p = subprocess.run([sys.executable, SCRIPT, run_dir, tdir, "--once", "--session-transcript", session],
                           capture_output=True, text=True)
        return p.stdout

    with tempfile.TemporaryDirectory() as run_dir, tempfile.TemporaryDirectory() as tdir:
        sd = os.path.join(run_dir, ".orchestrator"); os.makedirs(sd)
        open(os.path.join(sd, "agents.active"), "w").close()
        with open(os.path.join(sd, "tasks.tsv"), "w") as f:
            f.write("T1\t\tpending\t\nT2\t\tpending\t\nT3\t\tpending\t\n")
        run_once(run_dir, tdir)                                   # starts the READY-LOW clock, alerts IDLE-TASK
        with open(os.path.join(sd, "ready-low.since"), "w") as f:
            f.write(str(time.time() - 130))
        code, out = run_once(run_dir, tdir)
        if "READY-LOW running=0 ready=3" not in out:
            print(f"FAIL: READY-LOW not reported after 120 s with nothing running: {out!r}")
            fail = 1

    with tempfile.TemporaryDirectory() as run_dir, tempfile.TemporaryDirectory() as tdir:
        sd = os.path.join(run_dir, ".orchestrator"); os.makedirs(sd)
        open(os.path.join(sd, "agents.active"), "w").close()
        session = os.path.join(tdir, "session.jsonl")
        lines = [call("Agent", description=f"T5 fix {i}") for i in range(7)]
        lines += [call("SendMessage", to="aX", message="again"), call("SendMessage", to="aX", message="more"),
                  call("SendMessage", to="aY", message="first"), call("SendMessage", to="aY", message="SCOPE: also T2")]
        write_transcript(session, lines)
        out = run_with_session(run_dir, tdir, session)
        if "SPLIT T5 has 7 agents" not in out:
            print(f"FAIL: SPLIT not reported: {out!r}")
            fail = 1
        if "RESUME aX received 2 messages" not in out or "RESUME aY" in out:
            print(f"FAIL: RESUME must count aX and skip a SCOPE: correction to aY: {out!r}")
            fail = 1

    with tempfile.TemporaryDirectory() as run_dir, tempfile.TemporaryDirectory() as tdir:
        sd = os.path.join(run_dir, ".orchestrator"); os.makedirs(sd)
        open(os.path.join(sd, "agents.active"), "w").close()
        rows = [750, 760, 740, 755, 745, 1400]
        with open(os.path.join(sd, "suite-times.tsv"), "w") as f:
            for w in rows:
                f.write(f"2026-01-01T00:00:00Z\t{w}\t6000\t2\t0\n")
        code, out = run_once(run_dir, tdir)
        if "SUITE-SLOW last run 1400s, median of the previous 5 is 750s" not in out:
            print(f"FAIL: SUITE-SLOW not reported: {out!r}")
            fail = 1
    with tempfile.TemporaryDirectory() as run_dir, tempfile.TemporaryDirectory() as tdir:
        sd = os.path.join(run_dir, ".orchestrator"); os.makedirs(sd)
        open(os.path.join(sd, "agents.active"), "w").close()
        with open(os.path.join(sd, "suite-times.tsv"), "w") as f:
            for w in [750, 760, 740, 755, 745, 800]:
                f.write(f"2026-01-01T00:00:00Z\t{w}\t6000\t2\t0\n")
        code, out = run_once(run_dir, tdir)
        if "SUITE-SLOW" in out:
            print(f"FAIL: a 800 s run against a 750 s median is not slow: {out!r}")
            fail = 1

    with tempfile.TemporaryDirectory() as run_dir, tempfile.TemporaryDirectory() as tdir:
        sd = os.path.join(run_dir, ".orchestrator"); os.makedirs(sd)
        open(os.path.join(sd, "agents.active"), "w").close()
        session = os.path.join(tdir, "session.jsonl")
        mix = [call("Bash", command="rtk grep -n foo src")] * 30 + [call("Edit", file_path="/w/x.py")] * 70
        write_transcript(session, mix)
        out = run_with_session(run_dir, tdir, session)
        if "ORCH-RESEARCH 30 of the last 100" not in out:
            print(f"FAIL: ORCH-RESEARCH not reported at 30 of 100: {out!r}")
            fail = 1
        write_transcript(session, [call("Bash", command="rtk grep -n foo src")] * 10 + [call("Edit", file_path="/w/x.py")] * 90)
        out = run_with_session(run_dir, tdir, session)
        if "ORCH-RESEARCH" in out:
            print(f"FAIL: ORCH-RESEARCH at 10 of 100: {out!r}")
            fail = 1

    # Plan E4: writing files through Bash scripts is reported.
    with tempfile.TemporaryDirectory() as run_dir, tempfile.TemporaryDirectory() as tdir:
        sd = os.path.join(run_dir, ".orchestrator"); os.makedirs(sd)
        with open(os.path.join(sd, "agents.active"), "w") as f:
            f.write("agentC 100 impl\n")
        s = json.dumps({"message": {"content": [{"type": "tool_use", "name": "Bash",
                        "input": {"command": "python3 -c 'p.write_text(s)'"}}]}}) + "\n"
        write_transcript(os.path.join(tdir, "agent-agentC.jsonl"), [usage_line(500), s, s, s])
        code, out = run_once(run_dir, tdir)
        if "SCRIPT-EDIT agentC" not in out:
            print(f"FAIL: script writes were not reported: {out!r}")
            fail = 1

    # Plan E3/F28: --status separates registered, running and finished-open agents from the transcripts.
    with tempfile.TemporaryDirectory() as run_dir, tempfile.TemporaryDirectory() as tdir:
        sd = os.path.join(run_dir, ".orchestrator"); os.makedirs(sd)
        with open(os.path.join(sd, "agents.active"), "w") as f:
            f.write("done1 100 impl\nwork1 100 impl\nnew1 100 impl\n")
        end = json.dumps({"type": "assistant", "message": {"stop_reason": "end_turn", "content": []}}) + "\n"
        write_transcript(os.path.join(tdir, "agent-done1.jsonl"), [usage_line(1000), end])
        write_transcript(os.path.join(tdir, "agent-work1.jsonl"), [usage_line(1000)])
        p = subprocess.run([sys.executable, SCRIPT, run_dir, tdir, "--status"], capture_output=True, text=True)
        if p.stdout.strip() != "registered=3 running=2 finished-open=1":
            print(f"FAIL: --status must count one finished-open agent, got: {p.stdout!r}")
            fail = 1

    if fail:
        print("test_monitor.py: FAIL")
        return 1
    print("test_monitor.py: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
