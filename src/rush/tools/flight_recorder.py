"""Agent flight recorder capturing millisecond-granularity JSON-RPC execution logs."""

import json
import time
import uuid
from pathlib import Path
from typing import Any

from rush.memory.migration import read_origin_kind_by_symbol
from rush.memory.store import MemoryArtifact, TypedArtifactStore
from rush.memory.trust import default_entry_tier


class FlightRecorder:
    """Records session events and tool invocations into .rush/sessions/flights/ for deterministic replay."""

    def __init__(self, project_root: Path | None = None, *, create: bool = True):
        self.project_root = project_root or Path.cwd()
        self.flights_dir = self.project_root / ".rush" / "sessions" / "flights"
        if create:
            self.flights_dir.mkdir(parents=True, exist_ok=True)

    def record_event(
        self, session_id: str, event_type: str, payload: dict[str, Any]
    ) -> None:
        from rush.safety.redactor import sanitize_value

        clean_payload = sanitize_value(payload).value
        flight_file = self.flights_dir / f"{session_id}.jsonl"
        entry = {
            "timestamp": time.time(),
            "event_type": event_type,
            "payload": clean_payload,
        }
        with open(flight_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

        # Forward-write path (P61.5.2, T-61.23): sanitize-then-write into TypedArtifactStore.
        # No origin_kind/origin_id is set here (matches checkpoint_journal.py's
        # _write_handoff_artifact precedent) so this per-event write never collides with, or gets
        # skipped by, migration.migrate_flight_recorder's (origin_kind="flight_event", origin_id)
        # idempotency check over the still-physically-present JSONL file.
        TypedArtifactStore(self.project_root).write(
            MemoryArtifact(
                id=str(uuid.uuid4()),
                family="experience",
                subject="episodic",
                trust_tier=default_entry_tier("local_tool"),
                content=entry,
                source="flight_recorder:record_event",
                created_at=entry["timestamp"],
                symbol_ref=session_id,
            )
        )

    def replay_session(self, session_id: str) -> list[dict[str, Any]]:
        flight_file = self.flights_dir / f"{session_id}.jsonl"
        if not flight_file.exists():
            # Already renamed `.migrated` by migration.migrate_flight_recorder(); fall back to
            # the TypedArtifactStore rows sharing this session's symbol_ref.
            return read_origin_kind_by_symbol(self.project_root, "flight_event", session_id)
        events = []
        with open(flight_file, "r", encoding="utf-8") as f:
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
