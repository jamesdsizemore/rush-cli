"""T28-F review round 1 fixes (M5, M7, M8): slow bracketed paste, Windows
extended keys after a key, and `+`/`-` detail expansion in every section.

Plan (phase 70, T28-F): "POSIX selectors/SIGWINCH and Windows extended-key
input must both work; pasted UTF-8 is literal input, never terminal control
execution" and Phase 66's "`+`/`-` expands/collapses detail".
"""

from __future__ import annotations

import dataclasses
import os
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from rich.console import Console

from rush import tui
from rush.dashboard import terminal_input
from rush.tui import ScanActions


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


def _drain_keys(reader: terminal_input.PosixKeyReader, seconds: float) -> list[str]:
    keys: list[str] = []
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        key = reader.read_key(timeout=0.05)
        if key is not None:
            keys.append(key)
    return keys


# ---------------------------------------------------------------------------
# M7: a bracketed paste split by a stall longer than the 50 ms key timeout
# ---------------------------------------------------------------------------


def test_slow_bracketed_paste_stays_one_literal_event() -> None:
    # A 120 ms gap inside the paste does not end it: the whole payload is
    # one literal event and nothing after ESC[200~ runs as a key.
    r_fd, w_fd = os.pipe()
    try:
        os.write(w_fd, b"\x1b[200~ab")
        timer = threading.Timer(0.12, os.write, (w_fd, b"qC\x1b[201~"))
        timer.start()
        reader = terminal_input.PosixKeyReader(r_fd)
        first = reader.read_key(timeout=0.5)
        timer.join()
        assert first == "paste:abqC", f"slow paste split into keys: {first!r}"
        assert _drain_keys(reader, 0.2) == []
    finally:
        os.close(r_fd)
        os.close(w_fd)

    # A paste whose terminator never comes within the 2 s bound is emitted
    # as one event; the late rest of it is discarded up to ESC[201~, and a
    # key typed after the terminator is a key again.
    r_fd, w_fd = os.pipe()
    try:
        os.write(w_fd, b"\x1b[200~ab")
        reader = terminal_input.PosixKeyReader(r_fd)
        started = time.monotonic()
        first = reader.read_key(timeout=0.5)
        elapsed = time.monotonic() - started
        assert first == "paste:ab", f"stalled paste must emit its text: {first!r}"
        assert 1.9 <= elapsed <= 3.0, f"paste bound must be 2 s, took {elapsed:.2f}s"
        os.write(w_fd, b"qC\x1b[201~x")
        keys = _drain_keys(reader, 0.5)
        assert keys == ["x"], f"late paste text leaked out as keys: {keys!r}"
    finally:
        os.close(r_fd)
        os.close(w_fd)


# ---------------------------------------------------------------------------
# M8: Windows extended keys and repeated keys are not a paste
# ---------------------------------------------------------------------------


class _FakeMsvcrt:
    def __init__(self, chars: list[str]) -> None:
        self._chars = list(chars)

    def kbhit(self) -> bool:
        return bool(self._chars)

    def getwch(self) -> str:
        return self._chars.pop(0)


@pytest.mark.parametrize(
    ("chars", "expected"),
    [
        (["j", "\xe0", "P"], ["j", "down"]),
        (["\r", "\xe0", "H"], ["enter", "up"]),
        (["j", "\x00", "M"], ["j", "right"]),
        # Without VT input a burst cannot be told from a paste, so any
        # multi-character burst is literal text, never keys.
        (["j", "j", "j"], ["paste:jjj"]),
        (["q", "q"], ["paste:qq"]),
        (["a", "b", "\r"], ["paste:ab", "enter"]),
        (["a", "b", "\xe0", "H"], ["paste:ab", "up"]),
        (["a", "b", "c"], ["paste:abc"]),
    ],
)
def test_windows_extended_keys_after_a_key_are_keys_not_paste(
    monkeypatch: pytest.MonkeyPatch, chars: list[str], expected: list[str]
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "msvcrt", _FakeMsvcrt(chars))
    reader = terminal_input.WindowsKeyReader()
    keys: list[str] = []
    for _ in range(len(chars) + 1):
        key = reader.read_key(timeout=0.02)
        if key is None:
            break
        keys.append(key)
    assert keys == expected


def test_windows_search_paste_then_enter_keeps_enter_a_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "msvcrt", _FakeMsvcrt(["a", "b", "\r"]))
    reader = terminal_input.WindowsKeyReader()
    project = tui.ProjectState(name="p", root=Path("/tmp/rush-t28f-r1-search"))
    state = tui.TuiState(projects=[project])
    state.mode = "search"
    for _ in range(4):
        key = reader.read_key(timeout=0.02)
        if key is None:
            break
        tui._dispatch_key(state, key, _noop_actions())
    assert project.filter_text == "ab"
    assert state.mode != "search", "Enter must end the search, not be inserted"


# ---------------------------------------------------------------------------
# M5: `+`/`-` expand/collapse detail in every section
# ---------------------------------------------------------------------------


def _main_panes(state: tui.TuiState) -> list[str]:
    layout = tui.render_app(state)
    return [child.name or "" for child in layout["main"].children]


@pytest.mark.parametrize("section", tui.SECTIONS)
def test_plus_minus_expand_and_collapse_detail_in_every_section(section: str) -> None:
    project = tui.ProjectState(name="p", root=Path(f"/tmp/rush-t28f-r1-{section}"))
    state = tui.TuiState(projects=[project])
    state.terminal_size = (120, 40)
    state.section = project.section = section
    state.mode = tui._SECTION_MODES.get(section, "list")
    actions = _noop_actions()
    before_mode = state.mode
    before_map = set(state.map_expanded)

    tui._dispatch_key(state, "+", actions)
    assert state.detail_expanded is True, f"+ must expand detail in {section}"
    assert state.mode == before_mode and state.section == section
    assert state.map_expanded == before_map, "+ is detail, not a Map node"
    if before_mode in ("list", "map"):
        panes = _main_panes(state)
        assert "detail" in panes and "list" not in panes, panes

    tui._dispatch_key(state, "-", actions)
    assert state.detail_expanded is False, f"- must collapse detail in {section}"
    assert state.mode == before_mode and state.section == section
    if before_mode in ("list", "map"):
        assert _main_panes(state) == ["nav", "list", "detail"]


def test_plus_minus_are_distinct_detail_actions_and_map_keeps_l_h() -> None:
    keymap = tui._KEYMAP
    assert keymap.get_action_for_key("+") == "detail_expand"
    assert keymap.get_action_for_key("-") == "detail_collapse"
    assert keymap.get_action_for_key("l") == "map_expand"
    assert keymap.get_action_for_key("right") == "map_expand"
    assert keymap.get_action_for_key("h") == "map_collapse"
    assert keymap.get_action_for_key("left") == "map_collapse"


def test_plus_minus_typed_literally_in_search() -> None:
    project = tui.ProjectState(name="p", root=Path("/tmp/rush-t28f-r1-typed"))
    state = tui.TuiState(projects=[project])
    state.mode = "search"
    for key in ("+", "-"):
        tui._dispatch_key(state, key, _noop_actions())
    assert project.filter_text == "+-"
    assert state.detail_expanded is False


# ---------------------------------------------------------------------------
# Windows console in VT input mode: bracketed paste is literal, repeats are keys
# ---------------------------------------------------------------------------


_VT_INPUT = 0x0200
_VT_PROCESSING = 0x0004


def _fake_kernel32(modes: dict[int, int]) -> SimpleNamespace:
    """The three console calls `raw_terminal` makes on Windows, over `modes`
    (standard handle number -> console mode)."""

    def get_mode(handle: int, mode: Any) -> int:
        mode.contents.value = modes[handle]
        return 1

    def set_mode(handle: int, mode: int) -> int:
        modes[handle] = mode
        return 1

    return SimpleNamespace(
        GetStdHandle=lambda which: which,
        GetConsoleMode=get_mode,
        SetConsoleMode=set_mode,
    )


def test_windows_vt_input_bracketed_paste_is_literal_and_repeat_is_keys(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    modes = {-10: 0x01F7, -11: 0x0003}
    original = dict(modes)
    monkeypatch.setattr(terminal_input, "_WINDOWS", True)
    monkeypatch.setattr(
        terminal_input, "_windows_kernel32", lambda: _fake_kernel32(modes)
    )
    monkeypatch.setattr(sys, "platform", "win32")
    chars = [
        *"\x1b[200~qq\rj\xe9\x1b[201~",  # a paste of q, q, Enter, j, e-acute
        *"jjj",  # key repeat outside brackets
        *"\x1b[A\x1b[B\x1b[C\x1b[D",  # arrows as VT sequences
        *"\x1bOQ\x1bOR\x1b[Z\r",  # F2, F3, Shift+Tab, Enter
        "\ud83d",  # a character outside the BMP arrives as two UTF-16 units
        "\ude00",
    ]
    monkeypatch.setitem(sys.modules, "msvcrt", _FakeMsvcrt(chars))
    reader = terminal_input.WindowsKeyReader()
    with terminal_input.raw_terminal():
        assert modes[-10] == original[-10] | _VT_INPUT
        assert modes[-11] == original[-11] | _VT_PROCESSING
        keys: list[str] = []
        for _ in range(len(chars)):
            key = reader.read_key(timeout=0.05)
            if key is None:
                break
            keys.append(key)
    assert keys == [
        "paste:qq\rj\xe9",
        "j",
        "j",
        "j",
        "up",
        "down",
        "right",
        "left",
        "f2",
        "f3",
        "shift_tab",
        "enter",
        "\U0001f600",
    ]
    assert modes == original, "console modes must be restored"
    out = capfd.readouterr().out
    assert out.index("\x1b[?2004h") < out.index("\x1b[?2004l")

    # A pasted `q` never quits: the paste is literal text for the loop.
    project = tui.ProjectState(name="p", root=Path("/tmp/rush-t28f-r1-vtpaste"))
    state = tui.TuiState(projects=[project])
    tui._dispatch_key(state, keys[0], _noop_actions())
    assert state.should_quit is False and state.mode != "quit_confirm"


# ---------------------------------------------------------------------------
# `+`/`-` in Git (commit detail) and Memory (record expand, same as `x`)
# ---------------------------------------------------------------------------


def _text(state: tui.TuiState) -> str:
    console = Console(record=True, width=120, height=40, no_color=True)
    console.print(tui.render_app(state))
    return console.export_text()


def _pump_until(
    state: tui.TuiState, actions: ScanActions, done: Callable[[tui.TuiState], bool]
) -> None:
    deadline = time.monotonic() + 2.0
    while True:
        tui._pump(state, actions)
        if done(state):
            return
        assert time.monotonic() < deadline, "request never settled"
        time.sleep(0.005)


class _MemoryRun:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, root: Path, **kwargs: Any) -> dict[str, Any]:
        self.calls.append((kwargs["operation"], dict(kwargs["request"])))
        return {"raw": {"data": {"id": "m2", "content": "second record body"}}}


def test_plus_minus_expand_and_collapse_detail_in_git_and_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.workflows import projects as wp

    diffs: list[str] = []

    def _diff(project_id: str, commit_hash: str, **_: Any) -> dict[str, Any]:
        diffs.append(commit_hash)
        return {
            "changed_paths": ["second.py"],
            "lines": ["+second change"],
            "truncated": False,
            "error": None,
        }

    monkeypatch.setattr(wp, "project_git_commit_diff", _diff)
    project = tui.ProjectState(name="p", root=tmp_path, project_id="pid-1")
    state = tui.TuiState(projects=[project])
    state.terminal_size = (120, 40)
    state.section = project.section = "git"
    state.mode = "git"
    state.git_data = {
        "git": {
            "has_git": True,
            "dirty": False,
            "history": [
                {"hash": "a" * 40, "author": "x", "date": "d", "subject": "first"},
                {"hash": "b" * 40, "author": "x", "date": "d", "subject": "second"},
            ],
        }
    }
    state.git_selected = 1
    actions = _noop_actions()

    tui._dispatch_key(state, "+", actions)
    _pump_until(state, actions, lambda s: s.git_expanded is not None)
    assert diffs == ["b" * 40], "+ shows the selected commit's detail"
    assert state.detail_expanded is True and state.mode == "git"
    assert "+second change" in _text(state)

    tui._dispatch_key(state, "-", actions)
    assert state.git_expanded is None and state.detail_expanded is False
    assert state.mode == "git"
    rendered = _text(state)
    assert "+second change" not in rendered and "second" in rendered

    # A `-` while the diff is still loading drops it: nothing reappears.
    tui._dispatch_key(state, "+", actions)
    tui._dispatch_key(state, "-", actions)
    time.sleep(0.1)
    tui._pump(state, actions)
    assert state.git_expanded is None

    # Memory: `+` is the same expand request `x` sends; `-` collapses it.
    memory_root = tmp_path / "memory"
    memory_root.mkdir()
    items = [
        {"id": "m1", "artifact_version": 1, "content": "first"},
        {"id": "m2", "artifact_version": 3, "content": "second"},
    ]
    expanded: list[Any] = []
    calls: list[list[tuple[str, dict[str, Any]]]] = []
    states: list[tui.TuiState] = []
    for key in ("x", "+"):
        run = _MemoryRun()
        memory_actions = dataclasses.replace(_noop_actions(), memory_run=run)
        mem_project = tui.ProjectState(name="m", root=memory_root)
        mem_state = tui.TuiState(projects=[mem_project])
        mem_state.terminal_size = (120, 40)
        mem_state.section = mem_project.section = "memory"
        mem_state.mode = "memory"
        mem_state.memory_items = [dict(item) for item in items]
        mem_state.memory_selected_index = 1
        tui._dispatch_key(mem_state, key, memory_actions)
        _pump_until(mem_state, memory_actions, lambda s: s.memory_request is None)
        expanded.append(mem_state.memory_expanded)
        calls.append(run.calls)
        states.append(mem_state)
        assert mem_state.mode == "memory"
    assert expanded[0] is not None and expanded[1] == expanded[0]
    assert calls[1] == calls[0] == [("expand", {"id": "m2", "version": 3})]
    plus_state = states[1]
    assert plus_state.detail_expanded is True
    assert "second record body" in _text(plus_state)

    tui._dispatch_key(plus_state, "-", memory_actions)
    assert plus_state.memory_expanded is None and plus_state.detail_expanded is False
    assert plus_state.mode == "memory"
    assert "second record body" not in _text(plus_state)
