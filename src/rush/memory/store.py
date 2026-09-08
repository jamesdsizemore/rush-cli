"""Unified typed-artifact store: WAL-mode SQLite backing every memory subject.

Phase 61 §6.1/§6.3 — `MemoryArtifact` is one row of the unified schema; `TypedArtifactStore`
enforces the no-STATED-on-entry, redact-before-store, recall-rescan, and staleness invariants.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Literal

from rush.memory.merkle_invalidator import MerkleInvalidator
from rush.memory.trust import evaluate_conflict
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


_SCHEMA_SQL = """
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
    expired_by TEXT
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

_INSERT_SQL = """
INSERT INTO memory_artifacts (
    id, family, subject, trust_tier, content, source, created_at,
    symbol_ref, content_hash, corroboration_count, promoted_at, stale,
    signature, origin_kind, origin_id
) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
"""


def compute_content_signature(content: dict[str, Any]) -> str:
    """Deterministic SHA-256 over a content dict, used for STATED-row signature verification."""
    payload = json.dumps(content, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


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
    )


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
            conn.executescript(_SCHEMA_SQL)
            self._migrate_expiry_columns(conn)
            conn.commit()

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

    def write(self, artifact: MemoryArtifact) -> MemoryArtifact:
        """Persist an artifact. Enforces Invariant 1 (no-STATED-on-entry) and 2 (redact-before-store)."""
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
        stored = dataclasses.replace(artifact, content=sanitized_content)
        with self._connect() as conn:
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
                ),
            )
            conn.commit()
        return stored

    def update_content(self, artifact_id: str, content: dict[str, Any]) -> None:
        """Update an existing row's content (redacted), exercising the AFTER UPDATE FTS trigger."""
        sanitized_content = sanitize_value(content).value
        with self._connect() as conn:
            conn.execute(
                "UPDATE memory_artifacts SET content = ? WHERE id = ?",
                (json.dumps(sanitized_content), artifact_id),
            )
            conn.commit()

    def delete(self, artifact_id: str) -> None:
        """Delete a row by id, exercising the AFTER DELETE FTS trigger."""
        with self._connect() as conn:
            conn.execute("DELETE FROM memory_artifacts WHERE id = ?", (artifact_id,))
            conn.commit()

    def search(self, subject: MemorySubject, query: str) -> list[MemoryArtifact]:
        """FTS5 match scoped to a subject, BM25-ranked (best match first).

        Never applies recall()'s per-row defense checks.
        """
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT ma.* FROM memory_artifacts ma "
                "JOIN memory_fts f ON f.rowid = ma.rowid "
                "WHERE f.content MATCH ? AND ma.subject = ? "
                "ORDER BY f.rank",
                (query, subject),
            )
            rows = cur.fetchall()
        return [_row_to_artifact(row) for row in rows]

    def recall(
        self,
        subject: MemorySubject,
        query: str,
        session_allowlist: Iterable[str] | None = None,
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
        for artifact in self.search(subject, query):
            if artifact.source not in allowed_sources:
                continue
            if artifact.trust_tier == "STATED":
                if artifact.signature is None or (
                    compute_content_signature(artifact.content) != artifact.signature
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
                if file_path.is_file():
                    current_hash = self._merkle.hash_content(
                        file_path.read_text(encoding="utf-8")
                    )
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
