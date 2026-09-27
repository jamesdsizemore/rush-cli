"""Per-type expiry policy and sweep (Phase 62 §6.3).

`sweep_expired()` runs as the `"expiry_sweep"` `MaintenanceTask` (`src/rush/memory/maintenance.py`),
stamping `expires_at`/`expired_at`/`expired_by` on rows whose TTL has elapsed — never silently
recomputed on read (matches Phase 61's own invariant-writing style: `TypedArtifactStore.recall()`
never mutates the DB).
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Collection
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from rush.memory.store import (
    OwnerScope,
    TypedArtifactStore,
    _write_version,
    legacy_owner_scope,
    note_committed_write,
)

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


def expired_candidate_rows(
    conn: sqlite3.Connection,
    project_root: Path,
    *,
    owner_scope: OwnerScope,
    batch_size: int,
    now: float,
    candidate_ids: Collection[str] | None = None,
) -> list[sqlite3.Row]:
    """The rows `sweep_expired()` would stamp: TTL elapsed, not yet expired, owned by
    exactly `owner_scope`, and (when given) inside the reviewed `candidate_ids`. A pure
    SELECT, so a read-only connection can run it for a zero-write preview."""
    legacy_default = legacy_owner_scope(project_root)
    ttl_cases = []
    parameters: list[object] = []
    for policy in DEFAULT_POLICIES:
        ttl_cases.append("WHEN trust_tier = ? AND (? = '*' OR subject = ?) THEN ?")
        parameters.extend(
            (policy.trust_tier, policy.subject, policy.subject, policy.ttl_seconds)
        )
    ttl_sql = "CASE " + " ".join(ttl_cases) + " END"
    candidate_sql = ""
    candidate_params: tuple[object, ...] = ()
    if candidate_ids is not None:
        candidate_sql = "AND id IN (SELECT value FROM json_each(?)) "
        candidate_params = (json.dumps(list(candidate_ids)),)
    return conn.execute(
        "SELECT id, subject, trust_tier, created_at, content, source, artifact_version "
        f"FROM memory_artifacts WHERE expired_at IS NULL AND created_at + ({ttl_sql}) <= ? "
        "AND COALESCE(owner_scope_kind, ?) = ? AND COALESCE(owner_scope_id, ?) = ? "
        + candidate_sql
        + "ORDER BY created_at ASC LIMIT ?",
        (
            *parameters,
            now,
            legacy_default.kind,
            owner_scope.kind,
            legacy_default.id,
            owner_scope.id,
            *candidate_params,
            batch_size,
        ),
    ).fetchall()


def sweep_expired(
    project_root: Path | None = None,
    *,
    batch_size: int = 500,
    owner_scope: OwnerScope | None = None,
    candidate_ids: Collection[str] | None = None,
) -> int:
    """Stamps `expires_at`/`expired_at`/`expired_by="expiry_sweep"` on rows whose TTL has
    elapsed. Returns the count of rows stamped this pass.

    Scoped to `expired_at IS NULL` so a row is never re-stamped by a later sweep, and `STATED`
    rows (policy `ttl_seconds=None`) are never touched. P69-07 subsection h: also scoped to
    exactly `owner_scope` (kind, id) -- omitted, defaults to `legacy_owner_scope(root)`
    (this project's own path-form owner), never a wildcard sweep across owners.
    `candidate_ids` (T28-D), when given, restricts the sweep to exactly those
    previewed rows; `None` sweeps every eligible row as before.
    """
    store = TypedArtifactStore(project_root)
    scope = owner_scope or legacy_owner_scope(store.project_root)
    now = time.time()
    changed = 0
    expired: list[tuple[str, int, str]] = []
    with closing(sqlite3.connect(str(store.db_path))) as conn, conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN IMMEDIATE")
        rows = expired_candidate_rows(
            conn,
            store.project_root,
            owner_scope=scope,
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
                    content=json.loads(row["content"]),
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
        conn.commit()
    for artifact_id, new_version, source in expired:
        note_committed_write(artifact_id, new_version, source, "expire")
    return changed
