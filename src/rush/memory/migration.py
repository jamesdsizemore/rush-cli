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
own physical file is missing (already renamed by a prior migration run). Preference mutations
and replacement checkpoint migrations update existing origins without retaining old approvals.
"""

from __future__ import annotations

import calendar
import functools
import hashlib
import json
import math
import os
import re
import sqlite3
import time
import uuid
from collections.abc import Callable, Iterator, Sequence
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any

from rush.memory.store import (
    UNBOUND_VERIFIER,
    BindingVerifier,
    MemoryArtifact,
    MemoryFamily,
    MemorySubject,
    TypedArtifactStore,
    _stored_text,
    _verified_binding,
    _write_version,
    next_row_mac,
    note_committed_write,
    note_memory_read,
    read_sqlite_readonly,
    sqlite_has_table,
    sqlite_text,
)
from rush.memory.trust import default_entry_tier
from rush.safety.redactor import sanitize_value

_LOCAL_TIER = default_entry_tier("local_tool")


# 72-T05: every documented `PreferenceError` code (D10). Defined here because
# `preference_store` imports this module; the reverse import would cycle.
PREFERENCE_ERROR_CODES = frozenset(
    {
        "E_INPUT",
        "E_PERMISSION",
        "E_OWNER",
        "E_SCOPE",
        "E_VERSION",
        "E_MIGRATION",
        "E_UNAVAILABLE",
    }
)


class PreferenceError(Exception):
    """72-T05: the one exception a preference action raises: `code` (one of
    `PREFERENCE_ERROR_CODES`) and a machine `reason`; `str(e) == "CODE: reason"`."""

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(f"{code}: {reason}")
        self.code = code
        self.reason = reason


def artifact_exists(
    store: TypedArtifactStore, origin_kind: str, origin_id: str
) -> bool:
    """Idempotency key check (T-61.22, T-61.37): True if this origin was already migrated."""
    with closing(sqlite3.connect(str(store.db_path))) as conn, conn:
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
    access: Any = None,
) -> MemoryArtifact | None:
    """Idempotent insert keyed by `(origin_kind, origin_id)`; returns `None` if already
    migrated. 72-T01 D4: authorized for `source` through the shared writer gate (a
    supplied `access` must authorize it); a denial returns `None` with no effect."""
    from rush.memory.retrieval import (
        RouteDenial,
        authorize_writer,
        recheck_failure,
        writer_owner,
    )
    from rush.memory.store import MemoryAccessChanged

    with authorize_writer(store.project_root, source, access=access) as granted:
        if isinstance(granted, RouteDenial):
            return None
        if artifact_exists(store, origin_kind, origin_id):
            return None
        try:
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
                    owner_scope=writer_owner(granted),
                ),
                commit_check=lambda: recheck_failure(granted),
            )
        except MemoryAccessChanged:
            return None


def replace_origin_content(
    store: TypedArtifactStore,
    origin_kind: str,
    origin_id: str,
    content: dict[str, Any],
    *,
    created_at: float | None = None,
) -> bool:
    """Replace changed compatibility content without inheriting approval of old bytes.

    Routed through `_write_version` (MC01 §6.1) only when content actually changed: an
    identical import stays a no-op, never advancing `artifact_version`. 72-T05: one
    `BEGIN IMMEDIATE` around `replace_origin_content_tx`.
    """
    with closing(sqlite3.connect(str(store.db_path))) as conn, conn:
        conn.row_factory = sqlite3.Row
        conn.text_factory = sqlite_text  # 72-T02 D32
        conn.execute("BEGIN IMMEDIATE")
        new_version = replace_origin_content_tx(
            conn,
            origin_kind,
            origin_id,
            content,
            created_at=created_at,
            project_root=store.project_root,
        )
        if new_version is None:
            return False
        row = conn.execute(
            "SELECT id, source FROM memory_artifacts "
            "WHERE origin_kind = ? AND origin_id = ?",
            (origin_kind, origin_id),
        ).fetchone()
    note_committed_write(row["id"], new_version, row["source"], "update")
    return True


def _connection_project_root(conn: sqlite3.Connection) -> Path:
    """The project root of a `<root>/.rush/memory.db` connection."""
    main = next(r for r in conn.execute("PRAGMA database_list") if r[1] == "main")
    return Path(main[2]).parent.parent


def replace_origin_content_tx(
    conn: sqlite3.Connection,
    origin_kind: str,
    origin_id: str,
    content: dict[str, Any],
    *,
    created_at: float | None = None,
    project_root: Path | None = None,
) -> int | None:
    """72-T05 (D30 site): `replace_origin_content` inside the caller's transaction.
    Returns the new `artifact_version`, or `None` when no origin row exists or its
    content already equals `content` (no write). Never connects, commits or notes;
    applies the D41 row-MAC write rule to the covered UPDATE."""
    previous_factory = conn.row_factory
    conn.row_factory = sqlite3.Row
    try:
        clean_content = sanitize_value(content).value
        row = conn.execute(
            "SELECT id, content, source FROM memory_artifacts "
            "WHERE origin_kind = ? AND origin_id = ?",
            (origin_kind, origin_id),
        ).fetchone()
        if row is None or json.dumps(
            json.loads(row["content"]), sort_keys=True
        ) == json.dumps(clean_content, sort_keys=True):
            return None
        new_version = _write_version(
            conn,
            row["id"],
            content=clean_content,
            source=row["source"],
            trust_tier=_LOCAL_TIER,
            expected_version=None,
        )
        new_text = json.dumps(clean_content)
        mac = next_row_mac(
            conn,
            project_root
            if project_root is not None
            else _connection_project_root(conn),
            row["id"],
            {"content": new_text, "trust_tier": _LOCAL_TIER, "content_hash": None},
        )
        conn.execute(
            "UPDATE memory_artifacts SET content = ?, trust_tier = ?, created_at = ?, "
            "signature = NULL, promoted_at = NULL, corroboration_count = 0, "
            "stale = 0, content_hash = NULL, expires_at = NULL, expired_at = NULL, "
            "expired_by = NULL, artifact_version = ?, row_mac = ? "
            "WHERE origin_kind = ? AND origin_id = ?",
            (
                new_text,
                _LOCAL_TIER,
                created_at if created_at is not None else time.time(),
                new_version,
                mac,
                origin_kind,
                origin_id,
            ),
        )
        return int(new_version)
    finally:
        conn.row_factory = previous_factory


# 72-T01 D1 (§2.3 Migration readers): the sources that write each `origin_kind`
# (its `migrate_*` source plus any live writer's source).
_ORIGIN_SOURCES: dict[str, tuple[str, ...]] = {
    "preference": ("migration:preference_store",),
    "invariant_graph": ("migration:invariant_graph",),
    "merkle_cache": ("migration:merkle_invalidator",),
    "checkpoint": (
        "checkpoint_journal:save_checkpoint",
        "migration:checkpoint_journal",
    ),
    "failure_ledger": ("migration:failure_ledger",),
    "patch_memory": ("migration:patch_memory",),
    "flight_event": ("flight_recorder:record_event", "migration:flight_recorder"),
    "hook_signature": ("migration:hook_signatures",),
    "session_memory": ("session_memory:record_turn", "migration:session_memory"),
    "attribution_link": ("provenance_ai:attribution_link",),
}


def _origin_filter(
    project_root: Path, origin_kind: str
) -> tuple[Callable[[sqlite3.Row], bool], Callable[[], str]] | None:
    """72-T01 D1: the row test for one compatibility-view read of `origin_kind` and
    the access recheck to run after the read, or `None` when the route is denied
    (the reader returns no rows and opens nothing). `legacy` mode keeps every row,
    as at HEAD; `policy` mode keeps the grant owner's rows whose source it
    approves."""
    from rush.memory.retrieval import RouteDenial, reader_route, reader_row_allowed

    root = Path(project_root).resolve()
    access = reader_route(root, "ask", _ORIGIN_SOURCES.get(origin_kind, ()))
    if isinstance(access, RouteDenial):
        return None
    return (lambda row: reader_row_allowed(access, root, row)), access.recheck


def _decodable(row: sqlite3.Row) -> bool:
    """72-T02 D32: a row whose stored content is not UTF-8 is skipped by every
    compatibility-view reader (never decoded with replacement characters)."""
    return _stored_text(row["content"]) is not None


def read_origin(
    project_root: Path, origin_kind: str, origin_id: str
) -> dict[str, Any] | None:
    """Compatibility-view read fallback: a migrated row's content by its exact origin
    key. Read-only: it never creates or migrates `memory.db`."""
    return read_origin_readonly(project_root, origin_kind, origin_id)


def read_origin_kind(project_root: Path, origin_kind: str) -> list[dict[str, Any]]:
    """Compatibility-view read fallback: every migrated row's content for one `origin_kind`,
    ordered by `created_at` (session_memory.py's `format_for_mcp` needs chronological order).
    Read-only: it never creates or migrates `memory.db`."""
    return read_origin_kind_readonly(project_root, origin_kind)


def read_origin_kind_by_symbol(
    project_root: Path, origin_kind: str, symbol_ref: str
) -> list[dict[str, Any]]:
    """Compatibility-view read fallback scoped to a shared `symbol_ref` (e.g. a flight
    session id). Read-only: it never creates or migrates `memory.db`."""
    return read_origin_kind_by_symbol_readonly(project_root, origin_kind, symbol_ref)


_ORIGIN_SQL = "SELECT * FROM memory_artifacts WHERE origin_kind = ?"
_ORIGIN_ID_SQL = _ORIGIN_SQL + " AND origin_id = ? ORDER BY created_at"
_ORIGIN_SYMBOL_SQL = _ORIGIN_SQL + " AND symbol_ref = ? ORDER BY created_at"
_ORIGIN_KIND_SQL = _ORIGIN_SQL + " ORDER BY created_at"


def _origin_rows_readonly(
    project_root: Path, sql: str, params: tuple[str, ...]
) -> list[tuple[dict[str, Any], tuple[str, int, str] | None]]:
    """T10: the non-creating compatibility-view read. One `read_sqlite_readonly`
    connection (no `.rush`, DB, `-wal`/`-shm` or migration is ever created); a
    legacy DB predating `artifact_version` still yields its origin rows, because
    `origin_kind`/`origin_id`/`symbol_ref` are base-schema columns. A missing DB
    or table gives no rows.

    T19: each row is paired with its `(id, revision, source)` ref, or `None`
    for a legacy row with no `artifact_version`; the public readers note the
    refs of the rows they actually return (`note_memory_read`).

    72-T01 D1: `params[0]` is the `origin_kind`; a denied route reads nothing and
    `policy` mode keeps only the rows `_origin_filter` allows. D41: a STATED row
    whose row MAC does not verify against this store is never returned, in either
    mode. Every tier is held to the shared integrity check (`retrieval._integrity`):
    a row whose content no longer matches its `payload_hash` is never returned,
    while an unbound row (`payload_hash` NULL or absent, an older schema) stays
    readable. The access is rechecked after the read; a grant that stopped holding
    during the read returns nothing."""
    from rush.memory.retrieval import _integrity

    filtered = _origin_filter(project_root, params[0])
    if filtered is None:
        return []
    visible, recheck = filtered
    root = Path(project_root).resolve()
    db = root / ".rush" / "memory.db"

    def read(
        conn: sqlite3.Connection,
    ) -> list[tuple[dict[str, Any], tuple[str, int, str] | None]]:
        if not sqlite_has_table(conn, "memory_artifacts"):
            return []
        cursor = conn.execute(sql, params)
        # A legacy DB predating `artifact_version` has rows but no revision.
        versioned = any(col[0] == "artifact_version" for col in cursor.description)
        found = _verified_binding(conn, root)
        verifier = (
            BindingVerifier("bound", found[0], found[1])
            if found is not None
            else UNBOUND_VERIFIER
        )
        return [
            (
                json.loads(_stored_text(row["content"]) or ""),
                (row["id"], row["artifact_version"], row["source"])
                if versioned
                else None,
            )
            for row in cursor.fetchall()
            if visible(row)
            and _decodable(row)
            and (
                # The oldest schema has no trust tier, signature or payload binding.
                "trust_tier" not in row.keys()  # noqa: SIM118 - sqlite3.Row
                or not _integrity(row, verifier)[0]
            )
        ]

    rows = read_sqlite_readonly(db, read) or []
    return rows if recheck() == "ok" else []


def _returned(
    rows: list[tuple[dict[str, Any], tuple[str, int, str] | None]],
) -> list[dict[str, Any]]:
    for _content, ref in rows:
        if ref is not None:
            note_memory_read(*ref)
    return [content for content, _ref in rows]


def read_origin_readonly(
    project_root: Path, origin_kind: str, origin_id: str
) -> dict[str, Any] | None:
    """Non-creating `read_origin`."""
    rows = _origin_rows_readonly(project_root, _ORIGIN_ID_SQL, (origin_kind, origin_id))
    returned = _returned(rows[:1])
    return returned[0] if returned else None


def read_origin_kind_readonly(
    project_root: Path, origin_kind: str
) -> list[dict[str, Any]]:
    """Non-creating `read_origin_kind`."""
    return _returned(read_origin_kind_refs_readonly(project_root, origin_kind))


def read_origin_kind_refs_readonly(
    project_root: Path, origin_kind: str
) -> list[tuple[dict[str, Any], tuple[str, int, str] | None]]:
    """Non-creating `read_origin_kind`, each row paired with its
    `(id, revision, source)` ref and nothing noted: a caller that returns only
    some rows notes those itself (`note_memory_read`)."""
    return _origin_rows_readonly(project_root, _ORIGIN_KIND_SQL, (origin_kind,))


def read_origin_kind_by_symbol_readonly(
    project_root: Path, origin_kind: str, symbol_ref: str
) -> list[dict[str, Any]]:
    """Non-creating `read_origin_kind_by_symbol`."""
    return _returned(
        _origin_rows_readonly(
            project_root, _ORIGIN_SYMBOL_SQL, (origin_kind, symbol_ref)
        )
    )


def _gated_migration(
    source: str,
) -> Callable[[Callable[[Path], int]], Callable[[Path], int]]:
    """72-T01 D4: a `migrate_*` function runs (store, writes, rename) only inside the
    shared writer gate for its `migration:<name>` source; a denial migrates 0 rows,
    creates nothing and renames nothing."""

    def decorate(migrate: Callable[[Path], int]) -> Callable[[Path], int]:
        @functools.wraps(migrate)
        def gated(project_root: Path) -> int:
            from rush.memory.retrieval import RouteDenial, authorize_writer

            with authorize_writer(Path(project_root).resolve(), source) as granted:
                if isinstance(granted, RouteDenial):
                    return 0
                return migrate(project_root)

        return gated

    return decorate


def _rename_migrated(path: Path) -> None:
    path.rename(path.with_name(path.name + ".migrated"))


def _read_map_file(path: Path, project_root: Path) -> dict[str, Any]:
    from rush.memory.transactions import CASMapTransaction

    return dict(
        CASMapTransaction(file_path=path, root_path=project_root)
        .read(allow_missing=True)
        .data
    )


def _read_map_source(
    old_file: Path, project_root: Path, *, backups: Sequence[Path] = ()
) -> dict[str, Any]:
    """Reads a `CASMapTransaction` JSON map from `old_file`, or its `.migrated` sibling if `old_file`
    was already renamed by a prior run — lets a rerun after partial completion (T-61.37) recover a
    manually-deleted row without needing the original, unrenamed filename to still exist.

    72-T05 (A1): with `backups`, merges `.migrated`, then each backup in the given
    order, then the live `old_file` (a later map wins per key)."""
    migrated_file = old_file.with_name(old_file.name + ".migrated")
    if backups:
        merged: dict[str, Any] = {}
        for path in (migrated_file, *backups, old_file):
            if path.exists():
                merged.update(_read_map_file(path, project_root))
        return merged
    source_file = old_file if old_file.exists() else migrated_file
    if not source_file.exists():
        return {}
    return _read_map_file(source_file, project_root)


# 72-T05 D27: the preference migration core (plan, transactional apply, verified
# publication). Lock order: Lock 2 (policy lock) is held by the caller, then Lock 4
# (`preference_source_lock`), then pending set/delete publications resume.
PREFERENCE_MIGRATION_SOURCE = "migration:preference_store"
_PREFERENCE_MIGRATION_PREFIX = "preference-migration:"
_PREFERENCE_PUBLICATION_PREFIX = "preference-publication:"
_PREFERENCE_SOURCE_RELATIVE = ".rush/preferences.json"
_PREFERENCE_LEGACY_BACKUP_RELATIVE = ".rush/preferences.json.migrated"
_PREFERENCE_BACKUP_NAME = re.compile(r"^preferences\.json\.migrated\.([0-9a-f]{16})$")


def _preference_root(project_root: Path) -> Path:
    try:
        return Path(project_root).resolve()
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise PreferenceError("E_INPUT", "project_root_invalid") from exc


def preference_source_path(project_root: Path) -> Path:
    """The resolved `.rush/preferences.json` path of a project."""
    return _preference_root(project_root) / ".rush" / "preferences.json"


@contextmanager
def preference_source_lock(project_root: Path) -> Iterator[None]:
    """Lock 4 (D27, §3.9): the `"preferences:"` cross-process lock of one source.

    A directory lock on the project root itself (flock / named mutex, no lock file):
    a legacy-mode `set` never writes under the user data root."""
    from rush.dashboard.state import cross_process_project_lock

    source = preference_source_path(project_root)
    with cross_process_project_lock(
        "preferences:" + str(source),
        data_root=source.parent.parent,
        storage="directory",
    ):
        yield


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _contained(root: Path, relative: str) -> Path:
    from rush.io.physical_paths import ContainmentError, PhysicalRoot

    try:
        return PhysicalRoot(root).open_contained(relative, purpose="read")
    except ContainmentError as exc:
        raise PreferenceError("E_INPUT", "path_not_contained") from exc
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise PreferenceError("E_INPUT", "project_root_invalid") from exc


def _read_optional(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise PreferenceError("E_MIGRATION", "source_corrupt") from exc


def _parse_preference_map(raw: bytes) -> dict[str, Any]:
    """`CASMapTransaction.read` semantics over exact bytes: a `{"version": int >= 0,
    "data": {...}}` object, else `E_MIGRATION source_corrupt` (never a traceback,
    including a parser recursion limit)."""
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise PreferenceError("E_MIGRATION", "source_corrupt") from exc
    if (
        not isinstance(payload, dict)
        or type(payload.get("version")) is not int
        or payload["version"] < 0
        or not isinstance(payload.get("data"), dict)
    ):
        raise PreferenceError("E_MIGRATION", "source_corrupt")
    return dict(payload["data"])


def _preference_db_state(
    root: Path, conn: sqlite3.Connection | None
) -> tuple[dict[str, Any], dict[str, float]]:
    """`origin_id -> parsed content` of every preference origin row and `digest ->
    created_at` of every preference-migration receipt."""

    def read(
        c: sqlite3.Connection,
    ) -> tuple[dict[str, Any], dict[str, float]]:
        origins: dict[str, Any] = {}
        receipts: dict[str, float] = {}
        if sqlite_has_table(c, "memory_artifacts"):
            for origin_id, content in c.execute(
                "SELECT origin_id, content FROM memory_artifacts "
                "WHERE origin_kind = 'preference' AND origin_id IS NOT NULL"
            ).fetchall():
                try:
                    origins[str(origin_id)] = json.loads(content)
                except (TypeError, ValueError, RecursionError):
                    origins[str(origin_id)] = {}
        if sqlite_has_table(c, "mutation_receipts"):
            for operation_id, created_at in c.execute(
                "SELECT operation_id, created_at FROM mutation_receipts "
                "WHERE substr(operation_id, 1, ?) = ?",
                (len(_PREFERENCE_MIGRATION_PREFIX), _PREFERENCE_MIGRATION_PREFIX),
            ).fetchall():
                digest = str(operation_id)[len(_PREFERENCE_MIGRATION_PREFIX) :]
                receipts[digest] = float(created_at)
        return origins, receipts

    if conn is not None:
        return read(conn)
    state = read_sqlite_readonly(root / ".rush" / "memory.db", read)
    return state if state is not None else ({}, {})


def _origin_conflicts(origin: Any, live_value: Any) -> bool:
    if not isinstance(origin, dict) or origin.get("deleted") is True:
        return True
    if "value" not in origin:
        return True
    return _canonical(origin["value"]) != _canonical(sanitize_value(live_value).value)


def _preference_migration_plan(
    project_root: Path, *, conn_or_view: sqlite3.Connection | None = None
) -> dict[str, Any]:
    """D27 plan (read-only; creates nothing). `conn_or_view` reads origin rows and
    receipts through the caller's connection; `None` opens a read-only view.

    Returns `{"preview", "preview_digest", "inserts", "conflicts", "receipt",
    "source_bytes", "source_digest", "source_path"}`; `preview` is the D27 preview
    and `preview_digest == sha256(compact.canonical_json(preview))`."""
    from rush.delivery.compact import canonical_json

    root = _preference_root(project_root)
    rush_dir = root / ".rush"
    source_path = rush_dir / "preferences.json"
    src_bytes: bytes | None = None
    legacy_bytes: bytes | None = None
    hashed: list[tuple[str, bytes]] = []
    if rush_dir.is_dir():
        src_bytes = _read_optional(_contained(root, _PREFERENCE_SOURCE_RELATIVE))
        legacy_bytes = _read_optional(
            _contained(root, _PREFERENCE_LEGACY_BACKUP_RELATIVE)
        )
        try:
            names = sorted(os.listdir(rush_dir))
        except OSError as exc:
            raise PreferenceError("E_MIGRATION", "source_corrupt") from exc
        for name in names:
            match = _PREFERENCE_BACKUP_NAME.match(name)
            if match is None:
                continue
            raw = _read_optional(_contained(root, f".rush/{name}"))
            # A backup whose bytes do not hash to its suffix is ignored.
            if raw is not None and _sha256(raw)[:16] == match.group(1):
                hashed.append((name, raw))
    origins, receipts = _preference_db_state(root, conn_or_view)
    hashed.sort(key=lambda item: (receipts.get(_sha256(item[1]), math.inf), item[0]))
    try:
        live = _parse_preference_map(src_bytes) if src_bytes is not None else {}
        merged: dict[str, Any] = {}
        if legacy_bytes is not None:
            merged.update(_parse_preference_map(legacy_bytes))
        for _name, raw in hashed:
            merged.update(_parse_preference_map(raw))
        merged.update(live)
        inserts = [
            {"key": key, "value": merged[key]}
            for key in sorted(merged)
            if key not in origins
        ]
        conflicts = sorted(
            key
            for key in live
            if key in origins and _origin_conflicts(origins[key], live[key])
        )
        src_digest = _sha256(src_bytes) if src_bytes is not None else None
        preview = {
            "source": {
                "path": _PREFERENCE_SOURCE_RELATIVE,
                "present": src_bytes is not None,
                "digest": src_digest,
            },
            "receipt": "committed"
            if src_digest is not None and src_digest in receipts
            else "absent",
            "inserts": inserts,
            "conflicts": conflicts,
            "publication": "pending" if src_bytes is not None else "none",
            "backups": (
                ["preferences.json.migrated"] if legacy_bytes is not None else []
            )
            + [name for name, _raw in hashed],
        }
        preview_digest = hashlib.sha256(canonical_json(preview)).hexdigest()
    except (RecursionError, TypeError, ValueError) as exc:
        raise PreferenceError("E_MIGRATION", "source_corrupt") from exc
    return {
        "preview": preview,
        "preview_digest": preview_digest,
        "inserts": inserts,
        "conflicts": conflicts,
        "receipt": preview["receipt"],
        "source_bytes": src_bytes,
        "source_digest": src_digest,
        "source_path": source_path,
    }


def _commit_preference_rows(
    root: Path,
    plan: dict[str, Any],
    *,
    owner_scope: Any = None,
    commit_check: Callable[[], tuple[str, str] | None] | None = None,
) -> list[dict[str, Any]]:
    """D27 apply DB step: one `BEGIN IMMEDIATE` inserting every planned key, verifying
    each stored row, writing the `preference-migration:<digest>` receipt (source
    present, no receipt yet), then committing. Any failure rolls back every effect."""
    store = TypedArtifactStore(root)
    inserted: list[tuple[MemoryArtifact, tuple[str, int, str] | None]] = []
    with store._connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            fresh = _preference_migration_plan(root, conn_or_view=conn)
            if fresh["preview_digest"] != plan["preview_digest"]:
                raise PreferenceError("E_VERSION", "preview_changed")
            for item in plan["inserts"]:
                stored, evicted = store._prepare_write(
                    conn,
                    MemoryArtifact(
                        id=str(uuid.uuid4()),
                        family="memory",
                        subject="preference",
                        trust_tier=_LOCAL_TIER,
                        content={"key": item["key"], "value": item["value"]},
                        source=PREFERENCE_MIGRATION_SOURCE,
                        created_at=time.time(),
                        origin_kind="preference",
                        origin_id=item["key"],
                        owner_scope=owner_scope,
                    ),
                )
                store._insert_row(conn, stored)
                inserted.append((stored, evicted))
            for (stored, _evicted), item in zip(inserted, plan["inserts"], strict=True):
                row = conn.execute(
                    "SELECT content FROM memory_artifacts "
                    "WHERE id = ? AND origin_kind = 'preference' AND origin_id = ?",
                    (stored.id, item["key"]),
                ).fetchone()
                expected = sanitize_value(
                    {"key": item["key"], "value": item["value"]}
                ).value
                if row is None or _canonical(json.loads(row[0])) != _canonical(
                    expected
                ):
                    raise PreferenceError("E_MIGRATION", "migration_verify_mismatch")
            ids = [stored.id for stored, _evicted in inserted]
            count = (
                conn.execute(
                    "SELECT COUNT(*) FROM memory_artifacts "
                    "WHERE origin_kind = 'preference' AND id IN "
                    f"({','.join('?' * len(ids))})",
                    ids,
                ).fetchone()[0]
                if ids
                else 0
            )
            if count != len(plan["inserts"]):
                raise PreferenceError("E_MIGRATION", "migration_verify_mismatch")
            if plan["source_bytes"] is not None and plan["receipt"] != "committed":
                store._write_receipt(
                    conn,
                    _PREFERENCE_MIGRATION_PREFIX + plan["source_digest"],
                    None,
                    "preference_migration",
                    None,
                    {
                        "source_path": str(plan["source_path"]),
                        "digest": plan["source_digest"],
                        "stage": "committed",
                        "inserted": plan["inserts"],
                    },
                )
            failure = commit_check() if commit_check is not None else None
            if failure is not None:
                raise PreferenceError(*failure)
        except BaseException:
            conn.rollback()
            raise
        conn.commit()
    for stored, evicted in inserted:
        store._note_inserted(stored, evicted)
    return [dict(item) for item in plan["inserts"]]


def _unlink_quietly(path: Path) -> None:
    # g15 cleanup failure: a failed cleanup never replaces the primary failure.
    try:
        os.unlink(path)
    except OSError:
        pass


def _publish_preference_source(project_root: Path, plan: dict[str, Any]) -> str:
    """D27 verified publication of a committed source: hard-link the exact planned
    bytes to `.migrated.<sha16>`, verify, then unlink the source. Never overwrites a
    backup; never unlinks bytes other than the planned ones."""
    if plan["source_bytes"] is None:
        return "none"
    root = _preference_root(project_root)
    digest = str(plan["source_digest"])
    source = _contained(root, _PREFERENCE_SOURCE_RELATIVE)
    backup = _contained(root, f".rush/preferences.json.migrated.{digest[:16]}")
    current = _read_optional(source)
    if current is None:
        existing = _read_optional(backup)
        if existing is not None and _sha256(existing) == digest:
            return "published"
        raise PreferenceError("E_VERSION", "preview_changed")
    if _sha256(current) != digest:
        raise PreferenceError("E_VERSION", "preview_changed")
    try:
        os.link(source, backup)
    except FileExistsError:
        existing = _read_optional(backup)
        if existing is None or _sha256(existing) != digest:
            raise PreferenceError("E_VERSION", "backup_digest_mismatch") from None
    except OSError as exc:
        raise PreferenceError("E_UNAVAILABLE", "publication_unsupported") from exc
    else:
        linked = _read_optional(backup)
        if linked is None or _sha256(linked) != digest:
            _unlink_quietly(backup)
            raise PreferenceError("E_VERSION", "preview_changed")
    again = _read_optional(source)
    if again is None:
        return "published"
    if _sha256(again) != digest:
        raise PreferenceError("E_VERSION", "preview_changed")
    try:
        os.unlink(source)
    except FileNotFoundError:
        return "published"
    except OSError as exc:
        raise PreferenceError("E_UNAVAILABLE", "publication_unconfirmed") from exc
    return "published"


def _preference_migration_apply(
    project_root: Path,
    *,
    preview_digest: str | None = None,
    require_digest: bool = False,
    owner_scope: Any = None,
    commit_check: Callable[[], tuple[str, str] | None] | None = None,
) -> dict[str, Any]:
    """D27 apply. The caller holds Lock 2 and Lock 4 and has resumed pending
    set/delete publications. Recomputes the plan; `require_digest` (the preference
    route) refuses a missing/changed `preview_digest`; conflicts refuse with zero
    effects; then the DB step (skipped when nothing is to insert and the source's
    receipt is committed) and the verified publication.

    Returns `{"applied": True, "inserted", "inserted_count", "receipt",
    "publication"}`; every refusal raises `PreferenceError`."""
    root = _preference_root(project_root)
    plan = _preference_migration_plan(root)
    if require_digest:
        if preview_digest is None:
            raise PreferenceError("E_INPUT", "preview_digest_required")
        if preview_digest != plan["preview_digest"]:
            raise PreferenceError("E_VERSION", "preview_changed")
    if plan["conflicts"]:
        raise PreferenceError("E_VERSION", "migration_conflict")
    inserted: list[dict[str, Any]] = []
    present = plan["source_bytes"] is not None
    if plan["inserts"] or (present and plan["receipt"] != "committed"):
        inserted = _commit_preference_rows(
            root, plan, owner_scope=owner_scope, commit_check=commit_check
        )
    publication = _publish_preference_source(root, plan)
    return {
        "applied": True,
        "inserted": inserted,
        "inserted_count": len(inserted),
        "receipt": "committed" if present else plan["receipt"],
        "publication": publication,
    }


def _committed_publication_pending(root: Path) -> bool:
    """§3.9: whether a `preference-publication:` receipt is still `committed`
    (read-only; nothing is created)."""

    def read(conn: sqlite3.Connection) -> bool:
        if not sqlite_has_table(conn, "mutation_receipts"):
            return False
        row = conn.execute(
            "SELECT 1 FROM mutation_receipts WHERE substr(operation_id, 1, ?) = ? "
            "AND json_valid(payload) AND json_extract(payload, '$.stage') = "
            "'committed' LIMIT 1",
            (len(_PREFERENCE_PUBLICATION_PREFIX), _PREFERENCE_PUBLICATION_PREFIX),
        ).fetchone()
        return row is not None

    return bool(read_sqlite_readonly(root / ".rush" / "memory.db", read))


@_gated_migration(PREFERENCE_MIGRATION_SOURCE)
def migrate_preference_store(project_root: Path) -> int:
    """Absorbs `.rush/preferences.json` (`PreferenceStore`) into `subject="preference"`
    rows through the D27 core (72-T05): the write gate (Lock 2), then Lock 4, pending
    publication resume, the transactional insert + receipt and the verified
    `.migrated.<sha16>` publication. Returns the inserted row count; conflicts and
    publication failures raise `PreferenceError`."""
    from rush.memory.retrieval import (
        RouteDenial,
        authorize_writer,
        recheck_failure,
        writer_owner,
    )

    root = _preference_root(project_root)
    with authorize_writer(root, PREFERENCE_MIGRATION_SOURCE) as granted:
        if isinstance(granted, RouteDenial):
            return 0
        with preference_source_lock(root):
            if _committed_publication_pending(root):
                from rush.memory.preference_store import (
                    resume_preference_publications,
                )

                resume_preference_publications(root)
            result = _preference_migration_apply(
                root,
                owner_scope=writer_owner(granted),
                commit_check=lambda: recheck_failure(granted),
            )
    return int(result["inserted_count"])


@_gated_migration("migration:invariant_graph")
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


@_gated_migration("migration:merkle_invalidator")
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


@_gated_migration("migration:checkpoint_journal")
def migrate_checkpoint_journal(project_root: Path) -> int:
    """Absorbs `.rush/sessions/*.json` (`CheckpointJournal`) into `family="handoff"` rows."""
    session_dir = project_root / ".rush" / "sessions"
    if not session_dir.exists():
        return 0
    json_files = list(session_dir.glob("*.json"))
    if not json_files:
        return 0
    from rush.memory.checkpoint_journal import CheckpointJournal

    # Ungated: this migration already holds its own writer gate.
    entries = CheckpointJournal(project_root)._list_checkpoints()
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
        if result is not None or replace_origin_content(
            store, "checkpoint", origin_id, entry, created_at=entry.get("created_at")
        ):
            migrated += 1
    for json_file in json_files:
        _rename_migrated(json_file)
    return migrated


@_gated_migration("migration:failure_ledger")
def migrate_failure_ledger(project_root: Path) -> int:
    """Absorbs `.rush/memory/failures.db` (`FailureLedger`) rows into `subject="failure"` rows.

    `failures.db` is never renamed (not in Invariant 5's rename list); only row data is copied.
    """
    db_path = project_root / ".rush" / "memory" / "failures.db"
    if not db_path.exists():
        return 0
    store = TypedArtifactStore(project_root)
    with closing(sqlite3.connect(str(db_path))) as conn, conn:
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


@_gated_migration("migration:patch_memory")
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


@_gated_migration("migration:flight_recorder")
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
            # Ungated: this migration already holds its own writer gate.
            events = recorder._replay_session(session_id)
        except ValueError:
            continue
        for event in events:
            timestamp = event.get("timestamp")
            event_type = event.get("event_type", "")
            origin_id = hashlib.sha256(
                f"{session_id}|{timestamp}|{event_type}".encode()
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


@_gated_migration("migration:hook_signatures")
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


@_gated_migration("migration:session_memory")
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
            f"{record.timestamp}{record.tool_name}{record.summary}".encode()
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
