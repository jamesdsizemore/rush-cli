"""Negative knowledge failure ledger recording failed AST patch fingerprints."""

import hashlib
import sqlite3
import time
from pathlib import Path


class FailureLedger:
    """Tracks failed patch attempts in .rush/memory/failures.db to avoid duplicate error loops."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()
        self.db_path = self.project_root / ".rush" / "memory" / "failures.db"
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS failure_ledgers (
                    fingerprint TEXT PRIMARY KEY,
                    error_message TEXT NOT NULL,
                    failed_patch TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                )
                """
            )
            conn.commit()

    def record_failure(self, failed_patch: str, error_message: str) -> str:
        fingerprint = hashlib.sha256(failed_patch.encode("utf-8")).hexdigest()
        now = int(time.time())
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO failure_ledgers (fingerprint, error_message, failed_patch, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(fingerprint) DO UPDATE SET error_message=excluded.error_message
                """,
                (fingerprint, error_message, failed_patch, now),
            )
            conn.commit()
        return fingerprint

    def is_known_failure(self, patch: str) -> bool:
        fingerprint = hashlib.sha256(patch.encode("utf-8")).hexdigest()
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "SELECT 1 FROM failure_ledgers WHERE fingerprint = ?", (fingerprint,)
            )
            return cur.fetchone() is not None
