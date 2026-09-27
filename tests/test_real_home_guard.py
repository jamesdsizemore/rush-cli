"""F14: tests never touch the real HOME, ~/.claude.json, ~/.codex or the
real Rush data root."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from rush.setup.provision import default_data_root

pytest_plugins = ["pytester"]

_CONFTEST = Path(__file__).resolve().parent / "conftest.py"


def test_home_and_xdg_dirs_are_redirected_under_pytest_basetemp(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    base = tmp_path_factory.getbasetemp().resolve()
    # Checked before any write, so a missing redirect fails here instead of
    # writing to the real HOME.
    assert Path.home().resolve().is_relative_to(base)
    for var in ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        assert Path(os.environ[var]).resolve().is_relative_to(base), var
    assert default_data_root().resolve().is_relative_to(base)

    target = Path.home() / ".claude.json"
    target.write_text("{}", encoding="utf-8")
    assert target.resolve().is_relative_to(base)
    assert target.read_text(encoding="utf-8") == "{}"


def test_each_test_gets_a_fresh_home(tmp_path_factory: pytest.TempPathFactory) -> None:
    base = tmp_path_factory.getbasetemp().resolve()
    assert Path.home().resolve().is_relative_to(base)
    assert not (Path.home() / ".claude.json").exists()


def test_a_test_that_sets_its_own_home_keeps_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert Path.home() == tmp_path


def test_guard_reports_a_changed_file(tmp_path: Path) -> None:
    from conftest import _changed_paths, _real_home_snapshot

    home = tmp_path / "home"
    data_root = home / "data"
    (home / ".codex").mkdir(parents=True)
    (data_root / "toolchains").mkdir(parents=True)
    claude = home / ".claude.json"
    claude.write_text("{}", encoding="utf-8")
    before = _real_home_snapshot(home, data_root)
    assert _changed_paths(before, _real_home_snapshot(home, data_root)) == []

    claude.write_text('{"mcpServers": {"rush": {}}}', encoding="utf-8")
    (home / ".codex" / "config.toml").write_text("x = 1\n", encoding="utf-8")
    (data_root / "owners").mkdir()
    (data_root / "toolchains").rmdir()

    assert _changed_paths(before, _real_home_snapshot(home, data_root)) == sorted(
        [
            str(claude),
            str(home / ".codex" / "config.toml"),
            str(data_root / "owners"),
            str(data_root / "toolchains"),
        ]
    )


def test_guard_reports_an_absent_data_root_that_appears(tmp_path: Path) -> None:
    from conftest import _changed_paths, _real_home_snapshot

    data_root = tmp_path / "data"
    before = _real_home_snapshot(tmp_path, data_root)
    (data_root / "bin").mkdir(parents=True)
    assert _changed_paths(before, _real_home_snapshot(tmp_path, data_root)) == [
        str(data_root),
        str(data_root / "bin"),
    ]


def test_guard_ignores_claude_json_changes_outside_mcp_servers(tmp_path: Path) -> None:
    from conftest import _changed_paths, _real_home_snapshot

    claude = tmp_path / ".claude.json"
    data_root = tmp_path / "data"
    claude.write_text(
        json.dumps(
            {
                "numStartups": 1,
                "mcpServers": {"other": {"command": "x"}},
                "projects": {"/p": {"mcpServers": {}, "history": []}},
            }
        ),
        encoding="utf-8",
    )
    before = _real_home_snapshot(tmp_path, data_root)
    # Claude Code rewrites the file while a session is open: counters,
    # history and a new project with no MCP servers are not Rush's business.
    claude.write_text(
        json.dumps(
            {
                "numStartups": 2,
                "projects": {
                    "/p": {"history": ["hi"], "mcpServers": {}},
                    "/q": {"mcpServers": {}},
                },
                "mcpServers": {"other": {"command": "x"}},
            }
        ),
        encoding="utf-8",
    )
    assert _changed_paths(before, _real_home_snapshot(tmp_path, data_root)) == []


@pytest.mark.parametrize("where", ["top-level", "project"])
def test_guard_reports_an_added_rush_mcp_server_in_claude_json(
    tmp_path: Path, where: str
) -> None:
    from conftest import _changed_paths, _real_home_snapshot

    claude = tmp_path / ".claude.json"
    data_root = tmp_path / "data"
    config: dict[str, object] = {"mcpServers": {}, "projects": {"/p": {}}}
    claude.write_text(json.dumps(config), encoding="utf-8")
    before = _real_home_snapshot(tmp_path, data_root)
    rush = {"rush": {"command": "rush", "args": ["mcp", "serve"]}}
    if where == "top-level":
        config["mcpServers"] = rush
    else:
        config["projects"] = {"/p": {"mcpServers": rush}}
    claude.write_text(json.dumps(config), encoding="utf-8")
    assert _changed_paths(before, _real_home_snapshot(tmp_path, data_root)) == [
        str(claude)
    ]


def test_guard_compares_only_mcp_servers_tables_of_codex_config(tmp_path: Path) -> None:
    from conftest import _changed_paths, _real_home_snapshot

    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir()
    data_root = tmp_path / "data"
    config.write_text(
        'model = "a"\n\n[mcp_servers.other]\ncommand = "x"\n', encoding="utf-8"
    )
    before = _real_home_snapshot(tmp_path, data_root)
    config.write_text(
        'model = "b"\n[history]\npersistence = "none"\n\n'
        '[mcp_servers.other]\ncommand = "x"\n',
        encoding="utf-8",
    )
    assert _changed_paths(before, _real_home_snapshot(tmp_path, data_root)) == []

    config.write_text(
        config.read_text(encoding="utf-8")
        + '\n[mcp_servers.rush]\ncommand = "rush"\nargs = ["mcp", "serve"]\n',
        encoding="utf-8",
    )
    assert _changed_paths(before, _real_home_snapshot(tmp_path, data_root)) == [
        str(config)
    ]


def test_session_guard_reports_only_changes_this_process_or_its_children_caused(
    tmp_path: Path,
) -> None:
    import conftest

    data_root = tmp_path / "data"
    (data_root / "owners").mkdir(parents=True)
    (data_root / "gone").mkdir()
    (data_root / "gone" / "old.json").write_text("{}", encoding="utf-8")
    (data_root / "kept.json").write_text("{}", encoding="utf-8")
    before = conftest._real_home_snapshot(tmp_path, data_root)
    # Changed by an unrelated process (another worktree's test run, a real
    # TUI that has since exited): the hook never saw it, so not reported.
    (data_root / "owners" / "outside.lock").touch()
    (data_root / "kept.json").write_text("[1]", encoding="utf-8")
    root = str(data_root) + os.sep
    conftest._WATCHED_ROOTS.append(root)
    try:
        (data_root / "owners" / "mine.lock").touch()
        shutil.rmtree(data_root / "gone")
        # A child handed a path owns everything at or under it.
        code = "import pathlib, sys; d = pathlib.Path(sys.argv[1]); d.mkdir(); (d / 'c.json').touch()"
        subprocess.run(
            [sys.executable, "-c", code, str(data_root / "kids")], check=True
        )
        changes = conftest._session_changes(
            before, conftest._real_home_snapshot(tmp_path, data_root)
        )
    finally:
        conftest._WATCHED_ROOTS.remove(root)
        for recorded in (conftest._SESSION_WRITES, conftest._SESSION_TREES):
            recorded.difference_update(
                {path for path in recorded if path.startswith(str(data_root))}
            )
    assert changes == sorted(
        [
            str(data_root / "owners" / "mine.lock"),
            str(data_root / "gone"),
            str(data_root / "gone" / "old.json"),
            str(data_root / "kids"),
            str(data_root / "kids" / "c.json"),
        ]
    )


def test_session_guard_attributes_a_path_embedded_in_a_child_argument(
    tmp_path: Path,
) -> None:
    import conftest

    data_root = tmp_path / "Application Support" / "Rush"
    (data_root / "owners").mkdir(parents=True)
    before = conftest._real_home_snapshot(tmp_path, data_root)
    embedded = data_root / "owners" / "embedded.lock"
    root = str(data_root) + os.sep
    conftest._WATCHED_ROOTS.append(root)
    try:
        # The path is inside the child's code string, not its own argument.
        subprocess.run(
            [sys.executable, "-c", f"open({str(embedded)!r}, 'w').close()"],
            check=True,
        )
        changes = conftest._session_changes(
            before, conftest._real_home_snapshot(tmp_path, data_root)
        )
    finally:
        conftest._WATCHED_ROOTS.remove(root)
        for recorded in (conftest._SESSION_WRITES, conftest._SESSION_TREES):
            recorded.difference_update(
                {path for path in recorded if path.startswith(str(data_root))}
            )
    assert changes == [str(embedded)]


def test_guard_lsof_probe_is_not_attributed_to_the_session(tmp_path: Path) -> None:
    import conftest

    data_root = tmp_path / "data"
    (data_root / "owners").mkdir(parents=True)
    before = conftest._real_home_snapshot(tmp_path, data_root)
    # Written by another process (another worktree's test run).
    foreign = data_root / "owners" / "foreign.lock"
    foreign.touch()
    root = str(data_root) + os.sep
    conftest._WATCHED_ROOTS.append(root)
    try:
        # The per-test guard probes new foreign entries with lsof.
        conftest._held_by([str(foreign)], {os.getpid()})
        changes = conftest._session_changes(
            before, conftest._real_home_snapshot(tmp_path, data_root)
        )
    finally:
        conftest._WATCHED_ROOTS.remove(root)
        for recorded in (conftest._SESSION_WRITES, conftest._SESSION_TREES):
            recorded.difference_update(
                {path for path in recorded if path.startswith(str(data_root))}
            )
    assert changes == []


def test_snapshot_reports_rewritten_files_and_rush_home_files(tmp_path: Path) -> None:
    from conftest import _changed_paths, _real_home_snapshot

    data_root = tmp_path / "data"
    (data_root / "owners").mkdir(parents=True)
    lock = data_root / "owners" / "a.lock"
    lock.write_text("1", encoding="utf-8")
    rush_home = tmp_path / ".rush"
    rush_home.mkdir()
    config = rush_home / "config.json"
    config.write_text("{}", encoding="utf-8")
    before = _real_home_snapshot(tmp_path, data_root)
    assert _changed_paths(before, _real_home_snapshot(tmp_path, data_root)) == []

    lock.write_text("2", encoding="utf-8")  # same size: only mtime tells
    stat = lock.stat()
    os.utime(lock, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    config.write_text('{"a": 1}', encoding="utf-8")
    (rush_home / "new.json").write_text("x", encoding="utf-8")
    assert _changed_paths(before, _real_home_snapshot(tmp_path, data_root)) == sorted(
        [str(lock), str(config), str(rush_home / "new.json")]
    )


def test_audit_hook_records_writes_links_and_sqlite_under_a_watched_root(
    tmp_path: Path,
) -> None:
    import conftest

    root = tmp_path / "Rush"
    root.mkdir()
    names = ("appended", "rdwr", "truncated", "rewritten", "read", "source")
    files = {name: root / f"{name}.json" for name in names}
    for path in files.values():
        path.write_text("{}", encoding="utf-8")
    conftest._WATCHED_ROOTS.append(str(root) + os.sep)
    try:
        with open(files["appended"], "a", encoding="utf-8") as handle:
            handle.write("x")
        os.close(os.open(files["rdwr"], os.O_RDWR))
        os.close(os.open(files["truncated"], os.O_WRONLY | os.O_TRUNC))
        files["rewritten"].write_text("[]", encoding="utf-8")
        files["read"].read_text(encoding="utf-8")
        sqlite3.connect(root / "state.db").close()
        os.link(files["source"], root / "hard.json")
        os.symlink(files["source"], root / "soft.json")
        created = conftest._created_entries(root, set())
    finally:
        conftest._WATCHED_ROOTS.remove(str(root) + os.sep)
    assert created == sorted(
        str(root / name)
        for name in (
            "appended.json",
            "rdwr.json",
            "truncated.json",
            "rewritten.json",
            "state.db",
            "hard.json",
            "soft.json",
        )
    )


@pytest.mark.parametrize(
    ("name", "content"),
    [
        (".claude.json", b"[1, 2]"),
        (".claude.json", b'"text"'),
        (".claude.json", b'{"projects": [1]}'),
        (".claude.json", b"{not json"),
        (".claude.json", b"\xff\xfe"),
        ("config.toml", b"x = ["),
    ],
)
def test_unreadable_mcp_config_is_a_stable_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, content: bytes
) -> None:
    import conftest

    monkeypatch.setattr(conftest.time, "sleep", lambda _seconds: None)
    path = tmp_path / name
    path.write_bytes(content)
    expected = "unreadable:" + hashlib.sha256(content).hexdigest()
    assert conftest._mcp_servers(path) == expected
    assert conftest._mcp_servers(path) == expected


def test_per_test_guard_fails_a_write_to_an_existing_real_file(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytester.makeconftest(_CONFTEST.read_text(encoding="utf-8"))
    pytester.makepyfile(
        test_writes="""
        import sqlite3

        import conftest


        def test_appends_to_an_existing_data_root_file():
            path = conftest._REAL_HOME_GUARD["data_root"] / "state.json"
            with open(path, "a", encoding="utf-8") as handle:
                handle.write("x")


        def test_connects_sqlite_under_rush_home():
            db = conftest._REAL_HOME_GUARD["home"] / ".rush" / "state.db"
            sqlite3.connect(db).close()
        """
    )
    with tempfile.TemporaryDirectory() as real_home:
        monkeypatch.setenv("HOME", real_home)
        monkeypatch.setenv("USERPROFILE", real_home)
        monkeypatch.setenv("XDG_DATA_HOME", str(Path(real_home) / ".local" / "share"))
        data_root = _data_root_for(Path(real_home))
        data_root.mkdir(parents=True)
        (data_root / "state.json").write_text("{}", encoding="utf-8")
        (Path(real_home) / ".rush").mkdir()
        result = pytester.runpytest_subprocess("-p", "no:cacheprovider")
    result.assert_outcomes(passed=2, errors=2)
    result.stdout.fnmatch_lines(
        [
            "*test_appends_to_an_existing_data_root_file wrote under the real*",
            f"*{data_root / 'state.json'}*",
        ]
    )
    result.stdout.fnmatch_lines(
        [
            "*test_connects_sqlite_under_rush_home wrote under the real*",
            f"*{Path(real_home) / '.rush' / 'state.db'}*",
        ]
    )


def test_new_owner_entries_are_attributed_only_to_this_process_and_its_children() -> (
    None
):
    import conftest
    from conftest import _created_entries, _watched_entries

    from rush.dashboard.state import _owner_lock_path

    with tempfile.TemporaryDirectory() as real:
        data_root = Path(real) / "Rush"
        (data_root / "owners").mkdir(parents=True)
        (data_root / "owners" / "old.lock").touch()
        conftest._WATCHED_ROOTS.append(str(data_root) + os.sep)
        try:
            before = _watched_entries(data_root)
            # Another process that already exited: not ours.
            foreign = data_root / "owners" / "foreign.lock"
            subprocess.run(
                [sys.executable, "-c", f"open({str(foreign)!r}, 'w').close()"],
                check=True,
            )
            # This process, through the resolved owner-lock path.
            mine = _owner_lock_path("hash:mine", data_root=data_root)
            mine.touch()
            # A live child still holding its lock open.
            held = data_root / "owners" / "tui:child.lock"
            child = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    (
                        f"import sys; f = open({str(held)!r}, 'w');"
                        " print('ok', flush=True); sys.stdin.read()"
                    ),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
            )
            try:
                assert child.stdout is not None
                assert child.stdout.readline() == "ok\n"
                created = _created_entries(data_root, before)
            finally:
                child.communicate("")
        finally:
            conftest._WATCHED_ROOTS.remove(str(data_root) + os.sep)
    assert created == sorted([str(mine), str(held)])


def test_per_test_guard_fails_the_test_that_writes_under_the_real_data_root(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytester.makeconftest(_CONFTEST.read_text(encoding="utf-8"))
    pytester.makepyfile(
        test_writes="""
        from rush.dashboard.state import _owner_lock_path, _project_mutation_lock_path


        def test_owner_lock_resolved_with_the_real_home(monkeypatch):
            monkeypatch.undo()  # HOME back to the session's real HOME
            _owner_lock_path("hash:leaked").touch()


        def test_project_lock_resolved_with_the_real_home(monkeypatch):
            monkeypatch.undo()
            _project_mutation_lock_path("proj").touch()


        def test_owner_lock_under_the_isolated_home():
            _owner_lock_path("hash:isolated").touch()


        def test_foreign_entry_while_the_test_patches_which_and_platform(monkeypatch):
            import shutil
            import subprocess
            import sys

            import conftest

            def _forbidden(*_args):
                raise AssertionError("which called")

            monkeypatch.setattr(shutil, "which", _forbidden)
            monkeypatch.setattr(sys, "platform", "win32")
            foreign = conftest._REAL_HOME_GUARD["data_root"] / "owners" / "foreign.lock"
            foreign.parent.mkdir(parents=True, exist_ok=True)
            # Created by a process that has exited: not attributed to the test.
            subprocess.run(
                [sys.executable, "-c", f"open({str(foreign)!r}, 'w').close()"],
                check=True,
            )
        """
    )
    with tempfile.TemporaryDirectory() as real_home:
        monkeypatch.setenv("HOME", real_home)
        monkeypatch.setenv("USERPROFILE", real_home)
        monkeypatch.setenv("XDG_DATA_HOME", str(Path(real_home) / ".local" / "share"))
        result = pytester.runpytest_subprocess("-p", "no:cacheprovider")
        lock = _data_root_for(Path(real_home)) / "owners" / "hash:leaked.lock"
        foreign = lock.with_name("foreign.lock")
        assert lock.exists()
    result.assert_outcomes(passed=4, errors=2)
    # The exited child's lock is not attributed to a test, but no live
    # process outside this tree holds it: the session check fails on it.
    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines(["*REAL HOME GUARD*", f"*{foreign}*"])
    result.stdout.fnmatch_lines(
        [
            "*ERROR at teardown of test_owner_lock_resolved_with_the_real_home*",
            (
                "*test_owner_lock_resolved_with_the_real_home wrote under the "
                "real Rush data root*"
            ),
            f"*{lock}*",
        ]
    )
    result.stdout.fnmatch_lines(
        ["*ERROR at teardown of test_project_lock_resolved_with_the_real_home*"]
    )
    assert "hash:isolated" not in result.stdout.str()


def test_per_test_guard_fails_a_late_thread_write(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytester.makeconftest(_CONFTEST.read_text(encoding="utf-8"))
    pytester.makepyfile(
        test_late="""
        import threading
        import time

        import conftest


        def test_thread_writes_after_the_test_returns():
            owners = conftest._REAL_HOME_GUARD["data_root"] / "owners"

            def late():
                time.sleep(0.3)
                owners.mkdir(parents=True, exist_ok=True)
                (owners / "late.lock").touch()

            threading.Thread(target=late).start()
        """
    )
    with tempfile.TemporaryDirectory() as real_home:
        monkeypatch.setenv("HOME", real_home)
        monkeypatch.setenv("USERPROFILE", real_home)
        monkeypatch.setenv("XDG_DATA_HOME", str(Path(real_home) / ".local" / "share"))
        result = pytester.runpytest_subprocess("-p", "no:cacheprovider")
        late = _data_root_for(Path(real_home)) / "owners" / "late.lock"
        assert late.exists()
    result.assert_outcomes(passed=1, errors=1)
    result.stdout.fnmatch_lines(
        [
            "*ERROR at teardown of test_thread_writes_after_the_test_returns*",
            (
                "*test_thread_writes_after_the_test_returns wrote under the "
                "real Rush data root*"
            ),
            f"*{late}*",
        ]
    )


def _data_root_for(home: Path) -> Path:
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Rush"
    return home / ".local" / "share" / "rush"
