"""Unified typed-artifact store: WAL-mode SQLite backing every memory subject.

Phase 61 §6.1/§6.3 — `MemoryArtifact` is one row of the unified schema; `TypedArtifactStore`
enforces the no-STATED-on-entry, redact-before-store, recall-rescan, and staleness invariants.
"""

from __future__ import annotations

import dataclasses
import gc
import hashlib
import json
import secrets
import sqlite3
import time
import urllib.parse
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from rush.memory.merkle_invalidator import MerkleInvalidator
from rush.memory.trust import PromotionResult, evaluate_conflict, evaluate_promotion
from rush.safety.redactor import sanitize_value

MemoryFamily = Literal["handoff", "experience", "memory", "skill"]
MemorySubject = Literal[
    "active_context",
    "episodic",
    "preference",
    "failure",
    "architectural_decision",
    "domain_knowledge",
    "skill_pattern",
]
TrustTier = Literal["STATED", "DERIVED", "EXTERNAL_WRITE", "IMPORTED"]

# T18: bookkeeping sources -- internal plumbing that writes memory rows as a
# side effect (flight-recorder/checkpoint-journal producers and their one-time
# migration backfills), never something a project owner asked to remember.
# Exact membership only, no prefix matching: a similarly-named source
# (`flight_recorder:record_event2`) or a different migration target
# (`migration:failure_ledger`) stays useful.
INTERNAL_MEMORY_SOURCES = frozenset(
    {
        "flight_recorder:record_event",
        "checkpoint_journal:save_checkpoint",
        "migration:flight_recorder",
        "migration:checkpoint_journal",
    }
)

#: SQLite's signed 64-bit INTEGER range: a larger Python int raises
#: `OverflowError` at parameter binding, so versions are range-checked first.
SQLITE_INT_MIN = -(2**63)
SQLITE_INT_MAX = 2**63 - 1


def sqlite_integer_in_range(value: int) -> bool:
    return SQLITE_INT_MIN <= value <= SQLITE_INT_MAX


# T19: MemoryArtifact revisions committed inside `collect_committed_writes()`.
# Every store mutator notes a revision only after its transaction commits, so a
# rolled-back or failed write is never reported as written.
_COMMITTED_WRITES: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "rush_memory_committed_writes", default=None
)
# T19: artifact rows a read-only compatibility reader returned to its caller
# inside `collect_memory_reads()`.
_MEMORY_READS: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "rush_memory_reads", default=None
)


@contextmanager
def collect_committed_writes() -> Iterator[list[dict[str, Any]]]:
    """Collect `{id, revision, source, kind}` for every revision committed in
    this block, in commit order."""
    collected: list[dict[str, Any]] = []
    token = _COMMITTED_WRITES.set(collected)
    try:
        yield collected
    finally:
        _COMMITTED_WRITES.reset(token)


@contextmanager
def collect_memory_reads() -> Iterator[list[dict[str, Any]]]:
    """Collect `{id, revision, source}` for every row a read-only
    compatibility reader returned in this block, in read order."""
    collected: list[dict[str, Any]] = []
    token = _MEMORY_READS.set(collected)
    try:
        yield collected
    finally:
        _MEMORY_READS.reset(token)


def note_committed_write(
    artifact_id: str, revision: int, source: str, kind: str
) -> None:
    collected = _COMMITTED_WRITES.get()
    if collected is not None:
        collected.append(
            {"id": artifact_id, "revision": revision, "source": source, "kind": kind}
        )


def note_memory_read(artifact_id: str, revision: int, source: str) -> None:
    collected = _MEMORY_READS.get()
    if collected is not None:
        collected.append({"id": artifact_id, "revision": revision, "source": source})


def is_internal_memory_source(source: str) -> bool:
    """Exact-membership check against `INTERNAL_MEMORY_SOURCES` -- the single
    predicate every useful-memory projection filters by (T18 B1)."""
    return source in INTERNAL_MEMORY_SOURCES


def internal_source_exclusion_sql() -> tuple[str, tuple[str, ...]]:
    """SQL fragment + bound params excluding `INTERNAL_MEMORY_SOURCES` rows,
    built from the same frozenset as `is_internal_memory_source` so the two
    can never drift apart."""
    sources = tuple(sorted(INTERNAL_MEMORY_SOURCES))
    placeholders = ", ".join("?" for _ in sources)
    return f"source NOT IN ({placeholders})", sources


def useful_memory_count(conn: sqlite3.Connection) -> int:
    """R18.1: the internal-exclusion predicate AND `archived_at IS NULL` AND
    `expired_at IS NULL` -- the "useful memory count" T20/T23/T28 share."""
    fragment, params = internal_source_exclusion_sql()
    row = conn.execute(
        f"SELECT COUNT(*) FROM memory_artifacts WHERE {fragment} "
        "AND archived_at IS NULL AND expired_at IS NULL",
        params,
    ).fetchone()
    return int(row[0])


class TrustTierError(ValueError):
    """Raised when write() is given a disallowed trust_tier on insert."""


class VersionConflictError(Exception):
    """Raised when a mutation's `expected_version` doesn't match the row's current version
    (MC01 §6.1 compare-and-swap concurrency check). `.code` is always `"E_VERSION"`."""

    def __init__(self, message: str, *, code: str = "E_VERSION") -> None:
        super().__init__(message)
        self.code = code


class MemoryScopeError(Exception):
    """Raised by `delete_batch()` when a batch member's actual `subject` doesn't match
    the request's declared `scope` (P65-07.3, plan §6.4). Refuses the entire batch,
    matching the stale-revision refusal `VersionConflictError` already enforces."""

    code = "E_SCOPE"


class SignatureMismatchError(Exception):
    """Raised by recall() when a STATED row's signature doesn't match its recomputed content hash."""


class TrojanSourceFoundError(Exception):
    """Raised by recall() when a returned record's content contains Trojan Source Unicode chars."""


class OwnerScopeError(Exception):
    """Raised when a mutation's declared `owner_scope` doesn't match the stored row's owner.

    P69-07 ownership contract subsections e/g/i: an owner mismatch behaves exactly like a
    version mismatch -- reject the whole operation, never silently allow it -- so ownership
    is an enforced boundary rather than a label. Deliberately *not* a `MemoryScopeError`
    subclass: that exception means "wrong `subject`", a completely separate check this
    packet leaves untouched.
    """

    def __init__(self, message: str, *, code: str = "E_OWNER") -> None:
        super().__init__(message)
        self.code = code


class MemoryMigrationRequiredError(Exception):
    """Raised by a read-only preview against a database that predates `artifact_version`.

    P69-07 ownership contract subsection f: a preview (`apply=False`) is genuinely
    read-only, so it can never run the migration a legacy database needs; it reports the
    requirement instead of silently migrating (which would make a "preview" write).
    """


class MemoryStoreUnreadableError(Exception):
    """Raised by a read-only preview when `open_readonly()` reports a non-`None` `state`.
    `.code` is `readonly_state_code(...)`: `E_STORE_CORRUPT` or `E_STORE_BUSY`."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


_READONLY_VIEW_REASONS = {
    "migration_required": (
        "memory.db predates the current schema; reads never migrate it -- run any "
        "`rush memory` write command (for example `rush memory write`) to migrate"
    ),
    "corrupt": "memory.db could not be read: the database file is corrupt",
    "busy": (
        "memory.db could not be read without creating files while a writer is "
        "active; retry"
    ),
}


def readonly_view_reason(state: str) -> str:
    """Human reason for an `open_readonly_view()` state."""
    return _READONLY_VIEW_REASONS[state]


def readonly_state_code(state: str, db: Path) -> str:
    """Error code for an unusable read-only open. A `read_conflict` on a DB that has no
    `-wal` now (no writer appeared) is corruption; anything else is a writer in the way."""
    if state == "read_conflict" and not Path(f"{db}-wal").exists():
        return "E_STORE_CORRUPT"
    return "E_STORE_BUSY"


OwnerScopeKind = Literal["user", "project", "session", "agent"]
_OWNER_SCOPE_KINDS: frozenset[str] = frozenset({"user", "project", "session", "agent"})


@dataclass(frozen=True)
class OwnerScope:
    """Who owns a memory artifact (P69-07 ownership contract).

    Subsection a -- `id` namespace per kind: a `project`-kind `id` is the project
    identifier already used elsewhere; `user`/`agent`/`session`-kind ids are opaque
    caller-supplied strings this phase does not authenticate (no identity provider
    exists yet), so validation here is structural only: a known kind and a non-blank
    string id. Subsection d -- ownership is immutable after write: no mutation in this
    module ever updates a row's owner columns; changing an owner means archiving and
    re-writing, exactly like changing `subject`.
    """

    kind: OwnerScopeKind
    id: str

    def __post_init__(self) -> None:
        if self.kind not in _OWNER_SCOPE_KINDS:
            raise ValueError(
                f"owner_scope kind must be one of {sorted(_OWNER_SCOPE_KINDS)}, "
                f"got {self.kind!r}"
            )
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("owner_scope id must be a non-empty string")

    def as_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "id": self.id}

    @classmethod
    def from_value(cls, value: Any) -> OwnerScope:
        """Build one from an `OwnerScope` or a `{"kind": ..., "id": ...}` mapping
        (the wire shape the tool/HTTP/TUI layers carry). Raises `ValueError` on
        anything else, so a malformed owner can never reach storage."""
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict) or set(value) != {"kind", "id"}:
            raise ValueError(
                "owner_scope must be an object with exactly 'kind' and 'id' keys"
            )
        return cls(value["kind"], value["id"])


def legacy_owner_scope(project_root: Path) -> OwnerScope:
    """The ownership contract's legacy/default owner (subsection c).

    A row migrated from a database that predates `owner_scope` -- and any row written
    without an explicit owner -- belongs to `{kind: "project", id: <that row's own
    project>}`: the most conservative default available, never granting broader access
    than the row already implicitly had. `store.py` has no project registry of its own
    (resolving a registered project's UUID lives in `workflows/projects.py`), so the
    project identity available here is its resolved root path.
    """
    return OwnerScope("project", str(Path(project_root).resolve()))


def _row_value(row: sqlite3.Row, name: str) -> Any:
    """Column value, or `None` when the column doesn't exist on this row at all --
    the real shape of a database opened read-only before any migration has run."""
    return row[name] if name in row.keys() else None  # noqa: SIM118 -- sqlite3.Row


def owner_scope_for_row(row: sqlite3.Row, project_root: Path) -> OwnerScope:
    """This row's owner, falling back to the legacy default (subsection c).

    Public because `open_readonly()` never runs a migration: a read-only caller gets rows
    whose `owner_scope_kind`/`owner_scope_id` columns may not exist yet, and still needs a
    usable owner for every one of them.
    """
    kind = _row_value(row, "owner_scope_kind")
    identifier = _row_value(row, "owner_scope_id")
    if kind and identifier:
        return OwnerScope(kind, identifier)
    return legacy_owner_scope(project_root)


@dataclass(frozen=True)
class MemoryArtifact:
    """One row of the unified typed-artifact schema (§6.1)."""

    id: str
    family: MemoryFamily
    subject: MemorySubject
    trust_tier: TrustTier
    content: dict[str, Any]
    source: str
    created_at: float
    symbol_ref: str | None = None
    content_hash: str | None = None
    corroboration_count: int = 0
    promoted_at: float | None = None
    stale: bool = False
    signature: str | None = None
    origin_kind: str | None = None
    origin_id: str | None = None
    expired: bool = False
    artifact_version: int = 1
    # P69-07 ownership contract. Optional rather than required: 17 `MemoryArtifact(...)`
    # construction sites across 14 production files predate this field, and a required
    # field would break every one of them at construction time. `None` means "no explicit
    # owner declared"; `_prepare_write()` resolves it to `legacy_owner_scope(project_root)`
    # (subsection c) before storage, so a persisted row always has a real owner.
    owner_scope: OwnerScope | None = None


_VERSION_TABLE_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS memory_artifact_versions (
        artifact_id TEXT NOT NULL,
        artifact_version INTEGER NOT NULL,
        content TEXT NOT NULL,
        source TEXT NOT NULL,
        trust_tier TEXT NOT NULL,
        created_at REAL NOT NULL,
        deleted INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (artifact_id, artifact_version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS memory_changes (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        artifact_id TEXT NOT NULL,
        artifact_version INTEGER NOT NULL,
        tombstone INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL,
        subject TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_memory_changes_artifact ON memory_changes(artifact_id)",
)
# Joined form for `executescript()` contexts (fresh-DB `_SCHEMA_SQL`); `upgrade()` instead
# executes `_VERSION_TABLE_STATEMENTS` one at a time via `.execute()`, because
# `executescript()` implicitly commits any pending transaction first — which would silently
# defeat `upgrade()`'s rollback-on-failure guarantee (MC01 §6.1).
_VERSION_TABLES_SQL = ";\n".join(_VERSION_TABLE_STATEMENTS) + ";"

# MC02 §9.0 scoped-candidate index: a *second*, additive FTS5 table alongside the existing
# single-column `memory_fts` (never repurposed — `search()`/`recall()` keep querying it
# unchanged, so legacy ranking/behavior can't regress). Contextual fields are extracted from
# `content` at write time so `search_candidates()` can rank/weight them separately from the
# raw `body`, per the fixed §9.0 column order and BM25 weights (4, 8, 8, 6, 3, 1).
# `json_valid()` guards every `json_extract()` so a malformed `content` value (a corrupt
# candidate, e.g. a row inserted outside `write()`) degrades to an empty contextual field
# instead of aborting the triggering INSERT/UPDATE/DELETE.
_CANDIDATE_FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts_candidates USING fts5(
    title, symbol_path, error_signature, behavior_id, dependency_identity, body,
    content='memory_artifacts', content_rowid='rowid'
);
CREATE TRIGGER IF NOT EXISTS memory_artifacts_candidates_ai AFTER INSERT ON memory_artifacts BEGIN
    INSERT INTO memory_fts_candidates(rowid, title, symbol_path, error_signature, behavior_id, dependency_identity, body)
    VALUES (
        new.rowid,
        CASE WHEN json_valid(new.content) THEN COALESCE(json_extract(new.content, '$.title'), '') ELSE '' END,
        COALESCE(new.symbol_ref, ''),
        CASE WHEN json_valid(new.content) THEN COALESCE(json_extract(new.content, '$.error_signature'), '') ELSE '' END,
        CASE WHEN json_valid(new.content) THEN COALESCE(json_extract(new.content, '$.behavior_id'), '') ELSE '' END,
        CASE WHEN json_valid(new.content) THEN COALESCE(json_extract(new.content, '$.dependency_identity'), '') ELSE '' END,
        new.content
    );
END;
CREATE TRIGGER IF NOT EXISTS memory_artifacts_candidates_ad AFTER DELETE ON memory_artifacts BEGIN
    INSERT INTO memory_fts_candidates(memory_fts_candidates, rowid, title, symbol_path, error_signature, behavior_id, dependency_identity, body)
    VALUES (
        'delete', old.rowid,
        CASE WHEN json_valid(old.content) THEN COALESCE(json_extract(old.content, '$.title'), '') ELSE '' END,
        COALESCE(old.symbol_ref, ''),
        CASE WHEN json_valid(old.content) THEN COALESCE(json_extract(old.content, '$.error_signature'), '') ELSE '' END,
        CASE WHEN json_valid(old.content) THEN COALESCE(json_extract(old.content, '$.behavior_id'), '') ELSE '' END,
        CASE WHEN json_valid(old.content) THEN COALESCE(json_extract(old.content, '$.dependency_identity'), '') ELSE '' END,
        old.content
    );
END;
CREATE TRIGGER IF NOT EXISTS memory_artifacts_candidates_au AFTER UPDATE ON memory_artifacts BEGIN
    INSERT INTO memory_fts_candidates(memory_fts_candidates, rowid, title, symbol_path, error_signature, behavior_id, dependency_identity, body)
    VALUES (
        'delete', old.rowid,
        CASE WHEN json_valid(old.content) THEN COALESCE(json_extract(old.content, '$.title'), '') ELSE '' END,
        COALESCE(old.symbol_ref, ''),
        CASE WHEN json_valid(old.content) THEN COALESCE(json_extract(old.content, '$.error_signature'), '') ELSE '' END,
        CASE WHEN json_valid(old.content) THEN COALESCE(json_extract(old.content, '$.behavior_id'), '') ELSE '' END,
        CASE WHEN json_valid(old.content) THEN COALESCE(json_extract(old.content, '$.dependency_identity'), '') ELSE '' END,
        old.content
    );
    INSERT INTO memory_fts_candidates(rowid, title, symbol_path, error_signature, behavior_id, dependency_identity, body)
    VALUES (
        new.rowid,
        CASE WHEN json_valid(new.content) THEN COALESCE(json_extract(new.content, '$.title'), '') ELSE '' END,
        COALESCE(new.symbol_ref, ''),
        CASE WHEN json_valid(new.content) THEN COALESCE(json_extract(new.content, '$.error_signature'), '') ELSE '' END,
        CASE WHEN json_valid(new.content) THEN COALESCE(json_extract(new.content, '$.behavior_id'), '') ELSE '' END,
        CASE WHEN json_valid(new.content) THEN COALESCE(json_extract(new.content, '$.dependency_identity'), '') ELSE '' END,
        new.content
    );
END;
"""

# MC02 §9.0 cursor integrity key: one random 256-bit key per store, created only when a
# write-authorized `TypedArtifactStore` is constructed (never by `open_readonly()`, whose
# connection is SQLite `mode=ro` and would simply fail the `INSERT` below). `recall_page()`
# cursors are HMAC-signed with this key so a cursor can't be forged or replayed across stores.
_CURSOR_KEY_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS memory_cursor_key (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    key BLOB NOT NULL
);
"""

# MC03 §6.3 evidence edges: a new, additive table (`rush.memory.relations` owns the
# read/write logic; this module only owns the schema, per the phase-63 file map). Endpoints
# are versioned (`source_id`/`source_version`, `target_id`/`target_version`) rather than
# pointing at "the current row", so an edge's target can go stale independently of
# `memory_artifacts` being mutated — `related_artifacts()` detects that by comparing the
# recorded version against `get_current()`. `sequence` is the append-only creation order used
# for provenance; `origin_ref` is an optional free-text originating observation/user reference.
_RELATIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS memory_relations (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    source_version INTEGER NOT NULL,
    target_id TEXT NOT NULL,
    target_version INTEGER NOT NULL,
    kind TEXT NOT NULL,
    origin_ref TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_relations_source ON memory_relations(source_id);
CREATE INDEX IF NOT EXISTS idx_memory_relations_target ON memory_relations(target_id);
"""

# MC10 §9.0 last-success index: namespace/behavior/runtime-platform-digest -> the exact
# observation artifact id/version that pointer currently names. An *index* over evidence,
# never a second source of truth -- the only writer is `TypedArtifactStore.write_pass()`,
# and only inside the same transaction as the passing observation it points at ("Only an
# observed pass of that behavior updates its pointer transactionally").
_BEHAVIOR_SUCCESS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS memory_behavior_success (
    namespace TEXT NOT NULL,
    behavior_id TEXT NOT NULL,
    runtime_digest TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    artifact_version INTEGER NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (namespace, behavior_id, runtime_digest)
);
"""

# MC11 §9.0 restricted-receiver handoff: a session descriptor (root/audience/grants/budgets,
# hashed capability, TTL) plus a per-(session, artifact) acknowledgement receipt. Additive
# only -- no existing table touched. `rush.memory.handoff` owns all read/write logic; this
# module only owns the schema, per the phase-63 file map.
_HANDOFF_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS memory_handoff_sessions (
    session_id TEXT PRIMARY KEY,
    root TEXT NOT NULL,
    audience TEXT NOT NULL,
    capability_hash TEXT NOT NULL,
    granted_ids TEXT NOT NULL,
    session_allowlist TEXT NOT NULL,
    constraints TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    revoked_at REAL
);
CREATE TABLE IF NOT EXISTS memory_handoff_receipts (
    session_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    acknowledged_version INTEGER NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL,
    PRIMARY KEY (session_id, artifact_id)
);
"""

# MC12 §6.7 versioned embedding cache: one row per (artifact, version, embedded content
# hash, model digest, chunking version) -- any of those four changing invalidates the prior
# vector rather than reusing it silently. Additive only -- no existing table touched.
# `rush.memory.retrieval.hybrid_candidates()` owns all read/write logic; this module only
# owns the schema and row accessors, per the phase-63 file map.
_EMBEDDING_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS memory_embeddings (
    namespace TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    artifact_version INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    model_digest TEXT NOT NULL,
    chunking_version TEXT NOT NULL,
    dimension INTEGER NOT NULL,
    vector TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (namespace, artifact_id, artifact_version, content_hash, model_digest, chunking_version)
);
"""

# P69-01.2f: per-operation-kind recovery receipts. Written inside the exact same
# transaction as the effect itself (write()/edit()/archive()/delete_batch()/promote()/
# create_handoff_session() each pass their own open connection through), keyed by the
# dashboard MutationLedger's preallocated operation_id -- a receipt existing means that
# specific operation committed, regardless of what any other request did to the artifact
# afterward; absent means never committed, resume as never-attempted.
_MUTATION_RECEIPTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS mutation_receipts (
    operation_id TEXT PRIMARY KEY,
    artifact_id TEXT,
    kind TEXT NOT NULL,
    revision INTEGER,
    payload TEXT,
    created_at REAL NOT NULL
);
"""

_SCHEMA_SQL = (
    """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS memory_artifacts (
    id TEXT PRIMARY KEY,
    family TEXT NOT NULL,
    subject TEXT NOT NULL,
    trust_tier TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at REAL NOT NULL,
    symbol_ref TEXT,
    content_hash TEXT,
    corroboration_count INTEGER NOT NULL DEFAULT 0,
    promoted_at REAL,
    stale INTEGER NOT NULL DEFAULT 0,
    signature TEXT,
    origin_kind TEXT,
    origin_id TEXT,
    expires_at REAL,
    expired_at REAL,
    expired_by TEXT,
    artifact_version INTEGER NOT NULL DEFAULT 1,
    archived_at REAL,
    owner_scope_kind TEXT,
    owner_scope_id TEXT,
    orphaned_at REAL
);
CREATE INDEX IF NOT EXISTS idx_memory_subject ON memory_artifacts(subject);
CREATE INDEX IF NOT EXISTS idx_memory_trust ON memory_artifacts(trust_tier);
CREATE INDEX IF NOT EXISTS idx_memory_symbol ON memory_artifacts(symbol_ref);
CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_origin ON memory_artifacts(origin_kind, origin_id) WHERE origin_kind IS NOT NULL AND origin_id IS NOT NULL;
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(content, content='memory_artifacts', content_rowid='rowid');
CREATE TRIGGER IF NOT EXISTS memory_artifacts_ai AFTER INSERT ON memory_artifacts BEGIN
    INSERT INTO memory_fts(rowid, content) VALUES (new.rowid, new.content);
END;
CREATE TRIGGER IF NOT EXISTS memory_artifacts_ad AFTER DELETE ON memory_artifacts BEGIN
    INSERT INTO memory_fts(memory_fts, rowid, content) VALUES ('delete', old.rowid, old.content);
END;
CREATE TRIGGER IF NOT EXISTS memory_artifacts_au AFTER UPDATE ON memory_artifacts BEGIN
    INSERT INTO memory_fts(memory_fts, rowid, content) VALUES ('delete', old.rowid, old.content);
    INSERT INTO memory_fts(rowid, content) VALUES (new.rowid, new.content);
END;
"""
    + _VERSION_TABLES_SQL
    + _CANDIDATE_FTS_SQL
    + _CURSOR_KEY_TABLE_SQL
    + _RELATIONS_TABLE_SQL
    + _BEHAVIOR_SUCCESS_TABLE_SQL
    + _HANDOFF_TABLES_SQL
    + _EMBEDDING_TABLE_SQL
    + _MUTATION_RECEIPTS_TABLE_SQL
)

_INSERT_SQL = """
INSERT INTO memory_artifacts (
    id, family, subject, trust_tier, content, source, created_at,
    symbol_ref, content_hash, corroboration_count, promoted_at, stale,
    signature, origin_kind, origin_id, artifact_version,
    owner_scope_kind, owner_scope_id
) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
"""


def compute_content_signature(content: dict[str, Any]) -> str:
    """Deterministic SHA-256 over a content dict, used for STATED-row signature verification."""
    payload = json.dumps(content, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _write_version(
    conn: sqlite3.Connection,
    artifact_id: str,
    *,
    content: dict[str, Any],
    source: str,
    trust_tier: str,
    expected_version: int | None,
    tombstone: bool = False,
    subject: str | None = None,
) -> int:
    """Atomically advances `artifact_id`'s version inside the caller's transaction (MC01 §6.1).

    Caller must already hold the write lock (`BEGIN IMMEDIATE`) and is responsible for
    persisting the returned version (and any other changed columns) onto `memory_artifacts`
    in the same transaction; this only appends the `memory_artifact_versions`/`memory_changes`
    audit rows and enforces the optimistic-concurrency check. Raises `KeyError` if the artifact
    doesn't exist, or `VersionConflictError` (`code="E_VERSION"`) if `expected_version` is given
    and doesn't match the row's current `artifact_version`.

    `subject` (P65-07.3) is optional, minimal, non-content provenance recorded onto the
    `memory_changes` row only -- it lets `list_deleted_refs()` show *what kind* of artifact a
    tombstoned id used to be without retaining any of its deleted content. Callers that don't
    care (every pre-P65-07 call site) simply omit it and get `NULL`, unchanged behavior.
    """
    row = conn.execute(
        "SELECT artifact_version FROM memory_artifacts WHERE id = ?", (artifact_id,)
    ).fetchone()
    if row is None:
        raise KeyError(artifact_id)
    current_version = row[0]
    if expected_version is not None and current_version != expected_version:
        raise VersionConflictError(
            f"artifact {artifact_id!r} expected version {expected_version}, "
            f"found {current_version}"
        )
    new_version = current_version + 1
    now = time.time()
    conn.execute(
        "INSERT INTO memory_artifact_versions "
        "(artifact_id, artifact_version, content, source, trust_tier, created_at, deleted) "
        "VALUES (?,?,?,?,?,?,?)",
        (
            artifact_id,
            new_version,
            json.dumps(content),
            source,
            trust_tier,
            now,
            int(tombstone),
        ),
    )
    conn.execute(
        "INSERT INTO memory_changes (artifact_id, artifact_version, tombstone, created_at, subject) "
        "VALUES (?,?,?,?,?)",
        (artifact_id, new_version, int(tombstone), now, subject),
    )
    return new_version


def _inspect_text_for_trojan_chars(text: str) -> list[str]:
    """Trojan Source scan over an in-memory string, reusing BIDI_CHARS (not re-implementing it).

    Lazy/function-local import: `rush.hook`'s package `__init__` transitively imports
    `rush.tools` -> `rush.continuity` -> `rush.memory.checkpoint_journal` -> `rush.memory.migration`
    -> back to this module, so importing `rush.hook.trojan_source` at module load time makes
    `rush.memory.store` circular. Deferring it here breaks the cycle at its real entry point.
    """
    from rush.hook.trojan_source import BIDI_CHARS

    findings = []
    for idx, line in enumerate(text.splitlines() or [text], start=1):
        for ch in BIDI_CHARS:
            if ch in line:
                findings.append(
                    f"line {idx}: Dangerous Trojan Source Unicode character detected (U+{ord(ch):04X})."
                )
    return findings


def _handoff_blob_relpath(artifact_id: str, family: str) -> str | None:
    """P65-07.3: only `family="handoff"` artifacts written by `build_handoff()`'s
    `scan-handoff-<uuid>` id convention have a companion Rush-owned blob file on disk
    (`.rush/handoffs/<uuid>.json`, `rush.workflows.project_run._handoff_path`) -- every
    other family's content lives solely in this row, so it has no blob to remove.
    Returns a project-root-relative path, never an absolute or external one."""
    prefix = "scan-handoff-"
    if family != "handoff" or not artifact_id.startswith(prefix):
        return None
    return f".rush/handoffs/{artifact_id[len(prefix) :]}.json"


def _row_to_artifact(
    row: sqlite3.Row, *, default_owner_scope: OwnerScope | None = None
) -> MemoryArtifact:
    owner_scope = None
    kind = _row_value(row, "owner_scope_kind")
    identifier = _row_value(row, "owner_scope_id")
    if kind and identifier:
        owner_scope = OwnerScope(kind, identifier)
    elif default_owner_scope is not None:
        owner_scope = default_owner_scope
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
        origin_kind=row["origin_kind"],
        origin_id=row["origin_id"],
        expired=row["expired_at"] is not None,
        artifact_version=row["artifact_version"],
        owner_scope=owner_scope,
    )


@dataclass(frozen=True)
class ReadOnlyOpenResult:
    """Result of `open_sqlite_readonly` / `TypedArtifactStore.open_readonly` (MC01 §6.1):
    never creates a DB, directory, or `-wal`/`-shm` sidecar.

    `mode` is the SQLite URI mode actually used (`"ro"` or `"ro&immutable=1"`).
    `consistency` is `"last_checkpoint"` for an immutable open (committed data still in
    a `-wal` is not visible, but no `-wal` existed at open time). `state` is `None` on a
    usable open, `"read_conflict"` when an immutable read raised `sqlite3.DatabaseError`
    (corrupt, or changed underneath the read), or `"wal_index_missing"` when a `-wal`
    exists without its `-shm` (reading it would create the `-shm`)."""

    available: bool
    migration_required: bool = False
    connection: sqlite3.Connection | None = None
    mode: str | None = None
    consistency: str | None = None
    state: str | None = None


def open_sqlite_readonly(db: Path) -> ReadOnlyOpenResult:
    """W4 X2 shared read-only SQLite opener (memory, ledger, telemetry readers).

    - `db` missing: `available=False`, no I/O beyond the existence check.
    - `<db>-wal` exists (a writer is, or was, connected): `mode=ro`. Both sidecars
      already exist, so nothing is created, and reads see a transactional snapshot.
      A `-wal` without its `-shm` would force SQLite to create the `-shm`, so that
      case returns `state="wal_index_missing"` with no connection.
    - Otherwise: `mode=ro&immutable=1`, which never creates a sidecar. Each table's
      first row is read once (cost bounded by the table count, never the DB size); a
      `sqlite3.DatabaseError` from that read returns `state="read_conflict"` with no
      connection. Never retried in a mode that could create sidecars. Corruption deeper
      in a table surfaces as the `DatabaseError` of the caller's own read.
    """
    if not db.exists():
        return ReadOnlyOpenResult(available=False)
    quoted = urllib.parse.quote(str(db))
    if Path(f"{db}-wal").exists():
        if not Path(f"{db}-shm").exists():
            return ReadOnlyOpenResult(
                available=True, mode="ro", state="wal_index_missing"
            )
        conn = sqlite3.connect(f"file:{quoted}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return ReadOnlyOpenResult(available=True, connection=conn, mode="ro")
    mode = "ro&immutable=1"
    conn = sqlite3.connect(f"file:{quoted}?mode={mode}", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND sql NOT LIKE 'CREATE VIRTUAL%'"
        ).fetchall()
        for (name,) in tables:
            quoted_name = name.replace('"', '""')
            conn.execute(f'SELECT * FROM "{quoted_name}" LIMIT 1').fetchall()
    except sqlite3.DatabaseError:
        conn.close()
        return ReadOnlyOpenResult(
            available=False,
            mode=mode,
            consistency="last_checkpoint",
            state="read_conflict",
        )
    return ReadOnlyOpenResult(
        available=True, connection=conn, mode=mode, consistency="last_checkpoint"
    )


def store_generation(conn: sqlite3.Connection) -> int:
    """MC02 §9.0 "store generation" over an already-open connection: the latest
    `memory_changes` sequence number, or 0 when that table does not exist yet (an
    older read-compatible DB opened read-only, which no migration has touched)."""
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='memory_changes'"
    ).fetchone()
    if exists is None:
        return 0
    row = conn.execute(
        "SELECT COALESCE(MAX(sequence), 0) FROM memory_changes"
    ).fetchone()
    return int(row[0])


def _sqlite_fingerprint(db: Path) -> tuple[int, int, int] | None:
    try:
        st = db.stat()
    except FileNotFoundError:
        return None
    return (st.st_ino, st.st_size, st.st_mtime_ns)


def _unchanged_since(db: Path, fingerprint: tuple[int, int, int]) -> bool:
    return not Path(f"{db}-wal").exists() and _sqlite_fingerprint(db) == fingerprint


def read_sqlite_readonly[T](
    db: Path,
    read: Callable[[sqlite3.Connection], T],
    *,
    attempts: int = 3,
) -> T | None:
    """X1 (T10): run `read` over one `open_sqlite_readonly` connection, leaving no
    `-wal`/`-shm` and no byte change behind. `None` when `db` is missing.

    An immutable open (no `-wal` present) records `(st_ino, st_size, st_mtime_ns)`
    before the read and re-checks it, and that no `-wal` appeared, after the read; a
    change retries, up to `attempts` in total, then raises `E_STORE_BUSY`. An unusable
    open (`wal_index_missing`, or a `read_conflict` on an unchanged file) raises
    `MemoryStoreUnreadableError` with `readonly_state_code`. Nothing is ever migrated.
    """
    if Path(f"{db}-wal").exists():
        # ponytail: this process's own leaked writers (`with self._connect()` commits
        # but never closes) are collected first, so they checkpoint and remove their
        # WAL now, not mid-read -- a read-only connection that closes last cannot
        # checkpoint and would strand committed pages in the `-wal`. Ceiling: a
        # writer in another process can still close first; closing every writer
        # connection deterministically is the upgrade.
        gc.collect()
    for _ in range(attempts):
        before = _sqlite_fingerprint(db)
        if before is None:
            return None
        opened = open_sqlite_readonly(db)
        conn = opened.connection
        immutable = opened.mode == "ro&immutable=1"
        if conn is None:
            if opened.state is None:
                return None
            if immutable and not _unchanged_since(db, before):
                continue
            raise MemoryStoreUnreadableError(
                f"{db} cannot be read without writing ({opened.state}); retry",
                code=readonly_state_code(opened.state, db),
            )
        try:
            value = read(conn)
        except sqlite3.DatabaseError as exc:
            if immutable and not _unchanged_since(db, before):
                continue
            raise MemoryStoreUnreadableError(
                f"{db} could not be read: {exc}",
                code=readonly_state_code("read_conflict", db),
            ) from exc
        finally:
            conn.close()
        if not immutable or _unchanged_since(db, before):
            return value
    raise MemoryStoreUnreadableError(
        f"{db} kept changing during a read-only read; retry", code="E_STORE_BUSY"
    )


def sqlite_has_table(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
        ).fetchone()
        is not None
    )


def artifact_version_sources(
    project_root: Path, refs: Iterable[tuple[str, int]]
) -> dict[tuple[str, int], str]:
    """T19: the recorded `source` of each exact `(artifact_id, version)`, read
    from the append-only version history through one `read_sqlite_readonly`
    connection (nothing is created or migrated). A ref with no stored version,
    or an unreadable store, is absent from the result."""
    wanted = [ref for ref in dict.fromkeys(refs) if sqlite_integer_in_range(ref[1])]
    if not wanted:
        return {}

    def read(conn: sqlite3.Connection) -> dict[tuple[str, int], str]:
        if not sqlite_has_table(conn, "memory_artifact_versions"):
            return {}
        found: dict[tuple[str, int], str] = {}
        for artifact_id, version in wanted:
            row = conn.execute(
                "SELECT source FROM memory_artifact_versions "
                "WHERE artifact_id = ? AND artifact_version = ?",
                (artifact_id, version),
            ).fetchone()
            if row is not None:
                found[(artifact_id, version)] = row[0]
        return found

    db = Path(project_root).resolve() / ".rush" / "memory.db"
    try:
        return read_sqlite_readonly(db, read) or {}
    except MemoryStoreUnreadableError:
        return {}


class TypedArtifactStore:
    """WAL-mode SQLite store for `MemoryArtifact` rows across every memory subject."""

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = (
            Path(project_root).resolve() if project_root else Path.cwd().resolve()
        )
        self.db_path = self.project_root / ".rush" / "memory.db"
        self._owner_scope_default = legacy_owner_scope(self.project_root)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._merkle = MerkleInvalidator(project_root=self.project_root)
        self._init_db()

    _readonly_conn: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        if self._readonly_conn is not None:
            return self._readonly_conn
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            candidate_fts_existed = (
                conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' "
                    "AND name='memory_fts_candidates'"
                ).fetchone()
                is not None
            )
            conn.executescript(_SCHEMA_SQL)
            self._migrate_expiry_columns(conn)
            self._migrate_version_column(conn)
            self._migrate_changes_subject_column(conn)
            self._migrate_archived_column(conn)
            self._migrate_owner_scope_columns(conn)
            self._migrate_handoff_recovery_columns(conn)
            self._ensure_cursor_key(conn)
            if not candidate_fts_existed:
                self._backfill_candidate_fts(conn)
            conn.commit()

    def _ensure_cursor_key(self, conn: sqlite3.Connection) -> None:
        """MC02 §9.0: creates this store's cursor-signing key exactly once (idempotent via
        `INSERT OR IGNORE`), only reachable from a write-authorized `_init_db()` call."""
        conn.execute(
            "INSERT OR IGNORE INTO memory_cursor_key (id, key) VALUES (1, ?)",
            (secrets.token_bytes(32),),
        )

    def _backfill_candidate_fts(self, conn: sqlite3.Connection) -> None:
        """MC02 §9.0: `memory_fts_candidates` triggers only fire on new writes, so a DB that
        predates this table needs its pre-existing rows indexed once (mirrors
        `_migrate_version_column`'s additive-migration pattern); the caller (`_init_db()`)
        only invokes this the first time it sees the table didn't already exist, so it never
        re-scans a store that MC02 has already been indexing all along.

        Deliberately a Python-side loop with per-row `INSERT OR IGNORE`, not one
        `INSERT ... SELECT ... FROM memory_artifacts` (with or without a `WHERE rowid NOT IN
        (SELECT rowid FROM memory_fts_candidates)` guard): SQLite's query planner can't
        resolve *any* plain (non-MATCH) read of an external-content FTS5 table —
        `OperationalError: no such column: T.title` — because `memory_fts_candidates`'s
        declared columns (title, symbol_path, ...) don't name-match `memory_artifacts`'s real
        columns; reproduced directly against a throwaway `:memory:` DB before landing this.
        """
        pending = conn.execute(
            "SELECT rowid, content, symbol_ref FROM memory_artifacts"
        ).fetchall()
        for rowid, content, symbol_ref in pending:
            title = error_signature = behavior_id = dependency_identity = ""
            try:
                parsed = json.loads(content)
            except (TypeError, json.JSONDecodeError):
                parsed = None
            if isinstance(parsed, dict):
                title = str(parsed.get("title") or "")
                error_signature = str(parsed.get("error_signature") or "")
                behavior_id = str(parsed.get("behavior_id") or "")
                dependency_identity = str(parsed.get("dependency_identity") or "")
            conn.execute(
                "INSERT OR IGNORE INTO memory_fts_candidates"
                "(rowid, title, symbol_path, error_signature, behavior_id, dependency_identity, body) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    rowid,
                    title,
                    symbol_ref or "",
                    error_signature,
                    behavior_id,
                    dependency_identity,
                    content,
                ),
            )

    def cursor_key(self) -> bytes:
        """MC02 §9.0: this store's per-workspace cursor-signing key (`retrieval.py` HMACs
        `recall_page()` continuation cursors with it)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT key FROM memory_cursor_key WHERE id = 1"
            ).fetchone()
        return bytes(row["key"])

    def current_generation(self, conn: sqlite3.Connection | None = None) -> int:
        """MC02 §9.0 "store generation": the latest `memory_changes` sequence number. A
        `recall_page()` cursor binds this; any write between pages changes it, forcing
        `E_RESTART` instead of silently paging over a mutated candidate set.

        P69-01.2n: an already-open `conn` runs this query inside the caller's own
        transaction instead of opening a second connection -- required by
        `snapshot_memories()`'s atomic (memories, generation) read."""
        if conn is not None:
            return store_generation(conn)
        with self._connect() as own_conn:
            return store_generation(own_conn)

    def snapshot_memories(
        self, owner_filter: str | None = None, *, include_internal: bool = False
    ) -> tuple[list[dict[str, Any]], int]:
        """P69-01.2n shared primitive: reads the memory inventory and calls
        `current_generation()` inside the same read transaction/connection,
        returning `(memories, generation)` as one atomic pair -- never a
        memory list from before a generation bump paired with the bumped
        generation, or vice versa.

        T18: bookkeeping rows (`is_internal_memory_source`) are excluded by
        default -- diagnostic `include_internal=True` restores exactly the
        pre-T18 row set."""
        with self._connect() as conn:
            conn.execute("BEGIN")
            rows = conn.execute(
                "SELECT id, subject, trust_tier, source, artifact_version, archived_at "
                "FROM memory_artifacts ORDER BY id ASC"
            ).fetchall()
            generation = self.current_generation(conn)
            conn.commit()
        memories = [
            {
                "id": row["id"],
                "subject": row["subject"],
                "trust_tier": row["trust_tier"],
                "source": row["source"],
                "artifact_version": row["artifact_version"],
                "archived": row["archived_at"] is not None,
            }
            for row in rows
            if (owner_filter is None or row["source"] == owner_filter)
            and (include_internal or not is_internal_memory_source(row["source"]))
        ]
        return memories, generation

    def _write_receipt(
        self,
        conn: sqlite3.Connection,
        operation_id: str,
        artifact_id: str | None,
        kind: str,
        revision: int | None,
        payload: dict[str, Any],
    ) -> None:
        """P69-01.2f: caller owns the transaction -- this only inserts."""
        conn.execute(
            "INSERT OR REPLACE INTO mutation_receipts "
            "(operation_id, artifact_id, kind, revision, payload, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (
                operation_id,
                artifact_id,
                kind,
                revision,
                json.dumps(payload),
                time.time(),
            ),
        )

    def get_receipt(self, operation_id: str) -> dict[str, Any] | None:
        """P69-01.2f recovery read: `None` means this operation id never
        committed its effect."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM mutation_receipts WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "operation_id": row["operation_id"],
            "artifact_id": row["artifact_id"],
            "kind": row["kind"],
            "revision": row["revision"],
            "payload": json.loads(row["payload"]),
            "created_at": row["created_at"],
        }

    def search_candidates(
        self,
        subject: MemorySubject,
        query: str,
        *,
        source_allowlist: Iterable[str],
        trust_tiers: Iterable[str] | None = None,
        include_expired: bool = False,
        scan_offset: int = 0,
        scan_limit: int = 64,
    ) -> list[sqlite3.Row]:
        """MC02 §9.0 scoped candidate query, filtered before rank/LIMIT: subject, source
        allowlist, trust eligibility and expiry. "Repository namespace" scoping (§6.2) is the
        whole store — one `memory.db` per project root — so there is exactly one namespace to
        scope to here; no separate namespace column exists to filter on.

        Ranked over `memory_fts_candidates` using the §9.0 fixed BM25 weights (title=4,
        symbol_path=8, error_signature=8, behavior_id=6, dependency_identity=3, body=1) with
        artifact-ID ascending as the deterministic tie-break. `query` is wrapped as a literal
        FTS5 phrase so operator/quote characters can't be used to build unintended FTS syntax
        ("malformed FTS input produces a validation error, not raw SQL execution").

        Returns raw `sqlite3.Row`s (never `MemoryArtifact`s) via `fetchmany(scan_limit)` —
        never `fetchall()` — so a caller can detect and skip corrupt candidates (rows whose
        `content` fails to `json.loads`) without one bad row aborting the whole batch, and so
        the compact-recall path never materializes more than one 64-row batch at a time.
        """
        sources = list(source_allowlist)
        if not sources:
            return []
        quoted_query = '"' + query.replace('"', '""') + '"'
        clauses = [
            "memory_fts_candidates MATCH ?",
            "ma.subject = ?",
            f"ma.source IN ({','.join('?' for _ in sources)})",
        ]
        params: list[Any] = [quoted_query, subject, *sources]
        tiers = list(trust_tiers) if trust_tiers is not None else []
        if tiers:
            clauses.append(f"ma.trust_tier IN ({','.join('?' for _ in tiers)})")
            params.extend(tiers)
        if not include_expired:
            clauses.append("ma.expired_at IS NULL")
        params.extend([scan_limit, scan_offset])
        sql = (
            "SELECT ma.* FROM memory_artifacts ma "
            "JOIN memory_fts_candidates fc ON fc.rowid = ma.rowid "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY bm25(memory_fts_candidates, 4.0, 8.0, 8.0, 6.0, 3.0, 1.0) ASC, ma.id ASC "
            "LIMIT ? OFFSET ?"
        )
        with self._connect() as conn:
            cur = conn.execute(sql, params)
            return cur.fetchmany(scan_limit)

    def scope_artifacts(
        self,
        subject: MemorySubject,
        *,
        source_allowlist: Iterable[str],
        trust_tiers: Iterable[str] | None = None,
        include_expired: bool = False,
        include_archived: bool = False,
        scan_offset: int = 0,
        scan_limit: int = 512,
    ) -> list[sqlite3.Row]:
        """MC12 §6.7 hybrid-retrieval candidate scope: the same subject/source/trust/expiry
        filters `search_candidates()` applies, without requiring an FTS text match -- vector
        similarity ranks these, so a candidate a lexical query would never match (no shared
        terms) is still eligible to be embedded and recovered by cosine rank. Ordered by ID
        for a deterministic, boundable scan (never BM25 order, which doesn't apply here).

        P69-07 subsection g: `include_archived=False` (the default) excludes archived rows,
        matching `search()`'s existing `include_archived` precedent -- this method predated
        that filter entirely, letting an archived record leak into an ordinary browse.
        `scan_offset` (mirrors `search_candidates()`'s own offset/limit pair) lets a caller
        page past one `scan_limit`-sized batch instead of being permanently capped at it."""
        sources = list(source_allowlist)
        if not sources:
            return []
        clauses = ["subject = ?", f"source IN ({','.join('?' for _ in sources)})"]
        params: list[Any] = [subject, *sources]
        tiers = list(trust_tiers) if trust_tiers is not None else []
        if tiers:
            clauses.append(f"trust_tier IN ({','.join('?' for _ in tiers)})")
            params.extend(tiers)
        if not include_expired:
            clauses.append("expired_at IS NULL")
        if not include_archived:
            clauses.append("archived_at IS NULL")
        params.extend([scan_limit, scan_offset])
        sql = (
            "SELECT * FROM memory_artifacts "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY id ASC LIMIT ? OFFSET ?"
        )
        with self._connect() as conn:
            cur = conn.execute(sql, params)
            return cur.fetchmany(scan_limit)

    def list_artifact_refs(self) -> list[sqlite3.Row]:
        """P65-07.2 project-evidence listing: every *live* artifact's metadata across
        every subject, deliberately excluding `content` -- a generic reference view can
        never leak a secret embedded in stored content because it never reads that column
        (plan §6.4: "Redacted views never expose secrets from raw storage")."""
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT id, family, subject, trust_tier, source, created_at, "
                "artifact_version FROM memory_artifacts ORDER BY id ASC"
            )
            return cur.fetchall()

    def list_deleted_refs(self) -> list[dict[str, Any]]:
        """P65-07.2/.3: minimal, content-free provenance for artifacts `delete_batch()`
        removed -- the `memory_changes` tombstone rows for ids no longer present in
        `memory_artifacts`. Lets a project-evidence view keep showing "this id existed and
        was deleted" without retaining any of its deleted content."""
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT artifact_id AS id, subject, "
                "MAX(artifact_version) AS revision, MAX(created_at) AS deleted_at "
                "FROM memory_changes WHERE tombstone = 1 "
                "AND artifact_id NOT IN (SELECT id FROM memory_artifacts) "
                "GROUP BY artifact_id ORDER BY artifact_id ASC"
            )
            return [dict(row) for row in cur.fetchall()]

    def delete_batch(
        self,
        artifact_ids: Sequence[str],
        *,
        expected_revisions: dict[str, int],
        scope: str,
        owner_scope: OwnerScope | None = None,
        apply: bool = False,
        receipt_operation_id: str | None = None,
        receipt_operation_ids: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """Batch memory deletion (P65-07.3, plan §6.4 transaction/outbox algorithm).

        Validates every member's existence, declared `scope` (its `subject`) match,
        declared `owner_scope` match, and `expected_revisions` inside one transaction
        before any write; a missing id, a cross-scope id (`MemoryScopeError`), a
        wrong-owner id (`OwnerScopeError`, P69-07 subsection g -- even one wrong-owner
        member writes zero rows), or a stale revision (`VersionConflictError`)
        refuses the *entire* batch atomically -- never a partial apply. Preview
        (`apply=False`) only ever runs the validation `SELECT`s. Apply replaces each row's
        version-history entry with a content-free tombstone (`content={}`, never the real
        bytes -- "no deleted content retained in active memory versions"), removes the row
        from `memory_artifacts` so retrieval/expansion see it as gone the instant this
        transaction commits, and drops any cached embedding vectors for that id (an
        invalidated index entry). Returns each affected id's prior revision, dependent
        `memory_relations` reference count, and -- for `family="handoff"` ids only -- the
        Rush-owned on-disk packet path an `artifact_write`-granted caller may additionally
        remove; every other family has no on-disk blob, so `blob_path` is `None`.

        `receipt_operation_ids` (S04 residual fix): an optional `artifact_id -> reserved
        receipt id` mapping. When given, apply writes one receipt per target (its own
        `artifact_id` column set, matching `edit()`/`archive()`'s per-artifact receipts)
        instead of the single whole-batch receipt `receipt_operation_id` writes -- the
        batch's atomicity (validate-then-write-all-or-nothing, above) is unaffected,
        since every per-target receipt still commits inside this same transaction. A
        target absent from the mapping simply gets no receipt, same as any other
        harmless-missing-reservation case elsewhere in this module. Takes precedence
        over `receipt_operation_id` when both are given.
        """
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows: dict[str, sqlite3.Row] = {}
            for artifact_id in artifact_ids:
                row = conn.execute(
                    "SELECT * FROM memory_artifacts WHERE id = ?", (artifact_id,)
                ).fetchone()
                if row is None:
                    raise KeyError(artifact_id)
                rows[artifact_id] = row

            for artifact_id, row in rows.items():
                if row["subject"] != scope:
                    raise MemoryScopeError(
                        f"artifact {artifact_id!r} has subject {row['subject']!r}, "
                        f"outside declared scope {scope!r}"
                    )

            for artifact_id, row in rows.items():
                self._require_owner(row, artifact_id, owner_scope)

            for artifact_id, row in rows.items():
                expected = expected_revisions[artifact_id]
                if row["artifact_version"] != expected:
                    raise VersionConflictError(
                        f"artifact {artifact_id!r} expected version {expected}, "
                        f"found {row['artifact_version']}"
                    )

            affected = [
                {
                    "id": artifact_id,
                    "revision": row["artifact_version"],
                    "family": row["family"],
                    "references": conn.execute(
                        "SELECT COUNT(*) FROM memory_relations "
                        "WHERE source_id = ? OR target_id = ?",
                        (artifact_id, artifact_id),
                    ).fetchone()[0],
                    "blob_path": _handoff_blob_relpath(artifact_id, row["family"]),
                }
                for artifact_id, row in rows.items()
            ]

            if not apply:
                return {"applied": False, "affected": affected}

            tombstones: list[tuple[str, int, str]] = []
            for artifact_id, row in rows.items():
                tombstone_version = _write_version(
                    conn,
                    artifact_id,
                    content={},
                    source=row["source"],
                    trust_tier=row["trust_tier"],
                    expected_version=expected_revisions[artifact_id],
                    tombstone=True,
                    subject=row["subject"],
                )
                tombstones.append((artifact_id, tombstone_version, row["source"]))
                conn.execute(
                    "DELETE FROM memory_artifacts WHERE id = ?", (artifact_id,)
                )
                conn.execute(
                    "DELETE FROM memory_embeddings WHERE artifact_id = ?",
                    (artifact_id,),
                )
            if receipt_operation_ids:
                affected_by_id = {item["id"]: item for item in affected}
                for artifact_id, target_receipt_id in receipt_operation_ids.items():
                    if not target_receipt_id or artifact_id not in rows:
                        continue
                    self._write_receipt(
                        conn,
                        target_receipt_id,
                        artifact_id,
                        "delete",
                        rows[artifact_id]["artifact_version"],
                        {"affected": [affected_by_id[artifact_id]]},
                    )
            elif receipt_operation_id:
                self._write_receipt(
                    conn,
                    receipt_operation_id,
                    None,
                    "delete",
                    None,
                    {"affected": affected},
                )
            conn.commit()
        for artifact_id, tombstone_version, source in tombstones:
            note_committed_write(artifact_id, tombstone_version, source, "delete")
        return {"applied": True, "affected": affected}

    def edit(
        self,
        artifact_id: str,
        content: dict[str, Any],
        *,
        expected_version: int,
        scope: str,
        owner_scope: OwnerScope | None = None,
        apply: bool = False,
        receipt_operation_id: str | None = None,
    ) -> dict[str, Any]:
        """Single-artifact content edit under compare-and-swap (P65-07.3, plan §6.4).

        Mirrors `delete_batch()`'s validate-then-write shape but for one id: verifies
        existence, declared `scope` match, declared `owner_scope` match (P69-07
        subsection e -- a mismatched owner rejects exactly like a mismatched version,
        inside the same compare-and-swap; the owner columns themselves are never
        rewritten, per subsection d's immutability rule), and `expected_version`
        before any write. Preview
        (`apply=False`) only ever runs the validation `SELECT`. Apply routes the new content
        through `_write_version` (preserving the prior version's content as history, same as
        every other mutation here) and, if the row's current `trust_tier` is `STATED`
        (previously promoted/authoritative), resets it to `DERIVED` -- an edit demotes trust
        back to an unpromoted candidate, never leaving stale content signed as authoritative.
        A relation edge recorded against the pre-edit version is invalidated for free: MC03's
        `related_artifacts()` already compares a stored `target_version` against
        `get_current()` and treats a mismatch as stale.
        """
        sanitized_content = sanitize_value(content).value
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM memory_artifacts WHERE id = ?", (artifact_id,)
            ).fetchone()
            if row is None:
                raise KeyError(artifact_id)
            if row["subject"] != scope:
                raise MemoryScopeError(
                    f"artifact {artifact_id!r} has subject {row['subject']!r}, "
                    f"outside declared scope {scope!r}"
                )
            self._require_owner(row, artifact_id, owner_scope)
            if row["artifact_version"] != expected_version:
                raise VersionConflictError(
                    f"artifact {artifact_id!r} expected version {expected_version}, "
                    f"found {row['artifact_version']}"
                )
            if not apply:
                return {
                    "applied": False,
                    "id": artifact_id,
                    "revision": row["artifact_version"],
                    "trust_tier": row["trust_tier"],
                }
            new_trust_tier = (
                "DERIVED" if row["trust_tier"] == "STATED" else row["trust_tier"]
            )
            new_version = _write_version(
                conn,
                artifact_id,
                content=sanitized_content,
                source=row["source"],
                trust_tier=new_trust_tier,
                expected_version=expected_version,
                subject=scope,
            )
            conn.execute(
                "UPDATE memory_artifacts SET content = ?, artifact_version = ?, "
                "trust_tier = ?, signature = NULL, promoted_at = NULL WHERE id = ?",
                (
                    json.dumps(sanitized_content),
                    new_version,
                    new_trust_tier,
                    artifact_id,
                ),
            )
            if receipt_operation_id:
                self._write_receipt(
                    conn,
                    receipt_operation_id,
                    artifact_id,
                    "edit",
                    new_version,
                    {"trust_tier": new_trust_tier},
                )
            conn.commit()
            note_committed_write(artifact_id, new_version, row["source"], "edit")
            return {
                "applied": True,
                "id": artifact_id,
                "revision": new_version,
                "trust_tier": new_trust_tier,
            }

    def archive(
        self,
        artifact_id: str,
        *,
        expected_version: int,
        scope: str,
        owner_scope: OwnerScope | None = None,
        apply: bool = False,
        archived: bool = True,
        receipt_operation_id: str | None = None,
    ) -> dict[str, Any]:
        """Sets/clears an archived marker under compare-and-swap (P65-07.3, plan §6.4).

        Carries the identical ownership enforcement `edit()` does (P69-07 subsection g):
        a wrong `owner_scope` raises `OwnerScopeError` before any write, because
        forwarding ownership through the HTTP/tool layers does nothing unless this
        method validates it inside its own compare-and-swap.

        Never touches `content` -- history and bytes are fully retained, only excluded from
        normal `recall()`/`search()` (see their `include_archived` parameter). The marker
        change is itself routed through `_write_version` ("a versioned store mutation") so it
        gets its own audit row, exactly mirroring `edit()`/`delete_batch()`'s atomicity.
        Reversible: call again with `archived=False` and the row's current `expected_version`.
        """
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM memory_artifacts WHERE id = ?", (artifact_id,)
            ).fetchone()
            if row is None:
                raise KeyError(artifact_id)
            if row["subject"] != scope:
                raise MemoryScopeError(
                    f"artifact {artifact_id!r} has subject {row['subject']!r}, "
                    f"outside declared scope {scope!r}"
                )
            self._require_owner(row, artifact_id, owner_scope)
            if row["artifact_version"] != expected_version:
                raise VersionConflictError(
                    f"artifact {artifact_id!r} expected version {expected_version}, "
                    f"found {row['artifact_version']}"
                )
            if not apply:
                return {
                    "applied": False,
                    "id": artifact_id,
                    "revision": row["artifact_version"],
                    "archived": row["archived_at"] is not None,
                }
            new_version = _write_version(
                conn,
                artifact_id,
                content=json.loads(row["content"]),
                source=row["source"],
                trust_tier=row["trust_tier"],
                expected_version=expected_version,
                subject=scope,
            )
            conn.execute(
                "UPDATE memory_artifacts SET archived_at = ?, artifact_version = ? "
                "WHERE id = ?",
                (time.time() if archived else None, new_version, artifact_id),
            )
            if receipt_operation_id:
                self._write_receipt(
                    conn,
                    receipt_operation_id,
                    artifact_id,
                    "archive",
                    new_version,
                    {"archived": archived},
                )
            conn.commit()
            note_committed_write(artifact_id, new_version, row["source"], "archive")
            return {
                "applied": True,
                "id": artifact_id,
                "revision": new_version,
                "archived": archived,
            }

    def get_embedding(
        self,
        *,
        artifact_id: str,
        artifact_version: int,
        content_hash: str,
        model_digest: str,
        chunking_version: str,
    ) -> list[float] | None:
        """MC12 §6.7: a previously cached vector for this exact (artifact, version, content
        hash, model digest, chunking version) key, or `None` if uncached or invalidated by a
        content/model-digest/chunking-version change."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT vector FROM memory_embeddings WHERE namespace = ? AND artifact_id = ? "
                "AND artifact_version = ? AND content_hash = ? AND model_digest = ? "
                "AND chunking_version = ?",
                (
                    str(self.project_root),
                    artifact_id,
                    artifact_version,
                    content_hash,
                    model_digest,
                    chunking_version,
                ),
            ).fetchone()
        return json.loads(row["vector"]) if row else None

    def put_embedding(
        self,
        *,
        artifact_id: str,
        artifact_version: int,
        content_hash: str,
        model_digest: str,
        chunking_version: str,
        vector: list[float],
    ) -> None:
        """MC12 §6.7: persists one vector. Always writes -- the caller (`hybrid_candidates()`)
        only calls this when the caller-granted `cache_write` permits it, so a read-only
        hybrid request never reaches this method."""
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO memory_embeddings (namespace, artifact_id, "
                "artifact_version, content_hash, model_digest, chunking_version, dimension, "
                "vector, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    str(self.project_root),
                    artifact_id,
                    artifact_version,
                    content_hash,
                    model_digest,
                    chunking_version,
                    len(vector),
                    json.dumps(vector),
                    time.time(),
                ),
            )
            conn.commit()

    def get_current(self, artifact_id: str) -> MemoryArtifact | None:
        """MC02 §9.0 `expand_artifact()` support: the *current* row for one ID, re-fetched
        fresh (never a `recall_page()` snapshot) so visibility/version checks reflect any
        write that happened since that artifact was last paged."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM memory_artifacts WHERE id = ?", (artifact_id,)
            ).fetchone()
        return (
            _row_to_artifact(row, default_owner_scope=self._owner_scope_default)
            if row
            else None
        )

    def get_version_content(self, artifact_id: str, version: int) -> str | None:
        """MC02 §9.0 `expand_artifact()` support: the exact stored bytes (as originally
        written, never re-serialized) for one artifact version, from the immutable
        `memory_artifact_versions` audit trail (MC01 §6.1)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT content FROM memory_artifact_versions "
                "WHERE artifact_id = ? AND artifact_version = ?",
                (artifact_id, version),
            ).fetchone()
        return row[0] if row else None

    def _migrate_version_column(self, conn: sqlite3.Connection) -> None:
        """Additive migration (MC01 §6.1): a pre-MC01 DB predates `artifact_version`; add it,
        defaulting existing rows to version 1 (mirrors `_migrate_expiry_columns`'s pattern).
        Does not backfill `memory_artifact_versions`/`memory_changes` history for rows that
        predate this column — call `upgrade()` for the full explicit migration with history."""
        existing = {
            row["name"] for row in conn.execute("PRAGMA table_info(memory_artifacts)")
        }
        if "artifact_version" not in existing:
            conn.execute(
                "ALTER TABLE memory_artifacts ADD COLUMN artifact_version "
                "INTEGER NOT NULL DEFAULT 1"
            )

    def _migrate_archived_column(self, conn: sqlite3.Connection) -> None:
        """Additive migration (P65-07 §6.4): a pre-archive DB predates `archived_at`;
        add it, defaulting existing rows to NULL (never archived), mirroring
        `_migrate_expiry_columns`'s pattern."""
        existing = {
            row["name"] for row in conn.execute("PRAGMA table_info(memory_artifacts)")
        }
        if "archived_at" not in existing:
            conn.execute("ALTER TABLE memory_artifacts ADD COLUMN archived_at REAL")

    def _migrate_changes_subject_column(self, conn: sqlite3.Connection) -> None:
        """Additive migration (P65-07.3): a pre-P65-07 DB's `memory_changes` predates the
        `subject` column `delete_batch()`'s tombstone rows use for provenance (mirrors
        `_migrate_expiry_columns`'s pattern) -- existing rows default to `NULL`."""
        existing = {
            row["name"] for row in conn.execute("PRAGMA table_info(memory_changes)")
        }
        if "subject" not in existing:
            conn.execute("ALTER TABLE memory_changes ADD COLUMN subject TEXT")

    def _migrate_handoff_recovery_columns(self, conn: sqlite3.Connection) -> None:
        """S05 bullet 4: additive migration (mirrors `_migrate_expiry_columns`'s
        pattern) -- a pre-S05 DB predates both columns. `memory_handoff_sessions
        .revoked_at` lets dead-owner recovery reject a session it has
        determined is unrecoverable (S05 bullet 4's "committed session
        receipt with no matching prepared descriptor" case) instead of
        leaving it silently reusable. `memory_artifacts.orphaned_at` marks a
        recovery-created artifact safe for later cleanup without deleting it
        outright (recovery never destroys data, only flags it)."""
        session_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(memory_handoff_sessions)")
        }
        if "revoked_at" not in session_columns:
            conn.execute(
                "ALTER TABLE memory_handoff_sessions ADD COLUMN revoked_at REAL"
            )
        artifact_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(memory_artifacts)")
        }
        if "orphaned_at" not in artifact_columns:
            conn.execute("ALTER TABLE memory_artifacts ADD COLUMN orphaned_at REAL")

    def _migrate_owner_scope_columns(self, conn: sqlite3.Connection) -> None:
        """Additive migration (P69-07 ownership contract): a pre-P69-07 DB predates
        `owner_scope_kind`/`owner_scope_id`; add them, defaulting existing rows to NULL,
        which every reader resolves to `legacy_owner_scope(project_root)` (subsection c)
        via `owner_scope_for_row()`. Mirrors `_migrate_expiry_columns`'s pattern exactly.

        Deliberately additive-only, with no `UPDATE ... SET owner_scope_* ` backfill
        here: `_SCHEMA_SQL` creates the external-content `memory_fts` table and its
        AFTER UPDATE trigger in this same `_init_db()` call, so on a database whose rows
        predate that table, any UPDATE fires a trigger that deletes an FTS entry which
        was never inserted -- SQLite reports "database disk image is malformed". The
        explicit legacy path (`upgrade()`), which never creates those triggers, does
        materialize the default on disk.
        """
        existing = {
            row["name"] for row in conn.execute("PRAGMA table_info(memory_artifacts)")
        }
        for column in ("owner_scope_kind", "owner_scope_id"):
            if column not in existing:
                conn.execute(f"ALTER TABLE memory_artifacts ADD COLUMN {column} TEXT")
        # Created here rather than in `_SCHEMA_SQL`: that script runs *before* this
        # migration, so on a pre-P69-07 database the columns don't exist yet.
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memory_owner "
            "ON memory_artifacts(owner_scope_kind, owner_scope_id)"
        )

    def _require_owner(
        self,
        row: sqlite3.Row,
        artifact_id: str,
        owner_scope: OwnerScope | None,
    ) -> None:
        """Ownership half of the compare-and-swap (P69-07 subsections e/g/i).

        Runs inside the caller's own open transaction, next to the `subject` and
        `expected_version` checks, and rejects exactly like a version mismatch does.
        `owner_scope=None` means the caller declared no owner -- the pre-P69-07
        contract, still used by internal callers that have no owner to declare; the
        dashboard/TUI/tool layers always declare one.
        """
        if owner_scope is None:
            return
        stored = owner_scope_for_row(row, self.project_root)
        if stored != owner_scope:
            raise OwnerScopeError(
                f"artifact {artifact_id!r} is owned by "
                f"{stored.kind}:{stored.id!r}, not {owner_scope.kind}:{owner_scope.id!r}"
            )

    def _migrate_expiry_columns(self, conn: sqlite3.Connection) -> None:
        """Additive migration (P62.7 §6.3): a pre-P62.7 DB predates `expires_at`/`expired_at`/
        `expired_by`; `CREATE TABLE IF NOT EXISTS` doesn't retrofit columns onto an existing
        table, so add any missing ones here, defaulting existing rows to NULL."""
        existing = {
            row["name"] for row in conn.execute("PRAGMA table_info(memory_artifacts)")
        }
        for column, col_type in (
            ("expires_at", "REAL"),
            ("expired_at", "REAL"),
            ("expired_by", "TEXT"),
        ):
            if column not in existing:
                conn.execute(
                    f"ALTER TABLE memory_artifacts ADD COLUMN {column} {col_type}"
                )

    @classmethod
    def open_readonly(cls, project_root: Path) -> ReadOnlyOpenResult:
        """Query-only open (MC01 §6.1): never creates a DB, directory, journal, or migrated
        schema. A missing DB returns `available=False` with zero filesystem I/O. An existing DB
        predating `artifact_version` returns `migration_required=True` without touching it —
        callers must run `upgrade()` before writing. Otherwise returns an open read-only
        `sqlite3.Connection` (SQLite `mode=ro`, so any accidental write raises).

        G1/X2: opens through `open_sqlite_readonly`, so it never leaves a `-wal`/`-shm`
        behind; a non-`None` `state` is passed through with no connection."""
        root = Path(project_root).resolve()
        opened = open_sqlite_readonly(root / ".rush" / "memory.db")
        conn = opened.connection
        if conn is None:
            return opened
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(memory_artifacts)")
        }
        if "artifact_version" not in columns:
            conn.close()
            return dataclasses.replace(opened, migration_required=True, connection=None)
        return opened

    @classmethod
    def open_readonly_view(
        cls, project_root: Path
    ) -> tuple[TypedArtifactStore | None, str | None]:
        """R20.G8: a query-only store for local read surfaces (dashboard, TUI). Its read
        methods (`list_artifact_refs`, `scope_artifacts`, `recall`, `current_generation`,
        ...) run over one `open_readonly()` connection, so reading never creates `.rush/`,
        a DB, a sidecar, a cursor key, or a migrated schema; any write method raises.

        Returns `(view, None)` on success and `(None, None)` when no DB exists (a genuinely
        empty store). Otherwise `(None, state)` with `state` one of `migration_required`
        (no `artifact_version`, or no `archived_at`/`expired_at` yet), `corrupt`, or
        `busy`; `readonly_view_reason(state)` explains it. Callers must show that state,
        never an empty store. Call `close()` on the view when done."""
        root = Path(project_root).resolve()
        opened = cls.open_readonly(root)
        if opened.state is not None:
            code = readonly_state_code(opened.state, root / ".rush" / "memory.db")
            return None, "corrupt" if code == "E_STORE_CORRUPT" else "busy"
        if opened.migration_required:
            return None, "migration_required"
        conn = opened.connection
        if conn is None:
            return None, None
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(memory_artifacts)")
        }
        if not {"archived_at", "expired_at"} <= columns:
            conn.close()
            return None, "migration_required"
        view = cls.__new__(cls)
        view.project_root = Path(project_root).resolve()
        view.db_path = view.project_root / ".rush" / "memory.db"
        view._owner_scope_default = legacy_owner_scope(view.project_root)
        view._readonly_conn = conn
        return view, None

    def close(self) -> None:
        """Close an `open_readonly_view()` connection; a no-op on a writable store."""
        conn = getattr(self, "_readonly_conn", None)
        if conn is not None:
            conn.close()
            self._readonly_conn = None

    @classmethod
    def preview_mutation(
        cls,
        project_root: Path,
        artifact_id: str,
        *,
        expected_version: int,
        scope: str,
        owner_scope: OwnerScope | None = None,
        operation: Literal["edit", "archive"],
    ) -> dict[str, Any]:
        """Genuinely read-only `apply=False` validation for `edit()`/`archive()`.

        P69-07 subsection f: constructing a `TypedArtifactStore` is itself write-adjacent
        (`__init__` creates `.rush/`, runs `executescript` on the schema, mints a cursor
        key, and now runs this packet's own `owner_scope` migration), so routing a preview
        through it made "preview" touch disk -- and this packet's migration would have
        widened that footprint on legacy databases. This runs the identical existence /
        `subject` / `owner_scope` / `expected_version` checks over `open_readonly()`
        instead, applying the ownership contract's legacy default in memory, and never
        creates a directory, journal, or schema.

        Raises `KeyError` (no database or no such row), `MemoryScopeError`,
        `OwnerScopeError`, `VersionConflictError`, or `MemoryMigrationRequiredError`
        (a database that predates `artifact_version`, which only a real write-path
        migration can fix).
        """
        root = Path(project_root).resolve()
        opened = cls.open_readonly(root)
        if opened.state is not None:
            db = root / ".rush" / "memory.db"
            raise MemoryStoreUnreadableError(
                f"{db} cannot be read without writing ({opened.state}); retry",
                code=readonly_state_code(opened.state, db),
            )
        if not opened.available:
            raise KeyError(artifact_id)
        if opened.migration_required or opened.connection is None:
            raise MemoryMigrationRequiredError(
                f"{root / '.rush' / 'memory.db'} predates artifact_version; "
                "run an apply-mode operation or `upgrade()` before previewing"
            )
        conn = opened.connection
        try:
            row = conn.execute(
                "SELECT * FROM memory_artifacts WHERE id = ?", (artifact_id,)
            ).fetchone()
            if row is None:
                raise KeyError(artifact_id)
            if row["subject"] != scope:
                raise MemoryScopeError(
                    f"artifact {artifact_id!r} has subject {row['subject']!r}, "
                    f"outside declared scope {scope!r}"
                )
            if owner_scope is not None:
                stored = owner_scope_for_row(row, root)
                if stored != owner_scope:
                    raise OwnerScopeError(
                        f"artifact {artifact_id!r} is owned by "
                        f"{stored.kind}:{stored.id!r}, not "
                        f"{owner_scope.kind}:{owner_scope.id!r}"
                    )
            if row["artifact_version"] != expected_version:
                raise VersionConflictError(
                    f"artifact {artifact_id!r} expected version {expected_version}, "
                    f"found {row['artifact_version']}"
                )
            preview: dict[str, Any] = {
                "applied": False,
                "id": artifact_id,
                "revision": row["artifact_version"],
            }
            if operation == "edit":
                preview["trust_tier"] = row["trust_tier"]
            else:
                preview["archived"] = _row_value(row, "archived_at") is not None
            return preview
        finally:
            conn.close()

    @classmethod
    def upgrade(cls, project_root: Path, *, cache_write: bool) -> int:
        """Explicit legacy-schema migration (MC01 §6.1): adds `artifact_version` if missing and
        backfills `memory_artifact_versions`/`memory_changes` history for every pre-existing
        row, all inside one transaction. Rolls back to the original schema/data on any failure
        (`_backfill_legacy_row` raising) with no partial rows. A no-op if history already exists.
        Uses a fresh, non-WAL connection (never `_init_db`/`_SCHEMA_SQL`) so a rollback restores
        the on-disk file exactly, including its pre-migration journal mode.
        """
        if not cache_write:
            raise ValueError("TypedArtifactStore.upgrade() requires cache_write=True")
        root = Path(project_root).resolve()
        db_path = root / ".rush" / "memory.db"
        if not db_path.exists():
            return 0
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(memory_artifacts)")
            }
            conn.execute("BEGIN IMMEDIATE")
            if "artifact_version" not in columns:
                conn.execute(
                    "ALTER TABLE memory_artifacts ADD COLUMN artifact_version "
                    "INTEGER NOT NULL DEFAULT 1"
                )
            for statement in _VERSION_TABLE_STATEMENTS:
                conn.execute(statement)
            changes_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(memory_changes)")
            }
            if "subject" not in changes_columns:
                conn.execute("ALTER TABLE memory_changes ADD COLUMN subject TEXT")
            # P69-07 ownership contract: the explicit legacy path adds the owner
            # columns and backfills subsection c's default in the same transaction,
            # so a failure here rolls the whole migration back exactly as before.
            for column in ("owner_scope_kind", "owner_scope_id"):
                if column not in columns:
                    conn.execute(
                        f"ALTER TABLE memory_artifacts ADD COLUMN {column} TEXT"
                    )
            default_owner = legacy_owner_scope(root)
            conn.execute(
                "UPDATE memory_artifacts SET owner_scope_kind = ?, owner_scope_id = ? "
                "WHERE owner_scope_kind IS NULL OR owner_scope_id IS NULL",
                (default_owner.kind, default_owner.id),
            )
            already_migrated = conn.execute(
                "SELECT COUNT(*) FROM memory_artifact_versions"
            ).fetchone()[0]
            migrated = 0
            if not already_migrated:
                for row in conn.execute("SELECT * FROM memory_artifacts").fetchall():
                    cls._backfill_legacy_row(conn, row)
                    migrated += 1
            conn.commit()
            return migrated
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @classmethod
    def _backfill_legacy_row(cls, conn: sqlite3.Connection, row: sqlite3.Row) -> None:
        """Writes one pre-existing row's history as version 1 (MC01 §6.1 legacy migration)."""
        now = time.time()
        conn.execute(
            "INSERT INTO memory_artifact_versions "
            "(artifact_id, artifact_version, content, source, trust_tier, created_at, deleted) "
            "VALUES (?,1,?,?,?,?,0)",
            (row["id"], row["content"], row["source"], row["trust_tier"], now),
        )
        conn.execute(
            "INSERT INTO memory_changes (artifact_id, artifact_version, tombstone, created_at) "
            "VALUES (?,1,0,?)",
            (row["id"], now),
        )

    def _find_stated_conflict(
        self,
        conn: sqlite3.Connection,
        subject: str,
        symbol_ref: str,
        owner_scope: OwnerScope,
    ) -> MemoryArtifact | None:
        """The incoming write's *own* conflicting STATED row (P69-07 subsection i).

        Scoped to `owner_scope` as well as `(subject, symbol_ref)`: a STATED record
        belonging to a different owner is not this write's conflict to resolve -- it is
        a separate artifact that happens to share subject/symbol_ref, not a stale
        duplicate, and silently deleting it was a fourth unguarded deletion path.
        """
        # COALESCE applies the ownership contract's legacy default (subsection c) in the
        # query itself: a row migrated by `_migrate_owner_scope_columns` keeps NULL owner
        # columns on disk (see that method for why it cannot rewrite them), and must
        # still behave as project-owned here.
        default = self._owner_scope_default
        cur = conn.execute(
            "SELECT * FROM memory_artifacts WHERE subject = ? AND symbol_ref = ? "
            "AND trust_tier = 'STATED' "
            "AND COALESCE(owner_scope_kind, ?) = ? AND COALESCE(owner_scope_id, ?) = ? "
            "LIMIT 1",
            (
                subject,
                symbol_ref,
                default.kind,
                owner_scope.kind,
                default.id,
                owner_scope.id,
            ),
        )
        row = cur.fetchone()
        return (
            _row_to_artifact(row, default_owner_scope=self._owner_scope_default)
            if row
            else None
        )

    def _delete_tx(
        self,
        conn: sqlite3.Connection,
        artifact_id: str,
        *,
        expected_version: int | None = None,
        owner_scope: OwnerScope | None = None,
    ) -> tuple[str, int, str] | None:
        """Shared delete body for `delete()`/`_prepare_write()`'s conflict-eviction path.
        Returns the tombstone revision's `(id, revision, source)`, or `None` when
        there was no row; the caller notes it only after its own commit (T19).
        Caller owns the transaction (BEGIN/commit) -- this never opens its own connection,
        so a conflict-delete and the insert that follows it (P69-01.2g) share one atomic
        transaction instead of two separately-committed ones.

        P69-07 subsection i: the ownership check happens *here*, inside the caller's
        transaction, so both the explicit `delete()` operation and `_prepare_write()`'s
        internal conflict eviction go through one owner-checked path rather than the
        conflict path bypassing ownership entirely."""
        row = conn.execute(
            "SELECT * FROM memory_artifacts WHERE id = ?",
            (artifact_id,),
        ).fetchone()
        if row is None:
            return None
        self._require_owner(row, artifact_id, owner_scope)
        tombstone_version = _write_version(
            conn,
            artifact_id,
            content=json.loads(row["content"]),
            source=row["source"],
            trust_tier=row["trust_tier"],
            expected_version=expected_version,
            tombstone=True,
        )
        conn.execute("DELETE FROM memory_artifacts WHERE id = ?", (artifact_id,))
        return artifact_id, tombstone_version, row["source"]

    def _prepare_write(
        self, conn: sqlite3.Connection, artifact: MemoryArtifact
    ) -> tuple[MemoryArtifact, tuple[str, int, str] | None]:
        """Shared pre-insert step for `write()`/`write_pass()`: enforces Invariant 1
        (no-STATED-on-entry), resolves any STATED conflict, and redacts content
        (Invariant 2). Runs inside the caller's own open transaction (P69-01.2g) --
        a process death between the conflict-delete and the insert that follows it
        can no longer permanently remove the original artifact with nothing
        replacing it, since both are now one atomic unit.
        """
        if artifact.trust_tier == "STATED":
            raise TrustTierError(
                "write() cannot insert trust_tier='STATED' directly; "
                "promotion is the only path to STATED"
            )
        owner_scope = artifact.owner_scope or self._owner_scope_default
        evicted = None
        if artifact.symbol_ref is not None:
            existing = self._find_stated_conflict(
                conn, artifact.subject, artifact.symbol_ref, owner_scope
            )
            if (
                existing is not None
                and evaluate_conflict(artifact, existing) == "delete"
            ):
                evicted = self._delete_tx(conn, existing.id, owner_scope=owner_scope)
        sanitized_content = sanitize_value(artifact.content).value
        stored = dataclasses.replace(
            artifact,
            content=sanitized_content,
            artifact_version=1,
            owner_scope=owner_scope,
        )
        return stored, evicted

    @staticmethod
    def _note_inserted(
        stored: MemoryArtifact, evicted: tuple[str, int, str] | None
    ) -> None:
        """T19: after the insert transaction commits, its conflict eviction
        (a tombstone revision) and the new artifact's first revision."""
        if evicted is not None:
            note_committed_write(*evicted, "delete")
        note_committed_write(stored.id, stored.artifact_version, stored.source, "write")

    def _insert_row(self, conn: sqlite3.Connection, stored: MemoryArtifact) -> None:
        """Shared insert body for `write()`/`write_pass()`: the artifact row plus its
        `memory_artifact_versions`/`memory_changes` audit trail. Caller owns the
        transaction (BEGIN/commit)."""
        now = time.time()
        conn.execute(
            _INSERT_SQL,
            (
                stored.id,
                stored.family,
                stored.subject,
                stored.trust_tier,
                json.dumps(stored.content),
                stored.source,
                stored.created_at,
                stored.symbol_ref,
                stored.content_hash,
                stored.corroboration_count,
                stored.promoted_at,
                int(stored.stale),
                stored.signature,
                stored.origin_kind,
                stored.origin_id,
                stored.artifact_version,
                (stored.owner_scope or self._owner_scope_default).kind,
                (stored.owner_scope or self._owner_scope_default).id,
            ),
        )
        conn.execute(
            "INSERT INTO memory_artifact_versions "
            "(artifact_id, artifact_version, content, source, trust_tier, created_at, deleted) "
            "VALUES (?,?,?,?,?,?,0)",
            (
                stored.id,
                stored.artifact_version,
                json.dumps(stored.content),
                stored.source,
                stored.trust_tier,
                now,
            ),
        )
        conn.execute(
            "INSERT INTO memory_changes (artifact_id, artifact_version, tombstone, created_at) "
            "VALUES (?,?,0,?)",
            (stored.id, stored.artifact_version, now),
        )

    def write(
        self, artifact: MemoryArtifact, *, receipt_operation_id: str | None = None
    ) -> MemoryArtifact:
        """Persist an artifact. Enforces Invariant 1 (no-STATED-on-entry) and 2
        (redact-before-store). The conflict lookup/delete `_prepare_write()` may run,
        this insert, and the optional creation receipt all share one transaction
        (P69-01.2g) -- an insertion failure after a conflict-delete rolls the delete
        back too, rather than leaving the deleted artifact permanently gone."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            stored, evicted = self._prepare_write(conn, artifact)
            self._insert_row(conn, stored)
            if receipt_operation_id:
                self._write_receipt(
                    conn,
                    receipt_operation_id,
                    stored.id,
                    "create",
                    stored.artifact_version,
                    {},
                )
            conn.commit()
        self._note_inserted(stored, evicted)
        return stored

    def write_pass(
        self,
        artifact: MemoryArtifact,
        *,
        namespace: str,
        behavior_id: str,
        runtime_digest: str,
    ) -> MemoryArtifact:
        """MC10 §9.0: insert one passing observation artifact and advance its
        namespace/behavior/runtime-platform-digest last-success pointer in the *same*
        transaction -- the only path that ever writes `memory_behavior_success` (no
        parallel write path; reuses `_insert_row()`, the same insert body `write()` uses).
        A cache hit, skip, tag, or caller label never reaches this method; only a
        genuinely executed pass does, via `rush.memory.experience.record_behavior_success`.
        """
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            stored, evicted = self._prepare_write(conn, artifact)
            self._insert_row(conn, stored)
            conn.execute(
                "INSERT INTO memory_behavior_success "
                "(namespace, behavior_id, runtime_digest, artifact_id, artifact_version, updated_at) "
                "VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(namespace, behavior_id, runtime_digest) DO UPDATE SET "
                "artifact_id = excluded.artifact_id, "
                "artifact_version = excluded.artifact_version, "
                "updated_at = excluded.updated_at",
                (
                    namespace,
                    behavior_id,
                    runtime_digest,
                    stored.id,
                    stored.artifact_version,
                    now,
                ),
            )
            conn.commit()
        self._note_inserted(stored, evicted)
        return stored

    def get_behavior_success(
        self, *, namespace: str, behavior_id: str, runtime_digest: str
    ) -> tuple[str, int] | None:
        """MC10 §9.0: the current last-success pointer for one exact
        namespace/behavior/runtime-platform-digest key, or `None` if that behavior has
        never passed under this exact environment."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT artifact_id, artifact_version FROM memory_behavior_success "
                "WHERE namespace = ? AND behavior_id = ? AND runtime_digest = ?",
                (namespace, behavior_id, runtime_digest),
            ).fetchone()
        return (row[0], row[1]) if row else None

    def find_any_behavior_success(
        self, *, namespace: str, behavior_id: str
    ) -> tuple[str, int] | None:
        """MC10.3 `historical=true` support: the most recently updated last-success
        pointer for `behavior_id` under *any* runtime/platform digest -- used only to
        surface a cross-environment baseline; callers must still treat it as
        `environment_compatible=False`, never as an exact-environment match."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT artifact_id, artifact_version FROM memory_behavior_success "
                "WHERE namespace = ? AND behavior_id = ? "
                "ORDER BY updated_at DESC LIMIT 1",
                (namespace, behavior_id),
            ).fetchone()
        return (row[0], row[1]) if row else None

    def create_handoff_session(
        self,
        *,
        session_id: str,
        root: str,
        audience: str,
        capability_hash: str,
        granted_ids: Sequence[str],
        session_allowlist: Sequence[str],
        constraints: dict[str, Any],
        created_at: float,
        expires_at: float,
        receipt_operation_id: str | None = None,
    ) -> None:
        """MC11 §9.0: persist one bounded-handoff session descriptor. `granted_ids` is the
        exact, immutable authorized artifact-ID set for this session -- widening scope
        always requires a brand-new session (no update path exists)."""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO memory_handoff_sessions "
                "(session_id, root, audience, capability_hash, granted_ids, "
                "session_allowlist, constraints, created_at, expires_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    session_id,
                    root,
                    audience,
                    capability_hash,
                    json.dumps(list(granted_ids)),
                    json.dumps(list(session_allowlist)),
                    json.dumps(constraints),
                    created_at,
                    expires_at,
                ),
            )
            if receipt_operation_id:
                self._write_receipt(
                    conn,
                    receipt_operation_id,
                    session_id,
                    "handoff_session",
                    None,
                    {"audience": audience},
                )
            conn.commit()

    def get_handoff_session(self, session_id: str) -> dict[str, Any] | None:
        """MC11 §9.0: the raw stored session row (JSON fields decoded), or `None` if
        `session_id` is unknown. Never checks capability or expiry -- callers (`rush.memory
        .handoff.load_session`) own that policy."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM memory_handoff_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "session_id": row["session_id"],
            "root": row["root"],
            "audience": row["audience"],
            "capability_hash": row["capability_hash"],
            "granted_ids": json.loads(row["granted_ids"]),
            "session_allowlist": json.loads(row["session_allowlist"]),
            "constraints": json.loads(row["constraints"]),
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "revoked_at": row["revoked_at"],
        }

    def revoke_handoff_session(
        self, session_id: str, *, now: float | None = None
    ) -> None:
        """S05 bullet 4: idempotently mark `session_id` revoked -- an
        `UPDATE ... WHERE revoked_at IS NULL` so a second call (two
        recovery attempts racing the same dead owner, or a retry) never
        overwrites the first revocation's timestamp. Silently a no-op for
        an unknown session_id."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE memory_handoff_sessions SET revoked_at = ? "
                "WHERE session_id = ? AND revoked_at IS NULL",
                (now if now is not None else time.time(), session_id),
            )
            conn.commit()

    def mark_artifact_orphaned(
        self, artifact_id: str, *, now: float | None = None
    ) -> None:
        """S05 bullet 4: idempotently flag a recovery-created artifact as
        orphaned (safe for later cleanup) without deleting it -- recovery
        never destroys data, only marks it. Silently a no-op for an
        unknown/already-orphaned artifact_id."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE memory_artifacts SET orphaned_at = ? "
                "WHERE id = ? AND orphaned_at IS NULL",
                (now if now is not None else time.time(), artifact_id),
            )
            conn.commit()

    def write_handoff_delivery_receipt(
        self, receipt_id: str, *, artifact_id: str, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        """S05 bullet 3: idempotent delivery-transition receipt shared by a
        handoff's initial send and its claimed-recovery delivery path.
        `INSERT OR IGNORE` -- unlike `_write_receipt`'s `INSERT OR REPLACE`
        used elsewhere, a delivery outcome already committed under this
        exact `receipt_id` is never overwritten by a second call (initial
        send racing its own crash-recovery retry). Returns the row that is
        now authoritative for `receipt_id`: the payload just given on a
        fresh insert, or the pre-existing stored payload on a replay --
        callers compare the two to detect a conflicting rebind rather than
        trusting their own call succeeded."""
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO mutation_receipts "
                "(operation_id, artifact_id, kind, revision, payload, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (
                    receipt_id,
                    artifact_id,
                    "delivery_transition",
                    None,
                    json.dumps(payload),
                    time.time(),
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT payload FROM mutation_receipts WHERE operation_id = ?",
                (receipt_id,),
            ).fetchone()
        return json.loads(row["payload"]) if row is not None else None

    def get_handoff_receipts(self, session_id: str) -> dict[str, int]:
        """MC11 §9.0: every artifact's currently-acknowledged version for `session_id`. An
        artifact absent from the result has never been acknowledged (implicit version 0)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT artifact_id, acknowledged_version FROM memory_handoff_receipts "
                "WHERE session_id = ?",
                (session_id,),
            ).fetchall()
        return {row["artifact_id"]: row["acknowledged_version"] for row in rows}

    def acknowledge_handoff(
        self, session_id: str, readbacks: Sequence[tuple[str, int, str]]
    ) -> dict[str, int]:
        """MC11 §9.0: atomically verify and record an exact receiver read-back.

        Each `(artifact_id, version, digest)` triple must name a version that genuinely
        exists in the immutable `memory_artifact_versions` audit trail, with `digest`
        matching the SHA-256 of that *exact* stored version's bytes -- proving the receiver
        actually read that content, not merely that a delivery turn completed. A single bad
        entry raises `VersionConflictError` before any row is written (the `with self
        ._connect()` context manager rolls the whole transaction back), so "same ID,
        different digest" never partially advances a receipt. Replaying an already-
        acknowledged (or lower) version is a no-op, not an error -- ACK is idempotent.
        """
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            current = {
                row["artifact_id"]: row["acknowledged_version"]
                for row in conn.execute(
                    "SELECT artifact_id, acknowledged_version "
                    "FROM memory_handoff_receipts WHERE session_id = ?",
                    (session_id,),
                ).fetchall()
            }
            for artifact_id, version, digest in readbacks:
                stored_content = conn.execute(
                    "SELECT content FROM memory_artifact_versions "
                    "WHERE artifact_id = ? AND artifact_version = ?",
                    (artifact_id, version),
                ).fetchone()
                if stored_content is None:
                    raise VersionConflictError(
                        f"artifact {artifact_id!r} version {version} was never delivered "
                        "to this store (cannot skip an unseen change).",
                    )
                actual_digest = hashlib.sha256(
                    stored_content[0].encode("utf-8")
                ).hexdigest()
                if actual_digest != digest:
                    raise VersionConflictError(
                        f"artifact {artifact_id!r} version {version} read-back digest "
                        "does not match the exact stored content.",
                    )
                if version > current.get(artifact_id, 0):
                    current[artifact_id] = version
            for artifact_id, version, _digest in readbacks:
                conn.execute(
                    "INSERT INTO memory_handoff_receipts "
                    "(session_id, artifact_id, acknowledged_version, updated_at) "
                    "VALUES (?,?,?,?) "
                    "ON CONFLICT(session_id, artifact_id) DO UPDATE SET "
                    "acknowledged_version = MAX(acknowledged_version, excluded.acknowledged_version), "
                    "updated_at = excluded.updated_at",
                    (session_id, artifact_id, current[artifact_id], now),
                )
            conn.commit()
        return self.get_handoff_receipts(session_id)

    def update_content(
        self,
        artifact_id: str,
        content: dict[str, Any],
        *,
        expected_version: int | None = None,
    ) -> None:
        """Update an existing row's content (redacted), exercising the AFTER UPDATE FTS trigger.

        Routed through `_write_version` (MC01 §6.1): advances `artifact_version`, appends a
        `memory_artifact_versions`/`memory_changes` row, and raises `VersionConflictError` if
        `expected_version` is given and stale. A missing `artifact_id` is a silent no-op,
        matching this method's pre-MC01 behavior.
        """
        sanitized_content = sanitize_value(content).value
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT source, trust_tier FROM memory_artifacts WHERE id = ?",
                (artifact_id,),
            ).fetchone()
            if row is None:
                return
            new_version = _write_version(
                conn,
                artifact_id,
                content=sanitized_content,
                source=row["source"],
                trust_tier=row["trust_tier"],
                expected_version=expected_version,
            )
            conn.execute(
                "UPDATE memory_artifacts SET content = ?, artifact_version = ? WHERE id = ?",
                (json.dumps(sanitized_content), new_version, artifact_id),
            )
            conn.commit()
            note_committed_write(artifact_id, new_version, row["source"], "update")

    def promote(
        self,
        artifact_id: str,
        *,
        user_stated: bool,
        candidate_sources: list[str] | None = None,
        expected_version: int | None = None,
        owner_scope: OwnerScope | None = None,
        receipt_operation_id: str | None = None,
    ) -> tuple[MemoryArtifact, PromotionResult]:
        """Evaluate persisted bytes and atomically persist their signed promotion.

        Promotion is a distinct, separately-committed effect from the candidate
        artifact's own creation (P69-01.2f) -- a receipt is only written here when
        `decision.promoted` is actually True, so recovery can tell "candidate created"
        apart from "candidate created *and* promoted" via two independently-addressable
        receipts rather than one conflated id.

        S08 bullet 3: `owner_scope` is checked here under the same
        compare-and-swap contract `edit()`/`archive()`/`delete_batch()`
        already enforce (P69-07) -- a wrong owner rejects before any write,
        same as a stale `expected_version`. Previously absent: promotion
        could rewrite/upgrade any artifact's trust tier regardless of a
        declared owner_scope mismatch."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM memory_artifacts WHERE id = ?", (artifact_id,)
            ).fetchone()
            if row is None:
                raise KeyError(artifact_id)
            self._require_owner(row, artifact_id, owner_scope)
            artifact, decision = promote_stored_artifact(
                conn,
                artifact_id,
                project_root=self.project_root,
                user_stated=user_stated,
                candidate_sources=candidate_sources,
                expected_version=expected_version,
            )
            if receipt_operation_id and decision.promoted:
                self._write_receipt(
                    conn,
                    receipt_operation_id,
                    artifact_id,
                    "promote",
                    artifact.artifact_version,
                    {"promoted": True},
                )
        # The `with` block commits on exit; only a real promotion wrote a revision.
        if decision.promoted:
            note_committed_write(
                artifact.id, artifact.artifact_version, artifact.source, "promote"
            )
        return artifact, decision

    def delete(
        self,
        artifact_id: str,
        *,
        expected_version: int | None = None,
        owner_scope: OwnerScope | None = None,
    ) -> None:
        """Delete a row by id, exercising the AFTER DELETE FTS trigger.

        Routed through `_write_version` (MC01 §6.1) with `tombstone=True` before the row is
        removed, so `memory_artifact_versions`/`memory_changes` retain the deletion's provenance
        even though `memory_artifacts` no longer has the row. A missing `artifact_id` is a
        silent no-op, matching this method's pre-MC01 behavior.
        """
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            tombstone = self._delete_tx(
                conn,
                artifact_id,
                expected_version=expected_version,
                owner_scope=owner_scope,
            )
            conn.commit()
        if tombstone is not None:
            note_committed_write(*tombstone, "delete")

    def search(
        self,
        subject: MemorySubject,
        query: str,
        *,
        include_archived: bool = False,
    ) -> list[MemoryArtifact]:
        """FTS5 match scoped to a subject, BM25-ranked (best match first).

        Never applies recall()'s per-row defense checks. `include_archived` (P65-07 §6.4)
        opts back into rows an `archive()` call has excluded from normal recall -- default
        False, matching "excluded from normal recall" for every other caller.
        """
        archived_clause = "" if include_archived else "AND ma.archived_at IS NULL "
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT ma.* FROM memory_artifacts ma "
                "JOIN memory_fts f ON f.rowid = ma.rowid "
                "WHERE f.content MATCH ? AND ma.subject = ? "
                + archived_clause
                + "ORDER BY f.rank",
                (query, subject),
            )
            rows = cur.fetchall()
        return [
            _row_to_artifact(row, default_owner_scope=self._owner_scope_default)
            for row in rows
        ]

    def recall(
        self,
        subject: MemorySubject,
        query: str,
        session_allowlist: Iterable[str] | None = None,
        *,
        include_archived: bool = False,
    ) -> list[MemoryArtifact]:
        """FTS5 match (identical to search()) with signature, Trojan-source, and staleness checks.

        `session_allowlist` scopes results to rows whose `source` is in the allowlist, applied
        before Invariants 3/4/6 run on any returned row (§9 P61.9). An empty or absent allowlist
        fails closed: zero rows are returned, never all rows (matches
        `src/rush/release/provenance_policy.py`'s empty-allowlist fail-closed precedent).
        """
        allowed_sources = set(session_allowlist) if session_allowlist else set()
        if not allowed_sources:
            return []
        verified: list[MemoryArtifact] = []
        for artifact in self.search(subject, query, include_archived=include_archived):
            if artifact.source not in allowed_sources:
                continue
            if artifact.trust_tier == "STATED" and (
                artifact.signature is None
                or compute_content_signature(artifact.content) != artifact.signature
            ):
                raise SignatureMismatchError(
                    f"signature mismatch for STATED artifact {artifact.id}"
                )

            findings = _inspect_text_for_trojan_chars(
                json.dumps(artifact.content, ensure_ascii=False)
            )
            if findings:
                raise TrojanSourceFoundError(
                    f"Trojan Source characters detected in artifact {artifact.id}: {findings}"
                )

            if artifact.symbol_ref is not None and artifact.content_hash is not None:
                path_part = artifact.symbol_ref.split("::", 1)[0]
                file_path = (self.project_root / path_part).resolve()
                try:
                    # Same sha256 as `MerkleInvalidator.hash_content`, computed
                    # directly so a read-only view (which has no invalidator; its
                    # construction mkdirs `.rush/cache`) can recall too.
                    current_hash = hashlib.sha256(
                        file_path.read_text(encoding="utf-8").encode("utf-8")
                    ).hexdigest()
                except (OSError, UnicodeError):
                    current_hash = None
                if current_hash != artifact.content_hash:
                    artifact = dataclasses.replace(artifact, stale=True)

            # API-diff staleness (§6.5 Invariant 5): independent baseline (git `base_ref`)
            # from the merkle check above (last-hashed content) — evaluated unconditionally,
            # never gated by it. An "unknown" ApiDiffer result never clears an existing
            # stale=True; this block only ever sets stale=True, never resets it to False.
            if artifact.symbol_ref is not None:
                path_part, sep, symbol_part = artifact.symbol_ref.partition("::")
                if sep and symbol_part:
                    file_path = (self.project_root / path_part).resolve()
                    if file_path.is_file():
                        from rush.tools.api_diff import ApiDiffer

                        diff_result = ApiDiffer(
                            project_root=self.project_root
                        ).diff_symbol(file_path, symbol_part)
                        if isinstance(diff_result, dict):
                            artifact = dataclasses.replace(artifact, stale=True)

            verified.append(artifact)
        return verified


def promote_stored_artifact(
    conn: sqlite3.Connection,
    artifact_id: str,
    *,
    project_root: Path,
    user_stated: bool,
    candidate_sources: list[str] | None = None,
    expected_version: int | None = None,
) -> tuple[MemoryArtifact, PromotionResult]:
    """Shared gate/update; caller owns transaction and commit.

    Routed through `_write_version` (MC01 §6.1) only when an actual promotion happens: a
    promotion is a real semantic change (trust-tier upgrade), so it always advances
    `artifact_version`, even if `content` is byte-identical to the prior version.
    """
    row = conn.execute(
        "SELECT * FROM memory_artifacts WHERE id = ?", (artifact_id,)
    ).fetchone()
    if row is None:
        raise KeyError(artifact_id)
    artifact = _row_to_artifact(
        row, default_owner_scope=legacy_owner_scope(project_root)
    )
    artifact = dataclasses.replace(
        artifact, content=sanitize_value(artifact.content).value
    )
    decision = evaluate_promotion(
        artifact,
        user_stated=user_stated,
        candidate_sources=candidate_sources,
        project_root=project_root,
    )
    if decision.promoted:
        new_version = _write_version(
            conn,
            artifact_id,
            content=artifact.content,
            source=artifact.source,
            trust_tier="STATED",
            expected_version=expected_version,
        )
        artifact = dataclasses.replace(
            artifact,
            trust_tier="STATED",
            promoted_at=time.time(),
            signature=compute_content_signature(artifact.content),
            corroboration_count=decision.corroboration_count,
            artifact_version=new_version,
        )
        conn.execute(
            "UPDATE memory_artifacts SET content = ?, trust_tier = ?, promoted_at = ?, "
            "signature = ?, corroboration_count = ?, artifact_version = ? WHERE id = ?",
            (
                json.dumps(artifact.content),
                artifact.trust_tier,
                artifact.promoted_at,
                artifact.signature,
                artifact.corroboration_count,
                artifact.artifact_version,
                artifact.id,
            ),
        )
    return artifact, decision
