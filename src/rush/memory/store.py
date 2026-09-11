"""Unified typed-artifact store: WAL-mode SQLite backing every memory subject.

Phase 61 §6.1/§6.3 — `MemoryArtifact` is one row of the unified schema; `TypedArtifactStore`
enforces the no-STATED-on-entry, redact-before-store, recall-rescan, and staleness invariants.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import secrets
import sqlite3
import time
import urllib.parse
from collections.abc import Iterable, Sequence
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
    expires_at REAL NOT NULL
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
    archived_at REAL
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
)

_INSERT_SQL = """
INSERT INTO memory_artifacts (
    id, family, subject, trust_tier, content, source, created_at,
    symbol_ref, content_hash, corroboration_count, promoted_at, stale,
    signature, origin_kind, origin_id, artifact_version
) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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


def _row_to_artifact(row: sqlite3.Row) -> MemoryArtifact:
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
    )


@dataclass(frozen=True)
class ReadOnlyOpenResult:
    """Result of `TypedArtifactStore.open_readonly` (MC01 §6.1): never creates a DB/directory."""

    available: bool
    migration_required: bool = False
    connection: sqlite3.Connection | None = None


class TypedArtifactStore:
    """WAL-mode SQLite store for `MemoryArtifact` rows across every memory subject."""

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = (
            Path(project_root).resolve() if project_root else Path.cwd().resolve()
        )
        self.db_path = self.project_root / ".rush" / "memory.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._merkle = MerkleInvalidator(project_root=self.project_root)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
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

    def current_generation(self) -> int:
        """MC02 §9.0 "store generation": the latest `memory_changes` sequence number. A
        `recall_page()` cursor binds this; any write between pages changes it, forcing
        `E_RESTART` instead of silently paging over a mutated candidate set."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(sequence), 0) FROM memory_changes"
            ).fetchone()
        return int(row[0])

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
        scan_limit: int = 512,
    ) -> list[sqlite3.Row]:
        """MC12 §6.7 hybrid-retrieval candidate scope: the same subject/source/trust/expiry
        filters `search_candidates()` applies, without requiring an FTS text match -- vector
        similarity ranks these, so a candidate a lexical query would never match (no shared
        terms) is still eligible to be embedded and recovered by cosine rank. Ordered by ID
        for a deterministic, boundable scan (never BM25 order, which doesn't apply here)."""
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
        params.append(scan_limit)
        sql = (
            "SELECT * FROM memory_artifacts "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY id ASC LIMIT ?"
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
        apply: bool = False,
    ) -> dict[str, Any]:
        """Batch memory deletion (P65-07.3, plan §6.4 transaction/outbox algorithm).

        Validates every member's existence, declared `scope` (its `subject`) match, and
        `expected_revisions` inside one transaction before any write; a missing id, a
        cross-scope id (`MemoryScopeError`), or a stale revision (`VersionConflictError`)
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

            for artifact_id, row in rows.items():
                _write_version(
                    conn,
                    artifact_id,
                    content={},
                    source=row["source"],
                    trust_tier=row["trust_tier"],
                    expected_version=expected_revisions[artifact_id],
                    tombstone=True,
                    subject=row["subject"],
                )
                conn.execute(
                    "DELETE FROM memory_artifacts WHERE id = ?", (artifact_id,)
                )
                conn.execute(
                    "DELETE FROM memory_embeddings WHERE artifact_id = ?",
                    (artifact_id,),
                )
            conn.commit()
            return {"applied": True, "affected": affected}

    def edit(
        self,
        artifact_id: str,
        content: dict[str, Any],
        *,
        expected_version: int,
        scope: str,
        apply: bool = False,
    ) -> dict[str, Any]:
        """Single-artifact content edit under compare-and-swap (P65-07.3, plan §6.4).

        Mirrors `delete_batch()`'s validate-then-write shape but for one id: verifies
        existence, declared `scope` match, and `expected_version` before any write. Preview
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
            conn.commit()
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
        apply: bool = False,
        archived: bool = True,
    ) -> dict[str, Any]:
        """Sets/clears an archived marker under compare-and-swap (P65-07.3, plan §6.4).

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
            conn.commit()
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
        return _row_to_artifact(row) if row else None

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
        `sqlite3.Connection` (SQLite `mode=ro`, so any accidental write raises)."""
        root = Path(project_root).resolve()
        db_path = root / ".rush" / "memory.db"
        if not db_path.exists():
            return ReadOnlyOpenResult(available=False)
        uri = f"file:{urllib.parse.quote(str(db_path))}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(memory_artifacts)")
        }
        if "artifact_version" not in columns:
            conn.close()
            return ReadOnlyOpenResult(available=True, migration_required=True)
        return ReadOnlyOpenResult(available=True, connection=conn)

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
        self, subject: str, symbol_ref: str
    ) -> MemoryArtifact | None:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM memory_artifacts WHERE subject = ? AND symbol_ref = ? "
                "AND trust_tier = 'STATED' LIMIT 1",
                (subject, symbol_ref),
            )
            row = cur.fetchone()
        return _row_to_artifact(row) if row else None

    def _prepare_write(self, artifact: MemoryArtifact) -> MemoryArtifact:
        """Shared pre-insert step for `write()`/`write_pass()`: enforces Invariant 1
        (no-STATED-on-entry), resolves any STATED conflict, and redacts content
        (Invariant 2). Does not touch the database itself -- callers own the transaction.
        """
        if artifact.trust_tier == "STATED":
            raise TrustTierError(
                "write() cannot insert trust_tier='STATED' directly; "
                "promotion is the only path to STATED"
            )
        if artifact.symbol_ref is not None:
            existing = self._find_stated_conflict(artifact.subject, artifact.symbol_ref)
            if (
                existing is not None
                and evaluate_conflict(artifact, existing) == "delete"
            ):
                self.delete(existing.id)
        sanitized_content = sanitize_value(artifact.content).value
        return dataclasses.replace(
            artifact, content=sanitized_content, artifact_version=1
        )

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

    def write(self, artifact: MemoryArtifact) -> MemoryArtifact:
        """Persist an artifact. Enforces Invariant 1 (no-STATED-on-entry) and 2 (redact-before-store)."""
        stored = self._prepare_write(artifact)
        with self._connect() as conn:
            self._insert_row(conn, stored)
            conn.commit()
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
        stored = self._prepare_write(artifact)
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
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
        }

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

    def promote(
        self,
        artifact_id: str,
        *,
        user_stated: bool,
        candidate_sources: list[str] | None = None,
        expected_version: int | None = None,
    ) -> tuple[MemoryArtifact, PromotionResult]:
        """Evaluate persisted bytes and atomically persist their signed promotion."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            return promote_stored_artifact(
                conn,
                artifact_id,
                project_root=self.project_root,
                user_stated=user_stated,
                candidate_sources=candidate_sources,
                expected_version=expected_version,
            )

    def delete(self, artifact_id: str, *, expected_version: int | None = None) -> None:
        """Delete a row by id, exercising the AFTER DELETE FTS trigger.

        Routed through `_write_version` (MC01 §6.1) with `tombstone=True` before the row is
        removed, so `memory_artifact_versions`/`memory_changes` retain the deletion's provenance
        even though `memory_artifacts` no longer has the row. A missing `artifact_id` is a
        silent no-op, matching this method's pre-MC01 behavior.
        """
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT content, source, trust_tier FROM memory_artifacts WHERE id = ?",
                (artifact_id,),
            ).fetchone()
            if row is None:
                return
            _write_version(
                conn,
                artifact_id,
                content=json.loads(row["content"]),
                source=row["source"],
                trust_tier=row["trust_tier"],
                expected_version=expected_version,
                tombstone=True,
            )
            conn.execute("DELETE FROM memory_artifacts WHERE id = ?", (artifact_id,))
            conn.commit()

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
        return [_row_to_artifact(row) for row in rows]

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
                    current_hash = self._merkle.hash_content(
                        file_path.read_text(encoding="utf-8")
                    )
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
    artifact = _row_to_artifact(row)
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
