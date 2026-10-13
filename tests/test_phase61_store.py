"""Contract tests T-61.01 through T-61.07 for the unified typed-artifact store (Phase 61 §6.1/§6.3)."""

from __future__ import annotations

import json
import os
import sqlite3
import stat
import time
import uuid
from pathlib import Path
from typing import Any

import pytest

import rush.hook  # noqa: F401 -- resolves pre-existing order-dependent circular import (T010 precedent)
from rush.memory.merkle_invalidator import MerkleInvalidator
from rush.memory.store import (
    MemoryAccessChanged,
    MemoryArtifact,
    SignatureMismatchError,
    TrojanSourceFoundError,
    TrustTierError,
    TypedArtifactStore,
    compute_content_signature,
    ensure_store_key,
)
from rush.setup.provision import default_data_root


def _artifact(**overrides) -> MemoryArtifact:
    defaults: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "family": "memory",
        "subject": "domain_knowledge",
        "trust_tier": "DERIVED",
        "content": {"note": "default content"},
        "source": "test",
        "created_at": time.time(),
    }
    defaults.update(overrides)
    return MemoryArtifact(**defaults)


def test_wal_mode_enabled_on_init(tmp_path: Path):
    store = TypedArtifactStore(project_root=tmp_path)
    conn = sqlite3.connect(str(store.db_path))
    mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
    conn.close()
    assert mode == "wal"


def test_write_rejects_stated_on_initial_insert(tmp_path: Path):
    store = TypedArtifactStore(project_root=tmp_path)
    artifact = _artifact(trust_tier="STATED")
    with pytest.raises(TrustTierError):
        store.write(artifact)


def test_write_redacts_content_before_persisting(tmp_path: Path):
    store = TypedArtifactStore(project_root=tmp_path)
    secret = "sk-ant-abcdefghijklmnopqrstuvwxyz012345"
    artifact = _artifact(content={"note": f"key is {secret}"})

    result = store.write(artifact)
    result_text = json.dumps(result.content)
    assert secret not in result_text
    assert "[REDACTED_ANTHROPIC_KEY]" in result_text

    conn = sqlite3.connect(str(store.db_path))
    row = conn.execute(
        "SELECT content FROM memory_artifacts WHERE id = ?", (artifact.id,)
    ).fetchone()
    conn.close()
    assert secret not in row[0]
    assert "[REDACTED_ANTHROPIC_KEY]" in row[0]


def _insert_stated_row(
    db_path: Path, artifact_id: str, content: dict, signature: str
) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO memory_artifacts "
        "(id, family, subject, trust_tier, content, source, created_at, promoted_at, signature) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (
            artifact_id,
            "memory",
            "domain_knowledge",
            "STATED",
            json.dumps(content),
            "test",
            time.time(),
            time.time(),
            signature,
        ),
    )
    conn.commit()
    conn.close()


def _bind_store(root: Path) -> None:
    """72-T01 D41: a raw-SQL fixture store is authoritative only after the approved
    binding (preview digest, then approve)."""
    preview = TypedArtifactStore.bind_store(root, approve=False)
    TypedArtifactStore.bind_store(
        root, approve=True, expected_binding_digest=preview["binding_digest"]
    )


def test_recall_rescans_stated_signature_and_raises_on_mismatch(tmp_path: Path):
    store = TypedArtifactStore(project_root=tmp_path)

    # (a) corrupted signature field, content unchanged -> mismatch on recompute.
    content_a = {"note": "alphapromoted stays same"}
    id_a = str(uuid.uuid4())
    _insert_stated_row(store.db_path, id_a, content_a, signature="0" * 64)
    _bind_store(tmp_path)
    with pytest.raises(SignatureMismatchError):
        store.recall("domain_knowledge", "alphapromoted", session_allowlist=["test"])

    # (b) correct signature at promotion time, content mutated afterward (bypassing write()).
    content_b = {"note": "bravopromoted original"}
    id_b = str(uuid.uuid4())
    correct_sig = compute_content_signature(content_b)
    _insert_stated_row(store.db_path, id_b, content_b, signature=correct_sig)

    conn = sqlite3.connect(str(store.db_path))
    conn.execute(
        "UPDATE memory_artifacts SET content = ? WHERE id = ?",
        (json.dumps({"note": "bravopromoted mutated"}), id_b),
    )
    conn.commit()
    conn.close()
    _bind_store(tmp_path)

    with pytest.raises(SignatureMismatchError):
        store.recall("domain_knowledge", "bravopromoted", session_allowlist=["test"])


def test_recall_scans_content_for_trojan_source_chars(tmp_path: Path):
    store = TypedArtifactStore(project_root=tmp_path)
    artifact = _artifact(content={"note": "trojanmarker \u202e reversed text"})
    store.write(artifact)

    with pytest.raises(TrojanSourceFoundError):
        store.recall("domain_knowledge", "trojanmarker", session_allowlist=["test"])


def test_staleness_flips_on_symbol_content_hash_mismatch(tmp_path: Path):
    store = TypedArtifactStore(project_root=tmp_path)
    target = tmp_path / "app.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")

    merkle = MerkleInvalidator(project_root=tmp_path)
    original_hash = merkle.hash_content(target.read_text(encoding="utf-8"))

    artifact = _artifact(
        content={"note": "stalecheck marker"},
        symbol_ref="app.py::VALUE",
        content_hash=original_hash,
    )
    store.write(artifact)

    fresh_results = store.recall(
        "domain_knowledge", "stalecheck", session_allowlist=["test"]
    )
    assert len(fresh_results) == 1
    assert fresh_results[0].stale is False

    target.write_text("VALUE = 2\n", encoding="utf-8")

    stale_results = store.recall(
        "domain_knowledge", "stalecheck", session_allowlist=["test"]
    )
    assert len(stale_results) == 1
    assert stale_results[0].stale is True


def test_recall_with_empty_allowlist_fails_closed(tmp_path: Path):
    store = TypedArtifactStore(project_root=tmp_path)
    store.write(
        _artifact(content={"note": "allowlistcheck marker"}, source="session-a")
    )

    # Absent allowlist: fails closed, never "allow all".
    assert store.recall("domain_knowledge", "allowlistcheck") == []
    # Explicit empty allowlist: same fail-closed result.
    assert (
        store.recall("domain_knowledge", "allowlistcheck", session_allowlist=[]) == []
    )


def test_recall_scopes_to_session_allowlist(tmp_path: Path):
    store = TypedArtifactStore(project_root=tmp_path)
    id_a, id_b = str(uuid.uuid4()), str(uuid.uuid4())
    store.write(
        _artifact(id=id_a, content={"note": "scopedmarker from A"}, source="session-a")
    )
    store.write(
        _artifact(id=id_b, content={"note": "scopedmarker from B"}, source="session-b")
    )

    results = store.recall(
        "domain_knowledge", "scopedmarker", session_allowlist=["session-a"]
    )
    assert {a.id for a in results} == {id_a}


def test_fts5_query_matches_indexed_content(tmp_path: Path):
    store = TypedArtifactStore(project_root=tmp_path)
    id1, id2, id3 = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())

    store.write(_artifact(id=id1, content={"note": "ftsalpha one"}))
    store.write(_artifact(id=id2, content={"note": "other two"}))
    store.write(_artifact(id=id3, content={"note": "ftsalpha three"}))

    matched = {a.id for a in store.search("domain_knowledge", "ftsalpha")}
    assert matched == {id1, id3}

    store.update_content(id1, {"note": "ftsbeta updated"})
    store.delete(id3)

    matched_after = {a.id for a in store.search("domain_knowledge", "ftsalpha")}
    assert matched_after == set()

    matched_beta = {a.id for a in store.search("domain_knowledge", "ftsbeta")}
    assert matched_beta == {id1}


def _embedding_count(store: TypedArtifactStore) -> int:
    with sqlite3.connect(store.db_path) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM memory_embeddings").fetchone()[0])


def test_put_embedding_commit_check_failure_persists_nothing(tmp_path: Path):
    """72-T01 brief §2.2: `put_embedding` takes keyword-only `commit_check`, called
    after the effect immediately before commit; a failure rolls back and raises
    `MemoryAccessChanged(code, reason)`. 72-T08 D39: the vector is only inserted for a
    current row, a source granted by `write_sources` and its embedding-text hash."""
    import hashlib

    from rush.memory.store import embedding_text

    store = TypedArtifactStore(project_root=tmp_path)
    content = {"note": "embed me"}
    store.write(_artifact(id="A1", content=content, source="test"))
    key: dict[str, Any] = {
        "artifact_id": "A1",
        "artifact_version": 1,
        "content_hash": hashlib.sha256(
            embedding_text(content).encode("utf-8")
        ).hexdigest(),
        "model_digest": "d",
        "chunking_version": "c",
    }
    with pytest.raises(MemoryAccessChanged) as exc:
        store.put_embedding(
            **key,
            vector=[1.0, 0.0],
            write_sources=["test"],
            commit_check=lambda: ("E_PERMISSION", "grant_revoked"),
        )
    assert (exc.value.code, exc.value.reason) == ("E_PERMISSION", "grant_revoked")
    assert store.get_embedding(**key) is None
    assert _embedding_count(store) == 0

    assert store.put_embedding(
        **key, vector=[1.0, 0.0], write_sources=["test"], commit_check=lambda: None
    )
    assert store.get_embedding(**key) == [1.0, 0.0]


@pytest.mark.posix_only
def test_store_key_creates_every_missing_parent_owner_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """72-T01 D41 (addendum: "POSIX uses 0o700 parents"): a fresh data root gets every
    missing parent of the key file created 0o700, not only the leaf directory."""
    home = tmp_path / "fresh-home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / "xdg"))
    key_dir = default_data_root() / "user" / ".rush"
    created: list[Path] = []
    probe = key_dir
    while not os.path.lexists(probe):
        created.append(probe)
        probe = probe.parent
    assert home in created and len(created) >= 3

    previous = os.umask(0o022)
    try:
        assert ensure_store_key() is not None
    finally:
        os.umask(previous)
    modes = {str(d): oct(stat.S_IMODE(d.stat().st_mode)) for d in created}
    assert modes == {str(d): oct(0o700) for d in created}
