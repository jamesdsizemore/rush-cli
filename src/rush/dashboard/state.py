"""Pure in-memory thread-safe state store for ephemeral dashboard."""

from __future__ import annotations

import base64
import threading
import time
from collections.abc import Callable
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


# --- Phase 66 P66-01: canonical per-server project scope --------------------
#
# ProjectRegistry/MutationLedger are constructed fresh per running dashboard
# server (see server.py::create_dashboard_server); they are never module- or
# class-level, so two concurrent servers never share project scope or
# mutation identities. Full Phase 65 snapshot/event wiring (scan progress,
# memory, git, artifacts) lands in later P66-02/03 packets -- this packet
# only needs project-scoped, sequenced snapshot data for the auth/API
# boundary itself.


@dataclass
class ProjectRecord:
    project_id: str
    source_identity: str
    snapshot: dict[str, Any]
    sequence: int = 1


class ProjectRegistry:
    """Per-server-instance registry of loaded project snapshots."""

    def __init__(self, projects: dict[str, dict[str, Any]]) -> None:
        self._lock = threading.Lock()
        self._projects: dict[str, ProjectRecord] = {
            project_id: ProjectRecord(
                project_id=project_id,
                source_identity=body.get("source_identity", project_id),
                snapshot=body,
            )
            for project_id, body in projects.items()
        }

    def get(self, project_id: str) -> ProjectRecord | None:
        with self._lock:
            return self._projects.get(project_id)

    def register(self, project_id: str, snapshot: dict[str, Any]) -> ProjectRecord:
        """Insert a newly added/created project's snapshot (P66-02: real
        `rush_project add|create` dispatch, never a UI-only registration).
        Idempotent: registering the same project_id again returns the
        existing record unchanged rather than resetting its sequence."""
        with self._lock:
            existing = self._projects.get(project_id)
            if existing is not None:
                return existing
            record = ProjectRecord(
                project_id=project_id,
                source_identity=snapshot.get("source_identity", project_id),
                snapshot=snapshot,
            )
            self._projects[project_id] = record
            return record

    def list_page(
        self, *, cursor: str | None, limit: int
    ) -> tuple[list[ProjectRecord], str | None]:
        """Paginate this server's currently-registered projects in stable
        insertion order. Cursor is an opaque offset -- this list is already
        behind session auth and is never the durable multi-session registry
        `list_projects_page` (Phase 65) signs with an HMAC key."""
        with self._lock:
            items = list(self._projects.values())
        offset = 0
        if cursor:
            try:
                offset = int(
                    base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
                )
            except (ValueError, UnicodeDecodeError):
                offset = 0
        page = items[offset : offset + limit]
        next_cursor: str | None = None
        if offset + limit < len(items):
            next_cursor = (
                base64.urlsafe_b64encode(str(offset + limit).encode("ascii"))
                .decode("ascii")
                .rstrip("=")
            )
        return page, next_cursor


class MutationLedger:
    """Per-server-instance idempotency cache for POST .../actions requests.

    Same request_id plus the same body hash returns the original response
    without allocating a second run; the same request_id with a different
    body hash conflicts. Run allocation happens under the same lock as the
    idempotency check so exactly one run is ever created per request_id
    even under concurrent duplicate requests.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._entries: dict[str, tuple[str, tuple[int, bytes]]] = {}
        self._run_counter = 0

    def commit(
        self,
        request_id: str,
        body_hash: str,
        builder: Callable[[], tuple[int, bytes]],
    ) -> tuple[tuple[int, bytes], bool]:
        """Return ((status_code, response_body), is_conflict) for a mutation
        request_id."""
        with self._lock:
            existing = self._entries.get(request_id)
            if existing is not None:
                existing_hash, existing_response = existing
                return existing_response, existing_hash != body_hash
            response = builder()
            self._entries[request_id] = (body_hash, response)
            return response, False

    def next_run_id(self) -> str:
        with self._lock:
            self._run_counter += 1
            return f"run-{self._run_counter}"


# --- Phase 66 P66-04: at most one active scan/rescan/resume per project ----
#
# `execute_scan`/`rescan_project_run`/`resume_scan_run` (rush.workflows.
# project_run) are real, potentially slow operations dispatched onto a
# background thread by server.py so the HTTP action itself returns 202
# immediately (plan Sec 3.7: "Expensive work is queued ... not held in HTTP
# worker"). `ScanRunTracker` is the per-server-instance guard that makes a
# browser refresh/reconnect *attach* to that same background job instead of
# spawning a duplicate: a second `scan_start`/`rescan`/`scan_resume` for a
# project that already has a live thread returns the existing job's
# identity unchanged and never starts a second thread.


@dataclass
class ActiveScan:
    run_id: str
    plan_id: str
    thread: threading.Thread


class ScanRunTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: dict[str, ActiveScan] = {}

    def start_or_attach(
        self,
        project_id: str,
        *,
        run_id: str,
        plan_id: str,
        thread: threading.Thread,
    ) -> tuple[str, str, bool]:
        """Return (run_id, plan_id, started). `thread` is not yet started;
        if a job is already active for `project_id` it is discarded and the
        existing job's identity is returned instead (`started=False`)."""
        with self._lock:
            existing = self._active.get(project_id)
            if existing is not None and existing.thread.is_alive():
                return existing.run_id, existing.plan_id, False
            self._active[project_id] = ActiveScan(
                run_id=run_id, plan_id=plan_id, thread=thread
            )
        thread.start()
        return run_id, plan_id, True

    def active_run_id(self, project_id: str) -> str | None:
        with self._lock:
            existing = self._active.get(project_id)
            if existing is not None and existing.thread.is_alive():
                return existing.run_id
            return None
