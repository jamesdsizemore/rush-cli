"""Per-type expiry policy and sweep (Phase 62 §6.3).

The private `_sweep_reviewed_expired()` runs only as the `"expiry_sweep"` `MaintenanceTask`
(`src/rush/memory/maintenance.py`, 72-T04 D9: under the cycle's access, policy lock and
lease), stamping `expires_at`/`expired_at`/`expired_by` on rows whose TTL has elapsed — never
silently recomputed on read (matches Phase 61's own invariant-writing style:
`TypedArtifactStore.recall()` never mutates the DB).
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from rush.memory.store import (
    OwnerScope,
    _content_or_none,
    _write_version,
    legacy_owner_scope,
    note_committed_write,
    source_predicate_sql,
)

if TYPE_CHECKING:
    from rush.memory.retrieval import MemoryAccess

_DAY_SECONDS = 86400


@dataclass(frozen=True)
class ExpiryPolicy:
    subject: str
    trust_tier: str
    ttl_seconds: int | None  # None = never expires


DEFAULT_POLICIES: tuple[ExpiryPolicy, ...] = (
    ExpiryPolicy(subject="*", trust_tier="STATED", ttl_seconds=None),
    # Resolved (§6.3) — the synthesis doc named no duration, so rush needed its own rationale
    # per P62.7.1's escape hatch. Grounded in this codebase's own precedent for "how long does
    # non-authoritative data stay relevant": src/rush/hotspots/time_decay.py:12's
    # `half_life_days: float = 90.0` for git-commit-churn weighting. Tiered by trust confidence,
    # shortest for the least-vetted tier.
    ExpiryPolicy(subject="*", trust_tier="DERIVED", ttl_seconds=14 * _DAY_SECONDS),
    ExpiryPolicy(
        subject="*", trust_tier="EXTERNAL_WRITE", ttl_seconds=30 * _DAY_SECONDS
    ),
    ExpiryPolicy(subject="*", trust_tier="IMPORTED", ttl_seconds=90 * _DAY_SECONDS),
)


def _policy_for(
    subject: str, trust_tier: str, policies: tuple[ExpiryPolicy, ...] = DEFAULT_POLICIES
) -> ExpiryPolicy | None:
    """First-match-wins against `(subject, trust_tier)`, `"*"` as wildcard for subject."""
    for policy in policies:
        if policy.trust_tier == trust_tier and policy.subject in ("*", subject):
            return policy
    return None


def _owner_of(access: MemoryAccess, project_root: Path) -> OwnerScope:
    """The one owner a maintenance access acts for (legacy default when unset)."""
    return access.owner_scope or legacy_owner_scope(project_root)


def _scope_sql(access: MemoryAccess, project_root: Path) -> tuple[str, list[object]]:
    """72-T04 D9: the owner and D40 source predicate every expiry read applies."""
    legacy_default = legacy_owner_scope(project_root)
    owner = _owner_of(access, project_root)
    source_sql, source_params = source_predicate_sql("source", access.sources)
    clause = (
        "COALESCE(owner_scope_kind, ?) = ? AND COALESCE(owner_scope_id, ?) = ? "
        f"AND {source_sql}"
    )
    return (
        clause,
        [legacy_default.kind, owner.kind, legacy_default.id, owner.id, *source_params],
    )


def expired_candidate_rows(
    conn: sqlite3.Connection,
    project_root: Path,
    *,
    access: MemoryAccess,
    batch_size: int,
    now: float,
    candidate_ids: Collection[str] | None = None,
) -> list[sqlite3.Row]:
    """The rows the expiry sweep would stamp: TTL elapsed, not yet expired, not
    archived, owned by `access`'s owner, in a source `access` grants (D40), and (when
    given) inside the reviewed `candidate_ids`. A pure SELECT, so a read-only
    connection can run it for a zero-write preview."""
    ttl_cases = []
    parameters: list[object] = []
    for policy in DEFAULT_POLICIES:
        ttl_cases.append("WHEN trust_tier = ? AND (? = '*' OR subject = ?) THEN ?")
        parameters.extend(
            (policy.trust_tier, policy.subject, policy.subject, policy.ttl_seconds)
        )
    ttl_sql = "CASE " + " ".join(ttl_cases) + " END"
    scope_sql, scope_params = _scope_sql(access, project_root)
    candidate_sql = ""
    candidate_params: tuple[object, ...] = ()
    if candidate_ids is not None:
        candidate_sql = "AND id IN (SELECT value FROM json_each(?)) "
        candidate_params = (json.dumps(list(candidate_ids)),)
    return conn.execute(
        "SELECT id, subject, trust_tier, created_at, content, source, artifact_version "
        "FROM memory_artifacts WHERE expired_at IS NULL AND archived_at IS NULL "
        f"AND created_at + ({ttl_sql}) <= ? AND {scope_sql} "
        + candidate_sql
        + "ORDER BY created_at ASC LIMIT ?",
        (*parameters, now, *scope_params, *candidate_params, batch_size),
    ).fetchall()


def reviewed_version_conflicts(
    conn: sqlite3.Connection,
    expected_revisions: Mapping[str, int],
    *,
    access: MemoryAccess | None = None,
    project_root: Path | None = None,
) -> list[tuple[str, int, int | None]]:
    """T28-D: `(id, reviewed version, current version or None)` for every reviewed id
    whose stored `artifact_version` differs, read on `conn` -- run it inside the write
    transaction that mutates those rows so no edit can land in between. With `access`
    (72-T04), a row of another owner or in a source the access does not grant reads as
    absent (`None`), exactly like an id that does not exist."""
    scope_sql = ""
    scope_params: list[object] = []
    if access is not None:
        root = Path(project_root) if project_root is not None else access.project_root
        clause, scope_params = _scope_sql(access, root)
        scope_sql = f" AND {clause}"
    current = {
        row[0]: row[1]
        for row in conn.execute(
            "SELECT id, artifact_version FROM memory_artifacts "
            "WHERE id IN (SELECT value FROM json_each(?))" + scope_sql,
            (json.dumps(list(expected_revisions)), *scope_params),
        )
    }
    return [
        (artifact_id, version, current.get(artifact_id))
        for artifact_id, version in expected_revisions.items()
        if current.get(artifact_id) != version
    ]


def _sweep_expired(
    conn: sqlite3.Connection,
    *,
    access: MemoryAccess,
    renew: Callable[[list[str]], None],
    batch_size: int = 500,
    candidate_ids: Collection[str] | None = None,
) -> int:
    """`_sweep_reviewed_expired()` without a reviewed-version check; returns only the
    count of rows stamped."""
    return _sweep_reviewed_expired(
        conn,
        access=access,
        renew=renew,
        batch_size=batch_size,
        candidate_ids=candidate_ids,
    )[0]


def _sweep_reviewed_expired(
    conn: sqlite3.Connection,
    *,
    access: MemoryAccess,
    renew: Callable[[list[str]], None],
    batch_size: int = 500,
    candidate_ids: Collection[str] | None = None,
    expected_revisions: Mapping[str, int] | None = None,
) -> tuple[int, list[tuple[str, int, int | None]]]:
    """Stamps `expires_at`/`expired_at`/`expired_by="expiry_sweep"` on the selected
    rows whose TTL has elapsed, in one `BEGIN IMMEDIATE` transaction on `conn` (the
    maintenance cycle's connection, under its policy lock and lease).

    Selection is `expired_candidate_rows()` under `access` (owner and D40 source), so a
    row is never re-stamped, `STATED` rows (policy `ttl_seconds=None`) are never
    touched, and archived rows are never selected. `candidate_ids` (T28-D), when given,
    restricts the sweep to exactly those previewed rows. `expected_revisions`, when
    given, is re-checked inside the transaction: every reviewed id whose current
    version differs (or that `access` cannot see) is left unstamped and returned as a
    conflict, and only the remaining reviewed ids are swept.

    `renew(selected_ids)` runs after stamping and before the commit; when it raises
    (lease lost, access changed), the whole batch rolls back and the exception
    propagates. Returns `(rows stamped, conflicts)`.
    """
    project_root = access.project_root
    now = time.time()
    changed = 0
    expired: list[tuple[str, int, str]] = []
    conn.execute("BEGIN IMMEDIATE")
    try:
        conflicts: list[tuple[str, int, int | None]] = []
        if expected_revisions is not None:
            conflicts = reviewed_version_conflicts(
                conn, expected_revisions, access=access, project_root=project_root
            )
            conflict_ids = {conflict[0] for conflict in conflicts}
            reviewed = expected_revisions if candidate_ids is None else candidate_ids
            candidate_ids = [i for i in reviewed if i not in conflict_ids]
        rows = expired_candidate_rows(
            conn,
            project_root,
            access=access,
            batch_size=batch_size,
            now=now,
            candidate_ids=candidate_ids,
        )
        for row in rows:
            row_policy = _policy_for(row["subject"], row["trust_tier"])
            if row_policy is None or row_policy.ttl_seconds is None:
                continue
            expires_at = row["created_at"] + row_policy.ttl_seconds
            if now >= expires_at:
                new_version = _write_version(
                    conn,
                    row["id"],
                    content=_content_or_none(row["content"]),
                    source=row["source"],
                    trust_tier=row["trust_tier"],
                    expected_version=None,
                )
                conn.execute(
                    "UPDATE memory_artifacts SET expires_at = ?, expired_at = ?, "
                    "expired_by = ?, artifact_version = ? WHERE id = ?",
                    (expires_at, now, "expiry_sweep", new_version, row["id"]),
                )
                expired.append((row["id"], new_version, row["source"]))
                changed += 1
        renew([str(row["id"]) for row in rows])
    except BaseException:
        conn.rollback()
        raise
    conn.commit()
    for artifact_id, new_version, source in expired:
        note_committed_write(artifact_id, new_version, source, "expire")
    return changed, conflicts
