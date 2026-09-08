"""One-shot migration functions absorbing pre-P61.3 satellite stores into `TypedArtifactStore`.

Phase 61 §6.3 Invariant 5, §9 P61.3.1-2 — each `migrate_*` function below is idempotent via an
`origin_kind`+`origin_id` existence check (`artifact_exists`): a row is inserted once and never
duplicated on a rerun (T-61.22), and a rerun after a row is manually deleted/mutated re-inserts
exactly that row without duplicating anything else (T-61.37). The JSON/JSONL satellite files
Invariant 5 names — `preferences.json`, `invariants.json`, checkpoint session files, flight
JSONL, and `hook_signatures.json` — are renamed with a `.migrated` suffix after a successful
migration (never deleted). `.rush/cache.db` (`PatchMemoryStore`, shared with `ResultCache`),
`.rush/memory/failures.db` (`FailureLedger`), and `.rush/cache/merkle.json`
(`MerkleInvalidator`) are never renamed, moved, or deleted — only their rows'/entries' data is
copied, since none of the three is in Invariant 5's rename list and `MerkleInvalidator` must stay
a pure, unrenamed cache per Invariant 6 (its `hash_content()` computation cannot depend on
`TypedArtifactStore`).

`read_origin`/`read_origin_kind`/`read_origin_kind_by_symbol` are the compatibility-view read
fallback the 5 renamed-satellite modules (`preference_store.py`, `invariant_graph.py`,
`checkpoint_journal.py`, `tools/flight_recorder.py`, `hook/tamper_detector.py`) call when their
own physical file is missing (already renamed by a prior migration run) — the write paths of all
8 modules stay unchanged.
"""

from __future__ import annotations

import calendar
import hashlib
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from rush.memory.store import (
    MemoryArtifact,
    MemoryFamily,
    MemorySubject,
    TypedArtifactStore,
)
from rush.memory.trust import default_entry_tier

_LOCAL_TIER = default_entry_tier("local_tool")


def artifact_exists(
    store: TypedArtifactStore, origin_kind: str, origin_id: str
) -> bool:
    """Idempotency key check (T-61.22, T-61.37): True if this origin was already migrated."""
    with sqlite3.connect(str(store.db_path)) as conn:
        row = conn.execute(
            "SELECT 1 FROM memory_artifacts WHERE origin_kind = ? AND origin_id = ? LIMIT 1",
            (origin_kind, origin_id),
        ).fetchone()
    return row is not None


def write_if_new(
    store: TypedArtifactStore,
    *,
    family: MemoryFamily,
    subject: MemorySubject,
    content: dict[str, Any],
    source: str,
    origin_kind: str,
    origin_id: str,
    symbol_ref: str | None = None,
    created_at: float | None = None,
) -> MemoryArtifact | None:
    """Idempotent insert keyed by `(origin_kind, origin_id)`; returns `None` if already migrated."""
    if artifact_exists(store, origin_kind, origin_id):
        return None
    return store.write(
        MemoryArtifact(
            id=str(uuid.uuid4()),
            family=family,
            subject=subject,
            trust_tier=_LOCAL_TIER,
            content=content,
            source=source,
            created_at=created_at if created_at is not None else time.time(),
            symbol_ref=symbol_ref,
            origin_kind=origin_kind,
            origin_id=origin_id,
        )
    )


def read_origin(
    project_root: Path, origin_kind: str, origin_id: str
) -> dict[str, Any] | None:
    """Compatibility-view read fallback: a migrated row's content by its exact origin key."""
    store = TypedArtifactStore(project_root)
    with sqlite3.connect(str(store.db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT content FROM memory_artifacts WHERE origin_kind = ? AND origin_id = ? LIMIT 1",
            (origin_kind, origin_id),
        ).fetchone()
    return json.loads(row["content"]) if row else None


def read_origin_kind(project_root: Path, origin_kind: str) -> list[dict[str, Any]]:
    """Compatibility-view read fallback: every migrated row's content for one `origin_kind`,
    ordered by `created_at` (session_memory.py's `format_for_mcp` needs chronological order)."""
    store = TypedArtifactStore(project_root)
    with sqlite3.connect(str(store.db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT content FROM memory_artifacts WHERE origin_kind = ? ORDER BY created_at",
            (origin_kind,),
        ).fetchall()
    return [json.loads(row["content"]) for row in rows]


def read_origin_kind_by_symbol(
    project_root: Path, origin_kind: str, symbol_ref: str
) -> list[dict[str, Any]]:
    """Compatibility-view read fallback scoped to a shared `symbol_ref` (e.g. a flight session id)."""
    store = TypedArtifactStore(project_root)
    with sqlite3.connect(str(store.db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT content FROM memory_artifacts WHERE origin_kind = ? AND symbol_ref = ? "
            "ORDER BY created_at",
            (origin_kind, symbol_ref),
        ).fetchall()
    return [json.loads(row["content"]) for row in rows]


def _rename_migrated(path: Path) -> None:
    path.rename(path.with_name(path.name + ".migrated"))


def _read_map_source(old_file: Path, project_root: Path) -> dict[str, Any]:
    """Reads a `CASMapTransaction` JSON map from `old_file`, or its `.migrated` sibling if `old_file`
    was already renamed by a prior run — lets a rerun after partial completion (T-61.37) recover a
    manually-deleted row without needing the original, unrenamed filename to still exist."""
    migrated_file = old_file.with_name(old_file.name + ".migrated")
    source_file = old_file if old_file.exists() else migrated_file
    if not source_file.exists():
        return {}
    from rush.memory.transactions import CASMapTransaction

    return (
        CASMapTransaction(file_path=source_file, root_path=project_root)
        .read(allow_missing=True)
        .data
    )


def migrate_preference_store(project_root: Path) -> int:
    """Absorbs `.rush/preferences.json` (`PreferenceStore`) into `subject="preference"` rows."""
    old_file = project_root / ".rush" / "preferences.json"
    migrated_file = old_file.with_name(old_file.name + ".migrated")
    if not old_file.exists() and not migrated_file.exists():
        return 0
    data = _read_map_source(old_file, project_root)
    store = TypedArtifactStore(project_root)
    migrated = 0
    for key, value in data.items():
        result = write_if_new(
            store,
            family="memory",
            subject="preference",
            content={"key": key, "value": value},
            source="migration:preference_store",
            origin_kind="preference",
            origin_id=key,
        )
        if result is not None:
            migrated += 1
    if old_file.exists():
        _rename_migrated(old_file)
    return migrated


def migrate_invariant_graph(project_root: Path) -> int:
    """Absorbs `.rush/memory/invariants.json` (`InvariantGraph`) into `subject="architectural_decision"` rows."""
    old_file = project_root / ".rush" / "memory" / "invariants.json"
    migrated_file = old_file.with_name(old_file.name + ".migrated")
    if not old_file.exists() and not migrated_file.exists():
        return 0
    data = _read_map_source(old_file, project_root)
    store = TypedArtifactStore(project_root)
    migrated = 0
    for rule_id, entry in data.items():
        result = write_if_new(
            store,
            family="memory",
            subject="architectural_decision",
            content={"rule_id": rule_id, **entry},
            source="migration:invariant_graph",
            origin_kind="invariant_graph",
            origin_id=rule_id,
        )
        if result is not None:
            migrated += 1
    if old_file.exists():
        _rename_migrated(old_file)
    return migrated


def migrate_merkle_invalidator(project_root: Path) -> int:
    """Copies `.rush/cache/merkle.json` (`MerkleInvalidator`) AST-hash entries as historical facts.

    The cache file is left live and unrenamed (not in Invariant 5's rename list); `check_and_update()`
    keeps reading/writing it directly and unchanged, per Invariant 6's pure-computation boundary.
    """
    old_file = project_root / ".rush" / "cache" / "merkle.json"
    if not old_file.exists():
        return 0
    from rush.memory.merkle_invalidator import MerkleInvalidator

    data = MerkleInvalidator(project_root)._read()
    store = TypedArtifactStore(project_root)
    migrated = 0
    for symbol_key, content_hash in data.items():
        result = write_if_new(
            store,
            family="memory",
            subject="domain_knowledge",
            content={"symbol_key": symbol_key, "content_hash": content_hash},
            source="migration:merkle_invalidator",
            origin_kind="merkle_cache",
            origin_id=symbol_key,
        )
        if result is not None:
            migrated += 1
    return migrated


def migrate_checkpoint_journal(project_root: Path) -> int:
    """Absorbs `.rush/sessions/*.json` (`CheckpointJournal`) into `family="handoff"` rows."""
    session_dir = project_root / ".rush" / "sessions"
    if not session_dir.exists():
        return 0
    json_files = list(session_dir.glob("*.json"))
    if not json_files:
        return 0
    from rush.memory.checkpoint_journal import CheckpointJournal

    entries = CheckpointJournal(project_root).list_checkpoints()
    store = TypedArtifactStore(project_root)
    migrated = 0
    for entry in entries:
        origin_id = str(entry.get("checkpoint_id") or entry.get("name") or "")
        if not origin_id:
            continue
        result = write_if_new(
            store,
            family="handoff",
            subject="active_context",
            content=entry,
            source="migration:checkpoint_journal",
            origin_kind="checkpoint",
            origin_id=origin_id,
            symbol_ref=origin_id,
            created_at=entry.get("created_at"),
        )
        if result is not None:
            migrated += 1
    for json_file in json_files:
        _rename_migrated(json_file)
    return migrated


def migrate_failure_ledger(project_root: Path) -> int:
    """Absorbs `.rush/memory/failures.db` (`FailureLedger`) rows into `subject="failure"` rows.

    `failures.db` is never renamed (not in Invariant 5's rename list); only row data is copied.
    """
    db_path = project_root / ".rush" / "memory" / "failures.db"
    if not db_path.exists():
        return 0
    store = TypedArtifactStore(project_root)
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT fingerprint, error_message, created_at FROM failure_ledgers"
            ).fetchall()
        except sqlite3.OperationalError:
            return 0
    migrated = 0
    for row in rows:
        result = write_if_new(
            store,
            family="memory",
            subject="failure",
            content={
                "fingerprint": row["fingerprint"],
                "error_message": row["error_message"],
            },
            source="migration:failure_ledger",
            origin_kind="failure_ledger",
            origin_id=row["fingerprint"],
            symbol_ref=row["fingerprint"],
            created_at=float(row["created_at"]),
        )
        if result is not None:
            migrated += 1
    return migrated


def migrate_patch_memory(project_root: Path) -> int:
    """Absorbs `.rush/cache.db`'s `patch_memory` table (`PatchMemoryStore`) into `subject="failure"` rows.

    `cache.db` is never renamed, moved, or deleted (shared with `ResultCache`'s unrelated
    `cache_entries` table, per Invariant 5) — only `patch_memory`'s row data is copied. Rows share
    `symbol_ref` with their matching `migrate_failure_ledger` row when the caller used the same
    signature text for both, making the pairing queryable (T-61.19).
    """
    db_path = project_root / ".rush" / "cache.db"
    if not db_path.exists():
        return 0
    from rush.patch.memory import PatchMemoryStore

    records = PatchMemoryStore(project_root).list_records()
    store = TypedArtifactStore(project_root)
    migrated = 0
    for record in records:
        result = write_if_new(
            store,
            family="memory",
            subject="failure",
            content={
                "error_signature": record.error_signature,
                "target_file": record.target_file,
                "diff_patch": record.diff_patch,
                "success_count": record.success_count,
            },
            source="migration:patch_memory",
            origin_kind="patch_memory",
            origin_id=record.error_signature,
            symbol_ref=record.error_signature,
            created_at=record.created_at,
        )
        if result is not None:
            migrated += 1
    return migrated


def migrate_flight_recorder(project_root: Path) -> int:
    """Absorbs `.rush/sessions/flights/*.jsonl` (`FlightRecorder`) into `subject="episodic"` rows."""
    flights_dir = project_root / ".rush" / "sessions" / "flights"
    if not flights_dir.exists():
        return 0
    jsonl_files = list(flights_dir.glob("*.jsonl"))
    if not jsonl_files:
        return 0
    from rush.tools.flight_recorder import FlightRecorder

    recorder = FlightRecorder(project_root, create=False)
    store = TypedArtifactStore(project_root)
    migrated = 0
    for jsonl_file in jsonl_files:
        session_id = jsonl_file.stem
        try:
            events = recorder.replay_session(session_id)
        except ValueError:
            continue
        for event in events:
            timestamp = event.get("timestamp")
            event_type = event.get("event_type", "")
            origin_id = hashlib.sha256(
                f"{session_id}|{timestamp}|{event_type}".encode("utf-8")
            ).hexdigest()
            result = write_if_new(
                store,
                family="experience",
                subject="episodic",
                content=event,
                source="migration:flight_recorder",
                origin_kind="flight_event",
                origin_id=origin_id,
                symbol_ref=session_id,
                created_at=timestamp,
            )
            if result is not None:
                migrated += 1
    for jsonl_file in jsonl_files:
        _rename_migrated(jsonl_file)
    return migrated


def migrate_hook_signatures(project_root: Path) -> int:
    """Absorbs `.rush/hook_signatures.json` (`HookTamperDetector`) into `origin_kind="hook_signature"` rows."""
    sig_file = project_root / ".rush" / "hook_signatures.json"
    migrated_sig_file = sig_file.with_name(sig_file.name + ".migrated")
    source_file = sig_file if sig_file.exists() else migrated_sig_file
    if not source_file.exists():
        return 0
    try:
        signatures = json.loads(source_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        signatures = {}
    store = TypedArtifactStore(project_root)
    migrated = 0
    for hook_name, sha in signatures.items():
        result = write_if_new(
            store,
            family="memory",
            subject="active_context",
            content={"hook_name": hook_name, "sha256": sha},
            source="migration:hook_signatures",
            origin_kind="hook_signature",
            origin_id=hook_name,
        )
        if result is not None:
            migrated += 1
    if sig_file.exists():
        _rename_migrated(sig_file)
    return migrated


def migrate_session_memory(project_root: Path) -> int:
    """Absorbs `.rush/session_memory.json` (`SessionMemoryManager`) into `subject="episodic"` rows.

    Shares its `origin_id` derivation with `SessionMemoryManager.record_turn`'s own forward-write
    (P61.5.2): a record already forward-written at creation time is skipped here (already
    migrated), so only records predating the forward-write wiring are absorbed.
    """
    old_file = project_root / ".rush" / "session_memory.json"
    migrated_file = old_file.with_name(old_file.name + ".migrated")
    source_file = old_file if old_file.exists() else migrated_file
    if not source_file.exists():
        return 0
    from rush.session_memory import SessionMemoryManager

    records = SessionMemoryManager(memory_file=source_file).load_records()
    store = TypedArtifactStore(project_root)
    migrated = 0
    for record in records:
        origin_id = hashlib.sha256(
            f"{record.timestamp}{record.tool_name}{record.summary}".encode("utf-8")
        ).hexdigest()
        created_at = float(
            calendar.timegm(time.strptime(record.timestamp, "%Y-%m-%dT%H:%M:%SZ"))
        )
        result = write_if_new(
            store,
            family="experience",
            subject="episodic",
            content={
                "timestamp": record.timestamp,
                "tool_name": record.tool_name,
                "finding_count": record.finding_count,
                "fixes_applied": record.fixes_applied,
                "summary": record.summary,
            },
            source="migration:session_memory",
            origin_kind="session_memory",
            origin_id=origin_id,
            created_at=created_at,
        )
        if result is not None:
            migrated += 1
    if old_file.exists():
        _rename_migrated(old_file)
    return migrated
