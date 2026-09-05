"""Contract tests for Phase 58: Checkpoint Journals and Corrupt Evidence (P58.4)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from rush.memory.checkpoint_journal import CheckpointJournal


def test_checkpoint_same_name_policy_and_replace_are_atomic(tmp_path: Path) -> None:
    """T-58.11: Overwriting/saving checkpoint with identical name replaces cleanly via AtomicFile.

    Asserts no partial files, torn reads, or orphaned temps occur during replacement.
    """
    journal = CheckpointJournal(tmp_path)
    sessions_dir = tmp_path / ".rush" / "sessions"

    # 1. Initial point-in-time checkpoint save
    dest1 = journal.save_checkpoint(
        "session-state",
        {"epoch": 1, "note": "initial snapshot"},
        ["src/main.py", "src/config.py"],
    )
    assert dest1.exists()
    assert dest1.is_file()

    # Verify initial content
    snap1 = journal.restore_checkpoint("session-state")
    assert snap1 is not None
    assert snap1.get("schema_version") == "1.0.0"
    assert snap1["metadata"]["epoch"] == 1
    assert snap1["metadata"]["note"] == "initial snapshot"
    assert snap1["files"] == ["src/main.py", "src/config.py"]

    # 2. Save with identical name replaces cleanly
    dest2 = journal.save_checkpoint(
        "session-state",
        {"epoch": 2, "note": "updated snapshot"},
        ["src/main.py", "src/auth.py", "src/new.py"],
    )
    assert dest2.resolve() == dest1.resolve()

    # Verify atomic replacement content
    snap2 = journal.restore_checkpoint("session-state")
    assert snap2 is not None
    assert snap2.get("schema_version") == "1.0.0"
    assert snap2["metadata"]["epoch"] == 2
    assert snap2["metadata"]["note"] == "updated snapshot"
    assert snap2["files"] == ["src/main.py", "src/auth.py", "src/new.py"]

    # 3. Assert zero orphaned temporary files remain in .rush/sessions
    temp_files = list(sessions_dir.glob(".rush_tmp_*"))
    assert len(temp_files) == 0, f"Orphaned temporary files found: {temp_files}"

    # Assert only the target json file exists in sessions_dir
    all_files = list(sessions_dir.glob("*"))
    assert len(all_files) == 1
    assert all_files[0].name == "session-state.json"


def test_corrupt_journal_bytes_are_retained_and_listed(tmp_path: Path) -> None:
    """T-58.12: Writes corrupt JSON bytes into checkpoint storage.

    Asserts list_checkpoints does not crash or silently ignore, but retains
    the file and lists it as a corrupt entry with status 'corrupt' and
    SHA-256 digest evidence.
    """
    journal = CheckpointJournal(tmp_path)
    sessions_dir = tmp_path / ".rush" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    # 1. Save a valid checkpoint
    journal.save_checkpoint(
        "valid_session",
        {"stage": "phase-58"},
        ["src/app.py"],
    )

    # 2. Inject corrupted unparseable bytes into storage
    corrupt_bytes = (
        b'{\n  "schema_version": "1.0.0",\n'
        b'  "truncated_data": [1, 2, 3,\n'
        b'  "unclosed_string": "oops\x80\xff\xfe\n'
    )
    corrupt_path = sessions_dir / "broken_corrupt_session.json"
    corrupt_path.write_bytes(corrupt_bytes)
    expected_digest = hashlib.sha256(corrupt_bytes).hexdigest()

    # 3. Call list_checkpoints: must NOT crash, must NOT silently ignore
    checkpoints = journal.list_checkpoints()
    assert len(checkpoints) == 2, (
        f"Expected 2 entries (1 valid + 1 corrupt), got {len(checkpoints)}"
    )

    # 4. Assert corrupt file is retained on disk (not deleted or truncated)
    assert corrupt_path.exists(), "Corrupt checkpoint file was deleted from disk"
    assert corrupt_path.read_bytes() == corrupt_bytes, "Corrupt file bytes were mutated"

    # 5. Assert corrupt entry properties and cryptographic evidence
    corrupt_entry = next(
        (c for c in checkpoints if c.get("checkpoint_id") == "broken_corrupt_session"),
        None,
    )
    assert corrupt_entry is not None, (
        "Corrupt entry missing from list_checkpoints results"
    )
    assert corrupt_entry.get("status") == "corrupt"
    assert corrupt_entry.get("raw_bytes_digest") == expected_digest
    assert len(corrupt_entry.get("raw_bytes_digest", "")) == 64
    assert corrupt_entry.get("error_message") is not None
    assert len(corrupt_entry["error_message"]) > 0

    # 6. Assert valid entry is also properly listed
    valid_entry = next(
        (
            c
            for c in checkpoints
            if c.get("checkpoint_id") == "valid_session"
            or c.get("name") == "valid_session"
        ),
        None,
    )
    assert valid_entry is not None
    assert valid_entry.get("status") == "ok"
    assert valid_entry["metadata"]["stage"] == "phase-58"
