"""Pure in-memory thread-safe state store for ephemeral dashboard."""

from __future__ import annotations

import base64
import copy
import dataclasses
import hashlib
import json
import os
import sqlite3
import sys
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.platform != "win32":
    import fcntl

from rush.sqlite_util import ClosingConnection
from rush.tools.base import ToolResult


def genesis_identity(project_id: str) -> str:
    """S08: the shared scalar identity a never-scanned project carries before
    its first real publication -- a pure function of `project_id` alone, so
    every server hydrates the identical value with nothing durable to read.
    Never equal to a real scanned `source_identity` (a content-derived
    value), so a genesis project can't be mistaken for an already-scanned
    one with a colliding identity."""
    return hashlib.sha256(
        json.dumps(
            {"kind": "unscanned", "project_id": project_id, "generation": 0},
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _project_mutation_lock_path(
    project_id: str, *, data_root: Path | None = None
) -> Path:
    """S08 bullet 1: `<data_root>/dashboard/project_locks/<sha256(project_id)>.lock`
    -- hashed like `_windows_mutex_name` below so an arbitrary project_id is
    always a filesystem-safe name."""
    if data_root is None:
        from rush.setup.provision import default_data_root

        data_root = default_data_root()
    locks_dir = data_root / "dashboard" / "project_locks"
    locks_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(project_id.encode("utf-8")).hexdigest()
    return locks_dir / f"{digest}.lock"


_cross_process_lock_depth = threading.local()


@contextmanager
def cross_process_project_lock(
    project_id: str, *, data_root: Path | None = None
) -> Iterator[None]:
    """S08 bullet 1: blocking cross-process mutual exclusion for one
    project's check-then-act mutation window (`_handle_action`'s
    `_check_expected_identity` through its gated effect, `configure`'s
    apply path in `rush.tools.project`). A second dashboard server process
    racing the same project blocks here instead of both passing the same
    now-stale `expected` comparison -- POSIX `flock()` associates the lock
    with the open file description, not the process, so two threads in
    this same process opening independent file descriptors to the same
    path also correctly contend with each other, not just two separate
    processes.

    Reentrant *within one thread* (a thread-local depth counter, checked
    before ever calling the OS primitive): `_handle_action` already holds
    this lock for the whole dispatch window before `configure`'s dispatch
    reaches `rush.tools.project`'s own acquisition of this same lock --
    without this, that inner acquisition would self-deadlock (flock's
    per-open-file-description exclusivity does not exempt the thread that
    already holds a *different* file descriptor to the same path). A
    second, genuinely different thread or process still blocks normally.

    Blocking (no `LOCK_NB`), unlike `claim_dead_owner`'s non-blocking
    best-effort claim above: this primitive is a real mutex a caller must
    wait for, never one it silently skips."""
    held = getattr(_cross_process_lock_depth, "held", None)
    if held is None:
        held = {}
        _cross_process_lock_depth.held = held
    if held.get(project_id, 0) > 0:
        held[project_id] += 1
        try:
            yield
        finally:
            held[project_id] -= 1
        return
    held[project_id] = 1
    try:
        with _acquire_cross_process_project_lock(project_id, data_root=data_root):
            yield
    finally:
        held[project_id] = 0


@contextmanager
def _acquire_cross_process_project_lock(
    project_id: str, *, data_root: Path | None = None
) -> Iterator[None]:
    """The real OS-level acquisition `cross_process_project_lock` above
    calls exactly once per outermost entry on a given thread."""
    if sys.platform == "win32":  # pragma: no cover -- Windows-only; no
        # runner reachable in this environment. Mirrors `OwnerLock`'s
        # blocking-wait mutex pattern above, just with an infinite timeout
        # instead of a park/release thread (no lifetime-of-process hold).
        import ctypes

        name = _windows_mutex_name(f"project-mutation:{project_id}")
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        handle = kernel32.CreateMutexW(None, False, name)
        if not handle:
            raise OSError(f"CreateMutexW failed for {name!r}")
        _INFINITE = 0xFFFFFFFF
        kernel32.WaitForSingleObject(handle, _INFINITE)
        try:
            yield
        finally:
            kernel32.ReleaseMutex(handle)
            kernel32.CloseHandle(handle)
        return
    path = _project_mutation_lock_path(project_id, data_root=data_root)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _windows_mutex_name(owner_instance_id: str) -> str:
    """S03: deterministic per-owner Windows named-mutex identity. Hashed
    rather than embedding the raw id directly, so an arbitrary
    `owner_instance_id` (e.g. `tui:<uuid>`) always produces a short,
    kernel-object-namespace-safe name. Pure string derivation -- the one
    piece of the Windows lifetime-lock path testable without a Windows
    runner."""
    digest = hashlib.sha256(owner_instance_id.encode("utf-8")).hexdigest()
    return f"Local\\RushOwner-{digest}"


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


@dataclass(frozen=True)
class ProjectRecord:
    """M01: immutable publication -- every field is set once at construction;
    a state change (`bump_sequence`/`refresh_memories`/`publish_scan_result`)
    replaces this whole object under `ProjectRegistry._lock` rather than
    mutating attributes or the `snapshot` dict in place, so a reader holding
    an already-returned record (or its `snapshot`) never observes a later
    mutation underneath it."""

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

    def __init__(
        self, projects: dict[str, dict[str, Any]], *, data_root: Path | None = None
    ) -> None:
        self._lock = threading.Lock()
        self._mutation_locks: dict[str, threading.Lock] = {}
        self._data_root = data_root
        self._projects: dict[str, ProjectRecord] = {
            project_id: ProjectRecord(
                project_id=project_id,
                source_identity=body.get("source_identity", project_id),
                snapshot=copy.deepcopy(body),
            )
            for project_id, body in projects.items()
        }

    @staticmethod
    def _detached(record: ProjectRecord) -> ProjectRecord:
        """M01: a caller-owned copy -- mutating the returned record's
        `snapshot` (or replacing an attribute via `dataclasses.replace`) never
        reaches back into this registry's own stored object, and a later
        internal update never mutates bytes this copy already handed out."""
        return dataclasses.replace(record, snapshot=copy.deepcopy(record.snapshot))

    def get(self, project_id: str) -> ProjectRecord | None:
        with self._lock:
            record = self._projects.get(project_id)
            return None if record is None else self._detached(record)

    def get_published(self, project_id: str) -> ProjectRecord | None:
        """The stored record itself, never copied -- for read-only callers
        only (the map path). Safe under M01: a state change replaces the
        stored record and its `snapshot` wholesale, so this object never
        changes underneath its reader. Mutating it would corrupt the
        registry; use `get()` for a caller-owned copy."""
        with self._lock:
            return self._projects.get(project_id)

    @contextmanager
    def mutation_lock(self, project_id: str) -> Iterator[None]:
        """S08 bullet 1: exclusion for one project's check-then-act window
        between an `expected` comparison and the effect it gates -- never
        nested with any other per-project/per-run lock. Holds this
        process's in-memory `threading.Lock` (fast-path ordering among this
        server's own threads) around `cross_process_project_lock` (a real
        cross-process `flock()`, so a second dashboard server process
        racing the same project also blocks here rather than both passing
        a now-stale `expected` comparison)."""
        with self._lock:
            lock = self._mutation_locks.get(project_id)
            if lock is None:
                lock = threading.Lock()
                self._mutation_locks[project_id] = lock
        with lock, cross_process_project_lock(project_id, data_root=self._data_root):
            yield

    def register(self, project_id: str, snapshot: dict[str, Any]) -> ProjectRecord:
        """Insert a newly added/created project's snapshot (P66-02: real
        `rush_project add|create` dispatch, never a UI-only registration).
        Idempotent: registering the same project_id again returns the
        existing record unchanged rather than resetting its sequence."""
        with self._lock:
            existing = self._projects.get(project_id)
            if existing is not None:
                return self._detached(existing)
            record = ProjectRecord(
                project_id=project_id,
                source_identity=snapshot.get("source_identity", project_id),
                snapshot=copy.deepcopy(snapshot),
            )
            self._projects[project_id] = record
            return self._detached(record)

    def list_page(
        self, *, cursor: str | None, limit: int
    ) -> tuple[list[ProjectRecord], str | None]:
        """Paginate this server's currently-registered projects in stable
        insertion order. Cursor is an opaque offset -- this list is already
        behind session auth and is never the durable multi-session registry
        `list_projects_page` (Phase 65) signs with an HMAC key."""
        with self._lock:
            items = [self._detached(record) for record in self._projects.values()]
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
                new_sequence = record.sequence + 1
                new_snapshot = {**record.snapshot, "sequence": new_sequence}
                self._projects[project_id] = dataclasses.replace(
                    record, sequence=new_sequence, snapshot=new_snapshot
                )

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
            new_sequence = record.sequence + 1
            new_snapshot = {
                **record.snapshot,
                "memories": memories,
                "sequence": new_sequence,
            }
            self._projects[project_id] = dataclasses.replace(
                record,
                snapshot=new_snapshot,
                memory_generation=generation,
                sequence=new_sequence,
            )
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
            # M01 bullet 2 / bullet 4 regression: `snapshot` (built by the
            # caller before this lock was ever acquired, e.g.
            # `_publish_scan_snapshot`) must never carry the scan's own stale
            # pre-lock read of `memories`/`agents` into the published record --
            # a concurrent `refresh_memories` that committed newer data while
            # this scan was still adapting its result would otherwise be lost
            # the instant this whole-dict replacement lands. Only this
            # lock-current record's own memories/agents (whatever the most
            # recent `refresh_memories` under this same lock actually
            # committed) are authoritative; scan-owned fields come from the
            # caller's `snapshot`.
            merged = {
                **copy.deepcopy(snapshot),
                "memories": list(record.snapshot.get("memories") or []),
                "agents": list(record.snapshot.get("agents") or []),
            }
            new_sequence = record.sequence + 1
            merged["sequence"] = new_sequence
            merged["source_identity"] = source_identity
            self._projects[project_id] = dataclasses.replace(
                record,
                snapshot=merged,
                source_identity=source_identity,
                sequence=new_sequence,
                scan_generation=(
                    generation if generation is not None else record.scan_generation
                ),
            )
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
    # S09: the admitted executor's own preallocated attempt id -- for an
    # attach/conflict this is the *active* row's attempt, never the losing
    # request's own minted (and possibly never-executed) attempt.
    attempt_id: str = ""


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
        conn = sqlite3.connect(
            str(self._db_path), timeout=10.0, factory=ClosingConnection
        )
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
                    run_id TEXT NOT NULL DEFAULT '',
                    attempt_id TEXT NOT NULL DEFAULT '',
                    attempt_sequence INTEGER NOT NULL DEFAULT 0,
                    event_kind TEXT NOT NULL DEFAULT 'transition',
                    candidate_id TEXT NOT NULL DEFAULT '',
                    outcome TEXT NOT NULL DEFAULT '',
                    stream TEXT NOT NULL DEFAULT 'operation',
                    transition_ordinal INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (project_id, sequence)
                );
                CREATE TABLE IF NOT EXISTS event_cursor_floor (
                    project_id TEXT PRIMARY KEY,
                    floor INTEGER NOT NULL DEFAULT 0
                );
                """
            )
            conn.commit()
            self._migrate_reservation_and_admission_columns(conn)

    def _migrate_reservation_and_admission_columns(
        self, conn: sqlite3.Connection
    ) -> None:
        """S04/S09: additive migration for two brand-new-since-P69-06
        columns on each table, added under one `BEGIN IMMEDIATE` so two
        server processes starting against the same pre-existing database
        file at once serialize on this transaction rather than both racing
        the same `ALTER TABLE` (SQLite's own busy-timeout, already set on
        this connection, is what makes the loser simply wait its turn
        instead of erroring)."""
        conn.execute("BEGIN IMMEDIATE")
        try:
            ledger_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(mutation_ledger)")
            }
            if "validated_arguments" not in ledger_columns:
                conn.execute(
                    "ALTER TABLE mutation_ledger ADD COLUMN "
                    "validated_arguments TEXT NOT NULL DEFAULT '{}'"
                )
            if "effect_ids" not in ledger_columns:
                conn.execute(
                    "ALTER TABLE mutation_ledger ADD COLUMN "
                    "effect_ids TEXT NOT NULL DEFAULT '{}'"
                )
            if "recovery_schema_version" not in ledger_columns:
                conn.execute(
                    "ALTER TABLE mutation_ledger ADD COLUMN "
                    "recovery_schema_version INTEGER NOT NULL DEFAULT 0"
                )
            admission_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(scan_admission)")
            }
            if "attempt_id" not in admission_columns:
                conn.execute(
                    "ALTER TABLE scan_admission ADD COLUMN "
                    "attempt_id TEXT NOT NULL DEFAULT ''"
                )
            # M04 bullet 3: `run_id` on every durable event row, so retention
            # can prune per `(project_id, run_id)` rather than per project
            # globally -- a non-scan operation's events (empty `run_id`)
            # keep their own separate allowance, never sharing a scan run's
            # 2,000-row budget.
            event_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(dashboard_events)")
            }
            if "run_id" not in event_columns:
                conn.execute(
                    "ALTER TABLE dashboard_events ADD COLUMN "
                    "run_id TEXT NOT NULL DEFAULT ''"
                )
            # M04 bullets 1-2: durable event identity (attempt/attempt-local
            # sequence/event-kind/candidate/outcome/stream) for real
            # candidate-progress rows ingested from an attempt's own
            # `events.json` (`ingest_attempt_events` below), alongside the
            # existing status-transition rows.
            for column, ddl in (
                ("attempt_id", "attempt_id TEXT NOT NULL DEFAULT ''"),
                ("attempt_sequence", "attempt_sequence INTEGER NOT NULL DEFAULT 0"),
                ("event_kind", "event_kind TEXT NOT NULL DEFAULT 'transition'"),
                ("candidate_id", "candidate_id TEXT NOT NULL DEFAULT ''"),
                ("outcome", "outcome TEXT NOT NULL DEFAULT ''"),
                ("stream", "stream TEXT NOT NULL DEFAULT 'operation'"),
                (
                    "transition_ordinal",
                    "transition_ordinal INTEGER NOT NULL DEFAULT 0",
                ),
            ):
                if column not in event_columns:
                    conn.execute(f"ALTER TABLE dashboard_events ADD COLUMN {ddl}")
            conn.commit()
        except BaseException:
            conn.rollback()
            raise

    def reserve(
        self,
        project_id: str,
        request_id: str,
        body_hash: str,
        *,
        operation_type: str = "",
        validated_arguments: dict[str, Any] | None = None,
        effect_ids: dict[str, Any] | None = None,
    ) -> _Reservation:
        """Preallocate an effect-id for (project_id, request_id) before any
        builder() runs (subsection e). Returns whichever of new-reservation /
        cached-replay / in-flight / conflict applies, decided by one
        transactional insert-or-detect against the durable table.

        S04: `validated_arguments`/`effect_ids` are optional -- a caller that
        already validated/canonicalized its arguments and preallocated its
        effect keys persists them here, in the same transaction as the
        reservation itself, so a later crash can recover from persisted data
        alone (`get_reservation`) rather than replaying `body_hash`."""
        operation_id = uuid.uuid4().hex
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "INSERT INTO mutation_ledger "
                    "(project_id, request_id, operation_id, operation_type, "
                    "body_hash, status, created_at, validated_arguments, "
                    "effect_ids, recovery_schema_version) "
                    "VALUES (?,?,?,?,?,?,?,?,?,1)",
                    (
                        project_id,
                        request_id,
                        operation_id,
                        operation_type,
                        body_hash,
                        "pending",
                        time.time(),
                        json.dumps(validated_arguments or {}, sort_keys=True),
                        json.dumps(effect_ids or {}, sort_keys=True),
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
        validated_arguments: dict[str, Any] | None = None,
        effect_ids: dict[str, Any] | None = None,
    ) -> tuple[tuple[int, bytes], bool]:
        """Return ((status_code, response_body), is_conflict) for a mutation
        request_id. `builder` receives the preallocated operation_id (empty
        string for a non-mutating call, which never reserves)."""
        if not mutating:
            return builder(""), False
        reservation = self.reserve(
            project_id,
            request_id,
            body_hash,
            operation_type=operation_type,
            validated_arguments=validated_arguments,
            effect_ids=effect_ids,
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

    def _prune_run_events(
        self, conn: sqlite3.Connection, project_id: str, run_id: str
    ) -> None:
        """M04 bullet 3: prune independently by `(project_id, run_id)` to
        `_EVENT_RETENTION_PER_PROJECT` rows -- a run with heavy event volume
        never evicts another run's (or a non-scan operation's, `run_id=''`)
        own separate allowance. Also updates this project's persisted
        `event_cursor_floor` to the greatest sequence ever deleted by any
        run, so `list_events` can reject a stale cursor even when a
        *different* run's surviving rows happen to have a lower sequence
        (never comparing a project cursor against one arbitrary run's own
        floor)."""
        run_sequences = [
            int(r["sequence"])
            for r in conn.execute(
                "SELECT sequence FROM dashboard_events "
                "WHERE project_id = ? AND run_id = ? ORDER BY sequence DESC "
                "LIMIT 1 OFFSET ?",
                (project_id, run_id, _EVENT_RETENTION_PER_PROJECT - 1),
            )
        ]
        if not run_sequences:
            return
        # `run_sequences[0]` is the oldest sequence to *keep* (rank
        # `_EVENT_RETENTION_PER_PROJECT` from the newest) -- strictly-less-
        # than, never `<=`, or this would delete that row too and retain
        # only N-1.
        deleted_max = conn.execute(
            "SELECT MAX(sequence) FROM dashboard_events "
            "WHERE project_id = ? AND run_id = ? AND sequence < ?",
            (project_id, run_id, run_sequences[0]),
        ).fetchone()[0]
        conn.execute(
            "DELETE FROM dashboard_events "
            "WHERE project_id = ? AND run_id = ? AND sequence < ?",
            (project_id, run_id, run_sequences[0]),
        )
        if deleted_max is not None:
            conn.execute(
                "INSERT INTO event_cursor_floor (project_id, floor) VALUES (?, ?) "
                "ON CONFLICT(project_id) DO UPDATE SET "
                "floor = MAX(floor, excluded.floor)",
                (project_id, int(deleted_max)),
            )

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
                "SELECT ml.project_id AS project_id, sa.run_id AS run_id, "
                "sa.attempt_id AS attempt_id "
                "FROM mutation_ledger ml "
                "LEFT JOIN scan_admission sa ON sa.operation_id = ml.operation_id "
                "WHERE ml.operation_id = ?",
                (operation_id,),
            ).fetchone()
            if row is not None:
                project_id = row["project_id"]
                # M04 bullet 1: scan lifecycle transitions carry the
                # admitted run/attempt explicitly on the immutable event row
                # itself, so correlation survives the admission slot's own
                # later release (`scan_admission` is deleted on completion).
                event_run_id = row["run_id"] or ""
                event_attempt_id = row["attempt_id"] or ""
                seq_row = conn.execute(
                    "INSERT INTO event_sequences (project_id, value) VALUES (?, 1) "
                    "ON CONFLICT(project_id) DO UPDATE SET value = value + 1 "
                    "RETURNING value",
                    (project_id,),
                ).fetchone()
                sequence = int(seq_row["value"])
                # `(project_id, operation_id, transition_ordinal)` is this
                # row's own dedupe key -- distinct from candidate events'
                # `(project_id, run_id, attempt_id, attempt_sequence)`.
                ordinal_row = conn.execute(
                    "SELECT COUNT(*) AS c FROM dashboard_events "
                    "WHERE project_id = ? AND operation_id = ?",
                    (project_id, operation_id),
                ).fetchone()
                transition_ordinal = int(ordinal_row["c"]) + 1
                conn.execute(
                    "INSERT INTO dashboard_events "
                    "(project_id, sequence, operation_id, status, payload, "
                    "created_at, run_id, attempt_id, event_kind, stream, "
                    "transition_ordinal) "
                    "VALUES (?,?,?,?,?,?,?,?,'transition',?,?)",
                    (
                        project_id,
                        sequence,
                        operation_id,
                        status,
                        json.dumps(payload),
                        time.time(),
                        event_run_id,
                        event_attempt_id,
                        "scan" if event_run_id else "operation",
                        transition_ordinal,
                    ),
                )
                self._prune_run_events(conn, project_id, event_run_id)
            conn.commit()

    def ingest_attempt_events(
        self,
        project_id: str,
        run_id: str,
        attempt_id: str,
        events: list[dict[str, Any]],
    ) -> int:
        """M04 bullets 1-2: ingest real per-candidate progress events already
        durable in the attempt's own `events.json`
        (`workflows/project_run.py`'s `_append_event`/`load_scan_events` --
        the existing event sink) into this project's `/events` stream.
        Dedupes on `(project_id, run_id, attempt_id, attempt_sequence)` so
        re-ingesting the same attempt after a restart, or a scan-completion
        catch-up racing a mid-scan poll, never double-counts. Returns the
        number of genuinely new rows ingested."""
        ingested = 0
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                for event in events:
                    attempt_sequence = int(event.get("sequence", 0))
                    existing = conn.execute(
                        "SELECT 1 FROM dashboard_events WHERE project_id = ? "
                        "AND run_id = ? AND attempt_id = ? AND attempt_sequence = ? "
                        "AND event_kind = 'candidate'",
                        (project_id, run_id, attempt_id, attempt_sequence),
                    ).fetchone()
                    if existing is not None:
                        continue
                    seq_row = conn.execute(
                        "INSERT INTO event_sequences (project_id, value) VALUES (?, 1) "
                        "ON CONFLICT(project_id) DO UPDATE SET value = value + 1 "
                        "RETURNING value",
                        (project_id,),
                    ).fetchone()
                    sequence = int(seq_row["value"])
                    conn.execute(
                        "INSERT INTO dashboard_events "
                        "(project_id, sequence, operation_id, status, payload, "
                        "created_at, run_id, attempt_id, attempt_sequence, "
                        "event_kind, candidate_id, outcome, stream) "
                        "VALUES (?,?,?,?,?,?,?,?,?,'candidate',?,?,'scan')",
                        (
                            project_id,
                            sequence,
                            "",
                            str(event.get("event", "")),
                            json.dumps(event),
                            time.time(),
                            run_id,
                            attempt_id,
                            attempt_sequence,
                            str(event.get("candidate_id") or ""),
                            str(event.get("outcome") or ""),
                        ),
                    )
                    ingested += 1
                self._prune_run_events(conn, project_id, run_id)
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
        return ingested

    def list_events(
        self, project_id: str, *, after: int, limit: int = _EVENT_PAGE_LIMIT
    ) -> tuple[list[dict[str, Any]], int, bool] | None:
        """P69-03p: durable read path over `dashboard_events` (written by
        `record_status_transition`/`ingest_attempt_events` above). Returns
        `None` when `after` falls below this project's persisted
        `event_cursor_floor` (M04 bullet 3: the greatest sequence ever
        deleted by any run's own retention -- never derived from the
        current MIN surviving sequence, which another run's independent
        retention window could leave inconsistent) -- the caller turns that
        into `409 event_cursor_expired` with a snapshot-reload instruction,
        never silently resetting to the oldest available event. Otherwise
        returns `(events, next_after, has_more)`, capped at
        `_EVENT_PAGE_LIMIT` per page regardless of the requested `limit`."""
        limit = max(1, min(limit, _EVENT_PAGE_LIMIT))
        with self._connect() as conn:
            floor_row = conn.execute(
                "SELECT floor FROM event_cursor_floor WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            floor = int(floor_row[0]) if floor_row is not None else 0
            if after < floor:
                return None
            rows = conn.execute(
                "SELECT sequence, operation_id, status, payload, created_at, "
                "run_id, attempt_id, event_kind, candidate_id, outcome "
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
                "run_id": row["run_id"],
                "attempt_id": row["attempt_id"],
                "event_kind": row["event_kind"],
                "candidate_id": row["candidate_id"],
                "outcome": row["outcome"],
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

    def get_reservation(self, operation_id: str) -> dict[str, Any] | None:
        """S04 recovery primitive: the persisted reservation data for
        `operation_id`, or `None` if unknown. `recovery_schema_version == 0`
        means a legacy pre-S04 row with no reconstructable
        `validated_arguments`/`effect_ids` -- callers must treat it as
        recovery-required, never replay `body_hash` to reinvent them."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT operation_id, body_hash, validated_arguments, effect_ids, "
                "recovery_schema_version FROM mutation_ledger WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "operation_id": row["operation_id"],
            "body_hash": row["body_hash"],
            "validated_arguments": json.loads(row["validated_arguments"] or "{}"),
            "effect_ids": json.loads(row["effect_ids"] or "{}"),
            "recovery_schema_version": int(row["recovery_schema_version"]),
            "recovery_required": int(row["recovery_schema_version"]) < 1,
        }

    def list_reservations_for_project(self, project_id: str) -> list[dict[str, Any]]:
        """T052/S05: every reservation ever made for `project_id` -- the
        `handoff_send` receipt-leak recovery scan's own enumeration
        primitive. `handoff_send` never calls `admit()` (no `scan_admission`
        row, and this table has no `owner_instance_id` column at all), so
        there is no owner- or admission-scoped way to find its reservations;
        callers own scoping this safely themselves (a held
        `cross_process_project_lock` for this exact project before touching
        anything returned here)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT operation_id, effect_ids, recovery_schema_version "
                "FROM mutation_ledger WHERE project_id = ?",
                (project_id,),
            ).fetchall()
        return [
            {
                "operation_id": row["operation_id"],
                "effect_ids": json.loads(row["effect_ids"] or "{}"),
                "recovery_schema_version": int(row["recovery_schema_version"]),
            }
            for row in rows
        ]

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
        attempt_id: str = "",
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
            attempt_id,
        )
        insert = (
            "INSERT INTO scan_admission (project_id, execution_identity, slot_id, "
            "operation_id, owner_instance_id, run_id, plan_id, created_at, "
            "attempt_id) VALUES (?,?,?,?,?,?,?,?,?)"
        )
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                try:
                    conn.execute(insert, columns)
                except sqlite3.IntegrityError:
                    row = conn.execute(
                        "SELECT execution_identity, slot_id, operation_id, "
                        "owner_instance_id, run_id, plan_id, attempt_id "
                        "FROM scan_admission WHERE project_id = ?",
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
                            attempt_id=row["attempt_id"],
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
                            # S09: the admitted executor's own preallocated
                            # attempt, read from the active row -- never the
                            # losing (attaching) request's own minted value.
                            attempt_id=row["attempt_id"],
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
            attempt_id=attempt_id,
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
                "owner_instance_id, run_id, plan_id, attempt_id FROM scan_admission "
                "WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def list_admissions(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT project_id, execution_identity, slot_id, operation_id, "
                "owner_instance_id, run_id, plan_id, attempt_id FROM scan_admission"
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

    POSIX (`fcntl.flock`) or, on Windows (S03), a session-local named mutex
    (`Local\\RushOwner-<sha256(owner_instance_id)>`) held by a dedicated
    coordinator thread for the same never-explicitly-released lifetime --
    WinAPI mutex release is thread-affine, so the thread that waits on it
    must be the one that (eventually) releases it.
    """

    def __init__(
        self, owner_instance_id: str, *, data_root: Path | None = None
    ) -> None:
        self.owner_instance_id = owner_instance_id
        if sys.platform == "win32":  # pragma: no cover -- Windows-only; no
            # runner reachable in this environment. See S03's own named
            # tests: implemented per spec, unverified on real Windows.
            self.path = None
            self._fd = None
            self._acquire_windows_mutex()
            return
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

    def _acquire_windows_mutex(self) -> None:  # pragma: no cover -- Windows-
        # only; no runner reachable in this environment.
        """`CreateMutexW` + zero-timeout `WaitForSingleObject` on a
        dedicated daemon thread that parks (never released by this class)
        until process exit, exactly mirroring the POSIX flock contract
        above. `WAIT_TIMEOUT` means another owner holds the mutex;
        `WAIT_OBJECT_0`/`WAIT_ABANDONED` gives this thread ownership."""
        import ctypes

        name = _windows_mutex_name(self.owner_instance_id)
        acquired = threading.Event()
        park = threading.Event()
        failure: list[OwnerLockError] = []

        def _hold() -> None:
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            kernel32.CreateMutexW.restype = ctypes.c_void_p
            handle = kernel32.CreateMutexW(None, False, name)
            if not handle:
                failure.append(OwnerLockError(f"CreateMutexW failed for {name!r}"))
                acquired.set()
                return
            _WAIT_TIMEOUT = 0x00000102
            wait_result = kernel32.WaitForSingleObject(handle, 0)
            if wait_result == _WAIT_TIMEOUT:
                kernel32.CloseHandle(handle)
                failure.append(
                    OwnerLockError(
                        f"owner-liveness lock already held for "
                        f"{self.owner_instance_id!r}"
                    )
                )
                acquired.set()
                return
            self._windows_mutex_handle = handle
            acquired.set()
            park.wait()
            kernel32.ReleaseMutex(handle)
            kernel32.CloseHandle(handle)

        thread = threading.Thread(target=_hold, daemon=True, name="rush-owner-mutex")
        thread.start()
        acquired.wait()
        if failure:
            raise failure[0]
        self._windows_thread = thread
        self._windows_park = park


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
    if sys.platform == "win32":  # pragma: no cover -- Windows-only; no
        # runner reachable in this environment. See S03's own named tests.
        import ctypes

        name = _windows_mutex_name(owner_instance_id)
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        handle = kernel32.CreateMutexW(None, False, name)
        if not handle:
            yield False
            return
        _WAIT_TIMEOUT = 0x00000102
        wait_result = kernel32.WaitForSingleObject(handle, 0)
        if wait_result == _WAIT_TIMEOUT:
            kernel32.CloseHandle(handle)
            yield False
            return
        try:
            yield True
        finally:
            kernel32.ReleaseMutex(handle)
            kernel32.CloseHandle(handle)
        return
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


def observe_owner(owner_instance_id: str, data_root: Path) -> str:
    """T23: `alive`, `dead` or `activity_unverified` for a recorded owner,
    observed without claiming or recovering it. Unlike `claim_dead_owner`,
    it only opens an existing lock (never `mkdir`, never `O_CREAT`); a
    missing lock is `activity_unverified`, never `alive`."""
    if (
        not owner_instance_id
        or os.sep in owner_instance_id
        or (os.altsep and os.altsep in owner_instance_id)
    ):
        return "activity_unverified"
    if sys.platform == "win32":  # pragma: no cover -- Windows-only; no
        # runner reachable in this environment.
        return _observe_owner_windows(owner_instance_id)
    path = data_root / "owners" / f"{owner_instance_id}.lock"
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return "activity_unverified"
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return "alive"
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return "dead"
    finally:
        os.close(fd)


def _observe_owner_windows(owner_instance_id: str) -> str:  # pragma: no cover
    """`OpenMutexW` (never `CreateMutexW`): absent is `activity_unverified`,
    held is `alive`, acquirable (released or abandoned) is `dead`."""
    import ctypes

    synchronize, wait_timeout = 0x00100000, 0x00000102
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    kernel32.OpenMutexW.restype = ctypes.c_void_p
    handle = kernel32.OpenMutexW(
        synchronize, False, _windows_mutex_name(owner_instance_id)
    )
    if not handle:
        return "activity_unverified"
    try:
        if kernel32.WaitForSingleObject(handle, 0) == wait_timeout:
            return "alive"
        kernel32.ReleaseMutex(handle)
        return "dead"
    finally:
        kernel32.CloseHandle(handle)


_LEDGER_ADMISSION_COLUMNS = (
    "run_id",
    "attempt_id",
    "operation_id",
    "owner_instance_id",
    "plan_id",
)
_LEDGER_PUBLISHED_COLUMNS = (
    "published_generation",
    "latest_published_run_id",
    "latest_published_attempt_id",
)


def _ledger_row(
    conn: sqlite3.Connection, table: str, columns: tuple[str, ...], project_id: str
) -> dict[str, Any] | None:
    """One project's row, reading only the columns this schema has (an older
    ledger without `attempt_id` reports it as `None`); a missing table or row
    is no evidence (`None`)."""
    present = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    wanted = [c for c in columns if c in present]
    if not wanted:
        return None
    row = conn.execute(
        f"SELECT {', '.join(wanted)} FROM {table} WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    if row is None:
        return None
    values = dict(zip(wanted, row, strict=True))
    return {c: values.get(c) for c in columns}


def read_ledger_view(project_id: str, data_root: Path) -> dict[str, Any]:
    """T23: the project's current scan admission and published result, read
    through the shared zero-write SQLite opener -- never `MutationLedger`,
    whose constructor creates directories, the schema and WAL files.
    `project_generations.value` (the allocator) is never read.

    `state` is `absent` (no ledger), `ok`, `corrupt` or `busy`."""
    from rush.memory.store import MemoryStoreUnreadableError, read_sqlite_readonly

    def read(conn: sqlite3.Connection) -> dict[str, Any]:
        return {
            "admission": _ledger_row(
                conn, "scan_admission", _LEDGER_ADMISSION_COLUMNS, project_id
            ),
            "published": _ledger_row(
                conn, "project_generations", _LEDGER_PUBLISHED_COLUMNS, project_id
            ),
        }

    db = data_root / "dashboard" / "mutation_ledger.db"
    try:
        rows = read_sqlite_readonly(db, read)
    except MemoryStoreUnreadableError as exc:
        state = "corrupt" if exc.code == "E_STORE_CORRUPT" else "busy"
        return {"state": state, "admission": None, "published": None, "error": str(exc)}
    if rows is None:
        return {"state": "absent", "admission": None, "published": None, "error": None}
    return {"state": "ok", **rows, "error": None}


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
    ledger: MutationLedger,
    *,
    data_root: Path | None = None,
    recovering_owner_instance_id: str = "",
) -> int:
    """P69-02.2h/S02: the only path that clears an admission row this process
    does not own, and the retry mechanism for a same-process terminalization
    that failed on its own. Returns how many rows it reconciled.

    `recovering_owner_instance_id` is *this* recovering server's own owner
    identity -- required to tell "a durable pending outcome I already
    attempted and am now retrying as bookkeeping" from "a durable pending
    outcome belonging to some other owner", which alone is never permission
    to release that other owner's admission while its children may still be
    running.

    Two distinct checks per row, in order:

    1. A durably-registered pending outcome belonging to *this* live,
       recovering owner is retried using that recorded outcome -- bookkeeping
       only, the operation's work is never re-executed, and its children are
       never reaped (this owner is alive; S15/S01 own its process fencing).
    2. An owner established dead by the kernel-held owner-liveness lock is
       whole-owner reaped (S02) while the dead-owner claim is held. Only once
       that reap reports every recorded process group's termination
       confirmed (`reconcilable=True`) is the pending outcome/receipt reread
       and the row terminalized/released as a real terminal outcome. An
       unconfirmed reap leaves the admission and process records intact --
       recorded `recovery_required`/`termination_unconfirmed` for the next
       sweep to retry -- so a new executor can never enter while this dead
       owner's subprocess may still be mutating files.

    A live foreign owner's row is never touched -- a live request that
    conflicts with a dead owner's row still receives the ordinary structured
    conflict and never attempts a takeover itself.
    """
    reconciled = 0
    for row in ledger.list_admissions():
        slot_id = row["slot_id"]
        owner_instance_id = row["owner_instance_id"]
        pending = ledger.pending_outcome(slot_id)
        if (
            pending is not None
            and owner_instance_id
            and owner_instance_id == recovering_owner_instance_id
        ):
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
        if not owner_instance_id:
            continue
        with claim_dead_owner(owner_instance_id, data_root=data_root) as claimed:
            if not claimed:
                continue
            from rush.runtime.subprocesses import reap_owner_processes

            reap_result = reap_owner_processes(owner_instance_id, data_root=data_root)
            if not reap_result["reconcilable"]:
                # S02 item 3: unconfirmed termination -- preserve admission
                # and process records intact for the next recovery attempt;
                # never release while a child may still be mutating files.
                with suppress(Exception):
                    # row intact and let the next sweep retry it.
                    ledger.record_status_transition(
                        row["operation_id"],
                        "recovery_required",
                        {
                            "status": "recovery_required",
                            "code": "termination_unconfirmed",
                            "execution_identity": row["execution_identity"],
                            "run_id": row["run_id"],
                            "plan_id": row["plan_id"],
                        },
                    )
                continue
            # T038/S05: alongside this row's own scan-admission release, this
            # same confirmed-dead owner may also have crashed mid
            # `handoff_send` (prepare succeeded, dispatch never ran) --
            # recover any handoff it left `prepared` for this row's project.
            # Reuses S04's own reserved effect receipt ids from the ledger
            # (`get_reservation`) rather than minting new ones, so recovery
            # replays the exact receipts `build_handoff` already committed.
            from rush.memory.store import TypedArtifactStore
            from rush.workflows.project_run import (
                handoff_descriptor_exists_for_operation,
                list_prepared_handoffs,
                recover_prepared_handoff,
            )
            from rush.workflows.projects import resolve_project

            try:
                project_root = Path(
                    resolve_project(row["project_id"], data_root=data_root)["root"]
                )
            except Exception:  # noqa: BLE001 -- an unresolvable project
                # never blocks this row's own scan-admission reconciliation.
                project_root = None
            if project_root is not None:
                for handoff in list_prepared_handoffs(project_root, owner_instance_id):
                    reservation = ledger.get_reservation(handoff.operation_id)
                    if reservation is None or reservation["recovery_required"]:
                        continue
                    effect_ids = reservation["effect_ids"]
                    artifact_receipt_id = effect_ids.get("artifact_create")
                    session_receipt_id = effect_ids.get("session_create")
                    if not artifact_receipt_id or not session_receipt_id:
                        continue
                    recovered = None
                    with suppress(Exception):
                        recovered = recover_prepared_handoff(
                            row["project_id"],
                            handoff.handoff_id,
                            claimed_operation_id=handoff.operation_id,
                            artifact_create_receipt_id=artifact_receipt_id,
                            session_create_receipt_id=session_receipt_id,
                            delivery_receipt_id=effect_ids.get(
                                "delivery_transition", ""
                            ),
                            data_root=data_root,
                        )
                    if recovered is None:
                        # T045/S05 bullet 4: recovery itself already gave
                        # up (revoked the session, orphaned the artifact)
                        # or raised -- record the same recovery_required
                        # transition the sibling scan-admission row above
                        # uses, so this handoff's own operation surfaces
                        # for the next sweep/consumer instead of vanishing
                        # silently inside `suppress(Exception)`.
                        with suppress(Exception):
                            ledger.record_status_transition(
                                handoff.operation_id,
                                "recovery_required",
                                {
                                    "status": "recovery_required",
                                    "code": "handoff_recovery_failed",
                                    "handoff_id": handoff.handoff_id,
                                    "project_id": row["project_id"],
                                },
                            )

                # T052/S05: `build_handoff` commits its `artifact_create`/
                # `session_create` receipts *before* ever reaching
                # `_persist_handoff` (its own final statement) -- a crash in
                # that window leaves no descriptor file at all for the
                # `list_prepared_handoffs` loop above to glob, so its
                # committed receipts never surface there. `handoff_send`
                # never calls `admit()` (no `scan_admission` row, and
                # `mutation_ledger` has no `owner_instance_id` column at
                # all for it) -- the only way to find this leak is a
                # project-wide receipt scan, made safe by acquiring this
                # exact project's own real cross-process dispatch lock
                # first: `_dispatch_handoff_send` holds it for the *entire*
                # synchronous `build_handoff` call, so once acquired here no
                # live process can possibly be mid-effect for this project
                # -- any receipts-committed-no-descriptor reservation found
                # while holding it is unambiguously abandoned, never a live
                # owner's in-flight write.
                with cross_process_project_lock(row["project_id"], data_root=data_root):
                    for reservation in ledger.list_reservations_for_project(
                        row["project_id"]
                    ):
                        if reservation["recovery_schema_version"] < 1:
                            continue
                        effect_ids = reservation["effect_ids"]
                        artifact_receipt_id = effect_ids.get("artifact_create")
                        session_receipt_id = effect_ids.get("session_create")
                        # `memory_propose` also reserves a bare
                        # `artifact_create` key with no `session_create`
                        # sibling -- requiring both is what scopes this to a
                        # `handoff_send` reservation specifically.
                        if not artifact_receipt_id or not session_receipt_id:
                            continue
                        op_id = reservation["operation_id"]
                        if handoff_descriptor_exists_for_operation(project_root, op_id):
                            # Either the loop above already recovered it (a
                            # `prepared` descriptor for a dead owner), or it
                            # genuinely advanced past `prepared` -- never a
                            # leak either way.
                            continue
                        leak_store = TypedArtifactStore(project_root)
                        artifact_receipt = leak_store.get_receipt(artifact_receipt_id)
                        session_receipt = leak_store.get_receipt(session_receipt_id)
                        if artifact_receipt is None and session_receipt is None:
                            continue
                        with suppress(Exception):
                            if artifact_receipt is not None:
                                leak_store.mark_artifact_orphaned(
                                    artifact_receipt["artifact_id"]
                                )
                            if session_receipt is not None:
                                leak_store.revoke_handoff_session(
                                    session_receipt["artifact_id"]
                                )
                            ledger.record_status_transition(
                                op_id,
                                "recovery_required",
                                {
                                    "status": "recovery_required",
                                    "code": "handoff_leaked_before_descriptor",
                                    "project_id": row["project_id"],
                                },
                            )

            # Reap confirmed every recorded process group terminated -- safe
            # to reread pending outcome/effect receipts and release now,
            # still under the same held dead-owner claim.
            reread_pending = ledger.pending_outcome(slot_id)
            try:
                if reread_pending is not None:
                    ledger.terminalize_and_release(
                        slot_id,
                        operation_id=reread_pending["operation_id"]
                        or row["operation_id"],
                        payload=reread_pending["payload"],
                    )
                else:
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
