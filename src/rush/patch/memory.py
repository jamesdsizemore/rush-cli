"""SQLite-backed persistent patch memory store for AI remediations."""

from __future__ import annotations

import hashlib
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PatchMemoryRecord:
    error_signature: str
    target_file: str
    diff_patch: str
    created_at: float
    success_count: int = 1


class PatchMemoryStore:
    """Stores successful patch diffs indexed by deterministic error signature hash."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.db_path = self.repo_root / ".rush" / "cache.db"
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS patch_memory (
                    error_signature TEXT PRIMARY KEY,
                    target_file TEXT NOT NULL,
                    diff_patch TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    success_count INTEGER DEFAULT 1
                )
                """
            )
            conn.commit()

    def record_success(self, error_signature: str, target_file: str, diff_patch: str) -> None:
        sig_hash = hashlib.sha256(error_signature.encode("utf-8")).hexdigest()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO patch_memory (error_signature, target_file, diff_patch, created_at, success_count)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(error_signature) DO UPDATE SET
                    diff_patch = excluded.diff_patch,
                    success_count = success_count + 1
                """,
                (sig_hash, target_file, diff_patch, time.time()),
            )
            conn.commit()

    def lookup_patch(self, error_signature: str) -> str | None:
        sig_hash = hashlib.sha256(error_signature.encode("utf-8")).hexdigest()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT diff_patch FROM patch_memory WHERE error_signature = ?",
                (sig_hash,),
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def list_records(self) -> list[PatchMemoryRecord]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT error_signature, target_file, diff_patch, created_at, success_count FROM patch_memory ORDER BY created_at DESC"
            )
            return [
                PatchMemoryRecord(
                    error_signature=row[0],
                    target_file=row[1],
                    diff_patch=row[2],
                    created_at=row[3],
                    success_count=row[4],
                )
                for row in cursor.fetchall()
            ]

    def clear_memory(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM patch_memory")
            conn.commit()
            return cursor.rowcount
