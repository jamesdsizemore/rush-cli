"""CCR (Context Compression & Restoration) SQLite LRU chunk store."""

import hashlib
import sqlite3
import time
import urllib.parse
from pathlib import Path


class CCRStore:
    """Stores full text chunks and replaces them with reversible <!-- ccr:chunk:HASH --> tags."""

    def __init__(self, project_root: Path | None = None):
        # T10 (R10.2): construction creates nothing; `store_chunk` creates the DB.
        self.project_root = project_root or Path.cwd()
        self.db_path = self.project_root / ".rush" / "cache" / "ccr.db"

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chunks (
                    hash TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    byte_size INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    last_accessed_at INTEGER NOT NULL
                )
                """
            )
            conn.commit()

    def store_chunk(self, content: str) -> str:
        """Stores content in chunk database and returns markdown restoration tag."""
        h = hashlib.sha256(content.encode("utf-8")).hexdigest()
        now = int(time.time())
        size = len(content.encode("utf-8"))

        self._init_db()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO chunks (hash, content, byte_size, created_at, last_accessed_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(hash) DO UPDATE SET last_accessed_at=excluded.last_accessed_at
                """,
                (h, content, size, now, now),
            )
            conn.commit()

        return f"<!-- ccr:chunk:{h} -->"

    def retrieve_chunk(self, chunk_hash: str, *, touch: bool = True) -> str | None:
        """Retrieves raw content and updates LRU state only when explicitly allowed.

        T10: a missing DB is `None` without creating anything, and `touch=False`
        reads over a SQLite `mode=ro` connection."""
        if not self.db_path.is_file():
            return None
        if not touch:
            uri = f"file:{urllib.parse.quote(str(self.db_path))}?mode=ro"
            conn = sqlite3.connect(uri, uri=True)
            try:
                row = conn.execute(
                    "SELECT content FROM chunks WHERE hash = ?", (chunk_hash,)
                ).fetchone()
            finally:
                conn.close()
            return row[0] if row else None
        now = int(time.time())
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "SELECT content FROM chunks WHERE hash = ?", (chunk_hash,)
            )
            row = cur.fetchone()
            if row and touch:
                conn.execute(
                    "UPDATE chunks SET last_accessed_at = ? WHERE hash = ?",
                    (now, chunk_hash),
                )
                conn.commit()
            if row:
                return row[0]
        return None
