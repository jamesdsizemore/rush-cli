"""Contract tests for Phase 58: Checkpoint Journals and Corrupt Evidence (P58.4)."""

from __future__ import annotations

import hashlib
import json
import types
from pathlib import Path
from typing import Any

import pytest

from rush.memory import checkpoint_journal
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
    assert dest1 is not None
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
    assert dest2 is not None
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


# --- spec-tests-10: checkpoint readers honor the C01 `ask` route ------------

_CP_SOURCES = ("checkpoint_journal:save_checkpoint", "migration:checkpoint_journal")
_SECRET = "CHECKPOINT-SECRET"


def _revision(auth: Any, data_root: Path) -> int:
    return int(auth.load_policy_readonly(data_root=data_root)["policy_revision"] or 0)


def _policy_journal(
    tmp_path: Path, ops: tuple[str, ...]
) -> tuple[CheckpointJournal, Any]:
    """A registered policy-mode project granted `ops` on the checkpoint sources
    for the writer's owner, with checkpoint `cp1` saved (it holds `_SECRET`).
    Returns the journal and a zero-argument revoke of that grant."""
    from rush.memory import authorization as auth
    from rush.memory.store import legacy_owner_scope
    from rush.setup.provision import default_data_root
    from rush.workflows.projects import register_project

    data_root = default_data_root()
    root = tmp_path / "project"
    root.mkdir()
    register_project(root, data_root=data_root)
    root = root.resolve()
    grant = auth.grant_memory_scope(
        project_root=root,
        owner_scope=legacy_owner_scope(root),
        approved_sources=list(_CP_SOURCES),
        allowed_operations=list(ops),
        expected_policy_revision=_revision(auth, data_root),
        consent=True,
        data_root=data_root,
    )
    journal = CheckpointJournal(root)
    saved = journal.save_checkpoint("cp1", {"secret": _SECRET}, ["a.py"])
    assert saved is not None and saved.is_file()

    def revoke() -> None:
        auth.revoke_memory_scope(
            grant_id=grant["grant_id"],
            expected_policy_revision=_revision(auth, data_root),
            consent=True,
            data_root=data_root,
        )

    return journal, revoke


def test_checkpoint_readers_return_nothing_under_write_only_grant(
    tmp_path: Path,
) -> None:
    journal, _revoke = _policy_journal(tmp_path, ("write",))
    assert journal.restore_checkpoint("cp1") is None
    assert journal.list_checkpoints() == []


def test_checkpoint_readers_return_nothing_after_revocation(tmp_path: Path) -> None:
    journal, revoke = _policy_journal(tmp_path, ("ask", "write"))
    restored = journal.restore_checkpoint("cp1")
    assert restored is not None and restored["metadata"] == {"secret": _SECRET}
    assert [c["checkpoint_id"] for c in journal.list_checkpoints()] == ["cp1"]

    revoke()
    assert journal.restore_checkpoint("cp1") is None
    assert journal.list_checkpoints() == []


@pytest.mark.parametrize("reader", ["restore", "list"])
def test_checkpoint_readers_recheck_after_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reader: str
) -> None:
    """The grant is revoked after the reader passed its route and selected the
    checkpoint file (inside its JSON parse): nothing is returned."""
    journal, revoke = _policy_journal(tmp_path, ("ask", "write"))
    revoked: list[bool] = []

    def loads(text: str) -> Any:
        if not revoked:
            revoked.append(True)
            revoke()
        return json.loads(text)

    monkeypatch.setattr(
        checkpoint_journal,
        "json",
        types.SimpleNamespace(loads=loads, JSONDecodeError=json.JSONDecodeError),
    )
    if reader == "restore":
        out: Any = journal.restore_checkpoint("cp1")
        assert out is None
    else:
        out = journal.list_checkpoints()
        assert out == []
    assert revoked == [True]
    assert _SECRET not in repr(out)
