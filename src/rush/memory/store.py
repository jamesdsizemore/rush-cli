"""Unified typed-artifact store: WAL-mode SQLite backing every memory subject.

Phase 61 §6.1/§6.3 — `MemoryArtifact` is one row of the unified schema; `TypedArtifactStore`
enforces the no-STATED-on-entry, redact-before-store, recall-rescan, and staleness invariants.
"""

from __future__ import annotations

import base64
import dataclasses
import errno
import gc
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import stat
import subprocess
import sys
import time
import urllib.parse
import uuid
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import ExitStack, closing, contextmanager, suppress
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, TypeGuard, cast, get_args

from rush.memory.merkle_invalidator import MerkleInvalidator
from rush.memory.trust import PromotionResult, evaluate_promotion
from rush.safety.redactor import sanitize_value
from rush.sqlite_util import ClosingConnection

if TYPE_CHECKING:
    from rush.memory.retrieval import MemoryAccess

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


def current_row_sql(conn: sqlite3.Connection) -> str:
    """`archived_at IS NULL AND expired_at IS NULL`, plus (72-T05, plan L51/L55)
    an active applicability (NULL = pre-T05) and no task binding (an omitted task
    context never matches one) when the store has those columns -- an old-schema
    store lacks them."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(memory_artifacts)")}
    live = ["archived_at IS NULL", "expired_at IS NULL"]
    if "applicability" in columns:
        live.append("(applicability IS NULL OR applicability = 'active')")
    if "task_id" in columns:
        live.append("task_id IS NULL")
    return " AND ".join(live)


def useful_memory_count(conn: sqlite3.Connection) -> int:
    """R18.1: the internal-exclusion predicate AND `current_row_sql` -- the
    "useful memory count" T20/T23/T28 share."""
    fragment, params = internal_source_exclusion_sql()
    row = conn.execute(
        f"SELECT COUNT(*) FROM memory_artifacts WHERE {fragment} "
        f"AND {current_row_sql(conn)}",
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

    72-T06 D30: `reason` names the requirement (`upgrade_required`,
    `duplicate_event_identity`) and `refs` lists only `{artifact_id, artifact_version}`
    rows the caller's access may see -- never a count or digest of hidden rows.
    """

    def __init__(
        self,
        message: str = "",
        *,
        reason: str | None = None,
        refs: tuple[dict[str, Any], ...] = (),
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.refs = tuple(refs)


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


def readonly_preview_error(state: str, db: Path) -> MemoryStoreUnreadableError:
    """T28-D: a read-only preview's unusable-open error, worded like
    `open_readonly_view()`'s reason -- a corrupt store is never called retryable."""
    code = readonly_state_code(state, db)
    return MemoryStoreUnreadableError(
        readonly_view_reason("corrupt" if code == "E_STORE_CORRUPT" else "busy"),
        code=code,
    )


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
        if not isinstance(self.kind, str) or self.kind not in _OWNER_SCOPE_KINDS:
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
    # T28-D: the stored archive timestamp (None = live), read-only on listed rows so a
    # caller can tell archived rows from live ones. Never written from this field.
    archived_at: float | None = None
    # 72-T01: the shared decision's freshness (`current`, `stale`, `unknown` or
    # `not_applicable`) on rows a read route returned; `None` when no decision ran.
    # Never written from this field.
    freshness: str | None = None
    # 72-T05: the row's applicability (`active`, `rejected`, `superseded`, `pending`;
    # `None` = a pre-T05 row, no gate) and its task binding (all three set, or none).
    # The four fields stay out of `repr`: internal routes return the pre-T05
    # `MemoryArtifact(...)` text and the G2 exact bodies pin it.
    applicability: str | None = dataclasses.field(default=None, repr=False)
    task_project_id: str | None = dataclasses.field(default=None, repr=False)
    task_worktree_id: str | None = dataclasses.field(default=None, repr=False)
    task_id: str | None = dataclasses.field(default=None, repr=False)


@dataclass(frozen=True)
class VersionBinding:
    """72-T05: the applicability/task snapshot a new version row records
    (`binding_recorded = 1`)."""

    applicability: str | None
    task_project_id: str | None = None
    task_worktree_id: str | None = None
    task_id: str | None = None


# 72-T05: the `applicability` a correction kind writes onto its target.
_CORRECTION_APPLICABILITY: dict[str, str] = {
    "correct": "active",
    "reject": "rejected",
    "supersede": "superseded",
}

# 72-T05: the additive columns (`_migrate_applicability_columns`).
APPLICABILITY_COLUMNS: tuple[str, ...] = (
    "applicability",
    "task_project_id",
    "task_worktree_id",
    "task_id",
)
VERSION_BINDING_COLUMNS: tuple[tuple[str, str], ...] = (
    *((name, "TEXT") for name in APPLICABILITY_COLUMNS),
    ("binding_recorded", "INTEGER"),
)


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
        payload_hash TEXT,
        payload_hash_origin TEXT,
        applicability TEXT,
        task_project_id TEXT,
        task_worktree_id TEXT,
        task_id TEXT,
        binding_recorded INTEGER,
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
    revoked_at REAL,
    sender_grant_id TEXT,
    sender_owner_kind TEXT,
    sender_owner_id TEXT,
    sender_project_id TEXT,
    sender_worktree_id TEXT,
    sender_policy_revision INTEGER,
    sender_task_id TEXT
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
    created_at REAL NOT NULL,
    invocation_id TEXT,
    effect_id TEXT,
    request_digest TEXT
);
"""

_BINDING_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS memory_store_binding (
    id INTEGER PRIMARY KEY CHECK(id=1),
    store_id TEXT NOT NULL,
    mac TEXT NOT NULL
);
"""

# 72-T06 D29: v2 mutation receipts. A fresh table gets the three columns from
# `_MUTATION_RECEIPTS_TABLE_SQL`; an existing one gains them in `_apply_v2_schema`
# (the constructor post-script and `upgrade`), which also owns the partial index:
# it can never live in `_SCHEMA_SQL`, whose script runs before an old table has them.
V2_RECEIPT_COLUMNS: tuple[str, ...] = ("invocation_id", "effect_id", "request_digest")
V2_RECEIPT_PREFIX = "v2:"
_V2_RECEIPT_INDEX_SQL = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_mutation_receipts_v2 "
    "ON mutation_receipts(invocation_id, effect_id) "
    "WHERE invocation_id IS NOT NULL AND effect_id IS NOT NULL"
)
# 72-T06 D30: event identity, unique within one owner.
EVENT_IDENTITY_KEYS: tuple[str, ...] = (
    "project_id",
    "worktree_id",
    "task_id",
    "event_id",
)


def _event_value_sql(key: str, column: str = "content") -> str:
    """D30 type-aware identity value: the key's nonempty JSON string, else NULL (a
    number, array, object, boolean, null or empty string never matches a string)."""
    return (
        f"(CASE WHEN json_valid({column}) THEN CASE WHEN "
        f"json_type({column}, '$.{key}') = 'text' AND "
        f"length(json_extract({column}, '$.{key}')) > 0 "
        f"THEN json_extract({column}, '$.{key}') END END)"
    )


def _event_type_sql(key: str, column: str) -> str:
    return f"(CASE WHEN json_valid({column}) THEN json_type({column}, '$.{key}') END)"


_EVENT_VALUE_SQL: tuple[str, ...] = tuple(
    _event_value_sql(key) for key in EVENT_IDENTITY_KEYS
)
_EVENT_KEY_SQL = ", ".join(
    (
        *_EVENT_VALUE_SQL,
        "COALESCE(owner_scope_kind, '')",
        "COALESCE(owner_scope_id, '')",
    )
)
_EVENT_PRESENT_SQL = " AND ".join(f"{expr} IS NOT NULL" for expr in _EVENT_VALUE_SQL)
_EVENT_INDEX_SQL = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_event_identity "
    f"ON memory_artifacts({_EVENT_KEY_SQL}) WHERE {_EVENT_PRESENT_SQL}"
)
_EVENT_TRIGGER_SQL = (
    "CREATE TRIGGER IF NOT EXISTS memory_event_identity_immutable "
    "BEFORE UPDATE OF content ON memory_artifacts WHEN "
    # D30: only an event-bearing row (a top-level `event_id` key) has an identity to
    # keep; any other row may gain or change `project_id`, `worktree_id` or `task_id`.
    f"{_event_type_sql('event_id', 'old.content')} IS NOT NULL AND ("
    + " OR ".join(
        f"{_event_type_sql(key, 'new.content')} IS NOT "
        f"{_event_type_sql(key, 'old.content')} OR "
        f"{_event_value_sql(key, 'new.content')} IS NOT "
        f"{_event_value_sql(key, 'old.content')}"
        for key in EVENT_IDENTITY_KEYS
    )
    + ") BEGIN SELECT RAISE(ABORT, 'event_identity_immutable'); END"
)


def v2_operation_id(invocation_id: str, effect_id: str) -> str:
    """D29: the reserved `mutation_receipts.operation_id` of one v2 effect."""
    digest = hashlib.sha256(json.dumps([invocation_id, effect_id]).encode("utf-8"))
    return V2_RECEIPT_PREFIX + digest.hexdigest()


def _reject_reserved_receipt_ids(*receipt_ids: Any) -> None:
    """D29: the `v2:` operation-id namespace belongs to `_write_v2_receipt` alone."""
    for receipt_id in receipt_ids:
        if isinstance(receipt_id, str) and receipt_id.startswith(V2_RECEIPT_PREFIX):
            from rush.memory.authorization import MemoryPolicyError

            raise MemoryPolicyError("E_INPUT", "reserved_receipt_namespace")


def v2_receipts_ready(conn: sqlite3.Connection) -> bool:
    """D29: the receipts table carries the v2 replay columns."""
    if not sqlite_has_table(conn, "mutation_receipts"):
        return False
    columns = {row[1] for row in conn.execute("PRAGMA table_info(mutation_receipts)")}
    return set(V2_RECEIPT_COLUMNS) <= columns


def v2_schema_current(conn: sqlite3.Connection) -> bool:
    """The unconditional 72-T06 post-schema DDL is present: receipt columns, receipt
    index and event trigger (the event index is conditional, D30). 72-T02's
    `writable_open_ddl_free` declaration consumes this."""
    if not v2_receipts_ready(conn):
        return False
    names = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE name IN "
            "('idx_mutation_receipts_v2', 'memory_event_identity_immutable')"
        )
    }
    return len(names) == 2


def _apply_v2_schema(conn: sqlite3.Connection) -> None:
    """D29/D30 post-schema DDL shared by `_init_db` and `upgrade`; the caller owns
    the transaction."""
    present = {row[1] for row in conn.execute("PRAGMA table_info(mutation_receipts)")}
    for column in V2_RECEIPT_COLUMNS:
        if column not in present:
            conn.execute(f"ALTER TABLE mutation_receipts ADD COLUMN {column} TEXT")
    conn.execute(_V2_RECEIPT_INDEX_SQL)
    conn.execute(_EVENT_TRIGGER_SQL)


def _event_index_present(conn: sqlite3.Connection) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'index' "
            "AND name = 'idx_memory_event_identity'"
        ).fetchone()
        is not None
    )


def _event_duplicate_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """D30 preflight: every row whose identity repeats within one owner."""
    return conn.execute(
        f"SELECT * FROM memory_artifacts WHERE {_EVENT_PRESENT_SQL} "
        f"AND ({_EVENT_KEY_SQL}) IN (SELECT {_EVENT_KEY_SQL} FROM memory_artifacts "
        f"WHERE {_EVENT_PRESENT_SQL} GROUP BY {_EVENT_KEY_SQL} HAVING COUNT(*) > 1) "
        "ORDER BY id"
    ).fetchall()


def _create_event_index_if_clean(conn: sqlite3.Connection) -> None:
    """D30 (iii): the constructor creates the index only when no row lacks an owner
    and no identity repeats; otherwise it stays absent until `upgrade`."""
    if _event_index_present(conn):
        return
    ownerless = conn.execute(
        "SELECT 1 FROM memory_artifacts "
        "WHERE owner_scope_kind IS NULL OR owner_scope_id IS NULL LIMIT 1"
    ).fetchone()
    if ownerless is not None or _event_duplicate_rows(conn):
        return
    conn.execute(_EVENT_INDEX_SQL)


def _check_event_identity(content: Any, access: MemoryAccess | None) -> bool:
    """D30: True for an event-bearing write; an invalid identity raises `E_INPUT`.
    `task_id`/`event_id` are event data, never authority; a policy access pins the
    project and worktree ids to its own."""
    if not (isinstance(content, dict) and "event_id" in content):
        return False
    from rush.memory.authorization import MemoryPolicyError

    values = [content.get(key) for key in EVENT_IDENTITY_KEYS]
    if not all(isinstance(value, str) and value for value in values):
        raise MemoryPolicyError("E_INPUT", "event_identity_invalid")
    if (
        access is not None
        and access.kind == "policy"
        and (
            content["project_id"] != access.project_id
            or content["worktree_id"] != access.worktree_id
        )
    ):
        raise MemoryPolicyError("E_INPUT", "event_identity_invalid")
    return True


def _raise_event_identity_immutable(
    exc: sqlite3.IntegrityError, conn: sqlite3.Connection | None
) -> None:
    """D30: map the immutability trigger's abort (after `conn`'s rollback when the
    site owns the transaction); any other integrity error returns for re-raise."""
    if str(exc) != "event_identity_immutable":
        return
    if conn is not None:
        conn.rollback()
    from rush.memory.authorization import MemoryPolicyError

    raise MemoryPolicyError("E_INPUT", "event_identity_immutable") from exc


def v2_receipt_binding_matches(binding: Any, access: MemoryAccess) -> bool:
    """D29 replay binding check: project, worktree, owner (when the access names
    one) and every recorded source still granted (D40)."""
    from rush.memory.authorization import source_granted

    if not isinstance(binding, dict):
        return False
    if (
        binding.get("project_id") != access.project_id
        or binding.get("worktree_id") != access.worktree_id
    ):
        return False
    if (
        access.owner_scope is not None
        and binding.get("owner_scope") != access.owner_scope.as_dict()
    ):
        return False
    sources = binding.get("sources")
    return isinstance(sources, list) and all(
        source_granted(source, access.sources) for source in sources
    )


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
    orphaned_at REAL,
    payload_hash TEXT,
    payload_hash_origin TEXT,
    row_mac TEXT,
    applicability TEXT,
    task_project_id TEXT,
    task_worktree_id TEXT,
    task_id TEXT
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
    + _BINDING_TABLE_SQL
)

_INSERT_SQL = """
INSERT INTO memory_artifacts (
    id, family, subject, trust_tier, content, source, created_at,
    symbol_ref, content_hash, corroboration_count, promoted_at, stale,
    signature, origin_kind, origin_id, artifact_version,
    owner_scope_kind, owner_scope_id, payload_hash, payload_hash_origin, row_mac,
    applicability, task_project_id, task_worktree_id, task_id
) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
"""

# 72-T01 (plan §2.1 item 2): `payload_hash` is the SHA-256 of the exact persisted
# `content` text; `payload_hash_origin` says how it was bound: `write` (an authorized
# write), `backfill` (the additive migration) or NULL (unbound, e.g. a row inserted
# outside `write()`).
PAYLOAD_HASH_COLUMNS = ("payload_hash", "payload_hash_origin")


def payload_digest(text: str) -> str:
    """SHA-256 of one persisted `content` text (`memory_artifact_versions.content`)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def payload_mismatched(text: Any, digest: Any) -> bool:
    """True when a payload binding exists and no longer matches the persisted text
    (`integrity_payload_mismatch`); an unbound row (`digest` None) is not a mismatch.
    72-T02 D32: stored content is decoded first (a UTF-8 BLOB is its text); content
    that does not decode as UTF-8 never matches a binding."""
    if digest is None:
        return False
    decoded = _stored_text(text)
    return decoded is None or payload_digest(decoded) != digest


def source_predicate_sql(column: str, sources: Sequence[str]) -> tuple[str, list[str]]:
    """D40: `column` is an exact approved label, or carries a granted family prefix
    with a non-empty suffix (never LIKE/glob matching)."""
    from rush.memory.authorization import family_prefixes

    exact = sorted(s for s in sources if not s.endswith(":*"))
    families = family_prefixes(sources)
    clause = (
        f"({column} IN (SELECT value FROM json_each(?)) OR EXISTS ("
        "SELECT 1 FROM json_each(?) AS f "
        f"WHERE substr({column}, 1, length(f.value)) = f.value "
        f"AND length({column}) > length(f.value)))"
    )
    return clause, [json.dumps(exact), json.dumps(families)]


def compute_content_signature(content: dict[str, Any]) -> str:
    """Deterministic SHA-256 over a content dict, used for STATED-row signature verification."""
    payload = json.dumps(content, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _backfill_bindable(text: Any, trust_tier: Any, signature: Any) -> bool:
    """OD-1: a STATED row is backfilled only when its signature still matches; every
    other row binds its persisted bytes as found."""
    if not isinstance(text, str):
        return False
    if trust_tier != "STATED":
        return True
    try:
        content = json.loads(text)
    except ValueError:
        return False
    return (
        isinstance(content, dict)
        and bool(signature)
        and compute_content_signature(content) == signature
    )


def _migrate_payload_hash_columns(conn: sqlite3.Connection) -> None:
    """72-T01 additive migration: adds `payload_hash`/`payload_hash_origin` to
    `memory_artifacts` and `memory_artifact_versions` wherever a table lacks them, and
    backfills (`origin='backfill'`) only in the step that adds them. Write-authorized
    callers only (`_init_db`, `upgrade`); a read never migrates."""
    for table in ("memory_artifacts", "memory_artifact_versions"):
        if not sqlite_has_table(conn, table):
            continue
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        missing = [column for column in PAYLOAD_HASH_COLUMNS if column not in columns]
        if not missing:
            continue
        for column in missing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
        artifact_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(memory_artifacts)")
        }
        if not {"content", "trust_tier", "signature"} <= artifact_columns:
            continue  # a partial legacy table: leave its rows unbound
        if table == "memory_artifacts":
            rows = conn.execute(
                "SELECT rowid, content, trust_tier, signature FROM memory_artifacts"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT v.rowid, v.content, v.trust_tier, a.signature "
                "FROM memory_artifact_versions v "
                "LEFT JOIN memory_artifacts a ON a.id = v.artifact_id"
            ).fetchall()
        for rowid, text, trust_tier, signature in rows:
            if _backfill_bindable(text, trust_tier, signature):
                conn.execute(
                    f"UPDATE {table} SET payload_hash = ?, "
                    "payload_hash_origin = 'backfill' WHERE rowid = ?",
                    (payload_digest(text), rowid),
                )


# --- D41: local store binding ------------------------------------------------

#: Row MAC payload columns, in order (D41).
ROW_MAC_COLUMNS: tuple[str, ...] = (
    "id",
    "family",
    "subject",
    "trust_tier",
    "content",
    "source",
    "symbol_ref",
    "content_hash",
    "owner_scope_kind",
    "owner_scope_id",
    "origin_kind",
    "origin_id",
    # 72-T05: NULL values are omitted, so every pre-T05 MAC stays valid.
    "applicability",
    "task_project_id",
    "task_worktree_id",
    "task_id",
)
_STORE_KEY_NAME = "memory_store.key"
_STORE_KEY_TMP_PREFIX = _STORE_KEY_NAME + ".tmp-"
_STORE_KEY_BYTES = 32
StoreBinding = Literal["bound", "unbound"]


def _store_key_dir() -> Path | None:
    """`<default_data_root()>/user/.rush`; `None` when the data root is unavailable."""
    from rush.setup.provision import DataRootUnavailableError, default_data_root

    try:
        return Path(default_data_root()) / "user" / ".rush"
    except (DataRootUnavailableError, OSError, RuntimeError, ValueError):
        return None


def _read_key_posix(path: Path) -> bytes | None:
    try:
        # O_NONBLOCK: a FIFO planted at the key path must fail the regular-file
        # check below instead of blocking the open.
        fd = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
        )
    except OSError:
        return None
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) & 0o077
            or info.st_size != _STORE_KEY_BYTES
        ):
            return None
        data = os.read(fd, _STORE_KEY_BYTES + 1)
    except OSError:
        return None
    finally:
        os.close(fd)
    return data if len(data) == _STORE_KEY_BYTES else None


def read_store_key() -> bytes | None:
    """D41: the 32-byte local store key, or `None`. Never creates anything."""
    key_dir = _store_key_dir()
    if key_dir is None:
        return None
    if sys.platform == "win32":  # pragma: no cover - native Windows lane
        return _windows_key_io(key_dir, create=False)
    return _read_key_posix(key_dir / _STORE_KEY_NAME)


def _unlink_temp(path: Path) -> None:
    """Remove the key's temporary hard link, retrying a `PermissionError` every
    0.02 s for one second (a remaining temp link is the permitted ceiling)."""
    deadline = time.monotonic() + 1.0
    while True:
        try:
            os.unlink(path)
            return
        except FileNotFoundError:
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                return
            time.sleep(0.02)
        except OSError:
            return


def _makedirs_owner_only(path: Path) -> None:
    """D41 POSIX: create every missing directory of `path`, parents included, 0o700
    (`os.makedirs` applies `mode` to the leaf only)."""
    missing: list[Path] = []
    while not os.path.lexists(path):
        missing.append(path)
        path = path.parent
    for directory in reversed(missing):
        try:
            os.mkdir(directory, 0o700)
        except FileExistsError:
            pass


def ensure_store_key() -> bytes | None:
    """D41: read the store key, publishing a new one when absent; `None` when it
    cannot be read or created."""
    existing = read_store_key()
    if existing is not None:
        return existing
    key_dir = _store_key_dir()
    if key_dir is None:
        return None
    if sys.platform == "win32":  # pragma: no cover - native Windows lane
        return _windows_key_io(key_dir, create=True)
    key_path = key_dir / _STORE_KEY_NAME
    if os.path.lexists(key_path):
        return None  # present but unusable: never replaced
    temp = key_dir / (_STORE_KEY_TMP_PREFIX + uuid.uuid4().hex)
    try:
        _makedirs_owner_only(key_dir)
        fd = os.open(
            temp,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except OSError:
        return None
    try:
        try:
            os.write(fd, secrets.token_bytes(_STORE_KEY_BYTES))
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            os.link(temp, key_path)
        except FileExistsError:
            pass
    except OSError:
        return None
    finally:
        _unlink_temp(temp)
    return read_store_key()


def _windows_key_io(key_dir: Path, *, create: bool) -> bytes | None:  # pragma: no cover
    """D41 Windows key read/create through pinned, non-reparse directory handles,
    an owner-only DACL and a shared-delete read handle. `None` on any failure."""
    try:
        return _windows_key_io_unchecked(key_dir, create=create)
    except Exception:  # noqa: BLE001 - every Windows key failure is "key unavailable"
        return None


def _windows_key_io_unchecked(  # pragma: no cover - native Windows lane
    key_dir: Path, *, create: bool
) -> bytes | None:
    if sys.platform != "win32":
        raise OSError("the Windows key lane runs only on Windows")
    import ctypes
    import msvcrt
    from ctypes import wintypes

    from rush.memory.authorization import _windows_sid_principal

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    invalid = ctypes.c_void_p(-1).value
    kernel32.CreateFileW.restype = ctypes.c_void_p
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetFileAttributesW.restype = wintypes.DWORD
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]

    class _Info(ctypes.Structure):
        _fields_ = [
            ("attrs", wintypes.DWORD),
            ("c1", wintypes.DWORD * 2),
            ("c2", wintypes.DWORD * 2),
            ("c3", wintypes.DWORD * 2),
            ("serial", wintypes.DWORD),
            ("size_high", wintypes.DWORD),
            ("size_low", wintypes.DWORD),
            ("links", wintypes.DWORD),
            ("index_high", wintypes.DWORD),
            ("index_low", wintypes.DWORD),
        ]

    kernel32.GetFileInformationByHandle.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(_Info),
    ]
    reparse, directory = 0x400, 0x10

    def info_of(handle: Any) -> _Info:
        info = _Info()
        if not kernel32.GetFileInformationByHandle(handle, ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        return info

    pinned: list[Any] = []
    try:
        root = key_dir.parent.parent
        if create:
            # D41 creates every missing ancestor (`os.makedirs`); only the ancestors
            # above the data root are created here, so `<data root>`, `user` and
            # `.rush` are still each created only after its parent is pinned.
            os.makedirs(root.parent, exist_ok=True)
        for directory_path in (root, root / "user", key_dir):
            if create and not os.path.lexists(directory_path):
                os.mkdir(directory_path)
            handle = kernel32.CreateFileW(
                str(directory_path), 0x81, 0x3, None, 3, 0x02200000, None
            )
            if handle in (None, invalid):
                return None
            pinned.append(handle)
            attrs = info_of(handle).attrs
            if attrs & reparse or not attrs & directory:
                return None
        principal = _windows_sid_principal()
        sid = principal.split(":", 1)[1]
        key_path = key_dir / _STORE_KEY_NAME
        if create and not os.path.lexists(key_path):
            sddl = f"O:{sid}D:P(A;;FA;;;{sid})(A;;FA;;;SY)"

            class _SA(ctypes.Structure):
                _fields_ = [
                    ("length", wintypes.DWORD),
                    ("descriptor", ctypes.c_void_p),
                    ("inherit", wintypes.BOOL),
                ]

            descriptor = ctypes.c_void_p()
            advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
                wintypes.LPCWSTR,
                wintypes.DWORD,
                ctypes.POINTER(ctypes.c_void_p),
                ctypes.c_void_p,
            ]
            if not advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
                sddl, 1, ctypes.byref(descriptor), None
            ):
                return None
            try:
                attrs_sa = _SA(ctypes.sizeof(_SA), descriptor, False)
                temp = key_dir / (_STORE_KEY_TMP_PREFIX + uuid.uuid4().hex)
                handle = kernel32.CreateFileW(
                    str(temp),
                    0x40020000,
                    0,
                    ctypes.byref(attrs_sa),
                    1,
                    0x00200080,
                    None,
                )
                if handle in (None, invalid):
                    return None
                fd = msvcrt.open_osfhandle(handle, os.O_WRONLY | os.O_BINARY)
                try:
                    os.write(fd, secrets.token_bytes(_STORE_KEY_BYTES))
                    os.fsync(fd)
                finally:
                    os.close(fd)
                try:
                    os.link(temp, key_path)
                except FileExistsError:
                    pass
                finally:
                    _unlink_temp(temp)
            finally:
                kernel32.LocalFree(descriptor)
        handle = kernel32.CreateFileW(
            str(key_path), 0x80020000, 5, None, 3, 0x00200000, None
        )
        if handle in (None, invalid):
            return None
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        try:
            info = info_of(handle)
            if info.attrs & reparse or info.attrs & directory:
                return None
            if info.size_high or info.size_low != _STORE_KEY_BYTES:
                return None
            if not _windows_key_acl_ok(handle, sid):
                return None
            data = os.read(fd, _STORE_KEY_BYTES + 1)
        finally:
            os.close(fd)
        return data if len(data) == _STORE_KEY_BYTES else None
    finally:
        for handle in pinned:
            kernel32.CloseHandle(handle)


def _windows_key_acl_ok(handle: Any, sid: str) -> bool:  # pragma: no cover
    """Owner is the current SID; the DACL is non-NULL and every non-inherit-only
    ACE is a deny or an allow for the current SID, SYSTEM or Administrators."""
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32.GetSecurityInfo.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi32.ConvertSidToStringSidW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.LPWSTR),
    ]
    advapi32.GetAce.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]

    def sid_text(pointer: Any) -> str | None:
        text = wintypes.LPWSTR()
        if not advapi32.ConvertSidToStringSidW(pointer, ctypes.byref(text)):
            return None
        try:
            return str(text.value)
        finally:
            kernel32.LocalFree(ctypes.cast(text, ctypes.c_void_p))

    owner = ctypes.c_void_p()
    dacl = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    if advapi32.GetSecurityInfo(
        handle,
        1,
        0x5,
        ctypes.byref(owner),
        None,
        ctypes.byref(dacl),
        None,
        ctypes.byref(descriptor),
    ):
        return False
    try:
        if sid_text(owner) != sid or not dacl.value:
            return False

        class _AclHeader(ctypes.Structure):
            _fields_ = [
                ("revision", ctypes.c_ubyte),
                ("sbz1", ctypes.c_ubyte),
                ("size", wintypes.WORD),
                ("count", wintypes.WORD),
                ("sbz2", wintypes.WORD),
            ]

        class _AceHeader(ctypes.Structure):
            _fields_ = [
                ("type", ctypes.c_ubyte),
                ("flags", ctypes.c_ubyte),
                ("size", wintypes.WORD),
            ]

        header = ctypes.cast(dacl, ctypes.POINTER(_AclHeader)).contents
        allowed = {sid, "S-1-5-18", "S-1-5-32-544"}
        for index in range(header.count):
            ace = ctypes.c_void_p()
            if not advapi32.GetAce(dacl, index, ctypes.byref(ace)):
                return False
            ace_header = ctypes.cast(ace, ctypes.POINTER(_AceHeader)).contents
            if ace_header.flags & 0x08:  # INHERIT_ONLY_ACE
                continue
            if ace_header.type in (1, 6):  # access-denied (object) ACE
                continue
            if ace_header.type != 0:  # only a plain access-allowed ACE may allow
                return False
            sid_pointer = (ace.value or 0) + ctypes.sizeof(_AceHeader) + 4
            if sid_text(ctypes.c_void_p(sid_pointer)) not in allowed:
                return False
        return True
    finally:
        kernel32.LocalFree(descriptor)


def _listed_case_path(path: Path) -> str:
    """The path spelled as its directories list each component (matched by device
    and inode); a component whose parent cannot be listed keeps its spelling."""
    resolved = Path(path)
    parts = resolved.parts
    if not parts:
        return str(resolved)
    current = Path(parts[0])
    for name in parts[1:]:
        candidate = current / name
        chosen = name
        try:
            target = os.lstat(candidate)
            names = os.listdir(current)
        except OSError:
            current = candidate
            continue
        if name not in names:
            for entry in names:
                try:
                    info = os.lstat(current / entry)
                except OSError:
                    continue
                if (info.st_dev, info.st_ino) == (target.st_dev, target.st_ino):
                    chosen = entry
                    break
        current = current / chosen
    return str(current)


def _binding_root_text(root: Path) -> str:
    """D41: the canonical spelling of a project root for the store MAC."""
    if sys.platform == "darwin":
        import fcntl

        try:
            fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        except OSError:
            return _listed_case_path(root)
        try:
            raw = fcntl.fcntl(fd, fcntl.F_GETPATH, bytes(1024))
        except OSError:
            return _listed_case_path(root)
        finally:
            # G15: a failed close of this read-only handle never masks the result.
            with suppress(OSError):
                os.close(fd)
        return os.fsdecode(raw.split(b"\0", 1)[0])
    if sys.platform == "win32":
        return str(root)
    return _listed_case_path(root)


def _store_mac(key: bytes, store_id: str, root: Path, db_ino: int) -> str:
    from rush.memory.authorization import _worktree_id

    worktree = _worktree_id(Path(_binding_root_text(root)))
    message = (
        b"rush-memory-store-v1\0"
        + store_id.encode()
        + b"\0"
        + worktree.encode()
        + b"\0"
        + str(db_ino).encode()
    )
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def row_mac(key: bytes, store_id: str, row: Mapping[str, Any] | sqlite3.Row) -> str:
    """D41: HMAC-SHA256 over the row's `ROW_MAC_COLUMNS` (NULL fields omitted)."""
    fields: list[list[Any]] = []
    for column in ROW_MAC_COLUMNS:
        value = row[column] if column in row.keys() else None  # noqa: SIM118
        if value is None:
            continue
        if isinstance(value, bytes):
            fields.append([column, "b", value.hex()])
        else:
            fields.append([column, "v", value])
    payload = json.dumps(fields, separators=(",", ":")).encode()
    message = b"rush-memory-row-v1\0" + store_id.encode() + b"\0" + payload
    return hmac.new(key, message, hashlib.sha256).hexdigest()


_MAC_HEX = frozenset("0123456789abcdef")


def _is_mac(value: object) -> TypeGuard[str]:
    """A 64-character lowercase hex MAC; anything else (including non-ASCII text,
    which `hmac.compare_digest` rejects with a `TypeError`) is never a valid MAC."""
    return isinstance(value, str) and len(value) == 64 and _MAC_HEX.issuperset(value)


def _binding_row(conn: sqlite3.Connection) -> tuple[str, str] | None:
    try:
        if not sqlite_has_table(conn, "memory_store_binding"):
            return None
        row = conn.execute(
            "SELECT store_id, mac FROM memory_store_binding WHERE id = 1"
        ).fetchone()
    except sqlite3.DatabaseError:
        return None
    if row is None or not isinstance(row[0], str) or not _is_mac(row[1]):
        return None
    return row[0], row[1]


def _verified_binding(
    conn: sqlite3.Connection, root: Path, key: bytes | None = None
) -> tuple[bytes, str] | None:
    """`(key, store_id)` when the store's binding row verifies for `root`."""
    found = _binding_row(conn)
    if found is None:
        return None
    if key is None:
        key = read_store_key()
    if key is None:
        return None
    store_id, mac = found
    try:
        db_ino = os.stat(Path(root) / ".rush" / "memory.db").st_ino
        expected = _store_mac(key, store_id, Path(root), db_ino)
    except (OSError, ValueError):
        return None
    if not hmac.compare_digest(mac, expected):
        return None
    return key, store_id


def store_binding(conn: sqlite3.Connection, root: Path) -> StoreBinding:
    """D41: `bound` when this store's binding row verifies under the local key."""
    return "bound" if _verified_binding(conn, root) is not None else "unbound"


@dataclass(frozen=True)
class BindingVerifier:
    """D41 per-read verifier: built once per read call."""

    store: StoreBinding
    key: bytes | None
    store_id: str | None

    def row(self, row: Mapping[str, Any] | sqlite3.Row) -> StoreBinding:
        if self.store != "bound" or self.key is None or self.store_id is None:
            return "unbound"
        keys = row.keys()
        mac = row["row_mac"] if "row_mac" in keys else None
        if not _is_mac(mac):
            return "unbound"
        expected = row_mac(self.key, self.store_id, row)
        return "bound" if hmac.compare_digest(mac, expected) else "unbound"

    def row_tampered(self, row: Mapping[str, Any] | sqlite3.Row) -> bool:
        """72-T05: True when a bound store's row has a MAC that verifies over the
        pre-T05 columns but not over all of them: `applicability` or the task binding
        was set outside the store, so the row carries a binding it was never given. A
        row with no MAC, or one that fails for another column, is only unbound."""
        if self.store != "bound" or self.key is None or self.store_id is None:
            return False
        keys = row.keys()
        mac = row["row_mac"] if "row_mac" in keys else None
        if not _is_mac(mac) or self.row(row) == "bound":
            return False
        legacy = {column: row[column] for column in keys}
        for column in ROW_MAC_COLUMNS[-4:]:
            legacy[column] = None
        if not hmac.compare_digest(mac, row_mac(self.key, self.store_id, legacy)):
            return False
        # A bare `rejected`/`pending` mark only narrows what a read returns and
        # carries no task binding, so it is not a tamper: the `edit` re-review path
        # still reaches the row (72-T06 row_state matrix) and re-stamps its MAC.
        task_unbound = all(
            (row[column] if column in keys else None) is None
            for column in ROW_MAC_COLUMNS[-3:]
        )
        narrowed = (row["applicability"] if "applicability" in keys else None) in (
            "rejected",
            "pending",
        )
        return not (narrowed and task_unbound)

    def version_bytes(
        self, row: Mapping[str, Any] | sqlite3.Row, version: int, content: Any
    ) -> StoreBinding:
        """Bound only for a bound row's current version with its exact stored bytes."""
        if self.row(row) != "bound":
            return "unbound"
        if version != row["artifact_version"] or content != row["content"]:
            return "unbound"
        return "bound"


UNBOUND_VERIFIER = BindingVerifier("unbound", None, None)


def binding_verifier(store: TypedArtifactStore) -> BindingVerifier:
    """D41: the verifier for one read over `store`'s connection."""
    try:
        with store._connect() as conn:
            found = _verified_binding(conn, store.project_root)
    except sqlite3.DatabaseError:
        return UNBOUND_VERIFIER
    if found is None:
        return UNBOUND_VERIFIER
    return BindingVerifier("bound", found[0], found[1])


def _row_dict(conn: sqlite3.Connection, artifact_id: str) -> dict[str, Any] | None:
    cur = conn.execute("SELECT * FROM memory_artifacts WHERE id = ?", (artifact_id,))
    row = cur.fetchone()
    if row is None:
        return None
    return {d[0]: row[i] for i, d in enumerate(cur.description)}


def next_row_mac(
    conn: sqlite3.Connection,
    root: Path,
    artifact_id: str,
    changes: Mapping[str, Any],
) -> str | None:
    """D41 covered update: the new `row_mac` when the previous row verified,
    else `None` (the row stays or becomes unbound)."""
    found = _verified_binding(conn, root)
    if found is None:
        return None
    previous = _row_dict(conn, artifact_id)
    if previous is None:
        return None
    verifier = BindingVerifier("bound", found[0], found[1])
    if verifier.row(previous) != "bound":
        return None
    return row_mac(found[0], found[1], {**previous, **changes})


def insert_row_mac(
    conn: sqlite3.Connection, root: Path, values: Mapping[str, Any]
) -> str | None:
    """D41 insert: a MAC when the store is bound, else `None`."""
    found = _verified_binding(conn, root)
    if found is None:
        return None
    return row_mac(found[0], found[1], values)


def _write_binding_row(conn: sqlite3.Connection, root: Path, key: bytes) -> str:
    store_id = uuid.uuid4().hex
    db_ino = os.stat(Path(root) / ".rush" / "memory.db").st_ino
    conn.execute(
        "INSERT OR REPLACE INTO memory_store_binding (id, store_id, mac) "
        "VALUES (1, ?, ?)",
        (store_id, _store_mac(key, store_id, Path(root), db_ino)),
    )
    return store_id


def _binding_digest(
    binding: StoreBinding, store_id: str | None, rows: list[tuple[str, int, str]]
) -> str:
    body = {
        "store_binding": binding,
        "store_id": store_id,
        "rows": [list(r) for r in sorted(rows)],
    }
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _binding_inventory(conn: sqlite3.Connection, root: Path) -> dict[str, Any]:
    found = _verified_binding(conn, root)
    stored = _binding_row(conn)
    verifier = (
        BindingVerifier("bound", found[0], found[1]) if found else UNBOUND_VERIFIER
    )
    binding: StoreBinding = "bound" if found else "unbound"
    rows: list[tuple[str, int, str]] = []
    stated = unbound = 0
    if sqlite_has_table(conn, "memory_artifacts"):
        cur = conn.execute("SELECT * FROM memory_artifacts ORDER BY id")
        names = [d[0] for d in cur.description]
        for raw in cur.fetchall():
            row = dict(zip(names, raw, strict=True))
            content = row.get("content")
            text = content if isinstance(content, str) else repr(content)
            rows.append(
                (
                    str(row["id"]),
                    int(row.get("artifact_version") or 1),
                    payload_digest(text),
                )
            )
            if row.get("trust_tier") == "STATED":
                stated += 1
            if verifier.row(row) != "bound":
                unbound += 1
    return {
        "store_binding": binding,
        "store_id": stored[0] if stored else None,
        "rows": len(rows),
        "stated_rows": stated,
        "unbound_rows": unbound,
        "binding_digest": _binding_digest(binding, stored[0] if stored else None, rows),
    }


def _git_tracked(root: Path) -> bool | None:
    try:
        done = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "--error-unmatch",
                "--",
                ".rush/memory.db",
            ],
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode == 0:
        return True
    return False if done.returncode == 1 else None


def decode_content(stored: Any) -> Any:
    """`json.loads` that reports content nested too deeply to parse as `ValueError`,
    so every caller's corrupt-content handling covers it (72-T01 J6)."""
    try:
        return json.loads(stored)
    except RecursionError:
        raise ValueError("memory content is nested too deeply to parse") from None


def _content_or_none(stored: Any) -> dict[str, Any] | None:
    try:
        content = decode_content(stored)
    except (TypeError, ValueError):
        return None
    return content if isinstance(content, dict) else None


def _stored_text(stored: Any) -> str | None:
    if isinstance(stored, (bytes, bytearray)):
        try:
            return bytes(stored).decode("utf-8")
        except UnicodeDecodeError:
            return None
    return stored if isinstance(stored, str) else None


def sqlite_text(raw: bytes) -> str | bytes:
    """72-T02 D32 `text_factory` for every connection that selects `content`: valid
    UTF-8 TEXT decodes as usual; non-UTF-8 TEXT comes back as its exact stored bytes
    instead of raising `OperationalError` for the whole statement."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw


def embedding_text(content: dict[str, Any]) -> str:
    """MC12 §6.7: the exact, deterministic text embedded (and hashed for the vector cache
    key) for one artifact's `content` -- sorted-key JSON so the same content always produces
    the same text regardless of dict insertion order."""
    return json.dumps(content, ensure_ascii=False, sort_keys=True)


def _content_unchanged(stored: Any, content: dict[str, Any] | None) -> bool:
    """Whether `content` is the same value the `stored` column holds. Type-strict
    (sorted canonical dumps): `True` vs `1` or `1` vs `1.0` is new content. `None`
    means the caller carries the stored bytes over unparsed (corrupt content)."""
    if content is None:
        return True
    text = _stored_text(stored)
    if text is None:
        return False
    try:
        return json.dumps(decode_content(text), sort_keys=True) == json.dumps(
            content, sort_keys=True
        )
    except (TypeError, ValueError):
        return False


def _persisted_text(stored: Any, content: dict[str, Any]) -> str:
    """72-T01 fix round 2 (J1): the bytes a write of `content` persists. Content that
    is unchanged keeps the stored text verbatim (never canonicalized, so its binding
    stays valid); new content is serialized with `json.dumps`."""
    if isinstance(stored, str) and _content_unchanged(stored, content):
        return stored
    return json.dumps(content)


def _write_version(
    conn: sqlite3.Connection,
    artifact_id: str,
    *,
    content: dict[str, Any] | None,
    source: str,
    trust_tier: str,
    expected_version: int | None,
    tombstone: bool = False,
    subject: str | None = None,
    binding: VersionBinding | None = None,
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

    72-T05: the new version row records `binding` (or, omitted, the row's current
    applicability/task columns) with `binding_recorded = 1`.
    """
    row = conn.execute(
        "SELECT artifact_version, content, payload_hash, payload_hash_origin, "
        "applicability, task_project_id, task_worktree_id, task_id "
        "FROM memory_artifacts WHERE id = ?",
        (artifact_id,),
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
    # 72-T01 payload binding. New bytes are bound by this authorized write. Content that
    # parses equal to the stored row (archive, expiry, promotion, maintenance) keeps the
    # stored text verbatim and its binding unchanged -- never re-hashed, never
    # canonicalized -- so an honest non-canonical row stays matched and a tampered or
    # unbound row never becomes `write`-bound (plan §2.1 item 2; fix rounds 1-2, F1/J1).
    # Callers that rewrite `memory_artifacts.content` persist `_persisted_text` too, so
    # the live row and its latest version row hold the same bytes and binding.
    # BLOB-typed or corrupt stored content (`content=None`) is carried over as
    # stored and keeps its binding; it is never canonicalized into a `write`-bound
    # row (T068 J5/J6).
    if _content_unchanged(row[1], content):
        text: Any = _stored_text(row[1]) if content is not None else row[1]
        digest, origin = row[2], row[3]
    else:
        assert content is not None
        text = json.dumps(content)
        digest, origin = payload_digest(text), "write"
    snapshot = (
        (
            binding.applicability,
            binding.task_project_id,
            binding.task_worktree_id,
            binding.task_id,
        )
        if binding is not None
        else (row[4], row[5], row[6], row[7])
    )
    conn.execute(
        "INSERT INTO memory_artifact_versions "
        "(artifact_id, artifact_version, content, source, trust_tier, created_at, "
        "deleted, payload_hash, payload_hash_origin, applicability, task_project_id, "
        "task_worktree_id, task_id, binding_recorded) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,1)",
        (
            artifact_id,
            new_version,
            text,
            source,
            trust_tier,
            now,
            int(tombstone),
            digest,
            origin,
            *snapshot,
        ),
    )
    conn.execute(
        "UPDATE memory_artifacts SET payload_hash = ?, payload_hash_origin = ? "
        "WHERE id = ?",
        (digest, origin, artifact_id),
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
        content=decode_content(row["content"]),
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
        archived_at=_row_value(row, "archived_at"),
        applicability=_row_value(row, "applicability"),
        task_project_id=_row_value(row, "task_project_id"),
        task_worktree_id=_row_value(row, "task_worktree_id"),
        task_id=_row_value(row, "task_id"),
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
        conn.text_factory = sqlite_text
        conn.row_factory = sqlite3.Row
        return ReadOnlyOpenResult(available=True, connection=conn, mode="ro")
    mode = "ro&immutable=1"
    conn = sqlite3.connect(f"file:{quoted}?mode={mode}", uri=True)
    conn.text_factory = sqlite_text
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
        # ponytail: store writers close on `with` exit (`ClosingConnection`); any
        # other writer this process leaked (a bare `with sqlite3.connect()` stays
        # open until collected) is collected first, so it checkpoints and removes
        # its WAL now, not mid-read -- a read-only connection that closes last
        # cannot checkpoint and would strand committed pages in the `-wal`.
        # Ceiling: a writer in another process can still close first.
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


# 72-T05: table -> additive columns. The one declaration the migration loop below
# and the 72-T02 `writable_open_ddl_free` schema check both read.
APPLICABILITY_MIGRATION_COLUMNS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    ("memory_artifacts", tuple((name, "TEXT") for name in APPLICABILITY_COLUMNS)),
    ("memory_artifact_versions", VERSION_BINDING_COLUMNS),
    ("memory_handoff_sessions", (("sender_task_id", "TEXT"),)),
)


def _migrate_applicability_columns(conn: sqlite3.Connection) -> None:
    """72-T05 additive migration, inside the caller's transaction (no commit):
    the current-row applicability/task columns, the version-row binding snapshot
    and `memory_handoff_sessions.sender_task_id`, each only when absent. Existing
    rows and versions keep NULL (`binding_recorded` NULL = pre-T05 history)."""
    for table, columns in APPLICABILITY_MIGRATION_COLUMNS:
        if not sqlite_has_table(conn, table):
            continue
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for column, col_type in columns:
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")


HANDOFF_SENDER_COLUMNS: tuple[tuple[str, str], ...] = (
    ("sender_grant_id", "TEXT"),
    ("sender_owner_kind", "TEXT"),
    ("sender_owner_id", "TEXT"),
    ("sender_project_id", "TEXT"),
    ("sender_worktree_id", "TEXT"),
    ("sender_policy_revision", "INTEGER"),
)

# 72-T02 R2: the declarations every additive migration below adds, shared by those
# migration loops and `writable_open_ddl_free()` (one source of truth; a later
# migration adds its declaration here in the same change).
_EXPIRY_COLUMNS: tuple[tuple[str, str], ...] = (
    ("expires_at", "REAL"),
    ("expired_at", "REAL"),
    ("expired_by", "TEXT"),
)
_VERSION_COLUMN = ("artifact_version", "INTEGER NOT NULL DEFAULT 1")
_ARCHIVED_COLUMN = ("archived_at", "REAL")
_CHANGES_SUBJECT_COLUMN = ("subject", "TEXT")
_HANDOFF_REVOKED_COLUMN = ("revoked_at", "REAL")
_ORPHANED_COLUMN = ("orphaned_at", "REAL")
_OWNER_SCOPE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("owner_scope_kind", "TEXT"),
    ("owner_scope_id", "TEXT"),
)
_ROW_MAC_COLUMN = ("row_mac", "TEXT")
# Created by `_migrate_owner_scope_columns` rather than `_SCHEMA_SQL` (see there).
_OWNER_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_memory_owner "
    "ON memory_artifacts(owner_scope_kind, owner_scope_id)"
)
_POST_SCHEMA_SQL: tuple[str, ...] = (_OWNER_INDEX_SQL,)
_MIGRATION_COLUMNS: tuple[tuple[str, str], ...] = (
    *(("memory_artifacts", name) for name, _type in _EXPIRY_COLUMNS),
    ("memory_artifacts", _VERSION_COLUMN[0]),
    ("memory_artifacts", _ARCHIVED_COLUMN[0]),
    ("memory_changes", _CHANGES_SUBJECT_COLUMN[0]),
    ("memory_handoff_sessions", _HANDOFF_REVOKED_COLUMN[0]),
    ("memory_artifacts", _ORPHANED_COLUMN[0]),
    *(("memory_artifacts", name) for name, _type in _OWNER_SCOPE_COLUMNS),
    ("memory_artifacts", _ROW_MAC_COLUMN[0]),
    *(("memory_handoff_sessions", name) for name, _type in HANDOFF_SENDER_COLUMNS),
    *(
        (table, name)
        for table in ("memory_artifacts", "memory_artifact_versions")
        for name in PAYLOAD_HASH_COLUMNS
    ),
    *(
        (table, name)
        for table, columns in APPLICABILITY_MIGRATION_COLUMNS
        for name, _type in columns
    ),
)
_DDL_NAME_RE = re.compile(
    r"CREATE (?:UNIQUE )?(?:VIRTUAL )?(?:TABLE|INDEX|TRIGGER) IF NOT EXISTS (\w+)"
)


def _write_local_gitignore(rush_dir: Path) -> None:
    """D41/D1: a `.rush` this process created ignores everything in it."""
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(rush_dir / ".gitignore", flags, 0o644)
    except OSError:
        return
    try:
        os.write(fd, b"*\n")
    except OSError:
        pass
    finally:
        os.close(fd)


CommitCheck = Callable[[], "tuple[str, str] | None"]
# 72-T06 D29 (72-T05 seam): called once, inside the effect's transaction and before
# commit, with `{artifact_id, artifact_version, result_refs, result}`.
ReceiptWriter = Callable[[sqlite3.Connection, dict[str, Any]], Any]


class MemoryAccessChanged(Exception):
    """D1 race rule: the resolved access changed before a mutation committed."""

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(f"{code}: {reason}")
        self.code = code
        self.reason = reason


def run_commit_check(
    conn: sqlite3.Connection, commit_check: CommitCheck | None
) -> None:
    """Call `commit_check` after every effect, immediately before commit; a
    failure rolls the transaction back and raises `MemoryAccessChanged`."""
    if commit_check is None:
        return
    failure = commit_check()
    if failure is not None:
        conn.rollback()
        raise MemoryAccessChanged(*failure)


def write_checked_artifact(
    project_root: Path,
    artifact: MemoryArtifact,
    *,
    commit_check: CommitCheck | None = None,
) -> MemoryArtifact:
    """D4: an internal writer's `TypedArtifactStore(root).write(artifact)`. When this
    call creates the store and `commit_check` then refuses the write, the database,
    cache directory, store key and every other path the creation added are removed
    again, so a denied first write leaves nothing behind."""
    root = Path(project_root).resolve()
    rush = root / ".rush"
    # Files and deeper directories first: removal runs in this order.
    candidates = [
        rush / "memory.db-shm",
        rush / "memory.db-wal",
        rush / "memory.db",
        rush / "cache" / "merkle.json",
        rush / "cache",
        rush / ".gitignore",
        rush,
    ]
    key_dir = _store_key_dir()
    if key_dir is not None:
        candidates = [
            key_dir / _STORE_KEY_NAME,
            key_dir,
            key_dir.parent,
            *candidates,
        ]
    # security-1: the store lock spans the snapshot through the cleanup, and every
    # store or key creation takes it too, so no path in `created` is another
    # writer's, whatever data root's policy lock that writer holds.
    with hold_store_lock(root):
        created = (
            []
            if os.path.lexists(rush / "memory.db")
            else [p for p in candidates if not os.path.lexists(p)]
        )
        try:
            return TypedArtifactStore(root).write(artifact, commit_check=commit_check)
        except MemoryAccessChanged:
            for path in created:
                try:
                    if path.is_dir() and not path.is_symlink():
                        path.rmdir()
                    else:
                        path.unlink()
                except OSError:
                    pass
            raise


@contextmanager
def hold_store_lock(project_root: Path) -> Iterator[None]:
    """security-1: serializes every store open and D41 key creation with a refused
    first write's snapshot-to-cleanup window, across writers of every data root:
    the default data root's policy lock (that root also holds the shared key), or
    the project root's directory lock when the default root is unavailable or cannot
    be created (no key can exist then). Reentrant within one thread; a caller that
    also holds an access's own policy lock takes that one first."""
    from rush.dashboard.state import PolicyLockRootUncreatable
    from rush.memory.authorization import MemoryPolicyError, hold_policy_lock

    with ExitStack() as stack:
        try:
            stack.enter_context(hold_policy_lock())
        except (MemoryPolicyError, PolicyLockRootUncreatable):
            stack.enter_context(hold_policy_lock(data_root=project_root))
        yield


def _bind_overlay_store(
    project_root: Path,
    *,
    approve: bool,
    expected_binding_digest: Any,
    access: MemoryAccess | None,
) -> dict[str, Any]:
    """73-T02 D41 (b): preview or approve the personal overlay store's binding.

    Only a policy access resolved for the overlay owner with the overlay storage
    root and the required operations ({overlay_read, list} to preview, write to
    approve) reaches the store; the store is opened, inventoried and MAC-bound at
    that storage root, while D1 row 1a is decided on `project_root`. Every refusal,
    including a stale digest, leaves the key, DB, binding and row MACs unchanged."""
    from rush.memory.authorization import hold_policy_lock, user_overlay_owner_scope
    from rush.memory.retrieval import memory_policy_decision

    root = Path(project_root).resolve()
    data_root = access.data_root if access is not None else None
    mode, reason = memory_policy_decision(root, data_root=data_root)
    if mode == "unavailable":
        return {"code": "E_PERMISSION", "reason": reason}
    owner = user_overlay_owner_scope(data_root=data_root)
    storage = Path(owner.id)
    required = {"write"} if approve else {"overlay_read", "list"}
    if (
        access is None
        or access.kind != "policy"
        or access.owner_scope != owner
        # ponytail: `storage_root` is 72-T05's MemoryAccess field; read by name so
        # this branch type-checks before T05 lands, and refuses until it does.
        or getattr(access, "storage_root", None) != storage
        or not required <= access.required_operations
    ):
        return {"code": "E_PERMISSION", "reason": "policy_grant_required"}
    db = storage / ".rush" / "memory.db"
    if not approve:
        try:
            inventory = read_sqlite_readonly(
                db, lambda conn: _binding_inventory(conn, storage)
            )
        except MemoryStoreUnreadableError as exc:
            return {"code": exc.code, "reason": "memory_store_unreadable"}
        if inventory is None:
            return {"code": "E_NOT_FOUND", "reason": "store_absent"}
        return {"code": "OK", **inventory, "git_tracked": _git_tracked(storage)}
    if not isinstance(expected_binding_digest, str):
        return {
            "code": "E_INPUT",
            "field": "expected_binding_digest",
            "message": "expected_binding_digest must be the preview's digest",
        }
    try:
        with hold_policy_lock(data_root=data_root):
            if not db.exists():
                return {"code": "E_NOT_FOUND", "reason": "store_absent"}
            with closing(sqlite3.connect(str(db), timeout=10.0)) as conn:
                conn.execute("BEGIN IMMEDIATE")
                inventory = _binding_inventory(conn, storage)
                if inventory["binding_digest"] != expected_binding_digest:
                    conn.rollback()
                    return {"code": "E_VERSION", "reason": "store_changed"}
                # The key is read or published only once the digest re-matched.
                key = ensure_store_key()
                if key is None:
                    conn.rollback()
                    return {"code": "E_UNAVAILABLE", "reason": "store_key_unavailable"}
                conn.execute(_BINDING_TABLE_SQL)
                columns = {
                    row[1]
                    for row in conn.execute("PRAGMA table_info(memory_artifacts)")
                }
                if "row_mac" not in columns:
                    conn.execute("ALTER TABLE memory_artifacts ADD COLUMN row_mac TEXT")
                store_id = _write_binding_row(conn, storage, key)
                cur = conn.execute("SELECT * FROM memory_artifacts")
                names = [d[0] for d in cur.description]
                rows = [dict(zip(names, r, strict=True)) for r in cur.fetchall()]
                for row in rows:
                    conn.execute(
                        "UPDATE memory_artifacts SET row_mac = ? WHERE id = ?",
                        (row_mac(key, store_id, row), row["id"]),
                    )
                conn.commit()
    except OSError:
        return {"code": "E_PERMISSION", "reason": "lock_unavailable"}
    return {
        "code": "OK",
        "store_binding": "bound",
        "store_id": store_id,
        "bound_rows": len(rows),
    }


class TypedArtifactStore:
    """WAL-mode SQLite store for `MemoryArtifact` rows across every memory subject."""

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = (
            Path(project_root).resolve() if project_root else Path.cwd().resolve()
        )
        self.db_path = self.project_root / ".rush" / "memory.db"
        self._owner_scope_default = legacy_owner_scope(self.project_root)
        with hold_store_lock(self.project_root):
            rush_created = not os.path.lexists(self.db_path.parent)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            if rush_created:
                _write_local_gitignore(self.db_path.parent)
            self._init_db()

    _readonly_conn: sqlite3.Connection | None = None
    # 72-T06 D18/D41: `_create_with_import` binds its in-memory store only once the
    # publication temp exists, so `_init_db` must not bind it to a path.
    _defer_binding: bool = False

    @property
    def _merkle(self) -> MerkleInvalidator:
        # 72-T04 R11: built on use only; constructing it creates `.rush/cache`, which
        # opening a store (a maintenance sweep included) never does.
        return MerkleInvalidator(project_root=self.project_root)

    def _connect(self) -> sqlite3.Connection:
        if self._readonly_conn is not None:
            return self._readonly_conn
        conn = sqlite3.connect(
            str(self.db_path), timeout=10.0, factory=ClosingConnection
        )
        conn.text_factory = sqlite_text
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        created = not self.db_path.exists()
        with self._connect() as conn:
            candidate_fts_existed = (
                conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' "
                    "AND name='memory_fts_candidates'"
                ).fetchone()
                is not None
            )
            # 72-T01: existing tables are migrated *before* `_SCHEMA_SQL` creates any
            # missing FTS table, so the backfill's UPDATE fires only triggers whose
            # index already holds these rows (see `_migrate_owner_scope_columns`). The
            # write lock makes the column check and ALTER one step for concurrent
            # openers; a fresh store gets the columns from `_SCHEMA_SQL` itself.
            conn.execute("BEGIN IMMEDIATE")
            _migrate_payload_hash_columns(conn)
            conn.commit()
            conn.executescript(_SCHEMA_SQL)
            self._migrate_expiry_columns(conn)
            self._migrate_version_column(conn)
            self._migrate_changes_subject_column(conn)
            self._migrate_archived_column(conn)
            self._migrate_owner_scope_columns(conn)
            self._migrate_handoff_recovery_columns(conn)
            self._migrate_binding_columns(conn)
            # 72-T05: the additive columns in one write-locked step (no inner commit).
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            _migrate_applicability_columns(conn)
            self._ensure_cursor_key(conn)
            if not candidate_fts_existed:
                self._backfill_candidate_fts(conn)
            if created and not self._defer_binding:
                # D41: the creating transaction binds the new store to this root.
                key = ensure_store_key()
                if key is not None:
                    _write_binding_row(conn, self.project_root, key)
            conn.commit()
            # 72-T06 D29/D30 post-script: v2 receipt columns and index, the event
            # trigger and (when D30 allows) the event index, in one transaction.
            conn.execute("BEGIN IMMEDIATE")
            _apply_v2_schema(conn)
            _create_event_index_if_clean(conn)
            conn.commit()

    def _migrate_binding_columns(self, conn: sqlite3.Connection) -> None:
        """72-T01 additive migration (writable constructor only): D41 `row_mac`
        and the D21 handoff sender columns. Existing rows stay unbound."""
        artifact_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(memory_artifacts)")
        }
        if _ROW_MAC_COLUMN[0] not in artifact_columns:
            conn.execute(
                "ALTER TABLE memory_artifacts ADD COLUMN "
                f"{_ROW_MAC_COLUMN[0]} {_ROW_MAC_COLUMN[1]}"
            )
        session_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(memory_handoff_sessions)")
        }
        for column, col_type in HANDOFF_SENDER_COLUMNS:
            if column not in session_columns:
                conn.execute(
                    f"ALTER TABLE memory_handoff_sessions ADD COLUMN {column} {col_type}"
                )

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
        self,
        owner_filter: str | None = None,
        *,
        include_internal: bool = False,
        access: MemoryAccess | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """P69-01.2n shared primitive: reads the memory inventory and calls
        `current_generation()` inside the same read transaction/connection,
        returning `(memories, generation)` as one atomic pair -- never a
        memory list from before a generation bump paired with the bumped
        generation, or vice versa.

        T18: bookkeeping rows (`is_internal_memory_source`) are excluded by
        default -- diagnostic `include_internal=True` restores exactly the
        pre-T18 row set.

        72-T01 D1 `list`: a policy `access` keeps only its owner's rows of the
        sources it approves (the generation still pairs with the whole read)."""
        from rush.memory.retrieval import reader_row_allowed

        with self._connect() as conn:
            conn.execute("BEGIN")
            columns = {
                r[1] for r in conn.execute("PRAGMA table_info(memory_artifacts)")
            }
            owner_columns = "".join(
                f", {c}" for c in ("owner_scope_kind", "owner_scope_id") if c in columns
            )
            rows = conn.execute(
                "SELECT id, subject, trust_tier, source, artifact_version, archived_at"
                f"{owner_columns} FROM memory_artifacts ORDER BY id ASC"
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
            and (access is None or reader_row_allowed(access, self.project_root, row))
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
        """P69-01.2f: caller owns the transaction -- this only inserts. 72-T06 D29: a
        `v2:` id is refused before any SQL."""
        _reject_reserved_receipt_ids(operation_id)
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

    def _write_v2_receipt(
        self,
        conn: sqlite3.Connection,
        *,
        invocation_id: str,
        effect_id: str,
        request_digest: str,
        artifact_id: str | None,
        kind: str,
        revision: int | None,
        payload: dict[str, Any],
    ) -> str:
        """D29: the one writer of a `v2:` receipt -- a plain INSERT, so a second
        effect under the same ids fails instead of replacing the first. Caller owns
        the transaction. Returns the derived `operation_id`."""
        if not (
            isinstance(invocation_id, str)
            and invocation_id
            and isinstance(effect_id, str)
            and effect_id
        ):
            from rush.memory.authorization import MemoryPolicyError

            raise MemoryPolicyError("E_INPUT", "receipt_ids_required")
        operation_id = v2_operation_id(invocation_id, effect_id)
        conn.execute(
            "INSERT INTO mutation_receipts "
            "(operation_id, artifact_id, kind, revision, payload, created_at, "
            "invocation_id, effect_id, request_digest) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                operation_id,
                artifact_id,
                kind,
                revision,
                json.dumps(payload),
                time.time(),
                invocation_id,
                effect_id,
                request_digest,
            ),
        )
        return operation_id

    @staticmethod
    def _find_v2_receipt(
        conn: sqlite3.Connection, invocation_id: str, effect_id: str
    ) -> dict[str, Any] | None:
        """D29 replay lookup by `(invocation_id, effect_id)`. A table without the v2
        columns (a read-only view of an older store) is `migration_required`."""
        if not v2_receipts_ready(conn):
            raise MemoryMigrationRequiredError(
                readonly_view_reason("migration_required"),
                reason="migration_required",
            )
        row = conn.execute(
            "SELECT * FROM mutation_receipts WHERE invocation_id = ? AND effect_id = ?",
            (invocation_id, effect_id),
        ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(row["payload"]) if row["payload"] is not None else None
        except (TypeError, ValueError):
            payload = None
        return {
            "operation_id": row["operation_id"],
            "artifact_id": row["artifact_id"],
            "kind": row["kind"],
            "revision": row["revision"],
            "payload": payload,
            "created_at": row["created_at"],
            "invocation_id": row["invocation_id"],
            "effect_id": row["effect_id"],
            "request_digest": row["request_digest"],
        }

    @staticmethod
    def read_artifact_receipts_readonly(
        project_root: Path, artifact_id: str, version: int, *, limit: int = 8
    ) -> list[dict[str, Any]]:
        """Bounded committed effects for one exact artifact revision; never opens a writer."""
        db = Path(project_root) / ".rush" / "memory.db"

        def read(conn: sqlite3.Connection) -> list[dict[str, Any]]:
            if not sqlite_has_table(conn, "mutation_receipts"):
                return []
            rows = conn.execute(
                "SELECT operation_id, kind, revision, created_at "
                "FROM mutation_receipts WHERE artifact_id = ? AND revision = ? "
                "ORDER BY created_at DESC, operation_id LIMIT ?",
                (artifact_id, version, max(1, min(limit, 32))),
            ).fetchall()
            return [
                {
                    "id": row["operation_id"],
                    "artifact_version": row["revision"],
                    "kind": row["kind"],
                    "origin": "mutation",
                    "timestamp": row["created_at"],
                }
                for row in rows
            ]

        return read_sqlite_readonly(db, read) or []

    @staticmethod
    def get_receipt_readonly(
        project_root: Path, operation_id: str
    ) -> tuple[Literal["absent", "present", "unavailable"], dict[str, Any] | None]:
        """D4 receipt inspection over one read-only connection: `absent` (no DB,
        table or row), `unavailable` (corrupt, busy, WAL index missing or an
        undecodable payload) or `present` with the receipt (payload `None` for
        NULL). Creates no file, `-wal` or `-shm`."""
        db = Path(project_root) / ".rush" / "memory.db"

        def read(conn: sqlite3.Connection) -> tuple[str, dict[str, Any] | None]:
            if not sqlite_has_table(conn, "mutation_receipts"):
                return "absent", None
            row = conn.execute(
                "SELECT * FROM mutation_receipts WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
            if row is None:
                return "absent", None
            raw = row["payload"]
            try:
                payload = None if raw is None else json.loads(raw)
            except (TypeError, ValueError):
                return "unavailable", None
            return "present", {
                "operation_id": row["operation_id"],
                "artifact_id": row["artifact_id"],
                "kind": row["kind"],
                "revision": row["revision"],
                "payload": payload,
                "created_at": row["created_at"],
            }

        try:
            result = read_sqlite_readonly(db, read)
        except MemoryStoreUnreadableError:
            return "unavailable", None
        except sqlite3.DatabaseError:
            return "unavailable", None
        if result is None:
            return "absent", None
        state, receipt = result
        return cast("Literal['absent', 'present', 'unavailable']", state), receipt

    @staticmethod
    def bind_store(
        project_root: Path,
        *,
        approve: bool,
        expected_binding_digest: Any = None,
        access: MemoryAccess | None = None,
        overlay: bool = False,
    ) -> dict[str, Any]:
        """D41: preview (read-only) or approve this store's local binding.

        Approval re-binds the store to this root under the local key and MACs
        every row, after `expected_binding_digest` re-matches under the policy
        lock and `BEGIN IMMEDIATE`."""
        if overlay:
            return _bind_overlay_store(
                project_root,
                approve=approve,
                expected_binding_digest=expected_binding_digest,
                access=access,
            )
        root = Path(project_root).resolve()
        db = root / ".rush" / "memory.db"
        if not approve:
            try:
                inventory = read_sqlite_readonly(
                    db, lambda conn: _binding_inventory(conn, root)
                )
            except MemoryStoreUnreadableError as exc:
                return {"code": exc.code, "reason": "memory_store_unreadable"}
            if inventory is None:
                return {"code": "E_NOT_FOUND", "reason": "store_absent"}
            return {"code": "OK", **inventory, "git_tracked": _git_tracked(root)}
        if not isinstance(expected_binding_digest, str):
            return {
                "code": "E_INPUT",
                "field": "expected_binding_digest",
                "message": "expected_binding_digest must be the preview's digest",
            }
        from rush.memory.authorization import hold_policy_lock
        from rush.memory.retrieval import (
            MemoryAccess,
            memory_policy_decision,
            recheck_failure,
        )

        data_root = access.data_root if access is not None else None
        if access is not None and access.project_root != root:
            return {"code": "E_PERMISSION", "reason": "policy_grant_required"}
        mode, reason = memory_policy_decision(root, data_root=data_root)
        if mode == "unavailable":
            return {"code": "E_PERMISSION", "reason": reason}
        owner = legacy_owner_scope(root)
        if mode == "policy":
            if access is None:
                access, _why = MemoryAccess.resolve_with_reason(
                    root, operation="write", apply=True, owner_scope=owner
                )
            if (
                access is None
                or access.kind != "policy"
                or "write" not in access.required_operations
                or access.owner_scope != owner
            ):
                return {"code": "E_PERMISSION", "reason": "policy_grant_required"}
        if access is None:
            # security-15: a legacy approval is rechecked like a policy one, so a
            # project enrolled before the lock is taken is refused.
            access = MemoryAccess.legacy(
                root, (), owner_scope=owner, operation="write", data_root=data_root
            )
        try:
            with hold_policy_lock(data_root=data_root), hold_store_lock(root):
                failure = recheck_failure(access)
                if failure is not None:
                    return {"code": failure[0], "reason": failure[1]}
                key = ensure_store_key()
                if key is None:
                    return {"code": "E_UNAVAILABLE", "reason": "store_key_unavailable"}
                if not db.exists():
                    return {"code": "E_NOT_FOUND", "reason": "store_absent"}
                with closing(sqlite3.connect(str(db), timeout=10.0)) as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    inventory = _binding_inventory(conn, root)
                    if inventory["binding_digest"] != expected_binding_digest:
                        conn.rollback()
                        return {"code": "E_VERSION", "reason": "store_changed"}
                    conn.execute(_BINDING_TABLE_SQL)
                    columns = {
                        row[1]
                        for row in conn.execute("PRAGMA table_info(memory_artifacts)")
                    }
                    if "row_mac" not in columns:
                        conn.execute(
                            "ALTER TABLE memory_artifacts ADD COLUMN row_mac TEXT"
                        )
                    store_id = _write_binding_row(conn, root, key)
                    cur = conn.execute("SELECT * FROM memory_artifacts")
                    names = [d[0] for d in cur.description]
                    rows = [dict(zip(names, r, strict=True)) for r in cur.fetchall()]
                    for row in rows:
                        conn.execute(
                            "UPDATE memory_artifacts SET row_mac = ? WHERE id = ?",
                            (row_mac(key, store_id, row), row["id"]),
                        )
                    failure = recheck_failure(access)
                    if failure is not None:
                        conn.rollback()
                        return {"code": failure[0], "reason": failure[1]}
                    conn.commit()
        except OSError:
            return {"code": "E_PERMISSION", "reason": "lock_unavailable"}
        return {
            "code": "OK",
            "store_binding": "bound",
            "store_id": store_id,
            "bound_rows": len(rows),
        }

    def search_candidates(
        self,
        subject: MemorySubject | Sequence[MemorySubject],
        query: str,
        *,
        source_allowlist: Iterable[str],
        trust_tiers: Iterable[str] | None = None,
        include_expired: bool = False,
        scan_offset: int = 0,
        scan_limit: int = 64,
        include_archived: bool = False,
        owner_scope: OwnerScope | None = None,
        now: float | None = None,
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
        subjects = _subject_list(subject)
        if not subjects:
            return []
        quoted_query = '"' + query.replace('"', '""') + '"'
        source_clause, source_params = source_predicate_sql("ma.source", sources)
        clauses = [
            "memory_fts_candidates MATCH ?",
            _subject_clause("ma.subject", subjects),
            source_clause,
        ]
        params: list[Any] = [quoted_query, *subjects, *source_params]
        tiers = list(trust_tiers) if trust_tiers is not None else []
        if tiers:
            clauses.append(f"ma.trust_tier IN ({','.join('?' for _ in tiers)})")
            params.extend(tiers)
        if not include_expired:
            clauses.append("ma.expired_at IS NULL")
        # 72-T01 SQL prefilters; `retrieval.evaluate_artifact_visibility` stays the
        # authoritative decision on every returned row.
        if not include_archived:
            clauses.append("ma.archived_at IS NULL")
        owner_clause, owner_params = self._owner_prefilter("ma.", owner_scope)
        if owner_clause:
            clauses.append(owner_clause)
            params.extend(owner_params)
        if now is not None and not include_expired:
            clauses.append("(ma.expires_at IS NULL OR ma.expires_at > ?)")
            params.append(now)
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
        subject: MemorySubject | Sequence[MemorySubject],
        *,
        source_allowlist: Iterable[str],
        trust_tiers: Iterable[str] | None = None,
        include_expired: bool = False,
        include_archived: bool = False,
        scan_offset: int = 0,
        scan_limit: int = 512,
        owner_scope: OwnerScope | None = None,
        now: float | None = None,
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
        subjects = _subject_list(subject)
        if not subjects:
            return []
        source_clause, source_params = source_predicate_sql("source", sources)
        clauses = [_subject_clause("subject", subjects), source_clause]
        params: list[Any] = [*subjects, *source_params]
        tiers = list(trust_tiers) if trust_tiers is not None else []
        if tiers:
            clauses.append(f"trust_tier IN ({','.join('?' for _ in tiers)})")
            params.extend(tiers)
        if not include_expired:
            clauses.append("expired_at IS NULL")
        if not include_archived:
            clauses.append("archived_at IS NULL")
        owner_clause, owner_params = self._owner_prefilter("", owner_scope)
        if owner_clause:
            clauses.append(owner_clause)
            params.extend(owner_params)
        if now is not None and not include_expired:
            clauses.append("(expires_at IS NULL OR expires_at > ?)")
            params.append(now)
        params.extend([scan_limit, scan_offset])
        sql = (
            "SELECT * FROM memory_artifacts "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY id ASC LIMIT ? OFFSET ?"
        )
        with self._connect() as conn:
            cur = conn.execute(sql, params)
            return cur.fetchmany(scan_limit)

    def _owner_prefilter(
        self, prefix: str, owner_scope: OwnerScope | None
    ) -> tuple[str, list[Any]]:
        """72-T01 SQL owner prefilter matching `owner_scope_for_row()`: a row with no
        stored owner belongs to this store's legacy owner."""
        if owner_scope is None:
            return "", []
        clause = f"({prefix}owner_scope_kind = ? AND {prefix}owner_scope_id = ?)"
        if owner_scope == self._owner_scope_default:
            clause = (
                f"({clause} OR {prefix}owner_scope_kind IS NULL "
                f"OR {prefix}owner_scope_kind = '' OR {prefix}owner_scope_id IS NULL "
                f"OR {prefix}owner_scope_id = '')"
            )
        return clause, [owner_scope.kind, owner_scope.id]

    def contest_peers(
        self,
        subject: str,
        keys: Iterable[tuple[str, str, str | None]],
        sources: Sequence[str],
    ) -> dict[tuple[str, str, str | None], list[sqlite3.Row]]:
        """D34: one untruncated scan for the rows of `subject` whose `(owner kind,
        owner id, symbol_ref)` -- owner NULL-defaulted, `symbol_ref` NULL-equal -- is
        one of `keys` and whose source passes the D40 predicate over `sources`,
        grouped by that key in ID order (callers exclude the row itself and still
        decide each peer)."""
        wanted = sorted(set(keys), key=repr)
        if not sources or not wanted:
            return {}
        default = self._owner_scope_default
        source_clause, source_params = source_predicate_sql("a.source", sources)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT a.* FROM memory_artifacts AS a WHERE a.subject = ? "
                "AND EXISTS (SELECT 1 FROM json_each(?) AS k "
                "WHERE COALESCE(a.owner_scope_kind, ?) = json_extract(k.value, '$[0]') "
                "AND COALESCE(a.owner_scope_id, ?) = json_extract(k.value, '$[1]') "
                "AND a.symbol_ref IS json_extract(k.value, '$[2]')) "
                f"AND {source_clause} ORDER BY a.id",
                (subject, json.dumps(wanted), default.kind, default.id, *source_params),
            ).fetchall()
        grouped: dict[tuple[str, str, str | None], list[sqlite3.Row]] = {}
        for row in rows:
            kind = row["owner_scope_kind"]
            identifier = row["owner_scope_id"]
            key = (
                default.kind if kind is None else kind,
                default.id if identifier is None else identifier,
                row["symbol_ref"],
            )
            grouped.setdefault(key, []).append(row)
        return grouped

    def contradiction_pairs(
        self, versions: Iterable[tuple[str, int]]
    ) -> set[tuple[tuple[str, int], tuple[str, int]]]:
        """D34: every `contradicts` relation touching one of these exact versions,
        as `((id, version), (id, version))` in both orientations (one scan)."""
        wanted = sorted(set(versions))
        if not wanted:
            return set()
        with self._connect() as conn:
            if not sqlite_has_table(conn, "memory_relations"):
                return set()
            rows = conn.execute(
                "SELECT r.source_id, r.source_version, r.target_id, r.target_version "
                "FROM memory_relations AS r WHERE r.kind = 'contradicts' AND EXISTS ("
                "SELECT 1 FROM json_each(?) AS v WHERE "
                "(r.source_id = json_extract(v.value, '$[0]') "
                "AND r.source_version = json_extract(v.value, '$[1]')) OR "
                "(r.target_id = json_extract(v.value, '$[0]') "
                "AND r.target_version = json_extract(v.value, '$[1]')))",
                (json.dumps(wanted),),
            ).fetchall()
        pairs: set[tuple[tuple[str, int], tuple[str, int]]] = set()
        for source_id, source_version, target_id, target_version in rows:
            left, right = (source_id, source_version), (target_id, target_version)
            pairs.add((left, right))
            pairs.add((right, left))
        return pairs

    def get_current_row(
        self, artifact_id: str, *, conn: sqlite3.Connection | None = None
    ) -> sqlite3.Row | None:
        """72-T01: the raw current row for one ID (what `evaluate_artifact_visibility`
        decides on), or `None`. 72-T02 R13: an open `conn` (a `fresh_reader()`) runs
        the read inside the caller's own read transaction."""
        sql = "SELECT * FROM memory_artifacts WHERE id = ?"
        if conn is not None:
            return cast(
                "sqlite3.Row | None", conn.execute(sql, (artifact_id,)).fetchone()
            )
        with self._connect() as own_conn:
            row = own_conn.execute(sql, (artifact_id,)).fetchone()
        return cast("sqlite3.Row | None", row)

    def get_version_binding(
        self, artifact_id: str, version: int
    ) -> tuple[str | bytes, str | None, str | None] | None:
        """72-T02 D32: `(content, payload_hash, payload_hash_origin)` of one exact
        version row, or `None` when that version does not exist (or is outside
        SQLite's integer range). `content` is `bytes` when it is a BLOB or TEXT that
        does not decode as UTF-8 (`sqlite_text`)."""
        if not sqlite_integer_in_range(version):
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT content, payload_hash, payload_hash_origin "
                "FROM memory_artifact_versions "
                "WHERE artifact_id = ? AND artifact_version = ?",
                (artifact_id, version),
            ).fetchone()
        return (row[0], row[1], row[2]) if row else None

    def get_version_payload(
        self, artifact_id: str, version: int
    ) -> tuple[str, str | None] | None:
        """72-T01 (X2): `(content, payload_hash)` for one exact version, or `None` when
        that version does not exist. `get_version_content()` is unchanged."""
        if not sqlite_integer_in_range(version):
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT content, payload_hash FROM memory_artifact_versions "
                "WHERE artifact_id = ? AND artifact_version = ?",
                (artifact_id, version),
            ).fetchone()
        return (row[0], row[1]) if row else None

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
        commit_check: CommitCheck | None = None,
        receipt_writer: ReceiptWriter | None = None,
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

        72-T06 D29: `receipt_writer` records the batch's one v2 receipt (result refs
        are the tombstones) inside this transaction, before commit.
        """
        _reject_reserved_receipt_ids(
            receipt_operation_id, *(receipt_operation_ids or {}).values()
        )
        with self._connect() as conn:
            # A preview only reads, so it also runs over a read-only view.
            conn.execute("BEGIN IMMEDIATE" if apply else "BEGIN")
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
            if receipt_writer is not None:
                receipt_writer(
                    conn,
                    {
                        "artifact_id": None,
                        "artifact_version": None,
                        "result_refs": [
                            {"artifact_id": artifact_id, "artifact_version": version}
                            for artifact_id, version, _source in tombstones
                        ],
                        "result": {"applied": True, "affected": affected},
                    },
                )
            run_commit_check(conn, commit_check)
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
        commit_check: CommitCheck | None = None,
        receipt_writer: ReceiptWriter | None = None,
        task_binding: tuple[str, str, str] | None = None,
    ) -> dict[str, Any]:
        """Single-artifact content edit under compare-and-swap (P65-07.3, plan §6.4).
        72-T06 D29: `receipt_writer` records the v2 receipt before commit.
        72-T06 D31: `task_binding` `(project_id, worktree_id, task_id)` is stamped on the
        new version and the row; omitted, the new version copies the row's binding.

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
        _reject_reserved_receipt_ids(receipt_operation_id)
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
            stamp = (
                VersionBinding(
                    _row_value(row, "applicability"),
                    task_binding[0],
                    task_binding[1],
                    task_binding[2],
                )
                if task_binding is not None
                else None
            )
            new_version = _write_version(
                conn,
                artifact_id,
                content=sanitized_content,
                source=row["source"],
                trust_tier=new_trust_tier,
                expected_version=expected_version,
                subject=scope,
                binding=stamp,
            )
            new_text = _persisted_text(row["content"], sanitized_content)
            changes: dict[str, Any] = {
                "content": new_text,
                "trust_tier": new_trust_tier,
            }
            if task_binding is not None:
                changes.update(
                    task_project_id=task_binding[0],
                    task_worktree_id=task_binding[1],
                    task_id=task_binding[2],
                )
            mac = next_row_mac(conn, self.project_root, artifact_id, changes)
            try:
                if task_binding is None:
                    conn.execute(
                        "UPDATE memory_artifacts SET content = ?, artifact_version = ?, "
                        "trust_tier = ?, signature = NULL, promoted_at = NULL, "
                        "row_mac = ? WHERE id = ?",
                        (new_text, new_version, new_trust_tier, mac, artifact_id),
                    )
                else:
                    conn.execute(
                        "UPDATE memory_artifacts SET content = ?, artifact_version = ?, "
                        "trust_tier = ?, signature = NULL, promoted_at = NULL, "
                        "task_project_id = ?, task_worktree_id = ?, task_id = ?, "
                        "row_mac = ? WHERE id = ?",
                        (
                            new_text,
                            new_version,
                            new_trust_tier,
                            *task_binding,
                            mac,
                            artifact_id,
                        ),
                    )
            except sqlite3.IntegrityError as exc:
                _raise_event_identity_immutable(exc, conn)
                raise
            if receipt_operation_id:
                self._write_receipt(
                    conn,
                    receipt_operation_id,
                    artifact_id,
                    "edit",
                    new_version,
                    {"trust_tier": new_trust_tier},
                )
            if receipt_writer is not None:
                receipt_writer(
                    conn,
                    {
                        "artifact_id": artifact_id,
                        "artifact_version": new_version,
                        "result_refs": [
                            {
                                "artifact_id": artifact_id,
                                "artifact_version": new_version,
                            }
                        ],
                        "result": {
                            "applied": True,
                            "id": artifact_id,
                            "revision": new_version,
                            "trust_tier": new_trust_tier,
                        },
                    },
                )
            run_commit_check(conn, commit_check)
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
        commit_check: CommitCheck | None = None,
        receipt_writer: ReceiptWriter | None = None,
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

        72-T06 D29: `receipt_writer` records the v2 receipt before commit.
        """
        _reject_reserved_receipt_ids(receipt_operation_id)
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
                content=_content_or_none(row["content"]),
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
            if receipt_writer is not None:
                receipt_writer(
                    conn,
                    {
                        "artifact_id": artifact_id,
                        "artifact_version": new_version,
                        "result_refs": [
                            {
                                "artifact_id": artifact_id,
                                "artifact_version": new_version,
                            }
                        ],
                        "result": {
                            "applied": True,
                            "id": artifact_id,
                            "revision": new_version,
                            "archived": archived,
                        },
                    },
                )
            run_commit_check(conn, commit_check)
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
        write_sources: Sequence[str],
        commit_check: CommitCheck | None = None,
    ) -> bool:
        """MC12 §6.7, 72-T08 D39: persists one vector only when, inside one
        `BEGIN IMMEDIATE`, the current row still has `artifact_version`, a source granted by
        `write_sources`, and embedding text whose sha256 is `content_hash` (the
        embedding-text hash, never the artifact `content_hash`/`payload_hash`). Returns
        whether the vector was inserted. `commit_check` runs immediately before commit."""
        from rush.memory.authorization import source_granted

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                "SELECT source, artifact_version, content FROM memory_artifacts "
                "WHERE id = ?",
                (artifact_id,),
            ).fetchone()
            if (
                cur is None
                or cur["artifact_version"] != artifact_version
                or not source_granted(cur["source"], write_sources)
            ):
                conn.rollback()
                return False
            text = _stored_text(cur["content"])
            current_hash: str | None = None
            if text is not None:
                try:
                    current_hash = hashlib.sha256(
                        embedding_text(json.loads(text)).encode("utf-8")
                    ).hexdigest()
                except (TypeError, ValueError, RecursionError):
                    current_hash = None
            if current_hash != content_hash:
                conn.rollback()
                return False
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
            run_commit_check(conn, commit_check)
            conn.commit()
        return True

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
        if _VERSION_COLUMN[0] not in existing:
            conn.execute(
                "ALTER TABLE memory_artifacts ADD COLUMN "
                f"{_VERSION_COLUMN[0]} {_VERSION_COLUMN[1]}"
            )

    def _migrate_archived_column(self, conn: sqlite3.Connection) -> None:
        """Additive migration (P65-07 §6.4): a pre-archive DB predates `archived_at`;
        add it, defaulting existing rows to NULL (never archived), mirroring
        `_migrate_expiry_columns`'s pattern."""
        existing = {
            row["name"] for row in conn.execute("PRAGMA table_info(memory_artifacts)")
        }
        if _ARCHIVED_COLUMN[0] not in existing:
            conn.execute(
                "ALTER TABLE memory_artifacts ADD COLUMN "
                f"{_ARCHIVED_COLUMN[0]} {_ARCHIVED_COLUMN[1]}"
            )

    def _migrate_changes_subject_column(self, conn: sqlite3.Connection) -> None:
        """Additive migration (P65-07.3): a pre-P65-07 DB's `memory_changes` predates the
        `subject` column `delete_batch()`'s tombstone rows use for provenance (mirrors
        `_migrate_expiry_columns`'s pattern) -- existing rows default to `NULL`."""
        existing = {
            row["name"] for row in conn.execute("PRAGMA table_info(memory_changes)")
        }
        if _CHANGES_SUBJECT_COLUMN[0] not in existing:
            conn.execute(
                "ALTER TABLE memory_changes ADD COLUMN "
                f"{_CHANGES_SUBJECT_COLUMN[0]} {_CHANGES_SUBJECT_COLUMN[1]}"
            )

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
        if _HANDOFF_REVOKED_COLUMN[0] not in session_columns:
            conn.execute(
                "ALTER TABLE memory_handoff_sessions ADD COLUMN "
                f"{_HANDOFF_REVOKED_COLUMN[0]} {_HANDOFF_REVOKED_COLUMN[1]}"
            )
        artifact_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(memory_artifacts)")
        }
        if _ORPHANED_COLUMN[0] not in artifact_columns:
            conn.execute(
                "ALTER TABLE memory_artifacts ADD COLUMN "
                f"{_ORPHANED_COLUMN[0]} {_ORPHANED_COLUMN[1]}"
            )

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
        for column, col_type in _OWNER_SCOPE_COLUMNS:
            if column not in existing:
                conn.execute(
                    f"ALTER TABLE memory_artifacts ADD COLUMN {column} {col_type}"
                )
        # Created here rather than in `_SCHEMA_SQL`: that script runs *before* this
        # migration, so on a pre-P69-07 database the columns don't exist yet.
        conn.execute(_OWNER_INDEX_SQL)

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
        for column, col_type in _EXPIRY_COLUMNS:
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
        version_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(memory_artifact_versions)")
        }
        # 72-T01: a store without the payload-hash columns predates the shared read
        # decision; reads never backfill it (plan §2.1 item 2). 72-T02 R2: the
        # ownership columns every read filters on are read-required too, so a store
        # lacking them is refused here instead of failing mid-read.
        if not (
            {
                "archived_at",
                "expired_at",
                *(name for name, _type in _OWNER_SCOPE_COLUMNS),
                *PAYLOAD_HASH_COLUMNS,
            }
            <= columns
            and set(PAYLOAD_HASH_COLUMNS) <= version_columns
        ):
            conn.close()
            return None, "migration_required"
        view = cls.__new__(cls)
        view.project_root = Path(project_root).resolve()
        view.db_path = view.project_root / ".rush" / "memory.db"
        view._owner_scope_default = legacy_owner_scope(view.project_root)
        view._readonly_conn = conn
        return view, None

    @contextmanager
    def fresh_reader(self) -> Iterator[sqlite3.Connection | None]:
        """72-T02 R13: a new connection, never this store's own read-only view, with
        one read transaction open, so a generation check and the selected-row re-reads
        before emission see the same committed state. A read-only view's opener that
        returns a `state` (or no connection) yields `None`: the caller refuses with
        `E_RESTART`. The connection is closed on exit (its read transaction ends)."""
        if self._readonly_conn is None:
            conn = self._connect()
        else:
            opened = open_sqlite_readonly(self.db_path)
            if opened.state is not None or opened.connection is None:
                yield None
                return
            conn = opened.connection
        try:
            conn.execute("BEGIN")
            yield conn
        finally:
            conn.close()

    def writable_open_ddl_free(self) -> bool:
        """72-T02 R2: True only when opening this store writable (`TypedArtifactStore(
        root)`) would run no DDL: the file is in WAL mode, every object `_SCHEMA_SQL`
        and `_POST_SCHEMA_SQL` declare exists, every column a migration adds
        (`_MIGRATION_COLUMNS`) exists, and the cursor-key row exists. A read route
        that gets False stays on its read-only view. A writable store has already run
        its constructor's migrations."""
        conn = self._readonly_conn
        if conn is None:
            return True
        try:
            with self.db_path.open("rb") as handle:
                header = handle.read(20)
        except OSError:
            return False
        # SQLite file header bytes 18/19 (read/write format version) are 2 in WAL
        # mode; `PRAGMA journal_mode` reports `delete` on an immutable connection.
        if len(header) < 20 or header[18] != 2 or header[19] != 2:
            return False
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
        required = set(_DDL_NAME_RE.findall(_SCHEMA_SQL))
        for statement in _POST_SCHEMA_SQL:
            required.update(_DDL_NAME_RE.findall(statement))
        if not required <= names:
            return False
        columns: dict[str, set[str]] = {}
        for table, column in _MIGRATION_COLUMNS:
            if table not in columns:
                columns[table] = {
                    row[1] for row in conn.execute(f"PRAGMA table_info({table})")
                }
            if column not in columns[table]:
                return False
        if not v2_schema_current(conn):  # 72-T06 D29: receipt columns, index, trigger
            return False
        return (
            conn.execute("SELECT 1 FROM memory_cursor_key WHERE id = 1").fetchone()
            is not None
        )

    def consent_inventory(self) -> list[dict[str, Any]]:
        """73-T02 H8: non-archived rows grouped by owner and source, in owner/source
        order, for the consent preview. Read-only; on a read-only view it runs over
        the view's connection."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT owner_scope_kind, owner_scope_id, source, COUNT(*) "
                "FROM memory_artifacts WHERE archived_at IS NULL "
                "GROUP BY 1, 2, 3 ORDER BY 1, 2, 3"
            ).fetchall()
        return [
            {
                "owner_scope_kind": kind,
                "owner_scope_id": owner_id,
                "source": source,
                "rows": int(count),
            }
            for kind, owner_id, source, count in rows
        ]

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
            raise readonly_preview_error(opened.state, root / ".rush" / "memory.db")
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
    def upgrade(
        cls,
        project_root: Path,
        *,
        cache_write: bool,
        access: MemoryAccess | None = None,
    ) -> int:
        """Explicit legacy-schema migration (MC01 §6.1): adds `artifact_version` if missing and
        backfills `memory_artifact_versions`/`memory_changes` history for every pre-existing
        row, all inside one transaction. Rolls back to the original schema/data on any failure
        (`_backfill_legacy_row` raising) with no partial rows. A no-op if history already exists.
        Uses a fresh, non-WAL connection (never `_init_db`/`_SCHEMA_SQL`) so a rollback restores
        the on-disk file exactly, including its pre-migration journal mode.

        72-T06 D29/D30: every `PRAGMA table_info` read runs inside the one
        `BEGIN IMMEDIATE`, which also adds the v2 receipt columns and index and the
        event trigger, backfills owners, refuses duplicate event identities
        (`MemoryMigrationRequiredError(reason="duplicate_event_identity")`, whose
        `refs` list only rows `access` may see) and then creates the event index.
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
            conn.execute("BEGIN IMMEDIATE")
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(memory_artifacts)")
            }
            if "artifact_version" not in columns:
                conn.execute(
                    "ALTER TABLE memory_artifacts ADD COLUMN artifact_version "
                    "INTEGER NOT NULL DEFAULT 1"
                )
            # 72-T01 (X2): payload-hash columns and their backfill, in this same
            # transaction, before any legacy history row is written (those copy it).
            _migrate_payload_hash_columns(conn)
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
            if "row_mac" not in columns:
                conn.execute("ALTER TABLE memory_artifacts ADD COLUMN row_mac TEXT")
            _migrate_applicability_columns(conn)
            conn.execute(_MUTATION_RECEIPTS_TABLE_SQL)
            _apply_v2_schema(conn)
            default_owner = legacy_owner_scope(root)
            ownerless = conn.execute(
                "SELECT id FROM memory_artifacts "
                "WHERE owner_scope_kind IS NULL OR owner_scope_id IS NULL"
            ).fetchall()
            for (artifact_id,) in ownerless:
                mac = next_row_mac(
                    conn,
                    root,
                    artifact_id,
                    {
                        "owner_scope_kind": default_owner.kind,
                        "owner_scope_id": default_owner.id,
                    },
                )
                conn.execute(
                    "UPDATE memory_artifacts SET owner_scope_kind = ?, "
                    "owner_scope_id = ?, row_mac = ? WHERE id = ?",
                    (default_owner.kind, default_owner.id, mac, artifact_id),
                )
            duplicates = _event_duplicate_rows(conn)
            if duplicates:
                raise MemoryMigrationRequiredError(
                    "memory.db repeats an event identity; resolve it with a "
                    "reviewed delete before upgrading",
                    reason="duplicate_event_identity",
                    refs=tuple(
                        {
                            "artifact_id": row["id"],
                            "artifact_version": row["artifact_version"],
                        }
                        for row in duplicates
                        if _upgrade_ref_visible(row, root, access)
                    ),
                )
            conn.execute(_EVENT_INDEX_SQL)
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
        """Writes one pre-existing row's history as version 1 (MC01 §6.1 legacy migration).
        72-T01: version 1 holds the row's exact bytes, so it carries the row's binding."""
        now = time.time()
        conn.execute(
            "INSERT INTO memory_artifact_versions "
            "(artifact_id, artifact_version, content, source, trust_tier, created_at, "
            "deleted, payload_hash, payload_hash_origin) VALUES (?,1,?,?,?,?,0,?,?)",
            (
                row["id"],
                row["content"],
                row["source"],
                row["trust_tier"],
                now,
                _row_value(row, "payload_hash"),
                _row_value(row, "payload_hash_origin"),
            ),
        )
        conn.execute(
            "INSERT INTO memory_changes (artifact_id, artifact_version, tombstone, created_at) "
            "VALUES (?,1,0,?)",
            (row["id"], now),
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
            content=_content_or_none(row["content"]),
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
        # 72-T01 D34: a write never evicts a STATED row (any owner, any source);
        # a conflicting write is inserted beside it and reads mark both `contested`.
        evicted = None
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
        transaction (BEGIN/commit). 72-T01: both rows carry the `write`-bound
        `payload_hash` of the exact persisted text."""
        now = time.time()
        text = json.dumps(stored.content)
        digest = payload_digest(text)
        owner = stored.owner_scope or self._owner_scope_default
        mac = insert_row_mac(
            conn,
            self.project_root,
            {
                "id": stored.id,
                "family": stored.family,
                "subject": stored.subject,
                "trust_tier": stored.trust_tier,
                "content": text,
                "source": stored.source,
                "symbol_ref": stored.symbol_ref,
                "content_hash": stored.content_hash,
                "owner_scope_kind": owner.kind,
                "owner_scope_id": owner.id,
                "origin_kind": stored.origin_kind,
                "origin_id": stored.origin_id,
                "applicability": stored.applicability,
                "task_project_id": stored.task_project_id,
                "task_worktree_id": stored.task_worktree_id,
                "task_id": stored.task_id,
            },
        )
        binding = (
            stored.applicability,
            stored.task_project_id,
            stored.task_worktree_id,
            stored.task_id,
        )
        conn.execute(
            _INSERT_SQL,
            (
                stored.id,
                stored.family,
                stored.subject,
                stored.trust_tier,
                text,
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
                owner.kind,
                owner.id,
                digest,
                "write",
                mac,
                *binding,
            ),
        )
        conn.execute(
            "INSERT INTO memory_artifact_versions "
            "(artifact_id, artifact_version, content, source, trust_tier, created_at, "
            "deleted, payload_hash, payload_hash_origin, applicability, "
            "task_project_id, task_worktree_id, task_id, binding_recorded) "
            "VALUES (?,?,?,?,?,?,0,?,?,?,?,?,?,1)",
            (
                stored.id,
                stored.artifact_version,
                text,
                stored.source,
                stored.trust_tier,
                now,
                digest,
                "write",
                *binding,
            ),
        )
        conn.execute(
            "INSERT INTO memory_changes (artifact_id, artifact_version, tombstone, created_at) "
            "VALUES (?,?,0,?)",
            (stored.id, stored.artifact_version, now),
        )

    def write(
        self,
        artifact: MemoryArtifact,
        *,
        receipt_operation_id: str | None = None,
        commit_check: CommitCheck | None = None,
        access: MemoryAccess | None = None,
        receipt_writer: ReceiptWriter | None = None,
    ) -> MemoryArtifact:
        """Persist an artifact. Enforces Invariant 1 (no-STATED-on-entry) and 2
        (redact-before-store). The conflict lookup/delete `_prepare_write()` may run,
        this insert, and the optional creation receipt all share one transaction
        (P69-01.2g) -- an insertion failure after a conflict-delete rolls the delete
        back too, rather than leaving the deleted artifact permanently gone.

        72-T06 D30: an event-bearing write (content with top-level `event_id`) is
        validated against `access` and replayed inside this transaction: the same
        identity with the same payload returns the original row (only when it is
        still visible under `access`), a changed payload is `event_digest_conflict`.
        D29: `receipt_writer` records the v2 receipt before commit."""
        _reject_reserved_receipt_ids(receipt_operation_id)
        event_bearing = _check_event_identity(artifact.content, access)
        replayed: sqlite3.Row | None = None
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            stored, evicted = self._prepare_write(conn, artifact)
            if event_bearing:
                replayed = self._event_replay_row(conn, stored)
            if replayed is not None:
                conn.rollback()
            else:
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
                if receipt_writer is not None:
                    ref = {"artifact_id": stored.id, "artifact_version": 1}
                    receipt_writer(
                        conn,
                        {
                            "artifact_id": stored.id,
                            "artifact_version": stored.artifact_version,
                            "result_refs": [ref],
                            "result": {"id": stored.id, "artifact_version": 1},
                        },
                    )
                run_commit_check(conn, commit_check)
                conn.commit()
        if replayed is not None:
            return self._visible_replay(replayed, access)
        self._note_inserted(stored, evicted)
        return stored

    def _event_replay_row(
        self, conn: sqlite3.Connection, stored: MemoryArtifact
    ) -> sqlite3.Row | None:
        """D30 replay inside the write transaction: the row already holding this
        identity for the same owner, or `None`. A missing index (an unbackfilled or
        duplicated store) is `upgrade_required`; a different version-1 payload is
        `event_digest_conflict`."""
        from rush.memory.authorization import MemoryPolicyError

        if not _event_index_present(conn):
            raise MemoryMigrationRequiredError(
                "memory.db needs `rush memory` upgrade before event writes",
                reason="upgrade_required",
            )
        owner = stored.owner_scope or self._owner_scope_default
        values = [str(stored.content[key]) for key in EVENT_IDENTITY_KEYS]
        clauses = " AND ".join(f"{expr} = ?" for expr in _EVENT_VALUE_SQL)
        row = conn.execute(
            f"SELECT * FROM memory_artifacts WHERE {clauses} "
            "AND COALESCE(owner_scope_kind, '') = ? "
            "AND COALESCE(owner_scope_id, '') = ?",
            (*values, owner.kind, owner.id),
        ).fetchone()
        if row is None:
            return None
        first = conn.execute(
            "SELECT payload_hash FROM memory_artifact_versions "
            "WHERE artifact_id = ? AND artifact_version = 1",
            (row["id"],),
        ).fetchone()
        if first is None or first["payload_hash"] != payload_digest(
            json.dumps(stored.content)
        ):
            raise MemoryPolicyError("E_VERSION", "event_digest_conflict")
        return row

    def _visible_replay(
        self, row: sqlite3.Row, access: MemoryAccess | None
    ) -> MemoryArtifact:
        """D30: a replayed original is returned only when it passes visibility."""
        if access is not None:
            from rush.memory.authorization import MemoryPolicyError
            from rush.memory.retrieval import evaluate_artifact_visibility

            if not evaluate_artifact_visibility(self, row, access=access).visible:
                raise MemoryPolicyError("E_NOT_VISIBLE", "not_visible")
        return _row_to_artifact(row, default_owner_scope=self._owner_scope_default)

    def write_pass(
        self,
        artifact: MemoryArtifact,
        *,
        namespace: str,
        behavior_id: str,
        runtime_digest: str,
        commit_check: CommitCheck | None = None,
        access: MemoryAccess | None = None,
    ) -> MemoryArtifact:
        """MC10 §9.0: insert one passing observation artifact and advance its
        namespace/behavior/runtime-platform-digest last-success pointer in the *same*
        transaction -- the only path that ever writes `memory_behavior_success` (no
        parallel write path; reuses `_insert_row()`, the same insert body `write()` uses).
        A cache hit, skip, tag, or caller label never reaches this method; only a
        genuinely executed pass does, via `rush.memory.experience.record_behavior_success`.

        72-T06 D30: event-bearing content follows `write()`'s identity rules.
        """
        now = time.time()
        event_bearing = _check_event_identity(artifact.content, access)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            stored, evicted = self._prepare_write(conn, artifact)
            replayed = self._event_replay_row(conn, stored) if event_bearing else None
            if replayed is not None:
                conn.rollback()
                return self._visible_replay(replayed, access)
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
            run_commit_check(conn, commit_check)
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
        sender: Mapping[str, Any] | None = None,
        commit_check: CommitCheck | None = None,
        sender_task_id: str | None = None,
    ) -> None:
        """MC11 §9.0: persist one bounded-handoff session descriptor. `granted_ids` is the
        exact, immutable authorized artifact-ID set for this session -- widening scope
        always requires a brand-new session (no update path exists). 72-T01 D21:
        `sender` holds the policy-mode sender binding (`sender_grant_id`, owner,
        project, worktree, policy revision); legacy sessions keep them NULL."""
        bound = dict(sender or {})
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO memory_handoff_sessions "
                "(session_id, root, audience, capability_hash, granted_ids, "
                "session_allowlist, constraints, created_at, expires_at, "
                "sender_grant_id, sender_owner_kind, sender_owner_id, "
                "sender_project_id, sender_worktree_id, sender_policy_revision, "
                "sender_task_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
                    *(bound.get(name) for name, _type in HANDOFF_SENDER_COLUMNS),
                    sender_task_id,
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
            run_commit_check(conn, commit_check)
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
            "revoked_at": _row_value(row, "revoked_at"),
            "sender_columns": all(
                name in row.keys()  # noqa: SIM118 -- sqlite3.Row
                for name, _type in HANDOFF_SENDER_COLUMNS
            ),
            **{name: _row_value(row, name) for name, _type in HANDOFF_SENDER_COLUMNS},
            # 72-T05: an older read-only schema without the column reads as no task.
            "sender_task_id": _row_value(row, "sender_task_id"),
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
        trusting their own call succeeded. 72-T06 D29: a `v2:` id is refused."""
        _reject_reserved_receipt_ids(receipt_id)
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
        self,
        session_id: str,
        readbacks: Sequence[tuple[str, int, str]],
        *,
        commit_check: CommitCheck | None = None,
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
            run_commit_check(conn, commit_check)
            conn.commit()
        return self.get_handoff_receipts(session_id)

    def update_content(
        self,
        artifact_id: str,
        content: dict[str, Any],
        *,
        expected_version: int | None = None,
        commit_check: CommitCheck | None = None,
    ) -> None:
        """Update an existing row's content (redacted), exercising the AFTER UPDATE FTS trigger.

        Routed through `_write_version` (MC01 §6.1): advances `artifact_version`, appends a
        `memory_artifact_versions`/`memory_changes` row, and raises `VersionConflictError` if
        `expected_version` is given and stale. A missing `artifact_id` is a silent no-op,
        matching this method's pre-MC01 behavior.

        72-T01: like `edit()`, a content change demotes a STATED row to DERIVED and
        clears `signature`/`promoted_at` in the same transaction, so changed bytes never
        keep promoted authority; the version row records the demoted tier.
        """
        sanitized_content = sanitize_value(content).value
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT source, trust_tier, content FROM memory_artifacts WHERE id = ?",
                (artifact_id,),
            ).fetchone()
            if row is None:
                return
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
            )
            new_text = _persisted_text(row["content"], sanitized_content)
            mac = next_row_mac(
                conn,
                self.project_root,
                artifact_id,
                {"content": new_text, "trust_tier": new_trust_tier},
            )
            try:
                conn.execute(
                    "UPDATE memory_artifacts SET content = ?, artifact_version = ?, "
                    "trust_tier = ?, signature = NULL, promoted_at = NULL, row_mac = ? "
                    "WHERE id = ?",
                    (new_text, new_version, new_trust_tier, mac, artifact_id),
                )
            except sqlite3.IntegrityError as exc:
                _raise_event_identity_immutable(exc, conn)
                raise
            run_commit_check(conn, commit_check)
            conn.commit()
            note_committed_write(artifact_id, new_version, row["source"], "update")

    def promote(
        self,
        artifact_id: str,
        *,
        user_stated: bool,
        candidate_sources: list[str] | None = None,
        candidate_refs: list[dict[str, Any]] | None = None,
        expected_version: int | None = None,
        owner_scope: OwnerScope | None = None,
        receipt_operation_id: str | None = None,
        access: MemoryAccess | None = None,
        commit_check: CommitCheck | None = None,
    ) -> tuple[MemoryArtifact, PromotionResult]:
        """Evaluate persisted bytes and atomically persist their signed promotion.

        Promotion is a distinct, separately-committed effect from the candidate
        artifact's own creation (P69-01.2f) -- a receipt is only written here when
        `decision.promoted` is actually True, so recovery can tell "candidate created"
        apart from "candidate created *and* promoted" via two independently-addressable
        receipts rather than one conflated id.

        S08 bullet 3: `owner_scope` is checked under the same compare-and-swap
        contract `edit()`/`archive()`/`delete_batch()` enforce (P69-07).

        72-T04 D8: corroboration is only ever counted from rows the code selects
        (`corroborating_peers`) under `access`; `candidate_sources` alone is refused
        (`E_INPUT candidate_refs_required`) and is ignored beside `candidate_refs`.
        `access=None` resolves the D1 mode: `policy` refuses (`policy_grant_required`),
        `unavailable` refuses with its reason, `legacy` grants every stored non-internal
        source to the declared (else legacy) owner. Always under the policy lock."""
        _reject_reserved_receipt_ids(receipt_operation_id)
        from rush.memory import retrieval
        from rush.memory.authorization import MemoryPolicyError, hold_policy_lock

        if candidate_sources is not None and candidate_refs is None:
            raise MemoryPolicyError("E_INPUT", "candidate_refs_required")
        lock = ExitStack()
        try:
            lock.enter_context(
                hold_policy_lock(
                    data_root=access.data_root if access is not None else None
                )
            )
        except OSError as exc:
            raise MemoryPolicyError("E_PERMISSION", "lock_unavailable") from exc
        with lock:
            if access is None:
                mode, reason = retrieval.memory_policy_decision(self.project_root)
                if mode == "unavailable":
                    raise MemoryPolicyError("E_PERMISSION", reason or "policy_invalid")
                if mode == "policy":
                    raise MemoryPolicyError("E_PERMISSION", "policy_grant_required")
            if not self.db_path.is_file():
                # A removed store holds no such row; never recreate it here.
                raise KeyError(artifact_id)
            if access is None:
                with self._connect() as conn:
                    stored = {
                        str(r[0])
                        for r in conn.execute(
                            "SELECT DISTINCT source FROM memory_artifacts"
                        )
                    }
                access = retrieval.MemoryAccess.legacy(
                    self.project_root,
                    sorted(stored - INTERNAL_MEMORY_SOURCES),
                    owner_scope=owner_scope or self._owner_scope_default,
                    operation="write",
                )
            resolved = access
            check: CommitCheck = commit_check or (
                lambda: retrieval.recheck_failure(resolved)
            )
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
                    store=self,
                    access=resolved,
                    user_stated=user_stated,
                    candidate_refs=candidate_refs,
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
                run_commit_check(conn, check)
        # The `with` block commits on exit; only a real promotion wrote a revision.
        if decision.promoted:
            note_committed_write(
                artifact.id, artifact.artifact_version, artifact.source, "promote"
            )
        return artifact, decision

    def apply_correction(
        self,
        *,
        access: MemoryAccess,
        kind: str,
        artifact_id: str,
        expected_version: int,
        target_content: dict[str, Any],
        replacement_content: dict[str, Any] | None = None,
        binding: VersionBinding,
        supersedes: Sequence[Any] | None = None,
        receipt_writer: Callable[[sqlite3.Connection, dict[str, Any]], None]
        | None = None,
        now: float | None = None,
    ) -> dict[str, Any]:
        """72-T05 correction core: `reject`, `correct` or `supersede` one current row
        inside one `BEGIN IMMEDIATE` under the policy lock.

        Every cited ref (the primary target plus `supersedes`, normalized with the
        primary once) is validated before the first write: visible in ordinary mode
        (`usable_as_current` is not required), owned by `access.owner_scope`, at its
        cited current version. `correct` appends the target version and promotes it
        to STATED; `reject` appends the `rejected` version; `supersede` inserts the
        replacement (v1, promoted to v2), writes one `supersedes` edge from
        replacement@1 to every cited version and appends the target's `superseded`
        version. A final access recheck precedes `receipt_writer` (called once with
        every written ref); any failure rolls back every effect. Returns `{"code":
        "OK", ...}` or `{"code", "reason"}`; exceptions roll back and propagate."""
        from rush.memory import relations
        from rush.memory.authorization import MemoryPolicyError, hold_policy_lock
        from rush.memory.retrieval import recheck_failure

        def refused(code: str, reason: str) -> dict[str, Any]:
            return {"code": code, "reason": reason}

        def version_ok(value: Any) -> bool:
            return type(value) is int and value >= 1 and sqlite_integer_in_range(value)

        if not isinstance(kind, str) or kind not in _CORRECTION_APPLICABILITY:
            return refused("E_INPUT", "kind_invalid")
        if not isinstance(artifact_id, str) or not artifact_id:
            return refused("E_INPUT", "artifact_id_invalid")
        if not version_ok(expected_version):
            return refused("E_INPUT", "expected_version_invalid")
        if not isinstance(target_content, dict) or (
            (kind == "supersede") != isinstance(replacement_content, dict)
        ):
            return refused("E_INPUT", "content_invalid")
        if not isinstance(binding, VersionBinding):
            return refused("E_INPUT", "binding_invalid")
        cited: list[tuple[str, int]] = [(artifact_id, expected_version)]
        explicit: set[tuple[str, int]] = set()
        if supersedes is not None and not isinstance(supersedes, (list, tuple)):
            return refused("E_INPUT", "supersedes_invalid")
        for ref in supersedes or ():
            if not isinstance(ref, Mapping) or set(ref) != {
                "artifact_id",
                "artifact_version",
            }:
                return refused("E_INPUT", "supersedes_invalid")
            ref_id, ref_version = ref["artifact_id"], ref["artifact_version"]
            if not isinstance(ref_id, str) or not ref_id or not version_ok(ref_version):
                return refused("E_INPUT", "supersedes_invalid")
            if (ref_id, ref_version) in explicit:
                return refused("E_INPUT", "supersedes_duplicate")
            explicit.add((ref_id, ref_version))
            if (ref_id, ref_version) not in cited:
                cited.append((ref_id, ref_version))
        if access.kind != "policy" or "write" not in access.required_operations:
            return refused("E_PERMISSION", "policy_grant_required")
        with ExitStack() as stack:
            try:
                stack.enter_context(hold_policy_lock(data_root=access.data_root))
            except (OSError, MemoryPolicyError):
                return refused("E_PERMISSION", "lock_unavailable")
            failure = recheck_failure(access)
            if failure is not None:
                return refused(*failure)
            if self.project_root != access.storage_root:
                return refused("E_NOT_VISIBLE", "not_visible")
            written: list[tuple[str, int, str, str]] = []
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    result = self._correction_effects(
                        conn,
                        relations.insert_relation_tx,
                        access=access,
                        kind=kind,
                        cited=cited,
                        target_content=target_content,
                        replacement_content=replacement_content,
                        binding=binding,
                        now=now,
                        written=written,
                    )
                    if result["code"] == "OK":
                        failure = recheck_failure(access)
                        if failure is not None:
                            result = refused(*failure)
                    if result["code"] != "OK":
                        conn.rollback()
                        return result
                    if receipt_writer is not None:
                        receipt_writer(
                            conn,
                            {
                                "artifact_id": artifact_id,
                                "artifact_version": result["artifact_version"],
                                "result_refs": [
                                    {"artifact_id": ref_id, "artifact_version": v}
                                    for ref_id, v, _source, _op in written
                                ],
                                "result": result,
                            },
                        )
                    conn.commit()
                except BaseException:
                    conn.rollback()
                    raise
        for ref_id, version, source, operation in written:
            note_committed_write(ref_id, version, source, operation)
        return result

    def _correction_effects(
        self,
        conn: sqlite3.Connection,
        insert_relation: Callable[..., dict[str, Any]],
        *,
        access: MemoryAccess,
        kind: str,
        cited: list[tuple[str, int]],
        target_content: dict[str, Any],
        replacement_content: dict[str, Any] | None,
        binding: VersionBinding,
        now: float | None,
        written: list[tuple[str, int, str, str]],
    ) -> dict[str, Any]:
        """`apply_correction`'s transaction body (caller owns BEGIN/commit)."""
        from rush.memory.retrieval import evaluate_artifact_visibility

        rows: dict[str, sqlite3.Row] = {}
        for ref_id, version in cited:
            row = conn.execute(
                "SELECT * FROM memory_artifacts WHERE id = ?", (ref_id,)
            ).fetchone()
            if (
                row is None
                or not evaluate_artifact_visibility(
                    self, row, access=access, mode="ordinary", now=now
                ).visible
                or owner_scope_for_row(row, self.project_root) != access.owner_scope
            ):
                return {"code": "E_NOT_VISIBLE", "reason": "not_visible"}
            if row["artifact_version"] != version:
                return {"code": "E_VERSION", "reason": "version_changed"}
            rows[ref_id] = row
        artifact_id, expected_version = cited[0]
        row = rows[artifact_id]
        tier = "DERIVED" if row["trust_tier"] == "STATED" else row["trust_tier"]
        applicability = _CORRECTION_APPLICABILITY[kind]
        target_binding = dataclasses.replace(binding, applicability=applicability)

        def promote(target_id: str, version: int) -> dict[str, Any] | None:
            _artifact, decision = promote_stored_artifact(
                conn,
                target_id,
                store=self,
                access=access,
                user_stated=True,
                expected_version=version,
            )
            if not decision.promoted:
                return {
                    "code": "E_INPUT",
                    "reason": str(decision.denial_reason or "promotion_denied"),
                }
            written.append((target_id, version + 1, row["source"], "update"))
            return None

        replacement: dict[str, Any] | None = None
        edge: dict[str, Any] | None = None
        if kind == "supersede":
            assert replacement_content is not None
            new_id = str(uuid.uuid4())
            stored, _evicted = self._prepare_write(
                conn,
                MemoryArtifact(
                    id=new_id,
                    family=row["family"],
                    subject=row["subject"],
                    trust_tier="DERIVED",
                    content=replacement_content,
                    source=row["source"],
                    created_at=now if now is not None else time.time(),
                    owner_scope=access.owner_scope,
                    applicability="active",
                    task_project_id=binding.task_project_id,
                    task_worktree_id=binding.task_worktree_id,
                    task_id=binding.task_id,
                ),
            )
            self._insert_row(conn, stored)
            written.append((new_id, 1, row["source"], "write"))
            denied = promote(new_id, 1)
            if denied is not None:
                return denied
            replacement = {"artifact_id": new_id, "artifact_version": 2}
            for ref_id, version in cited:
                out = insert_relation(
                    conn,
                    source_id=new_id,
                    source_version=1,
                    target_id=ref_id,
                    target_version=version,
                    kind="supersedes",
                    origin_ref="correction",
                )
                if out.get("code") != "OK":
                    return {
                        "code": str(out.get("code")),
                        "reason": str(out.get("reason") or "edge_refused"),
                    }
            edge = {
                "source_id": new_id,
                "source_version": 1,
                "target_id": artifact_id,
                "target_version": expected_version,
            }
        new_version = _write_version(
            conn,
            artifact_id,
            content=target_content,
            source=row["source"],
            trust_tier=tier,
            expected_version=expected_version,
            binding=target_binding,
        )
        text = _persisted_text(row["content"], target_content)
        task_columns = (
            target_binding.task_project_id,
            target_binding.task_worktree_id,
            target_binding.task_id,
        )
        mac = next_row_mac(
            conn,
            self.project_root,
            artifact_id,
            {
                "content": text,
                "trust_tier": tier,
                "applicability": applicability,
                "task_project_id": task_columns[0],
                "task_worktree_id": task_columns[1],
                "task_id": task_columns[2],
            },
        )
        conn.execute(
            "UPDATE memory_artifacts SET content = ?, trust_tier = ?, signature = NULL, "
            "promoted_at = NULL, corroboration_count = 0, applicability = ?, "
            "task_project_id = ?, task_worktree_id = ?, task_id = ?, "
            "artifact_version = ?, row_mac = ? WHERE id = ?",
            (text, tier, applicability, *task_columns, new_version, mac, artifact_id),
        )
        written.append((artifact_id, new_version, row["source"], "update"))
        current = new_version
        if kind == "correct":
            denied = promote(artifact_id, new_version)
            if denied is not None:
                return denied
            current = new_version + 1
        return {
            "code": "OK",
            "artifact_id": artifact_id,
            "artifact_version": current,
            "replacement": replacement,
            "edge": edge,
        }

    def version_history_readonly(
        self,
        artifact_id: str,
        *,
        access: MemoryAccess,
        archive_mode: Literal["active", "historical"] = "active",
        representation: Literal["utf8", "base64"] = "utf8",
    ) -> list[dict[str, Any]]:
        """D31 per-version history on an `open_readonly_view()` store only.

        An absent or reviewed-deleted row, a row `access` cannot see, or (in
        `active` mode) an archived or expired row is the one `E_NOT_VISIBLE`. A
        version is listed only when its own immutable `source` is granted; hidden
        versions are neither listed nor counted. Non-latest versions are never
        usable as current, their freshness is `unknown` and their store binding
        `unbound`; a version without a recorded context (`binding_recorded` NULL)
        reports `version_context_unbound` and never inherits the current row's."""
        if self._readonly_conn is None:
            raise TypeError(
                "version_history_readonly() runs only on an open_readonly_view() store"
            )
        from rush.memory.authorization import MemoryPolicyError, source_granted
        from rush.memory.retrieval import (
            _access_allows,
            _integrity,
            _lifecycle_reasons,
            _reference,
            evaluate_artifact_visibility,
        )

        conn = self._readonly_conn
        current = conn.execute(
            "SELECT * FROM memory_artifacts WHERE id = ?", (artifact_id,)
        ).fetchone()
        if current is None:
            raise MemoryPolicyError("E_NOT_VISIBLE", "not_visible")
        historical = archive_mode == "historical" and access.historical_allowed
        mode: Literal["historical", "inspect"] = (
            "historical" if historical else "inspect"
        )
        now = time.time()
        lifecycle = _lifecycle_reasons(current, now)
        verifier = binding_verifier(self)
        # The current row is the latest version as readers receive it: in active mode
        # an integrity-failed current row is not visible, and its latest version
        # entry reports the current row's payload mismatch.
        current_integrity, current_label = _integrity(current, verifier)
        if not _access_allows(self, current, access, mode) or (
            archive_mode != "historical" and (lifecycle or current_integrity)
        ):
            raise MemoryPolicyError("E_NOT_VISIBLE", "not_visible")
        ordinary = evaluate_artifact_visibility(
            self, current, access=access, mode="ordinary", now=now, verifier=verifier
        )
        decided = evaluate_artifact_visibility(
            self, current, access=access, mode=mode, now=now, verifier=verifier
        )
        versions = conn.execute(
            "SELECT * FROM memory_artifact_versions WHERE artifact_id = ? "
            "AND deleted = 0 ORDER BY artifact_version ASC",
            (artifact_id,),
        ).fetchall()
        history: list[dict[str, Any]] = []
        for version in versions:
            if not source_granted(version["source"], access.sources):
                continue
            stored = version["content"]
            raw = stored.encode("utf-8") if isinstance(stored, str) else stored
            try:
                text_value = raw.decode("utf-8") if isinstance(raw, bytes) else None
            except UnicodeDecodeError:
                text_value = None
            if representation == "utf8" and raw is not None and text_value is None:
                raise MemoryPolicyError("E_INPUT", "representation_unavailable")
            latest = version["artifact_version"] == current["artifact_version"]
            digest = _row_value(version, "payload_hash")
            if latest and current_label == "mismatch":
                integrity = "mismatch"
            elif digest is None:
                integrity = "unbound"
            elif isinstance(raw, bytes) and hashlib.sha256(raw).hexdigest() == digest:
                integrity = "verified"
            else:
                integrity = "mismatch"
            freshness = ordinary.freshness if latest and ordinary.visible else "unknown"
            reference = _reference(self, current, access, freshness, integrity)
            reference.update(
                artifact_version=version["artifact_version"],
                source=version["source"],
                trust_tier=version["trust_tier"],
                payload_hash=digest,
            )
            reasons = list(decided.reason_codes) if latest else []
            recorded = _row_value(version, "binding_recorded") is not None
            if not recorded:
                reasons.append("version_context_unbound")
            entry: dict[str, Any] = {
                "reference": reference,
                "integrity": integrity,
                "store_binding": verifier.version_bytes(
                    current, version["artifact_version"], stored
                ),
                "usable_as_current": latest and ordinary.usable_as_current,
                "freshness": freshness,
                "applicability": _row_value(version, "applicability")
                if recorded
                else None,
                "task_binding": [
                    _row_value(version, "task_project_id"),
                    _row_value(version, "task_worktree_id"),
                    _row_value(version, "task_id"),
                ]
                if recorded
                else None,
                "reason_codes": sorted(set(reasons)),
                "lifecycle": {
                    "archived": "archived" in lifecycle,
                    "expired": "expired" in lifecycle,
                },
                "created_at": version["created_at"],
            }
            if representation == "base64":
                entry["content_base64"] = (
                    base64.b64encode(raw).decode("ascii")
                    if isinstance(raw, bytes)
                    else None
                )
            else:
                entry["content_utf8"] = text_value
            history.append(entry)
        return history

    def _write_and_promote_tx(
        self,
        artifact_id: str,
        *,
        expected_version: int,
        user_stated: bool,
        candidate_refs: Sequence[Mapping[str, Any]] | None,
        access: MemoryAccess,
        receipt_writer: ReceiptWriter | None = None,
        commit_check: CommitCheck | None = None,
    ) -> dict[str, Any]:
        """D29 v2 promotion in one `BEGIN IMMEDIATE`: a new candidate@1 copied from
        the reviewed row, its promotion decision through the shared
        `promote_stored_artifact` (72-T04 signature), one receipt carrying both
        refs, then commit. The reviewed row is never written; any failure rolls
        back the candidate, the decision and the receipt together."""
        from rush.memory.authorization import MemoryPolicyError
        from rush.memory.retrieval import evaluate_artifact_visibility

        owner = access.owner_scope or self._owner_scope_default
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM memory_artifacts WHERE id = ?", (artifact_id,)
            ).fetchone()
            if (
                row is None
                or not evaluate_artifact_visibility(self, row, access=access).visible
            ):
                raise MemoryPolicyError("E_NOT_VISIBLE", "not_visible")
            if row["artifact_version"] != expected_version:
                raise VersionConflictError(
                    f"artifact {artifact_id!r} expected version {expected_version}, "
                    f"found {row['artifact_version']}"
                )
            if row["trust_tier"] == "STATED":
                raise MemoryPolicyError("E_INPUT", "already_stated")
            self._require_owner(row, artifact_id, owner)
            reviewed = _row_to_artifact(
                row, default_owner_scope=self._owner_scope_default
            )
            candidate = dataclasses.replace(
                reviewed,
                id=str(uuid.uuid4()),
                created_at=time.time(),
                owner_scope=owner,
                origin_kind=None,
                origin_id=None,
                corroboration_count=0,
                promoted_at=None,
                stale=False,
                signature=None,
                expired=False,
                archived_at=None,
                freshness=None,
            )
            stored, evicted = self._prepare_write(conn, candidate)
            self._insert_row(conn, stored)
            # 72-T04 owns this shared transaction signature (decisions.md 72-T04).
            promoted, decision = cast("Any", promote_stored_artifact)(
                conn,
                stored.id,
                store=self,
                access=access,
                user_stated=user_stated,
                candidate_refs=candidate_refs,
                expected_version=1,
            )
            decision_version = promoted.artifact_version
            candidate_ref = {"artifact_id": stored.id, "artifact_version": 1}
            result = {
                "candidate_ref": candidate_ref,
                "decision_ref": {
                    "artifact_id": stored.id,
                    "artifact_version": decision_version,
                    "promoted": decision.promoted,
                },
                "trust_tier": promoted.trust_tier,
                "denial_reason": decision.denial_reason,
            }
            refs = [candidate_ref]
            if decision_version != 1:
                refs.append(
                    {"artifact_id": stored.id, "artifact_version": decision_version}
                )
            if receipt_writer is not None:
                receipt_writer(
                    conn,
                    {
                        "artifact_id": stored.id,
                        "artifact_version": decision_version,
                        "result_refs": refs,
                        "result": result,
                    },
                )
            run_commit_check(conn, commit_check)
            conn.commit()
        self._note_inserted(stored, evicted)
        if decision.promoted:
            note_committed_write(stored.id, decision_version, stored.source, "promote")
        return result

    @classmethod
    def preview_import_records(
        cls,
        *,
        records: Sequence[Mapping[str, Any]],
        capsule_digest: str,
        confirm_constraint_ids: tuple[str, ...],
        mapping_id: str | None,
        access: MemoryAccess,
    ) -> dict[str, Any]:
        """D18 read-only preview of an import into `access.storage_root`: validates
        every record, reads the store through `open_readonly_view` (an absent store
        is allowed) and returns exactly `{preview_binding, store_state,
        store_revision, expected_versions, records, redactions}`. No filesystem
        effect; a corrupt or busy store raises `MemoryStoreUnreadableError`."""
        validated = _validate_import_records(records)
        if not _is_hex64(capsule_digest):
            raise _policy_error("E_INPUT", "capsule_digest_invalid")
        if mapping_id is not None and not isinstance(mapping_id, str):
            raise _policy_error("E_INPUT", "mapping_id_invalid")
        prepared, redactions = _prepare_import_records(
            validated, confirm_constraint_ids
        )
        root = _import_storage_root(access)
        view, store_state = _import_view(cls, root)
        try:
            revision = store_generation(view._connect()) if view is not None else 0
            existing = _import_existing_versions(view, prepared, access)
        finally:
            if view is not None:
                view.close()
        binding = _import_binding(
            prepared=prepared,
            capsule_digest=capsule_digest,
            confirm_constraint_ids=confirm_constraint_ids,
            mapping_id=mapping_id,
            access=access,
            root=root,
            store_state=store_state,
            store_revision=revision,
            existing=existing,
            redactions=redactions,
        )
        return {
            "preview_binding": binding,
            "store_state": store_state,
            "store_revision": revision,
            "expected_versions": dict(existing),
            "records": prepared,
            "redactions": redactions,
        }

    @classmethod
    def apply_import_records(
        cls,
        *,
        records: Sequence[Mapping[str, Any]],
        preview_binding: Mapping[str, Any],
        expected_store_revision: int,
        expected_versions: Mapping[str, int],
        confirm_foreign_ids: tuple[str, ...],
        confirm_constraint_ids: tuple[str, ...],
        invocation_id: str,
        effect_id: str,
        request_digest: str,
        access: MemoryAccess,
    ) -> dict[str, Any]:
        """D18 import apply into `access.storage_root`, in the order access
        recheck -> receipt replay -> binding (`E_INPUT`) -> revisions (`E_VERSION`)
        -> effects. A replay checks the receipt binding and result-ref visibility
        before comparing the caller's `request_digest`, and returns the committed
        mappings before any revision check. Every imported row is a new local id,
        `IMPORTED`, source `capsule:import`, `imported_unverified`; any failure
        rolls back every row, version and the receipt. An absent store is built in
        memory and published atomically (`_create_with_import`)."""
        from rush.dashboard.state import cross_process_project_lock
        from rush.memory.authorization import (
            MemoryPolicyError,
            hold_policy_lock,
            source_granted,
        )
        from rush.memory.retrieval import recheck_failure

        validated = _validate_import_records(records)
        _require_request_digest(request_digest)
        if not (_nonempty_str(invocation_id) and _nonempty_str(effect_id)):
            raise MemoryPolicyError("E_INPUT", "receipt_ids_required")
        if not isinstance(preview_binding, Mapping):
            raise MemoryPolicyError("E_INPUT", "preview_binding_invalid")
        if (
            not isinstance(expected_store_revision, int)
            or isinstance(expected_store_revision, bool)
            or not isinstance(expected_versions, Mapping)
        ):
            raise MemoryPolicyError("E_INPUT", "expected_revisions_invalid")
        prepared, redactions = _prepare_import_records(
            validated, confirm_constraint_ids
        )
        root = _import_storage_root(access)

        def recheck() -> tuple[str, str] | None:
            return recheck_failure(access)

        with _release_never_masks(hold_policy_lock(data_root=access.data_root)):
            failure = recheck()
            if failure is not None:
                raise MemoryPolicyError(*failure)
            # The target lock flocks the destination root directory itself, so
            # taking it leaves no lock file behind (a refused apply has no effect).
            target = _IMPORT_LOCK_PREFIX + str(root / ".rush" / "memory.db")
            with _release_never_masks(
                cross_process_project_lock(target, data_root=root, storage="directory")
            ):
                _remove_import_orphans(root)
                view, store_state = _import_view(cls, root)
                if store_state == "migration_required":
                    raise MemoryMigrationRequiredError(
                        readonly_view_reason("migration_required"),
                        reason="upgrade_required",
                    )
                try:
                    replay = _import_view_replay(
                        cls, view, invocation_id, effect_id, access, request_digest
                    )
                    if replay is not None:
                        return replay
                    _check_import_binding(
                        preview_binding,
                        validated,
                        confirm_foreign_ids,
                        confirm_constraint_ids,
                        access,
                        root,
                    )
                    granted = _grant_wide_access(access)
                    if not source_granted(IMPORT_SOURCE, granted.sources):
                        raise MemoryPolicyError("E_SCOPE", "source_not_granted")
                    revision = (
                        store_generation(view._connect()) if view is not None else 0
                    )
                    existing = _import_existing_versions(view, prepared, access)
                finally:
                    if view is not None:
                        view.close()
                _check_import_revisions(
                    preview_binding,
                    store_state=store_state,
                    store_revision=revision,
                    existing=existing,
                    expected_store_revision=expected_store_revision,
                    expected_versions=expected_versions,
                    access=access,
                    redactions=redactions,
                )
                owner = _import_owner(access, root)
                capsule_digest = str(preview_binding["capsule_digest"])
                artifacts = _import_artifacts(prepared, capsule_digest, owner)
                result = {
                    "capsule_digest": capsule_digest,
                    "mappings": [
                        {
                            "foreign_origin_id": record["foreign_origin_id"],
                            "artifact_id": artifact.id,
                            "artifact_version": 1,
                            "applicability": record["applicability"],
                        }
                        for record, artifact in zip(prepared, artifacts, strict=True)
                    ],
                }
                receipt = {
                    "invocation_id": invocation_id,
                    "effect_id": effect_id,
                    "request_digest": request_digest,
                    "artifact_id": None,
                    "kind": "import",
                    "revision": None,
                    "payload": {
                        "binding": {
                            "project_id": access.project_id,
                            "worktree_id": access.worktree_id,
                            "owner_scope": owner.as_dict(),
                            "sources": [IMPORT_SOURCE],
                        },
                        "result_refs": [
                            {"artifact_id": artifact.id, "artifact_version": 1}
                            for artifact in artifacts
                        ],
                        "result": result,
                    },
                }
                if store_state == "absent":
                    cls._create_with_import(
                        root, artifacts, receipt=receipt, commit_check=recheck
                    )
                elif not cls(root)._import_into(
                    artifacts,
                    receipt=receipt,
                    expected_store_revision=expected_store_revision,
                    commit_check=recheck,
                ):
                    # A concurrent apply committed this effect after the view read.
                    view, _state = _import_view(cls, root)
                    try:
                        raced = _import_view_replay(
                            cls, view, invocation_id, effect_id, access, request_digest
                        )
                    finally:
                        if view is not None:
                            view.close()
                    if raced is None:
                        raise MemoryPolicyError("E_VERSION", "store_changed")
                    return raced
        for artifact in artifacts:
            note_committed_write(artifact.id, 1, artifact.source, "write")
        return result

    def _import_into(
        self,
        artifacts: Sequence[MemoryArtifact],
        *,
        receipt: dict[str, Any],
        expected_store_revision: int,
        commit_check: CommitCheck,
    ) -> bool:
        """D18 effects into an existing store: one transaction for every row and
        the receipt. `False` when the receipt already exists (a racing apply)."""
        from rush.memory.authorization import MemoryPolicyError

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if (
                self._find_v2_receipt(
                    conn, receipt["invocation_id"], receipt["effect_id"]
                )
                is not None
            ):
                conn.rollback()
                return False
            if store_generation(conn) != expected_store_revision:
                conn.rollback()
                raise MemoryPolicyError("E_VERSION", "store_changed")
            for artifact in artifacts:
                self._insert_row(conn, artifact)
            self._write_v2_receipt(conn, **receipt)
            run_commit_check(conn, commit_check)
            conn.commit()
        return True

    @classmethod
    def find_import_effect_readonly(
        cls,
        *,
        invocation_id: str,
        effect_id: str,
        request_digest: str,
        access: MemoryAccess,
    ) -> dict[str, Any]:
        """D18 read-only replay lookup: `{"state": "absent"}`, `{"state":
        "unavailable", "store_state": "absent" | "migration_required"}` or
        `{"state": "present", "result": ...}` after the D29 binding, result-ref and
        digest checks. Creates and changes nothing."""
        _require_request_digest(request_digest)
        root = _import_storage_root(access)
        view, store_state = _import_view(cls, root)
        if view is None:
            return {"state": "unavailable", "store_state": store_state}
        try:
            if not v2_receipts_ready(view._connect()):
                return {"state": "unavailable", "store_state": "migration_required"}
            result = _import_view_replay(
                cls, view, invocation_id, effect_id, access, request_digest
            )
        finally:
            view.close()
        if result is None:
            return {"state": "absent"}
        return {"state": "present", "result": result}

    @classmethod
    def _create_with_import(
        cls,
        root: Path,
        artifacts: Sequence[MemoryArtifact],
        *,
        receipt: dict[str, Any],
        commit_check: CommitCheck,
    ) -> None:
        """D18 absent-store import: the whole store is built and committed on an
        in-memory connection (no SQLite file is opened by path), bound (D41) to
        the publication temp's inode, serialized into that temp and published by
        hard link with contained-path and identity checks."""
        store = cls.__new__(cls)
        store.project_root = Path(root).resolve()
        store.db_path = store.project_root / ".rush" / "memory.db"
        store._owner_scope_default = legacy_owner_scope(store.project_root)
        store._defer_binding = True
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        store._readonly_conn = conn
        try:
            store._init_db()
            conn.execute("BEGIN IMMEDIATE")
            for artifact in artifacts:
                store._insert_row(conn, artifact)
            store._write_v2_receipt(conn, **receipt)
            run_commit_check(conn, commit_check)
            conn.commit()
            bound = read_store_key() is not None
            if os.name == "nt":
                _publish_import_windows(conn, store.project_root)
            else:
                _publish_import_posix(conn, store.project_root)
        finally:
            store._readonly_conn = None
            conn.close()
        if not bound:
            # No local key existed before publication (creating one links a file):
            # bind the published store now, as the constructor binds a new store.
            key = ensure_store_key()
            if key is not None:
                with closing(sqlite3.connect(str(store.db_path), timeout=10.0)) as db:
                    db.row_factory = sqlite3.Row
                    _bind_import_store(
                        db, store.project_root, os.stat(store.db_path).st_ino, key
                    )

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
        return [
            _row_to_artifact(row, default_owner_scope=self._owner_scope_default)
            for row in self.search_rows(
                subject, query, include_archived=include_archived
            )
        ]

    def search_rows(
        self,
        subject: MemorySubject,
        query: str,
        *,
        include_archived: bool = False,
    ) -> list[sqlite3.Row]:
        """`search()`'s FTS5 match as raw rows, for callers that run the 72-T01 shared
        decision (`retrieval.evaluate_artifact_visibility`) on each one."""
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
            return list(cur.fetchall())

    def recall(
        self,
        subject: MemorySubject,
        query: str,
        session_allowlist: Iterable[str] | None = None,
        *,
        include_archived: bool = False,
        access: MemoryAccess | None = None,
        mode: Literal["ordinary", "inspect", "historical"] = "inspect",
    ) -> list[MemoryArtifact]:
        """FTS5 match (identical to search()) through the 72-T01 shared decision
        (`retrieval.evaluate_artifact_visibility`).

        `session_allowlist` is the legacy access form: rows whose `source` is in it, with no
        owner filter; an empty or absent allowlist with no `access` fails closed (zero
        rows, never all rows -- `src/rush/release/provenance_policy.py`'s precedent).
        `access` is a resolved `retrieval.MemoryAccess`; passing both raises `ValueError`.

        `mode="inspect"` (the default) returns every visible row with its decision
        `freshness` (and `stale=True` only for `stale`); `"ordinary"` returns only rows
        usable as current; `include_archived=True` selects `"historical"`. Archived,
        expired and integrity-failed rows are never returned outside historical mode.

        Legacy access keeps the documented raise, applied after the source/owner filter:
        `SignatureMismatchError` for a STATED row whose signature is missing or wrong,
        `TrojanSourceFoundError` for Trojan Source characters (§9 P61.9, Invariants 3/4).
        """
        from rush.memory.retrieval import (
            MemoryAccess,
            memory_policy_mode,
            visible_artifacts,
        )

        if access is not None and session_allowlist is not None:
            raise ValueError("pass access or session_allowlist, not both")
        if include_archived:
            mode = "historical"
        if access is None:
            if not session_allowlist:
                return []
            # D1: the allowlist form is legacy only in `legacy` mode; in `policy`
            # mode it narrows the resolved grant; `unavailable` reads nothing.
            policy_mode = memory_policy_mode(self.project_root)
            if policy_mode == "unavailable":
                return []
            if policy_mode == "legacy":
                access = MemoryAccess.legacy(self.project_root, session_allowlist)
            else:
                resolved = MemoryAccess.resolve(
                    self.project_root,
                    operation="recall",
                    historical=mode == "historical",
                    requested_sources=list(session_allowlist),
                )
                if resolved is None:
                    return []
                access = resolved
        rows = self.search_rows(
            subject, query, include_archived=include_archived or mode == "historical"
        )
        found = visible_artifacts(
            self, rows, access=access, mode=mode, legacy_raise=True
        )
        # 72-T01 F2: recheck the policy immediately before emit; a moved policy emits
        # nothing (fail closed).
        return found if access.recheck() == "ok" else []


_SUMMARY_KIND = "consolidated_episode_summary"


def _decoded_canon(stored: Any) -> tuple[Any, str]:
    """D8 canonical stored content: `json.dumps(sanitize_value(content).value,
    sort_keys=True)`, with the decoded value."""
    decoded = decode_content(stored)
    return decoded, json.dumps(sanitize_value(decoded).value, sort_keys=True)


def _is_summary(decoded: Any) -> bool:
    return isinstance(decoded, dict) and decoded.get("kind") == _SUMMARY_KIND


def _conn_verifier(conn: sqlite3.Connection, root: Path) -> BindingVerifier:
    found = _verified_binding(conn, root)
    return BindingVerifier("bound", found[0], found[1]) if found else UNBOUND_VERIFIER


def _binding_ok(verifier: BindingVerifier, row: sqlite3.Row) -> bool:
    """D41: in a bound store only a bound row is evidence; an unbound store has no
    row bindings to check."""
    return verifier.store != "bound" or verifier.row(row) == "bound"


def corroborating_peers(
    conn: sqlite3.Connection,
    store: TypedArtifactStore,
    candidate_row: sqlite3.Row,
    *,
    access: MemoryAccess,
    evidence_identity: bool,
    now: float | None = None,
) -> tuple[list[MemoryArtifact], bool]:
    """72-T04 D8: the agreeing peers that may count toward `candidate_row`'s
    corroboration, and whether an eligible different-content anchored peer
    contradicts it. Read on the caller's connection (its transaction).

    A peer is eligible when it is current (not archived, expired or past
    `expires_at`), not STATED/IMPORTED/internal/summary, in another source the
    access grants (D40), of the access owner, bound when the store is bound,
    payload-intact, decodable, and visible and usable as current. Agreement is equal
    canonical content; each source and (with `evidence_identity`) each complete
    non-null origin counts once, and a candidate or peer without a complete origin
    never counts. Contradiction ignores evidence identity; an unanchored candidate is
    never contradicted."""
    from rush.memory.retrieval import evaluate_artifact_visibility

    now = time.time() if now is None else now
    symbol_ref = candidate_row["symbol_ref"]
    candidate_origin = (
        _row_value(candidate_row, "origin_kind"),
        _row_value(candidate_row, "origin_id"),
    )
    origin_complete = None not in candidate_origin
    if evidence_identity and not origin_complete and symbol_ref is None:
        return [], False
    legacy = legacy_owner_scope(store.project_root)
    owner = access.owner_scope or legacy
    internal, internal_params = internal_source_exclusion_sql()
    granted, granted_params = source_predicate_sql("source", access.sources)
    rows = conn.execute(
        "SELECT * FROM memory_artifacts WHERE id != ? AND subject = ? "
        "AND symbol_ref IS ? AND trust_tier NOT IN ('STATED', 'IMPORTED') "
        "AND COALESCE(owner_scope_kind, ?) = ? AND COALESCE(owner_scope_id, ?) = ? "
        "AND archived_at IS NULL AND expired_at IS NULL "
        "AND (expires_at IS NULL OR expires_at > ?) AND source != ? "
        f"AND {internal} AND {granted} ORDER BY created_at, id",
        (
            candidate_row["id"],
            candidate_row["subject"],
            symbol_ref,
            legacy.kind,
            owner.kind,
            legacy.id,
            owner.id,
            now,
            candidate_row["source"],
            *internal_params,
            *granted_params,
        ),
    ).fetchall()
    _decoded, candidate_canon = _decoded_canon(candidate_row["content"])
    verifier = _conn_verifier(conn, store.project_root)
    peers: list[MemoryArtifact] = []
    contradicted = False
    seen_sources: set[str] = set()
    seen_origins = {candidate_origin}
    for peer in rows:
        if not _binding_ok(verifier, peer) or payload_mismatched(
            peer["content"], _row_value(peer, "payload_hash")
        ):
            continue
        try:
            decoded, canon = _decoded_canon(peer["content"])
        except (ValueError, TypeError, RecursionError):
            continue
        if _is_summary(decoded):
            continue
        decision = evaluate_artifact_visibility(
            store, peer, access=access, now=now, verifier=verifier
        )
        if not (decision.visible and decision.usable_as_current):
            continue
        if canon != candidate_canon:
            contradicted = contradicted or symbol_ref is not None
            continue
        origin = (_row_value(peer, "origin_kind"), _row_value(peer, "origin_id"))
        if evidence_identity and (
            not origin_complete or None in origin or origin in seen_origins
        ):
            continue
        if peer["source"] in seen_sources:
            continue
        seen_sources.add(peer["source"])
        seen_origins.add(origin)
        peers.append(_row_to_artifact(peer, default_owner_scope=legacy))
    return peers, contradicted


def promote_stored_artifact(
    conn: sqlite3.Connection,
    artifact_id: str,
    *,
    store: TypedArtifactStore,
    access: MemoryAccess,
    user_stated: bool,
    candidate_refs: list[dict[str, Any]] | None = None,
    expected_version: int | None = None,
) -> tuple[MemoryArtifact, PromotionResult]:
    """Shared gate/update; caller owns transaction and commit (72-T04 D8).

    Order: write gate (`E_PERMISSION policy_grant_required`), target visibility by
    root/source/owner (`E_NOT_VISIBLE`), payload binding, full visibility, IMPORTED
    without user confirmation (`imported_unverified`, no peer scan), then the
    user-stated path or the code-selected peer scan (`corroborating_peers`).
    `candidate_refs` only narrow which agreeing peers count: a hidden or absent ref is
    `E_NOT_VISIBLE`, a visible ref that is not a returned agreeing peer at its named
    version and source is `E_VERSION`, and refs never hide a contrary peer.

    Routed through `_write_version` (MC01 §6.1) only when an actual promotion happens: a
    promotion is a real semantic change (trust-tier upgrade), so it always advances
    `artifact_version`, even if `content` is byte-identical to the prior version.
    """
    from rush.memory import retrieval
    from rush.memory.authorization import MemoryPolicyError

    if not retrieval.is_write_access(access):
        raise MemoryPolicyError("E_PERMISSION", "policy_grant_required")
    project_root = store.project_root
    row = conn.execute(
        "SELECT * FROM memory_artifacts WHERE id = ?", (artifact_id,)
    ).fetchone()
    if row is None or not retrieval._access_allows(store, row, access, "ordinary"):
        raise VersionConflictError(
            "promotion target changed since review", code="E_NOT_VISIBLE"
        )
    artifact = _row_to_artifact(
        row, default_owner_scope=legacy_owner_scope(project_root)
    )
    # 72-T06 D30: promotion re-sanitizes persisted bytes; a sanitization that would
    # change the event identity is refused like the immutability trigger refuses it.
    if _event_identity_of(artifact.content) != _event_identity_of(
        sanitize_value(artifact.content).value
    ):
        from rush.memory.authorization import MemoryPolicyError

        raise MemoryPolicyError("E_INPUT", "event_identity_immutable")
    if payload_mismatched(row["content"], _row_value(row, "payload_hash")):
        # 72-T01 F1: promotion never blesses bytes that fail their payload binding.
        return artifact, PromotionResult(
            promoted=False,
            new_tier=artifact.trust_tier,
            denial_reason="integrity_payload_mismatch",
            corroboration_count=artifact.corroboration_count,
        )
    now = time.time()
    if not retrieval.evaluate_artifact_visibility(
        store, row, access=access, now=now
    ).visible:
        raise VersionConflictError(
            "promotion target changed since review", code="E_NOT_VISIBLE"
        )
    if artifact.trust_tier == "IMPORTED" and not user_stated:
        return artifact, PromotionResult(
            promoted=False,
            new_tier="IMPORTED",
            denial_reason="imported_unverified",
            corroboration_count=artifact.corroboration_count,
        )
    artifact = dataclasses.replace(
        artifact, content=sanitize_value(artifact.content).value
    )
    if user_stated:
        decision = evaluate_promotion(
            artifact, user_stated=True, project_root=project_root
        )
    elif _is_summary(artifact.content):
        # D6: a consolidated summary never promotes by agreement; no peer scan.
        decision = PromotionResult(
            promoted=False,
            new_tier=artifact.trust_tier,
            denial_reason="insufficient_corroboration",
            corroboration_count=1,
        )
    else:
        decision = _corroborated_decision(
            conn, store, row, artifact, access=access, refs=candidate_refs, now=now
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
        new_text = _persisted_text(row["content"], artifact.content)
        mac = next_row_mac(
            conn,
            project_root,
            artifact.id,
            {"content": new_text, "trust_tier": artifact.trust_tier},
        )
        try:
            conn.execute(
                "UPDATE memory_artifacts SET content = ?, trust_tier = ?, "
                "promoted_at = ?, signature = ?, corroboration_count = ?, "
                "artifact_version = ?, row_mac = ? WHERE id = ?",
                (
                    new_text,
                    artifact.trust_tier,
                    artifact.promoted_at,
                    artifact.signature,
                    artifact.corroboration_count,
                    artifact.artifact_version,
                    mac,
                    artifact.id,
                ),
            )
        except sqlite3.IntegrityError as exc:
            # The caller owns the transaction; its rollback follows the raise.
            _raise_event_identity_immutable(exc, None)
            raise
    return artifact, decision


def _corroborated_decision(
    conn: sqlite3.Connection,
    store: TypedArtifactStore,
    row: sqlite3.Row,
    artifact: MemoryArtifact,
    *,
    access: MemoryAccess,
    refs: list[dict[str, Any]] | None,
    now: float,
) -> PromotionResult:
    """D8 agreement decision: count the candidate's source plus each counted peer."""
    from rush.memory import retrieval

    peers, contradicted = corroborating_peers(
        conn, store, row, access=access, evidence_identity=refs is None, now=now
    )
    counted = peers
    if refs is not None:
        returned = {(p.id, p.artifact_version, p.source) for p in peers}
        named: set[tuple[Any, Any, Any]] = set()
        for ref in refs:
            key = (ref.get("id"), ref.get("version"), ref.get("source"))
            if key[0] == row["id"]:
                if key[1:] != (row["artifact_version"], row["source"]):
                    raise VersionConflictError(
                        "promotion corroborator changed since review", code="E_VERSION"
                    )
                continue
            peer_row = conn.execute(
                "SELECT * FROM memory_artifacts WHERE id = ?", (key[0],)
            ).fetchone()
            if (
                peer_row is None
                or not retrieval._access_allows(store, peer_row, access, "ordinary")
                or not retrieval.evaluate_artifact_visibility(
                    store, peer_row, access=access, now=now
                ).visible
            ):
                raise VersionConflictError(
                    "promotion corroborator changed since review", code="E_NOT_VISIBLE"
                )
            if key not in returned:
                raise VersionConflictError(
                    "promotion corroborator changed since review", code="E_VERSION"
                )
            named.add(key)
        counted = [p for p in peers if (p.id, p.artifact_version, p.source) in named]
    if not _binding_ok(_conn_verifier(conn, store.project_root), row):
        counted = []
    pool = [artifact.source, *(p.source for p in counted)]
    if contradicted:
        return PromotionResult(
            promoted=False,
            new_tier=artifact.trust_tier,
            denial_reason="contradicted",
            corroboration_count=len(set(pool)),
        )
    return evaluate_promotion(
        artifact,
        user_stated=False,
        candidate_sources=pool,
        project_root=store.project_root,
    )


def _event_identity_of(content: Any) -> tuple[tuple[str, str, Any], ...]:
    """D30: the four identity keys a content object carries, with JSON types."""
    if not isinstance(content, dict):
        return ()
    return tuple(
        (key, type(content[key]).__name__, content[key])
        for key in EVENT_IDENTITY_KEYS
        if key in content
    )


def _subject_list(subject: str | Sequence[str]) -> list[str]:
    """72-T06: one subject, or the sorted distinct members of a sequence."""
    if isinstance(subject, str):
        return [subject]
    return sorted(set(subject))


def _subject_clause(column: str, subjects: Sequence[str]) -> str:
    if len(subjects) == 1:
        return f"{column} = ?"
    return f"{column} IN ({','.join('?' for _ in subjects)})"


def _upgrade_ref_visible(
    row: sqlite3.Row, root: Path, access: MemoryAccess | None
) -> bool:
    """D30: a duplicate is listed only for the access that may see it (D40 source,
    owner); never for a missing access."""
    from rush.memory.authorization import source_granted

    if access is None or Path(access.project_root).resolve() != root:
        return False
    if not source_granted(row["source"], access.sources):
        return False
    return access.owner_scope is None or access.owner_scope == owner_scope_for_row(
        row, root
    )


# --- 72-T06 D18 import seam ----------------------------------------------------------------

IMPORT_SOURCE = "capsule:import"
_IMPORT_TEMP_PREFIX = "memory.db.import-"
_IMPORT_LOCK_PREFIX = "memory-capsule-target:"
_IMPORT_RECORD_KEYS = frozenset(
    {
        "foreign_origin_id",
        "family",
        "subject",
        "content",
        "foreign_source",
        "foreign_owner",
        "foreign_symbol_ref",
        "foreign_content_hash",
    }
)
_IMPORT_BINDING_KEYS = frozenset(
    {
        "preview_digest",
        "capsule_digest",
        "selected_ids",
        "destination",
        "store_state",
        "store_revision",
        "policy_revision",
        "grant_id",
        "mapping_id",
        "existing_versions",
        "confirm_constraint_ids",
        "redactions",
    }
)
_LOWER_HEX_64 = re.compile(r"[0-9a-f]{64}")
_WINDOWS_DIRECTORY_ACCESS = 0x81  # FILE_LIST_DIRECTORY | FILE_READ_ATTRIBUTES
_WINDOWS_DIRECTORY_SHARE = 0x3  # FILE_SHARE_READ | FILE_SHARE_WRITE
_WINDOWS_OPEN_EXISTING = 3
_WINDOWS_DIRECTORY_FLAGS = 0x02200000  # BACKUP_SEMANTICS | OPEN_REPARSE_POINT


def _policy_error(code: str, reason: str | None = None) -> Exception:
    from rush.memory.authorization import MemoryPolicyError

    return MemoryPolicyError(code, reason)


def _is_hex64(value: Any) -> bool:
    return isinstance(value, str) and _LOWER_HEX_64.fullmatch(value) is not None


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _require_request_digest(value: Any) -> None:
    """D18/decisions 72-T06: the caller's digest, exactly 64 lowercase hex."""
    if not _is_hex64(value):
        raise _policy_error("E_INPUT", "request_digest_invalid")


def _import_storage_root(access: MemoryAccess) -> Path:
    """D25: the destination store root (`access.storage_root`, 72-T05)."""
    return Path(getattr(access, "storage_root", None) or access.project_root).resolve()


def _import_owner(access: MemoryAccess, root: Path) -> OwnerScope:
    return access.owner_scope or legacy_owner_scope(root)


def _validate_import_records(records: Any) -> list[dict[str, Any]]:
    """D18 record shape: exactly the eight keys with their types; anything else is
    `E_INPUT import_record_invalid` before any effect."""
    invalid = _policy_error("E_INPUT", "import_record_invalid")
    if not isinstance(records, (tuple, list)) or not records:
        raise invalid
    families = set(get_args(MemoryFamily))
    subjects = set(get_args(MemorySubject))
    seen: set[str] = set()
    validated: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict) or set(record) != _IMPORT_RECORD_KEYS:
            raise invalid
        try:
            json.dumps(record["content"], allow_nan=False)
        except (TypeError, ValueError, RecursionError):
            raise invalid from None
        foreign_id = record["foreign_origin_id"]
        owner = record["foreign_owner"]
        symbol_ref = record["foreign_symbol_ref"]
        content_hash = record["foreign_content_hash"]
        owner_ok = owner is None or (
            isinstance(owner, dict)
            and set(owner) == {"kind", "id"}
            and _nonempty_str(owner["kind"])
            and _nonempty_str(owner["id"])
        )
        if (
            not _nonempty_str(foreign_id)
            or foreign_id in seen
            or not isinstance(record["family"], str)
            or record["family"] not in families
            or not isinstance(record["subject"], str)
            or record["subject"] not in subjects
            or not isinstance(record["content"], dict)
            or not _nonempty_str(record["foreign_source"])
            or not owner_ok
            or not (symbol_ref is None or isinstance(symbol_ref, str))
            or not (content_hash is None or _is_hex64(content_hash))
        ):
            raise invalid
        seen.add(foreign_id)
        validated.append(dict(record))
    return validated


def _prepare_import_records(
    records: list[dict[str, Any]], confirm_constraint_ids: Any
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """D18/D30: each record's content after the `origin_event` move and
    sanitization, with its `applicability`; plus the nonzero redaction counts.
    Every `confirm_constraint_ids` entry names exactly one selected constraint."""
    invalid = _policy_error("E_INPUT", "confirm_constraint_ids_invalid")
    if not isinstance(confirm_constraint_ids, (tuple, list)) or not all(
        isinstance(item, str) for item in confirm_constraint_ids
    ):
        raise invalid
    if len(set(confirm_constraint_ids)) != len(confirm_constraint_ids):
        raise invalid
    contents: list[dict[str, Any]] = []
    for record in records:
        content = dict(record["content"])
        origin = {
            key: content.pop(key) for key in EVENT_IDENTITY_KEYS if key in content
        }
        if origin:
            content["origin_event"] = origin
        contents.append(content)

    def constraint_id(content: dict[str, Any]) -> str | None:
        value = content.get("constraint_id")
        if content.get("kind") == "constraint" and isinstance(value, str):
            return value
        return None

    for confirmed in confirm_constraint_ids:
        if sum(1 for c in contents if constraint_id(c) == confirmed) != 1:
            raise invalid
    active = set(confirm_constraint_ids)
    prepared: list[dict[str, Any]] = []
    redactions: list[dict[str, Any]] = []
    for record, content in zip(records, contents, strict=True):
        cleaned = sanitize_value(content)
        if cleaned.redaction_count:
            redactions.append(
                {
                    "foreign_origin_id": record["foreign_origin_id"],
                    "count": cleaned.redaction_count,
                }
            )
        applicability = "active" if constraint_id(content) in active else "pending"
        prepared.append(
            {**record, "content": cleaned.value, "applicability": applicability}
        )
    return prepared, redactions


def _import_view(
    cls: type[TypedArtifactStore], root: Path
) -> tuple[TypedArtifactStore | None, str]:
    """D18 store state through `open_readonly_view`: `current`, `absent` or
    `migration_required`; corrupt or busy raise `MemoryStoreUnreadableError`."""
    view, state = cls.open_readonly_view(root)
    if state in ("corrupt", "busy"):
        raise MemoryStoreUnreadableError(
            readonly_view_reason(state),
            code="E_STORE_CORRUPT" if state == "corrupt" else "E_STORE_BUSY",
        )
    if state == "migration_required":
        return None, "migration_required"
    if view is None:
        return None, "absent"
    return view, "current"


def _grant_wide_access(access: MemoryAccess) -> MemoryAccess:
    """A policy access re-resolved without its requested-source narrowing: the
    same grant, owner and operations over every source that grant approves. A
    legacy access (an explicit allowlist) never widens."""
    if access.kind != "policy" or not access.requested_sources:
        return access
    full, _reason = dataclasses.replace(access, requested_sources=())._re_resolve()
    if full is None or full.grant_id != access.grant_id:
        return access
    return full


def _import_existing_versions(
    view: TypedArtifactStore | None,
    prepared: list[dict[str, Any]],
    access: MemoryAccess,
) -> dict[str, int]:
    """D18: every current local row visible (ordinary) under the access's grant
    with the record's subject and an equal `constraint_id` (constraints) or `key`
    (`preference` records)."""
    if view is None:
        return {}
    from rush.memory.retrieval import NOT_CURRENT_REASONS, evaluate_artifact_visibility

    access = _grant_wide_access(access)
    conn = view._connect()
    existing: dict[str, int] = {}
    for record in prepared:
        content = record["content"]
        if content.get("kind") == "constraint" and isinstance(
            content.get("constraint_id"), str
        ):
            path, value = "$.constraint_id", content["constraint_id"]
        elif record["subject"] == "preference" and isinstance(content.get("key"), str):
            path, value = "$.key", content["key"]
        else:
            continue
        rows = conn.execute(
            "SELECT * FROM memory_artifacts WHERE subject = ? AND "
            f"(CASE WHEN json_valid(content) THEN json_extract(content, '{path}') END)"
            " = ?",
            (record["subject"], value),
        ).fetchall()
        for row in rows:
            decision = evaluate_artifact_visibility(view, row, access=access)
            # a rejected, superseded or pending local row is not a current copy
            if decision.visible and not NOT_CURRENT_REASONS.intersection(
                decision.reason_codes
            ):
                existing[row["id"]] = row["artifact_version"]
    return dict(sorted(existing.items()))


def _import_binding(
    *,
    prepared: list[dict[str, Any]],
    capsule_digest: str,
    confirm_constraint_ids: Sequence[str],
    mapping_id: str | None,
    access: MemoryAccess,
    root: Path,
    store_state: str,
    store_revision: int,
    existing: dict[str, int],
    redactions: list[dict[str, Any]],
) -> dict[str, Any]:
    from rush.delivery.compact import canonical_json

    binding: dict[str, Any] = {
        "capsule_digest": capsule_digest,
        "selected_ids": [record["foreign_origin_id"] for record in prepared],
        "destination": _import_destination(access, root),
        "store_state": store_state,
        "store_revision": store_revision,
        "policy_revision": access.policy_revision,
        "grant_id": access.grant_id,
        "mapping_id": mapping_id,
        "existing_versions": dict(existing),
        "confirm_constraint_ids": list(confirm_constraint_ids),
        "redactions": list(redactions),
    }
    binding["preview_digest"] = hashlib.sha256(canonical_json(binding)).hexdigest()
    return binding


def _import_destination(access: MemoryAccess, root: Path) -> dict[str, Any]:
    return {
        "root": str(root),
        "project_id": access.project_id,
        "worktree_id": access.worktree_id,
        "owner_scope": _import_owner(access, root).as_dict(),
    }


def _check_import_binding(
    binding: Mapping[str, Any],
    records: list[dict[str, Any]],
    confirm_foreign_ids: Any,
    confirm_constraint_ids: Sequence[str],
    access: MemoryAccess,
    root: Path,
) -> None:
    """D18 digest step: the presented binding must recompute and match the request
    and the destination; `confirm_foreign_ids` must equal the selected set."""
    from rush.delivery.compact import canonical_json

    invalid = _policy_error("E_INPUT", "preview_binding_invalid")
    if set(binding) != _IMPORT_BINDING_KEYS:
        raise invalid
    without = {key: value for key, value in binding.items() if key != "preview_digest"}
    try:
        digest = hashlib.sha256(canonical_json(without)).hexdigest()
    except (TypeError, ValueError, RecursionError):
        raise invalid from None
    selected = [record["foreign_origin_id"] for record in records]
    mapping_id = binding["mapping_id"]
    if (
        binding["preview_digest"] != digest
        or not _is_hex64(binding["capsule_digest"])
        or binding["selected_ids"] != selected
        or binding["destination"] != _import_destination(access, root)
        or binding["confirm_constraint_ids"] != list(confirm_constraint_ids)
        or not (mapping_id is None or isinstance(mapping_id, str))
    ):
        raise invalid
    if (
        not isinstance(confirm_foreign_ids, (tuple, list))
        or not all(isinstance(item, str) for item in confirm_foreign_ids)
        or len(set(confirm_foreign_ids)) != len(confirm_foreign_ids)
        or set(confirm_foreign_ids) != set(selected)
    ):
        raise _policy_error("E_INPUT", "confirm_foreign_ids_invalid")


def _check_import_revisions(
    binding: Mapping[str, Any],
    *,
    store_state: str,
    store_revision: int,
    existing: dict[str, int],
    expected_store_revision: int,
    expected_versions: Mapping[str, int],
    access: MemoryAccess,
    redactions: list[dict[str, Any]],
) -> None:
    """D18 revisions step: store drift is `store_changed`; a changed policy
    revision, grant or redaction set is `recovery_required`."""
    if (
        store_state != binding["store_state"]
        or store_revision != binding["store_revision"]
        or expected_store_revision != store_revision
        or dict(expected_versions) != binding["existing_versions"]
        or existing != binding["existing_versions"]
    ):
        raise _policy_error("E_VERSION", "store_changed")
    if (
        binding["policy_revision"] != access.policy_revision
        or binding["grant_id"] != access.grant_id
        or redactions != binding["redactions"]
    ):
        raise _policy_error("E_VERSION", "recovery_required")


def _import_view_replay(
    cls: type[TypedArtifactStore],
    view: TypedArtifactStore | None,
    invocation_id: str,
    effect_id: str,
    access: MemoryAccess,
    request_digest: str,
) -> dict[str, Any] | None:
    """D29/decisions 72-T06 import replay on a read-only view: binding, then every
    result ref visible (inspect), then the digest; `None` when no receipt."""
    from rush.memory.retrieval import _access_allows

    if view is None:
        return None
    conn = view._connect()
    if not v2_receipts_ready(conn):
        return None
    receipt = cls._find_v2_receipt(conn, invocation_id, effect_id)
    if receipt is None:
        return None
    payload = receipt["payload"] if isinstance(receipt["payload"], dict) else {}
    hidden = _policy_error("E_NOT_VISIBLE", "not_visible")
    if not v2_receipt_binding_matches(payload.get("binding"), access):
        raise hidden
    refs = payload.get("result_refs")
    if not isinstance(refs, list):
        raise hidden
    for ref in refs:
        artifact_id = ref.get("artifact_id") if isinstance(ref, dict) else None
        row = conn.execute(
            "SELECT * FROM memory_artifacts WHERE id = ?", (artifact_id,)
        ).fetchone()
        if row is None or not _access_allows(view, row, access, "inspect"):
            raise hidden
    if receipt["request_digest"] != request_digest:
        raise _policy_error("E_VERSION", "effect_digest_conflict")
    result = payload.get("result")
    return result if isinstance(result, dict) else {}


def _import_artifacts(
    prepared: list[dict[str, Any]], capsule_digest: str, owner: OwnerScope
) -> list[MemoryArtifact]:
    """D18 stored rows: new local ids, `IMPORTED`, `capsule:import`, the access
    owner, no symbol/hash/signature/origin, and store-owned content keys."""
    fields = {field.name for field in dataclasses.fields(MemoryArtifact)}
    now = time.time()
    artifacts: list[MemoryArtifact] = []
    for record in prepared:
        content = dict(record["content"])
        content["authority"] = "imported_unverified"
        if record["subject"] == "preference":
            content["applicability"] = record["applicability"]
        content["import_provenance"] = {
            "capsule_digest": capsule_digest,
            "foreign_origin_id": record["foreign_origin_id"],
            "foreign_source": record["foreign_source"],
            "foreign_owner": record["foreign_owner"],
            "foreign_symbol_ref": record["foreign_symbol_ref"],
            "foreign_content_hash": record["foreign_content_hash"],
        }
        artifact = MemoryArtifact(
            id=str(uuid.uuid4()),
            family=record["family"],
            subject=record["subject"],
            trust_tier="IMPORTED",
            content=content,
            source=IMPORT_SOURCE,
            created_at=now,
            owner_scope=owner,
        )
        if "applicability" in fields:  # 72-T05 column
            changes: dict[str, Any] = {"applicability": record["applicability"]}
            artifact = dataclasses.replace(artifact, **changes)
        artifacts.append(artifact)
    return artifacts


def _remove_import_orphans(root: Path) -> None:
    """D18: under the target lock, remove `memory.db.import-*` temps a crashed
    publication left, without following any link."""
    rush = Path(root) / ".rush"
    if os.name == "nt":
        if not rush.is_dir() or rush.is_symlink():
            return
        for entry in os.scandir(rush):
            if entry.name.startswith(_IMPORT_TEMP_PREFIX):
                with suppress(OSError):
                    os.unlink(entry.path)
        return
    try:
        fd = os.open(rush, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        return
    try:
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            return
        for name in os.listdir(fd):
            if name.startswith(_IMPORT_TEMP_PREFIX):
                with suppress(OSError):
                    os.unlink(name, dir_fd=fd)
    finally:
        os.close(fd)


def _contained(physical: Any, relative: str) -> Path:
    """D18: revalidate one seam path; a symlink or reparse point is `symlink`,
    any other escape `path_escape`."""
    from rush.io.physical_paths import ContainmentError
    from rush.memory.authorization import _SYMLINK_CODES

    try:
        return cast("Path", physical.open_contained(relative, purpose="write"))
    except ContainmentError as exc:
        reason = "symlink" if exc.code in _SYMLINK_CODES else "path_escape"
        raise _policy_error("E_PERMISSION", reason) from exc


def _identity(result: os.stat_result) -> tuple[int, int]:
    return result.st_dev, result.st_ino


def _check_pinned_directory(physical: Any, fd: int, rush: Path) -> None:
    _contained(physical, ".rush")
    if _identity(os.fstat(fd)) != _identity(os.lstat(rush)):
        raise _policy_error("E_PERMISSION", "path_escape")


def _bind_import_store(
    conn: sqlite3.Connection, root: Path, db_ino: int, key: bytes | None
) -> None:
    """D41 deferred binding: the binding row MACs the store file's inode (the
    publication temp's, kept by the hard link), then every row is MACed under the
    new store id."""
    if key is None:
        return
    store_id = uuid.uuid4().hex
    conn.execute("BEGIN IMMEDIATE")
    conn.execute(
        "INSERT OR REPLACE INTO memory_store_binding (id, store_id, mac) "
        "VALUES (1, ?, ?)",
        (store_id, _store_mac(key, store_id, root, db_ino)),
    )
    for row in conn.execute("SELECT * FROM memory_artifacts").fetchall():
        conn.execute(
            "UPDATE memory_artifacts SET row_mac = ? WHERE id = ?",
            (row_mac(key, store_id, row), row["id"]),
        )
    conn.commit()


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        view = view[written:]


def _fsync_dir(path: Path) -> None:
    """Mirrors `project_run._fsync_dir`: make a directory entry change durable."""
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _link_error(exc: OSError) -> Exception:
    if isinstance(exc, FileExistsError):
        return _policy_error("E_VERSION", "store_changed")
    return _policy_error("E_UNAVAILABLE", "publication_unsupported")


@contextmanager
def _release_never_masks(manager: Any) -> Iterator[None]:
    """G15: an `OSError` raised while releasing `manager` never masks the outcome of
    its body: a completed body keeps its result and a failed body keeps its error."""
    manager.__enter__()
    try:
        yield
    except BaseException as exc:
        try:
            swallowed = manager.__exit__(type(exc), exc, exc.__traceback__)
        except OSError:
            swallowed = False
        if not swallowed:
            raise
    else:
        with suppress(OSError):
            manager.__exit__(None, None, None)


def _remove_created_rush(physical: Any, created: bool) -> None:
    """Remove a `.rush` this call created, by its revalidated path; a containment
    failure keeps it and denies, an `OSError` keeps it silently."""
    if not created:
        return
    path = _contained(physical, ".rush")
    with suppress(OSError):
        os.rmdir(path)


def _publish_import_posix(conn: sqlite3.Connection, root: Path) -> None:
    """D18 POSIX publication through one `.rush` directory fd: temp created with
    O_EXCL|O_NOFOLLOW under that fd, ancestry and identity rechecked after the
    open, before and after `os.link`; cleanup never uses a path."""
    from rush.io.physical_paths import PhysicalRoot

    physical = PhysicalRoot(root)
    rush = root / ".rush"
    _contained(physical, ".rush")
    created = False
    if not os.path.lexists(rush):
        os.mkdir(rush, 0o700)
        created = True
    try:
        fd = os.open(
            rush,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as exc:
        _remove_created_rush(physical, created)
        if exc.errno == errno.ELOOP:
            raise _policy_error("E_PERMISSION", "symlink") from exc
        raise
    temp_name = _IMPORT_TEMP_PREFIX + uuid.uuid4().hex
    temp_identity: tuple[int, int] | None = None
    linked = False
    try:
        _check_pinned_directory(physical, fd, rush)
        _contained(physical, f".rush/{temp_name}")
        temp_fd = os.open(
            temp_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=fd,
        )
        try:
            temp_stat = os.fstat(temp_fd)
            temp_identity = _identity(temp_stat)
            _bind_import_store(conn, root, temp_stat.st_ino, read_store_key())
            data = conn.serialize()
            conn.close()
            _write_all(temp_fd, data)
            os.fsync(temp_fd)
        finally:
            os.close(temp_fd)
        if _identity(os.stat(temp_name, dir_fd=fd, follow_symlinks=False)) != (
            temp_identity
        ):
            raise _policy_error("E_PERMISSION", "path_escape")
        _check_pinned_directory(physical, fd, rush)
        _contained(physical, ".rush/memory.db")
        try:
            os.link(
                temp_name,
                "memory.db",
                src_dir_fd=fd,
                dst_dir_fd=fd,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise _link_error(exc) from exc
        linked = True
        if (
            _identity(os.stat("memory.db", dir_fd=fd, follow_symlinks=False))
            != temp_identity
        ):
            raise _policy_error("E_PERMISSION", "path_escape")
        _check_pinned_directory(physical, fd, rush)
    except BaseException:
        try:
            if linked and temp_identity is not None:
                with suppress(OSError):
                    published = os.stat("memory.db", dir_fd=fd, follow_symlinks=False)
                    if _identity(published) == temp_identity:
                        os.unlink("memory.db", dir_fd=fd)
            if temp_identity is not None:
                with suppress(OSError):
                    os.unlink(temp_name, dir_fd=fd)
            with suppress(OSError):
                os.fsync(fd)
        finally:
            with suppress(OSError):
                os.close(fd)
        _remove_created_rush(physical, created)
        raise
    try:
        try:
            os.fsync(fd)
            if created:
                _fsync_dir(root)
        except OSError as exc:
            raise _policy_error("E_UNAVAILABLE", "publication_unconfirmed") from exc
        with suppress(OSError):
            os.unlink(temp_name, dir_fd=fd)
            os.fsync(fd)
        if created:
            _write_gitignore_at(fd)
    finally:
        with suppress(OSError):
            os.close(fd)


def _write_gitignore_at(fd: int) -> None:
    """D41/D1: a `.rush` this call created ignores everything in it."""
    try:
        handle = os.open(
            ".gitignore",
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
            0o644,
            dir_fd=fd,
        )
    except OSError:
        return
    try:
        with suppress(OSError):
            os.write(handle, b"*\n")
    finally:
        os.close(handle)


def _pin_windows_directories(physical: Any, rush: Path, handles: list[int]) -> None:
    """D18 Windows: open every directory from the anchor down to `.rush` with a
    retained handle that refuses rename and delete while held."""
    import ctypes
    import importlib

    native: Any = ctypes
    msvcrt: Any = importlib.import_module("msvcrt")
    kernel32 = native.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.restype = native.c_void_p
    invalid_handle = native.c_void_p(-1).value
    root_path = physical.root_path
    for directory in (*reversed(root_path.parents), root_path, rush):
        handle = create_file(
            str(directory),
            _WINDOWS_DIRECTORY_ACCESS,
            _WINDOWS_DIRECTORY_SHARE,
            None,
            _WINDOWS_OPEN_EXISTING,
            _WINDOWS_DIRECTORY_FLAGS,
            None,
        )
        if handle is None or handle == invalid_handle:
            if native.get_last_error() in (2, 3):
                raise _policy_error("E_PERMISSION", "path_escape")
            raise _policy_error("E_UNAVAILABLE", "publication_unsupported")
        handles.append(msvcrt.open_osfhandle(handle, os.O_RDONLY))
        attributes = getattr(os.fstat(handles[-1]), "st_file_attributes", 0)
        if not attributes & stat.FILE_ATTRIBUTE_DIRECTORY or (
            attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            raise _policy_error("E_PERMISSION", "symlink")


def _close_windows_handles(handles: list[int], physical: Any, created: bool) -> None:
    """The `.rush` handle closes before a created `.rush` is removed; the ancestor
    handles after it."""
    rush_handle = (
        handles[-1] if len(handles) > len(physical.root_path.parents) + 1 else None
    )
    try:
        if rush_handle is not None:
            with suppress(OSError):
                os.close(rush_handle)
        _remove_created_rush(physical, created)
    finally:
        for handle in handles:
            if handle != rush_handle:
                with suppress(OSError):
                    os.close(handle)


def _publish_import_windows(conn: sqlite3.Connection, root: Path) -> None:
    """D18 Windows publication: the destination ancestry is pinned by native
    handles, then the temp, link and checks use revalidated paths."""
    from rush.io.physical_paths import PhysicalRoot

    physical = PhysicalRoot(root)
    rush = root / ".rush"
    _contained(physical, ".rush")
    created = False
    if not os.path.lexists(rush):
        os.mkdir(rush, 0o700)
        created = True
    handles: list[int] = []
    temp_rel = f".rush/{_IMPORT_TEMP_PREFIX}{uuid.uuid4().hex}"
    temp_identity: tuple[int, int] | None = None
    linked = False
    try:
        _contained(physical, ".rush")
        _pin_windows_directories(physical, rush, handles)
        temp_path = _contained(physical, temp_rel)
        temp_fd = os.open(
            temp_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o600,
        )
        try:
            temp_stat = os.stat(temp_path)
            temp_identity = _identity(temp_stat)
            _bind_import_store(conn, root, temp_stat.st_ino, read_store_key())
            data = conn.serialize()
            conn.close()
            _write_all(temp_fd, data)
            os.fsync(temp_fd)
        finally:
            os.close(temp_fd)
        if _identity(os.stat(_contained(physical, temp_rel))) != temp_identity:
            raise _policy_error("E_PERMISSION", "path_escape")
        target = _contained(physical, ".rush/memory.db")
        try:
            os.link(_contained(physical, temp_rel), target)
        except OSError as exc:
            raise _link_error(exc) from exc
        linked = True
        published = os.stat(_contained(physical, ".rush/memory.db"))
        if _identity(published) != temp_identity:
            raise _policy_error("E_PERMISSION", "path_escape")
    except BaseException:
        try:
            if linked and temp_identity is not None:
                with suppress(OSError):
                    db_path = rush / "memory.db"
                    if _identity(os.stat(db_path)) == temp_identity:
                        os.unlink(db_path)
            if temp_identity is not None:
                with suppress(OSError):
                    os.unlink(root / temp_rel)
        finally:
            _close_windows_handles(handles, physical, created)
        raise
    try:
        with suppress(OSError):
            os.unlink(_contained(physical, temp_rel))
        if created:
            with suppress(OSError):
                gitignore = os.open(
                    _contained(physical, ".rush/.gitignore"),
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0),
                    0o644,
                )
                try:
                    os.write(gitignore, b"*\n")
                finally:
                    os.close(gitignore)
    finally:
        _close_windows_handles(handles, physical, False)
