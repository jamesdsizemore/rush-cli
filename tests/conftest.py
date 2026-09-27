"""Shared pytest fixtures.

Architecture §11.2.
"""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import tomllib
from collections.abc import Collection, Generator, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from rush.dashboard.server import stop_all_dashboard_contexts
from rush.runtime.binaries import clear_binary_cache
from rush.setup.provision import default_data_root

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_HOST_PATH = os.environ.get("PATH", "")
_POSIX_BASE_DIRS = ("/usr/bin", "/bin", "/usr/sbin", "/sbin")

_LEFT_SERVING = (
    "test left an HTTP server serving: call server.shutdown() before "
    "server.server_close()"
)


def _serving_threads() -> set[threading.Thread]:
    return {t for t in threading.enumerate() if "(serve_forever)" in t.name}


def pytest_collection_modifyitems(config: pytest.Config, items: list) -> None:
    """Platform-only markers are deselected (never skipped) off their
    platform: the owner rule is zero SKIPPED tests anywhere.

    `windows_only`: only Windows can run it; the Windows CI job still
    collects and runs it (`os.name == "nt"` there).
    `atheris_only`: the real atheris fuzz engine has no macOS/Windows wheel,
    only Linux x86_64; CI's engine-contracts job (ubuntu x86_64) still
    collects and runs it."""
    is_windows = os.name == "nt"
    is_linux_x86_64 = platform.system() == "Linux" and platform.machine() == "x86_64"
    keep, deselected = [], []
    for item in items:
        if (
            item.get_closest_marker("windows_only")
            and not is_windows
            or item.get_closest_marker("atheris_only")
            and not is_linux_x86_64
        ):
            deselected.append(item)
        else:
            keep.append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = keep


def _mcp_servers(path: Path) -> str:
    """The Rush-relevant content of `~/.claude.json` (top-level `mcpServers`
    plus each project's non-empty `mcpServers`) or `~/.codex/config.toml`
    (its `[mcp_servers.*]` tables), as canonical JSON, or "absent". Claude
    Code rewrites the rest of `~/.claude.json` while any session is open."""
    attempts = 10
    while True:
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return "absent"
        try:
            if path.suffix == ".toml":
                servers: object = tomllib.loads(text).get("mcp_servers", {})
            else:
                data = json.loads(text)
                servers = {
                    "mcpServers": data.get("mcpServers", {}),
                    "projects": {
                        project: entry["mcpServers"]
                        for project, entry in data.get("projects", {}).items()
                        if isinstance(entry, dict) and entry.get("mcpServers")
                    },
                }
            return json.dumps(servers, sort_keys=True)
        except (json.JSONDecodeError, tomllib.TOMLDecodeError):
            # A read racing the owner's rewrite; the next one is whole.
            attempts -= 1
            if not attempts:
                raise
            time.sleep(0.1)


def _real_home_snapshot(home: Path, data_root: Path) -> dict[str, str]:
    """Fingerprint of what tests must never change: the MCP server entries
    (or "absent") of `~/.claude.json` and `~/.codex/config.toml`, plus every
    path under the Rush data root (or "absent")."""
    snapshot: dict[str, str] = {}
    for path in (home / ".claude.json", home / ".codex" / "config.toml"):
        snapshot[str(path)] = _mcp_servers(path)
    if not data_root.is_dir():
        snapshot[str(data_root)] = "absent"
        return snapshot
    snapshot[str(data_root)] = "dir"
    for dirpath, dirnames, filenames in os.walk(data_root):
        for name in dirnames:
            snapshot[str(Path(dirpath) / name)] = "dir"
        for name in filenames:
            snapshot[str(Path(dirpath) / name)] = "file"
    return snapshot


def _changed_paths(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(
        p for p in before.keys() | after.keys() if before.get(p) != after.get(p)
    )


# Owner-liveness locks/`.procs` and project mutation locks: any Rush process
# on the machine (a running `rush mcp serve`, another worktree's suite) adds
# these, so only the per-test check, which attributes them, reports them.
_WATCHED_SUBDIRS = ("owners", os.path.join("dashboard", "project_locks"))


def _watched_entries(data_root: Path) -> set[str]:
    entries: set[str] = set()
    for sub in _WATCHED_SUBDIRS:
        try:
            entries.update(
                str(data_root / sub / name) for name in os.listdir(data_root / sub)
            )
        except FileNotFoundError:
            pass
    return entries


def _session_changes(
    before: dict[str, str], after: dict[str, str], data_root: Path
) -> list[str]:
    watched = tuple(str(data_root / sub) + os.sep for sub in _WATCHED_SUBDIRS)
    return [p for p in _changed_paths(before, after) if not p.startswith(watched)]


# Data-root prefixes (ending in os.sep) whose creates `_record_real_root_write`
# records, and the paths it recorded since the last per-test check.
_WATCHED_ROOTS: list[str] = []
_WRITTEN_IN_PROCESS: set[str] = set()


def _record_real_root_write(event: str, args: tuple[object, ...]) -> None:
    """F14 audit hook: remember every path under a watched data root that
    this process creates, from any thread, so a new entry there is
    attributable to this pytest process."""
    if not _WATCHED_ROOTS:
        return
    if event == "open":
        flags = args[2]
        if not isinstance(flags, int) or not flags & os.O_CREAT:
            return
        path = args[0]
    elif event == "os.mkdir":
        path = args[0]
    elif event == "os.rename":
        path = args[1]
    else:
        return
    if not isinstance(path, (str, bytes, os.PathLike)):
        return
    text = os.fsdecode(os.fspath(path))
    # The event fires before the call: an existing path is not a create
    # (`mkdir(exist_ok=True)`, reopening a lock with O_CREAT).
    if text.startswith(tuple(_WATCHED_ROOTS)) and not os.path.lexists(text):
        _WRITTEN_IN_PROCESS.add(os.path.normpath(text))


def _descendant_pids() -> set[int]:
    ps = shutil.which("ps")
    if ps is None:
        return set()
    listing = subprocess.run(
        [ps, "-A", "-o", "pid=,ppid="], capture_output=True, text=True, check=True
    ).stdout
    children: dict[int, list[int]] = {}
    for line in listing.splitlines():
        pid, ppid = (int(field) for field in line.split())
        children.setdefault(ppid, []).append(pid)
    found: set[int] = set()
    stack = [os.getpid()]
    while stack:
        for child in children.get(stack.pop(), ()):
            if child not in found:
                found.add(child)
                stack.append(child)
    return found


def _held_by_descendants(paths: Collection[str]) -> set[str]:
    """The paths a live child (or deeper descendant) of this process holds
    open: an owner-liveness lock is held for its owner's whole lifetime."""
    lsof = shutil.which("lsof")
    if not paths or lsof is None:
        return set()
    pids = _descendant_pids()
    if not pids:
        return set()
    # lsof exits 1 when no process has any of the files open.
    fields = subprocess.run(
        [lsof, "-F", "pn", "--", *paths], capture_output=True, text=True, check=False
    ).stdout
    # lsof names files by their real path (/private/var on macOS).
    by_real_path = {os.path.realpath(path): path for path in paths}
    held: set[str] = set()
    pid = 0
    for line in fields.splitlines():
        if line.startswith("p"):
            pid = int(line[1:])
        elif line.startswith("n") and pid in pids and line[1:] in by_real_path:
            held.add(by_real_path[line[1:]])
    return held


def _created_entries(data_root: Path, before: set[str]) -> list[str]:
    """Entries this pytest process created under the data root since the
    last check and that still exist, plus new owners/ and project_locks/
    entries (outside `before`) that one of its children holds. Entries of
    unrelated processes are not attributed."""
    root = str(data_root) + os.sep
    # A copy: the audit hook adds to the set from other threads.
    written = {path for path in set(_WRITTEN_IN_PROCESS) if path.startswith(root)}
    _WRITTEN_IN_PROCESS.difference_update(written)
    mine = {path for path in written if os.path.lexists(path)}
    new = _watched_entries(data_root) - before - mine
    return sorted(mine | _held_by_descendants(new))


_REAL_HOME_GUARD: dict[str, Path] = {}
_REAL_HOME_BEFORE: dict[str, str] = {}


def pytest_sessionstart(session: pytest.Session) -> None:
    """F14: record the real HOME before any fixture redirects it."""
    home = Path.home()
    data_root = default_data_root()
    _REAL_HOME_GUARD.update(home=home, data_root=data_root)
    _REAL_HOME_BEFORE.update(_real_home_snapshot(home, data_root))
    _WATCHED_ROOTS.append(str(data_root) + os.sep)
    sys.addaudithook(_record_real_root_write)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """F14: fail the session, naming each path, if the real HOME changed."""
    data_root = _REAL_HOME_GUARD["data_root"]
    after = _real_home_snapshot(_REAL_HOME_GUARD["home"], data_root)
    changed = _session_changes(_REAL_HOME_BEFORE, after, data_root)
    if not changed:
        return
    lines = ["tests changed the real HOME:", *changed]
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:
        print("\n".join(lines), file=sys.stderr)
    else:
        reporter.write_sep("=", "REAL HOME GUARD", red=True)
        for line in lines:
            reporter.write_line(line, red=True)
    session.exitstatus = pytest.ExitCode.TESTS_FAILED


@pytest.fixture(autouse=True)
def _isolated_home(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F14: every test gets a temporary HOME and XDG/AppData dirs; a test
    that sets its own HOME later through `monkeypatch` wins."""
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / ".local" / "share"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / ".cache"))
    if os.name == "nt":
        monkeypatch.setenv("USERPROFILE", str(home))
        monkeypatch.setenv("APPDATA", str(home / "AppData" / "Roaming"))
        monkeypatch.setenv("LOCALAPPDATA", str(home / "AppData" / "Local"))


_ENTRIES_BEFORE = pytest.StashKey[set[str]]()


@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item: pytest.Item) -> Generator[None]:
    item.stash[_ENTRIES_BEFORE] = _watched_entries(_REAL_HOME_GUARD["data_root"])
    return (yield)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item: pytest.Item) -> Generator[None]:
    """F14: fail, naming the test, when this pytest process (any thread) or
    a child it still runs created an entry under the real Rush data root
    since the previous test's check: in this test's setup (a session or
    module fixture included), call or teardown, or in a thread that
    outlived an earlier test. Runs once every fixture of the test is
    finalized, so no test's monkeypatch is still in effect."""

    def created_message() -> str:
        created = _created_entries(
            _REAL_HOME_GUARD["data_root"], item.stash[_ENTRIES_BEFORE]
        )
        if not created:
            return ""
        return "\n".join(
            [f"{item.nodeid} created under the real Rush data root:", *created]
        )

    try:
        result = yield
    except BaseException as exc:
        message = created_message()
        if message:
            exc.add_note(message)
        raise
    message = created_message()
    if message:
        pytest.fail(message, pytrace=False)
    return result


@pytest.fixture(autouse=True)
def _stop_dashboard_background_threads():
    """T028: every DashboardContext spawns recovery/outcome background
    threads that outlive the test if nothing stops them. Stopping only in
    a handful of test files' own fixtures let the rest leak, and leaked
    threads accumulating across a single pytest process caused full-suite
    hangs (see T027). Autouse here covers every test in the suite.

    A `serve_forever` thread this test started must also be gone: closing
    the socket without `server.shutdown()` leaves the loop spinning on a
    dead selector for the rest of the session."""
    before = _serving_threads()
    yield
    stop_all_dashboard_contexts()
    leaked = [t for t in _serving_threads() - before if t.is_alive()]
    for thread in leaked:
        thread.join(1.0)
    if any(thread.is_alive() for thread in leaked):
        pytest.fail(_LEFT_SERVING, pytrace=False)


def _engine_binaries() -> set[str]:
    from rush.catalog import ENGINE_SPECS
    from rush.engines import ENGINES

    return {spec.binary for spec in ENGINE_SPECS.values()} | {
        engine.binary for engine in ENGINES.values()
    }


@contextmanager
def _hermetic_engine_path(bin_dir: Path) -> Iterator[None]:
    """PATH reduced to `git` plus the OS base directories, so a scan resolves
    only the engines pinned in this venv (`resolve_binary` checks the
    interpreter's own bin first) instead of whatever the host has installed.
    On POSIX the base directories are mirrored into `bin_dir` minus every
    Rush engine binary: a runner image ships engines there too (ubuntu's
    `/usr/bin/mvn` runs the pitest candidate). PATH and the
    binary-resolution cache are restored on exit."""
    git = shutil.which("git")
    assert git is not None, "git must be on PATH"
    if os.name == "nt":
        system_root = os.environ["SystemRoot"]
        entries = [
            str(Path(git).parent),
            os.path.join(system_root, "System32"),
            system_root,
        ]
    else:
        bin_dir.mkdir(parents=True, exist_ok=True)
        (bin_dir / "git").symlink_to(git)
        hidden = _engine_binaries()
        for base in _POSIX_BASE_DIRS:
            if not os.path.isdir(base):
                continue
            for entry in os.scandir(base):
                link = bin_dir / entry.name
                if entry.name in hidden or os.path.lexists(link):
                    continue
                if os.path.isfile(entry.path) and os.access(entry.path, os.X_OK):
                    link.symlink_to(entry.path)
        entries = [str(bin_dir)]
    clear_binary_cache()
    try:
        with pytest.MonkeyPatch.context() as patch:
            patch.setenv("PATH", os.pathsep.join(entries))
            yield
    finally:
        clear_binary_cache()


@pytest.fixture
def hermetic_engine_path(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    # Its own directory, never inside the test's `tmp_path` (a test may use
    # that as a Git work tree, where an extra entry makes it dirty).
    with _hermetic_engine_path(tmp_path_factory.mktemp("hermetic-bin")):
        yield


@pytest.fixture
def host_engine_path(hermetic_engine_path: None) -> Iterator[None]:
    """For a live-engine test in a module marked `hermetic_engine_path`:
    PATH is the host's again (as when the session started), so the test
    runs the real engine it exists to exercise."""
    clear_binary_cache()
    try:
        with pytest.MonkeyPatch.context() as patch:
            patch.setenv("PATH", _HOST_PATH)
            yield
    finally:
        clear_binary_cache()


@pytest.fixture(scope="module")
def hermetic_engine_path_module(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[None]:
    with _hermetic_engine_path(tmp_path_factory.mktemp("hermetic-bin")):
        yield


@pytest.fixture(scope="session")
def native_release_archive(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """This platform's release archive, with its `SHA256SUMS` beside it,
    built once per session from the current source into a session temp dir
    -- the release workflow's PyInstaller build, which CI's quality/windows
    jobs also run. Never the repo's gitignored `dist/`, which may hold an
    archive built from older source."""
    import rush
    from scripts.probe_installed_artifacts import (
        build_release_archive,
        select_platform_asset,
        write_sha256sums,
    )

    build = tmp_path_factory.mktemp("pyinstaller")
    entry = build / "rush_entry.py"
    entry.write_text(
        'from rush.cli import cli\n\nif __name__ == "__main__":\n    cli()\n',
        encoding="utf-8",
    )
    if importlib.util.find_spec("PyInstaller") is not None:
        # CI's jobs `uv pip install pyinstaller` into the venv itself.
        pyinstaller = [sys.executable, "-m", "PyInstaller"]
    else:
        uv = shutil.which("uv")
        assert uv is not None, "building the native archive needs PyInstaller or uv"
        pyinstaller = [uv, "run", "--no-sync", "--with", "pyinstaller", "pyinstaller"]
    result = subprocess.run(
        [
            *pyinstaller,
            "--onefile",
            "--noconfirm",
            "--name",
            "rush",
            "--paths",
            str(PROJECT_ROOT / "src"),
            "--collect-data",
            "license_expression",
            "--collect-data",
            "rush.integrations",
            "--distpath",
            str(build / "bin"),
            "--workpath",
            str(build / "work"),
            "--specpath",
            str(build),
            str(entry),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"PyInstaller build failed:\n{result.stderr}"
    binary = build / "bin" / ("rush.exe" if os.name == "nt" else "rush")
    out = tmp_path_factory.mktemp("release-archive")
    archive = build_release_archive(
        binary,
        out,
        select_platform_asset(platform.system(), platform.machine()),
        rush.__version__,
    )
    write_sha256sums([archive], out / "SHA256SUMS")
    return archive


@pytest.fixture(scope="session")
def distribution_artifacts(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, Path]:
    """This version's `(wheel, sdist)`, built once per session from the
    current source with `uv build` (CI's build step) into a session temp dir
    -- never the repo's gitignored `dist/`, which may hold older builds."""
    import rush

    uv = shutil.which("uv")
    assert uv is not None, "building the wheel and sdist needs uv"
    out = tmp_path_factory.mktemp("distributions")
    result = subprocess.run(
        [uv, "build", "--out-dir", str(out)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"uv build failed:\n{result.stderr}"
    wheels = sorted(out.glob(f"rush_cli-{rush.__version__}-*.whl"))
    sdists = sorted(out.glob(f"rush_cli-{rush.__version__}.tar.gz"))
    assert len(wheels) == 1 and len(sdists) == 1, sorted(out.iterdir())
    return wheels[0], sdists[0]


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """A temp directory with a sample Python file and a sample TS file.

    The Python file has one clean function and one with a TODO (so review
    heuristics can flag it). The TS file is intentionally empty so we can
    later add a sample that prettier/eslint would flag.

    Phase 3: just the fixture exists; Phase 4 adds content.
    """
    repo = tmp_path / "rush-fixture"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "fixture"\n')
    (repo / "sample.py").write_text(
        "def clean(x: int) -> int:\n"
        '    """double x."""\n'
        "    return x * 2\n"
        "\n"
        "def dirty(x):  # no docstring, TODO, no annotation\n"
        "    # TODO: refactor\n"
        "    return x * 2\n"
    )
    return repo


@pytest.fixture
def skip_if_no():
    """Factory: `skip_if_no("ruff")(test_fn)` → skips test if ruff not on PATH."""
    import pytest

    def _factory(binary: str):
        return pytest.mark.skipif(
            shutil.which(binary) is None,
            reason=f"{binary} not on PATH",
        )

    return _factory
