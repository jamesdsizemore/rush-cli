"""Contract tests T-61.24, T-61.25 for the Active-Context / Handoff family (Phase 61 §9 P61.4)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import rush.hook.tamper_detector  # noqa: F401 -- import first, breaks a pre-existing circular

# import (memory.store -> hook -> tools -> continuity -> memory.checkpoint_journal ->
# memory.migration -> memory.store) that otherwise fires when `rush.continuity.receipts` is the
# first module of this cycle touched in the process.
from rush.continuity.receipts import restore_receipt, save_receipt
from rush.memory.checkpoint_journal import CheckpointJournal
from rush.memory.store import TypedArtifactStore


def test_receipts_save_restore_now_backed_by_unified_store(tmp_path: Path) -> None:
    """T-61.24: `save_receipt`/`restore_receipt` keep their unchanged public signatures; the
    handoff data they build/read round-trips through `checkpoint_journal.py`'s `TypedArtifactStore`
    compatibility view (a `family="handoff"` row) instead of the old CAS-JSON path."""
    handoff = {
        "current_goal": "ship phase61",
        "open_work": ["T006"],
        "dependencies": [],
    }
    receipt = save_receipt(tmp_path, handoff)

    journal = CheckpointJournal(tmp_path)
    journal.save_checkpoint("session-x", {"handoff": receipt}, ["src/rush/foo.py"])

    store = TypedArtifactStore(tmp_path)
    with sqlite3.connect(str(store.db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM memory_artifacts WHERE family = 'handoff' AND subject = 'active_context'"
        ).fetchall()
    assert len(rows) == 1
    content = json.loads(rows[0]["content"])
    assert content["metadata"]["handoff"]["current_goal"] == "ship phase61"

    restored_checkpoint = journal.restore_checkpoint("session-x")
    assert restored_checkpoint is not None
    restored_receipt = restore_receipt(tmp_path, restored_checkpoint)
    assert restored_receipt["current_goal"] == "ship phase61"
    assert restored_receipt["freshness"] == "current"


def test_quarantine_flag_replaced_by_trust_tier(tmp_path: Path) -> None:
    """T-61.25: `receipts.py` no longer emits the binary
    `"authority": "historical_evidence", "state": "quarantined"` shape for `historic_instruction`
    — it emits a `trust_tier` field instead."""
    handoff = {
        "current_goal": "ship phase61",
        "open_work": [],
        "historic_instruction": "inherited instruction text",
        "dependencies": [],
    }
    receipt = save_receipt(tmp_path, handoff)

    historic_instruction = receipt["historic_instruction"]
    assert "trust_tier" in historic_instruction
    assert historic_instruction["trust_tier"] != "STATED"
    assert "authority" not in historic_instruction
    assert "state" not in historic_instruction
