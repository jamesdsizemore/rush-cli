"""T28-F review round 1, part B: the run loop, frame pacing, motion, the F3
chooser and Ctrl-C.

Each case reproduces one defect the round-1 review found
(`.orchestrator/review-T28-F-1-detail.md` M1, M2, M3, M4, M6, m1, m2) through
the real `run_interactive_tui` loop, with a fake clock, a fake dashboard
owner and a recording `Live`. Plan lines 430-431; design gate W4 T28-F
("Dashboard-owned polling: in the worker"; 20 Hz active / 4 Hz idle,
selection 120 ms, detail 180 ms; reduced motion renders the final state).
"""

from __future__ import annotations

import io
import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import pytest
import rich.live as rich_live_module
from rich.console import Console

import rush.dashboard.server as server_module
from rush import tui
from rush.tui import ProjectSeed, ScanActions, run_interactive_tui
from rush.tools.base import Finding, ToolResult


@pytest.fixture(autouse=True)
def _zero_spawn_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    def _no_spawn(*_a: object, **_k: object) -> None:
        raise AssertionError("test must not spawn a subprocess")

    monkeypatch.setattr(subprocess, "Popen", _no_spawn)
    monkeypatch.setattr(subprocess, "run", _no_spawn)


@pytest.fixture(autouse=True)
def _motion_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RUSH_REDUCED_MOTION", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)


def _actions(**overrides: Any) -> ScanActions:
    base: dict[str, Any] = {
        "plan_scan": lambda *a, **k: None,
        "execute_scan": lambda *a, **k: None,
        "cancel_scan_run": lambda *a, **k: {},
        "rescan_project_run": lambda *a, **k: {},
        "build_handoff": lambda *a, **k: None,
        "dispatch_handoff": lambda *a, **k: None,
        "load_scan_events": lambda *a, **k: {"events": [], "run_state": None},
        "list_agents": list,
    }
    base.update(overrides)
    return ScanActions(**base)


def _findings_seed(root: Path, count: int = 5) -> ProjectSeed:
    findings = [
        Finding(path="a.py", line=3 + 4 * idx, severity="error", message=f"msg-{idx}")
        for idx in range(count)
    ]
    return ProjectSeed(
        name="demo",
        root=root,
        results=[ToolResult(tool="lint", status="fail", findings=findings)],
    )


def _source_file(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "a.py").write_text(
        "".join(f"srcline-{n:02d}\n" for n in range(1, 41)), encoding="utf-8"
    )


class _Clock:
    """A fake monotonic clock the key reader advances 10 ms per read."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


class _ScriptedReader:
    """Advances the fake clock 10 ms per read and returns each scripted key
    on the first read at or after its time."""

    def __init__(
        self,
        clock: _Clock,
        script: list[tuple[float, str]],
        size: tuple[int, int] = (120, 40),
        repeat: str | None = None,
    ) -> None:
        self._clock = clock
        self._script = list(script)
        self._size = size
        self._repeat = repeat

    def read_key(self, timeout: float) -> str | None:
        self._clock.now = round(self._clock.now + 0.01, 6)
        if self._repeat is not None:
            return self._repeat
        if self._script and self._clock.now >= self._script[0][0] - 1e-9:
            return self._script.pop(0)[1]
        return None

    def get_size(self) -> tuple[int, int]:
        return self._size


def _record_frames(
    monkeypatch: pytest.MonkeyPatch, clock: _Clock, probe: Any
) -> list[tuple[float, Any]]:
    """Replace Rich's `Live` so every refreshed frame records the fake time
    and `probe(renderable)`, measured at the moment it was shown."""
    frames: list[tuple[float, Any]] = []

    class _RecordingLive:
        def __init__(self, renderable: object, **_kwargs: object) -> None:
            pass

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

        def update(self, renderable: object, refresh: bool = False) -> None:
            if refresh:
                frames.append((clock.now, probe(renderable)))

    monkeypatch.setattr(rich_live_module, "Live", _RecordingLive)
    return frames


def _capture_state(monkeypatch: pytest.MonkeyPatch, setup: Any = None) -> list[Any]:
    """Wrap the loop's `_pump` to capture the loop's `TuiState` (and run
    `setup(state)` once, on the first tick)."""
    holder: list[Any] = []
    real_pump = tui._pump

    def _pump(state: tui.TuiState, actions: ScanActions) -> bool:
        if not holder:
            holder.append(state)
            if setup is not None:
                setup(state)
        return real_pump(state, actions)

    monkeypatch.setattr(tui, "_pump", _pump)
    return holder


def _lines(renderable: Any, width: int, height: int) -> list[list[Any]]:
    console = Console(
        width=width,
        height=height,
        file=io.StringIO(),
        force_terminal=True,
        color_system="standard",
    )
    return console.render_lines(
        renderable, console.options.update(width=width, height=height), pad=False
    )


# ---------------------------------------------------------------------------
# M1: dashboard-owned polling runs on the worker, never on the loop
# ---------------------------------------------------------------------------


class _HungDashboardOwner:
    """A dashboard that accepted the scan but never answers a status poll:
    every `operation_status` call blocks 0.5 s (the real client blocks up
    to its 5 s/10 s urlopen timeouts) until `finish` is set."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.status_threads: list[threading.Thread] = []
        self.finish = threading.Event()

    def dispatch(self, operation: str, **_arguments: object) -> dict[str, object]:
        self.calls.append(operation)
        if operation == "cancel":
            return {}
        return {"operation_id": "op-1", "run_id": "run-d"}

    def operation_status(self, operation_id: str) -> dict[str, object]:
        self.status_threads.append(threading.current_thread())
        if self.finish.wait(0.5):
            return {"status": "terminal", "payload": {"status": "cancelled"}}
        return {"status": "running"}


def test_hung_dashboard_never_blocks_a_tick_and_cancel_stays_usable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    owner = _HungDashboardOwner()

    def _setup(state: tui.TuiState) -> None:
        tui._start_dashboard_owned(state.active_project, owner, "scan_start", {})

    holder = _capture_state(monkeypatch, _setup)
    work: list[float] = []
    marks: dict[str, float] = {}
    reads = [0]

    class _Reader:
        def read_key(self, timeout: float) -> str | None:
            now = time.monotonic()
            if "returned" in marks:
                work.append(now - marks["returned"])
            reads[0] += 1
            key = "c" if reads[0] == 20 else None
            if key is None:
                time.sleep(0.01)
            marks["returned"] = time.monotonic()
            return key

        def get_size(self) -> tuple[int, int]:
            return (120, 40)

    try:
        run_interactive_tui(
            [ProjectSeed(name="demo", root=tmp_path)],
            key_reader=_Reader(),
            actions=_actions(dashboard_owner=lambda root: owner),
            use_live=False,
            max_ticks=40,
            tick_seconds=0.01,
        )
        project = holder[0].active_project
        assert owner.status_threads, "the dashboard status was never polled"
        assert all(
            t is not threading.main_thread() for t in owner.status_threads
        ), "dashboard status polling must run on the worker, never the loop"
        assert max(work) < 0.05, (
            "a tick blocked on the unanswering dashboard for "
            f"{max(work):.3f}s (bound 50 ms)"
        )
        deadline = time.monotonic() + 2.0
        while "cancel" not in owner.calls and time.monotonic() < deadline:
            time.sleep(0.01)
        assert "cancel" in owner.calls, "cancel was never dispatched"
        assert project.status == "cancelling"
    finally:
        owner.finish.set()
    # The worker, not the (ended) loop, observes the terminal status.
    deadline = time.monotonic() + 3.0
    while project.status == "cancelling" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert project.status == "cancelled"


def test_failed_dashboard_session_is_cached_until_the_owner_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[str] = []

    def _unanswered(base_url: str, _capability: str) -> tuple[str, str]:
        attempts.append(base_url)
        raise TimeoutError("timed out")

    monkeypatch.setattr(server_module, "_control_session", _unanswered)
    owner = tui.DashboardOwner(
        base_url="http://127.0.0.1:9", control_capability="cap", project_id="p1"
    )
    for _ in range(3):
        with pytest.raises(Exception, match="timed out"):
            owner.operation_status("op-1")
    assert len(attempts) == 1, (
        f"a failed session must be cached, not retried per poll: {attempts}"
    )
    fresh = tui.DashboardOwner(
        base_url="http://127.0.0.1:9", control_capability="cap", project_id="p1"
    )
    with pytest.raises(Exception, match="timed out"):
        fresh.operation_status("op-1")
    assert len(attempts) == 2, "a new owner starts a fresh session"


# ---------------------------------------------------------------------------
# M2/M3: frame pacing
# ---------------------------------------------------------------------------


def test_key_frame_skipped_by_the_cap_is_shown_in_the_next_active_slot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    clock = _Clock()
    monkeypatch.setattr(tui.time, "monotonic", clock)
    holder = _capture_state(monkeypatch)
    frames = _record_frames(
        monkeypatch,
        clock,
        lambda _r: holder[0].active_project.selected_index,
    )
    reader = _ScriptedReader(clock, [(0.62, "j"), (0.64, "j")])
    run_interactive_tui(
        [_findings_seed(tmp_path)],
        key_reader=reader,
        actions=_actions(),
        max_ticks=100,
        tick_seconds=0.01,
    )
    shown = [t for t, sel in frames if sel == 2]
    assert shown, f"selection 2 was never shown: {frames}"
    assert shown[0] <= 0.64 + 0.05 + 1e-6, (
        f"the second j (at 0.64s) was first shown at {shown[0]:.2f}s; a "
        "skipped key frame must be drawn in the next 50 ms active slot"
    )


def test_reduced_motion_still_caps_refresh_at_20hz(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("RUSH_REDUCED_MOTION", "1")
    clock = _Clock()
    monkeypatch.setattr(tui.time, "monotonic", clock)
    frames = _record_frames(monkeypatch, clock, lambda _r: None)
    reader = _ScriptedReader(clock, [], repeat="j")
    run_interactive_tui(
        [_findings_seed(tmp_path)],
        key_reader=reader,
        actions=_actions(),
        max_ticks=50,
        tick_seconds=0.01,
    )
    times = [t for t, _ in frames]
    gaps = [b - a for a, b in zip(times, times[1:], strict=False)]
    assert len(times) <= 11, (
        f"{len(times)} refreshes in 0.5s under reduced motion (20 Hz cap = 11)"
    )
    assert min(gaps) >= 0.05 - 1e-6, f"refresh gap {min(gaps):.3f}s < 50 ms"


# ---------------------------------------------------------------------------
# M4: selection highlight 120 ms, detail reveal 180 ms
# ---------------------------------------------------------------------------


def _motion_probe(renderable: Any) -> tuple[Any, list[bool]]:
    """(style of the second findings-table row's Tool cell, whether each
    detail-pane source line is dim). That row is the line holding `a.py:7`
    and its severity; the detail pane's title names `a.py:7` without a
    severity. The Tool column's own style (cyan) carries no dim/reverse."""
    style = None
    detail_dim: list[bool] = []
    for line in _lines(renderable, 120, 40):
        text = "".join(segment.text for segment in line)
        detail_dim.extend(
            bool(seg.style and seg.style.dim)
            for seg in line
            if "srcline-" in seg.text
        )
        if "a.py:7" in text and "error" in text and style is None:
            style = next(seg.style for seg in line if "lint" in seg.text)
    return style, detail_dim


def _run_selection_journey(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> list[tuple[float, Any]]:
    _source_file(tmp_path)
    clock = _Clock()
    monkeypatch.setattr(tui.time, "monotonic", clock)

    def _setup(state: tui.TuiState) -> None:
        state.section = "scans"

    _capture_state(monkeypatch, _setup)
    frames = _record_frames(monkeypatch, clock, _motion_probe)
    reader = _ScriptedReader(clock, [(1.0, "j")])
    run_interactive_tui(
        [_findings_seed(tmp_path)],
        key_reader=reader,
        actions=_actions(),
        max_ticks=160,
        tick_seconds=0.01,
    )
    return [(round(t - 1.0, 6), probe) for t, probe in frames if t >= 1.0 - 1e-9]


def test_selection_highlight_and_detail_reveal_animate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    frames = _run_selection_journey(monkeypatch, tmp_path)
    assert frames, "no frame after the selection moved"
    selection_ms = tui._TERMINAL_MOTION["selection_ms"] / 1000
    detail_ms = tui._TERMINAL_MOTION["detail_ms"] / 1000
    assert (selection_ms, detail_ms) == (0.12, 0.18)

    during = [(e, s) for e, (s, _) in frames if e < selection_ms - 1e-6]
    after = [(e, s) for e, (s, _) in frames if e >= selection_ms - 1e-6]
    assert during and after, frames
    for elapsed, style in during:
        assert style is not None and style.reverse and style.dim, (
            f"{elapsed * 1000:.0f} ms into the selection the highlight must be "
            f"mid-transition (dim reverse), got {style}"
        )
    for elapsed, style in after:
        assert style is not None and style.reverse and not style.dim, (
            f"{elapsed * 1000:.0f} ms after the selection the highlight must be "
            f"final (reverse), got {style}"
        )
    assert after[0][0] <= selection_ms + 0.05 + 1e-6, (
        f"final highlight first shown at {after[0][0] * 1000:.0f} ms"
    )

    # The detail pane fades in (MOTION `detail_row_fade_ms`): its text is
    # dim for the first 180 ms after the selection moved, then normal.
    fading = [(e, d) for e, (_, d) in frames if e < detail_ms - 1e-6]
    shown = [(e, d) for e, (_, d) in frames if e >= detail_ms - 1e-6]
    assert fading and shown, frames
    for elapsed, dims in fading:
        assert dims and all(dims), (
            f"{elapsed * 1000:.0f} ms into the detail reveal its text must "
            f"still be fading in (dim), got {dims[:3]}"
        )
    for elapsed, dims in shown:
        assert dims and not any(dims), (
            f"{elapsed * 1000:.0f} ms after the selection the detail reveal "
            f"must be complete (not dim), got {dims[:3]}"
        )
    assert shown[0][0] <= detail_ms + 0.05 + 1e-6, (
        f"the revealed detail was first shown at {shown[0][0] * 1000:.0f} ms"
    )


def test_reduced_motion_shows_final_selection_and_detail_at_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("RUSH_REDUCED_MOTION", "1")
    frames = _run_selection_journey(monkeypatch, tmp_path)
    assert frames, "no frame after the selection moved"
    first_style, first_dims = frames[0][1]
    assert first_style is not None and first_style.reverse and not first_style.dim
    assert first_dims and not any(first_dims), (
        "reduced motion must show the revealed detail in the first frame"
    )


# ---------------------------------------------------------------------------
# M6: the F3 section chooser keeps the cursor and every row reachable
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("size", [(60, 20), (80, 24)])
def test_section_chooser_keeps_cursor_and_every_row_reachable(
    size: tuple[int, int], tmp_path: Path
) -> None:
    project = tui.ProjectState(name="demo", root=tmp_path)
    state = tui.TuiState(projects=[project])
    state.terminal_size = size
    actions = _actions()
    tui._dispatch_key(state, "f3", actions)
    assert state.overlay == "sections"
    rows = tui._chooser_rows()
    seen: set[str] = set()
    for step in range(len(rows) + 1):
        frame = str(tui.render_app(state))
        idx = state.chooser_index
        number = f"{idx + 1} " if rows[idx][0].startswith("section:") else "  "
        assert f">{number}{rows[idx][1]}" in frame, (
            f"at {size[0]}x{size[1]} the chooser cursor on row {idx} "
            f"({rows[idx][1]}) is not on screen after {step} j presses"
        )
        assert "[enter] choose" in frame, "the chooser hint line is cut"
        for i, (target, label) in enumerate(rows):
            num = f"{i + 1} " if target.startswith("section:") else "  "
            if f"{num}{label}" in frame:
                seen.add(label)
        tui._dispatch_key(state, "j", actions)
    assert seen == {label for _, label in rows}, (
        f"rows never reachable at {size}: {sorted({l for _, l in rows} - seen)}"
    )


# ---------------------------------------------------------------------------
# m1/m2: Ctrl-C while detaching, and a Ctrl-C inside the quit choice
# ---------------------------------------------------------------------------


def test_ctrl_c_while_detaching_keeps_detaching_until_reap_and_ledger(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(tui, "OWNED_TERMINATION_TIMEOUT_SECONDS", 0.2)
    reaps: list[float] = []

    def _reap(*_a: object, **_k: object) -> None:
        time.sleep(0.2)  # the bounded SIGTERM/SIGKILL waits
        reaps.append(time.monotonic())

    monkeypatch.setattr(tui, "reap_owner_processes", _reap)
    ledger: list[tuple[object, ...]] = []

    class _Ledger:
        def record_status_transition(self, *a: object, **_k: object) -> None:
            ledger.append(a)

    monkeypatch.setattr(tui, "MutationLedger", _Ledger)

    def _setup(state: tui.TuiState) -> None:
        project = state.active_project
        project.status = "scanning"
        project.owner = "local"
        project.owner_instance_id = "owner-1"
        project.run_id = "run-1"
        project.ledger_admitted = True
        project.run_resolved = False

    holder = _capture_state(monkeypatch, _setup)
    messages: list[str] = []
    reads = [0]

    class _Reader:
        def read_key(self, timeout: float) -> str | None:
            reads[0] += 1
            if reads[0] > 3 and holder:
                messages.append(holder[0].message)
            if reads[0] == 1:
                return "q"
            if reads[0] == 2:
                return "d"
            if reads[0] == 3:
                raise KeyboardInterrupt
            time.sleep(timeout)
            return None

        def get_size(self) -> tuple[int, int]:
            return (120, 40)

    try:
        state = run_interactive_tui(
            [ProjectSeed(name="demo", root=tmp_path)],
            key_reader=_Reader(),
            actions=_actions(),
            use_live=False,
            max_ticks=1000,
            tick_seconds=0.01,
        )
    except KeyboardInterrupt:
        pytest.fail("Ctrl-C escaped run_interactive_tui")
    assert state.should_quit
    assert reaps, "Ctrl-C while detaching quit before the worker reaped the run"
    assert [c[1] for c in ledger] == ["recovery_required"], (
        f"the loop exited before the recovery_required ledger write: {ledger}"
    )
    assert state.detach_done is not None and state.detach_done.is_set()
    assert any("detaching..." in m for m in messages), (
        f"Ctrl-C while detaching must show a 'detaching...' note: {messages[:5]}"
    )


def test_second_ctrl_c_inside_the_quit_choice_never_escapes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    before = signal.getsignal(signal.SIGINT)

    def _setup(state: tui.TuiState) -> None:
        state.active_project.status = "scanning"

    holder = _capture_state(monkeypatch, _setup)
    real_begin_detach = tui._begin_detach

    def _begin_detach(*args: Any, **kwargs: Any) -> None:
        # A further Ctrl-C lands while the quit choice is being handled.
        os.kill(os.getpid(), signal.SIGINT)
        time.sleep(0.01)
        real_begin_detach(*args, **kwargs)

    monkeypatch.setattr(tui, "_begin_detach", _begin_detach)
    reads = [0]

    class _Reader:
        def read_key(self, timeout: float) -> str | None:
            reads[0] += 1
            if reads[0] in (1, 2):
                os.kill(os.getpid(), signal.SIGINT)  # a real Ctrl-C
                time.sleep(0.01)
            return None

        def get_size(self) -> tuple[int, int]:
            return (120, 40)

    escaped = False
    state = None
    try:
        state = run_interactive_tui(
            [ProjectSeed(name="demo", root=tmp_path)],
            key_reader=_Reader(),
            actions=_actions(),
            use_live=False,
            max_ticks=20,
            tick_seconds=0.01,
        )
    except KeyboardInterrupt:
        escaped = True
    assert not escaped, "a Ctrl-C inside the quit choice escaped as a traceback"
    assert state is not None and state.should_quit, "the second Ctrl-C must Detach"
    assert holder and holder[0].mode == "list"
    assert signal.getsignal(signal.SIGINT) is before, "SIGINT handler not restored"
