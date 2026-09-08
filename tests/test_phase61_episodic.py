"""Contract test T-61.23 for the Episodic/Session Family forward-write path
(Phase 61 §7, §9 P61.5.2)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import rush.hook.tamper_detector  # noqa: F401 -- import first, breaks a pre-existing circular

# import (memory.store -> hook -> tools -> continuity -> memory.checkpoint_journal ->
# memory.migration -> memory.store) that otherwise fires when a memory-package module is the
# first module of this cycle touched in the process (same workaround as test_phase61_handoff.py).
from rush.memory.store import TypedArtifactStore
from rush.safety.redactor import sanitize_value as real_sanitize_value
from rush.session_memory import SessionMemoryManager


def test_episodic_write_uses_flight_recorder_redaction_pattern(tmp_path: Path) -> None:
    """T-61.23: asserts a new episodic write path calls `sanitize_value` the same way
    `FlightRecorder.record_event` does (spy the call), not a re-implemented redaction path,
    and that the record actually lands in `TypedArtifactStore` as `subject="episodic"`,
    `family="experience"`."""
    mem_file = tmp_path / "session_memory.json"
    mgr = SessionMemoryManager(memory_file=mem_file)

    with patch(
        "rush.safety.redactor.sanitize_value", side_effect=real_sanitize_value
    ) as spy:
        mgr.record_turn(
            tool_name="lint", findings=1, fixes=0, summary="Fixed an unused import"
        )

    assert spy.called

    store = TypedArtifactStore(tmp_path)
    with sqlite3.connect(str(store.db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM memory_artifacts WHERE subject = 'episodic' AND family = 'experience'"
        ).fetchall()

    assert len(rows) == 1
    assert rows[0]["origin_kind"] == "session_memory"
