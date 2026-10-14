"""The TUI owner-liveness lock lives under the data root the TUI state uses.

A `rush ui` given an explicit data root takes its lifetime owner lock under
that root, never under the default (HOME-derived) one; the process-wide lock
is reused only for the root it was taken under.
"""

from __future__ import annotations

import sys
import tempfile
import textwrap
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import rush.tui as tui_module
from rush.dashboard.state import observe_owner
from rush.setup.provision import default_data_root
from rush.tools.base import Finding, ToolResult
from rush.tui import (
    ProjectSeed,
    ProjectState,
    ScanActions,
    TuiState,
    _dispatch_key,
    _poll_running_scans,
    _pump,
    _start_initial_check_thread,
    run_interactive_tui,
)

pytest_plugins = ["pytester"]

_CONFTEST = Path(__file__).resolve().parent / "conftest.py"


@pytest.fixture
def fresh_owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """No owner lock minted yet in this process, and a throwaway HOME whose
    default data root stands in for the real one. Returns that root."""
    monkeypatch.setattr(tui_module, "_OWNER_INSTANCE", [])
    monkeypatch.setattr(tui_module, "_OWNER_LOCK", [])
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    return default_data_root()


def _actions(**extra: Any) -> ScanActions:
    base: dict[str, Any] = {
        "plan_scan": lambda *a, **k: SimpleNamespace(plan_id="plan-1", candidates=[1]),
        "execute_scan": lambda *a, **k: SimpleNamespace(aggregate=None),
        "cancel_scan_run": lambda *a, **k: {},
        "rescan_project_run": lambda *a, **k: {},
        "build_handoff": lambda *a, **k: None,
        "dispatch_handoff": lambda *a, **k: None,
        "load_scan_events": lambda *a, **k: {"events": [], "run_state": "completed"},
        "list_agents": list,
        "dashboard_owner": lambda root: None,
    }
    base.update(extra)
    return ScanActions(**base)


def _entries(root: Path) -> list[str]:
    return sorted(str(p) for p in root.rglob("*")) if root.exists() else []


def test_tui_owner_lock_uses_the_isolated_data_root(
    tmp_path: Path, fresh_owner: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owners: list[str] = []

    def run_check_suite(root: Path, **kwargs: Any) -> dict[str, Any]:
        owners.append(str(kwargs["owner_instance_id"]))
        return {"tool": "suite", "status": "ok", "findings": [], "summary": "done"}

    actions = _actions(run_check_suite=run_check_suite)

    def check(data_root: Path | None) -> str:
        project = ProjectState(name="demo", root=tmp_path / "proj")
        _start_initial_check_thread(project, actions, data_root=data_root)
        assert project.scan_thread is not None
        project.scan_thread.join(timeout=10)
        assert project.owner == "local", project.last_message
        return owners[-1]

    first_root, second_root = tmp_path / "first", tmp_path / "second"
    first = check(first_root)
    assert observe_owner(first, first_root) == "alive"
    assert check(first_root) == first  # same root: the same lock, reused
    assert _entries(fresh_owner) == []  # nothing under the default root

    second = check(second_root)
    assert second != first  # a different root never reuses the first lock
    assert observe_owner(second, second_root) == "alive"
    assert observe_owner(first, first_root) != "alive"  # released on rebind
    assert not (second_root / "owners" / f"{first}.lock").exists()
    assert _entries(fresh_owner) == []

    # No explicit root: resolved when taken, and a later HOME (another
    # test's isolated root) takes its own lock instead of reusing this one.
    third = check(None)
    assert observe_owner(third, fresh_owner) == "alive"
    other_home = tmp_path / "other-home"
    other_home.mkdir()
    monkeypatch.setenv("HOME", str(other_home))
    fourth = check(None)
    assert fourth != third
    assert observe_owner(fourth, default_data_root()) == "alive"
    assert observe_owner(third, fresh_owner) != "alive"


def test_tui_launch_writes_nothing_under_the_real_data_root(
    tmp_path: Path, fresh_owner: Path
) -> None:
    data_root = tmp_path / "data"
    root = tmp_path / "proj"
    root.mkdir()
    finding: Finding = {
        "path": "a.py",
        "line": 1,
        "column": 1,
        "rule": "F1",
        "message": "issue in a.py",
        "severity": "error",
    }
    seed = ProjectSeed(
        name="proj",
        root=root,
        results=[
            ToolResult(
                tool="lint",
                status="fail",
                duration_ms=1,
                summary="1 finding",
                findings=[finding],
            )
        ],
    )
    actions = _actions(
        load_overview=lambda root_, **k: {
            "status": {},
            "status_summary": "proj",
            "evidence": None,
            "registration": {"state": "ok", "reason": None},
        }
    )

    class _IdleReader:
        def read_key(self, timeout: float) -> str | None:
            return None

        def get_size(self) -> tuple[int, int]:
            return (120, 40)

    state: TuiState = run_interactive_tui(
        [seed],
        key_reader=_IdleReader(),
        actions=actions,
        use_live=False,
        data_root=data_root,
        max_ticks=1,
    )
    for key in ("f3", "3", "s", "y"):
        _dispatch_key(state, key, actions)
        _pump(state, actions)
    project = state.active_project
    assert project.scan_thread is not None, state.message
    project.scan_thread.join(timeout=10)
    deadline = time.monotonic() + 10
    while project.status == "scanning" and time.monotonic() < deadline:
        _pump(state, actions)
        _poll_running_scans(state, actions)
        time.sleep(0.01)
    assert project.status != "scanning", project.last_message

    locks = sorted((data_root / "owners").glob("tui:*.lock"))
    assert len(locks) == 1, _entries(data_root)
    assert observe_owner(locks[0].stem, data_root) == "alive"
    assert _entries(fresh_owner) == []


def _data_root_for(home: Path) -> Path:
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Rush"
    return home / ".local" / "share" / "rush"


def _run_with_a_stand_in_real_home(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, test_source: str
) -> tuple[pytest.RunResult, Path]:
    """Run `test_source` under this repo's guard in a pytest subprocess whose
    real HOME is a throwaway directory; returns its result and data root."""
    pytester.makeconftest(_CONFTEST.read_text(encoding="utf-8"))
    pytester.makepyfile(test_guarded=textwrap.dedent(test_source))
    with tempfile.TemporaryDirectory() as real_home:
        monkeypatch.setenv("HOME", real_home)
        monkeypatch.setenv("USERPROFILE", real_home)
        monkeypatch.setenv("XDG_DATA_HOME", str(Path(real_home) / ".local" / "share"))
        result = pytester.runpytest_subprocess("-p", "no:cacheprovider")
        data_root = _data_root_for(Path(real_home))
        assert (data_root / "owners").is_dir()
    return result, data_root


def test_guard_fails_a_test_that_holds_a_new_real_root_owner_entry(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The entry was created by an exited child, so no write of this
    process recorded it; this process holding it open is enough."""
    result, data_root = _run_with_a_stand_in_real_home(
        pytester,
        monkeypatch,
        """
        import os
        import subprocess
        import sys

        import conftest

        HELD = []


        def test_holds_an_entry_a_child_created():
            lock = conftest._REAL_HOME_GUARD["data_root"] / "owners" / "tui:held.lock"
            make = (
                "import os, sys; os.makedirs(os.path.dirname(sys.argv[1]), exist_ok=True);"
                " open(sys.argv[1], 'w').close()"
            )
            subprocess.run([sys.executable, "-c", make, str(lock)], check=True)
            HELD.append(os.open(lock, os.O_RDONLY))
        """,
    )
    result.stdout.fnmatch_lines(
        [
            "*ERROR at teardown of test_holds_an_entry_a_child_created*",
            "*test_holds_an_entry_a_child_created wrote under the real Rush data root*",
            f"*{data_root / 'owners' / 'tui:held.lock'}*",
        ]
    )
    result.assert_outcomes(passed=1, errors=1)


def test_guard_fails_a_test_whose_exited_child_wrote_with_the_real_home(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A child given the real HOME resolves the real data root itself: no
    watched path appears in its arguments or environment, and it has exited
    (its lock released) by the time the test ends."""
    result, data_root = _run_with_a_stand_in_real_home(
        pytester,
        monkeypatch,
        """
        import os
        import subprocess
        import sys

        import conftest

        CHILD = (
            "import sys; from pathlib import Path; home = Path.home(); "
            "root = home / 'Library' / 'Application Support' / 'Rush' "
            "if sys.platform == 'darwin' else home / '.local' / 'share' / 'rush'; "
            "(root / 'owners').mkdir(parents=True, exist_ok=True); "
            "(root / 'owners' / 'hash:child.lock').touch()"
        )


        def test_child_with_the_real_home():
            env = {**os.environ, "HOME": str(conftest._REAL_HOME_GUARD["home"])}
            env.pop("XDG_DATA_HOME", None)
            subprocess.run([sys.executable, "-c", CHILD], env=env, check=True)


        def test_child_with_the_isolated_home():
            subprocess.run([sys.executable, "-c", CHILD], check=True)
        """,
    )
    result.stdout.fnmatch_lines(
        [
            "*ERROR at teardown of test_child_with_the_real_home*",
            "*test_child_with_the_real_home wrote under the real Rush data root*",
            f"*{data_root / 'owners' / 'hash:child.lock'}*",
        ]
    )
    assert "test_child_with_the_isolated_home wrote" not in result.stdout.str()
    result.assert_outcomes(passed=2, errors=1)
