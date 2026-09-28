"""T28-F review round 1, part C: no blocking dashboard I/O on the key path.

Plan line 416: the interactive loop keeps responding while work, dashboards
or reads are slow. Two waits sat on the input thread: the dashboard cancel
key waited for the owner's answer, and starting a scan, rescan or check
resolved the dashboard owner (descriptor read + `/api/control/health`
probe) before returning. Both now run on the worker.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest

import rush.cli as cli_module
from rush import tui
from rush.tui import ProjectState, ScanActions


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


def _wait_until(predicate: Any, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.005)
    return True


def test_dashboard_cancel_key_never_waits_for_the_answer(tmp_path: Path) -> None:
    release = threading.Event()

    class _BlockingOwner:
        def __init__(self) -> None:
            self.calls: list[str] = []
            self.threads: list[threading.Thread] = []

        def dispatch(self, operation: str, **arguments: object) -> dict:
            self.threads.append(threading.current_thread())
            release.wait(5.0)
            self.calls.append(operation)
            return {}

    owner = _BlockingOwner()
    local_cancels: list[int] = []
    actions = _actions(
        cancel_scan_run=lambda *a, **k: local_cancels.append(1),
        dashboard_owner=lambda root: owner,
    )
    elapsed: list[float] = []
    try:
        for _ in range(3):
            project = ProjectState(name="demo", root=tmp_path)
            project.owner = "dashboard"
            project.work_kind = "dashboard"
            project.status = "scanning"
            project.run_id = "run-1"
            project.operation_id = "op-1"
            project.dashboard_owner_handle = owner
            t0 = time.monotonic()
            tui._request_cancel(project, actions)
            elapsed.append(time.monotonic() - t0)
            assert project.status == "cancelling"
            assert owner.calls == [], "the owner's answer is still pending"
        assert min(elapsed) < 0.025, (
            f"the cancel key waited {min(elapsed):.3f}s on the calling thread "
            "for the dashboard's answer"
        )
        assert _wait_until(lambda: len(owner.threads) == 3)
        assert all(t is not threading.current_thread() for t in owner.threads), (
            "the dashboard cancel must run on a worker, never the key path"
        )
    finally:
        release.set()
    assert _wait_until(lambda: owner.calls == ["cancel"] * 3)
    assert local_cancels == []
    assert project.status == "cancelling"


@pytest.mark.parametrize("start", ["scan", "rescan", "check"])
def test_scan_start_never_probes_the_dashboard_on_the_key_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, start: str
) -> None:
    descriptor_dir = tmp_path / "data" / "dashboard"
    descriptor_dir.mkdir(parents=True)
    (descriptor_dir / "srv.json").write_text(
        json.dumps(
            {
                "bound_host": "127.0.0.1",
                "bound_port": 9,
                "control_capability": "cap",
                "pid": 1,
                "start_nonce": "n",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        cli_module,
        "_dashboard_descriptor_path",
        lambda server_id: descriptor_dir / f"{server_id}.json",
    )
    release = threading.Event()
    probe_threads: list[threading.Thread] = []

    def _hung_health_probe(descriptor: dict[str, Any]) -> bool | None:
        # An unanswering dashboard: the health probe holds until released,
        # then reports "unknown" (never proof of a live owner).
        probe_threads.append(threading.current_thread())
        release.wait(1.0)
        return None

    monkeypatch.setattr(cli_module, "_check_descriptor_liveness", _hung_health_probe)
    monkeypatch.setattr(tui, "_tui_owner_instance_id", lambda: "tui:review1c")
    monkeypatch.setattr(tui, "_admit_local_run", lambda *a, **k: None)

    local_work: list[str] = []
    actions = _actions(
        execute_scan=lambda *a, **k: local_work.append("scan"),
        rescan_project_run=lambda *a, **k: local_work.append("rescan"),
        run_check_suite=lambda *a, **k: local_work.append("check"),
        dashboard_owner=tui._find_live_dashboard_owner,
    )
    project = ProjectState(name="demo", root=tmp_path / "project")
    begin = {
        "scan": tui._start_scan_thread,
        "rescan": tui._start_rescan_thread,
        "check": tui._start_initial_check_thread,
    }[start]

    try:
        t0 = time.monotonic()
        begin(project, actions)
        elapsed = time.monotonic() - t0
        assert elapsed < 0.05, (
            f"starting a {start} blocked the key path {elapsed:.3f}s on the "
            "dashboard owner probe (bound 50 ms)"
        )
        assert project.status == "scanning"
        assert project.work_kind == "starting", (
            "the project must show the start is in progress"
        )
        assert local_work == [], "the ownership decision is still pending"
        assert _wait_until(lambda: bool(probe_threads))
    finally:
        release.set()
    assert project.scan_thread is not None
    project.scan_thread.join(timeout=5)
    assert all(t is not threading.main_thread() for t in probe_threads), (
        "owner resolution must run on the worker, never the key path"
    )
    assert local_work == [start]
    assert project.owner == "local"


class _CancelAwareOwner:
    """A live dashboard owner whose `scan_start` dispatch can be held open;
    its run reports terminal `cancelled` once a cancel has reached it."""

    def __init__(self, hold: threading.Event | None = None) -> None:
        self.hold = hold
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.dispatching = threading.Event()

    def dispatch(self, operation: str, **arguments: object) -> dict:
        if operation != "cancel" and self.hold is not None:
            self.dispatching.set()
            self.hold.wait(5.0)
        self.calls.append((operation, arguments))
        return {"operation_id": "op-9", "run_id": "run-9"}

    def operation_status(self, operation_id: str) -> dict:
        if any(op == "cancel" for op, _ in self.calls):
            return {"status": "terminal", "payload": {"status": "cancelled"}}
        return {"status": "running"}


@pytest.mark.parametrize("owner_kind", ["local", "dashboard"])
@pytest.mark.parametrize("start", ["scan", "rescan", "check"])
def test_cancel_while_starting_is_honored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, start: str, owner_kind: str
) -> None:
    """Plan line 430: cancellation stays usable while waiting. A cancel
    pressed while the start worker is still resolving the owner returns at
    once, and the start then launches and dispatches nothing."""
    admit_calls: list[object] = []
    monkeypatch.setattr(tui, "_tui_owner_instance_id", lambda: "tui:review1c")
    monkeypatch.setattr(
        tui, "_admit_local_run", lambda *a, **k: admit_calls.append((a, k))
    )
    release = threading.Event()
    resolving = threading.Event()
    owner = _CancelAwareOwner()

    def _slow_owner_finder(root: Path) -> Any:
        resolving.set()
        release.wait(5.0)
        return owner if owner_kind == "dashboard" else None

    local_work: list[str] = []
    local_cancels: list[object] = []
    actions = _actions(
        execute_scan=lambda *a, **k: local_work.append("scan"),
        rescan_project_run=lambda *a, **k: local_work.append("rescan"),
        run_check_suite=lambda *a, **k: local_work.append("check"),
        cancel_scan_run=lambda *a, **k: local_cancels.append(a),
        dashboard_owner=_slow_owner_finder,
    )
    project = ProjectState(name="demo", root=tmp_path / "project")
    project.run_id = "earlier-run"
    begin = {
        "scan": tui._start_scan_thread,
        "rescan": tui._start_rescan_thread,
        "check": tui._start_initial_check_thread,
    }[start]

    try:
        begin(project, actions)
        assert resolving.wait(5.0)
        assert project.work_kind == "starting"
        t0 = time.monotonic()
        tui._request_cancel(project, actions)
        elapsed = time.monotonic() - t0
        assert elapsed < 0.025, f"the cancel key waited {elapsed:.3f}s"
        assert project.status == "cancelling", (
            "a cancel while starting must be accepted, not refused"
        )
    finally:
        release.set()
    assert project.scan_thread is not None
    project.scan_thread.join(timeout=5)
    assert not project.scan_thread.is_alive()
    assert local_work == [], "a cancelled start must never launch local work"
    assert admit_calls == [], "a cancelled start must never reserve work"
    assert owner.calls == [], "a cancelled start must never dispatch work"
    assert local_cancels == []
    assert project.status == "cancelled"


def test_cancel_during_dashboard_dispatch_reaches_the_new_run(
    tmp_path: Path,
) -> None:
    """A cancel pressed after the start was handed to the dashboard but
    before its operation id came back is forwarded to that run once the
    dispatch answers."""
    hold = threading.Event()
    owner = _CancelAwareOwner(hold)
    actions = _actions(dashboard_owner=lambda root: owner)
    project = ProjectState(name="demo", root=tmp_path / "project")

    try:
        tui._start_scan_thread(project, actions)
        assert owner.dispatching.wait(5.0)
        t0 = time.monotonic()
        tui._request_cancel(project, actions)
        elapsed = time.monotonic() - t0
        assert elapsed < 0.025, f"the cancel key waited {elapsed:.3f}s"
        assert project.status == "cancelling"
        assert owner.calls == [], "the start dispatch is still unanswered"
    finally:
        hold.set()
    assert _wait_until(lambda: len(owner.calls) >= 2)
    assert owner.calls[0][0] == "scan_start"
    assert owner.calls[1] == ("cancel", {"run_id": "run-9", "operation_id": "op-9"})
    assert project.scan_thread is not None
    project.scan_thread.join(timeout=5)
    assert not project.scan_thread.is_alive()
    # The render loop's observer worker (T28-F part B) reads the run's
    # durable status; the dispatch worker never polls it.
    tui._start_dashboard_observers(tui.TuiState(projects=[project]))
    assert _wait_until(lambda: project.status == "cancelled")
    assert len(owner.calls) == 2, "the cancel is forwarded exactly once"
