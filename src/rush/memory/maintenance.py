"""Maintenance sub-agent for the typed-artifact memory store (Phase 62 §6.2).

`run_maintenance_cycle()` acquires a capability-scoped `MeshLockManager` lease before running a
bounded sweep over `memory_artifacts`, renews the lease every 50 rows, and stops with a partial
result the instant a renewal is lost (never falling back to the legacy `agent_id`-only release
path, which would let a stale cycle delete a different, live cycle's reclaimed lock).
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from rush.mcp_mesh.lock_manager import MeshLockManager
from rush.memory.expiry import reviewed_version_conflicts
from rush.memory.merkle_invalidator import MerkleInvalidator
from rush.memory.store import (
    MemoryArtifact,
    MemoryMigrationRequiredError,
    OwnerScope,
    TypedArtifactStore,
    _write_version,
    legacy_owner_scope,
    note_committed_write,
    promote_stored_artifact,
    readonly_preview_error,
)
from rush.memory.trust import count_corroboration
from rush.plugins.trust_store import PluginTrustStore

MaintenanceTask = Literal[
    "promotion_sweep", "staleness_sweep", "skill_admission_check", "expiry_sweep"
]

_LOCK_PATH = Path(".rush/memory-maintenance.lock")
_AGENT_ID = "memory-maintenance"
_RENEW_EVERY = 50

# P69-07 subsection h: every sweep is scoped by exact owner_scope (kind, id) equality --
# never a wildcard, even for a `project`-kind sweep, since a project store legitimately
# holds rows owned by other kinds too. A legacy row (owner_scope_kind/_id both NULL)
# resolves to `legacy_owner_scope(root)`, mirroring `owner_scope_for_row()`'s own
# read-time resolution in `store.py`.
_OWNER_CLAUSE = (
    "AND COALESCE(owner_scope_kind, :legacy_kind) = :owner_kind "
    "AND COALESCE(owner_scope_id, :legacy_id) = :owner_id "
)

# Each task's SELECT up to (not including) its ORDER BY, so `_select_sql()` can append
# the T28-D reviewed-candidate restriction before ordering.
_SELECT_SQL: dict[str, str] = {
    "promotion_sweep": (
        "SELECT id, family, subject, trust_tier, content, source, created_at, "
        "symbol_ref, content_hash, corroboration_count, promoted_at, stale, signature, "
        "artifact_version "
        "FROM memory_artifacts WHERE trust_tier != 'STATED' AND promoted_at IS NULL "
        + _OWNER_CLAUSE
    ),
    "staleness_sweep": (
        "SELECT id, symbol_ref, content_hash, artifact_version FROM memory_artifacts "
        "WHERE symbol_ref IS NOT NULL AND stale = 0 " + _OWNER_CLAUSE
    ),
    "skill_admission_check": (
        "SELECT id, family, subject, trust_tier, content, source, created_at, "
        "symbol_ref, content_hash, corroboration_count, promoted_at, stale, signature, "
        "artifact_version "
        "FROM memory_artifacts WHERE subject = 'skill_pattern' AND trust_tier != 'STATED' "
        "AND promoted_at IS NULL " + _OWNER_CLAUSE
    ),
}
_CANDIDATE_CLAUSE = "AND id IN (SELECT value FROM json_each(:candidate_ids)) "
_ORDER_SQL = "ORDER BY created_at ASC LIMIT :batch_size"
# Columns a preview's read-only SELECT needs; a store predating any of them must be
# migrated by a real apply first, never by a preview.
_PREVIEW_COLUMNS = {
    "artifact_version",
    "owner_scope_kind",
    "owner_scope_id",
    "expired_at",
}


def _select_rows(
    task: MaintenanceTask,
    conn: sqlite3.Connection,
    root: Path,
    *,
    owner_scope: OwnerScope,
    batch_size: int,
    candidate_ids: Collection[str] | None,
) -> list[sqlite3.Row]:
    """Rows `task` would visit: its own predicate, exactly `owner_scope`, and (when
    given) only the reviewed `candidate_ids`. A pure SELECT for writable and read-only
    connections alike."""
    legacy_default = legacy_owner_scope(root)
    params: dict[str, object] = {
        "batch_size": batch_size,
        "owner_kind": owner_scope.kind,
        "owner_id": owner_scope.id,
        "legacy_kind": legacy_default.kind,
        "legacy_id": legacy_default.id,
    }
    sql = _SELECT_SQL[task]
    if candidate_ids is not None:
        sql += _CANDIDATE_CLAUSE
        params["candidate_ids"] = json.dumps(list(candidate_ids))
    return conn.execute(sql + _ORDER_SQL, params).fetchall()


def preview_maintenance_candidates(
    task: MaintenanceTask,
    *,
    batch_size: int = 500,
    project_root: Path | None = None,
    owner_scope: OwnerScope,
    candidate_ids: Collection[str] | None = None,
) -> list[dict[str, object]]:
    """T28-D zero-write preview: the `{"id", "artifact_version"}` of every row a
    `run_maintenance_cycle()` of `task` would visit, read through
    `TypedArtifactStore.open_readonly()` -- no lock, no writable store, so no `.rush/`,
    DB, `-wal` or `-shm` is ever created and an existing DB keeps its bytes. A missing
    DB has no candidates. `expiry_sweep` uses its own TTL predicate.

    Raises `MemoryStoreUnreadableError` when the DB cannot be read without writing and
    `MemoryMigrationRequiredError` when it predates a column the sweep reads."""
    root = (project_root or Path.cwd()).resolve()
    db = root / ".rush" / "memory.db"
    opened = TypedArtifactStore.open_readonly(root)
    if opened.state is not None:
        raise readonly_preview_error(opened.state, db)
    if not opened.available:
        return []
    conn = opened.connection
    if opened.migration_required or conn is None:
        raise MemoryMigrationRequiredError(
            f"{db} predates artifact_version; run an apply-mode operation first"
        )
    try:
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(memory_artifacts)")
        }
        if not _PREVIEW_COLUMNS <= columns:
            raise MemoryMigrationRequiredError(
                f"{db} predates {sorted(_PREVIEW_COLUMNS - columns)}; run an "
                "apply-mode operation first"
            )
        if task == "expiry_sweep":
            from rush.memory.expiry import expired_candidate_rows

            rows = expired_candidate_rows(
                conn,
                root,
                owner_scope=owner_scope,
                batch_size=batch_size,
                now=time.time(),
                candidate_ids=candidate_ids,
            )
        else:
            rows = _select_rows(
                task,
                conn,
                root,
                owner_scope=owner_scope,
                batch_size=batch_size,
                candidate_ids=candidate_ids,
            )
        return [
            {"id": row["id"], "artifact_version": row["artifact_version"]}
            for row in rows
        ]
    finally:
        conn.close()


@dataclass(frozen=True)
class RevisionConflict:
    """T28-D: a reviewed candidate whose current `artifact_version` (None = row gone)
    no longer equals the version the caller reviewed; the cycle left it unchanged."""

    id: str
    expected: int
    actual: int | None


@dataclass(frozen=True)
class MaintenanceRunResult:
    task: MaintenanceTask
    processed: int
    changed: int
    errors: tuple[
        str, ...
    ] = ()  # row `id` values whose per-row mutation raised; skipped, not aborted
    refused: tuple[RevisionConflict, ...] = ()


def _revision_conflicts(
    root: Path, expected_revisions: Mapping[str, int]
) -> tuple[RevisionConflict, ...]:
    """Every reviewed id whose stored `artifact_version` differs from the reviewed one."""
    store = TypedArtifactStore(root)
    try:
        conn = sqlite3.connect(str(store.db_path))
        try:
            return tuple(
                RevisionConflict(*conflict)
                for conflict in reviewed_version_conflicts(conn, expected_revisions)
            )
        finally:
            conn.close()
    finally:
        store.close()


class _RowRefused(Exception):
    """A per-row write transaction found its row no longer at the reviewed version."""

    def __init__(self, conflict: RevisionConflict) -> None:
        super().__init__(conflict.id)
        self.conflict = conflict


def _refuse_unless_reviewed(
    conn: sqlite3.Connection, artifact_id: str, expected_version: int | None
) -> None:
    """T28-D: called right after a row's BEGIN IMMEDIATE, before any write -- rolls
    back and raises `_RowRefused` when the row is not at its reviewed version."""
    if expected_version is None:
        return
    conflicts = reviewed_version_conflicts(conn, {artifact_id: expected_version})
    if conflicts:
        conn.rollback()
        raise _RowRefused(RevisionConflict(*conflicts[0]))


def run_maintenance_cycle(
    task: MaintenanceTask,
    *,
    batch_size: int = 500,
    project_root: Path | None = None,
    owner_scope: OwnerScope,
    candidate_ids: Collection[str] | None = None,
    expected_revisions: Mapping[str, int] | None = None,
) -> MaintenanceRunResult:
    """Runs one bounded maintenance sweep under a capability-scoped lock lease (§6.2).

    P69-07 subsection h: `owner_scope` scopes the sweep to exactly that owner (kind, id)
    -- required (M09: no silent default), never a wildcard sweep across every owner in
    this project's store. Every caller (TUI, CLI, dashboard, `MemoryTool._run_maintain`)
    must resolve and pass a real owner; `legacy_owner_scope(root)` is still the right
    value to pass for an unregistered project, but it is never assumed here.

    T28-D: `candidate_ids`, when given, restricts the sweep to exactly those
    previewed rows (`preview_maintenance_candidates()`); `None` sweeps every eligible
    row as before.

    T28-D: `expected_revisions` ({id: reviewed artifact_version}), when given, is
    checked under the maintenance lease before any row is touched; every id whose
    current version differs is left unchanged and reported in `refused`, and the sweep
    visits only the remaining reviewed ids (`candidate_ids`, else the mapping's keys).
    Each version is checked again inside the write transaction that would change the
    row (the expiry sweep's single transaction, or each per-row transaction), so an
    edit committed after the first check is refused too, never changed unreviewed.
    """
    root = (project_root or Path.cwd()).resolve()
    scope = owner_scope
    lock_manager = MeshLockManager(root)
    lease = lock_manager.acquire(
        _LOCK_PATH,
        agent_id=_AGENT_ID,
        timeout_s=5.0,
        ttl_s=60.0,
        return_capability=True,
    )
    if not isinstance(lease, tuple) or not lease[0] or lease[1] is None:
        raise RuntimeError("memory-maintenance: failed to acquire maintenance lock")
    capability = lease[1]

    lock_lost = False
    try:
        refused: tuple[RevisionConflict, ...] = ()
        if expected_revisions is not None:
            refused = _revision_conflicts(root, expected_revisions)
            refused_ids = {conflict.id for conflict in refused}
            reviewed = expected_revisions if candidate_ids is None else candidate_ids
            candidate_ids = [i for i in reviewed if i not in refused_ids]
        if task == "expiry_sweep":
            from rush.memory.expiry import sweep_reviewed_expired

            changed, late_conflicts = sweep_reviewed_expired(
                root,
                batch_size=batch_size,
                owner_scope=scope,
                candidate_ids=candidate_ids,
                expected_revisions=expected_revisions,
            )
            refused_ids = {conflict.id for conflict in refused}
            refused += tuple(
                RevisionConflict(*conflict)
                for conflict in late_conflicts
                if conflict[0] not in refused_ids
            )
            return MaintenanceRunResult(
                task=task,
                processed=changed,
                changed=changed,
                errors=(),
                refused=refused,
            )

        store = TypedArtifactStore(root)
        conn = sqlite3.connect(str(store.db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = _select_rows(
                task,
                conn,
                root,
                owner_scope=scope,
                batch_size=batch_size,
                candidate_ids=candidate_ids,
            )

            processed = 0
            changed = 0
            errors: list[str] = []
            late_refused: list[RevisionConflict] = []
            for index, row in enumerate(rows, start=1):
                expected_version = (
                    None
                    if expected_revisions is None
                    else expected_revisions.get(row["id"])
                )
                try:
                    if _mutate_row(task, conn, row, root, expected_version):
                        changed += 1
                    processed += 1
                except _RowRefused as refusal:
                    late_refused.append(refusal.conflict)
                except Exception:  # noqa: BLE001 - isolate row failure, cycle continues
                    conn.rollback()
                    processed += 1
                    errors.append(row["id"])

                if index % _RENEW_EVERY == 0 and not lock_manager.renew(
                    _LOCK_PATH, capability, ttl_s=60.0
                ):
                    lock_lost = True
                    break

            return MaintenanceRunResult(
                task=task,
                processed=processed,
                changed=changed,
                errors=tuple(errors),
                refused=refused + tuple(late_refused),
            )
        finally:
            conn.close()
    finally:
        if not lock_lost:
            lock_manager.release(_LOCK_PATH, capability=capability)


def _mutate_row(
    task: MaintenanceTask,
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    root: Path,
    expected_version: int | None = None,
) -> bool:
    if task == "promotion_sweep":
        return _mutate_promotion_sweep(conn, row, root, expected_version)
    if task == "staleness_sweep":
        return _mutate_staleness_sweep(conn, row, root, expected_version)
    if task == "skill_admission_check":
        return _mutate_skill_admission_check(conn, row, root, expected_version)
    raise NotImplementedError(f"no maintenance dispatch for task {task!r}")


def _artifact_from_row(row: sqlite3.Row) -> MemoryArtifact:
    return MemoryArtifact(
        id=row["id"],
        family=row["family"],
        subject=row["subject"],
        trust_tier=row["trust_tier"],
        content=json.loads(row["content"]),
        source=row["source"],
        created_at=row["created_at"],
        symbol_ref=row["symbol_ref"],
        content_hash=row["content_hash"],
        corroboration_count=row["corroboration_count"],
        promoted_at=row["promoted_at"],
        stale=bool(row["stale"]),
        signature=row["signature"],
    )


def _candidate_sources(
    conn: sqlite3.Connection, subject: str, symbol_ref: str | None
) -> list[str]:
    rows = conn.execute(
        "SELECT source FROM memory_artifacts WHERE subject = ? AND symbol_ref IS ? "
        "AND trust_tier != 'STATED'",
        (subject, symbol_ref),
    ).fetchall()
    return [r["source"] for r in rows]


def _mutate_promotion_sweep(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    root: Path,
    expected_version: int | None = None,
) -> bool:
    artifact = _artifact_from_row(row)
    candidate_sources = _candidate_sources(conn, artifact.subject, artifact.symbol_ref)
    conn.execute("BEGIN IMMEDIATE")
    _refuse_unless_reviewed(conn, artifact.id, expected_version)
    promoted, decision = promote_stored_artifact(
        conn,
        artifact.id,
        user_stated=False,
        candidate_sources=candidate_sources,
        project_root=root,
    )
    if decision.promoted:
        conn.commit()
        note_committed_write(
            promoted.id, promoted.artifact_version, promoted.source, "promote"
        )
        return True
    recomputed_count = count_corroboration(
        artifact.subject, artifact.symbol_ref, candidate_sources
    )
    if recomputed_count != row["corroboration_count"]:
        new_version = _write_version(
            conn,
            artifact.id,
            content=artifact.content,
            source=artifact.source,
            trust_tier=artifact.trust_tier,
            expected_version=None,
        )
        conn.execute(
            "UPDATE memory_artifacts SET corroboration_count = ?, artifact_version = ? "
            "WHERE id = ?",
            (recomputed_count, new_version, artifact.id),
        )
        conn.commit()
        note_committed_write(artifact.id, new_version, artifact.source, "maintain")
        return True
    conn.commit()
    return False


def _mutate_staleness_sweep(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    root: Path,
    expected_version: int | None = None,
) -> bool:
    symbol_ref: str = row["symbol_ref"]
    path_part = symbol_ref.split("::", 1)[0]
    file_path = (root / path_part).resolve()
    try:
        current_hash = MerkleInvalidator(project_root=root).hash_content(
            file_path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError):
        current_hash = None
    if current_hash != row["content_hash"]:
        conn.execute("BEGIN IMMEDIATE")
        _refuse_unless_reviewed(conn, row["id"], expected_version)
        artifact_row = conn.execute(
            "SELECT content, source, trust_tier FROM memory_artifacts WHERE id = ?",
            (row["id"],),
        ).fetchone()
        new_version = _write_version(
            conn,
            row["id"],
            content=json.loads(artifact_row["content"]),
            source=artifact_row["source"],
            trust_tier=artifact_row["trust_tier"],
            expected_version=None,
        )
        conn.execute(
            "UPDATE memory_artifacts SET stale = 1, artifact_version = ? WHERE id = ?",
            (new_version, row["id"]),
        )
        conn.commit()
        note_committed_write(row["id"], new_version, artifact_row["source"], "maintain")
        return True
    return False


def _mutate_skill_admission_check(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    root: Path,
    expected_version: int | None = None,
) -> bool:
    artifact = _artifact_from_row(row)
    plugin_name = artifact.content.get("plugin_name")
    closure_digest = artifact.content.get("closure_digest")
    if not isinstance(plugin_name, str) or not isinstance(closure_digest, str):
        return False
    if not PluginTrustStore(repo_root=root).is_trusted(plugin_name, closure_digest):
        return False

    candidate_sources = _candidate_sources(conn, artifact.subject, artifact.symbol_ref)
    conn.execute("BEGIN IMMEDIATE")
    _refuse_unless_reviewed(conn, artifact.id, expected_version)
    promoted, decision = promote_stored_artifact(
        conn,
        artifact.id,
        user_stated=False,
        candidate_sources=candidate_sources,
        project_root=root,
    )
    conn.commit()
    if decision.promoted:
        note_committed_write(
            promoted.id, promoted.artifact_version, promoted.source, "promote"
        )
    return decision.promoted
