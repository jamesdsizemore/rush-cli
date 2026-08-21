"""Authenticated in-memory ephemeral dashboard and rich TUI."""

from __future__ import annotations

from rush.dashboard.auth import SessionAuthManager
from rush.dashboard.keymaps import DEFAULT_KEYBINDINGS, KeybindingAction, KeymapManager
from rush.dashboard.metrics import DashboardMetricsAggregator, QualityMetrics
from rush.dashboard.state import DashboardState, InMemoryStateStore
from rush.dashboard.static_assets import DASHBOARD_HTML_TEMPLATE

__all__ = [
    "DASHBOARD_HTML_TEMPLATE",
    "DEFAULT_KEYBINDINGS",
    "DashboardMetricsAggregator",
    "DashboardState",
    "InMemoryStateStore",
    "KeybindingAction",
    "KeymapManager",
    "QualityMetrics",
    "SessionAuthManager",
]
