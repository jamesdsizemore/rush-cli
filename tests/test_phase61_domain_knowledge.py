"""Contract test T-61.26 for the domain/project-knowledge family (Phase 61 §7/§9 P61.7)."""

from __future__ import annotations

import time
import uuid
from pathlib import Path

import rush.hook.tamper_detector  # noqa: F401 -- import first, breaks a pre-existing circular
from rush.memory.store import MemoryArtifact, TypedArtifactStore


def _artifact(**overrides) -> MemoryArtifact:
    defaults = {
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


def test_fts5_lexical_search_returns_ranked_results(tmp_path: Path):
    """search() scopes to subject and orders matches by FTS5's built-in BM25 rank."""
    store = TypedArtifactStore(project_root=tmp_path)

    id_low, id_high, id_nomatch = (
        str(uuid.uuid4()),
        str(uuid.uuid4()),
        str(uuid.uuid4()),
    )

    # Low relevance: single mention of the query term.
    store.write(_artifact(id=id_low, content={"note": "widget mentioned once here"}))
    # High relevance: repeated mentions of the query term -> higher BM25 score.
    store.write(
        _artifact(
            id=id_high,
            content={"note": "widget widget widget widget widget"},
        )
    )
    # No match at all: must not appear in results.
    store.write(_artifact(id=id_nomatch, content={"note": "unrelated gadget content"}))

    results = store.search("domain_knowledge", "widget")

    assert [r.id for r in results] == [id_high, id_low]
