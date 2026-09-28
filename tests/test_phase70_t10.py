"""Phase 70 T10 test matrix: project state stays under the logical root, and
denied/read-only queries create nothing.

Binding design: .scratch/phase-70-design-gate/W2-T9-T17.md, section "## 0" and
"## T10". Plan packet: docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md,
"#### T10 -- Contain project state and preserve recovery".

Predecessors T8/T9 (logical-root discovery: git/worktree walk-up, no-marker
fallback, custom data root plumbing into an ambient invocation root) are not
implemented in this worktree. Cases whose RED depends solely on that missing
discovery are labelled RED-via-T8 in their docstring, but each still asserts
T10's own end-state promise exactly (state lands only under the intended
logical root, nothing elsewhere) using the real, currently-wired entry points
(CLI commands via CliRunner, SessionContinuityTool.run, FlightRecorder,
CCRStore, ResultCache, CheckpointJournal). None of this touches the real main
checkout or ~/rush-recovery; every filesystem operation below is scoped to
pytest tmp_path directories and a monkeypatched HOME.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from rush.invocation.executor import adapt_signature_at_registration
from rush.invocation.resolver import resolve_invocation
from rush.permissions import ExecutionPermissions
from rush.setup.provision import default_data_root
from rush.token_economy.ccr_store import CCRStore
from rush.tools.continuity import SessionContinuityTool
from rush.tools.flight_recorder import FlightRecorder
from rush.workflows import projects as projects_workflow


@pytest.fixture(autouse=True)
def temp_home(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Every test in this file gets its own temp HOME; no test may touch the
    real user data root."""
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("RUSH_DATA_ROOT", raising=False)
    # Linux's default data root honours XDG_DATA_HOME before HOME.
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    return home


def _snapshot(root: Path) -> set[str]:
    """Relative POSIX paths of every file under root, recursively."""
    if not root.exists():
        return set()
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def _git_dir_marker(root: Path) -> None:
    (root / ".git").mkdir()


def _git_file_marker(root: Path) -> None:
    # Real git worktree marker: a `.git` *file* (not directory) pointing at
    # the real gitdir. Content is irrelevant to any check under test.
    (root / ".git").write_text("gitdir: ../actual.git/worktrees/wt\n", encoding="utf-8")


class TestT10ProjectStateUsesLogicalRoot:
    """test_t10_project_state_uses_logical_root -- parametrized per S10.7."""

    def test_cli_session_save_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """cli-session-save-root: invoked from the root itself.

        Keep-green guard: root == cwd already today, so this must already pass.
        """
        _git_dir_marker(tmp_path)
        monkeypatch.chdir(tmp_path)
        before = _snapshot(tmp_path)

        from rush.cli import cli

        runner = CliRunner()
        result = runner.invoke(
            cli, ["session", "save", "n1", "--allow-cache-write", "--json"]
        )
        assert result.exit_code == 0, result.output

        assert (tmp_path / ".rush" / "sessions" / "n1.json").is_file()
        assert (tmp_path / ".rush" / "memory.db").is_file()
        after = _snapshot(tmp_path)
        new_files = after - before
        assert all(f.startswith(".rush/") for f in new_files), new_files

    def test_cli_session_save_nested_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """cli-session-save-nested-dir: invoked from root/src/pkg.

        RED-via-T8: today's `root = path.resolve()` never walks up to the
        `.git`-marked root, so state lands at the nested cwd instead of
        `tmp_path`. T10's own promise (state under the ONE logical root, and
        nowhere else) still fails today regardless of who supplies the root.
        """
        _git_dir_marker(tmp_path)
        nested = tmp_path / "src" / "pkg"
        nested.mkdir(parents=True)
        monkeypatch.chdir(nested)

        from rush.cli import cli

        runner = CliRunner()
        result = runner.invoke(
            cli, ["session", "save", "n2", "--allow-cache-write", "--json"]
        )
        assert result.exit_code == 0, result.output

        assert (tmp_path / ".rush" / "sessions" / "n2.json").is_file()
        assert not (nested / ".rush").exists()

    def test_cli_session_save_nested_file_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """cli-session-save-nested-file-dir: invoked from the directory
        holding a specific file being worked on, one level deeper than the
        `src/pkg` case above.

        RED-via-T8: same missing walk-up, distinct depth.
        """
        _git_dir_marker(tmp_path)
        nested = tmp_path / "src" / "pkg" / "sub"
        nested.mkdir(parents=True)
        (nested / "mod.py").write_text("x = 1\n", encoding="utf-8")
        monkeypatch.chdir(nested)

        from rush.cli import cli

        runner = CliRunner()
        result = runner.invoke(
            cli, ["session", "save", "n3", "--allow-cache-write", "--json"]
        )
        assert result.exit_code == 0, result.output

        assert (tmp_path / ".rush" / "sessions" / "n3.json").is_file()
        assert not (nested / ".rush").exists()

    def test_mcp_continuity_file_target(self, tmp_path: Path) -> None:
        """mcp-continuity-file-target (S10.2): `rush_continuity(path="src/x.py",
        operation="save", ...)` must write under the logical root, never under
        the file or its parent.

        RED: today `SessionContinuityTool.run` does `root = path.resolve()`
        (continuity.py), so a file path becomes the "root" and
        `CheckpointJournal(root).__init__` calls `root.mkdir(exist_ok=True)`
        on a path that is already a regular file -- this raises instead of
        writing state anywhere sane.
        """
        _git_dir_marker(tmp_path)
        src = tmp_path / "src"
        src.mkdir()
        target_file = src / "x.py"
        target_file.write_text("x = 1\n", encoding="utf-8")

        result = SessionContinuityTool().run(
            target_file,
            operation="save",
            name="n4",
            permissions=ExecutionPermissions(cache_write=True),
        )

        assert result["status"] == "ok", result
        assert (tmp_path / ".rush" / "sessions" / "n4.json").is_file()
        assert not (src / ".rush").exists()
        assert not target_file.is_dir()

    def test_mcp_declared_project(self, tmp_path: Path, temp_home: Path) -> None:
        """mcp-declared-project (S10.7): an explicit registered root
        (`project=<id>`) determines the write location, not whatever `path`
        happened to be passed.

        RED: `SessionContinuityTool.run` accepts `project_id` only for
        telemetry attribution -- it is never consulted to resolve `root`, so
        state lands wherever `path` points instead of the registered project.
        """
        project_root = tmp_path / "registered_project"
        project_root.mkdir()
        _git_dir_marker(project_root)
        record = projects_workflow.register_project(project_root)

        elsewhere = tmp_path / "unrelated_cwd"
        elsewhere.mkdir()

        result = SessionContinuityTool().run(
            elsewhere,
            operation="save",
            name="n5",
            project_id=record.project_id,
            permissions=ExecutionPermissions(cache_write=True),
        )

        assert result["status"] == "ok", result
        assert (project_root / ".rush" / "sessions" / "n5.json").is_file()
        assert not (elsewhere / ".rush" / "sessions" / "n5.json").exists()

    def test_worktree_dotgit_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """worktree-dotgit-file (S10.7): a `.git` *file* (real git worktree
        marker) roots discovery exactly like a `.git` directory does.

        RED-via-T8: no marker-walk exists today at all, `.git`-file or
        `.git`-dir alike.
        """
        _git_file_marker(tmp_path)
        nested = tmp_path / "src"
        nested.mkdir()
        monkeypatch.chdir(nested)

        from rush.cli import cli

        runner = CliRunner()
        result = runner.invoke(
            cli, ["session", "save", "n6", "--allow-cache-write", "--json"]
        )
        assert result.exit_code == 0, result.output

        assert (tmp_path / ".rush" / "sessions" / "n6.json").is_file()
        assert not (nested / ".rush").exists()

    def test_no_marker_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """no-marker-dir (S10.7): no `.git`/project marker anywhere upward;
        the fallback is the invoked directory itself.

        Keep-green guard: today's `path.resolve()` already equals that
        fallback for a directory invocation, with no marker to walk past.
        """
        nested = tmp_path / "plain" / "dir"
        nested.mkdir(parents=True)
        monkeypatch.chdir(nested)

        from rush.cli import cli

        runner = CliRunner()
        result = runner.invoke(
            cli, ["session", "save", "n7", "--allow-cache-write", "--json"]
        )
        assert result.exit_code == 0, result.output

        assert (nested / ".rush" / "sessions" / "n7.json").is_file()
        assert not (tmp_path / ".rush").exists()

    def test_custom_data_root(self, tmp_path: Path, temp_home: Path) -> None:
        """custom-data-root (S10.7): global project-registry state stays under
        the (here, HOME-derived) data root; project state stays under the
        logical root; neither leaks into the other.

        Keep-green guard: `register_project`/`default_data_root` already keep
        this separation today.
        """
        project_root = tmp_path / "proj"
        project_root.mkdir()
        record = projects_workflow.register_project(project_root)

        data_root = default_data_root()
        assert data_root.is_relative_to(temp_home)
        assert (data_root / "projects.json").is_file()
        assert record.root == str(project_root.resolve())
        assert not (project_root / "Library").exists()
        assert not (project_root / ".local").exists()

        result = SessionContinuityTool().run(
            project_root,
            operation="save",
            name="n8",
            permissions=ExecutionPermissions(cache_write=True),
        )
        assert result["status"] == "ok", result
        assert (project_root / ".rush" / "sessions" / "n8.json").is_file()
        assert not (data_root / ".rush").exists()

    def test_denied_save(self, tmp_path: Path) -> None:
        """denied-save (S10.3): without the grant, status is skipped and the
        tree is byte-for-byte identical before/after.

        Keep-green guard: `_run_save` already checks permissions before
        constructing `CheckpointJournal`.
        """
        before = _snapshot(tmp_path)
        result = SessionContinuityTool().run(tmp_path, operation="save", name="n9")
        assert result["status"] == "skipped", result
        assert not (tmp_path / ".rush").exists()
        assert _snapshot(tmp_path) == before

    def test_session_list_empty(self, tmp_path: Path) -> None:
        """session-list-empty (S10.4): `session list` on a project with no
        `.rush` creates nothing.

        Keep-green guard: `_run_list` already guards on `session_dir.exists()`
        before constructing `CheckpointJournal`.
        """
        before = _snapshot(tmp_path)
        result = SessionContinuityTool().run(tmp_path, operation="list")
        assert result["status"] == "ok", result
        assert not (tmp_path / ".rush").exists()
        assert _snapshot(tmp_path) == before

    def test_session_restore_missing(self, tmp_path: Path) -> None:
        """session-restore-missing (S10.4): `session restore` on a project
        with no `.rush` creates nothing.

        RED: `_run_restore` constructs `CheckpointJournal(root)`
        unconditionally, and `CheckpointJournal.__init__` unconditionally
        `mkdir`s `.rush/sessions` as a constructor side effect, even though
        nothing is found to restore.
        """
        before = _snapshot(tmp_path)
        result = SessionContinuityTool().run(
            tmp_path, operation="restore", name="ghost"
        )
        # Phase 70 T27 (R27.1): an unknown name is an error; still no writes.
        assert result["status"] == "error", result
        assert not (tmp_path / ".rush").exists()
        assert _snapshot(tmp_path) == before

    def test_flight_status(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """flight-status (S10.5): `rush flight-recorder` (status, no
        `--replay`) creates nothing.

        RED: `flight_recorder_cmd` constructs `FlightRecorder()` with its
        default `create=True`, which unconditionally `mkdir`s
        `.rush/sessions/flights` before ever checking whether a replay was
        requested.
        """
        monkeypatch.chdir(tmp_path)
        before = _snapshot(tmp_path)

        from rush.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["flight-recorder"])
        assert result.exit_code == 0, result.output
        assert not (tmp_path / ".rush").exists()
        assert _snapshot(tmp_path) == before

    def test_flight_replay_missing_db(self, tmp_path: Path) -> None:
        """flight-replay-missing-db (S10.5): replaying a session with no
        flight file and no prior memory record creates nothing.

        RED: `FlightRecorder.replay_session` falls back to
        `read_origin_kind_by_symbol`, which constructs a real (creating)
        `TypedArtifactStore(project_root)` -- `memory.db` is created purely
        to prove there is nothing in it.
        """
        recorder = FlightRecorder(tmp_path, create=False)
        before = _snapshot(tmp_path)
        events = recorder.replay_session("nonexistent-session")
        assert events == []
        assert not (tmp_path / ".rush").exists()
        assert _snapshot(tmp_path) == before

    def test_cache_stats_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """cache-stats-absent (S10.6): `rush cache stats` with no
        `.rush/cache.db` creates nothing and reports the absence with its
        path.

        RED: `cache_stats` constructs `ResultCache()`, whose `__init__`
        unconditionally calls `_init_db()`, which `mkdir`s `.rush/` and
        creates `cache.db` as a side effect of merely asking for stats.
        """
        monkeypatch.chdir(tmp_path)
        before = _snapshot(tmp_path)

        from rush.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["cache", "stats"])
        assert result.exit_code == 0, result.output
        assert "false" in result.output.lower() or "entries" in result.output
        assert not (tmp_path / ".rush" / "cache.db").exists()
        assert _snapshot(tmp_path) == before

    def test_cache_clean_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """cache-clean-absent (S10.6): `rush cache clean` with a missing DB
        prints "Purged 0"; clean is explicit and may create its (anchored)
        db as part of that real write.

        Keep-green guard: today's `clear()` already reports 0 on a fresh db.
        """
        monkeypatch.chdir(tmp_path)

        from rush.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["cache", "clean"])
        assert result.exit_code == 0, result.output
        assert "Purged 0" in result.output


def test_t10_ccr_store_lazy_init(tmp_path: Path) -> None:
    """ccr-store-lazy-init (design section 3.5): construction alone creates
    nothing; only `store_chunk` creates the db, and `retrieve_chunk(touch=False)`
    on a missing db returns None without creating anything.

    RED: `CCRStore.__init__` unconditionally calls `_init_db()`, which
    `mkdir`s `.rush/cache/` and creates `ccr.db` merely by constructing the
    object.
    """
    store = CCRStore(tmp_path)
    assert not (tmp_path / ".rush").exists()

    assert store.retrieve_chunk("deadbeef", touch=False) is None
    assert not (tmp_path / ".rush").exists()

    tag = store.store_chunk("hello world")
    assert tag.startswith("<!-- ccr:chunk:")
    assert (tmp_path / ".rush" / "cache" / "ccr.db").is_file()


def test_t10_mcp_continuity_files_bound(tmp_path: Path) -> None:
    """mcp-continuity-files-bound (R10.5, added 2026-09-26): MCP
    `rush_continuity(files=["a.py","b.py"], ...)` must reach a handler
    parameter literally named `files` bound to exactly those two contained
    targets; CLI and MCP must agree.

    RED: `files` is in `invocation.resolver.RESERVED_REQUEST_KEYS`, so
    `resolver._is_typed_argument_name("files", ...)` is False and `files`
    never appears in `context.typed_args`. `executor._resolve_context_val`
    has no special case for a handler parameter literally named `files`
    either, so `adapt_signature_at_registration`'s general adapter falls
    through to the parameter's default (`None`) instead of the two contained
    targets built from the request's `files` list.
    """
    (tmp_path / "a.py").write_text("a = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("b = 1\n", encoding="utf-8")

    context = resolve_invocation(
        {"operation_id": "continuity", "files": ["a.py", "b.py"]},
        transport="mcp",
        workspace_root=tmp_path,
    )

    def handler(files: list[str] | None = None) -> list[str] | None:
        return files

    adapter = adapt_signature_at_registration(handler, operation_id="continuity")
    args, kwargs = adapter(context)
    bound_files = handler(*args, **kwargs)

    assert bound_files is not None
    assert {Path(f).name for f in bound_files} == {"a.py", "b.py"}


# ---------------------------------------------------------------------------
# W2 adversarial review -- T10 amendments (findings 3, 4, 15, 26 and X1)
# ---------------------------------------------------------------------------


def _byte_snapshot(root: Path) -> dict[str, str]:
    """Relative POSIX path -> sha256 of every file under root, so
    "byte-identical" compares content, not only names."""
    import hashlib

    if not root.exists():
        return {}
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


def _close_writers() -> None:
    """Writers use `with sqlite3.connect(...)`, which commits but does not
    close; collect those connections so each WAL database is cleanly closed
    (checkpointed, `-wal`/`-shm` removed) before a read-only case runs."""
    import gc

    gc.collect()


def _sidecars(root: Path) -> list[str]:
    return sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.name.endswith(("-wal", "-shm", "-journal"))
    )


@pytest.fixture
def spawn_spy(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """Finding 26: count every child once, at `Popen.__init__` (which also
    catches `subprocess.run` and `from subprocess import Popen` bindings);
    `subprocess.run` is patched too, per the amendment."""
    import subprocess

    spawned: list[object] = []
    real_init = subprocess.Popen.__init__
    real_run = subprocess.run

    def counting_init(self: Any, *args: Any, **kwargs: Any) -> None:
        spawned.append(args[0] if args else kwargs.get("args"))
        real_init(self, *args, **kwargs)

    def delegating_run(*args: Any, **kwargs: Any) -> Any:
        return real_run(*args, **kwargs)

    monkeypatch.setattr(subprocess.Popen, "__init__", counting_init)
    monkeypatch.setattr(subprocess, "run", delegating_run)
    return spawned


def test_t10_spawn_spy_positive_control(spawn_spy: list[object]) -> None:
    """Finding 26 positive control: the same spy records a real spawn."""
    import subprocess
    import sys

    subprocess.run([sys.executable, "-c", "pass"], check=True)
    assert len(spawn_spy) >= 1


def _save_legacy_checkpoint_json(root: Path, name: str, created_at: int) -> None:
    import json

    sessions = root / ".rush" / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    (sessions / f"{name}.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "checkpoint_id": name,
                "name": name,
                "status": "ok",
                "created_at": created_at,
                "metadata": {"cwd": str(root)},
                "files": ["a.py"],
            }
        ),
        encoding="utf-8",
    )


def _migrated_db_without_sessions_dir(root: Path) -> None:
    """A project whose checkpoints exist only as `memory.db` rows: the JSON
    files were migrated (renamed `.migrated`) and the sessions directory is
    gone. Every writer connection is closed, so the WAL is checkpointed."""
    import shutil

    from rush.memory.migration import migrate_checkpoint_journal

    _save_legacy_checkpoint_json(root, "old", 10)
    _save_legacy_checkpoint_json(root, "new", 20)
    assert migrate_checkpoint_journal(root) == 2
    shutil.rmtree(root / ".rush" / "sessions")
    assert (root / ".rush" / "memory.db").is_file()
    _close_writers()
    assert _sidecars(root) == []


def test_t10_session_list_legacy_json_no_db(
    tmp_path: Path, spawn_spy: list[object]
) -> None:
    """session-list-legacy-json-no-db (finding 3): the JSON entries are
    returned and no `memory.db` is created.

    RED: `list_checkpoints` falls back to `read_origin_kind`, which builds a
    creating `TypedArtifactStore` and leaves `.rush/memory.db` behind.
    """
    _save_legacy_checkpoint_json(tmp_path, "legacy", 5)
    before = _byte_snapshot(tmp_path)

    result = SessionContinuityTool().run(tmp_path, operation="list")

    assert result["status"] == "ok", result
    assert [entry["name"] for entry in result["raw"]] == ["legacy"]
    assert not (tmp_path / ".rush" / "memory.db").exists()
    assert _byte_snapshot(tmp_path) == before
    assert spawn_spy == []


def test_t10_session_list_migrated_no_sessions_dir(
    tmp_path: Path, spawn_spy: list[object]
) -> None:
    """session-list-migrated-no-sessions-dir (finding 3): rows that live only
    in `memory.db` are listed, and the tree is byte-identical.

    RED: `_run_list` returns `[]` whenever `.rush/sessions` is absent.
    """
    _migrated_db_without_sessions_dir(tmp_path)
    before = _byte_snapshot(tmp_path)

    result = SessionContinuityTool().run(tmp_path, operation="list")

    assert result["status"] == "ok", result
    assert [entry["name"] for entry in result["raw"]] == ["new", "old"]
    assert _byte_snapshot(tmp_path) == before
    assert _sidecars(tmp_path) == []
    assert spawn_spy == []


def test_t10_session_restore_migrated_no_sessions_dir(
    tmp_path: Path, spawn_spy: list[object]
) -> None:
    """session-restore-migrated-no-sessions-dir (finding 3): the row is
    restored, and the tree is byte-identical.

    RED: `CheckpointJournal.__init__` recreates `.rush/sessions`, and the
    `read_origin` fallback opens `memory.db` read-write.
    """
    _migrated_db_without_sessions_dir(tmp_path)
    before = _byte_snapshot(tmp_path)

    result = SessionContinuityTool().run(tmp_path, operation="restore", name="new")

    assert result["status"] == "ok", result
    assert result["raw"]["name"] == "new"
    assert result["raw"]["created_at"] == 20
    assert not (tmp_path / ".rush" / "sessions").exists()
    assert _byte_snapshot(tmp_path) == before
    assert _sidecars(tmp_path) == []
    assert spawn_spy == []


def _legacy_checkpoint_db(root: Path) -> Path:
    """A `memory.db` predating `artifact_version` (so `open_readonly`
    reports `migration_required`) that holds checkpoint origin rows."""
    import json
    import sqlite3

    db = root / ".rush" / "memory.db"
    db.parent.mkdir(parents=True)
    conn = sqlite3.connect(db)
    with conn:
        conn.execute(
            "CREATE TABLE memory_artifacts (id TEXT PRIMARY KEY, family TEXT NOT NULL, "
            "subject TEXT NOT NULL, trust_tier TEXT NOT NULL, content TEXT NOT NULL, "
            "source TEXT NOT NULL, created_at REAL NOT NULL, symbol_ref TEXT, "
            "content_hash TEXT, corroboration_count INTEGER NOT NULL DEFAULT 0, "
            "promoted_at REAL, stale INTEGER NOT NULL DEFAULT 0, signature TEXT, "
            "origin_kind TEXT, origin_id TEXT)"
        )
        for name, created in (("legacy-a", 1.0), ("legacy-b", 2.0)):
            content = {
                "name": name,
                "checkpoint_id": name,
                "status": "ok",
                "created_at": created,
            }
            conn.execute(
                "INSERT INTO memory_artifacts (id, family, subject, trust_tier, "
                "content, source, created_at, symbol_ref, origin_kind, origin_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    f"id-{name}",
                    "handoff",
                    "active_context",
                    "IMPORTED",
                    json.dumps(content),
                    "migration:checkpoint_journal",
                    created,
                    name,
                    "checkpoint",
                    name,
                ),
            )
    conn.close()
    return db


def test_t10_session_list_legacy_db_migration_required(
    tmp_path: Path, spawn_spy: list[object]
) -> None:
    """session-list-legacy-db-migration-required (finding 3): a DB predating
    `artifact_version` still yields its checkpoint origin rows, with the DB
    bytes and schema unchanged and nothing migrated.

    RED: `_run_list` returns `[]` without `.rush/sessions`, and the
    `read_origin_kind` fallback would construct `TypedArtifactStore`, which
    migrates the legacy schema in place.
    """
    import sqlite3

    db = _legacy_checkpoint_db(tmp_path)
    before = _byte_snapshot(tmp_path)

    result = SessionContinuityTool().run(tmp_path, operation="list")

    assert result["status"] == "ok", result
    assert [entry["name"] for entry in result["raw"]] == ["legacy-b", "legacy-a"]
    assert _byte_snapshot(tmp_path) == before
    assert _sidecars(tmp_path) == []
    conn = sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(memory_artifacts)")}
    conn.close()
    assert "artifact_version" not in columns
    assert spawn_spy == []


def test_t10_existing_wal_db_read_no_sidefiles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, spawn_spy: list[object]
) -> None:
    """existing-wal-db-read-no-sidefiles (X1): the flight replay fallback,
    `cache stats`, the session list and the gain-stats reader, run against
    cleanly closed WAL databases, leave no `-wal`/`-shm` and unchanged bytes.

    RED: every reader opens `mode=ro` on a WAL database (or read-write),
    which leaves `memory.db-wal`/`memory.db-shm` behind.
    """
    import json

    from rush.cache import ResultCache
    from rush.cli import cli
    from rush.mcp import rush_context_gain_stats
    from rush.memory.checkpoint_journal import CheckpointJournal
    from rush.memory.migration import (
        migrate_checkpoint_journal,
        migrate_flight_recorder,
    )
    from rush.token_economy.telemetry import TelemetryStore

    _git_dir_marker(tmp_path)
    FlightRecorder(tmp_path).record_event("sess-1", "tool_call", {"tool": "lint"})
    assert migrate_flight_recorder(tmp_path) == 1
    assert not (tmp_path / ".rush" / "sessions" / "flights" / "sess-1.jsonl").exists()
    CheckpointJournal(tmp_path).save_checkpoint("cp", {"cwd": str(tmp_path)}, [])
    assert migrate_checkpoint_journal(tmp_path) == 1
    assert not (tmp_path / ".rush" / "sessions" / "cp.json").exists()
    ResultCache(tmp_path / ".rush" / "cache.db")
    TelemetryStore(tmp_path).record_savings("pack", 100, 40)
    _close_writers()
    assert _sidecars(tmp_path) == []
    before = _byte_snapshot(tmp_path)
    spawn_spy.clear()

    events = FlightRecorder(tmp_path, create=False).replay_session("sess-1")
    assert [e["event_type"] for e in events] == ["tool_call"]

    monkeypatch.chdir(tmp_path)
    stats = CliRunner().invoke(cli, ["cache", "stats"])
    assert stats.exit_code == 0, stats.output
    assert json.loads(stats.output)["entries"] == 0

    listed = SessionContinuityTool().run(tmp_path, operation="list")
    assert [entry["name"] for entry in listed["raw"]] == ["cp"]

    summary = json.loads(rush_context_gain_stats(_anchor=tmp_path))
    assert summary["events_count"] == 1
    assert summary["available"] is True

    assert _sidecars(tmp_path) == []
    assert _byte_snapshot(tmp_path) == before
    assert spawn_spy == []


def test_t10_mcp_gain_stats_no_create(tmp_path: Path, spawn_spy: list[object]) -> None:
    """mcp-gain-stats-no-create (finding 15): through the real MCP custom
    wrapper, no telemetry DB is created, the summary is empty with
    `available: false` and a reason, and the reported path is under the
    logical root of the server-start anchor.

    RED: `rush_context_gain_stats` constructs `TelemetryStore()`, which
    creates `<cwd>/.rush/telemetry/tokens.db`.
    """
    import json

    from rush.invocation import InvocationExecutor
    from rush.mcp import rush_context_gain_stats
    from rush.mcp_support.tool_registry import _make_handler, make_custom_wrapper

    _git_dir_marker(tmp_path)
    anchor = tmp_path / "src" / "pkg"
    anchor.mkdir(parents=True)
    before = _byte_snapshot(tmp_path)
    executor = InvocationExecutor()
    executor.register("rush_context_gain_stats", _make_handler(rush_context_gain_stats))
    wrapper = make_custom_wrapper(
        rush_context_gain_stats,
        "rush_context_gain_stats",
        executor,
        anchor_cwd=anchor,
    )

    summary = json.loads(wrapper())

    assert summary["available"] is False
    assert summary["reason"]
    assert summary["events_count"] == 0
    assert summary["path"] == str(
        tmp_path.resolve() / ".rush" / "telemetry" / "tokens.db"
    )
    assert not (tmp_path / ".rush").exists()
    assert not (anchor / ".rush").exists()
    assert _byte_snapshot(tmp_path) == before
    assert spawn_spy == []


def test_t10_staged_scan_roots(tmp_path: Path) -> None:
    """staged-scan-roots (finding 4): inside a staged candidate,
    `current_invocation_root()` is the original (logical) root and
    `current_execution_root()` is the staged root; outside staging both are
    the context's workspace root, and both are unset outside `execute`.

    RED: neither accessor exists.
    """
    from rush.engines.staging import stage_inventory, staging_scope
    from rush.invocation import InvocationExecutor
    from rush.invocation.executor import (
        current_execution_root,
        current_invocation_root,
    )

    original = tmp_path / "project"
    original.mkdir()
    (original / "a.py").write_text("a = 1\n", encoding="utf-8")
    seen: list[tuple[Path | None, Path | None]] = []

    def handler() -> dict[str, str]:
        seen.append((current_invocation_root(), current_execution_root()))
        return {"status": "ok"}

    executor = InvocationExecutor()
    executor.register("probe", handler)

    staging = stage_inventory(original, tmp_path / "stage", ["a.py"])
    staged_root = staging.stage_path(original)
    assert staged_root is not None
    with staging_scope(staging):
        executor.execute(
            resolve_invocation(
                {"operation_id": "probe"}, transport="cli", workspace_root=staged_root
            )
        )
    executor.execute(
        resolve_invocation(
            {"operation_id": "probe"}, transport="cli", workspace_root=original
        )
    )

    assert seen == [
        (original.resolve(), staged_root.resolve()),
        (original.resolve(), original.resolve()),
    ]
    assert current_invocation_root() is None
    assert current_execution_root() is None


def test_t10_mcp_continuity_files_reach_tool_cli_agrees(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """mcp-continuity-files-bound (R10.5), end to end: the real MCP
    `rush_continuity(files=[...])` wrapper saves exactly those two contained
    targets, and CLI `session save --file` records the identical list.

    RED: `files` never reaches `SessionContinuityTool.__call__`, so the MCP
    checkpoint records `files: []`.
    """
    import json

    from rush.cli import cli
    from rush.invocation import InvocationExecutor
    from rush.mcp_support.tool_registry import make_tool_wrapper

    _git_dir_marker(tmp_path)
    (tmp_path / "a.py").write_text("a = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("b = 1\n", encoding="utf-8")
    tool = SessionContinuityTool()
    executor = InvocationExecutor()
    executor.register(tool.name, tool.__call__)
    wrapper = make_tool_wrapper(tool, executor, anchor_cwd=tmp_path)

    result = wrapper(
        path=".",
        operation="save",
        name="via-mcp",
        files=["a.py", "b.py"],
        allow_cache_write=True,
    )
    assert result["status"] == "ok", result

    monkeypatch.chdir(tmp_path)
    argv = ["session", "save", "via-cli", "-f", "a.py", "-f", "b.py"]
    cli_result = CliRunner().invoke(cli, [*argv, "--allow-cache-write", "--json"])
    assert cli_result.exit_code == 0, cli_result.output

    sessions = tmp_path / ".rush" / "sessions"
    mcp_files = json.loads((sessions / "via-mcp.json").read_text())["files"]
    cli_files = json.loads((sessions / "via-cli.json").read_text())["files"]
    assert mcp_files == ["a.py", "b.py"]
    assert cli_files == mcp_files


def test_t10_readonly_queries_zero_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, spawn_spy: list[object]
) -> None:
    """Finding 26 over the S10.4-S10.6 read-only queries: session list and
    restore, flight status and replay, and cache stats spawn nothing and
    create nothing.

    RED: flight status, session restore and cache stats create `.rush`.
    """
    from rush.cli import cli

    monkeypatch.chdir(tmp_path)
    before = _byte_snapshot(tmp_path)
    runner = CliRunner()
    for argv in (
        ["session", "list", "--json"],
        ["session", "restore", "ghost", "--json"],
        ["flight-recorder"],
        ["flight-recorder", "--replay", "ghost"],
        ["cache", "stats"],
    ):
        outcome = runner.invoke(cli, argv)
        assert outcome.exception is None or isinstance(outcome.exception, SystemExit), (
            argv,
            outcome.output,
        )
    assert not (tmp_path / ".rush").exists()
    assert _byte_snapshot(tmp_path) == before
    assert spawn_spy == []


def test_t10_path_relative_arguments_keep_their_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guard for R10.1: moving state to the logical root must not rebase the
    continuity arguments that are relative to the given path. CLI
    `context pack --path x.py` from `root/pkg`, and MCP `rush_context_pack`
    with an absolute file path, both still pack `root/pkg/x.py`; the CCR
    recovery state lands under the logical root only."""
    import json

    from rush.cli import cli
    from rush.mcp import rush_context_pack

    _git_dir_marker(tmp_path)
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "x.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    monkeypatch.chdir(pkg)

    cli_result = CliRunner().invoke(
        cli, ["context", "pack", "--path", "x.py", "--json"]
    )
    assert cli_result.exit_code == 0, cli_result.output
    assert json.loads(cli_result.output)["status"] == "ok", cli_result.output

    mcp_result = rush_context_pack(str(pkg / "x.py"))
    assert mcp_result["status"] == "ok", mcp_result
    assert not (pkg / ".rush").exists()


def test_t10_readonly_read_never_closes_last_over_a_leaked_writer(
    tmp_path: Path,
) -> None:
    """X1 guard: a `mode=ro` connection that closes after the last writer cannot
    checkpoint, stranding committed pages in `-wal` (an immutable read then sees
    no table). A writer leaked in a reference cycle (as `with self._connect()`
    leaves them) must be collected before the read-only read, never during it.
    The `read` callback collects garbage mid-read to force that timing."""
    import gc
    import sqlite3

    from rush.memory.store import read_sqlite_readonly

    db = tmp_path / "m.db"
    writer = sqlite3.connect(db)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("CREATE TABLE t (x)")
    writer.execute("INSERT INTO t VALUES (1)")
    writer.commit()
    cycle: list[object] = [writer]
    cycle.append(cycle)
    del writer, cycle
    assert Path(f"{db}-wal").exists()

    def read(conn: sqlite3.Connection) -> int:
        gc.collect()
        return int(conn.execute("SELECT count(*) FROM t").fetchone()[0])

    assert read_sqlite_readonly(db, read) == 1
    gc.collect()
    assert _sidecars(tmp_path) == []
    conn = sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True)
    assert conn.execute("SELECT count(*) FROM t").fetchone()[0] == 1
    conn.close()


# ---------------------------------------------------------------------------
# Fix round 1: remaining read paths on T10 surfaces open read-only
# ---------------------------------------------------------------------------


def _pack_fixture(root: Path) -> None:
    _git_dir_marker(root)
    (root / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")


@pytest.mark.parametrize("existing_store", [False, True])
def test_t10_context_pack_lookup_creates_nothing(
    tmp_path: Path, spawn_spy: list[object], existing_store: bool
) -> None:
    """An ungranted `context_pack` (its memory cache lookup) creates no `.rush`,
    `memory.db` or sidecar when no store exists, and leaves an existing store
    byte-identical (a cache hit is served read-only).

    RED: `check_memory_before_pack` constructed a creating `TypedArtifactStore`.
    """
    _pack_fixture(tmp_path)
    tool = SessionContinuityTool()
    if existing_store:
        granted = tool.run(
            tmp_path,
            operation="context_pack",
            context_path="a.py",
            permissions=ExecutionPermissions(cache_write=True),
        )
        assert granted["status"] == "ok", granted
        _close_writers()
        assert _sidecars(tmp_path) == []
    before = _byte_snapshot(tmp_path)
    spawn_spy.clear()

    result = tool.run(tmp_path, operation="context_pack", context_path="a.py")

    assert result["status"] == "ok", result
    assert _byte_snapshot(tmp_path) == before
    assert _sidecars(tmp_path) == []
    assert (tmp_path / ".rush").exists() is existing_store
    assert spawn_spy == []


@pytest.mark.parametrize("existing_ledger", [False, True])
def test_t10_coordination_recovery_creates_nothing(
    tmp_path: Path, existing_ledger: bool
) -> None:
    """Ungranted `coordination_recovery` reads the failure receipt read-only:
    no `.rush/memory/failures.db` is created, an existing one is unchanged, and
    its receipt is still returned. (It legitimately spawns a read-only
    `git log --grep=Revert` for mistake guardrails, so no zero-spawn check.)

    RED: the failure receipt read constructed `FailureLedger`, whose
    constructor creates `.rush/memory/failures.db`.
    """
    from rush.memory.failure_ledger import FailureLedger

    fingerprint = "b" * 64
    if existing_ledger:
        fingerprint = FailureLedger(tmp_path).record_failure("patch", "boom")
        _close_writers()
    before = _byte_snapshot(tmp_path)

    result = SessionContinuityTool().run(
        tmp_path,
        operation="coordination_recovery",
        flight_session_id="s1",
        failure_fingerprint=fingerprint,
    )

    assert result["status"] != "error", result
    assert _byte_snapshot(tmp_path) == before
    assert _sidecars(tmp_path) == []
    assert (tmp_path / ".rush").exists() is existing_ledger
    receipt = FailureLedger.read_receipt(tmp_path, fingerprint)
    if existing_ledger:
        assert receipt is not None and receipt["fingerprint"] == fingerprint
        assert "boom" in str(result)
    else:
        assert receipt is None


@pytest.mark.parametrize("existing_db", [False, True])
def test_t10_gain_panel_creates_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, existing_db: bool
) -> None:
    """The CLI/TUI gain HUD reads telemetry read-only, anchored at the logical
    root when no root is given.

    RED: `build_gain_panel` constructed `TelemetryStore`, which creates
    `.rush/telemetry/tokens.db`.
    """
    from rich.console import Console

    from rush.token_economy.telemetry import TelemetryStore
    from rush.token_economy.tui_gain import build_gain_panel

    _git_dir_marker(tmp_path)
    nested = tmp_path / "src"
    nested.mkdir()
    if existing_db:
        TelemetryStore(tmp_path).record_savings("pack", 100, 40)
        _close_writers()
    before = _byte_snapshot(tmp_path)
    monkeypatch.chdir(nested)

    console = Console(record=True, width=120)
    console.print(build_gain_panel())

    assert _byte_snapshot(tmp_path) == before
    assert _sidecars(tmp_path) == []
    assert not (nested / ".rush").exists()
    assert ("60" in console.export_text()) is existing_db


# ---------------------------------------------------------------------------
# Recovery procedure (finding 16) -- temp directories only
# ---------------------------------------------------------------------------


def _stray_rush(checkout: Path) -> Path:
    """A main-checkout-like tree with a stray `src/rush/tools/.rush` holding a
    cleanly closed WAL `memory.db` plus nested cache files."""
    from rush.memory.store import MemoryArtifact, TypedArtifactStore

    stray_root = checkout / "src" / "rush" / "tools"
    stray_root.mkdir(parents=True)
    TypedArtifactStore(stray_root).write(
        MemoryArtifact(
            id="m1",
            family="memory",
            subject="domain_knowledge",
            trust_tier="DERIVED",
            content={"note": "keep"},
            source="agent:notes",
            created_at=1.0,
        )
    )
    (stray_root / ".rush" / "cache" / "blob.bin").write_bytes(b"\x00\x01payload")
    _close_writers()
    return stray_root / ".rush"


def test_t10_recovery_inventory_backup_quarantine_restore(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Inventory with hashes, byte-exact backup, verified quarantine, printed
    restore command; running that command restores the identical bytes."""
    import json
    import subprocess

    from scripts.phase70_t10_recovery import main

    checkout = tmp_path / "checkout"
    source = _stray_rush(checkout)
    recovery = tmp_path / "rush-recovery" / "phase-70-t10"
    original = _byte_snapshot(source)
    assert "memory.db" in original and "cache/blob.bin" in original

    assert (
        main(
            [
                "--root",
                str(checkout),
                "--source",
                str(source),
                "--recovery",
                str(recovery),
            ]
        )
        == 0
    )
    listed = json.loads(capsys.readouterr().out)
    assert {f["path"]: f["sha256"] for f in listed["files"]} == original
    assert _byte_snapshot(source) == original
    assert not recovery.exists()

    assert (
        main(
            [
                "--root",
                str(checkout),
                "--source",
                str(source),
                "--recovery",
                str(recovery),
                "--execute",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    restore = out.rsplit("RESTORE: ", 1)[1].strip()
    assert not source.exists()
    assert _byte_snapshot(recovery / "backup" / ".rush") == original
    assert _byte_snapshot(recovery / "quarantine" / ".rush") == original
    manifest = json.loads((recovery / "manifest.json").read_text())
    assert manifest["restore_command"] == restore
    assert {f["path"]: f["sha256"] for f in manifest["files"]} == original
    assert all(
        f["integrity"] == "ok" for f in manifest["files"] if f["path"].endswith(".db")
    )

    subprocess.run(restore, shell=True, check=True)
    assert _byte_snapshot(source) == original
    assert _byte_snapshot(recovery / "backup" / ".rush") == original


def _refused(argv: list[str], capsys: pytest.CaptureFixture[str]) -> str:
    from scripts.phase70_t10_recovery import main

    assert main(argv) == 2
    return capsys.readouterr().err


@pytest.mark.parametrize(
    "case",
    [
        "source-outside-root",
        "not-dot-rush",
        "symlinked-source",
        "symlink-inside",
        "recovery-inside-root",
        "quarantine-exists",
    ],
)
def test_t10_recovery_refuses_outside_given_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], case: str
) -> None:
    """Refuses (exit 2) and changes nothing for anything outside the given
    paths or any link that could widen the copy or move."""
    checkout = tmp_path / "checkout"
    source = _stray_rush(checkout)
    recovery = tmp_path / "recovery"
    root = checkout
    if case == "source-outside-root":
        root = checkout / "src" / "rush" / "cli_support"
        root.mkdir()
    elif case == "not-dot-rush":
        source = source / "cache"
    elif case == "symlinked-source":
        real = tmp_path / "elsewhere" / ".rush"
        real.mkdir(parents=True)
        (real / "x").write_text("x")
        link_parent = checkout / "linked"
        link_parent.mkdir()
        (link_parent / ".rush").symlink_to(real, target_is_directory=True)
        source = link_parent / ".rush"
    elif case == "symlink-inside":
        outside = tmp_path / "outside-secret"
        outside.write_text("secret")
        (source / "cache" / "escape").symlink_to(outside)
    elif case == "recovery-inside-root":
        recovery = checkout / "recovery"
    elif case == "quarantine-exists":
        (recovery / "quarantine" / ".rush").mkdir(parents=True)
    before = _byte_snapshot(tmp_path)

    err = _refused(
        [
            "--root",
            str(root),
            "--source",
            str(source),
            "--recovery",
            str(recovery),
            "--execute",
        ],
        capsys,
    )

    assert err.startswith("REFUSED:"), err
    assert _byte_snapshot(tmp_path) == before
