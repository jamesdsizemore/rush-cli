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

import pytest

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="these tests require a POSIX pty"
)

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


def _run_pty_harness(
    tmp_path: Path,
    *,
    actions_src: str = _NOOP_ACTIONS_SRC,
    actions_expr: str = "actions",
    rows: int = 24,
    cols: int = 80,
    capture: list[bytes] | None = None,
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
