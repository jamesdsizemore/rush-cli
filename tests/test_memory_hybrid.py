"""MC12 §6.7 configured embeddings and deterministic hybrid ranking (docs/phase-plans/MC12.md)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Sequence
from pathlib import Path

import pytest

from rush.memory.embeddings import (
    EmbeddingConfig,
    EmbeddingResponseError,
    validate_embedding_response,
)
from rush.memory.retrieval import embedding_text, hybrid_candidates, hybrid_page
from rush.memory.store import MemoryArtifact, TypedArtifactStore
from rush.permissions import ExecutionPermissions
from rush.tools.memory import MemoryTool

_CONFIG_V1 = EmbeddingConfig(
    endpoint="http://fake-embed.invalid", model="fake-model", model_digest="digest-v1"
)


def _write(
    store: TypedArtifactStore, artifact_id: str, content: dict[str, object], source: str
) -> MemoryArtifact:
    return store.write(
        MemoryArtifact(
            id=artifact_id,
            family="memory",
            subject="domain_knowledge",
            trust_tier="IMPORTED",
            content=content,
            source=source,
            created_at=1.0,
        )
    )


def _content_hash(content: dict[str, object]) -> str:
    return hashlib.sha256(embedding_text(content).encode("utf-8")).hexdigest()


def _fixed_vector_adapter(vectors: dict[str, list[float]], calls: list[list[str]]):
    def _embed(config: EmbeddingConfig, chunks: Sequence[str]) -> list[list[float]]:
        calls.append(list(chunks))
        return [vectors[chunk] for chunk in chunks]

    return _embed


def test_hybrid_retrieves_lexical_paraphrase_miss(tmp_path: Path) -> None:
    store = TypedArtifactStore(tmp_path)
    a1_content = {"text": "a totally unrelated paraphrase"}
    _write(store, "A1", a1_content, "allowed")

    # "gizmo" shares zero terms with A1's text: a plain lexical query returns nothing.
    lexical_rows = store.search_candidates(
        "domain_knowledge", "gizmo", source_allowlist=["allowed"]
    )
    assert lexical_rows == []

    vectors = {"gizmo": [1.0, 0.0], embedding_text(a1_content): [1.0, 0.0]}
    calls: list[list[str]] = []
    page = hybrid_page(
        store,
        subject="domain_knowledge",
        query="gizmo",
        session_allowlist=["allowed"],
        embed_config=_CONFIG_V1,
        embed_fn=_fixed_vector_adapter(vectors, calls),
    )

    assert page["code"] == "OK"
    assert page["retrieval"] == "hybrid"
    assert {item["id"] for item in page["items"]} == {"A1"}


def test_rrf_order_is_deterministic(tmp_path: Path) -> None:
    store = TypedArtifactStore(tmp_path)
    a2_content = {"text": "widget widget widget"}
    a1_content = {"text": "widget"}
    d1_content = {"text": "denied widget content"}
    _write(store, "A2", a2_content, "allowed")
    _write(store, "A1", a1_content, "allowed")
    _write(store, "D1", d1_content, "denied")

    # Lexical order is A2 (higher term frequency) then A1; vector order is A1 (cosine 1.0
    # with the query) then A2 (cosine 0.0) -- symmetric ranks yield equal RRF scores and the
    # ID-ascending tie-break puts A1 first.
    vectors = {
        "widget": [1.0, 0.0],
        embedding_text(a1_content): [1.0, 0.0],
        embedding_text(a2_content): [0.0, 1.0],
    }
    calls: list[list[str]] = []
    fused_first = hybrid_candidates(
        store,
        subject="domain_knowledge",
        query="widget",
        session_allowlist=["allowed"],
        embed_config=_CONFIG_V1,
        embed_fn=_fixed_vector_adapter(vectors, calls),
    )
    fused_second = hybrid_candidates(
        store,
        subject="domain_knowledge",
        query="widget",
        session_allowlist=["allowed"],
        embed_config=_CONFIG_V1,
        embed_fn=_fixed_vector_adapter(vectors, calls),
    )

    assert fused_first["available"] is True
    ids_first = [row["id"] for row in fused_first["rows"]]
    ids_second = [row["id"] for row in fused_second["rows"]]
    assert ids_first == ["A1", "A2"]
    assert ids_first == ids_second

    lexical_rank = {"A2": 1, "A1": 2}
    vector_rank = {"A1": 1, "A2": 2}
    score_a1 = 1 / (60 + lexical_rank["A1"]) + 1 / (60 + vector_rank["A1"])
    score_a2 = 1 / (60 + lexical_rank["A2"]) + 1 / (60 + vector_rank["A2"])
    assert score_a1 == pytest.approx(score_a2)


def test_denied_source_never_sent_to_endpoint(tmp_path: Path) -> None:
    store = TypedArtifactStore(tmp_path)
    a1_content = {"text": "widget"}
    d1_content = {"text": "denied widget content"}
    _write(store, "A1", a1_content, "allowed")
    _write(store, "D1", d1_content, "denied")

    vectors = {"widget": [1.0, 0.0], embedding_text(a1_content): [1.0, 0.0]}
    calls: list[list[str]] = []
    fused = hybrid_candidates(
        store,
        subject="domain_knowledge",
        query="widget",
        session_allowlist=["allowed"],
        embed_config=_CONFIG_V1,
        embed_fn=_fixed_vector_adapter(vectors, calls),
    )

    assert fused["available"] is True
    assert [row["id"] for row in fused["rows"]] == ["A1"]
    sent_texts = [text for batch in calls for text in batch]
    assert embedding_text(d1_content) not in sent_texts
    assert "D1" not in {row["id"] for row in fused["rows"]}


def test_missing_engine_reports_lexical_fallback_explicitly(tmp_path: Path) -> None:
    store = TypedArtifactStore(tmp_path)
    _write(store, "A1", {"text": "findme"}, "allowed")

    page = hybrid_page(
        store,
        subject="domain_knowledge",
        query="findme",
        session_allowlist=["allowed"],
        embed_config=None,
    )

    assert page["code"] == "E_EMBEDDING_UNAVAILABLE"
    assert page["retrieval"] == "lexical"
    assert page["embedding_status"] == "skipped"
    assert page["hybrid_unavailable_reason"] == "no embedding engine configured"
    assert {item["id"] for item in page["items"]} == {"A1"}

    tool = MemoryTool()
    result = tool.run(
        tmp_path,
        operation="recall",
        subject="domain_knowledge",
        query="findme",
        session_allowlist=["allowed"],
        permissions=ExecutionPermissions(network=True),
        request={"view": "compact", "retrieval": "hybrid"},
    )
    assert result["status"] == "warn"
    assert result["raw"]["code"] == "E_EMBEDDING_UNAVAILABLE"
    assert result["raw"]["data"]["retrieval"] == "lexical"
    assert result["raw"]["data"]["embedding_status"] == "skipped"
    assert (
        result["raw"]["data"]["hybrid_unavailable_reason"]
        == "no embedding engine configured"
    )


def test_candidate_truncation_reported_when_scan_cap_hit(tmp_path: Path) -> None:
    store = TypedArtifactStore(tmp_path)
    a1_content = {"text": "widget one"}
    a2_content = {"text": "widget two"}
    _write(store, "A1", a1_content, "allowed")
    _write(store, "A2", a2_content, "allowed")

    vectors = {
        "widget": [1.0, 0.0],
        embedding_text(a1_content): [1.0, 0.0],
        embedding_text(a2_content): [0.0, 1.0],
    }
    calls: list[list[str]] = []

    under_cap = hybrid_candidates(
        store,
        subject="domain_knowledge",
        query="widget",
        session_allowlist=["allowed"],
        embed_config=_CONFIG_V1,
        embed_fn=_fixed_vector_adapter(vectors, calls),
    )
    assert under_cap["candidates_truncated"] is False

    # §6.7 "bound vector candidates to 512 and report candidate truncation": a `scan_limit`
    # smaller than the real candidate count means unseen rows exist beyond the cap.
    truncated = hybrid_candidates(
        store,
        subject="domain_knowledge",
        query="widget",
        session_allowlist=["allowed"],
        embed_config=_CONFIG_V1,
        embed_fn=_fixed_vector_adapter(vectors, calls),
        scan_limit=1,
    )
    assert truncated["candidates_truncated"] is True
    assert len(truncated["rows"]) == 1

    page = hybrid_page(
        store,
        subject="domain_knowledge",
        query="widget",
        session_allowlist=["allowed"],
        embed_config=_CONFIG_V1,
        embed_fn=_fixed_vector_adapter(vectors, calls),
    )
    assert page["candidates_truncated"] is False


def test_model_digest_change_invalidates_vectors(tmp_path: Path) -> None:
    store = TypedArtifactStore(tmp_path)
    content = {"text": "findme"}
    _write(store, "A1", content, "allowed")
    v1_hash = _content_hash(content)

    vectors = {"findme": [1.0, 0.0], embedding_text(content): [1.0, 0.0]}
    calls: list[list[str]] = []
    hybrid_candidates(
        store,
        subject="domain_knowledge",
        query="findme",
        session_allowlist=["allowed"],
        embed_config=_CONFIG_V1,
        cache_write=True,
        embed_fn=_fixed_vector_adapter(vectors, calls),
    )
    assert len(calls) == 2  # one candidate batch, one query embedding
    assert store.get_embedding(
        artifact_id="A1",
        artifact_version=1,
        content_hash=v1_hash,
        model_digest="digest-v1",
        chunking_version="mc12-v1",
    ) == [1.0, 0.0]

    # Same digest, same content: the candidate vector is cached, only the query is re-embedded.
    hybrid_candidates(
        store,
        subject="domain_knowledge",
        query="findme",
        session_allowlist=["allowed"],
        embed_config=_CONFIG_V1,
        cache_write=True,
        embed_fn=_fixed_vector_adapter(vectors, calls),
    )
    assert len(calls) == 3

    # Changed model digest: the digest-v1 vector is not reused; a new one is embedded and
    # cached under digest-v2 while the digest-v1 row is left untouched.
    config_v2 = EmbeddingConfig(
        endpoint="http://fake-embed.invalid",
        model="fake-model",
        model_digest="digest-v2",
    )
    hybrid_candidates(
        store,
        subject="domain_knowledge",
        query="findme",
        session_allowlist=["allowed"],
        embed_config=config_v2,
        cache_write=True,
        embed_fn=_fixed_vector_adapter(vectors, calls),
    )
    assert len(calls) == 5  # candidate batch + query, again
    assert store.get_embedding(
        artifact_id="A1",
        artifact_version=1,
        content_hash=v1_hash,
        model_digest="digest-v1",
        chunking_version="mc12-v1",
    ) == [1.0, 0.0]
    assert store.get_embedding(
        artifact_id="A1",
        artifact_version=1,
        content_hash=v1_hash,
        model_digest="digest-v2",
        chunking_version="mc12-v1",
    ) == [1.0, 0.0]

    # Changed content (same id/version, direct SQL update mirrors existing test convention
    # for raw-row setup): the digest-v1 vector keyed by the old content hash is untouched,
    # but the new content hash has never been embedded and must be recomputed.
    new_content = {"text": "different content now"}
    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            "UPDATE memory_artifacts SET content = ? WHERE id = 'A1'",
            (json.dumps(new_content),),
        )
        conn.commit()
    new_hash = _content_hash(new_content)
    assert store.get_embedding(
        artifact_id="A1",
        artifact_version=1,
        content_hash=v1_hash,
        model_digest="digest-v1",
        chunking_version="mc12-v1",
    ) == [1.0, 0.0]
    assert (
        store.get_embedding(
            artifact_id="A1",
            artifact_version=1,
            content_hash=new_hash,
            model_digest="digest-v1",
            chunking_version="mc12-v1",
        )
        is None
    )
    vectors[embedding_text(new_content)] = [0.0, 1.0]
    hybrid_candidates(
        store,
        subject="domain_knowledge",
        query="findme",
        session_allowlist=["allowed"],
        embed_config=_CONFIG_V1,
        cache_write=True,
        embed_fn=_fixed_vector_adapter(vectors, calls),
    )
    assert (
        len(calls) == 7
    )  # content changed under digest-v1: candidate batch + query, again
    assert store.get_embedding(
        artifact_id="A1",
        artifact_version=1,
        content_hash=new_hash,
        model_digest="digest-v1",
        chunking_version="mc12-v1",
    ) == [0.0, 1.0]


def test_nonfinite_wrong_dimension_or_truncated_embedding_rejected() -> None:
    truncated = b'{"embeddings": [[1.0, 2.0]'
    with pytest.raises(EmbeddingResponseError):
        validate_embedding_response(truncated, expected_count=1)

    wrong_count = json.dumps({"embeddings": [[1.0, 0.0], [1.0, 0.0]]}).encode()
    with pytest.raises(EmbeddingResponseError):
        validate_embedding_response(wrong_count, expected_count=1)

    inconsistent_dimension = json.dumps(
        {"embeddings": [[1.0, 0.0], [1.0, 0.0, 0.0]]}
    ).encode()
    with pytest.raises(EmbeddingResponseError):
        validate_embedding_response(inconsistent_dimension, expected_count=2)

    wrong_expected_dimension = json.dumps({"embeddings": [[1.0, 0.0, 0.0]]}).encode()
    with pytest.raises(EmbeddingResponseError):
        validate_embedding_response(
            wrong_expected_dimension, expected_count=1, expected_dimension=2
        )

    non_finite = json.dumps({"embeddings": [[1.0, float("nan")]]}).encode()
    with pytest.raises(EmbeddingResponseError):
        validate_embedding_response(non_finite, expected_count=1)

    zero_norm = json.dumps({"embeddings": [[0.0, 0.0]]}).encode()
    with pytest.raises(EmbeddingResponseError):
        validate_embedding_response(zero_norm, expected_count=1)


def test_read_only_hybrid_never_persists_vectors(tmp_path: Path) -> None:
    store = TypedArtifactStore(tmp_path)
    content = {"text": "findme"}
    _write(store, "A1", content, "allowed")

    vectors = {"findme": [1.0, 0.0], embedding_text(content): [1.0, 0.0]}
    calls: list[list[str]] = []
    fused = hybrid_candidates(
        store,
        subject="domain_knowledge",
        query="findme",
        session_allowlist=["allowed"],
        embed_config=_CONFIG_V1,
        cache_write=False,
        embed_fn=_fixed_vector_adapter(vectors, calls),
    )

    assert fused["available"] is True
    assert [row["id"] for row in fused["rows"]] == ["A1"]
    assert (
        store.get_embedding(
            artifact_id="A1",
            artifact_version=1,
            content_hash=_content_hash(content),
            model_digest="digest-v1",
            chunking_version="mc12-v1",
        )
        is None
    )
    with sqlite3.connect(store.db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM memory_embeddings").fetchone()[0]
    assert count == 0
