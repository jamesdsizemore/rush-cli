from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from rush.memory.store import (
    MemoryArtifact,
    MemoryMigrationRequiredError,
    MemoryScopeError,
    OwnerScope,
    OwnerScopeError,
    TypedArtifactStore,
    VersionConflictError,
    legacy_owner_scope,
    owner_scope_for_row,
)


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


# --- P69-07 ownership contract (owner_scope) ---------------------------------


def _pre_owner_scope_db(root: Path) -> Path:
    """A database already migrated to `artifact_version` but predating
    `owner_scope_kind`/`owner_scope_id` -- the real shape a pre-P69-07 Rush
    leaves behind, and the one `open_readonly()` must still read usefully."""
    db = _legacy_db(root)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "ALTER TABLE memory_artifacts ADD COLUMN artifact_version "
            "INTEGER NOT NULL DEFAULT 1"
        )
    return db


def _artifact(**overrides: object) -> MemoryArtifact:
    base: dict[str, object] = {
        "id": "a1",
        "family": "memory",
        "subject": "preference",
        "trust_tier": "IMPORTED",
        "content": {"value": 1},
        "source": "test",
        "created_at": 1.0,
    }
    base.update(overrides)
    return MemoryArtifact(**base)  # type: ignore[arg-type]


def test_owner_scope_validates_kind_and_id_structurally() -> None:
    assert OwnerScope("project", "p1").as_dict() == {"kind": "project", "id": "p1"}
    for kind in ("user", "project", "session", "agent"):
        assert OwnerScope(kind, "x").kind == kind
    with pytest.raises(ValueError):
        OwnerScope("root", "x")
    with pytest.raises(ValueError):
        OwnerScope("user", "")
    with pytest.raises(ValueError):
        OwnerScope("user", "   ")


def test_legacy_migration_backfills_default_owner_scope(tmp_path: Path) -> None:
    db = _legacy_db(tmp_path)

    TypedArtifactStore.upgrade(tmp_path, cache_write=True)

    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT owner_scope_kind, owner_scope_id FROM memory_artifacts"
        ).fetchone()
    default = legacy_owner_scope(tmp_path)
    assert default == OwnerScope("project", str(tmp_path.resolve()))
    assert row == (default.kind, default.id)


def test_pre_owner_scope_rows_read_back_with_the_legacy_default(
    tmp_path: Path,
) -> None:
    """A row that predates the owner columns keeps NULL on disk -- rewriting it in
    `_init_db()` would fire `memory_fts`'s AFTER UPDATE trigger against an FTS index
    that never held it -- and resolves to the legacy default on every read."""
    db = _pre_owner_scope_db(tmp_path)

    store = TypedArtifactStore(tmp_path)

    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT owner_scope_kind, owner_scope_id FROM memory_artifacts"
        ).fetchone()
    assert row == (None, None)
    current = store.get_current("legacy-id")
    assert current is not None
    assert current.owner_scope == legacy_owner_scope(tmp_path)


def test_readonly_open_of_unmigrated_database_returns_legacy_default_owner_scope(
    tmp_path: Path,
) -> None:
    _pre_owner_scope_db(tmp_path)

    result = TypedArtifactStore.open_readonly(tmp_path)

    assert result.available is True
    assert result.migration_required is False
    assert result.connection is not None
    row = result.connection.execute("SELECT * FROM memory_artifacts").fetchone()
    assert owner_scope_for_row(row, tmp_path) == legacy_owner_scope(tmp_path)
    result.connection.close()


def test_write_stores_explicit_owner_scope_and_defaults_to_the_project(
    tmp_path: Path,
) -> None:
    store = TypedArtifactStore(tmp_path)

    owned = store.write(_artifact(owner_scope=OwnerScope("user", "alice")))
    unowned = store.write(_artifact(id="a2"))

    assert owned.owner_scope == OwnerScope("user", "alice")
    assert unowned.owner_scope == legacy_owner_scope(tmp_path)
    assert store.get_current("a1").owner_scope == OwnerScope("user", "alice")


def test_owner_scope_mismatch_within_same_project_rejected(tmp_path: Path) -> None:
    store = TypedArtifactStore(tmp_path)
    store.write(_artifact(owner_scope=OwnerScope("user", "alice")))

    with pytest.raises(OwnerScopeError) as caught:
        store.edit(
            "a1",
            {"value": 9},
            expected_version=1,
            scope="preference",
            owner_scope=OwnerScope("user", "bob"),
            apply=True,
        )

    assert caught.value.code == "E_OWNER"
    assert store.get_current("a1").content == {"value": 1}


def test_owner_scope_is_immutable_after_write(tmp_path: Path) -> None:
    store = TypedArtifactStore(tmp_path)
    store.write(_artifact(owner_scope=OwnerScope("user", "alice")))

    store.edit(
        "a1",
        {"value": 2},
        expected_version=1,
        scope="preference",
        owner_scope=OwnerScope("user", "alice"),
        apply=True,
    )
    store.archive(
        "a1",
        expected_version=2,
        scope="preference",
        owner_scope=OwnerScope("user", "alice"),
        apply=True,
    )

    assert store.get_current("a1").owner_scope == OwnerScope("user", "alice")


def test_archive_rejects_wrong_owner_scope(tmp_path: Path) -> None:
    store = TypedArtifactStore(tmp_path)
    store.write(_artifact(owner_scope=OwnerScope("agent", "agent-7")))

    with pytest.raises(OwnerScopeError):
        store.archive(
            "a1",
            expected_version=1,
            scope="preference",
            owner_scope=OwnerScope("agent", "agent-8"),
            apply=True,
        )

    assert store.get_current("a1").content == {"value": 1}
    with sqlite3.connect(store.db_path) as conn:
        archived_at = conn.execute(
            "SELECT archived_at FROM memory_artifacts WHERE id='a1'"
        ).fetchone()[0]
    assert archived_at is None


def test_promote_rejects_mismatched_owner_scope(tmp_path: Path) -> None:
    """S08 bullet 3: `promote()` previously took no `owner_scope` at all --
    the only mutating method missing the compare-and-swap ownership check
    `edit()`/`archive()`/`delete_batch()` already enforce (P69-07). A wrong
    owner now rejects before any write, exactly like a stale
    `expected_version`."""
    store = TypedArtifactStore(tmp_path)
    store.write(_artifact(owner_scope=OwnerScope("user", "alice")))

    with pytest.raises(OwnerScopeError) as caught:
        store.promote(
            "a1",
            user_stated=True,
            expected_version=1,
            owner_scope=OwnerScope("user", "bob"),
        )

    assert caught.value.code == "E_OWNER"
    assert store.get_current("a1").trust_tier == "IMPORTED"


def test_promote_succeeds_with_matching_owner_scope(tmp_path: Path) -> None:
    store = TypedArtifactStore(tmp_path)
    store.write(_artifact(owner_scope=OwnerScope("user", "alice")))

    promoted, decision = store.promote(
        "a1",
        user_stated=True,
        expected_version=1,
        owner_scope=OwnerScope("user", "alice"),
    )

    assert decision.promoted is True
    assert promoted.trust_tier == "STATED"


def test_store_subject_equality_check_unaffected_by_owner_scope(
    tmp_path: Path,
) -> None:
    store = TypedArtifactStore(tmp_path)
    store.write(_artifact(owner_scope=OwnerScope("user", "alice")))

    with pytest.raises(MemoryScopeError):
        store.edit(
            "a1",
            {"value": 2},
            expected_version=1,
            scope="episodic",
            owner_scope=OwnerScope("user", "alice"),
            apply=True,
        )


def test_delete_batch_with_one_wrong_owner_member_writes_zero_rows(
    tmp_path: Path,
) -> None:
    store = TypedArtifactStore(tmp_path)
    store.write(_artifact(owner_scope=OwnerScope("user", "alice")))
    store.write(_artifact(id="a2", owner_scope=OwnerScope("user", "bob")))

    with pytest.raises(OwnerScopeError):
        store.delete_batch(
            ["a1", "a2"],
            expected_revisions={"a1": 1, "a2": 1},
            scope="preference",
            owner_scope=OwnerScope("user", "alice"),
            apply=True,
        )

    with sqlite3.connect(store.db_path) as conn:
        remaining = sorted(
            row[0] for row in conn.execute("SELECT id FROM memory_artifacts")
        )
        tombstones = conn.execute(
            "SELECT COUNT(*) FROM memory_changes WHERE tombstone = 1"
        ).fetchone()[0]
    assert remaining == ["a1", "a2"]
    assert tombstones == 0


def test_delete_batch_writes_one_distinct_receipt_per_target_from_mapping(
    tmp_path: Path,
) -> None:
    """T040/S04 residual: `receipt_operation_ids` (a target_id -> reserved
    receipt id mapping) makes `delete_batch()` persist one real receipt per
    target -- each addressed to its own `artifact_id` -- instead of the
    legacy single whole-batch receipt. A preview (`apply=False`) still
    writes nothing, and the batch's atomicity is unaffected: both targets
    commit (and receipt) inside the one transaction."""
    store = TypedArtifactStore(tmp_path)
    store.write(_artifact(id="a1"))
    store.write(_artifact(id="a2"))
    mapping = {"a1": "recv-op-a1", "a2": "recv-op-a2"}

    preview = store.delete_batch(
        ["a1", "a2"],
        expected_revisions={"a1": 1, "a2": 1},
        scope="preference",
        apply=False,
        receipt_operation_ids=mapping,
    )
    assert preview["applied"] is False
    assert store.get_receipt("recv-op-a1") is None
    assert store.get_receipt("recv-op-a2") is None

    store.delete_batch(
        ["a1", "a2"],
        expected_revisions={"a1": 1, "a2": 1},
        scope="preference",
        apply=True,
        receipt_operation_ids=mapping,
    )

    receipt_1 = store.get_receipt("recv-op-a1")
    receipt_2 = store.get_receipt("recv-op-a2")
    assert receipt_1 is not None
    assert receipt_2 is not None
    assert receipt_1["artifact_id"] == "a1"
    assert receipt_2["artifact_id"] == "a2"
    assert receipt_1["kind"] == "delete"
    assert receipt_2["kind"] == "delete"
    # Never one receipt written under a separate whole-batch id.
    assert store.get_receipt("op-delete-1") is None


def test_delete_batch_legacy_scalar_receipt_id_still_writes_one_whole_batch_receipt(
    tmp_path: Path,
) -> None:
    """Backward compatibility: a caller still passing the older scalar
    `receipt_operation_id` (no mapping) keeps writing exactly one
    whole-batch receipt, `artifact_id=None` -- unchanged legacy shape for
    any caller that hasn't moved to the per-target mapping."""
    store = TypedArtifactStore(tmp_path)
    store.write(_artifact(id="a1"))

    store.delete_batch(
        ["a1"],
        expected_revisions={"a1": 1},
        scope="preference",
        apply=True,
        receipt_operation_id="whole-batch-op",
    )

    receipt = store.get_receipt("whole-batch-op")
    assert receipt is not None
    assert receipt["artifact_id"] is None
    assert receipt["kind"] == "delete"


def _promoted_stated_row(store: TypedArtifactStore, root: Path, **kwargs) -> None:
    (root / "mod.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    stored = store.write(_artifact(symbol_ref="mod.py::helper", **kwargs))
    _, decision = store.promote(
        stored.id, user_stated=True, expected_version=stored.artifact_version
    )
    assert decision.promoted is True


def test_write_conflict_resolution_never_deletes_a_different_owners_stated_record(
    tmp_path: Path,
) -> None:
    store = TypedArtifactStore(tmp_path)
    _promoted_stated_row(
        store, tmp_path, content={"flag": True}, owner_scope=OwnerScope("user", "alice")
    )

    store.write(
        _artifact(
            id="a2",
            content={"flag": False},
            source="other",
            created_at=2.0,
            symbol_ref="mod.py::helper",
            owner_scope=OwnerScope("user", "bob"),
        )
    )

    with sqlite3.connect(store.db_path) as conn:
        remaining = sorted(
            row[0] for row in conn.execute("SELECT id FROM memory_artifacts")
        )
    assert remaining == ["a1", "a2"]


def test_write_conflict_resolution_still_deletes_the_same_owners_stated_record(
    tmp_path: Path,
) -> None:
    store = TypedArtifactStore(tmp_path)
    alice = OwnerScope("user", "alice")
    _promoted_stated_row(store, tmp_path, content={"flag": True}, owner_scope=alice)

    store.write(
        _artifact(
            id="a2",
            content={"flag": False},
            source="other",
            created_at=2.0,
            symbol_ref="mod.py::helper",
            owner_scope=alice,
        )
    )

    with sqlite3.connect(store.db_path) as conn:
        remaining = sorted(
            row[0] for row in conn.execute("SELECT id FROM memory_artifacts")
        )
    assert remaining == ["a2"]


def test_preview_apply_false_never_creates_directories_or_touches_database_bytes(
    tmp_path: Path,
) -> None:
    from rush.tools.memory import MemoryTool

    fresh = tmp_path / "fresh"
    fresh.mkdir()
    before = sorted(str(p.relative_to(fresh)) for p in fresh.rglob("*"))
    result = MemoryTool().run(
        fresh,
        operation="edit",
        request={
            "scope": "preference",
            "id": "missing",
            "expected_version": 1,
            "content": {"value": 1},
            "owner_scope": {"kind": "project", "id": str(fresh)},
            "apply": False,
        },
    )
    assert result["raw"]["code"] == "E_INPUT"
    assert sorted(str(p.relative_to(fresh)) for p in fresh.rglob("*")) == before

    legacy_root = tmp_path / "legacy"
    legacy_root.mkdir()
    db = _legacy_db(legacy_root)
    db_bytes = db.read_bytes()
    entries = sorted(p.name for p in db.parent.iterdir())
    result = MemoryTool().run(
        legacy_root,
        operation="archive",
        request={
            "scope": "preference",
            "id": "legacy-id",
            "expected_version": 1,
            "owner_scope": {"kind": "project", "id": str(legacy_root)},
            "apply": False,
        },
    )
    assert result["raw"]["code"] == "E_MIGRATION"
    assert db.read_bytes() == db_bytes
    assert sorted(p.name for p in db.parent.iterdir()) == entries


def test_preview_apply_false_still_reports_real_row_state(tmp_path: Path) -> None:
    from rush.tools.memory import MemoryTool

    store = TypedArtifactStore(tmp_path)
    store.write(_artifact(owner_scope=OwnerScope("user", "alice")))

    result = MemoryTool().run(
        tmp_path,
        operation="edit",
        request={
            "scope": "preference",
            "id": "a1",
            "expected_version": 1,
            "content": {"value": 5},
            "owner_scope": {"kind": "user", "id": "alice"},
            "apply": False,
        },
    )

    assert result["raw"]["code"] == "OK"
    assert result["raw"]["data"] == {
        "applied": False,
        "id": "a1",
        "revision": 1,
        "trust_tier": "IMPORTED",
    }

    denied = MemoryTool().run(
        tmp_path,
        operation="edit",
        request={
            "scope": "preference",
            "id": "a1",
            "expected_version": 1,
            "content": {"value": 5},
            "owner_scope": {"kind": "user", "id": "bob"},
            "apply": False,
        },
    )
    assert denied["raw"]["code"] == "E_OWNER"


def test_memory_tool_accepts_owner_scope_on_all_five_operations(
    tmp_path: Path,
) -> None:
    from rush.permissions import ExecutionPermissions
    from rush.tools.memory import MemoryTool

    tool = MemoryTool()
    granted = ExecutionPermissions(cache_write=True)
    owner = {"kind": "agent", "id": "agent-7"}

    written = tool.run(
        tmp_path,
        operation="write",
        subject="preference",
        content={"value": 1},
        source="unit",
        owner_scope=owner,
        permissions=granted,
    )
    assert written["status"] == "ok"
    artifact_id = written["raw"]["id"]
    assert written["raw"]["owner_scope"] == owner

    promoted = tool.run(
        tmp_path,
        operation="promote",
        subject="preference",
        content={"value": 2},
        source="unit",
        user_stated=True,
        owner_scope=owner,
        permissions=granted,
    )
    assert promoted["raw"]["artifact"]["owner_scope"] == owner

    edited = tool.run(
        tmp_path,
        operation="edit",
        request={
            "scope": "preference",
            "id": artifact_id,
            "expected_version": 1,
            "content": {"value": 3},
            "owner_scope": owner,
            "apply": True,
        },
        permissions=granted,
    )
    assert edited["raw"]["code"] == "OK"

    archived = tool.run(
        tmp_path,
        operation="archive",
        request={
            "scope": "preference",
            "id": artifact_id,
            "expected_version": 2,
            "owner_scope": owner,
            "apply": True,
        },
        permissions=granted,
    )
    assert archived["raw"]["code"] == "OK"

    deleted = tool.run(
        tmp_path,
        operation="delete",
        request={
            "artifact_ids": [artifact_id],
            "expected_revisions": {artifact_id: 3},
            "scope": "preference",
            "owner_scope": owner,
            "apply": True,
        },
        permissions=granted,
    )
    assert deleted["raw"]["code"] == "OK"


def test_memory_tool_rejects_a_wrong_owner_on_delete(tmp_path: Path) -> None:
    from rush.permissions import ExecutionPermissions
    from rush.tools.memory import MemoryTool

    store = TypedArtifactStore(tmp_path)
    store.write(_artifact(owner_scope=OwnerScope("user", "alice")))

    result = MemoryTool().run(
        tmp_path,
        operation="delete",
        request={
            "artifact_ids": ["a1"],
            "expected_revisions": {"a1": 1},
            "scope": "preference",
            "owner_scope": {"kind": "user", "id": "bob"},
            "apply": True,
        },
        permissions=ExecutionPermissions(cache_write=True),
    )

    assert result["raw"]["code"] == "E_OWNER"
    assert store.get_current("a1") is not None


def test_memory_tool_rejects_a_project_owner_scope_naming_another_project(
    tmp_path: Path,
) -> None:
    from rush.permissions import ExecutionPermissions
    from rush.tools.memory import MemoryTool

    other = tmp_path / "other"
    other.mkdir()
    result = MemoryTool().run(
        tmp_path,
        operation="write",
        subject="preference",
        content={"value": 1},
        source="unit",
        owner_scope={"kind": "project", "id": str(other)},
        permissions=ExecutionPermissions(cache_write=True),
    )

    assert result["status"] == "error"
    assert "owner_scope" in result["summary"]


def test_session_owner_scope_id_is_never_the_session_cookie_or_csrf_value() -> None:
    from rush.dashboard.auth import DashboardAuth

    auth = DashboardAuth()
    token = auth.issue_bootstrap()
    exchanged = auth.exchange_bootstrap(token)
    assert exchanged is not None
    session, cookie_value = exchanged

    assert session.owner_scope_id
    assert session.owner_scope_id not in (
        cookie_value,
        session.cookie_digest,
        session.csrf_token,
    )
    assert OwnerScope("session", session.owner_scope_id).id == session.owner_scope_id


def test_standalone_tui_invocation_has_a_usable_session_owner_scope_id() -> None:
    from rush.tui import _tui_session_owner_scope_id

    session_id = _tui_session_owner_scope_id()

    assert session_id
    assert _tui_session_owner_scope_id() == session_id
    assert OwnerScope("session", session_id).kind == "session"


def _fake_actions(calls: list[dict[str, object]]):
    from rush.tui import ScanActions

    def _memory_run(root, **kwargs):
        calls.append(kwargs)
        return {"status": "ok", "raw": {"code": "OK", "data": {"affected": []}}}

    def noop(*_args: object, **_kwargs: object) -> None:
        """Unused injectable seam -- this test only exercises `memory_run`."""

    return ScanActions(
        noop, noop, noop, noop, noop, noop, noop, list, memory_run=_memory_run
    )


def _memory_state(tmp_path: Path):
    from rush.tui import ProjectState, TuiState

    state = TuiState(projects=[ProjectState(name="p", root=tmp_path)])
    state.memory_items = [
        {"id": "a1", "artifact_version": 1, "content": {"value": 1}, "source": "s"}
    ]
    return state


def test_tui_memory_admin_sends_owner_scope_on_every_mutation(tmp_path: Path) -> None:
    from rush.tui import (
        _handle_memory_key,
        _memory_delete_preview,
        _memory_edit_commit,
    )

    calls: list[dict[str, object]] = []
    actions = _fake_actions(calls)
    state = _memory_state(tmp_path)
    state.memory_owner_scope_kind = "user"
    state.memory_owner_scope_id = "alice"
    state.memory_edit_buffer = "hello"
    state.memory_selected_ids = {"a1"}

    _memory_edit_commit(state, state.active_project, actions)
    _handle_memory_key(state, "y", actions)
    # T28-D: the applied edit refreshes the list and clears the selection
    # (these fake actions list no rows), so the delete is previewed on a
    # listed, reselected row -- never on one the refresh dropped.
    state.memory_items = _memory_state(tmp_path).memory_items
    state.memory_selected_ids = {"a1"}
    _memory_delete_preview(state, state.active_project, actions)

    assert [call["request"]["owner_scope"] for call in calls] == [
        {"kind": "user", "id": "alice"},
        {"kind": "user", "id": "alice"},
        {"kind": "user", "id": "alice"},
    ]
    assert [call["request"]["apply"] for call in calls] == [False, True, False]


def test_tui_owner_scope_selector_cycles_all_four_kinds(tmp_path: Path) -> None:
    from rush.tui import _handle_memory_key, _handle_memory_owner_key

    calls: list[dict[str, object]] = []
    actions = _fake_actions(calls)
    state = _memory_state(tmp_path)

    _handle_memory_key(state, "o", actions)
    assert state.mode == "memory_owner"

    seen = [state.memory_owner_scope_kind]
    for _ in range(4):
        _handle_memory_owner_key(state, "tab", actions)
        seen.append(state.memory_owner_scope_kind)
    assert set(seen) == {"user", "project", "session", "agent"}

    state.memory_owner_scope_kind = "user"
    state.memory_owner_buffer = ""
    for char in "alice":
        _handle_memory_owner_key(state, char, actions)
    _handle_memory_owner_key(state, "enter", actions)

    assert state.mode == "memory"
    assert state.memory_owner_scope_id == "alice"


def test_tui_project_and_session_owner_kinds_have_real_default_ids(
    tmp_path: Path,
) -> None:
    """`project`-kind's default id is `ProjectState.project_id` (M09: a
    registered project's real UUID) when one was resolved -- the raw root
    path is only a fallback for an explicit unregistered-project result
    (`ProjectState.project_id is None`, this helper's default), never the
    unconditional value. `session`-kind is unaffected by M09."""
    from rush.tui import _memory_owner_scope, _tui_session_owner_scope_id

    state = _memory_state(tmp_path)
    project = state.active_project
    assert project.project_id is None  # unregistered-project fallback case

    state.memory_owner_scope_kind = "project"
    state.memory_owner_scope_id = ""
    assert _memory_owner_scope(state, project) == {
        "kind": "project",
        "id": str(tmp_path),
    }

    state.memory_owner_scope_kind = "session"
    assert _memory_owner_scope(state, project) == {
        "kind": "session",
        "id": _tui_session_owner_scope_id(),
    }


def test_tui_project_owner_kind_uses_registered_uuid_not_root_path_when_resolved(
    tmp_path: Path,
) -> None:
    """M09: a registered project's `ProjectState.project_id` wins over the raw
    root path for `project`-kind's default owner id -- this is the case
    `test_tui_project_and_session_owner_kinds_have_real_default_ids` above
    never exercises (it always leaves `project_id` unset)."""
    from rush.tui import _memory_owner_scope

    state = _memory_state(tmp_path)
    state.active_project.project_id = "11111111-1111-1111-1111-111111111111"
    project = state.active_project

    state.memory_owner_scope_kind = "project"
    state.memory_owner_scope_id = ""
    assert _memory_owner_scope(state, project) == {
        "kind": "project",
        "id": "11111111-1111-1111-1111-111111111111",
    }


def test_memory_migration_required_error_is_distinct_from_version_conflict() -> None:
    assert not issubclass(MemoryMigrationRequiredError, VersionConflictError)
    assert not issubclass(OwnerScopeError, MemoryScopeError)
