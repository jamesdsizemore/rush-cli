"""SQLite-based Cryptographic Result Cache with CLI Flag Salting.

Architecture §8, Phase 21.

Keys are derived from:
SHA-256(file_content_bytes + tool_name + engine_version + config_hash + sorted_cli_flags)
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from rush.contracts.results import (
    ToolResultV1,
    ValidationErrorV1,
    adapt_legacy_tool_result,
    validate_tool_result,
)
from rush.invocation.cache_policy import decide_cache
from rush.logging import get_logger, log_subsystem
from rush.safety.redactor import sanitize_value
from rush.tools.base import ToolResult

logger = get_logger("cache")


class CachedToolResult(ToolResultV1, dict):
    """Dual-contract cached tool result satisfying both ToolResultV1 dataclass and dict interfaces."""

    def __init__(self, v1: ToolResultV1) -> None:
        dict.__init__(self, v1.to_dict())
        for f in v1.__dataclass_fields__:
            object.__setattr__(self, f, getattr(v1, f))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ToolResultV1):
            return self.to_dict() == other.to_dict()
        if isinstance(other, dict):
            return dict(self) == other
        return super().__eq__(other)


CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache_entries (
    key TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    engine TEXT,
    engine_version TEXT,
    result_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_file_path ON cache_entries(file_path);
"""


def compute_file_hash(path: Path) -> str:
    """Compute SHA-256 hash of a file's raw byte content."""
    hasher = hashlib.sha256()
    try:
        with path.open("rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as exc:  # noqa: BLE001
        log_subsystem("cache", "WARN", f"Failed to compute file hash for {path}: {exc}")
        return ""


def compute_cache_key(
    file_path: Path,
    tool_name: str,
    engine_version: str | None,
    config_hash: str | None,
    cli_flags: list[str] | None = None,
) -> str:
    """Compute composite cryptographic cache key salted with sorted CLI flags."""
    content_hash = compute_file_hash(file_path)
    engine_ver = engine_version or "default"
    cfg_hash = config_hash or "default"
    flags_salt = ":".join(sorted(cli_flags or []))

    payload = f"{content_hash}|{tool_name}|{engine_ver}|{cfg_hash}|{flags_salt}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ResultCache:
    """Thread-safe SQLite result cache with WAL mode, LRU eviction, and self-healing."""

    def __init__(self, db_path: Path | None = None, max_size_mb: int = 100) -> None:
        if db_path is None:
            self.db_path = Path.cwd() / ".rush" / "cache.db"
        else:
            self.db_path = db_path
        self.max_size_mb = max_size_mb
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._get_connection() as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")
                # Check DB integrity
                cursor = conn.cursor()
                cursor.execute("PRAGMA integrity_check;")
                row = cursor.fetchone()
                if row and row[0] != "ok":
                    log_subsystem(
                        "cache",
                        "WARN",
                        "Database integrity check failed, rebuilding cache",
                    )
                    self.clear()
                conn.executescript(CACHE_SCHEMA)
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            log_subsystem("cache", "WARN", f"Cache initialization warning: {exc}")

    def get(self, key: str, file_path: Path | None = None) -> ToolResultV1 | None:
        """Retrieve cached ToolResult by cryptographic key."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT result_json FROM cache_entries WHERE key = ?",
                    (key,),
                )
                row = cursor.fetchone()
                if row:
                    data = json.loads(row["result_json"])
                    clean_data = sanitize_value(data).value
                    if (
                        isinstance(clean_data, dict)
                        and "schema_version" not in clean_data
                    ):
                        clean_data = adapt_legacy_tool_result(clean_data).to_dict()
                    validated = validate_tool_result(clean_data)
                    log_subsystem("cache", "INFO", f"Cache HIT for key {key[:12]}")
                    return CachedToolResult(validated)
            log_subsystem("cache", "INFO", f"Cache MISS for key {key[:12]}")
            return None
        except ValidationErrorV1 as val_err:
            log_subsystem(
                "cache",
                "WARN",
                f"Cache retrieval validation failed for key {key[:12]}: {val_err}",
            )
            return None
        except Exception as exc:  # noqa: BLE001
            log_subsystem("cache", "WARN", f"Cache retrieval error: {exc}")
            return None

    def set(
        self,
        key: str,
        result: ToolResult | ToolResultV1 | dict[str, Any],
        file_path: Path | str | None = None,
    ) -> ToolResultV1:
        """Store ToolResult in SQLite cache using parameterized query."""
        if isinstance(result, ToolResultV1):
            result_dict = result.to_dict()
        elif isinstance(result, dict):
            if "schema_version" not in result:
                result_dict = adapt_legacy_tool_result(result).to_dict()
            else:
                result_dict = dict(result)
        else:
            raise ValidationErrorV1(
                code="INVALID_TYPE",
                message=f"Expected ToolResultV1 or dict, got {type(result).__name__}",
                path="",
                invalid_value=result,
            )

        clean_result = sanitize_value(result_dict).value
        validated = validate_tool_result(clean_result)
        result_json = json.dumps(validated.to_dict())
        target_file_path = str(file_path) if file_path is not None else ""

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO cache_entries (key, file_path, tool_name, engine, engine_version, result_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        result_json = excluded.result_json,
                        created_at = CURRENT_TIMESTAMP;
                    """,
                    (
                        key,
                        target_file_path,
                        str(validated.tool),
                        validated.engine,
                        validated.engine_version,
                        result_json,
                    ),
                )
                conn.commit()
            self._maybe_evict_lru()
            return validated
        except Exception as exc:
            log_subsystem("cache", "WARN", f"Cache store error: {exc}")
            raise

    def _maybe_evict_lru(self) -> None:
        """Evict oldest 20% of entries if database file exceeds max_size_mb."""
        if not self.db_path.exists():
            return
        try:
            size_mb = self.db_path.stat().st_size / (1024 * 1024)
            if size_mb > self.max_size_mb:
                with self._get_connection() as conn:
                    conn.execute(
                        """
                        DELETE FROM cache_entries WHERE key IN (
                            SELECT key FROM cache_entries ORDER BY created_at ASC LIMIT (
                                SELECT MAX(1, COUNT(*) / 5) FROM cache_entries
                            )
                        )
                        """
                    )
                    conn.commit()
        except Exception:  # noqa: BLE001, S110
            pass

    def clear(self) -> int:
        """Evict all cache entries and return count of deleted records."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT count(*) FROM cache_entries;")
                count = cursor.fetchone()[0]
                cursor.execute("DELETE FROM cache_entries;")
                conn.commit()
                return count
        except Exception as exc:  # noqa: BLE001
            log_subsystem("cache", "WARN", f"Cache clear error: {exc}")
            return 0

    def stats(self) -> dict[str, Any]:
        """Return cache health, size, and entry statistics."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT count(*) FROM cache_entries;")
                count = cursor.fetchone()[0]
                size_bytes = self.db_path.stat().st_size if self.db_path.exists() else 0
                return {
                    "entries": count,
                    "size_bytes": size_bytes,
                    "size_mb": round(size_bytes / (1024 * 1024), 2),
                    "path": str(self.db_path),
                }
        except Exception as exc:  # noqa: BLE001
            return {"entries": 0, "size_bytes": 0, "size_mb": 0.0, "error": str(exc)}

    def decide(self, context: Any, pure: bool = True) -> Any:
        """Evaluate cache eligibility and derive cache key for an InvocationContext."""
        return decide_cache(context, pure=pure)


__all__ = [
    "CACHE_SCHEMA",
    "CachedToolResult",
    "ResultCache",
    "compute_cache_key",
    "compute_file_hash",
    "decide_cache",
]
