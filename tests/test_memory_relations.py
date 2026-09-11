"""MC03 §6.3 evidence edges: versioned links, cycle prevention and bounded authorized
traversal (docs/phase-plans/MC03.md)."""

from __future__ import annotations

import json
import sqlite3
from itertools import pairwise
from pathlib import Path

from rush.memory.relations import add_relation, related_artifacts
from rush.memory.store import MemoryArtifact, TypedArtifactStore


def _write(
    store: TypedArtifactStore, artifact_id: str, text: str, source: str = "allowed"
) -> MemoryArtifact:
    return store.write(
        MemoryArtifact(
            id=artifact_id,
            family="memory",
            subject="domain_knowledge",
            trust_tier="IMPORTED",
            content={"text": text},
            source=source,
            created_at=1.0,
        )
    )


def _relation_count(store: TypedArtifactStore) -> int:
    with sqlite3.connect(store.db_path) as conn:
        return conn.execute("SELECT COUNT(*) FROM memory_relations").fetchone()[0]


def test_supersedes_cycle_rejected_atomically(tmp_path: Path) -> None:
    store = TypedArtifactStore(tmp_path)
    _write(store, "a1", "current advice")
    _write(store, "a2", "old advice")

    forward = add_relation(
        store,
        source_id="a1",
        source_version=1,
        target_id="a2",
        target_version=1,
        kind="supersedes",
    )
    assert forward["code"] == "OK"
    assert _relation_count(store) == 1

    inverse = add_relation(
        store,
        source_id="a2",
        source_version=1,
        target_id="a1",
        target_version=1,
        kind="supersedes",
    )
    assert inverse["code"] == "E_INPUT"
    # Rejected atomically: no partial/extra row from the failed inverse attempt.
    assert _relation_count(store) == 1

    unsupported = add_relation(
        store,
        source_id="a1",
        source_version=1,
        target_id="a2",
        target_version=1,
        kind="not_a_real_kind",
    )
    assert unsupported["code"] == "E_INPUT"
    assert _relation_count(store) == 1

    missing_endpoint = add_relation(
        store,
        source_id="a1",
        source_version=1,
        target_id="nope",
        target_version=1,
        kind="caused_by",
    )
    assert missing_endpoint["code"] == "E_INPUT"
    assert _relation_count(store) == 1


def test_related_hides_denied_neighbors(tmp_path: Path) -> None:
    store = TypedArtifactStore(tmp_path)
    _write(store, "a1", "seed")
    _write(store, "a2", "authorized neighbor")
    _write(store, "d1", "secret neighbor", source="denied")

    assert (
        add_relation(
            store,
            source_id="a1",
            source_version=1,
            target_id="a2",
            target_version=1,
            kind="depends_on",
        )["code"]
        == "OK"
    )
    assert (
        add_relation(
            store,
            source_id="a1",
            source_version=1,
            target_id="d1",
            target_version=1,
            kind="caused_by",
        )["code"]
        == "OK"
    )

    result = related_artifacts(
        store, artifact_id="a1", version=1, session_allowlist=["allowed"]
    )

    assert result["code"] == "OK"
    assert {item["id"] for item in result["items"]} == {"a2"}
    serialized = json.dumps(result, ensure_ascii=False)
    assert "d1" not in serialized
    assert "secret" not in serialized


def test_related_depth_node_and_token_caps(tmp_path: Path) -> None:
    store = TypedArtifactStore(tmp_path)
    chain = [f"c{i}" for i in range(5)]
    for node in chain:
        _write(store, node, f"node {node}")
    for left, right in pairwise(chain):
        assert (
            add_relation(
                store,
                source_id=left,
                source_version=1,
                target_id=right,
                target_version=1,
                kind="supersedes",
            )["code"]
            == "OK"
        )

    default_depth = related_artifacts(
        store, artifact_id="c0", version=1, session_allowlist=["allowed"]
    )
    assert {item["id"] for item in default_depth["items"]} == {"c1"}

    requested_beyond_cap = related_artifacts(
        store, artifact_id="c0", version=1, session_allowlist=["allowed"], depth=10
    )
    # Maximum depth 2: c1 (depth 1) and c2 (depth 2) only, never c3/c4.
    assert {item["id"] for item in requested_beyond_cap["items"]} == {"c1", "c2"}

    fanout_root = "root"
    _write(store, fanout_root, "fanout root")
    leaves = [f"leaf{i}" for i in range(40)]
    for leaf in leaves:
        _write(store, leaf, f"leaf {leaf}")
        assert (
            add_relation(
                store,
                source_id=fanout_root,
                source_version=1,
                target_id=leaf,
                target_version=1,
                kind="depends_on",
            )["code"]
            == "OK"
        )

    fanout_result = related_artifacts(
        store,
        artifact_id=fanout_root,
        version=1,
        session_allowlist=["allowed"],
        max_nodes=1000,
    )
    # Maximum 32 nodes regardless of a larger requested cap.
    assert len(fanout_result["items"]) <= 32
    assert fanout_result["complete"] is False

    tiny_budget = related_artifacts(
        store,
        artifact_id=fanout_root,
        version=1,
        session_allowlist=["allowed"],
        max_bytes=1,
    )
    assert tiny_budget["items"] == []
    assert tiny_budget["complete"] is False


def test_relation_version_change_invalidates_active_evidence(tmp_path: Path) -> None:
    store = TypedArtifactStore(tmp_path)
    _write(store, "a1", "seed")
    _write(store, "a2", "linked evidence")

    assert (
        add_relation(
            store,
            source_id="a1",
            source_version=1,
            target_id="a2",
            target_version=1,
            kind="fixed_by",
        )["code"]
        == "OK"
    )

    before = related_artifacts(
        store, artifact_id="a1", version=1, session_allowlist=["allowed"]
    )
    assert {item["id"] for item in before["items"]} == {"a2"}

    store.update_content("a2", {"text": "linked evidence, edited"}, expected_version=1)

    after = related_artifacts(
        store, artifact_id="a1", version=1, session_allowlist=["allowed"]
    )
    assert after["items"] == []
