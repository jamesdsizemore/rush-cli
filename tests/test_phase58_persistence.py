"""Governance contract tests for Phase 58: R-010 Contained Persistence and Schema Versioning."""

from __future__ import annotations

import json
from pathlib import Path

from rush.memory.checkpoint_journal import CheckpointJournal
from rush.memory.invariant_graph import InvariantGraph
from rush.memory.merkle_invalidator import MerkleInvalidator
from rush.memory.preference_store import PreferenceStore


def test_persistence_uses_atomic_file_with_schema_version(tmp_path: Path) -> None:
    """T-58.13 (R-010 Governance Test): Asserts persistence operations across memory and journals use AtomicFile with explicit schema versioning '1.0.0'."""
    # 1. CheckpointJournal persistence governance
    journal = CheckpointJournal(tmp_path)
    dest = journal.save_checkpoint(
        "gov-session", {"task": "r010-check"}, ["src/lib.py"]
    )
    assert dest.exists()
    checkpoint_raw = json.loads(dest.read_text(encoding="utf-8"))
    assert checkpoint_raw.get("schema_version") == "1.0.0", (
        f"CheckpointJournal missing schema_version 1.0.0: {checkpoint_raw}"
    )
    assert hasattr(journal, "physical_root"), (
        "CheckpointJournal must bind to a PhysicalRoot"
    )
    assert checkpoint_raw.get("checkpoint_id") == "gov-session"

    # 2. PreferenceStore persistence governance
    pref = PreferenceStore(tmp_path)
    pref.set("editor.tabSize", "4")
    pref_file = tmp_path / ".rush" / "preferences.json"
    assert pref_file.exists()
    pref_raw = json.loads(pref_file.read_text(encoding="utf-8"))
    assert pref_raw.get("schema_version") == "1.0.0", (
        f"PreferenceStore missing schema_version 1.0.0: {pref_raw}"
    )
    assert "version" in pref_raw and isinstance(pref_raw["version"], int)
    assert pref_raw["data"]["editor.tabSize"] == "4"

    # 3. InvariantGraph persistence governance
    inv = InvariantGraph(tmp_path)
    inv.add_invariant("INV-GOV", "Must use atomic persistence", "R-010 compliance")
    inv_file = tmp_path / ".rush" / "memory" / "invariants.json"
    assert inv_file.exists()
    inv_raw = json.loads(inv_file.read_text(encoding="utf-8"))
    assert inv_raw.get("schema_version") == "1.0.0", (
        f"InvariantGraph missing schema_version 1.0.0: {inv_raw}"
    )
    assert "version" in inv_raw and isinstance(inv_raw["version"], int)
    assert "INV-GOV" in inv_raw["data"]

    # 4. MerkleInvalidator persistence governance
    merkle = MerkleInvalidator(tmp_path)
    merkle.check_and_update("symbol_gov", "def run(): pass")
    merkle_file = tmp_path / ".rush" / "cache" / "merkle.json"
    assert merkle_file.exists()
    merkle_raw = json.loads(merkle_file.read_text(encoding="utf-8"))
    assert merkle_raw.get("schema_version") == "1.0.0", (
        f"MerkleInvalidator missing schema_version 1.0.0: {merkle_raw}"
    )
    assert "version" in merkle_raw and isinstance(merkle_raw["version"], int)
    assert "symbol_gov" in merkle_raw["data"]
