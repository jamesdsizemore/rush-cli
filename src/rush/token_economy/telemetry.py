"""Token economy SQLite telemetry ledger (.rush/telemetry/tokens.db)."""

import sqlite3
import time
from pathlib import Path
from typing import Any


class TelemetryStore:
    """Records raw and compressed token consumption to measure real-world savings and cost reduction."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()
        self.db_path = self.project_root / ".rush" / "telemetry" / "tokens.db"
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS token_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp INTEGER NOT NULL,
                    tool_name TEXT NOT NULL,
                    raw_tokens INTEGER NOT NULL,
                    compressed_tokens INTEGER NOT NULL,
                    duration_ms REAL NOT NULL
                )
                """
            )
            conn.commit()

    def record_savings(
        self,
        tool_name: str,
        raw_tokens: int,
        compressed_tokens: int,
        duration_ms: float = 0.0,
    ) -> None:
        now = int(time.time())
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO token_events (timestamp, tool_name, raw_tokens, compressed_tokens, duration_ms)
                VALUES (?, ?, ?, ?, ?)
                """,
                (now, tool_name, raw_tokens, compressed_tokens, duration_ms),
            )
            conn.commit()

    def get_summary(self) -> dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """
                SELECT 
                    COUNT(*),
                    COALESCE(SUM(raw_tokens), 0),
                    COALESCE(SUM(compressed_tokens), 0)
                FROM token_events
                """
            )
            count, total_raw, total_comp = cur.fetchone()

        net_saved = max(0, total_raw - total_comp)
        ratio = (net_saved / total_raw) if total_raw > 0 else 0.0
        # Estimated cost savings using blended $3.00 per 1M tokens ($0.000003/token)
        est_dollars = round(net_saved * 0.000003, 4)

        return {
            "events_count": count,
            "total_raw_tokens": total_raw,
            "total_compressed_tokens": total_comp,
            "net_tokens_saved": net_saved,
            "compression_ratio": round(ratio, 4),
            "dollar_savings_est": est_dollars,
        }
