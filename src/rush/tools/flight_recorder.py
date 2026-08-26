"""Agent flight recorder capturing millisecond-granularity JSON-RPC execution logs."""

import json
import time
from pathlib import Path
from typing import Any


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
        flight_file = self.flights_dir / f"{session_id}.jsonl"
        entry = {
            "timestamp": time.time(),
            "event_type": event_type,
            "payload": payload,
        }
        with open(flight_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def replay_session(self, session_id: str) -> list[dict[str, Any]]:
        flight_file = self.flights_dir / f"{session_id}.jsonl"
        if not flight_file.exists():
            return []
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
