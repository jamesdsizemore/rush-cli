"""Pure in-memory thread-safe state store for ephemeral dashboard."""

from __future__ import annotations

import base64
import fcntl
import json
import os
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rush.tools.base import ToolResult


@dataclass
class DashboardState:
    repo_root: str
    started_at: float = field(default_factory=time.time)
    results: list[ToolResult] = field(default_factory=list)
    recent_events: list[dict[str, Any]] = field(default_factory=list)


class InMemoryStateStore:
    """Thread-safe in-memory store for findings, execution history, and active watchers."""

    def __init__(self, repo_root: Path) -> None:
        self._state = DashboardState(repo_root=str(repo_root.resolve()))
        self._lock = threading.Lock()

    def update_results(self, results: list[ToolResult]) -> None:
        with self._lock:
            self._state.results = list(results)

    def add_event(self, event_type: str, details: dict[str, Any]) -> None:
        with self._lock:
            self._state.recent_events.append(
                {
                    "timestamp": time.time(),
                    "type": event_type,
                    "details": details,
                }
            )
            if len(self._state.recent_events) > 200:
                self._state.recent_events = self._state.recent_events[-200:]

    def get_snapshot(self) -> dict[str, Any]:
        with self._lock:
            total_findings = sum(
                len(r.get("findings", [])) for r in self._state.results
            )
            return {
                "repo_root": self._state.repo_root,
                "started_at": self._state.started_at,
                "total_tools": len(self._state.results),
                "total_findings": total_findings,
                "results": list(self._state.results),
                "recent_events": list(self._state.recent_events),
            }


# --- Phase 66 P66-01: canonical per-server project scope --------------------
#
# ProjectRegistry/MutationLedger are constructed fresh per running dashboard
# server (see server.py::create_dashboard_server); they are never module- or
# class-level, so two concurrent servers never share project scope or
# mutation identities. Full Phase 65 snapshot/event wiring (scan progress,
# memory, git, artifacts) lands in later P66-02/03 packets -- this packet
# only needs project-scoped, sequenced snapshot data for the auth/API
# boundary itself.


@dataclass
class ProjectRecord:
    project_id: str
    source_identity: str
    snapshot: dict[str, Any]
    sequence: int = 1
    # P69-03m: two independently-tracked generation values with different
    # ordering semantics -- `scan_generation` is allocated at job acceptance
    # from the durable `project_generations` counter (so two server processes
    # and a restart share one authoritative order), `memory_generation` is the
    # memory store's own real commit order (`TypedArtifactStore
    # .current_generation()`). They are never compared against each other:
    # scan and memory publish disjoint parts of `snapshot`.
    memory_generation: int = 0
    scan_generation: int = 0


class ProjectRegistry:
    """Per-server-instance registry of loaded project snapshots."""

    def __init__(self, projects: dict[str, dict[str, Any]]) -> None:
        self._lock = threading.Lock()
        self._projects: dict[str, ProjectRecord] = {
            project_id: ProjectRecord(
                project_id=project_id,
                source_identity=body.get("source_identity", project_id),
                snapshot=body,
            )
            for project_id, body in projects.items()
        }

    def get(self, project_id: str) -> ProjectRecord | None:
        with self._lock:
            return self._projects.get(project_id)

    def register(self, project_id: str, snapshot: dict[str, Any]) -> ProjectRecord:
        """Insert a newly added/created project's snapshot (P66-02: real
        `rush_project add|create` dispatch, never a UI-only registration).
        Idempotent: registering the same project_id again returns the
        existing record unchanged rather than resetting its sequence."""
        with self._lock:
            existing = self._projects.get(project_id)
            if existing is not None:
                return existing
            record = ProjectRecord(
                project_id=project_id,
                source_identity=snapshot.get("source_identity", project_id),
                snapshot=snapshot,
            )
            self._projects[project_id] = record
            return record

    def list_page(
        self, *, cursor: str | None, limit: int
    ) -> tuple[list[ProjectRecord], str | None]:
        """Paginate this server's currently-registered projects in stable
        insertion order. Cursor is an opaque offset -- this list is already
        behind session auth and is never the durable multi-session registry
        `list_projects_page` (Phase 65) signs with an HMAC key."""
        with self._lock:
            items = list(self._projects.values())
        offset = 0
        if cursor:
            try:
                offset = int(
                    base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
                )
            except (ValueError, UnicodeDecodeError):
                offset = 0
        page = items[offset : offset + limit]
        next_cursor: str | None = None
        if offset + limit < len(items):
            next_cursor = (
                base64.urlsafe_b64encode(str(offset + limit).encode("ascii"))
                .decode("ascii")
                .rstrip("=")
            )
        return page, next_cursor

    def bump_sequence(self, project_id: str) -> None:
        """P69-01.2n shared primitive: advances `sequence` only, under this
        registry's existing lock, without touching `source_identity`.
        `record.snapshot["sequence"]` is kept mirrored to the authoritative
        `record.sequence` attribute here too (P69-03l) -- `build_project_map`
        (project_map.py:427-428) reads `snapshot.get("sequence", 1)` directly
        and no scan producer ever populates that key, so without this mirror
        the map would silently report `sequence=1` forever after any
        sequence-only bump."""
        with self._lock:
            record = self._projects.get(project_id)
            if record is not None:
                record.sequence += 1
                record.snapshot["sequence"] = record.sequence

    def refresh_memories(
        self, project_id: str, memories: list[dict[str, Any]], generation: int
    ) -> bool:
        """P69-01.2n shared primitive: atomically replaces `snapshot["memories"]`
        and bumps `sequence`, but only if `generation` is newer than the
        record's currently-published `memory_generation` -- a stale
        (memories, generation) pair from an earlier `snapshot_memories()` read
        is rejected as a no-op rather than clobbering newer data. Never
        touches `source_identity` (a memory mutation doesn't touch source
        tree state). Mirrors the bumped `sequence` into `snapshot["sequence"]`
        (P69-03l/n), the same choke point `bump_sequence`/`publish_scan_result`
        use, so a pure memory mutation is visible to the map too."""
        with self._lock:
            record = self._projects.get(project_id)
            if record is None or generation <= record.memory_generation:
                return False
            record.snapshot["memories"] = memories
            record.memory_generation = generation
            record.sequence += 1
            record.snapshot["sequence"] = record.sequence
            return True

    def publish_scan_result(
        self,
        project_id: str,
        *,
        snapshot: dict[str, Any],
        source_identity: str,
        generation: int | None = None,
    ) -> bool:
        """P69-03.2c: atomically replaces `snapshot`/`source_identity` and
        bumps `sequence`, all three together under this registry's existing
        lock -- `get()` is itself lock-serialized, so a concurrent reader can
        never observe a combination that didn't exist together at any single
        point in time (a reader blocks in `get()` until this whole block
        releases the lock, never sees a partial update mid-flight). No-op if
        `project_id` isn't registered (a scan completing after its project
        was somehow removed). `sequence`/`source_identity` are also mirrored
        into `snapshot["sequence"]`/`snapshot["source_identity"]` (P69-03l):
        `_snapshot_from_scan_result` never sets either key on the dict it
        hands in here, so `build_project_map` (project_map.py:427-428, which
        reads `snapshot.get("sequence"/"source_identity")` directly, not this
        record's own attributes) would otherwise silently report
        `sequence=1`/`source_identity=project_id` forever after every real
        scan -- this registry is the single choke point every publish path
        goes through, so mirroring here keeps the dict copy authoritative
        without editing `project_map.py` itself.

        P69-03m: `generation` is the acceptance-allocated `scan_generation`
        (from `MutationLedger.allocate_scan_generation`). A completion whose
        generation isn't newer than what this record already published is
        rejected as a no-op -- that is what stops a slow initial scan, or a
        hydration reading an already-superseded published attempt, from
        overwriting a newer result. Compared only against `scan_generation`,
        never `memory_generation`. Returns whether the publish applied."""
        with self._lock:
            record = self._projects.get(project_id)
            if record is None:
                return False
            if generation is not None and generation <= record.scan_generation:
                return False
            record.snapshot = snapshot
            record.source_identity = source_identity
            if generation is not None:
                record.scan_generation = generation
            record.sequence += 1
            record.snapshot["sequence"] = record.sequence
            record.snapshot["source_identity"] = record.source_identity
            return True


@dataclass
class AdmissionResult:
    """Outcome of one durable admission attempt (P69-02.2f). Exactly one of
    `started` / `attached` / `conflict` is true. For an attach or a conflict
    the identity fields describe the *active* row, never the request that
    lost."""

    slot_id: str
    started: bool
    attached: bool
    conflict: bool
    run_id: str = ""
    plan_id: str = ""
    operation_id: str = ""
    execution_identity: str = ""
    owner_instance_id: str = ""


@dataclass
class _Reservation:
    operation_id: str
    is_new: bool
    cached: tuple[int, bytes] | None
    conflict: bool


# --- P69-03p: durable /events backing store ---------------------------------
#
# Phase 66 §3.6's exact numeric contract: at most 100 events per response,
# 2,000 retained per project before durable event-reference pagination is
# required. Module-level so tests can monkeypatch a small retention window
# to exercise the 409 event_cursor_expired path without pushing thousands of
# real rows through sqlite.
_EVENT_PAGE_LIMIT = 100
_EVENT_RETENTION_PER_PROJECT = 2000


class MutationLedger:
    """Durable, per-(project_id, request_id) idempotency + reservation ledger
    for POST .../actions mutation requests (Phase 69 P69-01 subsections d-g).

    Persisted to this OS user's durable Rush data root (the same
    `default_data_root()` pattern `cli.py::_dashboard_descriptor_path` already
    uses) so two server processes on the same project, or one server across a
    restart, share one exclusive reservation per (project_id, request_id) --
    a transactional `INSERT` under a `UNIQUE`/primary-key constraint, never a
    read-then-write race, is what makes two processes racing the same
    request_id exclusive at the storage layer, not merely an in-process lock.

    A non-mutating (preview/read-only) request bypasses persistence entirely
    (subsection l): `mutating=False` never reserves and never durably
    records, so it can't participate in idempotent replay or conflict
    detection -- only genuinely mutating operations get that guarantee.
    """

    def __init__(self, *, db_path: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._run_counter = 0
        if db_path is not None:
            self._db_path = db_path
        else:
            from rush.setup.provision import default_data_root

            self._db_path = default_data_root() / "dashboard" / "mutation_ledger.db"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            # `PRAGMA journal_mode=WAL` needs an exclusive lock and does not
            # honour the busy timeout, so two processes initializing the same
            # brand-new database file at the same moment (two dashboard
            # servers starting together, P69-03m's cross-process counter) can
            # collide here. The journal mode is a persistent property of the
            # file: whichever connection wins sets it for every later one, so
            # losing that race is not an error. The schema statements below
            # take ordinary write locks and do honour the busy timeout.
            with suppress(sqlite3.OperationalError):
                conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS mutation_ledger (
                    project_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    operation_type TEXT NOT NULL DEFAULT '',
                    body_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    status_code INTEGER,
                    response_body BLOB,
                    transition_status TEXT,
                    transition_payload TEXT,
                    created_at REAL NOT NULL,
                    terminal_at REAL,
                    PRIMARY KEY (project_id, request_id)
                );
                CREATE INDEX IF NOT EXISTS idx_mutation_ledger_operation_id
                    ON mutation_ledger(operation_id);
                CREATE TABLE IF NOT EXISTS scan_admission (
                    project_id TEXT NOT NULL,
                    execution_identity TEXT NOT NULL,
                    slot_id TEXT NOT NULL,
                    operation_id TEXT NOT NULL DEFAULT '',
                    owner_instance_id TEXT NOT NULL DEFAULT '',
                    run_id TEXT NOT NULL DEFAULT '',
                    plan_id TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    UNIQUE(project_id)
                );
                CREATE TABLE IF NOT EXISTS operation_attachments (
                    operation_id TEXT PRIMARY KEY,
                    executing_operation_id TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_attachment_executing
                    ON operation_attachments(executing_operation_id);
                CREATE TABLE IF NOT EXISTS project_generations (
                    project_id TEXT PRIMARY KEY,
                    value INTEGER NOT NULL,
                    published_generation INTEGER,
                    latest_published_run_id TEXT,
                    latest_published_attempt_id TEXT
                );
                CREATE TABLE IF NOT EXISTS pending_outcomes (
                    slot_id TEXT PRIMARY KEY,
                    operation_id TEXT NOT NULL DEFAULT '',
                    payload TEXT NOT NULL,
                    owner_instance_id TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS event_sequences (
                    project_id TEXT PRIMARY KEY,
                    value INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dashboard_events (
                    project_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    operation_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (project_id, sequence)
                );
                """
            )
            conn.commit()

    def reserve(
        self,
        project_id: str,
        request_id: str,
        body_hash: str,
        *,
        operation_type: str = "",
    ) -> _Reservation:
        """Preallocate an effect-id for (project_id, request_id) before any
        builder() runs (subsection e). Returns whichever of new-reservation /
        cached-replay / in-flight / conflict applies, decided by one
        transactional insert-or-detect against the durable table."""
        operation_id = uuid.uuid4().hex
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "INSERT INTO mutation_ledger "
                    "(project_id, request_id, operation_id, operation_type, "
                    "body_hash, status, created_at) VALUES (?,?,?,?,?,?,?)",
                    (
                        project_id,
                        request_id,
                        operation_id,
                        operation_type,
                        body_hash,
                        "pending",
                        time.time(),
                    ),
                )
                conn.commit()
                return _Reservation(
                    operation_id=operation_id, is_new=True, cached=None, conflict=False
                )
            except sqlite3.IntegrityError:
                conn.rollback()
            row = conn.execute(
                "SELECT operation_id, body_hash, status_code, response_body "
                "FROM mutation_ledger WHERE project_id = ? AND request_id = ?",
                (project_id, request_id),
            ).fetchone()
        assert row is not None
        if row["body_hash"] != body_hash:
            return _Reservation(
                operation_id=row["operation_id"],
                is_new=False,
                cached=None,
                conflict=True,
            )
        if row["response_body"] is not None:
            return _Reservation(
                operation_id=row["operation_id"],
                is_new=False,
                cached=(row["status_code"], bytes(row["response_body"])),
                conflict=False,
            )
        return _Reservation(
            operation_id=row["operation_id"], is_new=False, cached=None, conflict=False
        )

    def _wait_for_response(
        self, project_id: str, request_id: str, *, timeout: float = 3.0
    ) -> tuple[int, bytes] | None:
        """Bounded poll for another in-flight reserver (same process or a
        genuinely different one racing the same storage layer) to finish."""
        deadline = time.monotonic() + timeout
        while True:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT status_code, response_body FROM mutation_ledger "
                    "WHERE project_id = ? AND request_id = ?",
                    (project_id, request_id),
                ).fetchone()
            if row is not None and row["response_body"] is not None:
                return row["status_code"], bytes(row["response_body"])
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.01)

    def finalize(
        self, project_id: str, request_id: str, status_code: int, response_body: bytes
    ) -> None:
        """Cache builder()'s response for replay. A `202` (accepted, still
        in-flight) response is a valid replay target but not this
        operation's terminal outcome (subsection k) -- only a genuine final
        status code starts the TTL-pruning clock."""
        terminal = status_code != 202
        with self._connect() as conn:
            if terminal:
                conn.execute(
                    "UPDATE mutation_ledger SET status='terminal', status_code=?, "
                    "response_body=?, terminal_at=? WHERE project_id=? AND request_id=?",
                    (status_code, response_body, time.time(), project_id, request_id),
                )
            else:
                conn.execute(
                    "UPDATE mutation_ledger SET status_code=?, response_body=? "
                    "WHERE project_id=? AND request_id=?",
                    (status_code, response_body, project_id, request_id),
                )
            conn.commit()

    def commit(
        self,
        project_id: str,
        request_id: str,
        body_hash: str,
        builder: Callable[[str], tuple[int, bytes]],
        *,
        operation_type: str = "",
        mutating: bool = True,
    ) -> tuple[tuple[int, bytes], bool]:
        """Return ((status_code, response_body), is_conflict) for a mutation
        request_id. `builder` receives the preallocated operation_id (empty
        string for a non-mutating call, which never reserves)."""
        if not mutating:
            return builder(""), False
        reservation = self.reserve(
            project_id, request_id, body_hash, operation_type=operation_type
        )
        if reservation.conflict:
            return (0, b""), True
        if reservation.cached is not None:
            return reservation.cached, False
        if not reservation.is_new:
            cached = self._wait_for_response(project_id, request_id)
            if cached is not None:
                return cached, False
            return (0, b""), True
        response = builder(reservation.operation_id)
        self.finalize(project_id, request_id, response[0], response[1])
        return response, False

    def record_status_transition(
        self, operation_id: str, status: str, payload: dict[str, Any]
    ) -> None:
        """P69-01.2n shared primitive: appends an accepted/running/terminal
        transition for an operation id, in the same durable store as the
        ledger. `status == "terminal"` is what actually starts this row's
        TTL-pruning clock for an operation whose initial response was `202`.

        P69-03p: also the single write point for this project's durable
        `/events` log -- every transition recorded here is additionally
        appended as its own immutable, project-scoped sequenced row in
        `dashboard_events` (never overwritten, unlike the single-row
        `mutation_ledger` status above), so `/events` reads real history
        across a restart instead of a volatile in-memory ring buffer.
        Retention is pruned to the most recent `_EVENT_RETENTION_PER_PROJECT`
        rows per project on every write."""
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if status == "terminal":
                conn.execute(
                    "UPDATE mutation_ledger SET status='terminal', transition_status=?, "
                    "transition_payload=?, terminal_at=? WHERE operation_id=?",
                    (status, json.dumps(payload), time.time(), operation_id),
                )
            else:
                conn.execute(
                    "UPDATE mutation_ledger SET transition_status=?, transition_payload=? "
                    "WHERE operation_id=?",
                    (status, json.dumps(payload), operation_id),
                )
            row = conn.execute(
                "SELECT project_id FROM mutation_ledger WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
            if row is not None:
                project_id = row["project_id"]
                seq_row = conn.execute(
                    "INSERT INTO event_sequences (project_id, value) VALUES (?, 1) "
                    "ON CONFLICT(project_id) DO UPDATE SET value = value + 1 "
                    "RETURNING value",
                    (project_id,),
                ).fetchone()
                sequence = int(seq_row["value"])
                conn.execute(
                    "INSERT INTO dashboard_events "
                    "(project_id, sequence, operation_id, status, payload, created_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (
                        project_id,
                        sequence,
                        operation_id,
                        status,
                        json.dumps(payload),
                        time.time(),
                    ),
                )
                threshold = sequence - _EVENT_RETENTION_PER_PROJECT
                if threshold > 0:
                    conn.execute(
                        "DELETE FROM dashboard_events "
                        "WHERE project_id = ? AND sequence <= ?",
                        (project_id, threshold),
                    )
            conn.commit()

    def list_events(
        self, project_id: str, *, after: int, limit: int = _EVENT_PAGE_LIMIT
    ) -> tuple[list[dict[str, Any]], int, bool] | None:
        """P69-03p: durable read path over `dashboard_events` (written by
        `record_status_transition` above). Returns `None` when `after` falls
        outside this project's retained window -- the caller turns that into
        `409 event_cursor_expired` with a snapshot-reload instruction, never
        silently resetting to the oldest available event. Otherwise returns
        `(events, next_after, has_more)`, capped at `_EVENT_PAGE_LIMIT` per
        page regardless of the requested `limit`."""
        limit = max(1, min(limit, _EVENT_PAGE_LIMIT))
        with self._connect() as conn:
            oldest = conn.execute(
                "SELECT MIN(sequence) FROM dashboard_events WHERE project_id = ?",
                (project_id,),
            ).fetchone()[0]
            if oldest is not None and after < int(oldest) - 1:
                return None
            rows = conn.execute(
                "SELECT sequence, operation_id, status, payload, created_at "
                "FROM dashboard_events WHERE project_id = ? AND sequence > ? "
                "ORDER BY sequence LIMIT ?",
                (project_id, after, limit + 1),
            ).fetchall()
        has_more = len(rows) > limit
        rows = rows[:limit]
        events = [
            {
                "sequence": row["sequence"],
                "operation_id": row["operation_id"],
                "status": row["status"],
                "payload": json.loads(row["payload"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]
        next_after = events[-1]["sequence"] if events else after
        return events, next_after, has_more

    def get_operation_status(self, operation_id: str) -> dict[str, Any] | None:
        """P69-01.2n shared primitive: single-row lookup of the latest
        transition for `operation_id`."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT status, transition_status, transition_payload, terminal_at "
                "FROM mutation_ledger WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
        if row is None:
            return None
        payload = (
            json.loads(row["transition_payload"]) if row["transition_payload"] else None
        )
        return {
            "status": row["transition_status"] or row["status"],
            "terminal_at": row["terminal_at"],
            "payload": payload,
        }

    # --- P69-03m: durable per-project scan-generation counter + pointer -----
    #
    # Same database file and connection factory as the admission table above
    # (`default_data_root() / "dashboard" / "mutation_ledger.db"`), so two
    # independent server processes, or one server across a restart,
    # necessarily allocate from the identical durable counter rather than
    # from per-process counters that don't compare. Verified against the real
    # deployed engine: `sqlite3.sqlite_version_info` is 3.50.4 here, above
    # both `ON CONFLICT DO UPDATE` (3.24) and `RETURNING` (3.35).

    def allocate_scan_generation(self, project_id: str) -> int:
        """Allocate this project's next scan ordering number, at job
        acceptance. Touches `value` alone -- never the pointer columns: an
        accepted-but-not-yet-executed request must not be able to move the
        published pointer to a run with no results yet. A project's first-ever
        allocation creates the row at 1 (never a silent no-op)."""
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "INSERT INTO project_generations (project_id, value) VALUES (?, 1) "
                    "ON CONFLICT(project_id) DO UPDATE SET value = value + 1 "
                    "RETURNING value",
                    (project_id,),
                ).fetchone()
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
        return int(row["value"])

    def record_published_scan(
        self, project_id: str, generation: int, run_id: str, attempt_id: str
    ) -> bool:
        """Record the published pointer, only after a real publish succeeded --
        a durable compare-and-swap, never an unconditional write. A delayed
        publish racing a newer one that already landed loses here and leaves
        the newer pointer intact. `published_generation` (highest generation
        actually published) is a separate column from `value` (next
        allocation) and the two are never conflated. Returns whether this
        generation won."""
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                # Seeds `value` from the published generation only when no row
                # exists at all (a publisher that never allocated), so later
                # allocations still continue above it.
                conn.execute(
                    "INSERT OR IGNORE INTO project_generations (project_id, value) "
                    "VALUES (?, ?)",
                    (project_id, generation),
                )
                cursor = conn.execute(
                    "UPDATE project_generations SET published_generation = ?, "
                    "latest_published_run_id = ?, latest_published_attempt_id = ? "
                    "WHERE project_id = ? "
                    "AND ? > COALESCE(published_generation, 0)",
                    (generation, run_id, attempt_id, project_id, generation),
                )
                won = cursor.rowcount == 1
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
        return won

    def published_pointer(self, project_id: str) -> dict[str, Any] | None:
        """The durable answer to "which `(run_id, attempt_id)` is this
        project's currently-published scan, and at which generation" -- what a
        hydrating server reads *first*, never guessing or scanning run
        directories. The admission row that would otherwise hint at this is
        released the moment its job reaches terminal state (subsection g), so
        this pointer is the only durable thing left naming it. `None` until a
        real publish has landed."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT published_generation, latest_published_run_id, "
                "latest_published_attempt_id FROM project_generations "
                "WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        if row is None or row["published_generation"] is None:
            return None
        return {
            "published_generation": int(row["published_generation"]),
            "run_id": row["latest_published_run_id"] or "",
            "attempt_id": row["latest_published_attempt_id"] or "",
        }

    # --- P69-02.2f/g/h: durable single-slot-per-project admission ----------

    def admit(
        self,
        project_id: str,
        *,
        execution_identity: str,
        slot_id: str,
        operation_id: str = "",
        run_id: str = "",
        plan_id: str = "",
        owner_instance_id: str = "",
    ) -> AdmissionResult:
        """Subsection f: one durable admission decision per project, arbitrated
        by `scan_admission`'s `UNIQUE(project_id)` constraint rather than any
        in-memory `thread.is_alive()` check.

        The admission boundary is transaction **commit**, not an `INSERT` that
        returned without error -- this method only returns once its own
        transaction has durably committed, so a caller may never launch work
        or send a 202 before that point. On constraint failure the existing
        row is read *inside the same transaction* and compared: an exact
        `execution_identity` match attaches (writing the attachment record in
        that same transaction), a mismatch returns a structured conflict that
        names the active row's identity, and an admission row that has since
        been freed falls through to fresh admission.
        """
        now = time.time()
        columns = (
            project_id,
            execution_identity,
            slot_id,
            operation_id,
            owner_instance_id,
            run_id,
            plan_id,
            now,
        )
        insert = (
            "INSERT INTO scan_admission (project_id, execution_identity, slot_id, "
            "operation_id, owner_instance_id, run_id, plan_id, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)"
        )
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                try:
                    conn.execute(insert, columns)
                except sqlite3.IntegrityError:
                    row = conn.execute(
                        "SELECT execution_identity, slot_id, operation_id, "
                        "owner_instance_id, run_id, plan_id FROM scan_admission "
                        "WHERE project_id = ?",
                        (project_id,),
                    ).fetchone()
                    if row is None:
                        # The admission row was freed between the failed insert
                        # and this read: this request is admitted fresh, never
                        # attached to work that is already over.
                        conn.execute(insert, columns)
                    elif row["execution_identity"] != execution_identity:
                        conn.rollback()
                        return AdmissionResult(
                            slot_id=row["slot_id"],
                            started=False,
                            attached=False,
                            conflict=True,
                            run_id=row["run_id"],
                            plan_id=row["plan_id"],
                            operation_id=row["operation_id"],
                            execution_identity=row["execution_identity"],
                            owner_instance_id=row["owner_instance_id"],
                        )
                    else:
                        if (
                            operation_id
                            and row["operation_id"]
                            and operation_id != row["operation_id"]
                        ):
                            conn.execute(
                                "INSERT OR REPLACE INTO operation_attachments "
                                "(operation_id, executing_operation_id, created_at) "
                                "VALUES (?,?,?)",
                                (operation_id, row["operation_id"], now),
                            )
                        conn.commit()
                        return AdmissionResult(
                            slot_id=row["slot_id"],
                            started=False,
                            attached=True,
                            conflict=False,
                            run_id=row["run_id"],
                            plan_id=row["plan_id"],
                            operation_id=row["operation_id"],
                            execution_identity=row["execution_identity"],
                            owner_instance_id=row["owner_instance_id"],
                        )
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
        return AdmissionResult(
            slot_id=slot_id,
            started=True,
            attached=False,
            conflict=False,
            run_id=run_id,
            plan_id=plan_id,
            operation_id=operation_id,
            execution_identity=execution_identity,
            owner_instance_id=owner_instance_id,
        )

    def terminalize_and_release(
        self,
        slot_id: str,
        *,
        operation_id: str = "",
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Subsection g: the one idempotent transaction that records an
        operation's terminal status transition *and* frees its admission slot.

        Safe to retry. If any statement fails the whole transaction rolls
        back, so the admission row is never independently deleted -- it stays
        as-is, naming its `owner_instance_id`, for recovery's sweep to retry.
        """
        body = json.dumps(payload or {})
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if operation_id:
                    conn.execute(
                        "UPDATE mutation_ledger SET status='terminal', "
                        "transition_status='terminal', transition_payload=?, "
                        "terminal_at=COALESCE(terminal_at, ?) WHERE operation_id=?",
                        (body, now, operation_id),
                    )
                conn.execute("DELETE FROM scan_admission WHERE slot_id = ?", (slot_id,))
                conn.execute(
                    "DELETE FROM pending_outcomes WHERE slot_id = ?", (slot_id,)
                )
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def register_pending_outcome(
        self,
        slot_id: str,
        *,
        operation_id: str = "",
        payload: dict[str, Any] | None = None,
        owner_instance_id: str = "",
    ) -> None:
        """Subsection g: durable record of a real terminal outcome that has
        not yet been reflected in the ledger, so a transient terminalization
        failure under a still-live owner is retryable as bookkeeping alone --
        the operation's actual work is never re-executed."""
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO pending_outcomes (slot_id, operation_id, "
                "payload, owner_instance_id, created_at) VALUES (?,?,?,?,?)",
                (
                    slot_id,
                    operation_id,
                    json.dumps(payload or {}),
                    owner_instance_id,
                    time.time(),
                ),
            )
            conn.commit()

    def pending_outcome(self, slot_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT slot_id, operation_id, payload, owner_instance_id "
                "FROM pending_outcomes WHERE slot_id = ?",
                (slot_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "slot_id": row["slot_id"],
            "operation_id": row["operation_id"],
            "payload": json.loads(row["payload"]),
            "owner_instance_id": row["owner_instance_id"],
        }

    def admission_for_project(self, project_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT project_id, execution_identity, slot_id, operation_id, "
                "owner_instance_id, run_id, plan_id FROM scan_admission "
                "WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def list_admissions(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT project_id, execution_identity, slot_id, operation_id, "
                "owner_instance_id, run_id, plan_id FROM scan_admission"
            ).fetchall()
        return [dict(row) for row in rows]

    def resolve_attachment(self, operation_id: str) -> str:
        """Subsection e/i: follow an attachment chain of any length to the
        operation that is actually doing the work. An operation with no
        attachment record resolves to itself."""
        seen = {operation_id}
        current = operation_id
        with self._connect() as conn:
            while True:
                row = conn.execute(
                    "SELECT executing_operation_id FROM operation_attachments "
                    "WHERE operation_id = ?",
                    (current,),
                ).fetchone()
                if row is None:
                    return current
                following = row["executing_operation_id"]
                if following in seen:
                    return current
                seen.add(following)
                current = following

    def operation_project_id(self, operation_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT project_id FROM mutation_ledger WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
        return row["project_id"] if row is not None else None

    def attachment_count(self) -> int:
        with self._connect() as conn:
            return int(
                conn.execute("SELECT COUNT(*) FROM operation_attachments").fetchone()[0]
            )

    def attachment_pairs(self) -> list[tuple[str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT operation_id, executing_operation_id FROM operation_attachments"
            ).fetchall()
        return [(row["operation_id"], row["executing_operation_id"]) for row in rows]

    def prune_expired(
        self, *, ttl_seconds: float = 86400.0, deadline_seconds: float = 1.0
    ) -> int:
        """Subsection k/i: prune only rows that reached a genuine terminal
        state at least `ttl_seconds` ago. A `202`-accepted row that never
        transitioned (`terminal_at IS NULL`) is never matched, so an
        interrupted-but-unreconciled row stays visible to recovery.

        One transactional deletion unit per pass: discover the complete
        transitive attachment set pointing at each expiring row, then delete
        the target rows, every discovered attachment record and every
        discovered operation's own reservation entry together. On a
        contention/busy signal the *entire* transaction restarts
        (re-discover, re-delete) -- never a bare `DELETE` retry against
        previously-discovered, now-stale rows. Exhausting `deadline_seconds`
        leaves every row exactly as it was for the next sweep.
        """
        deadline = time.monotonic() + deadline_seconds
        backoff = 0.005
        while True:
            try:
                return self._prune_once(ttl_seconds)
            except sqlite3.OperationalError as exc:
                message = str(exc).lower()
                if "lock" not in message and "busy" not in message:
                    raise
                if time.monotonic() >= deadline:
                    return 0
                time.sleep(backoff)
                backoff = min(backoff * 2, 0.1)

    def _prune_once(self, ttl_seconds: float) -> int:
        cutoff = time.time() - ttl_seconds
        with self._lock, self._connect() as conn:
            # BEGIN IMMEDIATE, never a deferred BEGIN: the write lock must be
            # held before discovery runs, or a concurrent attachment write in
            # WAL mode is not serialized against discovery-through-deletion.
            conn.execute("BEGIN IMMEDIATE")
            try:
                targets = [
                    row["operation_id"]
                    for row in conn.execute(
                        "SELECT operation_id FROM mutation_ledger WHERE "
                        "status = 'terminal' AND terminal_at IS NOT NULL "
                        "AND terminal_at < ?",
                        (cutoff,),
                    ).fetchall()
                ]
                if not targets:
                    conn.commit()
                    return 0
                links = conn.execute(
                    "SELECT operation_id, executing_operation_id "
                    "FROM operation_attachments"
                ).fetchall()
                reverse: dict[str, list[str]] = {}
                for link in links:
                    reverse.setdefault(link["executing_operation_id"], []).append(
                        link["operation_id"]
                    )
                doomed = set(targets)
                frontier = list(targets)
                while frontier:
                    current = frontier.pop()
                    for attached in reverse.get(current, ()):
                        if attached not in doomed:
                            doomed.add(attached)
                            frontier.append(attached)
                ids = sorted(doomed)
                marks = ",".join("?" * len(ids))
                conn.execute(
                    f"DELETE FROM operation_attachments WHERE operation_id IN ({marks})",
                    ids,
                )
                conn.execute(
                    "DELETE FROM operation_attachments WHERE "
                    f"executing_operation_id IN ({marks})",
                    ids,
                )
                removed = conn.execute(
                    f"DELETE FROM mutation_ledger WHERE operation_id IN ({marks})",
                    ids,
                ).rowcount
                conn.commit()
                return removed
            except BaseException:
                conn.rollback()
                raise

    def next_run_id(self) -> str:
        with self._lock:
            self._run_counter += 1
            return f"run-{self._run_counter}"


# --- Phase 66 P66-04: at most one active scan/rescan/resume per project ----
#
# `execute_scan`/`rescan_project_run`/`resume_scan_run` (rush.workflows.
# project_run) are real, potentially slow operations dispatched onto a
# background thread by server.py so the HTTP action itself returns 202
# immediately (plan Sec 3.7: "Expensive work is queued ... not held in HTTP
# worker"). Making a browser refresh/reconnect *attach* to that same
# background job instead of spawning a duplicate is `MutationLedger.admit()`'s
# durable `scan_admission` table (P69-02.2f), not this tracker: an in-memory
# decision has no cross-process atomicity and, having produced zero durable
# writes, leaves nothing to replay from after a crash. `ScanRunTracker` is
# now only this server instance's own record of which thread is running an
# already-admitted job, for the Scans section's live-run indicator.


@dataclass
class ActiveScan:
    run_id: str
    plan_id: str
    thread: threading.Thread


class ScanConflictError(RuntimeError):
    """P69-01 subsection p / P69-02.2f: raised instead of silently attaching
    when the durable admission row for this project names a *different*
    `execution_identity` than the one being requested -- the new request's
    own distinct identity must never be silently discarded. Carries the
    active row's identity, never the request that lost. A dead owner's row
    produces this same structured conflict: a live request never attempts a
    takeover, it waits for recovery's sweep."""

    def __init__(
        self, project_id: str, active_operation_type: str, active_run_id: str
    ) -> None:
        self.project_id = project_id
        self.active_operation_type = active_operation_type
        self.active_run_id = active_run_id
        super().__init__(
            f"project {project_id!r} already has an active {active_operation_type!r} "
            f"operation (run_id={active_run_id!r})"
        )


class ScanRunTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: dict[str, ActiveScan] = {}

    def register(
        self,
        project_id: str,
        *,
        run_id: str,
        plan_id: str,
        thread: threading.Thread,
    ) -> None:
        """Record which background thread is running this project's already
        *admitted* job. P69-02.2f moved the admission decision itself out of
        here entirely -- an in-memory decision has no cross-process atomicity
        and leaves nothing to replay from after a crash -- so this tracker no
        longer decides anything; it only answers `active_run_id` for the
        Scans section's live-run indicator."""
        with self._lock:
            self._active[project_id] = ActiveScan(
                run_id=run_id, plan_id=plan_id, thread=thread
            )

    def active_run_id(self, project_id: str) -> str | None:
        with self._lock:
            existing = self._active.get(project_id)
            if existing is not None and existing.thread.is_alive():
                return existing.run_id
            return None


class OwnerLockError(RuntimeError):
    """Raised when this process's own owner-liveness lock cannot be
    acquired -- the exact `owner_instance_id` is already held by another
    live process. Should not happen in practice: `owner_instance_id` is
    minted fresh (server identity + a random start nonce) per process
    start, per subsection h."""


def _owner_lock_path(owner_instance_id: str, *, data_root: Path | None = None) -> Path:
    """P69-01 subsection h: `<data_root>/owners/<owner_instance_id>.lock`.
    Never keyed by project -- an owner-liveness lock identifies one
    executor instance (a dashboard server, a standalone TUI process, a
    local CHECK_SUITE job), not a project."""
    if data_root is None:
        from rush.setup.provision import default_data_root

        data_root = default_data_root()
    owners_dir = data_root / "owners"
    owners_dir.mkdir(parents=True, exist_ok=True)
    return owners_dir / f"{owner_instance_id}.lock"


class OwnerLock:
    """Owner-liveness lock (subsection h): acquired once at startup, held
    for this process's entire lifetime, never explicitly released. The
    kernel releases it the instant this process exits, including a crash
    -- no heartbeat/renewal needed. That release is what makes liveness
    checkable from any other process: a non-blocking exclusive-lock
    attempt on the same file either fails (still held -- this owner is
    alive) or succeeds (this owner is provably gone). See
    `probe_owner_alive`/`claim_dead_owner`.

    POSIX only (`fcntl.flock`) -- the real Windows-equivalent named-mutex
    primitive named in the plan is not implemented here.
    """

    def __init__(
        self, owner_instance_id: str, *, data_root: Path | None = None
    ) -> None:
        self.owner_instance_id = owner_instance_id
        self.path = _owner_lock_path(owner_instance_id, data_root=data_root)
        self._fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(self._fd)
            raise OwnerLockError(
                f"owner-liveness lock already held for {owner_instance_id!r}"
            ) from None
        # Intentionally never fcntl.LOCK_UN'd / os.close()'d here -- see
        # class docstring: the kernel is the only thing that releases it.


@contextmanager
def claim_dead_owner(
    owner_instance_id: str, *, data_root: Path | None = None
) -> Iterator[bool]:
    """Non-blocking attempt to become the exclusive reconciler for a dead
    owner's work (subsection h's atomic claim). Yields `True` only to the
    single caller that wins the race for `owner_instance_id`'s
    owner-liveness lock file -- the lock stays held (blocking every other
    concurrent claimant) for the duration of this context, so two
    recovery workers racing the same dead owner's pending row can never
    both proceed. Yields `False` immediately, without blocking, when the
    owner is still alive (its process still holds the lock) or another
    claimant already won.

    PID is never consulted -- only the lock's real kernel-held state --
    so an OS reusing a dead owner's old PID for an unrelated live process
    cannot cause a false "alive" result (no PID-reuse failure mode).
    """
    path = _owner_lock_path(owner_instance_id, data_root=data_root)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        yield False
        return
    try:
        yield True
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def probe_owner_alive(owner_instance_id: str, *, data_root: Path | None = None) -> bool:
    """True if the specific recorded owner is still alive, False if its
    process is provably gone. Always keyed by the exact
    `owner_instance_id` recorded on the row/operation being probed --
    never by project, and never by PID."""
    with claim_dead_owner(owner_instance_id, data_root=data_root) as claimed:
        return not claimed


@dataclass(eq=False)
class _PendingOutcome:
    slot_id: str
    operation_id: str
    payload: dict[str, Any]


class PendingOutcomeQueue:
    """Server-process-owned, in-memory retry queue for terminal outcomes
    (P69-02.2g).

    A worker/dispatcher hands its real outcome here *before* any durable write
    is attempted, then exits. This queue -- never the exiting worker -- owns
    retrying the durable pending-outcome write and then the idempotent
    terminalize-and-release transaction, for as long as this server process
    stays alive. The only way an outcome is lost is the server process itself
    dying before anything durable landed, which is exactly what the
    dead-owner reconciliation in `reconcile_admissions` handles.
    """

    def __init__(
        self,
        ledger: MutationLedger,
        *,
        owner_instance_id: str = "",
        retry_interval: float = 0.5,
    ) -> None:
        self._ledger = ledger
        self._owner_instance_id = owner_instance_id
        self._retry_interval = retry_interval
        self._pending: list[_PendingOutcome] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def submit(
        self,
        slot_id: str,
        *,
        operation_id: str = "",
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Hand one real terminal outcome to the queue. Never raises: a
        failure here must not propagate back into the exiting worker."""
        with self._lock:
            self._pending.append(
                _PendingOutcome(slot_id, operation_id, dict(payload or {}))
            )
        self.drain_once()
        if self.pending_count():
            self._ensure_worker()

    def drain_once(self) -> int:
        """Retry every queued outcome once. Bookkeeping only -- an
        operation's actual work is never re-executed from here."""
        with self._lock:
            items = list(self._pending)
        completed: list[_PendingOutcome] = []
        for item in items:
            try:
                self._ledger.register_pending_outcome(
                    item.slot_id,
                    operation_id=item.operation_id,
                    payload=item.payload,
                    owner_instance_id=self._owner_instance_id,
                )
                self._ledger.terminalize_and_release(
                    item.slot_id,
                    operation_id=item.operation_id,
                    payload=item.payload,
                )
            except Exception:  # noqa: BLE001,S112 -- a durable write that
                # fails for any reason stays queued for the next retry; this
                # queue is the retry mechanism, so there is nothing to log to.
                continue
            completed.append(item)
        with self._lock:
            for item in completed:
                if item in self._pending:
                    self._pending.remove(item)
        return len(completed)

    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    def stop(self) -> None:
        self._stop.set()

    def _ensure_worker(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._loop, daemon=True, name="rush-pending-outcomes"
            )
            self._thread.start()

    def _loop(self) -> None:
        while not self._stop.wait(self._retry_interval):
            self.drain_once()
            if not self.pending_count():
                return


def reconcile_admissions(
    ledger: MutationLedger, *, data_root: Path | None = None
) -> int:
    """P69-02.2h: the only path that clears an admission row this process does
    not own, and the retry mechanism for a same-process terminalization that
    failed on its own. Returns how many rows it reconciled.

    Two distinct checks per row, in order:

    1. A durably-registered pending outcome (whether or not the owner is
       alive) is retried using that recorded outcome -- bookkeeping only, the
       operation's work is never re-executed.
    2. An owner established dead by the kernel-held owner-liveness lock has
       its row reconciled from the row's own recorded identity and written as
       a real terminal outcome, which frees the admission row as a side
       effect of the same transaction.

    A live owner's row is never touched -- a live request that conflicts with
    a dead owner's row still receives the ordinary structured conflict and
    never attempts a takeover itself.
    """
    reconciled = 0
    for row in ledger.list_admissions():
        slot_id = row["slot_id"]
        pending = ledger.pending_outcome(slot_id)
        if pending is not None:
            try:
                ledger.terminalize_and_release(
                    slot_id,
                    operation_id=pending["operation_id"] or row["operation_id"],
                    payload=pending["payload"],
                )
            except Exception:  # noqa: BLE001,S112 -- a row that cannot be
                # reconciled this pass is left exactly as it was for the next
                # sweep; one bad row never aborts the whole sweep.
                continue
            reconciled += 1
            continue
        owner_instance_id = row["owner_instance_id"]
        if not owner_instance_id:
            continue
        with claim_dead_owner(owner_instance_id, data_root=data_root) as claimed:
            if not claimed:
                continue
            try:
                ledger.terminalize_and_release(
                    slot_id,
                    operation_id=row["operation_id"],
                    payload={
                        "status": "interrupted",
                        "code": "owner_died",
                        "execution_identity": row["execution_identity"],
                        "run_id": row["run_id"],
                        "plan_id": row["plan_id"],
                    },
                )
            except Exception:  # noqa: BLE001,S112 -- as above: leave the
                # row intact and let the next sweep retry it.
                continue
            reconciled += 1
    return reconciled
