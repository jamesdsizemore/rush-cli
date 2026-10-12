"""Maintenance sub-agent for the typed-artifact memory store (Phase 62 §6.2).

`run_maintenance_cycle()` runs one bounded sweep over `memory_artifacts` for a resolved
write `MemoryAccess` (72-T04 D9/D26) in two stages:

- Stage 1 (no policy lock, lease or write transaction): revision check, owner- and
  source-scoped selection, and per-row preparation (contained source hashes, plugin
  closure digests).
- Stage 2: under the policy lock, bounded by `POLICY_LOCK_HOLD_BUDGET_S`, a
  capability-scoped `MeshLockManager` lease; each row commits in its own write
  transaction after the lease is renewed and the access rechecked. A lost lease stops
  the cycle with `lock_lost` and the unprocessed ids (never releasing a lease that is
  no longer ours).
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import time
from collections.abc import Callable, Collection, Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, get_args

from rush.mcp_mesh.capabilities import LockCapabilityInput
from rush.mcp_mesh.lock_manager import MeshLockManager
from rush.memory import trust
from rush.memory.authorization import hold_policy_lock
from rush.memory.expiry import reviewed_version_conflicts
from rush.memory.retrieval import MemoryAccess, recheck_failure
from rush.memory.store import (
    MemoryArtifact,
    MemoryMigrationRequiredError,
    TypedArtifactStore,
    VersionConflictError,
    _write_version,
    decode_content,
    legacy_owner_scope,
    note_committed_write,
    payload_mismatched,
    promote_stored_artifact,
    readonly_preview_error,
    source_predicate_sql,
    sqlite_text,
)
from rush.plugins.trust_store import PluginTrustStore

MaintenanceTask = Literal[
    "promotion_sweep", "staleness_sweep", "skill_admission_check", "expiry_sweep"
]

_LOCK_PATH = Path(".rush/memory-maintenance.lock")
_AGENT_ID = "memory-maintenance"
# D26: the longest stage 2 holds the policy lock.
POLICY_LOCK_HOLD_BUDGET_S = 10.0
_MAX_BATCH = 1000

# P69-07 subsection h / D9: every sweep is scoped by exact owner_scope (kind, id)
# equality -- never a wildcard. A legacy row (owner_scope_kind/_id both NULL) resolves
# to `legacy_owner_scope(root)`, mirroring `owner_scope_for_row()` in `store.py`.
_OWNER_CLAUSE = (
    "AND COALESCE(owner_scope_kind, ?) = ? AND COALESCE(owner_scope_id, ?) = ? "
)
# D9/D8: a row that may still be promoted by agreement (never STATED or IMPORTED,
# never archived, expired, past `expires_at`, or a consolidated summary, D6).
_PROMOTABLE = (
    "trust_tier NOT IN ('STATED', 'IMPORTED') AND promoted_at IS NULL "
    "AND archived_at IS NULL AND expired_at IS NULL "
    "AND (expires_at IS NULL OR expires_at > ?) "
    "AND COALESCE(json_extract(CASE WHEN json_valid(content) THEN content END, "
    "'$.kind'), '') != 'consolidated_episode_summary' "
)
_CANDIDATE_CLAUSE = "AND id IN (SELECT value FROM json_each(?)) "
_ORDER_SQL = "ORDER BY created_at ASC LIMIT ?"
# Columns a preview's read-only SELECT needs; a store predating any of them must be
# migrated by a real apply first, never by a preview.
_PREVIEW_COLUMNS = {
    "artifact_version",
    "owner_scope_kind",
    "owner_scope_id",
    "expired_at",
    "expires_at",
    "archived_at",
}
_HEX = frozenset("0123456789abcdef")


class MaintenanceAccessDenied(Exception):
    """The access does not (or no longer) authorize the cycle; `unprocessed` names
    the selected ids left unchanged."""

    def __init__(
        self, code: str, reason: str, *, unprocessed: tuple[str, ...] = ()
    ) -> None:
        super().__init__(f"{code}: {reason}")
        self.code = code
        self.reason = reason
        self.unprocessed = tuple(unprocessed)


class MaintenanceLeaseLost(Exception):
    """The maintenance lease could not be renewed before a commit."""

    def __init__(self, unprocessed: tuple[str, ...] = ()) -> None:
        super().__init__("memory-maintenance: lease lost")
        self.unprocessed = tuple(unprocessed)


@dataclass(frozen=True)
class _Prepared:
    """Stage-1 evidence for one selected row."""

    artifact_version: int
    current_hash: str | None = None
    closure_digest: str | None = None


class _RowDrifted(Exception):
    """The row changed between preparation and its write transaction."""


def _validate(task: object, batch_size: object) -> None:
    if task not in get_args(MaintenanceTask):
        raise ValueError(f"unknown maintenance task {task!r}")
    if type(batch_size) is not int or not 1 <= batch_size <= _MAX_BATCH:
        raise ValueError(f"batch_size must be an int in 1..{_MAX_BATCH}")


def _select_rows(
    task: MaintenanceTask,
    conn: sqlite3.Connection,
    root: Path,
    *,
    access: MemoryAccess,
    batch_size: int,
    candidate_ids: Collection[str] | None,
    now: float | None = None,
) -> list[sqlite3.Row]:
    """Rows `task` would visit: its own predicate, exactly the access owner, only
    sources the access grants (D40), and (when given) only the reviewed
    `candidate_ids`. A pure SELECT for writable and read-only connections alike."""
    now = time.time() if now is None else now
    legacy = legacy_owner_scope(root)
    owner = access.owner_scope or legacy
    params: list[object] = []
    if task == "staleness_sweep":
        predicate = "symbol_ref IS NOT NULL AND stale = 0 AND archived_at IS NULL "
    else:
        predicate = _PROMOTABLE
        params.append(now)
        if task == "skill_admission_check":
            predicate = "subject = 'skill_pattern' AND " + predicate
    granted, granted_params = source_predicate_sql("source", access.sources)
    sql = (
        f"SELECT * FROM memory_artifacts WHERE {predicate}{_OWNER_CLAUSE}AND {granted} "
    )
    params += [legacy.kind, owner.kind, legacy.id, owner.id, *granted_params]
    if candidate_ids is not None:
        sql += _CANDIDATE_CLAUSE
        params.append(json.dumps(list(candidate_ids)))
    params.append(batch_size)
    return conn.execute(sql + _ORDER_SQL, params).fetchall()


def preview_maintenance_candidates(
    task: MaintenanceTask,
    *,
    access: MemoryAccess,
    batch_size: int = 500,
    project_root: Path | None = None,
    candidate_ids: Collection[str] | None = None,
    data_root: Path | None = None,
) -> list[dict[str, object]]:
    """T28-D zero-write preview: the `{"id", "artifact_version"}` of every row a
    `run_maintenance_cycle()` of `task` would visit for `access`, read through
    `TypedArtifactStore.open_readonly()` -- no lock, no writable store, so no `.rush/`,
    DB, `-wal` or `-shm` is ever created. A missing DB has no candidates. Other
    owners' and ungranted sources' ids are never listed.

    Raises `ValueError` for an unknown task or out-of-range `batch_size`,
    `MaintenanceAccessDenied` when the access no longer holds after selection,
    `MemoryStoreUnreadableError` when the DB cannot be read without writing and
    `MemoryMigrationRequiredError` when it predates a column the sweep reads."""
    _validate(task, batch_size)
    if data_root is not None and data_root != access.data_root:
        raise ValueError("data_root differs from the access data root")
    root = (project_root or Path.cwd()).resolve()
    db = root / ".rush" / "memory.db"
    opened = TypedArtifactStore.open_readonly(root)
    if opened.state is not None:
        raise readonly_preview_error(opened.state, db)
    rows: list[sqlite3.Row] = []
    if opened.available:
        conn = opened.connection
        if opened.migration_required or conn is None:
            raise MemoryMigrationRequiredError(
                f"{db} predates artifact_version; run an apply-mode operation first"
            )
        try:
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(memory_artifacts)")
            }
            if not _PREVIEW_COLUMNS <= columns:
                raise MemoryMigrationRequiredError(
                    f"{db} predates {sorted(_PREVIEW_COLUMNS - columns)}; run an "
                    "apply-mode operation first"
                )
            if task == "expiry_sweep":
                from rush.memory.expiry import expired_candidate_rows

                rows = list(
                    expired_candidate_rows(
                        conn,
                        root,
                        access=access,
                        batch_size=batch_size,
                        now=time.time(),
                        candidate_ids=candidate_ids,
                    )
                )
            else:
                rows = _select_rows(
                    task,
                    conn,
                    root,
                    access=access,
                    batch_size=batch_size,
                    candidate_ids=candidate_ids,
                )
        finally:
            conn.close()
    failure = recheck_failure(access)
    if failure is not None:
        raise MaintenanceAccessDenied(*failure, unprocessed=())
    return [
        {"id": row["id"], "artifact_version": row["artifact_version"]} for row in rows
    ]


@dataclass(frozen=True)
class RevisionConflict:
    """T28-D: a reviewed candidate whose current `artifact_version` (None = row gone
    or outside the access scope, `reason="not_visible"`) no longer equals the version
    the caller reviewed; the cycle left it unchanged."""

    id: str
    expected: int
    actual: int | None
    reason: str | None = None


@dataclass(frozen=True)
class MaintenanceRunResult:
    task: MaintenanceTask
    processed: int
    changed: int
    errors: tuple[
        str, ...
    ] = ()  # row `id` values whose per-row mutation raised; skipped, not aborted
    refused: tuple[RevisionConflict, ...] = ()
    lock_lost: bool = False
    # selected ids left unchanged (lease lost, hold budget spent, write lock busy,
    # or the row changed after preparation), in selection order
    unprocessed: tuple[str, ...] = ()


def _conflict(found: tuple[str, int, int | None]) -> RevisionConflict:
    cid, expected, actual = found
    return RevisionConflict(
        cid, expected, actual, "not_visible" if actual is None else None
    )


def _revision_conflicts(
    conn: sqlite3.Connection,
    expected_revisions: Mapping[str, int],
    *,
    access: MemoryAccess,
    root: Path,
) -> tuple[RevisionConflict, ...]:
    """Every reviewed id whose stored `artifact_version` differs from the reviewed one;
    a row outside the access owner/source scope reads as absent."""
    return tuple(
        _conflict(found)
        for found in reviewed_version_conflicts(
            conn, expected_revisions, access=access, project_root=root
        )
    )


class _RowRefused(Exception):
    """A per-row write transaction found its row no longer at the reviewed version."""

    def __init__(self, conflict: RevisionConflict) -> None:
        super().__init__(conflict.id)
        self.conflict = conflict


def _refuse_unless_reviewed(
    conn: sqlite3.Connection,
    artifact_id: str,
    expected_version: int | None,
    *,
    access: MemoryAccess,
    root: Path,
) -> None:
    """T28-D: called right after a row's BEGIN IMMEDIATE, before any write -- rolls
    back and raises `_RowRefused` when the row is not at its reviewed version."""
    if expected_version is None:
        return
    conflicts = reviewed_version_conflicts(
        conn, {artifact_id: expected_version}, access=access, project_root=root
    )
    if conflicts:
        conn.rollback()
        raise _RowRefused(_conflict(conflicts[0]))


def _prepare(task: MaintenanceTask, row: sqlite3.Row, root: Path) -> _Prepared:
    """Stage-1 evidence, read with no lock held."""
    version = int(row["artifact_version"])
    if task == "staleness_sweep":
        return _Prepared(version, current_hash=_current_hash(root, row["symbol_ref"]))
    if task == "skill_admission_check":
        try:
            content = decode_content(row["content"])
        except (ValueError, TypeError, RecursionError):
            return _Prepared(version)
        digest = content.get("closure_digest") if isinstance(content, dict) else None
        return _Prepared(version, closure_digest=_resolve_digest(root, digest))
    return _Prepared(version)


def _current_hash(root: Path, symbol_ref: str) -> str | None:
    """SHA-256 of the anchor file read through the contained-source reader; any
    refused, unreadable or non-UTF-8 source is `None` (the row reads stale)."""
    try:
        text = trust.read_contained_source(root, symbol_ref.split("::", 1)[0])
    except (OSError, UnicodeError, ValueError):
        return None
    return None if text is None else hashlib.sha256(text.encode("utf-8")).hexdigest()


def _resolve_digest(root: Path, value: object) -> str | None:
    """A 64-hex closure digest as-is; a path-form value hashed; else not admitted."""
    if not isinstance(value, str):
        return None
    if len(value) == 64 and set(value) <= _HEX:
        return value
    try:
        if Path(value).is_file():
            return PluginTrustStore(repo_root=root)._compute_sha256(Path(value))
    except (OSError, ValueError):
        return None
    return None


def run_maintenance_cycle(
    task: MaintenanceTask,
    *,
    access: MemoryAccess,
    batch_size: int = 500,
    project_root: Path | None = None,
    candidate_ids: Collection[str] | None = None,
    expected_revisions: Mapping[str, int] | None = None,
    data_root: Path | None = None,
) -> MaintenanceRunResult:
    """Runs one bounded maintenance sweep for a resolved write `access` (§6.2, D9).

    `access` decides the owner (exactly `access.owner_scope`, the legacy owner when
    it is `None`) and the sources (D40) every selected row, peer and revision lookup
    is scoped to. A preview (non-write) access is refused before any effect.

    T28-D: `candidate_ids`, when given, restricts the sweep to exactly those
    previewed rows; `expected_revisions` ({id: reviewed artifact_version}) refuses
    every changed or out-of-scope id (reported in `refused`) and is checked again
    inside each write transaction.

    D26: stage 2 holds the policy lock for at most `POLICY_LOCK_HOLD_BUDGET_S`; rows
    it could not reach are returned in `unprocessed`, never in `errors`.
    """
    _validate(task, batch_size)
    if data_root is not None and data_root != access.data_root:
        raise ValueError("data_root differs from the access data root")
    from rush.memory import retrieval

    if not retrieval.is_write_access(access):
        raise MaintenanceAccessDenied(
            "E_PERMISSION",
            "policy_grant_required",
            unprocessed=tuple(candidate_ids or ()),
        )
    root = (project_root or Path.cwd()).resolve()

    # Stage 1: no policy lock, lease or write transaction.
    store = TypedArtifactStore(root)
    conn = sqlite3.connect(str(store.db_path))
    conn.text_factory = sqlite_text
    conn.row_factory = sqlite3.Row
    capability: LockCapabilityInput | None = None
    lock_manager = MeshLockManager(root)
    lock_lost = False
    try:
        refused: tuple[RevisionConflict, ...] = ()
        if expected_revisions is not None:
            refused = _revision_conflicts(
                conn, expected_revisions, access=access, root=root
            )
            refused_ids = {conflict.id for conflict in refused}
            reviewed = expected_revisions if candidate_ids is None else candidate_ids
            candidate_ids = [i for i in reviewed if i not in refused_ids]
        prepared: list[tuple[sqlite3.Row, _Prepared]] = []
        if task != "expiry_sweep":
            rows = _select_rows(
                task,
                conn,
                root,
                access=access,
                batch_size=batch_size,
                candidate_ids=candidate_ids,
            )
            conn.commit()
            prepared = [(row, _prepare(task, row, root)) for row in rows]

        # Stage 2: policy lock (bounded hold) -> lease -> per-row write transactions.
        with hold_policy_lock(data_root=access.data_root):
            deadline = time.monotonic() + POLICY_LOCK_HOLD_BUDGET_S
            lease = lock_manager.acquire(
                _LOCK_PATH,
                agent_id=_AGENT_ID,
                timeout_s=min(5.0, max(deadline - time.monotonic(), 0.0)),
                ttl_s=60.0,
                return_capability=True,
            )
            if not isinstance(lease, tuple) or not lease[0] or lease[1] is None:
                raise RuntimeError(
                    "memory-maintenance: failed to acquire maintenance lock"
                )
            capability = lease[1]
            failure = recheck_failure(access)
            if failure is not None:
                raise MaintenanceAccessDenied(
                    *failure, unprocessed=tuple(candidate_ids or ())
                )
            conn.set_progress_handler(
                lambda: 1 if time.monotonic() > deadline else 0, 1000
            )
            try:
                if task == "expiry_sweep":
                    result = _run_expiry(
                        conn,
                        access=access,
                        lock_manager=lock_manager,
                        capability=capability,
                        deadline=deadline,
                        batch_size=batch_size,
                        candidate_ids=candidate_ids,
                        expected_revisions=expected_revisions,
                        refused=refused,
                    )
                else:
                    result = _run_rows(
                        task,
                        conn,
                        prepared,
                        store=store,
                        access=access,
                        lock_manager=lock_manager,
                        capability=capability,
                        deadline=deadline,
                        expected_revisions=expected_revisions,
                        refused=refused,
                    )
            finally:
                conn.set_progress_handler(None, 0)
            lock_lost = result.lock_lost
        return result
    finally:
        conn.close()
        store.close()
        if capability is not None and not lock_lost:
            # A cleanup failure never masks the cycle's own result or refusal.
            with suppress(OSError):
                lock_manager.release(_LOCK_PATH, capability=capability)


def _remaining(deadline: float) -> float:
    return deadline - time.monotonic()


def _renewer(
    lock_manager: MeshLockManager, capability: LockCapabilityInput, deadline: float
) -> Callable[[], bool]:
    def renew() -> bool:
        return bool(
            lock_manager.renew(
                _LOCK_PATH,
                capability,
                ttl_s=60.0,
                timeout_s=min(5.0, max(_remaining(deadline), 0.0)),
            )
        )

    return renew


def _busy_or_interrupted(exc: sqlite3.OperationalError) -> bool:
    message = str(exc).lower()
    return "locked" in message or "interrupted" in message


def _run_rows(
    task: MaintenanceTask,
    conn: sqlite3.Connection,
    prepared: list[tuple[sqlite3.Row, _Prepared]],
    *,
    store: TypedArtifactStore,
    access: MemoryAccess,
    lock_manager: MeshLockManager,
    capability: LockCapabilityInput,
    deadline: float,
    expected_revisions: Mapping[str, int] | None,
    refused: tuple[RevisionConflict, ...],
) -> MaintenanceRunResult:
    renew = _renewer(lock_manager, capability, deadline)
    ids = [row["id"] for row, _ in prepared]
    processed = 0
    changed = 0
    errors: list[str] = []
    late_refused: list[RevisionConflict] = []
    unprocessed: list[str] = []
    lock_lost = False
    for index, (row, evidence) in enumerate(prepared):
        tail = ids[index:]
        remaining = _remaining(deadline)
        if remaining <= 0:
            unprocessed += tail
            break
        expected_version = (
            None if expected_revisions is None else expected_revisions.get(row["id"])
        )
        try:
            conn.execute(f"PRAGMA busy_timeout = {max(int(remaining * 1000), 1)}")
            if _mutate_row(
                task,
                conn,
                row,
                store=store,
                access=access,
                renew=renew,
                deadline=deadline,
                prepared=evidence,
                expected_version=expected_version,
            ):
                changed += 1
            processed += 1
        except _RowRefused as refusal:
            late_refused.append(refusal.conflict)
        except _RowDrifted:
            conn.rollback()
            unprocessed.append(row["id"])
        except MaintenanceLeaseLost:
            conn.rollback()
            lock_lost = True
            unprocessed += tail
            break
        except MaintenanceAccessDenied as denied:
            conn.rollback()
            raise MaintenanceAccessDenied(
                denied.code, denied.reason, unprocessed=(*unprocessed, *tail)
            ) from denied
        except TimeoutError:
            conn.set_progress_handler(None, 0)
            conn.rollback()
            unprocessed += tail
            break
        except sqlite3.OperationalError as exc:
            if not _busy_or_interrupted(exc):
                conn.rollback()
                processed += 1
                errors.append(row["id"])
                continue
            conn.set_progress_handler(None, 0)
            conn.rollback()
            unprocessed += tail
            break
        except VersionConflictError as exc:
            conn.rollback()
            processed += 1
            if exc.code != "E_NOT_VISIBLE":
                errors.append(row["id"])
        except Exception:  # noqa: BLE001 - isolate row failure, cycle continues
            conn.rollback()
            processed += 1
            errors.append(row["id"])
    return MaintenanceRunResult(
        task=task,
        processed=processed,
        changed=changed,
        errors=tuple(errors),
        refused=refused + tuple(late_refused),
        lock_lost=lock_lost,
        unprocessed=tuple(unprocessed),
    )


def _run_expiry(
    conn: sqlite3.Connection,
    *,
    access: MemoryAccess,
    lock_manager: MeshLockManager,
    capability: LockCapabilityInput,
    deadline: float,
    batch_size: int,
    candidate_ids: Collection[str] | None,
    expected_revisions: Mapping[str, int] | None,
    refused: tuple[RevisionConflict, ...],
) -> MaintenanceRunResult:
    """D26: the expiry sweep is one batch transaction; the lease is renewed and the
    access rechecked once, immediately before its commit."""
    from rush.memory.expiry import _sweep_reviewed_expired

    renew = _renewer(lock_manager, capability, deadline)

    def renew_batch(batch_ids: Collection[str]) -> None:
        batch = tuple(batch_ids)
        if not renew():
            raise MaintenanceLeaseLost(batch)
        failure = recheck_failure(access)
        if failure is not None:
            raise MaintenanceAccessDenied(*failure, unprocessed=batch)
        if _remaining(deadline) <= 0:
            raise TimeoutError("memory-maintenance: policy lock hold budget spent")

    conn.execute(f"PRAGMA busy_timeout = {max(int(_remaining(deadline) * 1000), 1)}")
    reviewed = tuple(candidate_ids or ())
    try:
        changed, late_conflicts = _sweep_reviewed_expired(
            conn,
            access=access,
            renew=renew_batch,
            batch_size=batch_size,
            candidate_ids=candidate_ids,
            expected_revisions=expected_revisions,
        )
    except MaintenanceLeaseLost as lost:
        conn.rollback()
        return MaintenanceRunResult(
            task="expiry_sweep",
            processed=0,
            changed=0,
            refused=refused,
            lock_lost=True,
            unprocessed=lost.unprocessed,
        )
    except MaintenanceAccessDenied:
        conn.rollback()
        raise
    except (TimeoutError, sqlite3.OperationalError) as exc:
        if isinstance(exc, sqlite3.OperationalError) and not _busy_or_interrupted(exc):
            raise
        conn.set_progress_handler(None, 0)
        conn.rollback()
        return MaintenanceRunResult(
            task="expiry_sweep",
            processed=0,
            changed=0,
            refused=refused,
            unprocessed=reviewed,
        )
    refused_ids = {conflict.id for conflict in refused}
    refused += tuple(
        _conflict(conflict)
        for conflict in late_conflicts
        if conflict[0] not in refused_ids
    )
    return MaintenanceRunResult(
        task="expiry_sweep",
        processed=changed,
        changed=changed,
        errors=(),
        refused=refused,
    )


def _mutate_row(
    task: MaintenanceTask,
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    store: TypedArtifactStore,
    access: MemoryAccess,
    renew: Callable[[], bool],
    deadline: float = math.inf,
    prepared: _Prepared | None = None,
    expected_version: int | None = None,
) -> bool:
    if task == "promotion_sweep":
        mutate = _mutate_promotion_sweep
    elif task == "staleness_sweep":
        mutate = _mutate_staleness_sweep
    elif task == "skill_admission_check":
        mutate = _mutate_skill_admission_check
    else:
        raise NotImplementedError(f"no maintenance dispatch for task {task!r}")
    return mutate(
        conn,
        row,
        store=store,
        access=access,
        renew=renew,
        deadline=deadline,
        expected_version=expected_version,
        prepared=prepared,
    )


def _finish_row(
    conn: sqlite3.Connection,
    row_id: str,
    *,
    access: MemoryAccess,
    renew: Callable[[], bool],
    deadline: float,
) -> None:
    """D26: renew the lease, recheck the access and the hold budget, then commit."""
    if not renew():
        conn.rollback()
        raise MaintenanceLeaseLost((row_id,))
    failure = recheck_failure(access)
    if failure is not None:
        conn.rollback()
        raise MaintenanceAccessDenied(*failure, unprocessed=(row_id,))
    if time.monotonic() > deadline:
        conn.rollback()
        raise TimeoutError("memory-maintenance: policy lock hold budget spent")
    conn.commit()


def _begin_row(
    conn: sqlite3.Connection,
    row_id: str,
    *,
    access: MemoryAccess,
    root: Path,
    expected_version: int | None,
    prepared: _Prepared | None,
) -> sqlite3.Row | None:
    """BEGIN IMMEDIATE, the reviewed-version check, and the row re-read under the
    write lock (72-T01 J2); `None` when the row is gone (rolled back)."""
    conn.execute("BEGIN IMMEDIATE")
    _refuse_unless_reviewed(conn, row_id, expected_version, access=access, root=root)
    current: sqlite3.Row | None = conn.execute(
        "SELECT * FROM memory_artifacts WHERE id = ?", (row_id,)
    ).fetchone()
    if current is None:
        conn.rollback()
        return None
    if (
        prepared is not None
        and prepared.artifact_version != current["artifact_version"]
    ):
        conn.rollback()
        raise _RowDrifted(row_id)
    return current


def _artifact_from_row(row: sqlite3.Row) -> MemoryArtifact:
    return MemoryArtifact(
        id=row["id"],
        family=row["family"],
        subject=row["subject"],
        trust_tier=row["trust_tier"],
        content=decode_content(row["content"]),
        source=row["source"],
        created_at=row["created_at"],
        symbol_ref=row["symbol_ref"],
        content_hash=row["content_hash"],
        corroboration_count=row["corroboration_count"],
        promoted_at=row["promoted_at"],
        stale=bool(row["stale"]),
        signature=row["signature"],
    )


def _mutate_promotion_sweep(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    store: TypedArtifactStore,
    access: MemoryAccess,
    renew: Callable[[], bool],
    deadline: float = math.inf,
    expected_version: int | None = None,
    prepared: _Prepared | None = None,
) -> bool:
    current = _begin_row(
        conn,
        row["id"],
        access=access,
        root=store.project_root,
        expected_version=expected_version,
        prepared=prepared,
    )
    if current is None:
        return False
    # R8: decode inside the row, so an undecodable row is an isolated row error.
    artifact = _artifact_from_row(current)
    promoted, decision = promote_stored_artifact(
        conn, artifact.id, store=store, access=access, user_stated=False
    )
    if decision.promoted:
        _finish_row(conn, artifact.id, access=access, renew=renew, deadline=deadline)
        note_committed_write(
            promoted.id, promoted.artifact_version, promoted.source, "promote"
        )
        return True
    # D8: persist the shared decision's count; 72-T01 F1: a payload-mismatched row is
    # never rewritten (or re-bound) here.
    count = decision.corroboration_count
    if (
        count != current["corroboration_count"]
        and decision.denial_reason != "integrity_payload_mismatch"
    ):
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
            (count, new_version, artifact.id),
        )
        _finish_row(conn, artifact.id, access=access, renew=renew, deadline=deadline)
        note_committed_write(artifact.id, new_version, artifact.source, "maintain")
        return True
    _finish_row(conn, artifact.id, access=access, renew=renew, deadline=deadline)
    return False


def _mutate_staleness_sweep(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    store: TypedArtifactStore,
    access: MemoryAccess,
    renew: Callable[[], bool],
    deadline: float = math.inf,
    expected_version: int | None = None,
    prepared: _Prepared | None = None,
) -> bool:
    current_hash = (
        prepared.current_hash
        if prepared is not None
        else _current_hash(store.project_root, row["symbol_ref"])
    )
    if current_hash == row["content_hash"]:
        return False
    current = _begin_row(
        conn,
        row["id"],
        access=access,
        root=store.project_root,
        expected_version=expected_version,
        prepared=prepared,
    )
    if current is None:
        return False
    if payload_mismatched(current["content"], current["payload_hash"]):
        # 72-T01 F1: a payload-mismatched row is never rewritten (or re-bound).
        _finish_row(conn, row["id"], access=access, renew=renew, deadline=deadline)
        return False
    new_version = _write_version(
        conn,
        row["id"],
        content=decode_content(current["content"]),
        source=current["source"],
        trust_tier=current["trust_tier"],
        expected_version=None,
    )
    conn.execute(
        "UPDATE memory_artifacts SET stale = 1, artifact_version = ? WHERE id = ?",
        (new_version, row["id"]),
    )
    _finish_row(conn, row["id"], access=access, renew=renew, deadline=deadline)
    note_committed_write(row["id"], new_version, current["source"], "maintain")
    return True


def _mutate_skill_admission_check(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    store: TypedArtifactStore,
    access: MemoryAccess,
    renew: Callable[[], bool],
    deadline: float = math.inf,
    expected_version: int | None = None,
    prepared: _Prepared | None = None,
) -> bool:
    """D26: plugin-trust lock -> BEGIN IMMEDIATE -> trust check -> peer scan, so a
    trust revocation can never land between the check and the commit."""
    from rush.dashboard.state import cross_process_project_lock

    root = store.project_root
    artifact = _artifact_from_row(row)
    plugin_name = artifact.content.get("plugin_name")
    digest = (
        prepared.closure_digest
        if prepared is not None
        else _resolve_digest(root, artifact.content.get("closure_digest"))
    )
    if not isinstance(plugin_name, str) or digest is None:
        return False
    trust_store = PluginTrustStore(repo_root=root)
    remaining = _remaining(deadline)
    with cross_process_project_lock(
        "plugin-trust:" + str(trust_store.ledger_path),
        data_root=None,
        timeout_s=None if math.isinf(remaining) else max(remaining, 0.0),
    ):
        current = _begin_row(
            conn,
            artifact.id,
            access=access,
            root=root,
            expected_version=expected_version,
            prepared=prepared,
        )
        if current is None:
            return False
        if not trust_store.is_trusted(plugin_name, digest):
            conn.rollback()
            return False
        promoted, decision = promote_stored_artifact(
            conn, artifact.id, store=store, access=access, user_stated=False
        )
        _finish_row(conn, artifact.id, access=access, renew=renew, deadline=deadline)
    if decision.promoted:
        note_committed_write(
            promoted.id, promoted.artifact_version, promoted.source, "promote"
        )
    return decision.promoted
