"""Phase 70 memory visibility tests.

T18 -- separate useful memory from bookkeeping. One read-time presentation
predicate (`rush.memory.store.is_internal_memory_source`, exact membership in
`INTERNAL_MEMORY_SOURCES`) hides the four bookkeeping sources from default
useful-memory lists and counts. `include_internal=True` restores exactly the
pre-T18 row set. Explicit retrieval (expand by ID, checkpoint restore, flight
replay, export) keeps its existing data. No schema, row or byte change.

The fixture is built from the real producers (FlightRecorder.record_event,
CheckpointJournal.save_checkpoint, migrate_checkpoint_journal,
migrate_flight_recorder) plus direct `TypedArtifactStore` writes, one real
`archive`, one direct `expired_at` stamp and one real `delete_batch`
tombstone, in a registered temp project with an isolated data root.

Live rows (12):
  internal (5): I1 flight_recorder:record_event (episodic),
                I2 checkpoint_journal:save_checkpoint (active_context),
                I3 migration:checkpoint_journal (active_context),
                I4 migration:flight_recorder (episodic),
                I5 checkpoint_journal:save_checkpoint owned by user:alice
                   (active_context)
  useful (7):   U1, U2 agent:notes (domain_knowledge),
                U3 review:finding (failure),
                U4 flight_recorder:record_event2 (episodic, similar name),
                U5 agent:x-notes owned by agent:x (preference),
                A1 agent:notes (domain_knowledge, archived),
                E1 review:finding (failure, expired)
Tombstone (1):  D1 flight_recorder:record_event (episodic), deleted.
"""

from __future__ import annotations

import base64
import gc
import hashlib
import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest

from rush.dashboard import server as server_module
from rush.dashboard.project_map import build_project_map
from rush.dashboard.server import DashboardContext
from rush.memory.checkpoint_journal import CheckpointJournal
from rush.memory.migration import migrate_checkpoint_journal, migrate_flight_recorder
from rush.memory.store import MemoryArtifact, OwnerScope, TypedArtifactStore
from rush.tools.flight_recorder import FlightRecorder
from rush.tui import ProjectState, TuiState, _memory_known_sources, _render_git_panel
from rush.workflows.projects import (
    export_project_data,
    list_project_artifacts,
    project_snapshot,
    register_project,
)

INTERNAL_SOURCES = frozenset(
    {
        "flight_recorder:record_event",
        "checkpoint_journal:save_checkpoint",
        "migration:flight_recorder",
        "migration:checkpoint_journal",
    }
)
USEFUL_LIVE_IDS = {
    "useful-dk-1",
    "useful-dk-2",
    "useful-fail-1",
    "useful-similar",
    "useful-agent-x",
}
ARCHIVED_ID = "useful-archived"
EXPIRED_ID = "useful-expired"
DELETED_ID = "deleted-internal"
ALICE_ID = "internal-alice"
USEFUL_ALL_IDS = USEFUL_LIVE_IDS | {ARCHIVED_ID, EXPIRED_ID}
USEFUL_SOURCES = [
    "agent:notes",
    "agent:x-notes",
    "flight_recorder:record_event2",
    "review:finding",
]
ALL_SOURCES = sorted(set(USEFUL_SOURCES) | INTERNAL_SOURCES)


@pytest.fixture(autouse=True)
def _isolated_data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    isolated = tmp_path / "rush-data"
    monkeypatch.setattr("rush.setup.provision.default_data_root", lambda: isolated)
    monkeypatch.setattr("rush.workflows.projects.default_data_root", lambda: isolated)
    return isolated


def _write(
    store: TypedArtifactStore,
    artifact_id: str,
    subject: Any,
    source: str,
    *,
    family: Any = "memory",
    owner: OwnerScope | None = None,
) -> MemoryArtifact:
    return store.write(
        MemoryArtifact(
            id=artifact_id,
            family=family,
            subject=subject,
            trust_tier="DERIVED",
            content={"note": artifact_id},
            source=source,
            created_at=time.time(),
            owner_scope=owner,
        )
    )


def _build_fixture(tmp_path: Path, data_root: Path) -> dict[str, Any]:
    root = (tmp_path / "proj").resolve()
    root.mkdir()
    record = register_project(root, data_root=data_root)

    recorder = FlightRecorder(root)
    recorder.record_event("sess-1", "tool_call", {"tool": "lint"})
    CheckpointJournal(root).save_checkpoint("cp-1", {"branch": "main"}, ["a.py"])
    assert migrate_checkpoint_journal(root) == 1
    assert migrate_flight_recorder(root) == 1

    store = TypedArtifactStore(root)
    _write(
        store,
        ALICE_ID,
        "active_context",
        "checkpoint_journal:save_checkpoint",
        family="handoff",
        owner=OwnerScope("user", "alice"),
    )
    _write(store, "useful-dk-1", "domain_knowledge", "agent:notes")
    _write(store, "useful-dk-2", "domain_knowledge", "agent:notes")
    _write(store, "useful-fail-1", "failure", "review:finding")
    _write(
        store,
        "useful-similar",
        "episodic",
        "flight_recorder:record_event2",
        family="experience",
    )
    _write(
        store,
        "useful-agent-x",
        "preference",
        "agent:x-notes",
        owner=OwnerScope("agent", "x"),
    )
    _write(store, ARCHIVED_ID, "domain_knowledge", "agent:notes")
    assert store.archive(
        ARCHIVED_ID, expected_version=1, scope="domain_knowledge", apply=True
    )["applied"]
    _write(store, EXPIRED_ID, "failure", "review:finding")
    now = time.time()
    with closing(sqlite3.connect(store.db_path)) as conn, conn:
        conn.execute(
            "UPDATE memory_artifacts SET expires_at = ?, expired_at = ?, "
            "expired_by = 'test' WHERE id = ?",
            (now, now, EXPIRED_ID),
        )
        conn.commit()
    _write(
        store,
        DELETED_ID,
        "episodic",
        "flight_recorder:record_event",
        family="experience",
    )
    deleted = store.delete_batch(
        [DELETED_ID], expected_revisions={DELETED_ID: 1}, scope="episodic", apply=True
    )
    assert deleted["applied"] is True

    with closing(sqlite3.connect(store.db_path)) as conn, conn:
        rows = conn.execute(
            "SELECT id, source, subject FROM memory_artifacts"
        ).fetchall()
    by_source: dict[str, list[str]] = {}
    for artifact_id, source, _subject in rows:
        by_source.setdefault(source, []).append(artifact_id)
    internal_ids = {i for s in INTERNAL_SOURCES for i in by_source.get(s, [])}
    # Fixture shape guard: exactly the rows the module docstring lists.
    assert len(rows) == 12
    assert len(internal_ids) == 5
    assert ALICE_ID in internal_ids
    assert {r[0] for r in rows} - internal_ids == USEFUL_ALL_IDS
    flight_event = next(
        r
        for r in _content_rows(store.db_path)
        if r[1] == "flight_recorder:record_event"
    )[2]
    return {
        "root": root,
        "project_id": record.project_id,
        "data_root": data_root,
        "internal_ids": internal_ids,
        "all_live_ids": {r[0] for r in rows},
        "flight_event": flight_event,
    }


def _content_rows(db_path: Path) -> list[tuple[str, str, dict[str, Any]]]:
    with closing(sqlite3.connect(db_path)) as conn, conn:
        return [
            (r[0], r[1], json.loads(r[2]))
            for r in conn.execute(
                "SELECT id, source, content FROM memory_artifacts ORDER BY id"
            )
        ]


@pytest.fixture
def fx(tmp_path: Path, _isolated_data_root: Path) -> dict[str, Any]:
    return _build_fixture(tmp_path, _isolated_data_root)


def _live_memory_ids(listing: dict[str, Any]) -> set[str]:
    return {m["id"] for m in listing["memory"] if m["deleted"] is False}


def _deleted_memory_ids(listing: dict[str, Any]) -> set[str]:
    return {m["id"] for m in listing["memory"] if m["deleted"] is True}


def _db_state(root: Path) -> dict[str, Any]:
    # TypedArtifactStore's `with self._connect()` commits but does not close;
    # the connection closes (and checkpoints its WAL) when collected. Collect
    # first so the immutable read below sees every committed byte.
    gc.collect()
    db = root / ".rush" / "memory.db"
    with sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True) as conn:
        state = {
            "sqlite_master": conn.execute(
                "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
            ).fetchall(),
            "memory_artifacts": conn.execute(
                "SELECT * FROM memory_artifacts ORDER BY id"
            ).fetchall(),
            "memory_changes": conn.execute(
                "SELECT * FROM memory_changes ORDER BY sequence"
            ).fetchall(),
            "memory_artifact_versions": conn.execute(
                "SELECT * FROM memory_artifact_versions ORDER BY artifact_id, artifact_version"
            ).fetchall(),
        }
    state["sha256"] = hashlib.sha256(db.read_bytes()).hexdigest()
    state["journal_files"] = sorted(
        p.name for p in (root / ".rush").iterdir() if p.name.startswith("memory.db-")
    )
    return state


def _render(panel: Any) -> str:
    from rich.console import Console

    console = Console(record=True, width=200, force_terminal=False)
    console.print(panel)
    return console.export_text()


# ---------------------------------------------------------------------------
# B1 -- the predicate, its constant and its SQL helper
# ---------------------------------------------------------------------------


def _case_predicate_truth_table(fx: dict[str, Any]) -> None:
    from rush.memory.store import INTERNAL_MEMORY_SOURCES, is_internal_memory_source

    assert INTERNAL_MEMORY_SOURCES == INTERNAL_SOURCES
    assert isinstance(INTERNAL_MEMORY_SOURCES, frozenset)
    for source in sorted(INTERNAL_SOURCES):
        assert is_internal_memory_source(source) is True, source
    for source in (
        "flight_recorder:record_event2",
        "migration:failure_ledger",
        "migration:preference_store",
        "migration:flight_recorder_extra",
        "checkpoint_journal:save_checkpoint:v2",
        "Flight_Recorder:record_event",
        " flight_recorder:record_event",
        "flight_recorder:record_event ",
        "flight_recorder",
        "checkpoint_journal",
        "migration:",
        "agent:notes",
        "",
    ):
        assert is_internal_memory_source(source) is False, source


def _case_sql_helper_and_useful_count(fx: dict[str, Any]) -> None:
    # Decision flagged in the T18 test receipt: the brief names neither the SQL
    # helper nor the "useful memory count" helper. These tests pin
    # `internal_source_exclusion_sql() -> (fragment, params)` and
    # `useful_memory_count(conn) -> int` (R18.1: predicate AND archived_at IS
    # NULL AND expired_at IS NULL, built from the same helper).
    from rush.memory.store import internal_source_exclusion_sql, useful_memory_count

    fragment, params = internal_source_exclusion_sql()
    assert sorted(params) == sorted(INTERNAL_SOURCES)
    db = fx["root"] / ".rush" / "memory.db"
    # Collect first so the immutable read below sees every committed byte.
    gc.collect()
    with sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True) as conn:
        kept = {
            r[0]
            for r in conn.execute(
                f"SELECT id FROM memory_artifacts WHERE {fragment}", tuple(params)
            )
        }
        assert kept == USEFUL_ALL_IDS
        assert useful_memory_count(conn) == 5


# ---------------------------------------------------------------------------
# B2/B3 -- default exclusion and diagnostic restore at every projection
# ---------------------------------------------------------------------------


def _case_project_snapshot_counts(fx: dict[str, Any]) -> None:
    snap = project_snapshot(fx["project_id"])
    memory = snap["memory"]
    # G7: key set unchanged.
    assert set(memory) == {"counts_by_subject", "deleted_count", "admin_capabilities"}
    # Non-internal rows per subject, archived and expired still counted.
    assert memory["counts_by_subject"] == {
        "domain_knowledge": 3,
        "failure": 2,
        "episodic": 1,
        "preference": 1,
    }
    # Tombstones are not memory rows and carry no source: unchanged.
    assert memory["deleted_count"] == 1


def _case_list_project_artifacts(fx: dict[str, Any]) -> None:
    default = list_project_artifacts(fx["project_id"])
    diagnostic = list_project_artifacts(fx["project_id"], include_internal=True)
    assert _live_memory_ids(default) == USEFUL_ALL_IDS
    assert _live_memory_ids(diagnostic) == fx["all_live_ids"]
    assert (
        _live_memory_ids(diagnostic) - _live_memory_ids(default) == fx["internal_ids"]
    )
    assert len(diagnostic["memory"]) - len(default["memory"]) == 5
    # Tombstone refs unchanged in both views.
    assert _deleted_memory_ids(default) == {DELETED_ID}
    assert _deleted_memory_ids(diagnostic) == {DELETED_ID}
    # The snapshot's embedded artifact listing uses the default projection.
    embedded = project_snapshot(fx["project_id"])["artifacts"]
    assert _live_memory_ids(embedded) == USEFUL_ALL_IDS


def _case_export_includes_internal(fx: dict[str, Any]) -> None:
    # R18.3: export is explicit retrieval of all project data.
    exported = export_project_data(fx["project_id"])
    artifacts = exported["snapshot"]["artifacts"]
    assert _live_memory_ids(artifacts) == fx["all_live_ids"]
    assert _deleted_memory_ids(artifacts) == {DELETED_ID}
    # B4: export output is unchanged, so its embedded counts keep internal rows.
    assert exported["snapshot"]["memory"]["counts_by_subject"] == {
        "domain_knowledge": 3,
        "failure": 2,
        "episodic": 3,
        "preference": 1,
        "active_context": 3,
    }
    assert exported["snapshot"]["memory"]["deleted_count"] == 1


def _case_snapshot_memories(fx: dict[str, Any]) -> None:
    store = TypedArtifactStore(fx["root"])
    default, gen_default = store.snapshot_memories()
    diagnostic, gen_diag = store.snapshot_memories(include_internal=True)
    assert gen_default == gen_diag
    assert {m["id"] for m in default} == USEFUL_ALL_IDS
    assert {m["id"] for m in diagnostic} == fx["all_live_ids"]
    # Archived semantics of this surface unchanged: archived row present, flagged.
    assert {m["id"] for m in default if m["archived"]} == {ARCHIVED_ID}
    assert {m["id"] for m in diagnostic if m["archived"]} == {ARCHIVED_ID}
    # Existing owner_filter keyword still narrows by exact source.
    by_source, _ = store.snapshot_memories("agent:notes")
    assert {m["id"] for m in by_source} == {"useful-dk-1", "useful-dk-2", ARCHIVED_ID}


def _case_dashboard_overview_and_map(fx: dict[str, Any]) -> None:
    pid = fx["project_id"]
    ctx = DashboardContext(
        {pid: {"root": str(fx["root"]), "name": "proj"}},
        bound_host="127.0.0.1",
        bound_port=0,
        data_root=fx["data_root"],
    )
    server_module._refresh_project_memories(ctx, pid, fx["root"])
    record = ctx.projects.get(pid)
    overview = server_module._build_overview_section(pid, record)
    assert overview["memory_count"] == 7
    project_map = build_project_map({"project_id": pid, **record.snapshot})
    memory_nodes = {
        n["artifact_id"] for n in project_map["nodes"] if n["kind"] == "memory"
    }
    assert memory_nodes == USEFUL_ALL_IDS


def _memory_section(pid: str, **params: str) -> dict[str, Any]:
    query = {k: [v] for k, v in params.items()}
    query.setdefault("limit", ["100"])
    return server_module._build_memory_section(pid, query)


def _case_dashboard_memory_section(fx: dict[str, Any]) -> None:
    pid = fx["project_id"]
    default = _memory_section(pid)
    assert default["total"] == 5
    assert {i["id"] for i in default["items"]} == USEFUL_LIVE_IDS
    assert default["known_sources"] == USEFUL_SOURCES

    diagnostic = _memory_section(pid, include_internal="true")
    # include_internal relaxes only the internal filter: archived/expired stay hidden.
    assert diagnostic["total"] == 10
    assert {i["id"] for i in diagnostic["items"]} == USEFUL_LIVE_IDS | fx[
        "internal_ids"
    ]
    assert diagnostic["known_sources"] == ALL_SOURCES

    archived_only = _memory_section(pid, include_archived="true")
    assert archived_only["total"] == 7
    assert {i["id"] for i in archived_only["items"]} == USEFUL_ALL_IDS

    everything = _memory_section(pid, include_internal="true", include_archived="true")
    assert everything["total"] == 12
    assert {i["id"] for i in everything["items"]} == fx["all_live_ids"]

    # Text query mode also honors the default exclusion.
    queried = _memory_section(pid, query="note")
    assert queried["total"] == 6
    assert {i["id"] for i in queried["items"]} == USEFUL_LIVE_IDS | {EXPIRED_ID}
    queried_diag = _memory_section(pid, query="note", include_internal="true")
    assert queried_diag["total"] == 7
    assert {i["id"] for i in queried_diag["items"]} == USEFUL_LIVE_IDS | {
        EXPIRED_ID,
        ALICE_ID,
    }


def _case_dashboard_expand_internal_by_id(fx: dict[str, Any]) -> None:
    # R18.2 / B4: expand and related by explicit ID keep the unfiltered allowlist.
    pid = fx["project_id"]
    internal_id = next(
        i
        for i, s, _c in _content_rows(fx["root"] / ".rush" / "memory.db")
        if s == "checkpoint_journal:save_checkpoint" and i != ALICE_ID
    )
    section = _memory_section(pid, expand_id=internal_id, expand_version="1")
    expand = section["expand"]
    assert expand["status"] == "ok"
    assert expand["raw"]["code"] == "OK"
    assert expand["raw"]["data"]["id"] == internal_id
    assert expand["raw"]["data"]["version"] == 1
    assert expand["raw"]["data"]["complete"] is True
    expanded = json.loads(base64.b64decode(expand["raw"]["data"]["content_base64"]))
    assert expanded["name"] == "cp-1"
    assert expanded["metadata"] == {"branch": "main"}
    related = _memory_section(pid, related_id=internal_id, related_version="1")[
        "related"
    ]
    assert related["status"] == "ok"
    assert related["raw"]["code"] == "OK"
    assert related["raw"]["data"]["items"] == []


def _case_tui_known_sources_and_counts(fx: dict[str, Any]) -> None:
    project = ProjectState(name="proj", root=fx["root"], results=[])
    assert _memory_known_sources(project) == USEFUL_SOURCES
    state = TuiState(projects=[project])
    state.git_data = project_snapshot(fx["project_id"])
    rendered = _render(_render_git_panel(state))
    # Live non-internal rows plus the tombstone (category = subject).
    assert (
        "artifacts: domain_knowledge=3, episodic=2, failure=2, preference=1" in rendered
    )
    assert "active_context" not in rendered


# ---------------------------------------------------------------------------
# B4 -- explicit restore/replay keep their authorized data
# ---------------------------------------------------------------------------


def _case_restore_and_replay(fx: dict[str, Any]) -> None:
    root = fx["root"]
    assert not (root / ".rush" / "sessions" / "cp-1.json").exists()
    restored = CheckpointJournal(root).restore_checkpoint("cp-1")
    assert restored is not None
    assert restored["name"] == "cp-1"
    assert restored["checkpoint_id"] == "cp-1"
    assert restored["status"] == "ok"
    assert restored["metadata"] == {"branch": "main"}
    assert restored["files"] == ["a.py"]
    assert not (root / ".rush" / "sessions" / "flights" / "sess-1.jsonl").exists()
    replayed = FlightRecorder(root, create=False).replay_session("sess-1")
    assert replayed == [fx["flight_event"]]
    assert replayed[0]["event_type"] == "tool_call"
    assert replayed[0]["payload"] == {"tool": "lint"}


# ---------------------------------------------------------------------------
# Read-only guarantee -- no DB, schema, row or journal change on read paths
# ---------------------------------------------------------------------------


def _case_db_unchanged(fx: dict[str, Any]) -> None:
    """Keep-green guard: every pre-existing read surface T18 touches leaves
    memory.db bytes, schema, rows and journal files unchanged."""
    root, pid = fx["root"], fx["project_id"]
    before = _db_state(root)
    assert before["journal_files"] == []

    project_snapshot(pid)
    list_project_artifacts(pid)
    export_project_data(pid)
    TypedArtifactStore(root).snapshot_memories()
    _memory_section(pid)
    _memory_section(pid, include_archived="true")
    _memory_known_sources(ProjectState(name="proj", root=root, results=[]))
    CheckpointJournal(root).restore_checkpoint("cp-1")
    FlightRecorder(root, create=False).replay_session("sess-1")

    assert _db_state(root) == before


def _case_db_unchanged_diagnostic(fx: dict[str, Any]) -> None:
    """The new predicate, SQL helper and include_internal paths are reads too."""
    from rush.memory.store import (
        internal_source_exclusion_sql,
        is_internal_memory_source,
        useful_memory_count,
    )

    root, pid = fx["root"], fx["project_id"]
    before = _db_state(root)
    assert before["journal_files"] == []

    assert is_internal_memory_source("flight_recorder:record_event") is True
    fragment, params = internal_source_exclusion_sql()
    db = root / ".rush" / "memory.db"
    with sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True) as conn:
        conn.execute(f"SELECT id FROM memory_artifacts WHERE {fragment}", tuple(params))
        useful_memory_count(conn)
    list_project_artifacts(pid, include_internal=True)
    TypedArtifactStore(root).snapshot_memories(include_internal=True)
    _memory_section(pid, include_internal="true")
    _memory_section(pid, include_internal="true", include_archived="true")

    assert _db_state(root) == before


CASES = {
    "predicate": _case_predicate_truth_table,
    "sql_helper_useful_count": _case_sql_helper_and_useful_count,
    "project_snapshot_counts": _case_project_snapshot_counts,
    "list_project_artifacts": _case_list_project_artifacts,
    "export_includes_internal": _case_export_includes_internal,
    "snapshot_memories": _case_snapshot_memories,
    "dashboard_overview_map": _case_dashboard_overview_and_map,
    "dashboard_memory_section": _case_dashboard_memory_section,
    "dashboard_expand_internal": _case_dashboard_expand_internal_by_id,
    "tui_sources_counts": _case_tui_known_sources_and_counts,
    "restore_replay": _case_restore_and_replay,
    "db_unchanged": _case_db_unchanged,
    "db_unchanged_diagnostic": _case_db_unchanged_diagnostic,
}


@pytest.mark.parametrize("case", list(CASES))
def test_t18_bookkeeping_projection(case: str, fx: dict[str, Any]) -> None:
    CASES[case](fx)
