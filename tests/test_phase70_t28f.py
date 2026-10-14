"""RED tests for Phase 70 T28-F: TUI terminal behavior and exhaustive
acceptance.

Binding design: `.scratch/phase-70-design-gate/W4-T23-T29.md` ("### Shared
design (all packets)" and "### T28-F"). Plan packet: T28-F in
`docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md`.

Owner decision: Cursor is REMOVED from Phase 70; hosts are Claude Code and
Codex CLI only (not exercised directly by this file -- terminal behavior is
host-independent).

None of T28's packets (A-F) are merged into this worktree yet, so several
cases below fail via `pytest.fail` naming the exact entry point the shared
design pins (`ACTIONS`, `TuiState.overlay`, `tui._TERMINAL_MOTION`, a
row-reveal sampling function) that does not exist yet on `rush.tui` --
that is a valid RED per this task's own instructions, not a skip. The
terminal-input-decoding, bracketed-paste, EOF, Ctrl-C, and non-TTY cases
drive the real shipped code directly and fail with concrete assertion
mismatches against real current behavior.

Zero-spawn: an autouse fixture patches `subprocess.Popen`/`subprocess.run`
to raise if called. No network. Every fixture/helper is local to this file.
"""

from __future__ import annotations

import json
import os
import select
import subprocess
import sys
import time
from pathlib import Path

import pytest

import rush.workflows.suites as suites_module
from rush import tui
from rush.dashboard import terminal_input
from rush.dashboard.theme import MOTION
from rush.tui import ProjectSeed, ScanActions, run_interactive_tui

# ---------------------------------------------------------------------------
# Shared local fixtures/helpers (kept local to this file per task instructions)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _zero_spawn_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """No case in this file may spawn a real subprocess."""

    def _no_popen(*_a: object, **_k: object) -> None:
        raise AssertionError("test must not spawn a subprocess (Popen)")

    def _no_run(*_a: object, **_k: object) -> None:
        raise AssertionError("test must not spawn a subprocess (run)")

    monkeypatch.setattr(subprocess, "Popen", _no_popen)
    monkeypatch.setattr(subprocess, "run", _no_run)


def _noop_actions() -> ScanActions:
    return ScanActions(
        plan_scan=lambda *a, **k: None,
        execute_scan=lambda *a, **k: None,
        cancel_scan_run=lambda *a, **k: {},
        rescan_project_run=lambda *a, **k: {},
        build_handoff=lambda *a, **k: None,
        dispatch_handoff=lambda *a, **k: None,
        load_scan_events=lambda *a, **k: {"events": [], "run_state": None},
        list_agents=list,
    )


def _seed(name: str = "demo") -> ProjectSeed:
    return ProjectSeed(name=name, root=Path(f"/tmp/rush-t28f-{name}"))


class _RaisingThenNoneReader:
    """Raises `KeyboardInterrupt` the first `raise_count` calls, then
    returns `None` forever. Never lets `KeyboardInterrupt` propagate to
    pytest itself -- callers must catch it locally, since pytest treats an
    uncaught `KeyboardInterrupt` as a request to abort the whole session,
    not a per-test failure."""

    def __init__(self, raise_count: int) -> None:
        self._remaining = raise_count

    def read_key(self, timeout: float) -> str | None:
        if self._remaining > 0:
            self._remaining -= 1
            raise KeyboardInterrupt
        return None

    def get_size(self) -> tuple[int, int]:
        return (80, 24)


class _ConstantReader:
    """Always returns the same logical key."""

    def __init__(self, key: str) -> None:
        self._key = key

    def read_key(self, timeout: float) -> str | None:
        return self._key

    def get_size(self) -> tuple[int, int]:
        return (80, 24)


def _drain_available(fd: int, timeout: float = 0.3) -> bytes:
    """Reads whatever bytes are available on `fd` within `timeout`
    seconds, polling with `select` -- never a blocking read."""
    end = time.monotonic() + timeout
    buf = b""
    while time.monotonic() < end:
        ready, _, _ = select.select([fd], [], [], 0.05)
        if not ready:
            continue
        try:
            chunk = os.read(fd, 4096)
        except OSError:
            break
        if not chunk:
            break
        buf += chunk
    return buf


# ---------------------------------------------------------------------------
# Escape-sequence decoding (terminal_input.py)
# ---------------------------------------------------------------------------


def test_ss3_function_keys_f1_f4_decoded() -> None:
    """Shared design: decode SS3 (`ESC O P/Q/R/S` -> f1-f4). macOS
    Terminal.app/iTerm2/xterm send this form; `_read_escape_sequence` only
    handles CSI (`ESC [ ...`) today, so `ESC O P` returns ESCAPE and drops
    the trailing `P` as an unrelated future byte (matches the design gate's
    own reproduction)."""
    for body, expected in ((b"P", "f1"), (b"Q", "f2"), (b"R", "f3"), (b"S", "f4")):
        r_fd, w_fd = os.pipe()
        try:
            os.write(w_fd, b"\x1bO" + body)
            reader = terminal_input.PosixKeyReader(r_fd)
            result = reader.read_key(timeout=0.5)
            assert result == expected, (
                f"ESC O {body!r} must decode to {expected!r}, got {result!r}"
            )
        finally:
            os.close(r_fd)
            os.close(w_fd)


def test_ss3_arrow_keys_decoded() -> None:
    """Shared design: decode SS3 arrows (`ESC O A-D`)."""
    for body, expected in (
        (b"A", "up"),
        (b"B", "down"),
        (b"C", "right"),
        (b"D", "left"),
    ):
        r_fd, w_fd = os.pipe()
        try:
            os.write(w_fd, b"\x1bO" + body)
            reader = terminal_input.PosixKeyReader(r_fd)
            result = reader.read_key(timeout=0.5)
            assert result == expected, (
                f"ESC O {body!r} must decode to {expected!r}, got {result!r}"
            )
        finally:
            os.close(r_fd)
            os.close(w_fd)


def test_linux_console_function_keys_decoded() -> None:
    """Shared design: decode the Linux console form (`ESC [ [ A-E`)."""
    for body, expected in (
        (b"A", "f1"),
        (b"B", "f2"),
        (b"C", "f3"),
        (b"D", "f4"),
        (b"E", "f5"),
    ):
        r_fd, w_fd = os.pipe()
        try:
            os.write(w_fd, b"\x1b[[" + body)
            reader = terminal_input.PosixKeyReader(r_fd)
            result = reader.read_key(timeout=0.5)
            assert result == expected, (
                f"ESC [ [ {body!r} must decode to {expected!r}, got {result!r}"
            )
        finally:
            os.close(r_fd)
            os.close(w_fd)


def test_xterm_modifier_function_key_decoded() -> None:
    """Shared design: decode xterm modifier forms (`ESC [ 1;<n> P/Q/R/S`),
    e.g. Ctrl+F1 (`ESC [ 1;5 P`), to the base function key."""
    r_fd, w_fd = os.pipe()
    try:
        os.write(w_fd, b"\x1b[1;5P")
        reader = terminal_input.PosixKeyReader(r_fd)
        result = reader.read_key(timeout=0.5)
        assert result == "f1", f"ESC [ 1;5 P must decode to f1, got {result!r}"
    finally:
        os.close(r_fd)
        os.close(w_fd)


def test_csi_tilde_function_key_f2_still_decoded() -> None:
    """Keep-green guard: the existing CSI numeric-tilde form (`ESC [ 12~`
    -> f2) must keep working while SS3/Linux-console/xterm-modifier
    decoding is added."""
    r_fd, w_fd = os.pipe()
    try:
        os.write(w_fd, b"\x1b[12~")
        reader = terminal_input.PosixKeyReader(r_fd)
        result = reader.read_key(timeout=0.5)
        assert result == "f2"
    finally:
        os.close(r_fd)
        os.close(w_fd)


# ---------------------------------------------------------------------------
# Bracketed paste (POSIX raw_terminal + PosixKeyReader)
# ---------------------------------------------------------------------------


def test_raw_terminal_enables_bracketed_paste_mode() -> None:
    """Shared design: `raw_terminal` enables bracketed paste
    (`\\x1b[?2004h`)."""
    import pty

    master_fd, slave_fd = pty.openpty()
    try:
        with terminal_input.raw_terminal(slave_fd):
            pass
        written = _drain_available(master_fd)
        assert b"\x1b[?2004h" in written, (
            f"raw_terminal must write the bracketed-paste enable sequence; "
            f"got {written!r}"
        )
    finally:
        os.close(master_fd)
        os.close(slave_fd)


def test_raw_terminal_disables_bracketed_paste_in_finally_on_exception() -> None:
    """Shared design: bracketed paste is "disabled in `finally`" -- on a
    clean exit AND any exception, same guarantee `raw_terminal` already
    gives termios restore."""
    import pty

    master_fd, slave_fd = pty.openpty()
    try:
        with pytest.raises(RuntimeError), terminal_input.raw_terminal(slave_fd):
            raise RuntimeError("boom")
        written = _drain_available(master_fd)
        assert b"\x1b[?2004l" in written, (
            f"raw_terminal must disable bracketed paste in finally even on "
            f"an exception; got {written!r}"
        )
    finally:
        os.close(master_fd)
        os.close(slave_fd)


def test_bracketed_paste_sequence_decoded_as_single_paste_event() -> None:
    """Shared design: `ESC[200~...ESC[201~` becomes one `paste:<text>`
    event, with the pasted text preserved literally (including any
    embedded control bytes)."""
    r_fd, w_fd = os.pipe()
    try:
        os.write(w_fd, b"\x1b[200~sq\x1b[2J\x1b[201~")
        reader = terminal_input.PosixKeyReader(r_fd)
        result = reader.read_key(timeout=0.5)
        assert result == "paste:sq\x1b[2J", (
            f"a bracketed-paste sequence must decode to one paste:<text> "
            f"event with the content preserved literally, got {result!r}"
        )
    finally:
        os.close(r_fd)
        os.close(w_fd)


def test_paste_event_inserted_literally_into_search_text_field() -> None:
    """Shared design: a paste event is "inserted literally into a text
    field" -- here the search/filter buffer -- never interpreted as
    navigation or control keys."""
    project = tui.ProjectState(name="p", root=Path("/tmp/rush-t28f-paste"))
    state = tui.TuiState(projects=[project])
    state.mode = "search"
    tui._dispatch_key(state, "paste:sq\x1b[2J", _noop_actions())
    assert project.filter_text == "sq\x1b[2J", (
        f"paste content must be inserted literally into the active text "
        f"field, got filter_text={project.filter_text!r}"
    )
    assert state.mode == "search", "a paste must never exit the text field"


def test_paste_event_ignored_outside_text_field() -> None:
    """Keep-green guard: outside a text field a paste is ignored, never
    interpreted as a sequence of commands (e.g. it must never quit)."""
    project = tui.ProjectState(name="p", root=Path("/tmp/rush-t28f-paste2"))
    state = tui.TuiState(projects=[project])
    state.mode = "list"
    tui._dispatch_key(state, "paste:qqq", _noop_actions())
    assert state.should_quit is False
    assert state.mode == "list"


# ---------------------------------------------------------------------------
# Windows single-drain paste rule
# ---------------------------------------------------------------------------


class _FakeMsvcrt:
    def __init__(self, chars: list[str]) -> None:
        self._chars = list(chars)

    def kbhit(self) -> bool:
        return bool(self._chars)

    def getwch(self) -> str:
        return self._chars.pop(0)


def test_windows_single_char_drain_returns_plain_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep-green guard: a single buffered character is a normal key, not
    a paste."""
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "msvcrt", _FakeMsvcrt(["x"]))
    reader = terminal_input.WindowsKeyReader()
    assert reader.read_key(timeout=0.2) == "x"


def test_windows_multi_char_drain_returns_paste_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shared design: "characters available in a single `kbhit` drain
    count as a paste only if there is more than one printable character."
    `WindowsKeyReader.read_key` returns after the first `getwch()` today,
    so a 3-character single-drain paste ("abc") is misreported as the
    single key "a"."""
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "msvcrt", _FakeMsvcrt(["a", "b", "c"]))
    reader = terminal_input.WindowsKeyReader()
    result = reader.read_key(timeout=0.2)
    assert result == "paste:abc", (
        f"a multi-character single kbhit drain must be reported as one "
        f"paste event, got {result!r}"
    )


# ---------------------------------------------------------------------------
# EOF
# ---------------------------------------------------------------------------


def test_posix_key_reader_eof_returns_logical_eof_key() -> None:
    """Shared design: "EOF becomes the logical key `eof`." Today
    `os.read` returning `b""` is treated identically to "nothing ready
    yet" (`return None`), which the design gate calls a busy-loop."""
    r_fd, w_fd = os.pipe()
    os.close(w_fd)  # no writer left => os.read(r_fd, 1) reports EOF (b"")
    try:
        reader = terminal_input.PosixKeyReader(r_fd)
        result = reader.read_key(timeout=0.5)
        assert result == "eof", (
            f"EOF must decode to the logical key eof, got {result!r}"
        )
    finally:
        os.close(r_fd)


def test_run_interactive_tui_eof_detaches_restores_terminal_and_logs_cause(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Shared design: "EOF: Detach, then restore the terminal and print
    the cause on stderr." The `eof` logical key is unmapped in
    `_KEYMAP` today, so `_dispatch_key` no-ops on it forever."""
    seed = _seed("eof")
    reader = _ConstantReader("eof")
    state = run_interactive_tui(
        [seed],
        key_reader=reader,
        actions=_noop_actions(),
        use_live=False,
        max_ticks=5,
    )
    assert state.should_quit is True, "EOF must Detach (and so end the loop)"
    captured = capsys.readouterr()
    assert captured.err.strip() != "", (
        "EOF must print its cause on stderr before/while restoring the terminal"
    )


# ---------------------------------------------------------------------------
# Ctrl-C quit flow
# ---------------------------------------------------------------------------


def test_run_interactive_tui_sigint_idle_quits_immediately() -> None:
    """Shared design: "Ctrl-C (SIGINT caught in the loop): quit flow."
    With no running work this mirrors the plain `q` action -- an
    immediate quit, never an uncaught `KeyboardInterrupt`."""
    seed = _seed("sigint-idle")
    reader = _RaisingThenNoneReader(raise_count=1)
    raised = False
    state = None
    try:
        state = run_interactive_tui(
            [seed],
            key_reader=reader,
            actions=_noop_actions(),
            use_live=False,
            max_ticks=5,
        )
    except KeyboardInterrupt:
        raised = True
    assert not raised, "Ctrl-C must be caught inside the loop, never propagate"
    assert state is not None and state.should_quit is True


def test_run_interactive_tui_sigint_with_running_work_opens_quit_confirm() -> None:
    """Shared design + existing `q`-action parity: Ctrl-C with running
    work opens the same three-way quit_confirm choice `q` already gives,
    never an uncaught `KeyboardInterrupt`. No entry point catches
    `KeyboardInterrupt` inside `run_interactive_tui` at all yet -- named
    here via the plausible seam so the gap is explicit rather than
    silently exercising the idle path."""
    if not hasattr(tui, "_handle_sigint"):
        pytest.fail(
            "no rush.tui._handle_sigint (or equivalent) seam exists yet to "
            "catch KeyboardInterrupt inside run_interactive_tui's loop and "
            "route it through the same quit/quit_confirm logic as the q "
            "action; run_interactive_tui has no except KeyboardInterrupt at "
            "all today, so this case cannot be driven end to end without "
            "letting a real KeyboardInterrupt escape to pytest"
        )
    project = tui.ProjectState(
        name="sigint-running",
        root=Path("/tmp/rush-t28f-sigint-running"),
        status="scanning",
    )
    state = tui.TuiState(projects=[project])
    tui._handle_sigint(state, _noop_actions())
    assert state.mode == "quit_confirm", (
        "Ctrl-C with running work must open quit_confirm, same as the q "
        f"action; got mode={state.mode!r}"
    )


def test_run_interactive_tui_second_sigint_during_quit_confirm_detaches() -> None:
    """Shared design: "A second Ctrl-C while `quit_confirm` is open means
    Detach.\""""
    seed = _seed("sigint-detach")
    reader = _RaisingThenNoneReader(raise_count=2)
    raised = False
    state = None
    try:
        state = run_interactive_tui(
            [seed],
            key_reader=reader,
            actions=_noop_actions(),
            use_live=False,
            max_ticks=5,
        )
    except KeyboardInterrupt:
        raised = True
    assert not raised, "Ctrl-C must be caught inside the loop, never propagate"
    assert state is not None and state.should_quit is True, (
        "a second Ctrl-C while quit_confirm is open must Detach (and so end the loop)"
    )


# ---------------------------------------------------------------------------
# Layout thresholds
# ---------------------------------------------------------------------------


def test_width_branch_thresholds_wide_compact_narrow() -> None:
    """Keep-green guard: Wide >= 100, Compact 80-99, Narrow 60-79
    (`_width_branch` already implements these three column breakpoints)."""
    assert tui._width_branch(100) == "wide"
    assert tui._width_branch(140) == "wide"
    assert tui._width_branch(99) == "compact"
    assert tui._width_branch(80) == "compact"
    assert tui._width_branch(79) == "narrow"
    assert tui._width_branch(60) == "narrow"


def test_resize_guidance_overlay_below_60x20_preserves_state() -> None:
    """Shared design: "Below 60x20: the `resize_guidance` overlay, which
    still accepts `q`, `c`, F2, and Escape and preserves all state."
    `TuiState` has no `overlay` field at all yet (only the older `mode`
    string), so this cannot exist yet."""
    project = tui.ProjectState(name="p", root=Path("/tmp/rush-t28f-resize"))
    state = tui.TuiState(projects=[project])
    state.terminal_size = (59, 19)
    if not hasattr(state, "overlay"):
        pytest.fail(
            "TuiState has no `overlay` field yet (T28 shared design: "
            "overlay ∈ {None, projects, sections, help, grant_review, form, "
            "quit_confirm, resize_guidance, detaching}); the below-60x20 "
            "resize_guidance overlay cannot be expressed without it"
        )
    project.selected_index = 2  # state that must be preserved
    tui.render_app(state)
    assert state.overlay == "resize_guidance"
    for key in ("q", "c", "f2", "escape"):
        tui._dispatch_key(state, key, _noop_actions())
        assert project.selected_index == 2, "resize_guidance must preserve state"


# ---------------------------------------------------------------------------
# Motion constants
# ---------------------------------------------------------------------------


def test_terminal_motion_constants_match_shared_design() -> None:
    """Shared design: `_TERMINAL_MOTION = {selection_ms:
    MOTION["hover_focus_ms"] (120), detail_ms: MOTION["detail_row_fade_ms"]
    (180), row_reveal_ms: 40, row_reveal_cap_ms: 240}`; `MOTION` itself
    stays unchanged."""
    if not hasattr(tui, "_TERMINAL_MOTION"):
        pytest.fail(
            "rush.tui._TERMINAL_MOTION does not exist yet (T28-F shared "
            "design: selection_ms=MOTION['hover_focus_ms'], "
            "detail_ms=MOTION['detail_row_fade_ms'], row_reveal_ms=40, "
            "row_reveal_cap_ms=240)"
        )
    assert tui._TERMINAL_MOTION == {
        "selection_ms": MOTION["hover_focus_ms"],
        "detail_ms": MOTION["detail_row_fade_ms"],
        "row_reveal_ms": 40,
        "row_reveal_cap_ms": 240,
    }
    assert MOTION["hover_focus_ms"] == 120
    assert MOTION["detail_row_fade_ms"] == 180


def test_row_reveal_progress_matches_pinned_spec() -> None:
    """Orchestrator resolution R28F.1 pins the exact entry point:
    `rush.tui._row_reveal_progress(elapsed_ms: float, total_rows: int, *,
    reduced_motion: bool) -> int`, returning `total_rows` if
    `reduced_motion` or `elapsed_ms >= 240`, else `min(total_rows, 1 +
    int(elapsed_ms // 40))`."""
    if not hasattr(tui, "_row_reveal_progress"):
        pytest.fail(
            "rush.tui._row_reveal_progress(elapsed_ms, total_rows, *, "
            "reduced_motion) does not exist yet (orchestrator resolution "
            "R28F.1)"
        )
    fn = tui._row_reveal_progress
    assert fn(elapsed_ms=0, total_rows=10, reduced_motion=False) == 1
    assert fn(elapsed_ms=39, total_rows=10, reduced_motion=False) == 1
    assert fn(elapsed_ms=40, total_rows=10, reduced_motion=False) == 2
    assert fn(elapsed_ms=79, total_rows=10, reduced_motion=False) == 2
    assert fn(elapsed_ms=239, total_rows=10, reduced_motion=False) == 6
    assert fn(elapsed_ms=240, total_rows=10, reduced_motion=False) == 10
    assert fn(elapsed_ms=1000, total_rows=3, reduced_motion=False) == 3
    assert fn(elapsed_ms=0, total_rows=7, reduced_motion=True) == 7


def test_reduced_motion_env_renders_final_reveal_state_immediately() -> None:
    """Shared design: "Reduced motion (`RUSH_REDUCED_MOTION`) renders the
    final state immediately" -- the final state is in the FIRST rendered
    frame (elapsed_ms=0)."""
    if not hasattr(tui, "_row_reveal_progress"):
        pytest.fail(
            "rush.tui._row_reveal_progress does not exist yet "
            "(orchestrator resolution R28F.1); cannot verify "
            "RUSH_REDUCED_MOTION renders the final reveal state immediately"
        )
    assert (
        tui._row_reveal_progress(elapsed_ms=0, total_rows=9, reduced_motion=True) == 9
    )


def test_live_refresh_capped_at_20hz_active_and_4hz_idle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep-green guard for `tui.py:2523-2524`'s existing active/idle
    refresh-rate limiter, driven by a fake clock instead of wall time:
    with no key/scan activity (idle), `Live.update` must be called at
    most every 1/4s (4Hz), never every tick."""
    import rich.live as rich_live_module

    update_calls: list[float] = []
    clock = [0.0]

    class _FakeLive:
        def __init__(self, renderable: object, **_kwargs: object) -> None:
            self.renderable = renderable

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

        def update(self, renderable: object, refresh: bool = False) -> None:
            update_calls.append(clock[0])

    class _TickReader:
        def read_key(self, timeout: float) -> str | None:
            clock[0] += 0.01
            return None

        def get_size(self) -> tuple[int, int]:
            return (80, 24)

    monkeypatch.setattr(rich_live_module, "Live", _FakeLive)
    monkeypatch.setattr(tui.time, "monotonic", lambda: clock[0])

    run_interactive_tui(
        [_seed("refresh-cap")],
        key_reader=_TickReader(),
        actions=_noop_actions(),
        use_live=True,
        max_ticks=60,
        tick_seconds=0.01,
    )
    # 60 ticks * 0.01s clock advance = ~0.6s elapsed; idle 4Hz cap allows at
    # most 0.6 / 0.25 + 1 ~= 4 updates (plus the unconditional first render).
    assert len(update_calls) <= 5, (
        f"idle refresh must be capped at 4Hz, got {len(update_calls)} "
        f"Live.update calls over ~0.6s of fake-clock time"
    )


# ---------------------------------------------------------------------------
# Detach, dashboard-owned polling, disabled-action disclosure, paste, resize,
# NO_COLOR (W4 "### T28-F" brief items)
# ---------------------------------------------------------------------------


def test_detach_is_non_blocking_with_deadline_overlay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shared design: "Detach: non-blocking. A `detaching` overlay with a
    deadline is polled every tick while the same `reap_owner_processes`
    and ledger outcome run." `_handle_detach` today blocks the calling
    (render-loop) thread inside `_wait_for_cancel_ack`'s own sleep loop
    until ack or timeout -- it never returns control to the loop early."""
    project = tui.ProjectState(
        name="p",
        root=Path("/tmp/rush-t28f-detach"),
        status="scanning",
        owner="local",
        owner_instance_id="owner-1",
        run_id="run-1",
    )
    state = tui.TuiState(projects=[project])
    state.mode = "quit_confirm"
    if not hasattr(state, "overlay"):
        pytest.fail(
            "TuiState has no `overlay` field yet; cannot express the "
            "non-blocking `detaching` overlay with a deadline"
        )
    project.ledger_admitted = True  # an admitted, still-unresolved run
    project.run_resolved = False
    monkeypatch.setattr(tui, "OWNED_TERMINATION_TIMEOUT_SECONDS", 0.3)
    order: list[tuple[str, float]] = []
    monkeypatch.setattr(
        tui,
        "reap_owner_processes",
        lambda *a, **k: order.append(("reap", time.monotonic())),
    )
    ledger_calls = _fake_ledger(monkeypatch)
    actions = ScanActions(
        plan_scan=lambda *a, **k: None,
        execute_scan=lambda *a, **k: None,
        # never acknowledges cancel
        cancel_scan_run=lambda *a, **k: order.append(("cancel", time.monotonic())),
        rescan_project_run=lambda *a, **k: None,
        build_handoff=lambda *a, **k: None,
        dispatch_handoff=lambda *a, **k: None,
        load_scan_events=lambda *a, **k: {"events": [], "run_state": None},
        list_agents=list,
    )
    start = time.monotonic()
    tui._dispatch_key(state, "d", actions)
    elapsed = time.monotonic() - start
    assert elapsed < 0.05, (
        "Detach must be non-blocking (return immediately with a detaching "
        f"overlay + deadline, polled every tick), took {elapsed:.3f}s"
    )
    assert state.overlay == "detaching"
    assert state.detach_deadline is not None

    _drive_detach_ticks(state, actions)

    assert state.detach_done is not None and state.detach_done.is_set(), (
        "the Detach worker must finish before the overlay deadline"
    )
    names = [name for name, _ in order]
    assert names == ["cancel", "reap"], (
        f"Phase 69 order is cancel, then reap only after no acknowledgment: {names}"
    )
    reap_at = order[1][1]
    assert reap_at - start >= tui.OWNED_TERMINATION_TIMEOUT_SECONDS, (
        "reap_owner_processes must wait out the acknowledgment window "
        f"({tui.OWNED_TERMINATION_TIMEOUT_SECONDS}s), ran after "
        f"{reap_at - start:.3f}s"
    )
    assert [c[1] for c in ledger_calls] == ["recovery_required"], ledger_calls


def _fake_ledger(monkeypatch: pytest.MonkeyPatch) -> list[tuple[object, ...]]:
    """Record MutationLedger status transitions instead of writing them."""
    calls: list[tuple[object, ...]] = []

    class _Ledger:
        def record_status_transition(self, *a: object, **_k: object) -> None:
            calls.append(a)

    monkeypatch.setattr(tui, "MutationLedger", _Ledger)
    return calls


def _drive_detach_ticks(state: tui.TuiState, actions: ScanActions) -> None:
    """The render loop's per-tick polling, every 10 ms, until the detach
    worker finishes or the overlay deadline passes."""
    bound = time.monotonic() + 10.0
    while not state.should_quit:
        assert time.monotonic() < bound, "detach never ended"
        tui._poll_running_scans(state, actions)
        tui._poll_detach(state)
        time.sleep(0.01)


def test_detach_acknowledged_cancel_never_reaps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase 69 semantics: an acknowledged cancel ends the Detach with no
    reap and no `recovery_required` ledger outcome."""
    project = tui.ProjectState(
        name="p",
        root=Path("/tmp/rush-t28f-detach-ack"),
        status="scanning",
        owner="local",
        owner_instance_id="owner-1",
        run_id="run-1",
    )
    project.plan_total = 1
    project.ledger_admitted = True  # an admitted, still-unresolved run
    project.run_resolved = False
    state = tui.TuiState(projects=[project])
    state.mode = "quit_confirm"
    monkeypatch.setattr(tui, "OWNED_TERMINATION_TIMEOUT_SECONDS", 0.3)
    reap_calls: list[object] = []
    monkeypatch.setattr(
        tui, "reap_owner_processes", lambda *a, **k: reap_calls.append((a, k))
    )
    ledger_calls = _fake_ledger(monkeypatch)
    cancelled: list[bool] = []
    actions = ScanActions(
        plan_scan=lambda *a, **k: None,
        execute_scan=lambda *a, **k: None,
        cancel_scan_run=lambda *a, **k: cancelled.append(True),
        rescan_project_run=lambda *a, **k: None,
        build_handoff=lambda *a, **k: None,
        dispatch_handoff=lambda *a, **k: None,
        load_scan_events=lambda *a, **k: {
            "events": [],
            "run_state": "cancelled" if cancelled else "running",
        },
        list_agents=list,
    )
    tui._dispatch_key(state, "d", actions)
    assert state.overlay == "detaching"

    _drive_detach_ticks(state, actions)

    assert cancelled, "Detach must request the cooperative cancel"
    assert state.detach_done is not None and state.detach_done.is_set()
    assert project.status == "cancelled"
    assert reap_calls == [], "an acknowledged cancel must never be reaped"
    assert ledger_calls == [], (
        f"an acknowledged cancel records no recovery_required: {ledger_calls}"
    )


def test_dashboard_owned_polling_reuses_captured_owner_not_per_tick() -> None:
    """Shared design: "Dashboard-owned polling: in the worker, reusing the
    captured `DashboardOwner` (`:1156` currently rediscovers it every
    tick)." `_poll_dashboard_owned_scan` calls `actions.dashboard_owner`
    (owner discovery) on every call today."""
    discovery_calls: list[Path] = []

    def _owner_finder(root: Path) -> object:
        discovery_calls.append(root)

        class _Owner:
            def operation_status(self, operation_id: str) -> dict[str, object]:
                return {"status": "running"}

        return _Owner()

    actions = ScanActions(
        plan_scan=lambda *a, **k: None,
        execute_scan=lambda *a, **k: None,
        cancel_scan_run=lambda *a, **k: None,
        rescan_project_run=lambda *a, **k: None,
        build_handoff=lambda *a, **k: None,
        dispatch_handoff=lambda *a, **k: None,
        load_scan_events=lambda *a, **k: {"events": [], "run_state": None},
        list_agents=list,
        dashboard_owner=_owner_finder,
    )
    project = tui.ProjectState(
        name="p",
        root=Path("/tmp/rush-t28f-owner"),
        status="scanning",
        owner="dashboard",
        operation_id="op-1",
    )
    state = tui.TuiState(projects=[project])
    for _ in range(5):
        tui._poll_running_scans(state, actions)
    assert len(discovery_calls) == 1, (
        "dashboard owner discovery must run once and be reused across "
        f"ticks, got {len(discovery_calls)} calls over 5 ticks"
    )


def test_disabled_actions_show_reason_in_rendered_output() -> None:
    """Shared design: "Disabled actions show their reason" -- driven from
    `ACTIONS[*].enabled(state) -> (bool, reason)`."""
    if not hasattr(tui, "ACTIONS"):
        pytest.fail(
            "rush.tui.ACTIONS action registry does not exist yet; disabled "
            "actions cannot disclose a reason in the footer/help/action "
            "pane without it"
        )
    project = tui.ProjectState(name="p", root=Path("/tmp/rush-t28f-actions"))
    state = tui.TuiState(projects=[project])
    disabled = [a for a in tui.ACTIONS if not a.enabled(state)[0]]
    assert disabled, "expected at least one disabled action for a fresh idle project"
    reason = disabled[0].enabled(state)[1]
    assert reason, "a disabled action must carry a non-empty reason"
    rendered = str(tui.render_app(state))
    assert reason in rendered, (
        f"disabled action {disabled[0].id!r}'s reason {reason!r} must appear "
        "in the rendered footer/help/action pane"
    )


def test_bracketed_paste_sq_esc2j_literal_no_scan_no_quit_no_clear_screen() -> None:
    """Shared design item 4: bracketed paste of exactly `"sq\x1b[2J"` into
    search must land as literal text, never start a scan, never quit, and
    never emit a live clear-screen escape."""
    import io

    from rich.console import Console

    plan_calls: list[object] = []
    execute_calls: list[object] = []
    actions = ScanActions(
        plan_scan=lambda *a, **k: plan_calls.append((a, k)),
        execute_scan=lambda *a, **k: execute_calls.append((a, k)),
        cancel_scan_run=lambda *a, **k: None,
        rescan_project_run=lambda *a, **k: None,
        build_handoff=lambda *a, **k: None,
        dispatch_handoff=lambda *a, **k: None,
        load_scan_events=lambda *a, **k: {"events": [], "run_state": None},
        list_agents=list,
    )
    project = tui.ProjectState(name="p", root=Path("/tmp/rush-t28f-paste3"))
    state = tui.TuiState(projects=[project])
    state.mode = "search"
    tui._dispatch_key(state, "paste:sq\x1b[2J", actions)
    assert project.filter_text == "sq\x1b[2J"
    assert state.should_quit is False
    assert not plan_calls and not execute_calls, "paste must never start a scan"
    console = Console(file=io.StringIO(), width=80, no_color=True, force_terminal=False)
    console.print(tui.render_app(state))
    rendered = console.file.getvalue()
    assert "\x1b[2J" not in rendered, (
        "pasted content must never be emitted as a live clear-screen escape"
    )


def test_resize_sequence_full_journey_preserves_state() -> None:
    """Shared design item 5: 120x40 -> 80x24 -> 60x20 -> 59x19 (guidance
    overlay) -> 120x40, with selection and expanded state kept. Drives
    each size directly (rather than through run_interactive_tui) so the
    starting selection/expanded state is exactly known and controlled."""
    project = tui.ProjectState(name="p", root=Path("/tmp/rush-t28f-resize2"))
    project.selected_index = 2
    state = tui.TuiState(projects=[project])
    state.map_expanded = {"src/rush"}
    original_selected_index = project.selected_index
    original_expanded = set(state.map_expanded)

    sizes_and_branches = [
        ((120, 40), "wide"),
        ((80, 24), "compact"),
        ((60, 20), "narrow"),
        ((59, 19), None),  # below the narrow floor -> resize_guidance
    ]

    if not hasattr(state, "overlay"):
        pytest.fail(
            "TuiState has no `overlay` field yet; cannot verify the "
            "resize_guidance overlay appears at 59x19 and clears again at "
            "120x40 while selection/expanded state is preserved"
        )

    for size, expected_branch in sizes_and_branches:
        state.terminal_size = size
        tui.render_app(state)
        if expected_branch is not None:
            assert tui._width_branch(size[0]) == expected_branch, (
                f"terminal_size={size} must render as the {expected_branch!r} "
                "layout class"
            )

    assert state.terminal_size == (59, 19)
    assert state.overlay == "resize_guidance", (
        "below 60x20 must show the resize_guidance overlay, got "
        f"overlay={state.overlay!r}"
    )

    if not hasattr(tui, "ACTIONS"):
        pytest.fail(
            "rush.tui.ACTIONS action registry does not exist yet; cannot "
            "verify q/c/F2/Escape stay accepted while resize_guidance is "
            "shown"
        )
    for key in ("q", "c", "f2", "escape"):
        bound = [action for action in tui.ACTIONS if key in action.keys]
        assert bound, (
            f"key {key!r} must still be accepted (bound to a real action) "
            "while resize_guidance is shown"
        )

    state.terminal_size = (120, 40)
    tui.render_app(state)
    assert tui._width_branch(120) == "wide"
    assert state.overlay is None, (
        "returning to 120x40 must clear the resize_guidance overlay, got "
        f"overlay={state.overlay!r}"
    )
    assert project.selected_index == original_selected_index, (
        "selection index must be preserved across the whole resize journey"
    )
    assert state.map_expanded == original_expanded, (
        "expanded state must be preserved across the whole resize journey"
    )


def test_no_color_rendered_output_has_no_colour_sgr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shared design item 6: NO_COLOR -> rendered output contains no
    colour SGR sequences."""
    import io
    import re

    from rich.console import Console

    ansi_color_code = re.compile(rb"\x1b\[[0-9;]*(?:3[0-8]|4[0-8]|9[0-7])(?:;[0-9]+)*m")
    monkeypatch.setenv("NO_COLOR", "1")
    project = tui.ProjectState(name="p", root=Path("/tmp/rush-t28f-nocolor"))
    state = tui.TuiState(projects=[project])
    console = Console(
        file=io.StringIO(), width=80, no_color=bool(os.environ.get("NO_COLOR"))
    )
    console.print(tui.render_app(state))
    rendered = console.file.getvalue().encode()
    match = ansi_color_code.search(rendered)
    assert match is None, f"NO_COLOR output must carry no colour SGR, found {match}"


# ---------------------------------------------------------------------------
# Non-TTY / --json / plain
# ---------------------------------------------------------------------------


def test_ui_json_non_tty_never_runs_check_suite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Shared design: "Neither mode ever runs checks." `ui_cmd` runs
    CHECK_SUITE via `run_workflow_suite` for both `--json` and plain
    non-TTY output today -- confirmed RED via the design gate's own
    finding (test_tui.py:73)."""
    from click.testing import CliRunner

    from rush.cli import cli

    proj = tmp_path / "proj"
    proj.mkdir()

    def _fail_run_workflow_suite(*a: object, **k: object) -> None:
        raise AssertionError(
            "ui --json must never run CHECK_SUITE (T28-F: non-TTY never runs "
            "checks; it prints a StatusTool snapshot instead)"
        )

    monkeypatch.setattr(suites_module, "run_workflow_suite", _fail_run_workflow_suite)

    runner = CliRunner()
    result = runner.invoke(cli, ["ui", "--json", str(proj)])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert isinstance(payload, list) and payload
    for row in payload:
        assert set(row) >= {"project", "path", "status"}


def test_ui_plain_non_tty_prints_status_and_next_hints_exit_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Shared design: plain non-TTY mode "prints one line per project plus
    `Next: rush status PATH --json` and `rush check PATH`", exit 0, and
    never runs checks."""
    from click.testing import CliRunner

    from rush.cli import cli

    proj = tmp_path / "proj"
    proj.mkdir()

    def _fail_run_workflow_suite(*a: object, **k: object) -> None:
        raise AssertionError("ui (plain, non-tty) must never run CHECK_SUITE")

    monkeypatch.setattr(suites_module, "run_workflow_suite", _fail_run_workflow_suite)

    runner = CliRunner()
    result = runner.invoke(cli, ["ui", str(proj)])

    assert result.exit_code == 0, result.output
    assert "Next: rush status" in result.output
    assert "rush check" in result.output
