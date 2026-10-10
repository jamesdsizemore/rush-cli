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

import errno
import fcntl
import json
import os
import re
import runpy
import select
import struct
import sys
import termios
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from _process_children import spawn_pty_child

pytestmark = pytest.mark.posix_only  # a POSIX pty

_REPO_SRC = str(Path(__file__).resolve().parent.parent / "src")

# SGR escape carrying a real foreground/background colour parameter (30-38
# or 90-97, including the 256-colour/truecolor `38;5;N` / `38;2;R;G;B`
# forms Rich uses for styles like "grey50"). Deliberately excludes
# non-colour attributes (bold=1, reset=0) that `Console(no_color=True)`
# still legitimately emits.
_ANSI_COLOR_CODE = re.compile(rb"\x1b\[[0-9;]*(?:3[0-8]|9[0-7])(?:;[0-9]+)*m")

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


def _child_run_pty_harness(
    harness_path: str, rows: int, cols: int, error_path: str
) -> None:
    try:
        _set_pty_size(0, rows, cols)
        runpy.run_path(harness_path, run_name="__main__")
    except BaseException as exc:  # noqa: BLE001 -- child-process diagnostics
        # only: this is the child's last chance to record ANY failure
        # (including exotic ones) to `error_path` before it exits
        # silently; the parent test asserts on `error_path` via
        # `_collect`.
        try:
            Path(error_path).write_text(repr(exc))
        except OSError:
            pass


def _run_pty_harness(
    tmp_path: Path,
    *,
    actions_src: str = _NOOP_ACTIONS_SRC,
    actions_expr: str = "actions",
    rows: int = 24,
    cols: int = 80,
    capture: list[bytes] | None = None,
) -> tuple[int, int, Path]:
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

    pid, master_fd = spawn_pty_child(
        "test_tui_terminal",
        "_child_run_pty_harness",
        [str(harness_path), rows, cols, str(error_path)],
    )

    _set_pty_size(master_fd, rows, cols)
    if capture is not None:
        _start_capture_thread(master_fd, capture)
    else:
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


# U09 fix: `_collect` used to `os.close(master_fd)` right after `os.waitpid`
# with no guarantee the reader thread had drained the pty master's
# remaining buffered bytes first -- a real race (thread mid-`select`/`read`
# racing the main thread's `close`), not just a slow-CI flake. These
# registries let `_collect` join the exact reader thread for its
# `master_fd` -- and surface any reader error -- before ever closing the
# descriptor, removing the race by construction instead of hoping the
# thread finishes in time.
_READER_THREADS: dict[int, threading.Thread] = {}
_READER_ERRORS: dict[int, OSError] = {}


def _read_pty_master(master_fd: int, *, platform: str = sys.platform) -> bytes:
    """One read from the pty master. Once the child exits and every slave fd
    is closed, Linux fails the master read with EIO where macOS returns
    b"" -- both mean EOF (the documented Linux pty behaviour). Only that
    exact case becomes b""; every other error still propagates."""
    try:
        return os.read(master_fd, 65536)
    except OSError as exc:
        if exc.errno == errno.EIO and platform.startswith("linux"):
            return b""
        raise


def _start_drain_thread(master_fd: int) -> None:
    """A real terminal emulator continuously reads the pty master; nothing
    else does here. Without a drain, Rich's Live re-renders eventually fill
    the kernel pty buffer and the child's next `write()` blocks forever --
    a test-harness deadlock, not a production bug. Runs until it observes
    real EOF (the child has exited and closed the pty slave) -- `_collect`
    joins this thread before closing `master_fd`, so it never races a
    close from the other side."""

    def _drain() -> None:
        while True:
            try:
                ready, _, _ = select.select([master_fd], [], [], 0.05)
            except OSError as exc:
                _READER_ERRORS[master_fd] = exc
                return
            if not ready:
                continue
            try:
                chunk = _read_pty_master(master_fd)
            except OSError as exc:
                _READER_ERRORS[master_fd] = exc
                return
            if not chunk:
                return

    thread = threading.Thread(target=_drain, daemon=True)
    thread.start()
    _READER_THREADS[master_fd] = thread


def _start_capture_thread(master_fd: int, buffer: list[bytes]) -> None:
    """Same read loop as `_start_drain_thread`, but appends the real
    rendered bytes to `buffer` instead of discarding them -- used only by
    tests that need to inspect actual PTY output rather than just the
    final `TuiState`."""

    def _drain() -> None:
        while True:
            try:
                ready, _, _ = select.select([master_fd], [], [], 0.05)
            except OSError as exc:
                _READER_ERRORS[master_fd] = exc
                return
            if not ready:
                continue
            try:
                chunk = _read_pty_master(master_fd)
            except OSError as exc:
                _READER_ERRORS[master_fd] = exc
                return
            if not chunk:
                return
            buffer.append(chunk)

    thread = threading.Thread(target=_drain, daemon=True)
    thread.start()
    _READER_THREADS[master_fd] = thread


def _raise_oserror(err: int):
    def _read(fd: int, n: int) -> bytes:
        raise OSError(err, os.strerror(err))

    return _read


def test_pty_master_read_treats_linux_eio_as_eof(monkeypatch) -> None:
    monkeypatch.setattr(os, "read", _raise_oserror(errno.EIO))
    assert _read_pty_master(3, platform="linux") == b""


def test_pty_master_read_keeps_eio_an_error_off_linux(monkeypatch) -> None:
    monkeypatch.setattr(os, "read", _raise_oserror(errno.EIO))
    with pytest.raises(OSError) as raised:
        _read_pty_master(3, platform="darwin")
    assert raised.value.errno == errno.EIO


def test_pty_master_read_keeps_other_linux_errors_real(monkeypatch) -> None:
    monkeypatch.setattr(os, "read", _raise_oserror(errno.EBADF))
    with pytest.raises(OSError) as raised:
        _read_pty_master(3, platform="linux")
    assert raised.value.errno == errno.EBADF


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
    # U09 fix: the child has exited (so the pty slave is already closed by
    # the kernel), but the reader thread may not yet have drained the last
    # buffered bytes -- join it (bounded, so a genuinely stuck reader fails
    # loudly instead of hanging the test) *before* closing `master_fd`,
    # never race the close against the drain.
    reader_thread = _READER_THREADS.pop(master_fd, None)
    if reader_thread is not None:
        reader_thread.join(timeout=2.0)
        if reader_thread.is_alive():
            os.close(master_fd)
            raise AssertionError(
                "pty reader thread did not finish draining before harness "
                "collection -- captured output would be incomplete"
            )
    reader_error = _READER_ERRORS.pop(master_fd, None)
    os.close(master_fd)
    if reader_error is not None:
        raise AssertionError(f"pty reader thread failed: {reader_error!r}")
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
    """U01 fix: real project switching now goes through F2's project
    selector (a real xterm CSI numeric-tilde F2 sequence, decoded by
    `PosixKeyReader`) plus Down/Enter -- Tab no longer performs this
    action (see `test_tab_never_switches_project_over_a_real_pty` below)."""
    with capfd.disabled():
        pid, master_fd, result_path = _run_pty_harness(tmp_path)
        _send(master_fd, "\x1b[12~")  # real F2 escape sequence -> open selector
        _send(master_fd, "\x1b[B")  # down arrow -> move to beta
        _send(master_fd, "\r")  # enter -> confirm switch
        _send(master_fd, "q")
        state = _collect(pid, master_fd, result_path)

    assert state["active_project"] == "beta"
    assert state["active_index"] == 1


def test_tab_never_switches_project_over_a_real_pty(
    tmp_path: Path, capfd: pytest.CaptureFixture
) -> None:
    """U01 fix: a real Tab byte over the PTY must never change the active
    project -- it now cycles panes instead (dispatch-level coverage is in
    `tests/test_tui.py::test_tab_cycles_panes_not_projects`)."""
    with capfd.disabled():
        pid, master_fd, result_path = _run_pty_harness(tmp_path)
        _send(master_fd, "\t")
        _send(master_fd, "q")
        state = _collect(pid, master_fd, result_path)

    assert state["active_project"] == "alpha"
    assert state["active_index"] == 0


def test_question_mark_shows_real_current_bindings(
    tmp_path: Path, capfd: pytest.CaptureFixture
) -> None:
    """P69-06c/U01 fix: a real `?` binding opens a help view rendering the
    actual current `_KEYMAP` bindings, not a hardcoded string -- and this
    now checks the *displayed content*, not just the mode flag, so a
    static/stale help string could not satisfy it."""
    with capfd.disabled():
        captured: list[bytes] = []
        pid, master_fd, result_path = _run_pty_harness(tmp_path, capture=captured)
        _send(master_fd, "?")  # show_help
        _send(master_fd, "q")
        state = _collect(pid, master_fd, result_path)

    assert state["mode"] == "help"
    rendered = b"".join(captured).decode(errors="replace")
    # Real, current binding descriptions -- one pre-existing ("q"), one
    # from this packet's own U01 fix ("f2") -- proving the help view reads
    # `_KEYMAP.bindings` live rather than displaying stale/hardcoded copy.
    assert "Exit Rush TUI" in rendered
    assert "Open project selector" in rendered


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


def test_no_color_env_suppresses_ansi_color_codes(
    tmp_path: Path, capfd: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`run_interactive_tui` reads NO_COLOR itself (tui.py:2006-2009) and
    builds its own `Console(no_color=...)` when no console is injected --
    this drives that real path over a real PTY and inspects the actual
    rendered bytes, proving NO_COLOR=1 suppresses colour output rather
    than just confirming the env var is read."""
    with capfd.disabled():
        colored: list[bytes] = []
        pid, master_fd, result_path = _run_pty_harness(tmp_path, capture=colored)
        _send(master_fd, "q")
        _collect(pid, master_fd, result_path)
    colored_output = b"".join(colored)
    assert _ANSI_COLOR_CODE.search(colored_output), (
        "expected real ANSI colour codes without NO_COLOR"
    )

    no_color_dir = tmp_path / "no_color"
    no_color_dir.mkdir()
    monkeypatch.setenv("NO_COLOR", "1")
    with capfd.disabled():
        no_color: list[bytes] = []
        pid, master_fd, result_path = _run_pty_harness(no_color_dir, capture=no_color)
        _send(master_fd, "q")
        _collect(pid, master_fd, result_path)
    no_color_output = b"".join(no_color)
    assert not _ANSI_COLOR_CODE.search(no_color_output), (
        "NO_COLOR=1 should suppress ANSI colour codes"
    )


def test_pty_harness_capture_never_returns_empty_bytes_on_a_successful_run(
    tmp_path: Path, capfd: pytest.CaptureFixture
) -> None:
    """U09 regression guard: `_collect` used to `os.close(master_fd)`
    immediately after `os.waitpid`, racing the reader thread's own
    `select`/`read` loop -- a successful run could still capture `b""`
    if the close won that race before the last buffered render was
    drained. `_collect` now joins the reader thread (and surfaces any
    reader error) before closing the descriptor, so a normal run's
    captured bytes are never empty by construction, not by luck."""
    with capfd.disabled():
        captured: list[bytes] = []
        pid, master_fd, result_path = _run_pty_harness(tmp_path, capture=captured)
        _send(master_fd, "q")
        _collect(pid, master_fd, result_path)

    output = b"".join(captured)
    assert output, "pty harness capture must never be empty on a successful run"


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


def test_q_offers_detach_cancel_return_when_run_active(
    tmp_path: Path, capfd: pytest.CaptureFixture
) -> None:
    """P69-06g: quitting with an active run offers a real three-way choice
    (Detach/Cancel run and stay/Return), never an immediate exit. There is
    no live dashboard server in this harness, so Detach here is
    Cancel-with-saved-partial-result (Phase 66 S3.9's superseding clause,
    this plan's own S3) -- the run's own cooperative-cancel path stops it
    and the loop then exits with the menu dismissed."""
    with capfd.disabled():
        pid, master_fd, result_path = _run_pty_harness(
            tmp_path, actions_src=_CANCEL_ACTIONS_SRC
        )
        _send(master_fd, "s")  # start_scan -> grant review
        _send(master_fd, "y", settle=0.15)  # confirm -> real background scan starts
        time.sleep(0.12)  # let a few candidates complete first
        _send(master_fd, "q")  # opens the three-way quit_confirm menu
        _send(master_fd, "d", settle=0.3)  # Detach -- waits for the real cancel ack
        state = _collect(pid, master_fd, result_path)

    assert state["mode"] == "list"
    assert state["status"] == "cancelled"
    history = state["progress_history"]
    assert history, "expected at least one progress observation before Detach"
    assert history[-1]["executed"] < history[-1]["total"], (
        "scan should have stopped early via Detach's cancel, not run to completion"
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


def test_function_key_escape_sequences_decoded_not_just_arrows() -> None:
    """U01 fix: `PosixKeyReader` decodes real multi-byte CSI escape
    sequences beyond the 4 arrows -- xterm's numeric-tilde F-key family
    and Shift+Tab (`CSI Z`) -- via a real POSIX pipe (no tty needed for
    this decode logic; `raw_terminal`'s SIGWINCH wiring is covered
    separately below, and only that part needs a real tty)."""
    sys.path.insert(0, _REPO_SRC)
    from rush.dashboard.terminal_input import PosixKeyReader

    read_fd, write_fd = os.pipe()
    try:
        reader = PosixKeyReader(read_fd)
        cases = {
            b"\x1b[12~": "f2",
            b"\x1b[13~": "f3",
            b"\x1b[Z": "shift_tab",
            b"\x1b[A": "up",  # a plain arrow still decodes correctly too
        }
        for raw_bytes, expected in cases.items():
            os.write(write_fd, raw_bytes)
            assert reader.read_key(1.0) == expected

        # A bare Escape (nothing follows within the 50ms follow-up window)
        # must still decode as Escape, not a function key.
        os.write(write_fd, b"\x1b")
        assert reader.read_key(1.0) == "escape"
    finally:
        os.close(read_fd)
        os.close(write_fd)


def test_utf8_multibyte_input_decoded_correctly() -> None:
    """U01 fix: a split multibyte UTF-8 character decodes as one real
    character, not one-byte-at-a-time mangled replacement characters."""
    sys.path.insert(0, _REPO_SRC)
    from rush.dashboard.terminal_input import PosixKeyReader

    read_fd, write_fd = os.pipe()
    try:
        reader = PosixKeyReader(read_fd)
        for text in ("é", "中", "\U0001f680"):  # 2, 3, 4-byte UTF-8
            os.write(write_fd, text.encode("utf-8"))
            assert reader.read_key(1.0) == text
        # Plain ASCII still decodes as a single one-byte character.
        os.write(write_fd, b"x")
        assert reader.read_key(1.0) == "x"
    finally:
        os.close(read_fd)
        os.close(write_fd)


def test_posix_selectors_and_sigwinch_handling() -> None:
    """U01 fix: `raw_terminal` wires a self-pipe as the process's SIGWINCH
    wakeup fd, and `PosixKeyReader.read_key` (via `selectors`) wakes on it
    immediately -- verified with a real `os.kill(..., SIGWINCH)`, not a
    mock. Also verifies cleanup: the prior handler/wakeup fd are restored
    and both pipe descriptors are closed once the `with` block exits."""
    import pty
    import signal

    sys.path.insert(0, _REPO_SRC)
    from rush.dashboard.terminal_input import (
        _ACTIVE_WAKEUP_FD,
        PosixKeyReader,
        raw_terminal,
    )

    prior_handler = signal.getsignal(signal.SIGWINCH)
    prior_wakeup_fd = signal.set_wakeup_fd(-1)
    signal.set_wakeup_fd(prior_wakeup_fd)  # restore immediately, just peeking

    master_fd, slave_fd = pty.openpty()
    try:
        stream = os.fdopen(slave_fd, "rb", buffering=0, closefd=False)
        with raw_terminal(stream):
            wakeup_fd = _ACTIVE_WAKEUP_FD[0]
            assert wakeup_fd is not None
            reader = PosixKeyReader(slave_fd)

            start = time.monotonic()
            os.kill(os.getpid(), signal.SIGWINCH)
            # A long timeout that a real wakeup interrupts almost
            # immediately; a slow/absent wakeup would instead consume
            # nearly the entire timeout -- the elapsed-time bound below
            # is what actually proves the interrupt fired.
            result = reader.read_key(5.0)
            elapsed = time.monotonic() - start

            assert result is None  # SIGWINCH alone is not a keystroke
            assert elapsed < 1.0, (
                f"expected SIGWINCH to wake the selector almost immediately, "
                f"took {elapsed:.2f}s (>= the 5s timeout would mean no wakeup)"
            )
        stream.close()
    finally:
        os.close(slave_fd)
        os.close(master_fd)

    # Cleanup: nothing from this `with` block leaks past it.
    assert _ACTIVE_WAKEUP_FD[0] is None
    assert signal.getsignal(signal.SIGWINCH) == prior_handler
    restored_prior = signal.set_wakeup_fd(-1)
    signal.set_wakeup_fd(restored_prior)
    assert restored_prior == prior_wakeup_fd


def test_windows_f2_f3_shift_tab_decode_to_named_actions_not_escape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """U01 fix, Windows decode logic: no Windows console is reachable in
    this POSIX environment, so this verifies `WindowsKeyReader`'s own
    scan-code mapping (F2 0x3C, F3 0x3D, Shift+Tab 0x0F) via an injected
    `msvcrt` stub and a monkeypatched `sys.platform` -- a real, executable
    check of the decode logic itself. It does NOT verify that a real
    Windows console actually emits these exact scan codes for these exact
    keys; that empirical claim remains genuinely unverified here (named
    explicitly in this task's receipt), same as S03's Windows-only lanes
    elsewhere on this board."""
    import sys as sys_module
    import types

    sys.path.insert(0, _REPO_SRC)
    from rush.dashboard.terminal_input import WindowsKeyReader

    keys = iter(["\x00", "\x3c", "\x00", "\x3d", "\x00", "\x0f", "\x00", "H"])

    fake_msvcrt = types.ModuleType("msvcrt")
    fake_msvcrt.kbhit = lambda: True  # type: ignore[attr-defined]
    fake_msvcrt.getwch = lambda: next(keys)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys_module.modules, "msvcrt", fake_msvcrt)
    monkeypatch.setattr(sys_module, "platform", "win32")

    reader = WindowsKeyReader()
    assert reader.read_key(1.0) == "f2"
    assert reader.read_key(1.0) == "f3"
    assert reader.read_key(1.0) == "shift_tab"
    assert reader.read_key(1.0) == "up"  # a plain arrow still decodes too


class _WinConsole:
    """Scripted `msvcrt` (kbhit/getwch) plus the kernel32 console-mode calls
    `raw_terminal` makes on Windows. `refuse` makes SetConsoleMode fail for
    that flag; `no_console` makes GetConsoleMode fail (input is not a
    console)."""

    def __init__(
        self, chars: list[str], *, refuse: int = 0, no_console: bool = False
    ) -> None:
        self.chars = list(chars)
        self.modes = {-10: 0x01F7, -11: 0x0003}
        self.refuse = refuse
        self.no_console = no_console

    def kbhit(self) -> bool:
        return bool(self.chars)

    def getwch(self) -> str:
        return self.chars.pop(0)

    def kernel32(self) -> object:
        import types

        def get_mode(handle: int, mode: Any) -> int:
            if self.no_console:
                return 0
            mode.contents.value = self.modes[handle]
            return 1

        def set_mode(handle: int, mode: int) -> int:
            if mode & self.refuse:
                return 0
            self.modes[handle] = mode
            return 1

        return types.SimpleNamespace(
            GetStdHandle=lambda which: which,
            GetConsoleMode=get_mode,
            SetConsoleMode=set_mode,
        )


def _windows(monkeypatch: pytest.MonkeyPatch, console: _WinConsole) -> None:
    sys.path.insert(0, _REPO_SRC)
    from rush.dashboard import terminal_input

    monkeypatch.setattr(terminal_input, "_WINDOWS", True)
    monkeypatch.setattr(terminal_input, "_windows_kernel32", console.kernel32)
    monkeypatch.setitem(sys.modules, "msvcrt", console)
    monkeypatch.setattr(sys, "platform", "win32")


@pytest.mark.parametrize("error", [None, RuntimeError, KeyboardInterrupt])
def test_windows_console_vt_mode_saved_and_restored(
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    error: type[BaseException] | None,
) -> None:
    """`raw_terminal` turns on VT input (0x0200) and VT output (0x0004) and
    bracketed paste on Windows, and restores both console modes and turns
    bracketed paste off on a clean exit, an exception and an interrupt."""
    console = _WinConsole(["\x1b", "[", "A"])
    _windows(monkeypatch, console)
    from rush.dashboard import terminal_input

    original = dict(console.modes)
    reader = terminal_input.WindowsKeyReader()

    def body() -> None:
        with terminal_input.raw_terminal():
            assert console.modes == {-10: 0x01F7 | 0x0200, -11: 0x0003 | 0x0004}
            assert reader.read_key(0.2) == "up"
            if error is not None:
                raise error

    if error is None:
        body()
    else:
        with pytest.raises(error):
            body()
    assert console.modes == original
    assert terminal_input._WINDOWS_VT_INPUT == [False]
    out = capfd.readouterr().out
    assert out.count("\x1b[?2004h") == 1 and out.count("\x1b[?2004l") == 1
    assert out.index("\x1b[?2004h") < out.index("\x1b[?2004l")


@pytest.mark.parametrize(
    ("refuse", "no_console"), [(0x0200, False), (0x0004, False), (0, True)]
)
def test_windows_console_refusing_vt_falls_back_to_msvcrt_reader(
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    refuse: int,
    no_console: bool,
) -> None:
    """A console that refuses VT input or VT output (or input that is not a
    console) keeps its original modes, gets no bracketed-paste request, and
    the msvcrt reader decodes scan codes; any multi-character burst there
    is one literal paste, never keys (a pasted `qq` must not quit twice)."""
    console = _WinConsole(
        ["\xe0", "H", "q", "q", "j", "j", "\r", "x"],
        refuse=refuse,
        no_console=no_console,
    )
    _windows(monkeypatch, console)
    from rush.dashboard import terminal_input

    original = dict(console.modes)
    reader = terminal_input.WindowsKeyReader()
    with terminal_input.raw_terminal():
        assert console.modes == original
        keys = []
        for _ in range(8):
            key = reader.read_key(0.02)
            if key is None:
                break
            keys.append(key)
    assert keys == ["up", "paste:qqjj", "enter", "x"]
    assert console.modes == original
    assert "\x1b[?2004" not in capfd.readouterr().out


# ---------------------------------------------------------------------------
# Ctrl-C in a real PTY (T29 native walkthrough: an idle Ctrl-C never exited)
# ---------------------------------------------------------------------------
#
# `controlling=True`: the PTY is the child's controlling terminal and the
# child leads its foreground process group, so the line discipline turns
# Ctrl-C into SIGINT for it. `controlling=False`: the PTY is the child's
# stdin/stdout but not its controlling terminal -- what a launcher that
# runs the program outside the terminal's foreground group hands it. There
# the line discipline has nobody to signal, so Ctrl-C must reach the TUI as
# the 0x03 input byte. Both are a real Ctrl-C keypress on a real PTY.

_CTRL_C_LAUNCHER = """
import fcntl, runpy, sys, termios
from pathlib import Path
if {controlling!r}:
    fcntl.ioctl(0, termios.TIOCSCTTY, 0)
sys.argv = {argv!r}
def _modes():
    # PENDIN is kernel state, not a mode: the line discipline sets it itself
    # when canonical mode returns with input pending (after Ctrl-C's flush).
    attrs = termios.tcgetattr(0)
    attrs[3] &= ~getattr(termios, "PENDIN", 0)
    return attrs
_original = _modes()
try:
    runpy.{run}
finally:
    # Read back here: once a session leader exits, macOS revokes its
    # controlling terminal and the parent can no longer query it.
    Path({restored_path!r}).write_text(str(_modes() == _original))
"""

_ALT_SCREEN_ON = b"\x1b[?1049h"
_ALT_SCREEN_OFF = b"\x1b[?1049l"
_CURSOR_SHOWN = b"\x1b[?25h"
_ANSI_ANY = re.compile(rb"\x1b\[[0-9;?]*[ -/]*[@-~]")


class _CtrlCChild:
    """A real child on a real PTY; its launcher records whether the
    terminal modes it exits with equal the ones it started with."""

    def __init__(
        self,
        tmp_path: Path,
        run: str,
        argv: list[str],
        *,
        controlling: bool,
        rows: int = 24,
        cols: int = 80,
        native_argv: list[str] | None = None,
        native_env: dict[str, str] | None = None,
    ) -> None:
        import subprocess

        self.native = native_argv is not None
        home = tmp_path / "home"
        home.mkdir(exist_ok=True)
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("XDG_DATA_HOME", "RUSH_DATA_ROOT", "NO_COLOR")
        }
        env.update(HOME=str(home), PYTHONPATH=_REPO_SRC, TERM="xterm-256color")
        if native_argv is not None:
            env.pop("PYTHONPATH", None)
            env.pop("PYTHONHOME", None)
            env.pop("RUSH_REDUCED_MOTION", None)
            env.update(native_env or {})
        self.inputs: list[dict[str, Any]] = []
        self.launch_context = {
            "cwd": str(tmp_path),
            **{
                key: env.get(key)
                for key in (
                    "HOME",
                    "TERM",
                    "PYTHONPATH",
                    "PYTHONHOME",
                    "NO_COLOR",
                    "RUSH_REDUCED_MOTION",
                )
            },
        }
        self.master_fd, slave_fd = os.openpty()
        _set_pty_size(self.master_fd, rows, cols)
        self.restored_path = tmp_path / "restored"
        launcher = tmp_path / "launcher.py"
        source = _CTRL_C_LAUNCHER.format(
            controlling=controlling,
            argv=argv,
            run=run,
            restored_path=str(self.restored_path),
        )
        if native_argv is not None:
            source = source.replace(
                f"runpy.{run}",
                "import signal, subprocess\n    "
                "signal.signal(signal.SIGINT, lambda *_: None)\n    "
                f"child = subprocess.Popen({native_argv!r})\n    "
                "try:\n        code = child.wait()\n    "
                "finally:\n        if child.poll() is None:\n            "
                "child.kill()\n            child.wait()\n    "
                "sys.exit(code)",
            )
        launcher.write_text(source)
        self.out: list[bytes] = []
        self.proc = subprocess.Popen(
            [sys.executable, str(launcher)],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            env=env,
            cwd=str(tmp_path),
            start_new_session=True,
            close_fds=True,
        )
        self.process_group = self.proc.pid
        if self.native:
            self.launch_context.update(
                pid=self.proc.pid,
                pgid=os.getpgid(self.proc.pid),
                sid=os.getsid(self.proc.pid),
            )
            assert self.launch_context["pgid"] == self.process_group
            assert self.launch_context["sid"] == self.proc.pid
        os.close(slave_fd)
        _start_capture_thread(self.master_fd, self.out)

    def output(self, start: int = 0) -> bytes:
        return b"".join(self.out)[start:]

    def text(self, start: int = 0) -> str:
        return _ANSI_ANY.sub(b"", self.output(start)).decode(errors="replace")

    def wait_for(self, what: str, predicate: Any, timeout: float = 20.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            if self.proc.poll() is not None:
                break
            time.sleep(0.02)
        raise AssertionError(
            f"{what} never happened (exit {self.proc.poll()}); "
            f"tail: {self.text()[-800:]!r}"
        )

    def send(self, data: bytes) -> None:
        os.write(self.master_fd, data)
        if self.native:
            self.inputs.append({"keys_hex": data.hex(), "at": time.monotonic()})

    def exit_within(self, seconds: float) -> tuple[int | None, float]:
        start = time.monotonic()
        while time.monotonic() - start < seconds and self.proc.poll() is None:
            time.sleep(0.01)
        return self.proc.poll(), time.monotonic() - start

    def restored(self) -> bool:
        return self.restored_path.read_text() == "True"

    def wait_group_gone(self) -> None:
        if getattr(self, "_group_gone", False):
            return
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                os.killpg(self.process_group, 0)
            except ProcessLookupError:
                self._group_gone = True
                return
            except PermissionError:
                pass  # EPERM is not proof that an owned group is gone.
            time.sleep(0.02)
        raise AssertionError(f"owned process group {self.process_group} remained")

    def close(self) -> None:
        if getattr(self, "_closed", False):
            return
        if self.native and not getattr(self, "_group_gone", False):
            import signal

            try:
                os.killpg(self.process_group, signal.SIGKILL)
            except ProcessLookupError:
                pass
        elif self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait(timeout=10)
        thread = _READER_THREADS.pop(self.master_fd, None)
        if thread is not None:
            thread.join(timeout=2.0)
        _READER_ERRORS.pop(self.master_fd, None)
        os.close(self.master_fd)
        self._closed = True


def _close_native_child(child: _CtrlCChild, failure: BaseException | None) -> None:
    try:
        child.close()
        child.wait_group_gone()
    except Exception as cleanup_error:
        if failure is None:
            raise
        failure.add_note(f"native cleanup failed: {cleanup_error!r}")


def test_native_group_probe_permission_is_not_absence(monkeypatch) -> None:
    child = _CtrlCChild.__new__(_CtrlCChild)
    child.process_group = 42
    clock = iter((0.0, 0.0, 6.0))
    monkeypatch.setattr(time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(time, "sleep", lambda _: None)
    probes = []

    def denied(group, sig):
        probes.append((group, sig))
        raise PermissionError("owned group still present")

    monkeypatch.setattr(os, "killpg", denied)
    with pytest.raises(AssertionError, match="owned process group 42 remained"):
        child.wait_group_gone()
    assert probes == [(42, 0)]


def test_native_cleanup_preserves_original_failure(monkeypatch) -> None:
    child = _CtrlCChild.__new__(_CtrlCChild)
    monkeypatch.setattr(child, "close", lambda: None)

    def remaining():
        raise PermissionError("owned group still present")

    monkeypatch.setattr(child, "wait_group_gone", remaining)
    original = AssertionError(">Refresh never happened")
    _close_native_child(child, original)
    assert str(original) == ">Refresh never happened"
    assert original.__notes__ == [
        "native cleanup failed: PermissionError('owned group still present')"
    ]
    with pytest.raises(PermissionError, match="owned group still present"):
        _close_native_child(child, None)


def test_native_cleanup_never_signals_group_after_observed_absence(
    tmp_path: Path, capfd: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    with capfd.disabled():
        child = _CtrlCChild(
            tmp_path,
            "run_module('rush.cli', run_name='__main__')",
            [],
            controlling=True,
            native_argv=[sys.executable, "-c", "pass"],
        )
        try:
            status, _ = child.exit_within(2.0)
            assert status == 0
            child.wait_group_gone()
            assert child._group_gone is True

            def forbidden_signal(group, sig):
                raise AssertionError(f"signaled absent group {group} with {sig}")

            with monkeypatch.context() as patch:
                patch.setattr(os, "killpg", forbidden_signal)
                child.wait_group_gone()
                child.close()
            assert child._closed is True
        finally:
            child.close()


def test_native_launcher_cleanup_reaps_descendants_after_launcher_exit(
    tmp_path: Path, capfd: pytest.CaptureFixture
) -> None:
    marker = tmp_path / "descendant.pid"
    descendant = (
        "import os, signal, time\n"
        "from pathlib import Path\n"
        "signal.signal(signal.SIGHUP, signal.SIG_IGN)\n"
        f"Path({str(marker)!r}).write_text(str(os.getpid()))\n"
        "time.sleep(60)\n"
    )
    script = (
        "import subprocess, sys, time\n"
        "from pathlib import Path\n"
        f"subprocess.Popen([sys.executable, '-c', {descendant!r}])\n"
        f"marker = Path({str(marker)!r})\n"
        "deadline = time.monotonic() + 5\n"
        "while not marker.is_file() and time.monotonic() < deadline:\n"
        "    time.sleep(0.01)\n"
        "assert marker.is_file(), 'descendant did not signal readiness'\n"
    )
    with capfd.disabled():
        child = _CtrlCChild(
            tmp_path,
            "run_module('rush.cli', run_name='__main__')",
            [],
            controlling=True,
            native_argv=[sys.executable, "-c", script],
        )
        try:
            child.wait_for(
                "launcher exited with a surviving descendant",
                lambda: marker.is_file() and child.proc.poll() == 0,
            )
            os.kill(int(marker.read_text()), 0)
            child.close()

            child.wait_group_gone()
        finally:
            child.close()


@pytest.mark.parametrize("controlling", [True, False], ids=["sigint", "byte"])
def test_ctrl_c_at_idle_exits_promptly_in_a_real_pty(
    tmp_path: Path, capfd: pytest.CaptureFixture, controlling: bool
) -> None:
    """`rush ui <project>` with no running work: one Ctrl-C quits (the `q`
    flow at idle) within 2 s, exit status 0, and the terminal modes, cursor
    and alternate screen are restored."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "a.py").write_text("x = 1\n")
    with capfd.disabled():
        child = _CtrlCChild(
            tmp_path,
            "run_module('rush.cli', run_name='__main__', alter_sys=True)",
            ["rush", "ui", str(project)],
            controlling=controlling,
        )
        try:
            child.wait_for(
                "first frame",
                lambda: _ALT_SCREEN_ON in child.output() and "?:Help" in child.text(),
            )
            time.sleep(0.3)
            child.send(b"\x03")
            status, elapsed = child.exit_within(2.0)
            assert status == 0, (
                f"idle Ctrl-C did not exit within 2 s (status {status}, "
                f"{elapsed:.2f}s); tail: {child.text()[-400:]!r}"
            )
            assert child.restored(), "terminal modes were not restored"
            tail = child.output()[-4096:]
            assert _ALT_SCREEN_OFF in tail, "alternate screen was not left"
            assert _CURSOR_SHOWN in tail, "cursor was not shown again"
        finally:
            child.close()


_SLOW_CANCEL_ACTIONS_SRC = _CANCEL_ACTIONS_SRC.replace("_TOTAL = 40", "_TOTAL = 1000")


@pytest.mark.parametrize("controlling", [True, False], ids=["sigint", "byte"])
def test_ctrl_c_with_running_work_opens_the_quit_choice_in_a_real_pty(
    tmp_path: Path, capfd: pytest.CaptureFixture, controlling: bool
) -> None:
    """Ctrl-C while a run is active never exits: it opens the quit choice
    (Detach, Cancel run and stay, Return). Detach from it then cancels the
    run, exits 0 and restores the terminal."""
    result_path = tmp_path / "result.json"
    harness = tmp_path / "harness.py"
    harness.write_text(
        _HARNESS_TEMPLATE.format(
            src_root=_REPO_SRC,
            actions_src=_SLOW_CANCEL_ACTIONS_SRC,
            actions_expr="actions",
            result_path=str(result_path),
            ready_path=str(tmp_path / "ready"),
        )
    )
    with capfd.disabled():
        child = _CtrlCChild(
            tmp_path,
            f"run_path({str(harness)!r}, run_name='__main__')",
            ["harness"],
            controlling=controlling,
            rows=40,
            cols=120,
        )
        try:
            child.wait_for("first frame", lambda: "?:Help" in child.text())
            time.sleep(0.3)
            child.send(b"s")
            time.sleep(0.3)  # start_scan -> grant review
            child.send(b"y")
            time.sleep(0.5)
            assert child.proc.poll() is None
            mark = len(child.output())
            child.send(b"\x03")
            child.wait_for(
                "quit choice",
                lambda: "Cancel run, stay open" in child.text(mark),
                timeout=2.0,
            )
            shown = child.text(mark)
            for label in ("Detach", "Cancel run, stay open", "Return, keep observing"):
                assert label in shown, f"quit choice {label!r} not shown"
            assert child.proc.poll() is None, "Ctrl-C with running work exited"
            child.send(b"d")
            status, elapsed = child.exit_within(10.0)
            assert status == 0, f"Detach did not exit (status {status}, {elapsed:.2f}s)"
            assert child.restored(), "terminal modes were not restored"
        finally:
            child.close()
    state = json.loads(result_path.read_text())
    assert state["status"] == "cancelled", state["status"]
    assert state["progress_history"][-1]["executed"] < 1000


if "RUSH_G8_NATIVE_ARCHIVE" in os.environ:

    def test_installed_native_tui_real_terminal(
        tmp_path: Path, capfd: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """T28 installed-binary terminal lane; never substitutes source execution."""
        import hashlib
        import platform
        import shutil
        import signal
        import subprocess
        import tarfile

        from rush.workflows import projects
        from rush.workflows.project_run import load_run_manifest, load_scan_events
        from scripts.probe_installed_artifacts import (
            compute_sha256,
            scrub_environment,
            verify_archive_checksum,
        )

        archive = Path(os.environ["RUSH_G8_NATIVE_ARCHIVE"]).resolve()
        sums = Path(os.environ["RUSH_G8_NATIVE_SUMS"]).resolve()
        receipt_dir = Path(os.environ["RUSH_G8_NATIVE_RECEIPT_DIR"]).resolve()
        assert receipt_dir.is_dir(), receipt_dir
        assert verify_archive_checksum(archive, sums), "native archive checksum failed"
        installed = tmp_path / "installed"
        installed.mkdir()
        with tarfile.open(archive) as bundle:
            bundle.extractall(installed, filter="data")
        binary = installed / "rush"
        assert binary.is_file() and os.access(binary, os.X_OK)
        assert not binary.is_relative_to(Path(_REPO_SRC).parent)
        version = subprocess.run(
            [str(binary), "--version"],
            cwd=tmp_path,
            env=scrub_environment(),
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
        ).stdout.strip()
        installed_version = (installed / "VERSION").read_text().strip()
        assert installed_version and installed_version in version
        assert shutil.which("pytest"), "native scan fixture requires real pytest"
        engine_path = os.pathsep.join(
            (str(Path(sys.executable).parent), "/usr/bin", "/bin")
        )
        assert all(
            shutil.which(name, path=engine_path) is not None
            for name in ("python3", "pytest", "git")
        )
        assert all(
            shutil.which(name, path=engine_path) is None
            for name in ("ollama", "llama-cli", "llama")
        )
        observations = []
        for cols, rows in ((80, 24), (120, 40), (60, 20)):
            work = tmp_path / f"terminal-{cols}x{rows}"
            work.mkdir()
            home = work / "home"
            home.mkdir()
            with monkeypatch.context() as patch:
                patch.setenv("HOME", str(home))
                patch.delenv("XDG_DATA_HOME", raising=False)
                patch.delenv("RUSH_DATA_ROOT", raising=False)
                roots = [work / "alpha", work / "beta"]
                ids = []
                for root in roots:
                    root.mkdir()
                    (root / "marker.txt").write_text("installed native evidence\n")
                    for args in (
                        ["init", "--quiet"],
                        ["add", "marker.txt"],
                        [
                            "-c",
                            "user.name=G8",
                            "-c",
                            "user.email=g8@example.test",
                            "commit",
                            "--quiet",
                            "-m",
                            "native-evidence",
                        ],
                    ):
                        subprocess.run(
                            ["git", "-C", str(root), *args],
                            check=True,
                            capture_output=True,
                        )
                    ids.append(projects.register_project(root).project_id)
            seen = {}
            keys_seen = []
            resizes = []
            native_env = {
                "PATH": engine_path,
                "VIRTUAL_ENV": sys.prefix,
                **(
                    {"NO_COLOR": "1"}
                    if cols == 120
                    else {"RUSH_REDUCED_MOTION": "1"}
                    if cols == 60
                    else {}
                ),
            }
            with capfd.disabled():
                child = _CtrlCChild(
                    work,
                    "run_module('rush.cli', run_name='__main__')",
                    [],
                    controlling=True,
                    rows=rows,
                    cols=cols,
                    native_argv=[str(binary), "ui", "--allow-build", *map(str, roots)],
                    native_env=native_env,
                )
                last_frame_start = 0
                try:
                    child.wait_for(
                        "native alternate screen",
                        lambda child=child: (
                            _ALT_SCREEN_ON in child.output()
                            and "?:Help" in child.text()
                        ),
                    )

                    def press(
                        keys: bytes,
                        marker: str,
                        child: _CtrlCChild = child,
                        keys_seen: list[dict[str, str]] = keys_seen,
                    ) -> str:
                        nonlocal last_frame_start
                        start = len(child.output())
                        last_frame_start = start
                        child.send(keys)
                        child.wait_for(marker, lambda: marker in child.text(start))
                        shown = child.text(start)
                        keys_seen.append(
                            {"keys_hex": keys.hex(), "marker": marker, "output": shown}
                        )
                        return shown

                    for number, label, domain in (
                        (1, "Overview", "registration:"),
                        (2, "Map", ">[+] alpha"),
                        (3, "Scans/Findings", "Scan history"),
                        (4, "Memory", "owner=project:"),
                        (5, "Tokens", "attribution:"),
                        (6, "Git", "has_git=True"),
                        (7, "Artifacts", "Captured (0)"),
                        (8, "Setup/Agents", "Rush setup review"),
                    ):
                        press(b"\x1bOR", "[1-8] go")
                        text = press(str(number).encode(), domain)
                        assert label in text, (cols, rows, label, text[-1500:])
                        if number == 4:
                            assert f"owner=project:{ids[0]}" in text
                        seen[label] = text
                    press(b"\x1bOR", "[1-8] go")
                    press(b"6", "has_git=True")
                    press(b"\r", "diff --git a/marker.txt b/marker.txt")
                    overview = press(b"\x1b", f"Overview  ({cols}x{rows})")
                    assert "diff --git" not in overview
                    press(b"\x1bOR", "[1-8] go")
                    git_frame = press(b"6", f"Git  ({cols}x{rows})")
                    assert "has_git=True" in git_frame
                    press(b"\x1bOQ", ">alpha")
                    press(b"\x1b[B", ">beta")
                    press(b"\r", "[2/2] beta")
                    press(b"\t", "[2/2] beta")
                    press(b"\t", ">Refresh" if cols >= 80 else "[2/2] beta")
                    # Actions are hidden at 60 columns. Their real scan review
                    # proves forward focus traversal at every terminal size.
                    press(b"\x1b[B", ">Check" if cols >= 80 else "[2/2] beta")
                    press(b"\x1b[B", ">Scan" if cols >= 80 else "[2/2] beta")
                    focus_review = press(b"\r", "Review before mutation: start_scan")
                    assert "artifact_write" in focus_review
                    assert "build" in focus_review and "cache_write" in focus_review
                    press(b"n", "declined")
                    assert not (roots[1] / ".rush" / "runs").exists()
                    press(b"\x1b[A", ">Check" if cols >= 80 else "[2/2] beta")
                    press(b"\x1b[A", ">Refresh" if cols >= 80 else "[2/2] beta")
                    detail_focus = press(b"\x1b[Z", "[2/2] beta")
                    assert ">Refresh" not in detail_focus
                    press(b"\x1b[Z", "[2/2] beta")
                    # Reverse traversal reaches nav, where Down/Enter changes
                    # Overview to Map; Tab then restores list focus.
                    press(b"\x1b[Z", "[2/2] beta")
                    press(b"\x1b[B", ">2 Map" if cols >= 80 else "[2/2] beta")
                    text = press(b"\r", ">[+] beta")
                    assert "Map" in text and "[2/2] beta" in text
                    press(b"\t", "[2/2] beta")
                    press(b"\r", "Memories")
                    press(b"\x1b[B", ">  Memories")
                    press(b"/", "/")
                    press(b"beta\r", ">[-] beta")
                    overview = press(b"\x1b", f"Overview  ({cols}x{rows})")
                    assert "map search /" not in overview
                    press(b"\x1bOR", "[1-8] go")
                    map_frame = press(b"2", f"Map  ({cols}x{rows})")
                    assert "[2/2] beta" in map_frame
                    press(b"/", "map search /")
                    pasted = press(
                        b"\x1b[200~" + "βqC".encode() + b"\x1b[2J\x1b[201~",
                        "βqC",
                    )
                    assert "map search /βqC" in pasted
                    assert _ALT_SCREEN_OFF not in child.output()
                    assert not (roots[1] / ".rush" / "runs").exists()
                    press(b"\x1b", "Map")
                    press(b"?", "Exit Rush TUI")
                    closed = press(b"\x1b", "Map")
                    assert "Exit Rush TUI" not in closed
                    press(b"\x1bOR", "[1-8] go")
                    press(b"2", "beta")
                    size_targets = ((60, 20), (120, 40), (80, 24))
                    first_target = (size_targets.index((cols, rows)) + 1) % 3
                    for width, height in (
                        size_targets[first_target:] + size_targets[:first_target]
                    ):
                        start = len(child.output())
                        _set_pty_size(child.master_fd, height, width)
                        os.killpg(child.proc.pid, signal.SIGWINCH)
                        child.wait_for(
                            "native resize redraw",
                            lambda child=child, start=start, width=width, height=height: (
                                f"({width}x{height})" in child.text(start)
                            ),
                        )
                        assert struct.unpack(
                            "HHHH",
                            fcntl.ioctl(child.master_fd, termios.TIOCGWINSZ, b"\0" * 8),
                        )[:2] == (height, width)
                        resizes.append(
                            {"size": [width, height], "output": child.text(start)}
                        )
                    # Observe real idle writes, rather than equating NO_COLOR
                    # with reduced motion or checking a source constant.
                    time.sleep(0.3)
                    idle_start = len(child.output())
                    idle_started_at = time.monotonic()
                    time.sleep(0.7)
                    idle_bytes = len(child.output()) - idle_start
                    idle_seconds = time.monotonic() - idle_started_at
                    if native_env.get("RUSH_REDUCED_MOTION"):
                        assert idle_bytes == 0
                    else:
                        assert idle_bytes > 0
                    if native_env.get("NO_COLOR"):
                        assert _ANSI_COLOR_CODE.search(child.output()) is None
                    else:
                        assert _ANSI_COLOR_CODE.search(child.output()) is not None

                    press(b"\x1bOR", "[1-8] go")
                    press(b"1", "registration:")
                    config = roots[1] / "rush.toml"
                    config.write_text("[tools\n")
                    failed_config = press(b"\x1b[15~", "rush.toml: invalid")
                    config.write_text("[tools]\n")
                    recovered_config = press(b"\x1b[15~", "rush.toml: valid")

                    # A real project test, run by Rush's discovered pytest
                    # engine. Its gate makes cancellation observable without
                    # replacing native dispatch or inventing engine output.
                    (roots[1] / "pyproject.toml").write_text(
                        '[tool.pytest.ini_options]\ntestpaths = ["test_native.py"]\n'
                    )
                    (roots[1] / "test_native.py").write_text(
                        "import json, os, time\n"
                        "from pathlib import Path\n"
                        "def test_real_native_work():\n"
                        f"    Path({str(roots[1] / 'native-started.json')!r}).write_text(json.dumps({{'pid': os.getpid()}}))\n"
                        "    deadline = time.monotonic() + 30\n"
                        f"    while not Path({str(roots[1] / 'native-release')!r}).exists() and time.monotonic() < deadline:\n"
                        "        time.sleep(0.02)\n"
                        f"    assert Path({str(roots[1] / 'native-release')!r}).exists(), 'native gate was not released'\n"
                    )
                    # Build is an explicit launch grant, still reviewed and
                    # declined/accepted through the visible native form.
                    reviewed = press(b"s", "Review before mutation: start_scan")
                    assert "build" in reviewed and "cache_write" in reviewed
                    assert "artifact_write" in reviewed
                    press(b"n", "declined")
                    assert not (roots[1] / "native-started.json").exists()
                    assert not (roots[1] / ".rush" / "runs").exists()
                    press(b"s", "Review before mutation: start_scan")
                    child.send(b"y")
                    child.wait_for(
                        "real pytest start",
                        lambda roots=roots: (
                            roots[1] / "native-started.json"
                        ).is_file(),
                    )
                    worker_pid = json.loads(
                        (roots[1] / "native-started.json").read_text()
                    )["pid"]
                    child.send(b"c")
                    child.wait_for(
                        "durable cancellation request",
                        lambda roots=roots: bool(
                            list(
                                (roots[1] / ".rush" / "runs").glob(
                                    "*/attempts/*/cancel_requested.json"
                                )
                            )
                        ),
                    )
                    cancel_path = next(
                        (roots[1] / ".rush" / "runs").glob(
                            "*/attempts/*/cancel_requested.json"
                        )
                    )
                    cancellation = json.loads(cancel_path.read_text())
                    child.wait_for(
                        "durable cancellation acknowledgment",
                        lambda roots=roots, cancellation=cancellation: (
                            load_scan_events(
                                roots[1],
                                cancellation["run_id"],
                                cancellation["attempt_id"],
                            )["run_state"]
                            == "cancelled"
                        ),
                    )
                    press(b"\x1bOR", "[1-8] go")
                    press(b"3", cancellation["run_id"])
                    history_status = re.compile(
                        re.escape(cancellation["run_id"]) + r"(?:(?!╰).)*cancelled",
                        re.DOTALL,
                    )
                    frame_start = last_frame_start
                    child.wait_for(
                        "cancelled run in scan history",
                        lambda child=child, frame_start=frame_start, history_status=history_status: (
                            history_status.search(child.text(frame_start)) is not None
                        ),
                    )
                    cancelled_display = child.text(last_frame_start)
                    keys_seen[-1]["output"] = cancelled_display
                    assert cancellation["run_id"] in cancelled_display
                    scan_events = load_scan_events(
                        roots[1], cancellation["run_id"], cancellation["attempt_id"]
                    )
                    assert scan_events["run_state"] == "cancelled"
                    manifest = load_run_manifest(
                        roots[1],
                        cancellation["run_id"],
                        attempt_id=cancellation["attempt_id"],
                    )
                    assert manifest["run_state"] == "cancelled"
                    with pytest.raises(ProcessLookupError):
                        os.kill(worker_pid, 0)
                    (roots[1] / "native-release").touch()
                    from test_windows_import_safety import (
                        _exercise_native_artifact_actions,
                        _exercise_native_memory_actions,
                        _seed_native_artifact_actions,
                        _seed_native_memory_actions,
                    )

                    artifact_entries = _seed_native_artifact_actions(roots[0], ids[0])
                    memory_entries = _seed_native_memory_actions(roots[0], ids[0])
                    press(b"\x1bOQ", roots[0].name)
                    press(b"\x1b[A\r", "[1/2]")
                    memory_actions = _exercise_native_memory_actions(
                        roots[0], memory_entries, press
                    )
                    artifact_actions = _exercise_native_artifact_actions(
                        roots[0], artifact_entries, press
                    )
                    child.send(b"q")
                    status, quit_seconds = child.exit_within(10)
                    assert status == 0
                    assert child.restored()
                    assert _ALT_SCREEN_OFF in child.output()
                    assert _CURSOR_SHOWN in child.output()
                    journey_output_sha256 = hashlib.sha256(child.output()).hexdigest()
                    journey_inputs = child.inputs
                    journey_context = child.launch_context
                    assert journey_context["PYTHONPATH"] is None
                    assert journey_context["PYTHONHOME"] is None
                    child.wait_group_gone()
                    child.close()
                    last_frame_start = 0
                    child = _CtrlCChild(
                        work,
                        "run_module('rush.cli', run_name='__main__')",
                        [],
                        controlling=True,
                        rows=rows,
                        cols=cols,
                        native_argv=[str(binary), "ui", str(roots[1])],
                        native_env=native_env,
                    )
                    child.wait_for(
                        "idle native first frame",
                        lambda child=child: (
                            _ALT_SCREEN_ON in child.output()
                            and "?:Help" in child.text()
                        ),
                    )
                    child.send(b"\x03")
                    status, interrupt_seconds = child.exit_within(2.0)
                    assert status == 0
                    assert child.restored()
                    assert _ALT_SCREEN_OFF in child.output()
                    assert _CURSOR_SHOWN in child.output()
                    child.wait_group_gone()
                    observations.append(
                        {
                            "size": [cols, rows],
                            "projects": ids,
                            "sections": seen,
                            "keys": keys_seen,
                            "resizes": resizes,
                            "exit": status,
                            "termios_restored": child.restored(),
                            "platform": platform.platform(),
                            "sys_platform": sys.platform,
                            "TERM": "xterm-256color",
                            "cwd": str(work),
                            "HOME": str(home),
                            "environment": native_env,
                            "idle_bytes": idle_bytes,
                            "idle_seconds": idle_seconds,
                            "failed_config": failed_config,
                            "recovered_config": recovered_config,
                            "grant_review": reviewed,
                            "cancel_request": cancellation,
                            "scan_events": scan_events,
                            "cancelled_display": cancelled_display,
                            "scan_manifest": manifest,
                            "artifact_actions": artifact_actions,
                            "memory_actions": memory_actions,
                            "worker_pid": worker_pid,
                            "interrupt_exit_seconds": interrupt_seconds,
                            "quit_exit_seconds": quit_seconds,
                            "journey_output_sha256": journey_output_sha256,
                            "journey_inputs": journey_inputs,
                            "journey_context": journey_context,
                            "interrupt_inputs": child.inputs,
                            "interrupt_context": child.launch_context,
                            "output_sha256": hashlib.sha256(child.output()).hexdigest(),
                        }
                    )
                except BaseException as error:
                    try:
                        (receipt_dir / f"posix-failure-{cols}x{rows}.bin").write_bytes(
                            child.output(last_frame_start)
                        )
                        (receipt_dir / f"posix-failure-{cols}x{rows}.json").write_text(
                            json.dumps(
                                {
                                    "error": repr(error),
                                    "context": child.launch_context,
                                    "inputs": child.inputs,
                                    "output": child.text(last_frame_start),
                                },
                                indent=2,
                            )
                        )
                    except (OSError, TypeError, ValueError) as capture_error:
                        error.add_note(
                            f"native failure capture failed: {capture_error!r}"
                        )
                    raise
                finally:
                    _close_native_child(child, sys.exception())
        receipt = {
            "archive": str(archive),
            "archive_sha256": compute_sha256(archive),
            "binary": str(binary),
            "binary_sha256": compute_sha256(binary),
            "version": version,
            "observations": observations,
        }
        path = receipt_dir / "posix-installed-tui.json"
        path.write_text(json.dumps(receipt, indent=2))
        assert json.loads(path.read_text()) == receipt
        assert [item["size"] for item in observations] == [
            [80, 24],
            [120, 40],
            [60, 20],
        ]
