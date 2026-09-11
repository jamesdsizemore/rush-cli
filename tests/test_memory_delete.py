"""P65-07.3 (plan §6.4): the public `memory delete` operation's transaction/outbox
batch-deletion algorithm. Preview is always allowed and never writes; apply requires
`cache_write`, replaces each row's stored bytes with a content-free tombstone version,
and refuses the *entire* batch atomically on a stale revision or a cross-scope member.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from rush.memory.store import MemoryArtifact, TypedArtifactStore
from rush.permissions import ExecutionPermissions
from rush.tools.memory import MemoryTool

_WRITE = ExecutionPermissions(cache_write=True)
_WRITE_AND_BLOB = ExecutionPermissions(cache_write=True, artifact_write=True)


def _seed(root: Path, *, source: str = "s1") -> dict[str, MemoryArtifact]:
    store = TypedArtifactStore(root)
    written: dict[str, MemoryArtifact] = {}
    for artifact_id, subject, body in (
        ("d1", "domain_knowledge", "keep or delete me"),
        ("d2", "domain_knowledge", "second candidate"),
        ("p1", "preference", "wrong scope for domain_knowledge deletes"),
    ):
        written[artifact_id] = store.write(
            MemoryArtifact(
                id=artifact_id,
                family="memory",
                subject=subject,
                trust_tier="DERIVED",
                content={"body": body},
                source=source,
                created_at=time.time(),
            )
        )
    return written


def _delete_request(
    artifact_ids: list[str],
    revisions: dict[str, int],
    *,
    scope: str = "domain_knowledge",
    apply: bool = False,
) -> dict:
    return {
        "artifact_ids": artifact_ids,
        "expected_revisions": revisions,
        "scope": scope,
        "apply": apply,
    }


def test_preview_never_writes(tmp_path: Path) -> None:
    _seed(tmp_path)
    result = MemoryTool().run(
        tmp_path,
        operation="delete",
        request=_delete_request(["d1"], {"d1": 1}, apply=False),
    )
    assert result["status"] == "ok"
    data = result["raw"]["data"]
    assert data["applied"] is False
    assert data["affected"][0]["id"] == "d1"
    assert data["affected"][0]["revision"] == 1

    store = TypedArtifactStore(tmp_path)
    current = store.get_current("d1")
    assert current is not None
    assert current.content == {"body": "keep or delete me"}


def test_apply_without_cache_write_is_denied_and_writes_nothing(tmp_path: Path) -> None:
    _seed(tmp_path)
    result = MemoryTool().run(
        tmp_path,
        operation="delete",
        request=_delete_request(["d1"], {"d1": 1}, apply=True),
    )
    assert result["raw"]["code"] == "E_PERMISSION"
    store = TypedArtifactStore(tmp_path)
    assert store.get_current("d1") is not None


def test_exact_authorized_batch_deletes_only_the_selected_records(
    tmp_path: Path,
) -> None:
    _seed(tmp_path)
    result = MemoryTool().run(
        tmp_path,
        operation="delete",
        request=_delete_request(["d1", "d2"], {"d1": 1, "d2": 1}, apply=True),
        permissions=_WRITE,
    )
    assert result["status"] == "ok"
    data = result["raw"]["data"]
    assert data["applied"] is True
    assert {item["id"] for item in data["affected"]} == {"d1", "d2"}

    store = TypedArtifactStore(tmp_path)
    assert store.get_current("d1") is None
    assert store.get_current("d2") is None
    # A record outside the requested batch is untouched.
    remaining = store.get_current("p1")
    assert remaining is not None
    assert remaining.content == {"body": "wrong scope for domain_knowledge deletes"}


def test_cross_scope_member_refuses_the_entire_batch(tmp_path: Path) -> None:
    _seed(tmp_path)
    result = MemoryTool().run(
        tmp_path,
        operation="delete",
        request=_delete_request(
            ["d1", "p1"], {"d1": 1, "p1": 1}, scope="domain_knowledge", apply=True
        ),
        permissions=_WRITE,
    )
    assert result["raw"]["code"] == "E_SCOPE"

    store = TypedArtifactStore(tmp_path)
    # Neither member was removed -- not even the one whose scope did match.
    assert store.get_current("d1") is not None
    assert store.get_current("p1") is not None


def test_stale_revision_refuses_the_entire_batch_atomically(tmp_path: Path) -> None:
    _seed(tmp_path)
    result = MemoryTool().run(
        tmp_path,
        operation="delete",
        # d1's real revision is 1; d2's declared revision (2) is stale.
        request=_delete_request(["d1", "d2"], {"d1": 1, "d2": 2}, apply=True),
        permissions=_WRITE,
    )
    assert result["raw"]["code"] == "E_VERSION"

    store = TypedArtifactStore(tmp_path)
    assert store.get_current("d1") is not None
    assert store.get_current("d2") is not None


def test_unavailable_expansion_after_deletion(tmp_path: Path) -> None:
    _seed(tmp_path)
    delete_result = MemoryTool().run(
        tmp_path,
        operation="delete",
        request=_delete_request(["d1"], {"d1": 1}, apply=True),
        permissions=_WRITE,
    )
    assert delete_result["raw"]["data"]["applied"] is True

    expand_result = MemoryTool().run(
        tmp_path,
        operation="expand",
        session_allowlist=["s1"],
        request={"id": "d1", "version": 1},
    )
    assert expand_result["raw"]["code"] == "E_NOT_VISIBLE"


def test_no_deleted_content_retained_in_active_memory_versions(tmp_path: Path) -> None:
    _seed(tmp_path)
    MemoryTool().run(
        tmp_path,
        operation="delete",
        request=_delete_request(["d1"], {"d1": 1}, apply=True),
        permissions=_WRITE,
    )

    db_path = tmp_path / ".rush" / "memory.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT content, deleted FROM memory_artifact_versions "
            "WHERE artifact_id = ? ORDER BY artifact_version",
            ("d1",),
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 2
    assert rows[0]["content"] != rows[1]["content"]
    tombstone_row = rows[-1]
    assert tombstone_row["deleted"] == 1
    assert tombstone_row["content"] == "{}"
    assert "keep or delete me" not in tombstone_row["content"]


def test_deleted_reference_stays_discoverable_with_provenance(tmp_path: Path) -> None:
    _seed(tmp_path)
    MemoryTool().run(
        tmp_path,
        operation="delete",
        request=_delete_request(["d1"], {"d1": 1}, apply=True),
        permissions=_WRITE,
    )

    store = TypedArtifactStore(tmp_path)
    deleted = store.list_deleted_refs()
    assert len(deleted) == 1
    assert deleted[0]["id"] == "d1"
    assert deleted[0]["subject"] == "domain_knowledge"
    assert deleted[0]["revision"] == 2  # tombstone advanced the version once more


def test_unknown_artifact_id_refuses_the_batch(tmp_path: Path) -> None:
    _seed(tmp_path)
    result = MemoryTool().run(
        tmp_path,
        operation="delete",
        request=_delete_request(["does-not-exist"], {"does-not-exist": 1}, apply=True),
        permissions=_WRITE,
    )
    assert result["raw"]["code"] == "E_INPUT"


def test_handoff_blob_requires_artifact_write_else_cleanup_pending(
    tmp_path: Path,
) -> None:
    root = tmp_path
    handoffs_dir = root / ".rush" / "handoffs"
    handoffs_dir.mkdir(parents=True)
    blob_path = handoffs_dir / "h1.json"
    blob_path.write_text("{}", encoding="utf-8")

    store = TypedArtifactStore(root)
    store.write(
        MemoryArtifact(
            id="scan-handoff-h1",
            family="handoff",
            subject="active_context",
            trust_tier="DERIVED",
            content={"run_id": "r1"},
            source=str(root),
            created_at=time.time(),
        )
    )

    result = MemoryTool().run(
        root,
        operation="delete",
        request=_delete_request(
            ["scan-handoff-h1"],
            {"scan-handoff-h1": 1},
            scope="active_context",
            apply=True,
        ),
        permissions=_WRITE,  # cache_write only, no artifact_write
    )
    assert result["raw"]["data"]["blob_cleanup"] == {
        "scan-handoff-h1": "cleanup_pending"
    }
    assert blob_path.exists()

    # Re-seed the same id/blob to prove artifact_write actually removes it.
    store.write(
        MemoryArtifact(
            id="scan-handoff-h2",
            family="handoff",
            subject="active_context",
            trust_tier="DERIVED",
            content={"run_id": "r1"},
            source=str(root),
            created_at=time.time(),
        )
    )
    blob_path_2 = handoffs_dir / "h2.json"
    blob_path_2.write_text("{}", encoding="utf-8")

    result2 = MemoryTool().run(
        root,
        operation="delete",
        request=_delete_request(
            ["scan-handoff-h2"],
            {"scan-handoff-h2": 1},
            scope="active_context",
            apply=True,
        ),
        permissions=_WRITE_AND_BLOB,
    )
    assert result2["raw"]["data"]["blob_cleanup"] == {"scan-handoff-h2": "removed"}
    assert not blob_path_2.exists()


def test_no_wildcard_and_no_external_file_paths(tmp_path: Path) -> None:
    _seed(tmp_path)
    result = MemoryTool().run(
        tmp_path,
        operation="delete",
        request=_delete_request(["../etc/passwd"], {"../etc/passwd": 1}, apply=False),
    )
    assert result["raw"]["code"] == "E_INPUT"


def test_batch_size_over_100_is_rejected(tmp_path: Path) -> None:
    _seed(tmp_path)
    ids = [f"id-{i}" for i in range(101)]
    result = MemoryTool().run(
        tmp_path,
        operation="delete",
        request=_delete_request(ids, dict.fromkeys(ids, 1), apply=False),
    )
    assert result["raw"]["code"] == "E_INPUT"
