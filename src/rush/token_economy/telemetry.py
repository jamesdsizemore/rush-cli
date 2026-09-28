"""Token economy SQLite telemetry ledger (.rush/telemetry/tokens.db)."""

import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any

# MC04 §9.0: the real-cost event kinds `record_memory_event()` accepts. "embedding" has no
# wired producer yet (no embedding call site exists in this codebase) — it's a valid kind so
# the ledger doesn't need a schema change the day one shows up.
_MEMORY_EVENT_KINDS = frozenset(
    {"retrieval", "expansion", "packing", "handoff", "embedding"}
)

# P69-07 subsections d/e: real, non-NULL attribution sentinel for identity columns whose
# real value a caller didn't supply -- SQLite never treats two NULLs as equal in a filter,
# so a missing attribution value must be a real string, never NULL.
_UNSCOPED = "unscoped"
_IDENTITY_COLUMNS = ("project_id", "run_id", "agent_id", "session_id")


class TelemetryStore:
    """Records raw and compressed token consumption to measure real-world savings and cost reduction."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()
        self.db_path = self.project_root / ".rush" / "telemetry" / "tokens.db"
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS token_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp INTEGER NOT NULL,
                    tool_name TEXT NOT NULL,
                    raw_tokens INTEGER NOT NULL,
                    compressed_tokens INTEGER NOT NULL,
                    duration_ms REAL NOT NULL,
                    project_id TEXT NOT NULL DEFAULT 'unscoped',
                    run_id TEXT NOT NULL DEFAULT 'unscoped',
                    agent_id TEXT NOT NULL DEFAULT 'unscoped',
                    session_id TEXT NOT NULL DEFAULT 'unscoped'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_events (
                    invocation_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    tokens INTEGER NOT NULL,
                    timestamp INTEGER NOT NULL,
                    request_id TEXT NOT NULL,
                    project_id TEXT NOT NULL DEFAULT 'unscoped',
                    run_id TEXT NOT NULL DEFAULT 'unscoped',
                    agent_id TEXT NOT NULL DEFAULT 'unscoped',
                    session_id TEXT NOT NULL DEFAULT 'unscoped',
                    PRIMARY KEY (invocation_id, event_id)
                )
                """
            )
            self._migrate_token_events(conn)
            self._migrate_memory_events(conn)
            conn.commit()

    def _migrate_token_events(self, conn: sqlite3.Connection) -> None:
        """P69-07 subsection d: additive migration for a pre-P69-07 `token_events` table
        that predates the identity columns -- `CREATE TABLE IF NOT EXISTS` above never
        retrofits columns onto an existing table."""
        existing = {row[1] for row in conn.execute("PRAGMA table_info(token_events)")}
        if not existing:
            return
        for column in _IDENTITY_COLUMNS:
            if column not in existing:
                conn.execute(
                    f"ALTER TABLE token_events ADD COLUMN {column} TEXT "
                    f"NOT NULL DEFAULT '{_UNSCOPED}'"
                )

    def _migrate_memory_events(self, conn: sqlite3.Connection) -> None:
        """P69-07 subsection e: a pre-P69-07 `memory_events` table is keyed by
        `(request_id, event_id)` -- a content-derived `request_id` silently collides two
        distinct invocations that share identical content, dropping the second event. The
        real fix changes the primary key to `(invocation_id, event_id)`; SQLite can't
        `ALTER TABLE` a primary key, so a legacy table is recreated: `request_id` is kept
        (as a plain attribution column, unchanged meaning) and backfilled as this
        migration's own `invocation_id` too -- since the old table already enforced
        uniqueness on `(request_id, event_id)`, `(request_id, event_id)` is still unique
        under the new key, so this copy can't collide."""
        existing = {row[1] for row in conn.execute("PRAGMA table_info(memory_events)")}
        if not existing or "invocation_id" in existing:
            return
        conn.execute("ALTER TABLE memory_events RENAME TO memory_events_legacy")
        conn.execute(
            """
            CREATE TABLE memory_events (
                invocation_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                tokens INTEGER NOT NULL,
                timestamp INTEGER NOT NULL,
                request_id TEXT NOT NULL,
                project_id TEXT NOT NULL DEFAULT 'unscoped',
                run_id TEXT NOT NULL DEFAULT 'unscoped',
                agent_id TEXT NOT NULL DEFAULT 'unscoped',
                session_id TEXT NOT NULL DEFAULT 'unscoped',
                PRIMARY KEY (invocation_id, event_id)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO memory_events
                (invocation_id, event_id, kind, tokens, timestamp, request_id)
            SELECT request_id, event_id, kind, tokens, timestamp, request_id
            FROM memory_events_legacy
            """
        )
        conn.execute("DROP TABLE memory_events_legacy")

    def record_memory_event(
        self,
        kind: str,
        tokens: int,
        *,
        request_id: str,
        event_id: str,
        invocation_id: str | None = None,
        project_id: str = _UNSCOPED,
        run_id: str = _UNSCOPED,
        agent_id: str = _UNSCOPED,
        session_id: str = _UNSCOPED,
        opt_in: bool = False,
        cache_write: bool = False,
    ) -> bool:
        """MC04 §9.0 / P69-07 subsection e: persist one real retrieval/expansion/packing/
        handoff/embedding cost, deduplicated by `(invocation_id, event_id)` so a genuine
        retry of the same invocation never inflates the total. `invocation_id` identifies
        *this call*, never content -- omitting it (existing callers) falls back to
        `request_id` as the identity, preserving their exact pre-P69-07 dedup behavior;
        a caller that mints a real per-invocation id (P69-07's own new call sites) passes
        it explicitly so two distinct invocations sharing identical content/`request_id`
        no longer collide. `project_id`/`run_id`/`agent_id`/`session_id` are pure
        attribution for the run/agent/session filters below, never part of the identity
        key -- conflating the two is exactly the bug this migration fixes. Requires
        `opt_in` or `cache_write` — a read-only lookup must call this with neither (or,
        better, never call it at all) so it never persists anything.

        Returns whether a new row was actually written (`False` on a denied write or an
        already-recorded `(invocation_id, event_id)` pair).
        """
        if kind not in _MEMORY_EVENT_KINDS:
            raise ValueError(f"unknown memory event kind: {kind!r}")
        if not (opt_in or cache_write):
            return False
        real_invocation_id = invocation_id if invocation_id is not None else request_id
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO memory_events
                    (invocation_id, event_id, kind, tokens, timestamp, request_id,
                     project_id, run_id, agent_id, session_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    real_invocation_id,
                    event_id,
                    kind,
                    int(tokens),
                    int(time.time()),
                    request_id,
                    project_id,
                    run_id,
                    agent_id,
                    session_id,
                ),
            )
            conn.commit()
            return cur.rowcount > 0

    def get_memory_event_total(
        self,
        kind: str | None = None,
        *,
        project_id: str | None = None,
        run_id: str | None = None,
        agent_id: str | None = None,
        session_id: str | None = None,
    ) -> int:
        """Sum of `tokens` across recorded memory events, optionally scoped to one `kind`
        and/or (P69-07 subsection e) one `project_id`/`run_id`/`agent_id`/`session_id`."""
        clauses: list[str] = []
        params: list[str] = []
        if kind is not None:
            clauses.append("kind = ?")
            params.append(kind)
        for column, value in (
            ("project_id", project_id),
            ("run_id", run_id),
            ("agent_id", agent_id),
            ("session_id", session_id),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                params.append(value)
        sql = "SELECT COALESCE(SUM(tokens), 0) FROM memory_events"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            row = conn.execute(sql, params).fetchone()
        return int(row[0])

    def record_savings(
        self,
        tool_name: str,
        raw_tokens: int,
        compressed_tokens: int,
        duration_ms: float = 0.0,
        *,
        project_id: str = _UNSCOPED,
        run_id: str = _UNSCOPED,
        agent_id: str = _UNSCOPED,
        session_id: str = _UNSCOPED,
    ) -> None:
        now = int(time.time())
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute(
                """
                INSERT INTO token_events
                    (timestamp, tool_name, raw_tokens, compressed_tokens, duration_ms,
                     project_id, run_id, agent_id, session_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now,
                    tool_name,
                    raw_tokens,
                    compressed_tokens,
                    duration_ms,
                    project_id,
                    run_id,
                    agent_id,
                    session_id,
                ),
            )
            conn.commit()

    def get_summary(
        self,
        *,
        project_id: str | None = None,
        run_id: str | None = None,
        agent_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """M10: optionally scoped to one `project_id`/`run_id`/`agent_id`/`session_id`,
        the same clause shape `get_memory_event_total()` already uses -- omitted (the
        default) sums every row, unchanged from before this filter existed."""
        sql, params = _summary_query(project_id, run_id, agent_id, session_id)
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            cur = conn.execute(sql, params)
            count, total_raw, total_comp = cur.fetchone()
        return _summary_payload(count, total_raw, total_comp)


def _summary_query(
    project_id: str | None,
    run_id: str | None,
    agent_id: str | None,
    session_id: str | None,
) -> tuple[str, list[str]]:
    clauses: list[str] = []
    params: list[str] = []
    for column, value in (
        ("project_id", project_id),
        ("run_id", run_id),
        ("agent_id", agent_id),
        ("session_id", session_id),
    ):
        if value is not None:
            clauses.append(f"{column} = ?")
            params.append(value)
    sql = (
        "SELECT COUNT(*), COALESCE(SUM(raw_tokens), 0), "
        "COALESCE(SUM(compressed_tokens), 0) FROM token_events"
    )
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    return sql, params


def _summary_payload(count: int, total_raw: int, total_comp: int) -> dict[str, Any]:
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


def read_summary_readonly(
    project_root: Path,
    *,
    project_id: str | None = None,
    run_id: str | None = None,
    agent_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """T10 (finding 15): `TelemetryStore.get_summary()` without constructing a store.
    Reads `<project_root>/.rush/telemetry/tokens.db` through the X1 read-only opener,
    so nothing (no directory, DB, `-wal`/`-shm` or migration) is ever created. A
    missing DB or table gives the empty summary with `available: false`, a reason,
    and the path."""
    from rush.memory.store import read_sqlite_readonly, sqlite_has_table

    db_path = Path(project_root) / ".rush" / "telemetry" / "tokens.db"
    sql, params = _summary_query(project_id, run_id, agent_id, session_id)
    requested = {
        column
        for column, value in (
            ("project_id", project_id),
            ("run_id", run_id),
            ("agent_id", agent_id),
            ("session_id", session_id),
        )
        if value is not None
    }
    legacy = False

    def read(conn: sqlite3.Connection) -> tuple[int, int, int] | None:
        nonlocal legacy
        if not sqlite_has_table(conn, "token_events"):
            return None
        columns = {row[1] for row in conn.execute("PRAGMA table_info(token_events)")}
        if not requested <= columns:
            # Legacy schema: rows carry no stored identity, so they are
            # unscoped and never attributed to a scoped selection.
            legacy = True
            return 0, 0, 0
        count, total_raw, total_comp = conn.execute(sql, params).fetchone()
        return int(count), int(total_raw), int(total_comp)

    row = read_sqlite_readonly(db_path, read)
    if legacy:
        return {
            **_summary_payload(0, 0, 0),
            "available": True,
            "unscoped": True,
            "reason": "legacy telemetry rows carry no run/agent/session identity",
            "path": str(db_path),
        }
    if row is None:
        return {
            **_summary_payload(0, 0, 0),
            "available": False,
            "reason": "no token telemetry has been recorded for this project",
            "path": str(db_path),
        }
    return {**_summary_payload(*row), "available": True, "path": str(db_path)}
