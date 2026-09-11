from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from rush.memory.store import MemoryArtifact, TypedArtifactStore, VersionConflictError


def _legacy_db(root: Path) -> Path:
    db = root / ".rush" / "memory.db"
    db.parent.mkdir(parents=True)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE memory_artifacts (id TEXT PRIMARY KEY, family TEXT NOT NULL, "
            "subject TEXT NOT NULL, trust_tier TEXT NOT NULL, content TEXT NOT NULL, "
            "source TEXT NOT NULL, created_at REAL NOT NULL, symbol_ref TEXT, "
            "content_hash TEXT, corroboration_count INTEGER NOT NULL DEFAULT 0, "
            "promoted_at REAL, stale INTEGER NOT NULL DEFAULT 0, signature TEXT, "
            "origin_kind TEXT, origin_id TEXT, expires_at REAL, expired_at REAL, expired_by TEXT)"
        )
        conn.execute(
            "INSERT INTO memory_artifacts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "legacy-id",
                "memory",
                "preference",
                "IMPORTED",
                '{"value":"exact"}',
                "legacy-source",
                1.0,
                None,
                None,
                0,
                None,
                0,
                None,
                "preference",
                "theme",
                None,
                None,
                None,
            ),
        )
    return db


def test_legacy_migration_preserves_ids_origins_and_trust(tmp_path: Path) -> None:
    db = _legacy_db(tmp_path)

    TypedArtifactStore.upgrade(tmp_path, cache_write=True)

    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT id, origin_kind, origin_id, trust_tier, artifact_version "
            "FROM memory_artifacts"
        ).fetchone()
        version = conn.execute(
            "SELECT content, source, trust_tier FROM memory_artifact_versions"
        ).fetchone()
    assert row == ("legacy-id", "preference", "theme", "IMPORTED", 1)
    assert version == ('{"value":"exact"}', "legacy-source", "IMPORTED")


def test_read_only_open_creates_no_files(tmp_path: Path) -> None:
    root = tmp_path / "project ?#% space"
    root.mkdir()
    before = sorted(str(path.relative_to(root)) for path in root.rglob("*"))

    missing = TypedArtifactStore.open_readonly(root)

    assert missing.available is False
    assert sorted(str(path.relative_to(root)) for path in root.rglob("*")) == before

    db = _legacy_db(root)
    schema_before = db.read_bytes()
    journal_before = sorted(path.name for path in db.parent.iterdir())
    legacy = TypedArtifactStore.open_readonly(root)
    assert legacy.available is True
    assert legacy.migration_required is True
    assert db.read_bytes() == schema_before
    assert sorted(path.name for path in db.parent.iterdir()) == journal_before


def test_content_promotion_expiry_and_delete_advance_sequence(tmp_path: Path) -> None:
    store = TypedArtifactStore(tmp_path)
    artifact = store.write(
        MemoryArtifact(
            id="a1",
            family="memory",
            subject="preference",
            trust_tier="IMPORTED",
            content={"value": 1},
            source="test",
            created_at=1.0,
        )
    )
    assert artifact.artifact_version == 1
    store.update_content("a1", {"value": 2}, expected_version=1)
    promoted, decision = store.promote("a1", user_stated=True, expected_version=2)
    assert decision.promoted is True
    assert promoted.artifact_version == 3
    store.delete("a1", expected_version=3)

    with sqlite3.connect(store.db_path) as conn:
        versions = conn.execute(
            "SELECT artifact_version, deleted FROM memory_artifact_versions "
            "WHERE artifact_id='a1' ORDER BY artifact_version"
        ).fetchall()
        changes = conn.execute(
            "SELECT sequence, artifact_version, tombstone FROM memory_changes "
            "WHERE artifact_id='a1' ORDER BY sequence"
        ).fetchall()
    assert versions == [(1, 0), (2, 0), (3, 0), (4, 1)]
    assert [row[1:] for row in changes] == [(1, 0), (2, 0), (3, 0), (4, 1)]


def test_migration_failure_rolls_back(tmp_path: Path, monkeypatch) -> None:
    db = _legacy_db(tmp_path)
    original = db.read_bytes()

    def fail(*_args) -> None:
        raise RuntimeError("injected migration failure")

    monkeypatch.setattr(TypedArtifactStore, "_backfill_legacy_row", fail)
    with pytest.raises(RuntimeError, match="injected migration failure"):
        TypedArtifactStore.upgrade(tmp_path, cache_write=True)

    with sqlite3.connect(db) as conn:
        columns = [
            row[1] for row in conn.execute("PRAGMA table_info(memory_artifacts)")
        ]
        row = conn.execute("SELECT id, content FROM memory_artifacts").fetchone()
    assert "artifact_version" not in columns
    assert row == ("legacy-id", '{"value":"exact"}')
    assert db.read_bytes() == original


def test_concurrent_expected_version_rejects_lost_update(tmp_path: Path) -> None:
    first = TypedArtifactStore(tmp_path)
    first.write(
        MemoryArtifact(
            id="a1",
            family="memory",
            subject="preference",
            trust_tier="IMPORTED",
            content={"value": 1},
            source="test",
            created_at=1.0,
        )
    )
    second = TypedArtifactStore(tmp_path)
    first.update_content("a1", {"value": 2}, expected_version=1)

    with pytest.raises(VersionConflictError) as caught:
        second.update_content("a1", {"value": 3}, expected_version=1)

    assert caught.value.code == "E_VERSION"
    with sqlite3.connect(first.db_path) as conn:
        current = conn.execute(
            "SELECT content, artifact_version FROM memory_artifacts WHERE id='a1'"
        ).fetchone()
        change_count = conn.execute("SELECT COUNT(*) FROM memory_changes").fetchone()[0]
    assert current == ('{"value": 2}', 2)
    assert change_count == 2
