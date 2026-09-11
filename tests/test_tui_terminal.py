"""Real terminal-interaction tests for the persistent TUI (P66-03, F36).

Every test here drives an actual POSIX pseudo-terminal (`pty.fork`/
`pty.openpty`, stdlib) -- real raw-mode keystrokes and a real resized
window, never a scripted in-process fake reader. Windows console PTY
journeys are a named, honest platform-lane gap in this environment (no
Windows console is reachable from this POSIX CI/dev machine) -- see T304's
`stop_if`; `tests/test_tui.py` already exercises the same dispatch logic
platform-independently via the injectable `KeyReader` seam.
"""

from __future__ import annotations

import fcntl
import json
import os
import runpy
import select
import struct
import sys
import termios
import threading
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="these tests require a POSIX pty"
)

_REPO_SRC = str(Path(__file__).resolve().parent.parent / "src")

_HARNESS_TEMPLATE = """
import json, sys
from pathlib import Path
sys.path.insert(0, {src_root!r})
from rush.tui import ProjectSeed, ScanActions, run_interactive_tui
from rush.tools.base import Finding, ToolResult

{actions_src}

# Imports (rich, rush.*) are the dominant startup cost -- signal readiness
# right after they finish, before the parent sends any keystroke. Without
# this, a keystroke sent while the child is still importing lands before
# `raw_terminal()` calls `tty.setcbreak` (which uses TCSAFLUSH by default
# and silently discards any input queued before it runs) -- a genuine
# test-harness race, not a production bug.
Path({ready_path!r}).write_text("ready")

seeds = [
    ProjectSeed(name="alpha", root=Path("/tmp/rush-tui-pty-alpha"), results=[
        ToolResult(tool="lint", status="fail", duration_ms=1, summary="x", findings=[
            Finding(path="a.py", line=1, column=1, rule="F1", message="alpha finding one", severity="error"),
            Finding(path="b.py", line=2, column=1, rule="F2", message="alpha finding two", severity="warn"),
        ]),
    ]),
    ProjectSeed(name="beta", root=Path("/tmp/rush-tui-pty-beta"), results=[
        ToolResult(tool="lint", status="fail", duration_ms=1, summary="x", findings=[
            Finding(path="c.py", line=3, column=1, rule="F3", message="beta finding one", severity="info"),
        ]),
    ]),
]
state = run_interactive_tui(seeds, max_ticks=3000, tick_seconds=0.02, actions={actions_expr})
Path({result_path!r}).write_text(json.dumps(state.to_dict()))
"""

_NOOP_ACTIONS_SRC = """
def _noop(*a, **k):
    return None

actions = ScanActions(
    plan_scan=lambda *a, **k: type("P", (), {"candidates": []})(),
    execute_scan=lambda *a, **k: type("R", (), {"aggregate": {}})(),
    cancel_scan_run=_noop,
    rescan_project_run=_noop,
    build_handoff=_noop,
    dispatch_handoff=_noop,
    load_scan_events=lambda *a, **k: {"events": [], "run_state": None},
    list_agents=lambda: [],
)
"""


def _set_pty_size(fd: int, rows: int, cols: int) -> None:
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


def _run_pty_harness(
    tmp_path: Path,
    *,
    actions_src: str = _NOOP_ACTIONS_SRC,
    actions_expr: str = "actions",
    rows: int = 24,
    cols: int = 80,
) -> tuple[int, int, Path]:
    import pty

    result_path = tmp_path / "result.json"
    error_path = tmp_path / "result.json.error"
    ready_path = tmp_path / "ready"
    harness_src = _HARNESS_TEMPLATE.format(
        src_root=_REPO_SRC,
        actions_src=actions_src,
        actions_expr=actions_expr,
        result_path=str(result_path),
        ready_path=str(ready_path),
    )
    # Written to a real file and run via `runpy.run_path` rather than
    # `exec(compile(...))`: this is a controlled, locally-authored harness
    # script (never user/external input), and running it as an actual
    # module import path avoids the raw `exec` builtin entirely.
    harness_path = tmp_path / "harness.py"
    harness_path.write_text(harness_src)

    pid, master_fd = pty.fork()
    if pid == 0:
        try:
            _set_pty_size(0, rows, cols)
            runpy.run_path(str(harness_path), run_name="__main__")
        except BaseException as exc:  # noqa: BLE001 -- child-process diagnostics
            # only: this is the forked test child's last chance to record
            # ANY failure (including exotic ones) to `error_path` before
            # `os._exit(0)` below discards it silently; the parent test
            # asserts on `error_path` via `_collect`.
            try:
                error_path.write_text(repr(exc))
            except OSError:
                pass
        os._exit(0)

    _set_pty_size(master_fd, rows, cols)
    _start_drain_thread(master_fd)
    _wait_ready(ready_path)
    time.sleep(0.05)  # small margin past the readiness marker into `raw_terminal()`
    return pid, master_fd, result_path


def _wait_ready(ready_path: Path, *, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if ready_path.exists():
            return
        time.sleep(0.02)
    raise AssertionError("pty harness never signalled readiness")


def _start_drain_thread(master_fd: int) -> None:
    """A real terminal emulator continuously reads the pty master; nothing
    else does here. Without a drain, Rich's Live re-renders eventually fill
    the kernel pty buffer and the child's next `write()` blocks forever --
    a test-harness deadlock, not a production bug. Runs until `master_fd`
    is closed by the caller."""

    def _drain() -> None:
        while True:
            try:
                ready, _, _ = select.select([master_fd], [], [], 0.05)
            except OSError:
                return
            if not ready:
                continue
            try:
                chunk = os.read(master_fd, 65536)
            except OSError:
                return
            if not chunk:
                return

    threading.Thread(target=_drain, daemon=True).start()


def _send(master_fd: int, data: str, *, settle: float = 0.08) -> None:
    os.write(master_fd, data.encode())
    time.sleep(settle)


def _collect(
    pid: int, master_fd: int, result_path: Path, *, timeout: float = 8.0
) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not result_path.exists():
        time.sleep(0.05)
    os.waitpid(pid, 0)
    os.close(master_fd)
    error_path = Path(str(result_path) + ".error")
    if error_path.exists():
        raise AssertionError(f"pty harness raised: {error_path.read_text()}")
    assert result_path.exists(), "pty harness never wrote a result"
    return json.loads(result_path.read_text())


def test_pty_resize_updates_terminal_size(
    tmp_path: Path, capfd: pytest.CaptureFixture
) -> None:
    # `capfd.disabled()`: pytest's fd-level output capture doesn't survive
    # `pty.fork()` cleanly -- the forked child's writes race the harness's
    # capture pipes and the parent's later writes to the pty master start
    # raising EIO. Real terminal output isn't under test here (the PTY
    # itself is); disabling capture for the fork+drive+collect window is
    # the standard fix for fork-based pty tests under pytest.
    with capfd.disabled():
        pid, master_fd, result_path = _run_pty_harness(tmp_path, rows=24, cols=80)
        _set_pty_size(master_fd, rows=30, cols=100)
        time.sleep(0.2)
        _send(master_fd, "q")
        state = _collect(pid, master_fd, result_path)

    assert state["terminal_size"] == [100, 30]


def test_keyboard_project_switch(tmp_path: Path, capfd: pytest.CaptureFixture) -> None:
    with capfd.disabled():
        pid, master_fd, result_path = _run_pty_harness(tmp_path)
        _send(master_fd, "\t")  # tab -> next_project
        _send(master_fd, "q")
        state = _collect(pid, master_fd, result_path)

    assert state["active_project"] == "beta"
    assert state["active_index"] == 1


def test_search_filter_narrows_findings(
    tmp_path: Path, capfd: pytest.CaptureFixture
) -> None:
    with capfd.disabled():
        pid, master_fd, result_path = _run_pty_harness(tmp_path)
        _send(master_fd, "/")  # focus_filter
        _send(master_fd, "alpha")
        _send(master_fd, "\r")  # enter -> confirm filter, back to list
        _send(master_fd, "q")
        state = _collect(pid, master_fd, result_path)

    assert state["mode"] == "list"
    assert state["filter_text"] == "alpha"


def test_escape_cancels_search_without_keeping_filter(
    tmp_path: Path, capfd: pytest.CaptureFixture
) -> None:
    with capfd.disabled():
        pid, master_fd, result_path = _run_pty_harness(tmp_path)
        _send(master_fd, "/")
        _send(master_fd, "xyz")
        _send(master_fd, "\x1b")  # escape -> discard filter, back to list
        _send(master_fd, "q")
        state = _collect(pid, master_fd, result_path)

    assert state["mode"] == "list"
    assert state["filter_text"] == ""


_CANCEL_ACTIONS_SRC = """
import time as _time

_cancel_flag = {"requested": False}
_events = {"events": [], "run_state": "running"}
_TOTAL = 40

def _plan_scan(root, **kw):
    return type("P", (), {"candidates": list(range(_TOTAL))})()

def _execute_scan(plan, *, run_id=None, **kw):
    for _ in range(_TOTAL):
        if _cancel_flag["requested"]:
            _events["run_state"] = "cancelled"
            return type("R", (), {"aggregate": {}})()
        _time.sleep(0.03)
        _events["events"].append({"event": "candidate_completed"})
    _events["run_state"] = "completed"
    return type("R", (), {"aggregate": {}})()

def _cancel_scan_run(root, run_id, **kw):
    _cancel_flag["requested"] = True
    return {}

def _load_scan_events(root, run_id, attempt_id=None):
    return dict(_events)

def _noop(*a, **k):
    return None

actions = ScanActions(
    plan_scan=_plan_scan,
    execute_scan=_execute_scan,
    cancel_scan_run=_cancel_scan_run,
    rescan_project_run=_noop,
    build_handoff=_noop,
    dispatch_handoff=_noop,
    load_scan_events=_load_scan_events,
    list_agents=lambda: [],
)
"""


def test_scan_start_and_cancellation_retains_partial_progress(
    tmp_path: Path, capfd: pytest.CaptureFixture
) -> None:
    with capfd.disabled():
        pid, master_fd, result_path = _run_pty_harness(
            tmp_path, actions_src=_CANCEL_ACTIONS_SRC
        )
        _send(master_fd, "s")  # start_scan -> grant review
        _send(master_fd, "y", settle=0.15)  # confirm -> real background scan starts
        time.sleep(0.12)  # let 1-2 candidates complete first
        _send(master_fd, "c")  # cancel_scan -> cooperative cancel request
        time.sleep(0.3)  # let the worker thread observe the cancel flag and stop
        _send(master_fd, "q")
        state = _collect(pid, master_fd, result_path)

    assert state["status"] == "cancelled"
    history = state["progress_history"]
    assert history, "expected at least one progress observation before cancellation"
    assert history[-1]["executed"] < history[-1]["total"], (
        "scan should have stopped early, not run to completion"
    )


def test_terminal_restored_after_error_inside_raw_mode() -> None:
    """Direct test of the actual restoration mechanism (`raw_terminal`):
    entering cbreak mode, then an exception mid-body, still restores the
    real terminal's original attributes. Uses `pty.openpty` directly (no
    fork needed) so the assertion is on the same process's own tcgetattr
    read, with zero PTY-timing flakiness."""
    import pty

    sys.path.insert(0, _REPO_SRC)
    from rush.dashboard.terminal_input import raw_terminal

    master_fd, slave_fd = pty.openpty()
    try:
        stream = os.fdopen(slave_fd, "rb", buffering=0, closefd=False)
        original = termios.tcgetattr(slave_fd)

        class _Boom(Exception):
            pass

        with pytest.raises(_Boom), raw_terminal(stream):
            during = termios.tcgetattr(slave_fd)
            assert during != original  # really entered cbreak mode
            raise _Boom("scan crashed mid-render")

        restored = termios.tcgetattr(slave_fd)
        # Darwin's tty driver sets the PENDIN ("retype pending input")
        # state bit on some tcsetattr(TCSADRAIN) transitions -- pure kernel
        # bookkeeping, not an actual terminal setting our code controls or
        # a real app would ever notice. Mask it before comparing.
        pendin = getattr(termios, "PENDIN", 0)
        assert (restored[3] & ~pendin) == (original[3] & ~pendin)
        assert restored[:3] == original[:3]
        assert restored[4:] == original[4:]
        stream.close()
    finally:
        os.close(slave_fd)
        os.close(master_fd)
