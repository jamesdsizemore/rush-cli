"""Phase 62 P62.7 contract tests: per-type expiry policy and `sweep_expired()`.

Covers T-62.12, T-62.13, T-62.14, T-62.24, T-62.25 (phase-62-memory-integration-layer-plan.md §7).
TTL durations (DERIVED=14d, EXTERNAL_WRITE=30d, IMPORTED=90d) are §6.3's already-resolved,
rush-own rationale grounded in `src/rush/hotspots/time_decay.py:12`'s 90-day precedent — not
re-derived here.
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path

from rush.memory.expiry import sweep_expired
from rush.memory.merkle_invalidator import MerkleInvalidator
from rush.memory.store import MemoryArtifact, TypedArtifactStore

_DAY = 86400


def _artifact(**overrides) -> MemoryArtifact:
    defaults = dict(
        id=str(uuid.uuid4()),
        family="memory",
        subject="domain_knowledge",
        trust_tier="DERIVED",
        content={"note": "default content"},
        source="test",
        created_at=time.time(),
    )
    defaults.update(overrides)
    return MemoryArtifact(**defaults)


def _insert_stated_row(db_path: Path, artifact_id: str, created_at: float) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO memory_artifacts "
        "(id, family, subject, trust_tier, content, source, created_at, signature) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (
            artifact_id,
            "memory",
            "domain_knowledge",
            "STATED",
            '{"note": "stated marker"}',
            "test",
            created_at,
            "0" * 64,
        ),
    )
    conn.commit()
    conn.close()


def _expiry_columns(db_path: Path, artifact_id: str) -> sqlite3.Row:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT expires_at, expired_at, expired_by FROM memory_artifacts WHERE id = ?",
        (artifact_id,),
    ).fetchone()
    conn.close()
    return row


def test_stated_records_never_expire(tmp_path: Path) -> None:
    """T-62.12: a STATED record, TTL sweep run repeatedly; asserts never expired."""
    store = TypedArtifactStore(project_root=tmp_path)
    artifact_id = str(uuid.uuid4())
    _insert_stated_row(store.db_path, artifact_id, created_at=time.time() - 365 * _DAY)

    for _ in range(3):
        sweep_expired(store.project_root)

    row = _expiry_columns(store.db_path, artifact_id)
    assert row["expired_at"] is None
    assert row["expired_by"] is None


def test_derived_record_expires_after_configured_ttl(tmp_path: Path) -> None:
    """T-62.13: a DERIVED record older than its configured 14-day TTL (§6.3, resolved);
    asserts sweep_expired() stamps expired_at/expired_by once that TTL elapses."""
    store = TypedArtifactStore(project_root=tmp_path)
    artifact = _artifact(trust_tier="DERIVED", created_at=time.time() - 15 * _DAY)
    store.write(artifact)

    changed = sweep_expired(store.project_root)

    assert changed == 1
    row = _expiry_columns(store.db_path, artifact.id)
    assert row["expires_at"] is not None
    assert row["expired_at"] is not None
    assert row["expired_by"] == "expiry_sweep"


def test_external_write_record_expires_after_configured_ttl(tmp_path: Path) -> None:
    """T-62.24: an EXTERNAL_WRITE record older than its configured 30-day TTL (§6.3, resolved);
    asserts sweep_expired() stamps expired_at/expired_by once that TTL elapses."""
    store = TypedArtifactStore(project_root=tmp_path)
    artifact = _artifact(
        trust_tier="EXTERNAL_WRITE", created_at=time.time() - 31 * _DAY
    )
    store.write(artifact)

    changed = sweep_expired(store.project_root)

    assert changed == 1
    row = _expiry_columns(store.db_path, artifact.id)
    assert row["expired_at"] is not None
    assert row["expired_by"] == "expiry_sweep"


def test_imported_record_expires_after_configured_ttl(tmp_path: Path) -> None:
    """T-62.25: an IMPORTED record older than its configured 90-day TTL (§6.3, resolved);
    asserts sweep_expired() stamps expired_at/expired_by once that TTL elapses."""
    store = TypedArtifactStore(project_root=tmp_path)
    artifact = _artifact(trust_tier="IMPORTED", created_at=time.time() - 91 * _DAY)
    store.write(artifact)

    changed = sweep_expired(store.project_root)

    assert changed == 1
    row = _expiry_columns(store.db_path, artifact.id)
    assert row["expired_at"] is not None
    assert row["expired_by"] == "expiry_sweep"


def test_expiry_and_staleness_are_independent(tmp_path: Path) -> None:
    """T-62.14: a record that's stale-but-not-expired and one that's expired-but-not-stale;
    asserts both booleans independently correct (Invariant 6, §6.5)."""
    store = TypedArtifactStore(project_root=tmp_path)

    target = tmp_path / "app.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    original_hash = MerkleInvalidator(project_root=tmp_path).hash_content(
        target.read_text(encoding="utf-8")
    )

    stale_not_expired = _artifact(
        trust_tier="DERIVED",
        created_at=time.time(),
        symbol_ref="app.py::VALUE",
        content_hash=original_hash,
    )
    store.write(stale_not_expired)
    target.write_text("VALUE = 2\n", encoding="utf-8")  # drift -> flips stale on recall

    expired_not_stale = _artifact(
        trust_tier="DERIVED", created_at=time.time() - 15 * _DAY
    )
    store.write(expired_not_stale)

    sweep_expired(store.project_root)

    results = store.recall("domain_knowledge", "default", session_allowlist=["test"])
    by_id = {a.id: a for a in results}

    assert by_id[stale_not_expired.id].stale is True
    assert by_id[stale_not_expired.id].expired is False
    assert by_id[expired_not_stale.id].stale is False
    assert by_id[expired_not_stale.id].expired is True
