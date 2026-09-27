"""F14: tests never touch the real HOME, ~/.claude.json, ~/.codex or the
real Rush data root."""

from __future__ import annotations

import json
import os
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


def test_session_guard_leaves_owner_and_project_lock_entries_to_the_per_test_check(
    tmp_path: Path,
) -> None:
    from conftest import _real_home_snapshot, _session_changes

    data_root = tmp_path / "data"
    (data_root / "owners").mkdir(parents=True)
    (data_root / "dashboard" / "project_locks").mkdir(parents=True)
    before = _real_home_snapshot(tmp_path, data_root)
    # A running `rush mcp serve` or another worktree's suite adds these;
    # only the per-test check, which attributes them, may report them.
    (data_root / "owners" / "a:b.lock").touch()
    (data_root / "dashboard" / "project_locks" / "c.lock").touch()
    (data_root / "toolchains").mkdir()
    assert _session_changes(
        before, _real_home_snapshot(tmp_path, data_root), data_root
    ) == [str(data_root / "toolchains")]


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
        assert lock.exists()
    result.assert_outcomes(passed=4, errors=2)
    result.stdout.fnmatch_lines(
        [
            "*ERROR at teardown of test_owner_lock_resolved_with_the_real_home*",
            (
                "*test_owner_lock_resolved_with_the_real_home created under the "
                "real Rush data root:*"
            ),
            f"*{lock}*",
        ]
    )
    result.stdout.fnmatch_lines(
        ["*ERROR at teardown of test_project_lock_resolved_with_the_real_home*"]
    )
    assert "hash:isolated" not in result.stdout.str()


def _data_root_for(home: Path) -> Path:
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Rush"
    return home / ".local" / "share" / "rush"
