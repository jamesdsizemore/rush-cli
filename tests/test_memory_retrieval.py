"""MC02 §9.0 bounded recall and exact expansion (docs/phase-plans/MC02.md)."""

from __future__ import annotations

import base64
import json
import sqlite3
from pathlib import Path

import tiktoken

from rush.memory.retrieval import expand_artifact, recall_page
from rush.memory.store import MemoryArtifact, TypedArtifactStore
from rush.permissions import ExecutionPermissions
from rush.tools.memory import MemoryTool


def _write(
    store: TypedArtifactStore, artifact_id: str, text: str, source: str
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


def _seed_bulk(
    store: TypedArtifactStore, ids: list[str], text_prefix: str, source: str
) -> None:
    """Raw-SQL bulk insert (bypasses `write()`'s per-row transaction) so the FTS candidate
    triggers still fire per row, but seeding hundreds of rows for a scan-cap test doesn't pay
    for 500+ separate connections/commits."""
    with sqlite3.connect(store.db_path) as conn:
        conn.executemany(
            "INSERT INTO memory_artifacts (id, family, subject, trust_tier, content, source, "
            "created_at, artifact_version) VALUES (?, 'memory', 'domain_knowledge', 'IMPORTED', "
            "?, ?, 1.0, 1)",
            [
                (
                    artifact_id,
                    json.dumps({"text": f"{text_prefix} {artifact_id}"}),
                    source,
                )
                for artifact_id in ids
            ],
        )
        conn.commit()


def _seed_corrupt(store: TypedArtifactStore, ids: list[str], source: str) -> None:
    """Rows whose `content` is not valid JSON — inserted directly, bypassing `write()`'s
    `json.dumps()` — to exercise the corrupt-candidate skip path."""
    with sqlite3.connect(store.db_path) as conn:
        conn.executemany(
            "INSERT INTO memory_artifacts (id, family, subject, trust_tier, content, source, "
            "created_at, artifact_version) VALUES (?, 'memory', 'domain_knowledge', 'IMPORTED', "
            "?, ?, 1.0, 1)",
            [
                (artifact_id, f"needle not json at all {artifact_id}", source)
                for artifact_id in ids
            ],
        )
        conn.commit()


def _measure(
    items: list[dict], next_cursor: str | None, complete: bool, encoding: str
) -> tuple[int, int]:
    payload = {
        "items": items,
        "next_cursor": next_cursor,
        "complete": complete,
        "encoding": encoding,
    }
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return len(text.encode("utf-8")), len(tiktoken.get_encoding(encoding).encode(text))


def test_authorized_result_survives_denied_rank_prefix(tmp_path: Path) -> None:
    store = TypedArtifactStore(tmp_path)
    _write(store, "d1", "needle secret ranked first", "denied")
    _write(store, "a1", "needle alpha", "allowed")
    _write(store, "a2", "needle beta", "allowed")

    page = recall_page(
        store, subject="domain_knowledge", query="needle", session_allowlist=["allowed"]
    )

    assert page["code"] == "OK"
    assert {item["id"] for item in page["items"]} == {"a1", "a2"}
    serialized = json.dumps(page, ensure_ascii=False)
    assert "d1" not in serialized
    assert "secret" not in serialized


def test_corrupt_candidates_do_not_starve_page(tmp_path: Path) -> None:
    store = TypedArtifactStore(tmp_path)
    _seed_corrupt(store, [f"corrupt{i:03d}" for i in range(70)], "allowed")
    _write(store, "a1", "needle alpha", "allowed")
    _write(store, "a2", "needle beta", "allowed")
    _write(store, "d1", "needle secret", "denied")

    page = recall_page(
        store, subject="domain_knowledge", query="needle", session_allowlist=["allowed"]
    )

    assert page["code"] == "OK"
    assert page["complete"] is True
    assert {item["id"] for item in page["items"]} == {"a1", "a2"}


def test_scan_cap_returns_continuation(tmp_path: Path) -> None:
    store = TypedArtifactStore(tmp_path)
    ids = [f"c{i:04d}" for i in range(513)]
    _seed_bulk(store, ids, "scanme cap", "allowed")

    page = recall_page(
        store,
        subject="domain_knowledge",
        query="scanme",
        session_allowlist=["allowed"],
        limit=10_000,
        max_tokens=1_000_000,
        max_bytes=1_000_000,
    )

    assert page["code"] == "OK"
    assert page["complete"] is False
    assert page["next_cursor"] is not None
    assert len(page["items"]) == 512

    next_page = recall_page(
        store,
        subject="domain_knowledge",
        query="scanme",
        session_allowlist=["allowed"],
        limit=10_000,
        max_tokens=1_000_000,
        max_bytes=1_000_000,
        cursor=page["next_cursor"],
    )
    assert next_page["code"] == "OK"
    assert next_page["complete"] is True
    assert len(next_page["items"]) == 1
    assert {item["id"] for item in page["items"]} | {
        item["id"] for item in next_page["items"]
    } == set(ids)


def test_serialized_payload_obeys_both_caps(tmp_path: Path) -> None:
    store = TypedArtifactStore(tmp_path)
    for i in range(20):
        _write(
            store,
            f"a{i:03d}",
            f"needle payload item number {i:03d} padding padding padding",
            "allowed",
        )

    page = recall_page(
        store,
        subject="domain_knowledge",
        query="needle",
        session_allowlist=["allowed"],
        limit=20,
        max_tokens=100,
        max_bytes=400,
    )

    assert page["code"] == "OK"
    assert len(page["items"]) < 20
    expected_bytes, expected_tokens = _measure(
        page["items"], page["next_cursor"], page["complete"], page["encoding"]
    )
    assert page["bytes"] == expected_bytes
    assert page["tokens"] == expected_tokens
    assert page["bytes"] <= 400
    assert page["tokens"] <= 100

    # Too-small envelope budget: not even an empty page fits -> E_BUDGET, no content.
    budget_page = recall_page(
        store,
        subject="domain_knowledge",
        query="needle",
        session_allowlist=["allowed"],
        max_bytes=1,
    )
    assert budget_page["code"] == "E_BUDGET"
    assert budget_page["items"] == []


def test_unicode_expansion_reconstructs_exact_original(tmp_path: Path) -> None:
    store = TypedArtifactStore(tmp_path)
    original_text = "café 中文 emoji 🙂 " * 40
    store.write(
        MemoryArtifact(
            id="u1",
            family="memory",
            subject="domain_knowledge",
            trust_tier="IMPORTED",
            content={"text": original_text},
            source="allowed",
            created_at=1.0,
        )
    )
    stored_bytes = store.get_version_content("u1", 1).encode("utf-8")

    chunks: list[bytes] = []
    offset = 0
    pages = 0
    while True:
        page = expand_artifact(
            store,
            artifact_id="u1",
            version=1,
            session_allowlist=["allowed"],
            offset=offset,
            max_bytes=100,
        )
        assert page["code"] == "OK"
        chunks.append(base64.b64decode(page["content_base64"]))
        pages += 1
        if page["complete"]:
            break
        offset = page["next_offset"]
        assert pages < 1000  # runaway-loop guard, never expected to trip

    assert pages > 1
    assert b"".join(chunks) == stored_bytes

    # Too-small envelope budget: E_BUDGET, no content leaked.
    tiny_budget = expand_artifact(
        store, artifact_id="u1", version=1, session_allowlist=["allowed"], max_bytes=1
    )
    assert tiny_budget["code"] == "E_BUDGET"
    assert tiny_budget["content_base64"] is None


def test_revoked_or_changed_version_cannot_expand(tmp_path: Path) -> None:
    store = TypedArtifactStore(tmp_path)
    _write(store, "a1", "needle alpha", "allowed")
    _write(store, "d1", "needle secret", "denied")

    stale = expand_artifact(
        store, artifact_id="a1", version=99, session_allowlist=["allowed"]
    )
    assert stale["code"] == "E_VERSION"
    assert stale["content_base64"] is None

    store.update_content("a1", {"text": "needle alpha updated"}, expected_version=1)
    now_stale = expand_artifact(
        store, artifact_id="a1", version=1, session_allowlist=["allowed"]
    )
    assert now_stale["code"] == "E_VERSION"
    assert now_stale["content_base64"] is None

    denied = expand_artifact(
        store, artifact_id="d1", version=1, session_allowlist=["allowed"]
    )
    assert denied["code"] == "E_NOT_VISIBLE"
    assert denied["content_base64"] is None

    missing = expand_artifact(
        store, artifact_id="nope", version=1, session_allowlist=["allowed"]
    )
    assert missing["code"] == "E_NOT_VISIBLE"
    assert missing["content_base64"] is None

    # Identical E_NOT_VISIBLE bodies for missing vs. denied (no distinguishing content).
    assert {k: v for k, v in denied.items() if k not in ("id",)} == {
        k: v for k, v in missing.items() if k not in ("id",)
    }


def test_cursor_rejects_scope_or_generation_change(tmp_path: Path) -> None:
    store = TypedArtifactStore(tmp_path)
    ids = [f"c{i:04d}" for i in range(513)]
    _seed_bulk(store, ids, "scanme cap", "allowed")

    page = recall_page(
        store,
        subject="domain_knowledge",
        query="scanme",
        session_allowlist=["allowed"],
        limit=10_000,
        max_tokens=1_000_000,
        max_bytes=1_000_000,
    )
    assert page["complete"] is False
    cursor = page["next_cursor"]
    assert cursor is not None

    scope_changed = recall_page(
        store,
        subject="domain_knowledge",
        query="scanme",
        session_allowlist=["other_source"],
        limit=10_000,
        max_tokens=1_000_000,
        max_bytes=1_000_000,
        cursor=cursor,
    )
    assert scope_changed["code"] == "E_RESTART"
    assert scope_changed["items"] == []

    tampered = recall_page(
        store,
        subject="domain_knowledge",
        query="scanme",
        session_allowlist=["allowed"],
        limit=10_000,
        max_tokens=1_000_000,
        max_bytes=1_000_000,
        cursor=cursor[:-1] + ("0" if cursor[-1] != "0" else "1"),
    )
    assert tampered["code"] == "E_RESTART"

    _write(store, "generation-bump", "scanme extra", "allowed")
    generation_changed = recall_page(
        store,
        subject="domain_knowledge",
        query="scanme",
        session_allowlist=["allowed"],
        limit=10_000,
        max_tokens=1_000_000,
        max_bytes=1_000_000,
        cursor=cursor,
    )
    assert generation_changed["code"] == "E_RESTART"


def test_legacy_memory_response_remains_compatible(tmp_path: Path) -> None:
    tool = MemoryTool()
    tool.run(
        tmp_path,
        operation="write",
        subject="domain_knowledge",
        content={"text": "needle alpha"},
        source="allowed",
        permissions=ExecutionPermissions(cache_write=True),
    )

    legacy = tool.run(
        tmp_path,
        operation="ask",
        subject="domain_knowledge",
        query="needle",
        session_allowlist=["allowed"],
    )
    assert legacy["status"] == "ok"
    assert isinstance(legacy["raw"], list)
    assert legacy["raw"][0]["id"]
    assert "schema_version" not in legacy
    assert not isinstance(legacy["raw"], dict)
    assert legacy["metadata"] == {"operation": "ask"}

    compact = tool.run(
        tmp_path,
        operation="ask",
        subject="domain_knowledge",
        query="needle",
        session_allowlist=["allowed"],
        request={"view": "compact"},
    )
    assert compact["raw"]["schema_version"] == 1
    assert compact["raw"]["operation"] == "ask"
    assert compact["raw"]["code"] == "OK"
    assert "items" in compact["raw"]["data"]
