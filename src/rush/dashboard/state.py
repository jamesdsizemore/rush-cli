"""Pure in-memory thread-safe state store for ephemeral dashboard."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rush.tools.base import ToolResult


@dataclass
class DashboardState:
    repo_root: str
    started_at: float = field(default_factory=time.time)
    results: list[ToolResult] = field(default_factory=list)
    recent_events: list[dict[str, Any]] = field(default_factory=list)


class InMemoryStateStore:
    """Thread-safe in-memory store for findings, execution history, and active watchers."""

    def __init__(self, repo_root: Path) -> None:
        self._state = DashboardState(repo_root=str(repo_root.resolve()))
        self._lock = threading.Lock()

    def update_results(self, results: list[ToolResult]) -> None:
        with self._lock:
            self._state.results = list(results)

    def add_event(self, event_type: str, details: dict[str, Any]) -> None:
        with self._lock:
            self._state.recent_events.append(
                {
                    "timestamp": time.time(),
                    "type": event_type,
                    "details": details,
                }
            )
            if len(self._state.recent_events) > 200:
                self._state.recent_events = self._state.recent_events[-200:]

    def get_snapshot(self) -> dict[str, Any]:
        with self._lock:
            total_findings = sum(
                len(r.get("findings", [])) for r in self._state.results
            )
            return {
                "repo_root": self._state.repo_root,
                "started_at": self._state.started_at,
                "total_tools": len(self._state.results),
                "total_findings": total_findings,
                "results": list(self._state.results),
                "recent_events": list(self._state.recent_events),
            }
