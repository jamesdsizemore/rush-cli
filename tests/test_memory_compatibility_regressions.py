"""Behavioral regressions for migrated legacy memory APIs."""

import json
from xml.etree import ElementTree

import pytest

from rush.continuity.receipts import last_handoff_for_provider, save_receipt
from rush.memory.checkpoint_journal import CheckpointJournal
from rush.memory.migration import (
    migrate_checkpoint_journal,
    migrate_preference_store,
    migrate_session_memory,
    read_origin_kind,
)
from rush.memory.preference_store import PreferenceStore
from rush.memory.store import TypedArtifactStore
from rush.session_memory import SessionMemoryManager


def test_default_session_uses_canonical_store(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    manager = SessionMemoryManager()
    manager.record_turn("lint", 2, 1, "canonical turn")
    assert len(read_origin_kind(tmp_path, "session_memory")) == 1
    assert not (tmp_path / ".rush" / ".rush" / "memory.db").exists()
    assert migrate_session_memory(tmp_path) == 0
    assert "canonical turn" in manager.format_for_mcp()


def test_custom_session_file_stays_isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    isolated = tmp_path / "isolated"
    manager = SessionMemoryManager(isolated / "history.json")
    manager.record_turn("lint", 0, 0, "isolated turn")
    assert len(read_origin_kind(isolated, "session_memory")) == 1
    assert not (tmp_path / ".rush" / "memory.db").exists()


def test_session_xml_keeps_latest_bounded_history(tmp_path):
    manager = SessionMemoryManager(tmp_path / "history.json", max_records=2)
    for number in range(4):
        manager.record_turn("lint", number, 0, f"turn {number}")
    records = ElementTree.fromstring(manager.format_for_mcp())
    assert [record.text for record in records] == ["turn 2", "turn 3"]
    assert len(read_origin_kind(tmp_path, "session_memory")) == 4


@pytest.mark.parametrize("override", [False, True])
def test_delete_migrated_preference_never_resurrects(tmp_path, override):
    preferences = PreferenceStore(tmp_path)
    preferences.set("editor", "old")
    assert migrate_preference_store(tmp_path) == 1
    if override:
        preferences.set("editor", "new")
    assert preferences.delete("editor") is True
    assert preferences.get("editor", "missing") == "missing"
    assert preferences.list_all() == {}
    assert preferences.delete("editor") is False
    assert migrate_preference_store(tmp_path) == 0
    assert PreferenceStore(tmp_path).get("editor", "missing") == "missing"
    preferences.set("editor", "fresh")
    assert preferences.list_all() == {"editor": "fresh"}
    assert migrate_preference_store(tmp_path) == 0
    assert PreferenceStore(tmp_path).get("editor") == "fresh"
    assert preferences.delete("editor") is True
    assert preferences.list_all() == {}


def test_migrated_checkpoints_preserve_listing_corruption_and_physical_precedence(
    tmp_path,
):
    journal = CheckpointJournal(tmp_path)
    for name, timestamp in [("older", 10), ("newer", 20)]:
        (journal.session_dir / f"{name}.json").write_text(
            json.dumps({"name": name, "created_at": timestamp, "metadata": {}})
        )
    broken = journal.session_dir / "broken.json"
    broken.write_bytes(b"not json")
    before = journal.list_checkpoints()
    assert migrate_checkpoint_journal(tmp_path) == 3
    assert journal.list_checkpoints() == before
    assert journal.restore_checkpoint("newer")["created_at"] == 20
    assert journal.restore_checkpoint("broken") is None
    (journal.session_dir / "newer.json").write_text(
        json.dumps({"name": "newer", "created_at": 30, "metadata": {"new": True}})
    )
    after = journal.list_checkpoints()
    assert len(after) == 3
    assert [entry["name"] for entry in after if entry["status"] == "ok"] == [
        "newer",
        "older",
    ]
    assert next(entry for entry in after if entry["name"] == "newer")["metadata"] == {
        "new": True
    }
    assert migrate_checkpoint_journal(tmp_path) == 1
    assert journal.list_checkpoints() == after
    assert journal.restore_checkpoint("newer")["metadata"] == {"new": True}
    assert migrate_checkpoint_journal(tmp_path) == 0


def test_migrated_handoff_retains_provider_diff_history(tmp_path):
    handoff = {"target_provider": "codex_cli", "current_goal": "fix memory"}
    receipt = save_receipt(tmp_path, handoff)
    CheckpointJournal(tmp_path).save_checkpoint("handoff", {"handoff": receipt}, [])
    assert migrate_checkpoint_journal(tmp_path) == 1
    assert last_handoff_for_provider(tmp_path, "codex_cli") == receipt
    assert save_receipt(tmp_path, handoff)["diff"] == {}


def test_checkpoint_listing_retains_non_scalar_legacy_id(tmp_path):
    journal = CheckpointJournal(tmp_path)
    data = {"checkpoint_id": ["legacy"], "name": "legacy", "status": "ok"}
    (journal.session_dir / "legacy.json").write_text(json.dumps(data))
    assert journal.list_checkpoints() == [data]


@pytest.mark.parametrize("operation", ["set", "delete"])
def test_mutating_promoted_preference_discards_old_approval(tmp_path, operation):
    preferences = PreferenceStore(tmp_path)
    preferences.set("editor", "old")
    migrate_preference_store(tmp_path)
    store = TypedArtifactStore(tmp_path)
    artifact = store.search("preference", "editor")[0]
    approved, decision = store.promote(artifact.id, user_stated=True)
    assert decision.promoted is True
    assert approved.signature is not None
    preferences.set("editor", "old")
    unchanged = store.recall("preference", "old", ["migration:preference_store"])[0]
    assert unchanged.trust_tier == "STATED"
    assert unchanged.signature == approved.signature
    if operation == "set":
        preferences.set("editor", "fresh")
        query = "fresh"
        expected = {"key": "editor", "value": "fresh"}
    else:
        assert preferences.delete("editor") is True
        query = "deleted"
        expected = {"deleted": True}
    recalled = store.recall("preference", query, ["migration:preference_store"])
    assert len(recalled) == 1
    updated = recalled[0]
    assert updated.content == expected
    assert updated.trust_tier == "EXTERNAL_WRITE"
    assert updated.signature is None
    assert updated.promoted_at is None
    assert updated.corroboration_count == 0


@pytest.mark.parametrize("old,new", [(1, True), (True, 1), (0, False), (False, 0)])
def test_preference_json_type_change_survives_remigration(tmp_path, old, new):
    preferences = PreferenceStore(tmp_path)
    preferences.set("setting", old)
    migrate_preference_store(tmp_path)
    store = TypedArtifactStore(tmp_path)
    artifact = store.search("preference", "setting")[0]
    store.promote(artifact.id, user_stated=True)

    preferences.set("setting", new)
    migrate_preference_store(tmp_path)

    assert type(preferences.get("setting")) is type(new)
    assert preferences.get("setting") == new
    updated = store.recall("preference", "setting", ["migration:preference_store"])[0]
    assert type(updated.content["value"]) is type(new)
    assert updated.trust_tier == "EXTERNAL_WRITE"
    assert updated.signature is None


def test_saved_checkpoint_remigration_preserves_latest_handoff(tmp_path):
    journal = CheckpointJournal(tmp_path)
    handoff = {"target_provider": "codex_cli", "current_goal": "old goal"}
    journal.save_checkpoint("same", {"handoff": save_receipt(tmp_path, handoff)}, [])
    assert migrate_checkpoint_journal(tmp_path) == 1
    handoff["current_goal"] = "new goal"
    receipt = save_receipt(tmp_path, handoff)
    journal.save_checkpoint("same", {"handoff": receipt}, ["new.py"])
    assert migrate_checkpoint_journal(tmp_path) == 1
    restored = journal.restore_checkpoint("same")
    assert restored["metadata"]["handoff"] == receipt
    assert restored["files"] == ["new.py"]
    assert journal.list_checkpoints() == [restored]
    assert last_handoff_for_provider(tmp_path, "codex_cli") == receipt
    assert save_receipt(tmp_path, handoff)["diff"] == {}
    assert migrate_checkpoint_journal(tmp_path) == 0
