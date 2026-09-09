"""Per-type expiry policy and sweep (Phase 62 §6.3).

`sweep_expired()` runs as the `"expiry_sweep"` `MaintenanceTask` (`src/rush/memory/maintenance.py`),
stamping `expires_at`/`expired_at`/`expired_by` on rows whose TTL has elapsed — never silently
recomputed on read (matches Phase 61's own invariant-writing style: `TypedArtifactStore.recall()`
never mutates the DB).
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from rush.memory.store import TypedArtifactStore

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


def sweep_expired(project_root: Path | None = None, *, batch_size: int = 500) -> int:
    """Stamps `expires_at`/`expired_at`/`expired_by="expiry_sweep"` on rows whose TTL has
    elapsed. Returns the count of rows stamped this pass.

    Scoped to `expired_at IS NULL` so a row is never re-stamped by a later sweep, and `STATED`
    rows (policy `ttl_seconds=None`) are never touched.
    """
    store = TypedArtifactStore(project_root)
    now = time.time()
    changed = 0
    ttl_cases = []
    parameters: list[object] = []
    for policy in DEFAULT_POLICIES:
        ttl_cases.append("WHEN trust_tier = ? AND (? = '*' OR subject = ?) THEN ?")
        parameters.extend(
            (policy.trust_tier, policy.subject, policy.subject, policy.ttl_seconds)
        )
    ttl_sql = "CASE " + " ".join(ttl_cases) + " END"
    with sqlite3.connect(str(store.db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, subject, trust_tier, created_at FROM memory_artifacts "
            f"WHERE expired_at IS NULL AND created_at + ({ttl_sql}) <= ? "
            "ORDER BY created_at ASC LIMIT ?",
            (*parameters, now, batch_size),
        ).fetchall()
        for row in rows:
            row_policy = _policy_for(row["subject"], row["trust_tier"])
            if row_policy is None or row_policy.ttl_seconds is None:
                continue
            expires_at = row["created_at"] + row_policy.ttl_seconds
            if now >= expires_at:
                conn.execute(
                    "UPDATE memory_artifacts SET expires_at = ?, expired_at = ?, "
                    "expired_by = ? WHERE id = ?",
                    (expires_at, now, "expiry_sweep", row["id"]),
                )
                changed += 1
        conn.commit()
    return changed
