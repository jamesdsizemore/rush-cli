"""Tests for Phase 27: Authenticated In-Memory Dashboard & Rich TUI."""

from __future__ import annotations

from pathlib import Path

from rush.dashboard.auth import SessionAuthManager
from rush.dashboard.keymaps import KeymapManager
from rush.dashboard.metrics import DashboardMetricsAggregator
from rush.dashboard.state import InMemoryStateStore
from rush.tools.base import ToolResult


def test_in_memory_state_store(tmp_path: Path) -> None:
    store = InMemoryStateStore(tmp_path)
    res: ToolResult = {
        "tool": "lint",
        "engine": "ruff",
        "engine_version": "0.4.0",
        "status": "ok",
        "duration_ms": 15,
        "summary": "all clean",
        "findings": [],
    }
    store.update_results([res])
    store.add_event("run_complete", {"tool": "lint"})

    snapshot = store.get_snapshot()
    assert snapshot["total_tools"] == 1
    assert snapshot["total_findings"] == 0
    assert len(snapshot["recent_events"]) == 1


def test_session_auth_manager() -> None:
    auth = SessionAuthManager()
    assert len(auth.session_token) > 20
    assert auth.verify_token(auth.session_token) is True
    assert auth.verify_token("invalid_token") is False
    assert auth.verify_token(None) is False


def test_dashboard_metrics_aggregator() -> None:
    res1: ToolResult = {
        "tool": "lint",
        "status": "ok",
        "duration_ms": 10,
        "summary": "ok",
        "findings": [],
    }
    res2: ToolResult = {
        "tool": "typecheck",
        "status": "fail",
        "duration_ms": 30,
        "summary": "error",
        "findings": [{"path": "a.py", "line": 1, "column": 1, "rule": "E1", "severity": "fail", "message": "fail"}],
    }

    metrics = DashboardMetricsAggregator.compute_metrics([res1, res2])
    assert metrics.pass_rate_percentage == 50.0
    assert metrics.total_findings == 1
    assert metrics.critical_findings == 1
    assert metrics.slowest_tool_name == "typecheck"


def test_keymap_manager() -> None:
    km = KeymapManager()
    assert km.get_action_for_key("q") == "quit"
    assert km.get_action_for_key("j") == "cursor_down"
    assert km.get_action_for_key("unknown") is None
