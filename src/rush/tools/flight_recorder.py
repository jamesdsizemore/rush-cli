"""Agent flight recorder capturing millisecond-granularity JSON-RPC execution logs."""

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from rush.io.physical_paths import ContainmentError
from rush.memory.authorization import literal_source_is_valid
from rush.memory.migration import read_origin_kind_by_symbol_readonly
from rush.memory.store import MemoryArtifact, write_checked_artifact
from rush.memory.trust import default_entry_tier

# The recorder's own sources: the forward write and the migrated rows.
_FLIGHT_SOURCES = ("flight_recorder:record_event", "migration:flight_recorder")


class FlightRecorder:
    """Records session events and tool invocations into .rush/sessions/flights/ for deterministic replay."""

    def __init__(self, project_root: Path | None = None, *, create: bool = True):
        # 72-T01 D4: construction has no effect; `record_event` creates the flights
        # directory only after the write is authorized (`create` is kept for callers).
        self.project_root = project_root or Path.cwd()
        self.flights_dir = self.project_root / ".rush" / "sessions" / "flights"
        self._create = create

    def _flight_fd(self, session_id: str, *, append: bool = False) -> int | None:
        """72-T01 security-2/13: the session's JSONL opened through the checked fd of
        `open_contained_file` (every component opened from the root's fd without
        following links; a regular, single-link file, so a hard link aliasing an
        outside inode is refused). A session id is one literal file label (no
        separator, traversal or absolute form). A refusal is `None`; an absent
        file (read) raises `FileNotFoundError`. The caller closes the fd."""
        from rush.workflows.projects import open_contained_file

        if (
            not literal_source_is_valid(session_id)
            or "/" in session_id
            or "\\" in session_id
        ):
            return None
        try:
            return open_contained_file(
                self.project_root,
                str(Path(".rush") / "sessions" / "flights" / f"{session_id}.jsonl"),
                append=append,
            )
        except FileNotFoundError:
            raise
        except (ContainmentError, ValueError, OSError):
            return None

    def _flight_usable(self, session_id: str) -> bool:
        """The session's JSONL is absent or passes the checked open; writes nothing."""
        try:
            fd = self._flight_fd(session_id)
        except FileNotFoundError:
            return True
        if fd is None:
            return False
        os.close(fd)
        return True

    def record_event(
        self, session_id: str, event_type: str, payload: dict[str, Any]
    ) -> None:
        """Append one event and forward-write it, after the shared writer gate; a
        denial writes nothing (no directory either) and never raises."""
        from rush.memory.retrieval import RouteDenial, authorize_writer
        from rush.memory.store import MemoryAccessChanged

        if not self._flight_usable(session_id):
            return
        with authorize_writer(
            Path(self.project_root).resolve(), "flight_recorder:record_event"
        ) as granted:
            if isinstance(granted, RouteDenial):
                return
            from rush.memory.retrieval import recheck_failure, writer_owner

            entry = self._build_event(event_type, payload)
            # Forward-write path (P61.5.2, T-61.23): sanitize-then-write into
            # TypedArtifactStore. No origin_kind/origin_id is set here (matches
            # checkpoint_journal.py's _write_handoff_artifact precedent) so this
            # per-event write never collides with, or gets skipped by,
            # migration.migrate_flight_recorder's (origin_kind="flight_event",
            # origin_id) idempotency check over the still-physically-present JSONL.
            try:
                write_checked_artifact(
                    self.project_root,
                    MemoryArtifact(
                        id=str(uuid.uuid4()),
                        family="experience",
                        subject="episodic",
                        trust_tier=default_entry_tier("local_tool"),
                        content=entry,
                        source="flight_recorder:record_event",
                        created_at=entry["timestamp"],
                        symbol_ref=session_id,
                        owner_scope=writer_owner(granted),
                    ),
                    commit_check=lambda: recheck_failure(granted),
                )
            except MemoryAccessChanged:
                return
            self._append_event(session_id, entry)

    @staticmethod
    def _build_event(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        """One sanitized event; touches no file."""
        from rush.safety.redactor import sanitize_value

        return {
            "timestamp": time.time(),
            "event_type": event_type,
            "payload": sanitize_value(payload).value,
        }

    def _append_event(self, session_id: str, entry: dict[str, Any]) -> None:
        """Append the event to the session's JSONL file through the checked append
        fd; runs only after the checked typed-store write committed."""
        if not self._flight_usable(session_id):
            return
        self.flights_dir.mkdir(parents=True, exist_ok=True)
        fd = self._flight_fd(session_id, append=True)
        if fd is None:
            return
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def replay_session(self, session_id: str) -> list[dict[str, Any]]:
        """72-T01 D1 (security-3): an `ask` read of the recorder's own sources. A
        denied route (a write-only or revoked grant) replays nothing, and so does an
        access that no longer holds once the events are read."""
        from rush.memory.retrieval import RouteDenial, reader_route

        access = reader_route(Path(self.project_root).resolve(), "ask", _FLIGHT_SOURCES)
        if isinstance(access, RouteDenial):
            return []
        events = self._replay_session(session_id)
        return events if access.recheck() == "ok" else []

    def _replay_session(self, session_id: str) -> list[dict[str, Any]]:
        """The session's events with no authorization of its own, for a caller that
        holds its own authority (`replay_session`'s `ask` route, or the writer-gated
        flight migration). A refused file gives []."""
        try:
            fd = self._flight_fd(session_id)
        except FileNotFoundError:
            # Already renamed `.migrated` by migration.migrate_flight_recorder(); fall back to
            # the TypedArtifactStore rows sharing this session's symbol_ref. T10: read-only
            # (no `.rush`, DB, `-wal`/`-shm` or migration is created); no DB gives [].
            return read_origin_kind_by_symbol_readonly(
                self.project_root, "flight_event", session_id
            )
        if fd is None:
            return []
        events = []
        with os.fdopen(fd, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    event = json.loads(line.strip())
                    if (
                        not isinstance(event, dict)
                        or not isinstance(event.get("event_type"), str)
                        or not isinstance(event.get("payload"), dict)
                    ):
                        raise ValueError("flight event has an invalid schema")
                    events.append(event)
        return events
