"""Phase 70 T20 test matrix: bare `rush memory` shows a read-only project overview.

Binding design: `.scratch/phase-70-design-gate/W3-T18-T22.md` §T20, cross-cutting
findings G1/G5/G8, and W4 §X2 (T20 now owns the shared `open_sqlite_readonly`
opener, per orchestrator ownership-change note).

Every RED here fails today because `rush.tools.memory.memory_overview`,
`rush.memory.store.open_sqlite_readonly`, `rush.memory.store.store_generation`,
and the `--include-internal`/bare-invocation `cli.py` group do not exist yet.
Predecessors T18 (internal-source predicate) and T23 (`project_snapshot`
construction fix) are not implemented in this worktree; T20's own filtering
uses the literal internal-source strings T18 will define (not an import of
T18 code), so no case here needs a `RED-via-T18` label. T8's
`resolve_logical_root` canonicalization is also absent from this worktree, so
the nested-directory parity case only asserts today's `Path.cwd().resolve()`
root consistency, not T8's canonical-root rule.

Fixtures write directly through `TypedArtifactStore.write`/raw sqlite3, never
through the CLI, so each test seeds exactly the row shape it asserts on.
"""

from __future__ import annotations

import gc
import json
import sqlite3
import time
import uuid
from pathlib import Path

import pytest
from click.testing import CliRunner

from rush.cli import cli
from rush.governance.public_operations import build_operations_inventory
from rush.mcp_support.tool_registry import build_memory_bridge_handler
from rush.memory.store import MemoryArtifact, OwnerScope, TypedArtifactStore
from rush.tools.memory import MemoryTool
from rush.tui import ProjectState

# --- shared local fixtures (kept local to this file, no shared conftest) ----


def _legacy_db(root: Path) -> Path:
    """A pre-`artifact_version` schema `memory.db` (mirrors
    `tests/test_memory_versions.py::_legacy_db`, kept local per task rules)."""
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
                None,
                None,
                None,
                None,
                None,
            ),
        )
    return db


def _pre_owner_scope_db(root: Path) -> Path:
    """A current-schema DB predating `owner_scope_kind`/`owner_scope_id` (mirrors
    `tests/test_memory_versions.py::_pre_owner_scope_db`)."""
    db = _legacy_db(root)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "ALTER TABLE memory_artifacts ADD COLUMN artifact_version "
            "INTEGER NOT NULL DEFAULT 1"
        )
    return db


def _artifact(**overrides: object) -> MemoryArtifact:
    base: dict[str, object] = {
        "id": str(uuid.uuid4()),
        "family": "memory",
        "subject": "preference",
        "trust_tier": "IMPORTED",
        "content": {"value": 1},
        "source": "test-source",
        "created_at": time.time(),
    }
    base.update(overrides)
    return MemoryArtifact(**base)  # type: ignore[arg-type]


def _rglob_snapshot(root: Path) -> set[str]:
    if not root.exists():
        return set()
    return {str(p.relative_to(root)) for p in root.rglob("*")}


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _checkpoint_and_close(store: TypedArtifactStore) -> None:
    """`TypedArtifactStore` never exposes `close()`; its per-call connections
    (`with self._connect() as conn:`) only commit on `__exit__`, not close, so
    a lingering reference cycle keeps `-wal`/`-shm` alive until cyclic GC
    actually runs. Force that now so a fixture's own writer leaves a clean,
    checkpointed single-file DB before the test's own "before" snapshot."""
    del store
    gc.collect()


def _run_cli(root: Path, args: list[str], monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(root)
    return CliRunner().invoke(cli, args)


def _overview_json(root: Path, monkeypatch: pytest.MonkeyPatch, *extra: str):
    result = _run_cli(root, ["memory", "--json", *extra], monkeypatch)
    payload = json.loads(result.output) if result.output.strip() else {}
    return result, payload


# =============================================================================
# W4 §X2 -- shared `open_sqlite_readonly` opener (T20 now owns this; T23
# depends on T20). This supersedes the retry/fingerprint sketch in the W3 T20
# §3 note: no retry, a `DatabaseError` during an immutable read is
# `state="read_conflict"`, never retried in a mode that creates sidecars.
# =============================================================================


class TestOpenSqliteReadonlyX2:
    def test_missing_db_is_unavailable_with_zero_io(self, tmp_path: Path) -> None:
        from rush.memory.store import open_sqlite_readonly

        root = tmp_path / "project"
        root.mkdir()
        before = _rglob_snapshot(root)

        result = open_sqlite_readonly(root / ".rush" / "memory.db")

        assert result.available is False
        assert _rglob_snapshot(root) == before

    def test_wal_present_opens_plain_ro_no_new_files(self, tmp_path: Path) -> None:
        from rush.memory.store import open_sqlite_readonly

        store = TypedArtifactStore(tmp_path)
        store.write(_artifact(id="a1"))
        # Keep a writer connection open so `-wal` survives past this call --
        # SQLite deletes `-wal` when a WAL database is closed cleanly.
        writer = sqlite3.connect(str(store.db_path))
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("SELECT 1")
        db_dir = store.db_path.parent
        before = sorted(p.name for p in db_dir.iterdir())
        assert any(name.endswith("-wal") for name in before)

        result = open_sqlite_readonly(store.db_path)

        assert result.available is True
        assert result.mode == "ro"
        assert sorted(p.name for p in db_dir.iterdir()) == before
        if result.connection is not None:
            result.connection.close()
        writer.rollback()
        writer.close()

    def test_no_wal_opens_immutable_with_last_checkpoint_consistency(
        self, tmp_path: Path
    ) -> None:
        from rush.memory.store import open_sqlite_readonly

        store = TypedArtifactStore(tmp_path)
        store.write(_artifact(id="a1"))
        _checkpoint_and_close(store)
        db_dir = tmp_path / ".rush"
        before = sorted(p.name for p in db_dir.iterdir())
        assert not any(name.endswith(("-wal", "-shm")) for name in before)

        result = open_sqlite_readonly(db_dir / "memory.db")

        assert result.available is True
        assert result.mode == "ro&immutable=1"
        assert result.consistency == "last_checkpoint"
        assert sorted(p.name for p in db_dir.iterdir()) == before
        if result.connection is not None:
            result.connection.close()

    def test_database_error_during_immutable_read_is_read_conflict_no_retry(
        self, tmp_path: Path
    ) -> None:
        from rush.memory.store import open_sqlite_readonly

        store = TypedArtifactStore(tmp_path)
        store.write(_artifact(id="a1"))
        _checkpoint_and_close(store)
        db_path = tmp_path / ".rush" / "memory.db"
        # Corrupt a page past the valid 100-byte header so `connect()` itself
        # can succeed but a read raises `sqlite3.DatabaseError`.
        raw = bytearray(db_path.read_bytes())
        raw[4096:4200] = b"\xff" * (4200 - 4096)
        db_path.write_bytes(bytes(raw))
        db_dir = db_path.parent
        before = sorted(p.name for p in db_dir.iterdir())
        before_bytes = db_path.read_bytes()

        result = open_sqlite_readonly(db_path)

        assert result.state == "read_conflict"
        assert result.available is False or result.connection is None
        assert sorted(p.name for p in db_dir.iterdir()) == before
        assert db_path.read_bytes() == before_bytes

    def test_result_carries_mode_consistency_state_fields(self, tmp_path: Path) -> None:
        from rush.memory.store import ReadOnlyOpenResult

        result = ReadOnlyOpenResult(available=False)
        assert result.mode is None
        assert result.consistency is None
        assert result.state is None

    def test_open_readonly_is_rewritten_onto_open_sqlite_readonly(
        self, tmp_path: Path
    ) -> None:
        """G1 regression via X2: the existing `open_readonly` classmethod must
        route through the new opener and inherit its no-sidecar guarantee."""
        store = TypedArtifactStore(tmp_path)
        store.write(_artifact(id="a1"))
        _checkpoint_and_close(store)
        db_dir = tmp_path / ".rush"
        before = sorted(p.name for p in db_dir.iterdir())

        result = TypedArtifactStore.open_readonly(tmp_path)

        assert result.available is True
        assert sorted(p.name for p in db_dir.iterdir()) == before
        if result.connection is not None:
            result.connection.close()


# =============================================================================
# `store_generation` module function (T20 deliverable): `current_generation`
# delegates to it; it must return 0 when `memory_changes` is absent (the
# `_pre_owner_scope_db` shape has no such table).
# =============================================================================


def test_store_generation_returns_zero_when_memory_changes_table_absent(
    tmp_path: Path,
) -> None:
    from rush.memory.store import store_generation

    db = _pre_owner_scope_db(tmp_path)
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        assert store_generation(conn) == 0


def test_store_generation_matches_current_generation_on_a_live_store(
    tmp_path: Path,
) -> None:
    from rush.memory.store import store_generation

    store = TypedArtifactStore(tmp_path)
    store.write(_artifact(id="a1"))
    with sqlite3.connect(store.db_path) as conn:
        conn.row_factory = sqlite3.Row
        assert store_generation(conn) == store.current_generation()


# =============================================================================
# CLI-level acceptance matrix: bare `rush memory`.
# =============================================================================


def test_virgin_project_ok_exit_zero_with_reason_and_zero_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    before = _rglob_snapshot(root)

    result, payload = _overview_json(root, monkeypatch)

    assert result.exit_code == 0, result.output
    data = payload["raw"]["data"]
    assert data["total"] == 0
    assert data["reason"]
    assert _rglob_snapshot(root) == before


def test_recent_rows_ordered_desc_created_at_then_id_with_exact_row_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = TypedArtifactStore(tmp_path)
    older = store.write(_artifact(id="row-older", created_at=1.0))
    newer = store.write(_artifact(id="row-newer", created_at=2.0))

    result, payload = _overview_json(tmp_path, monkeypatch)

    assert result.exit_code == 0, result.output
    rows = payload["raw"]["data"]["rows"]
    assert [r["id"] for r in rows] == [newer.id, older.id]
    row = rows[0]
    assert set(row) == {
        "id",
        "subject",
        "source",
        "owner_scope",
        "created_at",
        "trust_tier",
    }
    assert row["owner_scope"]["kind"] and row["owner_scope"]["id"]


def test_no_author_key_in_any_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = TypedArtifactStore(tmp_path)
    store.write(_artifact(id="a1"))

    _, payload = _overview_json(tmp_path, monkeypatch)

    for row in payload["raw"]["data"]["rows"]:
        assert "author" not in row
        assert "content" not in row


def test_source_redacted_and_raw_token_never_leaks_in_json_or_human(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "ghp_" + "a" * 24
    store = TypedArtifactStore(tmp_path)
    store.write(_artifact(id="a1", source=f"token={secret}"))

    result, payload = _overview_json(tmp_path, monkeypatch)
    assert secret not in result.output
    row = payload["raw"]["data"]["rows"][0]
    assert secret not in row["source"]
    assert "[REDACTED" in row["source"]

    human = _run_cli(tmp_path, ["memory"], monkeypatch)
    assert secret not in human.output


def test_owners_each_shown_with_their_own_stored_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = TypedArtifactStore(tmp_path)
    store.write(
        _artifact(id="a1", created_at=2.0, owner_scope=OwnerScope("user", "alice"))
    )
    store.write(
        _artifact(id="a2", created_at=1.0, owner_scope=OwnerScope("user", "bob"))
    )

    _, payload = _overview_json(tmp_path, monkeypatch)

    rows = {r["id"]: r["owner_scope"] for r in payload["raw"]["data"]["rows"]}
    assert rows["a1"] == {"kind": "user", "id": "alice"}
    assert rows["a2"] == {"kind": "user", "id": "bob"}


@pytest.mark.parametrize(
    "make_hidden",
    [
        lambda store, id_: store.archive(
            id_, expected_version=1, scope="preference", apply=True
        ),
        None,  # expired: set directly below (no public store API to expire)
    ],
    ids=["archived", "expired"],
)
def test_archived_and_expired_rows_excluded_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_hidden
) -> None:
    store = TypedArtifactStore(tmp_path)
    hidden = store.write(_artifact(id="hidden", created_at=2.0))
    visible = store.write(_artifact(id="visible", created_at=1.0))
    if make_hidden is not None:
        make_hidden(store, hidden.id)
    else:
        with sqlite3.connect(store.db_path) as conn:
            conn.execute(
                "UPDATE memory_artifacts SET expired_at = ? WHERE id = ?",
                (time.time(), hidden.id),
            )

    _, payload = _overview_json(tmp_path, monkeypatch)

    rows = payload["raw"]["data"]["rows"]
    assert [r["id"] for r in rows] == [visible.id]
    assert payload["raw"]["data"]["total"] == 1


def test_internal_sources_excluded_by_default_and_shown_with_include_internal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Literal internal-source strings T18 defines
    (`INTERNAL_MEMORY_SOURCES`), asserted here without importing T18 code --
    not present in this worktree."""
    store = TypedArtifactStore(tmp_path)
    internal = store.write(
        _artifact(id="internal", created_at=2.0, source="flight_recorder:record_event")
    )
    useful = store.write(_artifact(id="useful", created_at=1.0, source="test-source"))

    _, default_payload = _overview_json(tmp_path, monkeypatch)
    default_rows = default_payload["raw"]["data"]["rows"]
    assert [r["id"] for r in default_rows] == [useful.id]
    assert default_payload["raw"]["data"]["hidden_internal"] == 1

    _, included_payload = _overview_json(tmp_path, monkeypatch, "--include-internal")
    included_rows = included_payload["raw"]["data"]["rows"]
    assert {r["id"] for r in included_rows} == {internal.id, useful.id}


def test_pagination_21_rows_same_created_at_exact_tie_order_and_token_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = TypedArtifactStore(tmp_path)
    ids = [f"row-{i:02d}" for i in range(21)]
    for artifact_id in ids:
        store.write(_artifact(id=artifact_id, created_at=100.0))

    page1_result, page1 = _overview_json(tmp_path, monkeypatch)
    assert page1_result.exit_code == 0, page1_result.output
    data1 = page1["raw"]["data"]
    assert data1["total"] == 21
    assert len(data1["rows"]) == 20
    # descending id for identical created_at
    assert data1["rows"][0]["id"] == max(ids)
    token = data1["generation_token"]
    assert data1["next_offset"] == 20

    page2_result, page2 = _overview_json(
        tmp_path, monkeypatch, "--offset", "20", "--generation", token
    )
    assert page2_result.exit_code == 0, page2_result.output
    data2 = page2["raw"]["data"]
    assert len(data2["rows"]) == 1
    assert data2["rows"][0]["id"] == min(ids)
    assert data2["next_offset"] is None


def test_offset_beyond_end_is_ok_with_empty_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = TypedArtifactStore(tmp_path)
    store.write(_artifact(id="only", created_at=1.0))

    _, page1 = _overview_json(tmp_path, monkeypatch)
    token = page1["raw"]["data"]["generation_token"]

    result, payload = _overview_json(
        tmp_path, monkeypatch, "--offset", "500", "--generation", token
    )
    assert result.exit_code == 0, result.output
    data = payload["raw"]["data"]
    assert data["rows"] == []
    assert data["next_offset"] is None


def test_offset_without_token_rejected_with_no_db_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    before = _rglob_snapshot(root)

    result, payload = _overview_json(root, monkeypatch, "--offset", "5")

    assert result.exit_code == 2, result.output
    assert payload["raw"]["data"]["reason"] == "token_required"
    assert payload["raw"]["data"]["restart"] == {"offset": 0}
    assert _rglob_snapshot(root) == before


def test_stale_generation_token_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = TypedArtifactStore(tmp_path)
    store.write(_artifact(id="a1", created_at=1.0))
    _, page1 = _overview_json(tmp_path, monkeypatch)
    token = page1["raw"]["data"]["generation_token"]

    store.write(_artifact(id="a2", created_at=2.0))  # bumps generation

    result, payload = _overview_json(
        tmp_path, monkeypatch, "--offset", "1", "--generation", token
    )
    assert result.exit_code == 2, result.output
    assert payload["raw"]["data"]["reason"] == "stale_generation"
    assert payload["raw"]["data"]["restart"] == {"offset": 0}


def test_cross_project_token_with_equal_generation_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_a = tmp_path / "a"
    project_b = tmp_path / "b"
    project_a.mkdir()
    project_b.mkdir()
    TypedArtifactStore(project_a).write(_artifact(id="a1", created_at=1.0))
    TypedArtifactStore(project_b).write(_artifact(id="b1", created_at=1.0))

    _, page_a = _overview_json(project_a, monkeypatch)
    token_a = page_a["raw"]["data"]["generation_token"]

    result, payload = _overview_json(
        project_b, monkeypatch, "--offset", "1", "--generation", token_a
    )
    assert result.exit_code == 2, result.output
    assert payload["raw"]["data"]["reason"] == "project_mismatch"


def test_changed_include_internal_filter_rejects_the_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = TypedArtifactStore(tmp_path)
    for i in range(2):
        store.write(_artifact(id=f"a{i}", created_at=float(i)))

    _, page1 = _overview_json(tmp_path, monkeypatch)
    token = page1["raw"]["data"]["generation_token"]

    result, payload = _overview_json(
        tmp_path,
        monkeypatch,
        "--include-internal",
        "--offset",
        "1",
        "--generation",
        token,
    )
    assert result.exit_code == 2, result.output
    assert payload["raw"]["data"]["reason"] == "filter_mismatch"


def test_malformed_token_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = TypedArtifactStore(tmp_path)
    store.write(_artifact(id="a1", created_at=1.0))
    _, page1 = _overview_json(tmp_path, monkeypatch)
    token = page1["raw"]["data"]["generation_token"]
    tampered = ("X" if token[0] != "X" else "Y") + token[1:]

    result, payload = _overview_json(
        tmp_path, monkeypatch, "--offset", "0", "--generation", tampered
    )
    assert result.exit_code == 2, result.output
    assert payload["raw"]["data"]["reason"] == "malformed_token"


def test_subcommand_with_overview_option_is_usage_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    root.mkdir()

    result = _run_cli(
        root,
        ["memory", "--offset", "5", "ask", "preference", "q", "--session", "s"],
        monkeypatch,
    )

    assert result.exit_code == 2, result.output


def test_nested_directory_write_then_root_overview_shows_the_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    nested = root / "sub" / "dir"
    nested.mkdir(parents=True)
    # Project marker: makes `project/` the logical root for commands run below it.
    (root / "rush.toml").write_text("", encoding="utf-8")

    write_result = _run_cli(
        nested,
        [
            "memory",
            "write",
            "preference",
            "test-source",
            "--content",
            json.dumps({"value": 1}),
            "--allow-cache-write",
            "--json",
        ],
        monkeypatch,
    )
    assert write_result.exit_code == 0, write_result.output

    result, payload = _overview_json(root, monkeypatch)
    assert result.exit_code == 0, result.output
    assert payload["raw"]["data"]["total"] == 1


def test_older_read_compatible_db_shows_legacy_owner_and_generation_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.memory.store import legacy_owner_scope

    _pre_owner_scope_db(tmp_path)
    db_path = tmp_path / ".rush" / "memory.db"
    with sqlite3.connect(db_path) as conn:
        columns_before = sorted(
            row[1] for row in conn.execute("PRAGMA table_info(memory_artifacts)")
        )

    result, payload = _overview_json(tmp_path, monkeypatch)

    assert result.exit_code == 0, result.output
    data = payload["raw"]["data"]
    assert data["rows"][0]["owner_scope"] == legacy_owner_scope(tmp_path).as_dict()
    token_bytes = data["generation_token"]
    assert token_bytes  # decodable, generation 0 encoded inside
    with sqlite3.connect(db_path) as conn:
        columns_after = sorted(
            row[1] for row in conn.execute("PRAGMA table_info(memory_artifacts)")
        )
    assert columns_after == columns_before


def test_unsupported_schema_errors_without_migration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = _legacy_db(tmp_path)  # no `artifact_version` column at all
    before_bytes = db_path.read_bytes()

    result, payload = _overview_json(tmp_path, monkeypatch)

    assert result.exit_code == 2, result.output
    assert payload["raw"]["code"] == "E_SCHEMA_UNSUPPORTED"
    assert db_path.read_bytes() == before_bytes


def test_corrupt_db_reports_store_corrupt_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / ".rush" / "memory.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_bytes(b"not a sqlite file at all, just junk bytes" * 10)

    result, payload = _overview_json(tmp_path, monkeypatch)

    assert result.exit_code == 2, result.output
    assert payload["raw"]["code"] == "E_STORE_CORRUPT"


# =============================================================================
# R20.G8 -- dashboard/TUI read paths must not create or migrate `memory.db`.
# =============================================================================


def _fresh_and_current_projects(tmp_path: Path) -> tuple[Path, Path]:
    virgin = tmp_path / "virgin"
    virgin.mkdir()
    current = tmp_path / "current"
    current.mkdir()
    store = TypedArtifactStore(current)
    store.write(_artifact(id="a1"))
    _checkpoint_and_close(store)
    return virgin, current


class TestDashboardTuiReadNoCreate:
    """Each surface, on a project with no `memory.db`, must create none; on a
    project with a current-schema `memory.db`, bytes and directory listing
    must stay identical (no `-wal`/`-shm`)."""

    def test_build_memory_section_virgin_creates_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from rush.dashboard import server as server_module
        from rush.workflows import projects as projects_module

        data_root = tmp_path / "rush-data"
        monkeypatch.setattr(projects_module, "default_data_root", lambda: data_root)
        virgin, _ = _fresh_and_current_projects(tmp_path)
        record = projects_module.register_project(virgin)
        before = _rglob_snapshot(virgin)

        server_module._build_memory_section(record.project_id, {})

        assert _rglob_snapshot(virgin) == before

    def test_build_memory_section_current_db_byte_identical(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from rush.dashboard import server as server_module
        from rush.workflows import projects as projects_module

        data_root = tmp_path / "rush-data"
        monkeypatch.setattr(projects_module, "default_data_root", lambda: data_root)
        _, current = _fresh_and_current_projects(tmp_path)
        record = projects_module.register_project(current)
        db_path = current / ".rush" / "memory.db"
        before_hash = _sha256(db_path)
        before_dir = sorted(p.name for p in db_path.parent.iterdir())

        server_module._build_memory_section(record.project_id, {})

        assert _sha256(db_path) == before_hash
        assert sorted(p.name for p in db_path.parent.iterdir()) == before_dir

    def test_sync_current_map_creates_nothing_on_virgin_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from rush.dashboard import server as server_module
        from rush.workflows import projects as projects_module

        data_root = tmp_path / "rush-data"
        monkeypatch.setattr(projects_module, "default_data_root", lambda: data_root)
        virgin, _ = _fresh_and_current_projects(tmp_path)
        record = projects_module.register_project(virgin)
        snapshot = {
            "schema_version": 1,
            "project_id": record.project_id,
            "source_identity": str(virgin),
            "root": str(virgin),
            "files": [],
            "findings": [],
            "memories": [],
            "agents": [],
        }
        _server, ctx, _token = server_module.create_dashboard_server(
            {record.project_id: snapshot}
        )
        before = _rglob_snapshot(virgin)

        server_module._sync_current_map(ctx, record.project_id)

        assert _rglob_snapshot(virgin) == before

    def test_build_tokens_section_creates_nothing_on_virgin_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from rush.dashboard import server as server_module
        from rush.workflows import projects as projects_module

        data_root = tmp_path / "rush-data"
        monkeypatch.setattr(projects_module, "default_data_root", lambda: data_root)
        virgin, _ = _fresh_and_current_projects(tmp_path)
        record = projects_module.register_project(virgin)
        before = _rglob_snapshot(virgin)

        server_module._build_tokens_section(record.project_id, {})

        assert _rglob_snapshot(virgin) == before

    def test_tui_memory_known_sources_creates_nothing_on_virgin_project(
        self, tmp_path: Path
    ) -> None:
        from rush import tui as tui_module

        virgin = tmp_path / "virgin"
        virgin.mkdir()
        before = _rglob_snapshot(virgin)

        tui_module._memory_known_sources(ProjectState(name="virgin", root=virgin))

        assert _rglob_snapshot(virgin) == before

    def test_tui_memory_known_sources_current_db_byte_identical(
        self, tmp_path: Path
    ) -> None:
        from rush import tui as tui_module

        current = tmp_path / "current"
        current.mkdir()
        store = TypedArtifactStore(current)
        store.write(_artifact(id="a1"))
        _checkpoint_and_close(store)
        db_path = current / ".rush" / "memory.db"
        before_hash = _sha256(db_path)
        before_dir = sorted(p.name for p in db_path.parent.iterdir())

        tui_module._memory_known_sources(ProjectState(name="current", root=current))

        assert _sha256(db_path) == before_hash
        assert sorted(p.name for p in db_path.parent.iterdir()) == before_dir


# =============================================================================
# B7 -- no MCP overview exposure. The full server and restricted receiver
# already reject "overview" today (keep-green guards, locked here so T20
# cannot silently open this path); MC02 ask/recall-without-allowlist
# fail-closed is also already true today.
# =============================================================================


def test_full_mcp_server_schema_rejects_overview_operation(tmp_path: Path) -> None:
    import asyncio
    import json as _json

    from mcp.types import CallToolResult, TextContent

    from rush.mcp import build_server

    server = build_server()

    async def _call() -> object:
        return await server.call_tool(
            "rush_memory", {"path": str(tmp_path), "operation": "overview"}
        )

    # Since T6 the full server validates the request against the published
    # schema before dispatch: `overview` is not a MemoryTool operation, so the
    # call is rejected as a structured E_INPUT error with zero effects.
    result = asyncio.run(_call())
    assert isinstance(result, CallToolResult)
    block = result.content[0]
    assert isinstance(block, TextContent)
    payload = _json.loads(block.text)
    assert payload["status"] == "error"
    assert payload["raw"]["code"] == "E_INPUT"
    assert "operation must be one of" in payload["raw"]["data"]["message"]
    assert "overview" not in payload["raw"]["data"]["message"].split(":")[-1]
    assert not (tmp_path / ".rush").exists()


def test_restricted_memory_session_server_rejects_overview(tmp_path: Path) -> None:
    handler = build_memory_bridge_handler(
        root=tmp_path, session_id="s1", capability="cap1"
    )

    result = handler("overview", {})

    assert result["code"] == "E_PERMISSION"


def test_ask_without_session_allowlist_fails_closed(tmp_path: Path) -> None:
    result = MemoryTool().run(
        tmp_path,
        operation="ask",
        subject="preference",
        query="x",
        session_allowlist=None,
    )
    assert result["status"] == "skipped"


def test_rush_memory_schema_operation_count_unchanged_at_22(tmp_path: Path) -> None:
    from rush.tools.memory import VALID_OPERATIONS

    assert len(VALID_OPERATIONS) == 22
    assert "overview" not in VALID_OPERATIONS


# =============================================================================
# G5 -- bare `rush memory` must not silently become an unadvertised CLI leaf.
# =============================================================================


def test_operations_manifest_gains_the_cli_memory_op() -> None:
    inventory = build_operations_inventory()
    by_id = {op.id: op for op in inventory}

    assert "cli.memory" in by_id
    op = by_id["cli.memory"]
    assert op.kind == "admin"
    assert op.canonical_impl == "rush.cli:memory"
    assert op.cli_command == "memory"
    assert op.mcp_tool is None
    assert op.effect_class == "read-only"
    assert op.safe_probe == "rush memory --help"


# =============================================================================
# Fix round 1: old-schema stores report `migration_required` on every read
# surface (never shown as empty, never migrated), and the dashboard query path
# stays read-only.
# =============================================================================


def test_cli_overview_reports_migration_required_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = _legacy_db(tmp_path)
    before_bytes = db_path.read_bytes()

    result, payload = _overview_json(tmp_path, monkeypatch)
    human = _run_cli(tmp_path, ["memory"], monkeypatch)

    assert result.exit_code == 2, result.output
    assert payload["raw"]["data"]["reason"] == "migration_required"
    assert "migrate" in payload["raw"]["data"]["message"]
    assert human.exit_code == 2
    assert "E_SCHEMA_UNSUPPORTED" in human.output
    assert db_path.read_bytes() == before_bytes


@pytest.mark.parametrize(
    "make_db", [_legacy_db, _pre_owner_scope_db], ids=["legacy", "pre_owner_scope"]
)
def test_dashboard_memory_section_reports_migration_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_db
) -> None:
    from rush.dashboard import server as server_module
    from rush.workflows import projects as projects_module

    monkeypatch.setattr(
        projects_module, "default_data_root", lambda: tmp_path / "rush-data"
    )
    project = tmp_path / "old"
    project.mkdir()
    db_path = make_db(project)
    record = projects_module.register_project(project)
    before_bytes = db_path.read_bytes()
    before_dir = sorted(p.name for p in db_path.parent.iterdir())

    section = server_module._build_memory_section(record.project_id, {})

    assert section["store_state"] == "migration_required"
    assert "migrate" in section["store_reason"]
    assert section["items"] == []
    assert db_path.read_bytes() == before_bytes
    assert sorted(p.name for p in db_path.parent.iterdir()) == before_dir


def test_tui_memory_refresh_reports_migration_required(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from rush import tui as tui_module

    project_root = tmp_path / "old"
    project_root.mkdir()
    db_path = _legacy_db(project_root)
    before_bytes = db_path.read_bytes()
    calls: list[object] = []

    def _memory_run(*_args: object, **kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {"status": "ok", "raw": []}

    actions = tui_module.ScanActions(
        plan_scan=lambda *a, **k: SimpleNamespace(candidates=[]),
        execute_scan=lambda *a, **k: SimpleNamespace(aggregate={}),
        cancel_scan_run=lambda *a, **k: {},
        rescan_project_run=lambda *a, **k: {},
        build_handoff=lambda *a, **k: None,
        dispatch_handoff=lambda *a, **k: None,
        load_scan_events=lambda *a, **k: {"events": [], "run_state": None},
        list_agents=list,
        memory_run=_memory_run,
    )
    project = ProjectState(name="old", root=project_root)
    state = tui_module.TuiState(projects=[project])
    state.memory_query_buffer = "exact"

    tui_module._memory_refresh(state, project, actions)

    assert state.memory_message.startswith("migration_required:")
    assert state.memory_items == []
    assert calls == []
    assert db_path.read_bytes() == before_bytes


def test_dashboard_memory_query_path_is_read_only_and_finds_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R20.G8 `dashboard-tui-read-no-create`: the non-empty `query` branch of
    GET `section=memory` must not construct a writable store either."""
    from rush.dashboard import server as server_module
    from rush.workflows import projects as projects_module

    monkeypatch.setattr(
        projects_module, "default_data_root", lambda: tmp_path / "rush-data"
    )
    _, current = _fresh_and_current_projects(tmp_path)
    record = projects_module.register_project(current)
    db_path = current / ".rush" / "memory.db"
    before_hash = _sha256(db_path)
    before_dir = sorted(p.name for p in db_path.parent.iterdir())

    section = server_module._build_memory_section(
        record.project_id, {"query": ["value"], "subject": ["preference"]}
    )

    assert [item["id"] for item in section["items"]] == ["a1"]
    assert section["items"][0]["dynamic_freshness_checked"] is True
    assert _sha256(db_path) == before_hash
    assert sorted(p.name for p in db_path.parent.iterdir()) == before_dir


# =============================================================================
# Fix round 2 -- R20.G8 `dashboard-tui-read-no-create`: GET `section=memory`
# with `expand_id` / `related_id` reads through the read-only view too.
# =============================================================================

_EXPAND_RELATED_QUERIES = {
    "expand": {"expand_id": ["a1"], "expand_version": ["1"]},
    "related": {"related_id": ["a1"], "related_version": ["1"]},
}


@pytest.mark.parametrize("operation", ["expand", "related"])
def test_dashboard_expand_related_virgin_project_creates_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    from rush.dashboard import server as server_module
    from rush.workflows import projects as projects_module

    monkeypatch.setattr(
        projects_module, "default_data_root", lambda: tmp_path / "rush-data"
    )
    virgin, _ = _fresh_and_current_projects(tmp_path)
    record = projects_module.register_project(virgin)
    before = _rglob_snapshot(virgin)

    section = server_module._build_memory_section(
        record.project_id, _EXPAND_RELATED_QUERIES[operation]
    )

    assert section[operation]["raw"]["code"] == "E_NOT_VISIBLE"
    assert _rglob_snapshot(virgin) == before
    assert not (virgin / ".rush" / "memory.db").exists()


@pytest.mark.parametrize("operation", ["expand", "related"])
def test_dashboard_expand_related_current_db_byte_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    from rush.dashboard import server as server_module
    from rush.workflows import projects as projects_module

    monkeypatch.setattr(
        projects_module, "default_data_root", lambda: tmp_path / "rush-data"
    )
    _, current = _fresh_and_current_projects(tmp_path)
    record = projects_module.register_project(current)
    db_path = current / ".rush" / "memory.db"
    before_hash = _sha256(db_path)
    before_dir = sorted(p.name for p in db_path.parent.iterdir())

    section = server_module._build_memory_section(
        record.project_id, _EXPAND_RELATED_QUERIES[operation]
    )

    assert section[operation]["raw"]["code"] == "OK"
    assert _sha256(db_path) == before_hash
    assert sorted(p.name for p in db_path.parent.iterdir()) == before_dir
