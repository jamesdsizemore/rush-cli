"""Maintenance sub-agent for the typed-artifact memory store (Phase 62 §6.2).

`run_maintenance_cycle()` acquires a capability-scoped `MeshLockManager` lease before running a
bounded sweep over `memory_artifacts`, renews the lease every 50 rows, and stops with a partial
result the instant a renewal is lost (never falling back to the legacy `agent_id`-only release
path, which would let a stale cycle delete a different, live cycle's reclaimed lock).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from rush.mcp_mesh.lock_manager import MeshLockManager
from rush.memory.merkle_invalidator import MerkleInvalidator
from rush.memory.store import (
    MemoryArtifact,
    TypedArtifactStore,
    _write_version,
    promote_stored_artifact,
)
from rush.memory.trust import count_corroboration
from rush.plugins.trust_store import PluginTrustStore

MaintenanceTask = Literal[
    "promotion_sweep", "staleness_sweep", "skill_admission_check", "expiry_sweep"
]

_LOCK_PATH = Path(".rush/memory-maintenance.lock")
_AGENT_ID = "memory-maintenance"
_RENEW_EVERY = 50

_SELECT_SQL: dict[str, str] = {
    "promotion_sweep": (
        "SELECT id, family, subject, trust_tier, content, source, created_at, "
        "symbol_ref, content_hash, corroboration_count, promoted_at, stale, signature "
        "FROM memory_artifacts WHERE trust_tier != 'STATED' AND promoted_at IS NULL "
        "ORDER BY created_at ASC LIMIT :batch_size"
    ),
    "staleness_sweep": (
        "SELECT id, symbol_ref, content_hash FROM memory_artifacts "
        "WHERE symbol_ref IS NOT NULL AND stale = 0 ORDER BY created_at ASC LIMIT :batch_size"
    ),
    "skill_admission_check": (
        "SELECT id, family, subject, trust_tier, content, source, created_at, "
        "symbol_ref, content_hash, corroboration_count, promoted_at, stale, signature "
        "FROM memory_artifacts WHERE subject = 'skill_pattern' AND trust_tier != 'STATED' "
        "AND promoted_at IS NULL ORDER BY created_at ASC LIMIT :batch_size"
    ),
}


@dataclass(frozen=True)
class MaintenanceRunResult:
    task: MaintenanceTask
    processed: int
    changed: int
    errors: tuple[
        str, ...
    ] = ()  # row `id` values whose per-row mutation raised; skipped, not aborted


def run_maintenance_cycle(
    task: MaintenanceTask, *, batch_size: int = 500, project_root: Path | None = None
) -> MaintenanceRunResult:
    """Runs one bounded maintenance sweep under a capability-scoped lock lease (§6.2)."""
    root = (project_root or Path.cwd()).resolve()
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
        if task == "expiry_sweep":
            from rush.memory.expiry import sweep_expired

            changed = sweep_expired(root, batch_size=batch_size)
            return MaintenanceRunResult(
                task=task, processed=changed, changed=changed, errors=()
            )

        store = TypedArtifactStore(root)
        conn = sqlite3.connect(str(store.db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                _SELECT_SQL[task], {"batch_size": batch_size}
            ).fetchall()

            processed = 0
            changed = 0
            errors: list[str] = []
            for index, row in enumerate(rows, start=1):
                try:
                    if _mutate_row(task, conn, row, root):
                        changed += 1
                    processed += 1
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
                task=task, processed=processed, changed=changed, errors=tuple(errors)
            )
        finally:
            conn.close()
    finally:
        if not lock_lost:
            lock_manager.release(_LOCK_PATH, capability=capability)


def _mutate_row(
    task: MaintenanceTask, conn: sqlite3.Connection, row: sqlite3.Row, root: Path
) -> bool:
    if task == "promotion_sweep":
        return _mutate_promotion_sweep(conn, row, root)
    if task == "staleness_sweep":
        return _mutate_staleness_sweep(conn, row, root)
    if task == "skill_admission_check":
        return _mutate_skill_admission_check(conn, row, root)
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
    conn: sqlite3.Connection, row: sqlite3.Row, root: Path
) -> bool:
    artifact = _artifact_from_row(row)
    candidate_sources = _candidate_sources(conn, artifact.subject, artifact.symbol_ref)
    conn.execute("BEGIN IMMEDIATE")
    _, decision = promote_stored_artifact(
        conn,
        artifact.id,
        user_stated=False,
        candidate_sources=candidate_sources,
        project_root=root,
    )
    if decision.promoted:
        conn.commit()
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
        return True
    conn.commit()
    return False


def _mutate_staleness_sweep(
    conn: sqlite3.Connection, row: sqlite3.Row, root: Path
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
        return True
    return False


def _mutate_skill_admission_check(
    conn: sqlite3.Connection, row: sqlite3.Row, root: Path
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
    _, decision = promote_stored_artifact(
        conn,
        artifact.id,
        user_stated=False,
        candidate_sources=candidate_sources,
        project_root=root,
    )
    conn.commit()
    return decision.promoted
