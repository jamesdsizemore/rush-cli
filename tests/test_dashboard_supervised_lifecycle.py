"""Lifecycle of the dashboard's `_run_terminal_supervised` workers
(`handoff_send`, `provision_apply`): a worker never outlives its server's
shutdown into a released state store, and a failed terminal-status write is
recorded or logged, never raised as an unhandled thread exception."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from rush.dashboard import server as server_module
from rush.dashboard.server import create_dashboard_server


def _supervised_threads() -> list[threading.Thread]:
    return [
        t
        for t in threading.enumerate()
        if t.name.startswith("rush-supervised-") and t.is_alive()
    ]


def test_supervised_operation_never_outlives_server_shutdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(server_module, "SUPERVISED_SHUTDOWN_JOIN_SECONDS", 1.0)
    server, ctx, _token = create_dashboard_server({}, data_root=tmp_path / "data")
    finishing = ctx.mutations.reserve("proj", "req-finishing", "hash").operation_id
    stuck = ctx.mutations.reserve("proj", "req-stuck", "hash").operation_id
    release = threading.Event()

    def _finishing() -> dict[str, Any]:
        time.sleep(0.2)
        return {"status": "success", "which": "finishing"}

    def _stuck() -> dict[str, Any]:
        release.wait(30)
        return {"status": "success", "which": "stuck"}

    finishing_thread = ctx.start_terminal_supervised(finishing, _finishing)
    stuck_thread = ctx.start_terminal_supervised(stuck, _stuck)
    try:
        server.server_close()

        # Joined within the bound: terminal before close returned.
        assert not finishing_thread.is_alive()
        finished = ctx.mutations.get_operation_status(finishing)
        assert finished is not None
        assert finished["status"] == "terminal"
        assert finished["payload"] == {"status": "success", "which": "finishing"}

        # Still running past the bound: shutdown recorded its terminal.
        abandoned = ctx.mutations.get_operation_status(stuck)
        assert abandoned is not None
        assert abandoned["status"] == "terminal"
        assert abandoned["payload"]["status"] == "error"
        assert abandoned["payload"]["code"] == "server_shutdown"

        writes: list[str] = []
        monkeypatch.setattr(
            ctx.mutations,
            "record_status_transition",
            lambda operation_id, status, payload: writes.append(operation_id),
        )
    finally:
        release.set()
        stuck_thread.join(5)

    # The abandoned worker exits without touching the state store again.
    assert not stuck_thread.is_alive()
    assert writes == []
    assert _supervised_threads() == []
    assert ctx.mutations.get_operation_status(stuck) == abandoned


def test_supervised_terminal_write_failure_is_recorded_not_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    thread_errors: list[Any] = []
    monkeypatch.setattr(threading, "excepthook", thread_errors.append)
    server, ctx, _token = create_dashboard_server({}, data_root=tmp_path / "data")
    try:
        # A payload the store cannot serialize: the failure itself becomes
        # the operation's recorded terminal state.
        unserializable = ctx.mutations.reserve("proj", "req-bad", "hash").operation_id
        thread = ctx.start_terminal_supervised(
            unserializable, lambda: {"status": "success", "bad": object()}
        )
        thread.join(5)
        assert not thread.is_alive()
        recorded = ctx.mutations.get_operation_status(unserializable)
        assert recorded is not None
        assert recorded["status"] == "terminal"
        assert recorded["payload"]["status"] == "error"
        assert recorded["payload"]["code"] == "terminal_write_failed"

        # The store itself unreachable: surfaced through the log.
        unreachable = ctx.mutations.reserve("proj", "req-gone", "hash").operation_id

        def _store_gone(*_args: Any, **_kwargs: Any) -> None:
            raise OSError("unable to open database file")

        monkeypatch.setattr(ctx.mutations, "record_status_transition", _store_gone)
        server_logger = logging.getLogger("rush.dashboard.server")
        server_logger.addHandler(caplog.handler)
        try:
            with caplog.at_level(logging.ERROR, logger="rush.dashboard.server"):
                thread = ctx.start_terminal_supervised(
                    unreachable, lambda: {"status": "success"}
                )
                thread.join(5)
        finally:
            server_logger.removeHandler(caplog.handler)
        assert not thread.is_alive()
        assert unreachable in caplog.text
        assert "unable to open database file" in caplog.text
    finally:
        server.server_close()
    assert thread_errors == []
    assert _supervised_threads() == []
