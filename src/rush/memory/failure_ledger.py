"""Negative knowledge failure ledger recording failed AST patch fingerprints."""

import hashlib
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any

from rush.safety.redactor import SecretRedactor


class FailureLedger:
    """Tracks failed patch attempts in .rush/memory/failures.db to avoid duplicate error loops."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()
        self.db_path = self.project_root / ".rush" / "memory" / "failures.db"
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
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
        safe_patch = SecretRedactor.redact_text(failed_patch)
        safe_error = SecretRedactor.redact_text(error_message)
        now = int(time.time())
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute(
                """
                INSERT INTO failure_ledgers (fingerprint, error_message, failed_patch, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(fingerprint) DO UPDATE SET error_message=excluded.error_message
                """,
                (fingerprint, safe_error, safe_patch, now),
            )
            conn.commit()
        return fingerprint

    def is_known_failure(self, patch: str) -> bool:
        fingerprint = hashlib.sha256(patch.encode("utf-8")).hexdigest()
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            cur = conn.execute(
                "SELECT 1 FROM failure_ledgers WHERE fingerprint = ?", (fingerprint,)
            )
            return cur.fetchone() is not None

    def get_receipt(self, fingerprint: str) -> dict[str, str | int] | None:
        """Return safe failure evidence without disclosing the failed patch."""
        if not re.fullmatch(r"[a-f0-9]{64}", fingerprint):
            return None
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            row = conn.execute(
                "SELECT error_message, created_at FROM failure_ledgers WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
        return _receipt(fingerprint, row)

    @staticmethod
    def read_receipt(
        project_root: Path, fingerprint: str
    ) -> dict[str, str | int] | None:
        """T10: `get_receipt` without constructing a ledger -- a read-only open that
        never creates `.rush/memory/failures.db` or any sidecar. A missing DB or
        table is no receipt."""
        from rush.memory.store import read_sqlite_readonly, sqlite_has_table

        if not re.fullmatch(r"[a-f0-9]{64}", fingerprint):
            return None

        def read(conn: sqlite3.Connection) -> tuple[str, int] | None:
            if not sqlite_has_table(conn, "failure_ledgers"):
                return None
            return conn.execute(
                "SELECT error_message, created_at FROM failure_ledgers WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()

        db = project_root / ".rush" / "memory" / "failures.db"
        return _receipt(fingerprint, read_sqlite_readonly(db, read))


def _receipt(fingerprint: str, row: Any) -> dict[str, str | int] | None:
    """Safe failure evidence without disclosing the failed patch."""
    if row is None:
        return None
    return {
        "fingerprint": fingerprint,
        "created_at": row[1],
        "redacted_error": SecretRedactor.redact_text(row[0]),
    }
