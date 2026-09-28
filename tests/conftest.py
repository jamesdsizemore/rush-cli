"""Shared pytest fixtures.

Architecture §11.2.
"""

from __future__ import annotations

import hashlib
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
from collections.abc import Callable, Collection, Generator, Iterator, Mapping
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


# A `needs_<name>` marker needs the binary `<name>` (underscores as hyphens)
# on PATH, except where named here.
_BINARY_FOR_MARKER = {"needs_npm_audit": "npm"}


def _marker_binary(name: str) -> str:
    return _BINARY_FOR_MARKER.get(name, name.removeprefix("needs_").replace("_", "-"))


def _deselected_by(
    item: pytest.Item,
    *,
    is_windows: bool,
    is_linux_x86_64: bool,
    is_root: bool,
    which: Callable[[str], str | None],
) -> str | None:
    """The marker that deselects `item` here, or None to run it."""
    names = {marker.name for marker in item.iter_markers()}
    for name, off in (
        ("windows_only", not is_windows),
        ("atheris_only", not is_linux_x86_64),
        ("posix_only", is_windows),
        ("posix_nonroot", is_windows or is_root),
    ):
        if off and name in names:
            return name
    for name in sorted(names):
        if name.startswith("needs_") and which(_marker_binary(name)) is None:
            return name
    return None


_DESELECT_REASONS = {
    "windows_only": "not Windows",
    "atheris_only": "not Linux x86_64",
    "posix_only": "Windows",
    "posix_nonroot": "Windows or root",
}


def pytest_collection_modifyitems(config: pytest.Config, items: list) -> None:
    """Markers that cannot run here are deselected (never skipped), with a
    count per marker printed: the owner rule is zero SKIPPED tests anywhere.

    `windows_only`: only Windows can run it; the Windows CI job still
    collects and runs it (`os.name == "nt"` there).
    `atheris_only`: the real atheris fuzz engine has no macOS/Windows wheel,
    only Linux x86_64; CI's engine-contracts job (ubuntu x86_64) still
    collects and runs it.
    `posix_only` / `posix_nonroot`: POSIX-only fixtures (symlinks, shell
    scripts, ptys, permission bits); every POSIX CI job runs them as a
    non-root user.
    `needs_<binary>`: an optional external engine not on PATH; CI's
    static-tool-acceptance job installs and runs each one."""
    which_cache: dict[str, str | None] = {}

    def which(binary: str) -> str | None:
        if binary not in which_cache:
            which_cache[binary] = shutil.which(binary)
        return which_cache[binary]

    is_windows = os.name == "nt"
    is_linux_x86_64 = platform.system() == "Linux" and platform.machine() == "x86_64"
    is_root = hasattr(os, "geteuid") and os.geteuid() == 0
    keep, deselected = [], []
    counts: dict[str, int] = {}
    for item in items:
        name = _deselected_by(
            item,
            is_windows=is_windows,
            is_linux_x86_64=is_linux_x86_64,
            is_root=is_root,
            which=which,
        )
        if name is None:
            keep.append(item)
        else:
            deselected.append(item)
            counts[name] = counts.get(name, 0) + 1
    if not deselected:
        return
    config.hook.pytest_deselected(items=deselected)
    items[:] = keep
    reporter = config.pluginmanager.get_plugin("terminalreporter")
    for name, count in sorted(counts.items()):
        reason = _DESELECT_REASONS.get(name) or f"{_marker_binary(name)} not on PATH"
        line = f"{name}: {count} deselected ({reason})"
        if reporter is None:
            print(line, file=sys.stderr)
        else:
            reporter.write_line(line)


def _mcp_servers(path: Path) -> str:
    """The Rush-relevant content of `~/.claude.json` (top-level `mcpServers`
    plus each project's non-empty `mcpServers`) or `~/.codex/config.toml`
    (its `[mcp_servers.*]` tables), as canonical JSON, or "absent". Claude
    Code rewrites the rest of `~/.claude.json` while any session is open."""
    attempts = 10
    while True:
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            return "absent"
        try:
            text = raw.decode("utf-8")
            if path.suffix == ".toml":
                servers: object = tomllib.loads(text).get("mcp_servers", {})
            else:
                data = json.loads(text)
                projects = data.get("projects", {})
                servers = {
                    "mcpServers": data.get("mcpServers", {}),
                    "projects": {
                        project: entry["mcpServers"]
                        for project, entry in projects.items()
                        if isinstance(entry, dict) and entry.get("mcpServers")
                    },
                }
            return json.dumps(servers, sort_keys=True)
        except (ValueError, TypeError, AttributeError):
            # A read racing the owner's rewrite; the next one is whole. Still
            # malformed after the retries (not UTF-8, not JSON/TOML, not the
            # expected shape): a stable digest, never an error at startup.
            attempts -= 1
            if not attempts:
                return "unreadable:" + hashlib.sha256(raw).hexdigest()
            time.sleep(0.1)


def _real_home_snapshot(home: Path, data_root: Path) -> dict[str, str]:
    """Fingerprint of what tests must never change: the MCP server entries
    (or "absent") of `~/.claude.json` and `~/.codex/config.toml`, plus every
    path under the Rush data root and `~/.rush` (or "absent"), each file
    with its size and mtime_ns."""
    snapshot: dict[str, str] = {}
    for path in (home / ".claude.json", home / ".codex" / "config.toml"):
        snapshot[str(path)] = _mcp_servers(path)
    for root in (data_root, home / ".rush"):
        if not root.is_dir():
            snapshot[str(root)] = "absent"
            continue
        snapshot[str(root)] = "dir"
        for dirpath, dirnames, filenames in os.walk(root):
            for name in dirnames:
                snapshot[str(Path(dirpath) / name)] = "dir"
            for name in filenames:
                path = Path(dirpath) / name
                try:
                    stat = path.lstat()
                except FileNotFoundError:  # removed during the walk
                    continue
                snapshot[str(path)] = f"file:{stat.st_size}:{stat.st_mtime_ns}"
    return snapshot


def _changed_paths(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(
        p for p in before.keys() | after.keys() if before.get(p) != after.get(p)
    )


# Owner-liveness locks and project mutation locks: the per-test check
# attributes new entries here to a live child of this process.
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


def _session_changes(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """Every changed, appeared or removed path this pytest process caused:
    one its audit hook saw it write, create, rename onto or link, or one at
    or under a path it removed or handed to a child process. A change by an
    unrelated process (another worktree's test run, a real Rush TUI that has
    since exited) is not attributed."""
    trees = tuple(_SESSION_TREES)
    return [
        path
        for path in _changed_paths(before, after)
        if path in _SESSION_WRITES
        or any(path == tree or path.startswith(tree + os.sep) for tree in trees)
    ]


# Data-root prefixes (ending in os.sep) whose creates `_record_real_root_write`
# records, and the paths it recorded since the last per-test check.
_WATCHED_ROOTS: list[str] = []
_WRITTEN_IN_PROCESS: set[str] = set()
# Session-long, never consumed: exact paths written, and trees removed or
# handed to a child process (everything at or under them is attributed).
_SESSION_WRITES: set[str] = set()
_SESSION_TREES: set[str] = set()
# Set on a thread while `_held_by` runs lsof: the probe only reads the paths
# it is handed, so they are not attributed to this process.
_PROBING = threading.local()
# Set when this process started a child whose environment resolves the real
# data root (a real HOME): an entry that child created and released before
# the next check is attributed to the test. Consumed by that check.
_REAL_ROOT_CHILD = threading.Event()


def _resolves_real_data_root(env: object) -> bool:
    """Whether a child started with `env` (None: this process's own
    environment) resolves the real data root, per `default_data_root`."""
    child_env = os.environ if env is None else env
    if not isinstance(child_env, Mapping) or not _REAL_HOME_GUARD:
        return False
    if os.name == "nt":
        base = child_env.get("LOCALAPPDATA")
        root = Path(base) / "Rush" if base else None
    else:
        home = child_env.get("HOME")
        if not home:
            import pwd

            home = pwd.getpwuid(os.getuid()).pw_dir
        if sys.platform == "darwin":
            root = Path(home) / "Library" / "Application Support" / "Rush"
        else:
            xdg = child_env.get("XDG_DATA_HOME")
            root = (Path(xdg) if xdg else Path(home) / ".local" / "share") / "rush"
    return root == _REAL_HOME_GUARD["data_root"]


_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_TRUNC | os.O_APPEND


def _record_real_root_write(event: str, args: tuple[object, ...]) -> None:
    """F14 audit hook: remember every path under a watched root (the real
    data root, `~/.rush`) that this process creates or writes, from any
    thread, so the entry is attributable to this pytest process: an `open`
    that creates or writes, `mkdir`, a rename, link or symlink target, and
    a `sqlite3.connect` database."""
    if not _WATCHED_ROOTS or getattr(_PROBING, "active", False):
        return
    create_only = False
    if event == "open":
        mode, flags = args[1], args[2]
        if not isinstance(flags, int):
            return
        writes = bool(flags & _WRITE_FLAGS) or (
            isinstance(mode, str) and any(c in mode for c in "wax+")
        )
        if not writes and not flags & os.O_CREAT:
            return
        # Reopening an existing lock read-only with O_CREAT writes nothing.
        create_only = not writes
        path = args[0]
    elif event == "os.mkdir":
        create_only = True  # `mkdir(exist_ok=True)` on an existing dir
        path = args[0]
    elif event in ("os.rename", "os.link", "os.symlink"):
        path = args[1]
    elif event == "sqlite3.connect":
        path = args[0]
    elif event in ("os.remove", "os.rmdir", "shutil.rmtree"):
        _record_tree(args[0])
        return
    elif event == "os.fork":
        if _resolves_real_data_root(None):
            _REAL_ROOT_CHILD.set()
        return
    elif event == "subprocess.Popen":
        _, argv, cwd, env = args
        if _resolves_real_data_root(env):
            _REAL_ROOT_CHILD.set()
        values = list(argv) if isinstance(argv, (list, tuple)) else [argv]
        for value in (cwd, *values, *(env.values() if isinstance(env, dict) else ())):
            _record_tree(value)
        return
    else:
        return
    if not isinstance(path, (str, bytes, os.PathLike)):
        return
    text = os.fsdecode(os.fspath(path))
    # The event fires before the call.
    if text.startswith(tuple(_WATCHED_ROOTS)) and not (
        create_only and os.path.lexists(text)
    ):
        _WRITTEN_IN_PROCESS.add(os.path.normpath(text))
        _SESSION_WRITES.add(os.path.normpath(text))


def _record_tree(value: object) -> None:
    """Record `value` if it is a path at or under a watched root, else every
    watched path embedded in it (a `-c` code string, an env value): from each
    watched root up to the first quote, whitespace, `)`, `,` or the end."""
    if not isinstance(value, (str, bytes, os.PathLike)):
        return
    text = os.fsdecode(os.fspath(value))
    roots = tuple(_WATCHED_ROOTS)
    if (text + os.sep).startswith(roots):
        _SESSION_TREES.add(os.path.normpath(text))
        return
    for root in roots:
        start = text.find(root)
        while start != -1:
            end = start + len(root)
            while end < len(text) and not (text[end] in "'\")," or text[end].isspace()):
                end += 1
            _SESSION_TREES.add(os.path.normpath(text[start:end]))
            start = text.find(root, end)


def _ps_parents() -> dict[int, int]:
    """pid -> parent pid of every live process (empty without `ps`)."""
    ps = shutil.which("ps")
    if ps is None:
        return {}
    # The guard's own probe, run with the real HOME after a test: not a
    # child of the test.
    _PROBING.active = True
    try:
        listing = subprocess.run(
            [ps, "-A", "-o", "pid=,ppid="], capture_output=True, text=True, check=True
        ).stdout
    finally:
        _PROBING.active = False
    parents: dict[int, int] = {}
    for line in listing.splitlines():
        pid, ppid = (int(field) for field in line.split())
        parents[pid] = ppid
    return parents


def _descendant_pids(parents: dict[int, int] | None = None) -> set[int]:
    children: dict[int, list[int]] = {}
    for pid, ppid in (_ps_parents() if parents is None else parents).items():
        children.setdefault(ppid, []).append(pid)
    found: set[int] = set()
    stack = [os.getpid()]
    while stack:
        for child in children.get(stack.pop(), ()):
            if child not in found:
                found.add(child)
                stack.append(child)
    return found


def _held_by(paths: Collection[str], pids: Collection[int] | None) -> set[str]:
    """The paths one of `pids` (None: any process) holds open: an
    owner-liveness lock is held for its owner's whole lifetime."""
    lsof = shutil.which("lsof")
    if not paths or pids is not None and not pids or lsof is None:
        return set()
    # lsof exits 1 when no process has any of the files open.
    _PROBING.active = True
    try:
        fields = subprocess.run(
            [lsof, "-F", "pn", "--", *paths],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
    finally:
        _PROBING.active = False
    # lsof names files by their real path (/private/var on macOS).
    by_real_path = {os.path.realpath(path): path for path in paths}
    held: set[str] = set()
    pid = 0
    for line in fields.splitlines():
        if line.startswith("p"):
            pid = int(line[1:])
        elif (
            line.startswith("n")
            and (pids is None or pid in pids)
            and line[1:] in by_real_path
        ):
            held.add(by_real_path[line[1:]])
    return held


def _written_under(root: Path) -> set[str]:
    """Consume the recorded writes under `root` whose path still exists."""
    prefix = str(root) + os.sep
    # A copy: the audit hook adds to the set from other threads.
    written = {path for path in set(_WRITTEN_IN_PROCESS) if path.startswith(prefix)}
    _WRITTEN_IN_PROCESS.difference_update(written)
    return {path for path in written if os.path.lexists(path)}


def _created_entries(data_root: Path, before: set[str]) -> list[str]:
    """Entries this pytest process created or wrote under the data root since the
    last check and that still exist, plus new owners/ and project_locks/
    entries (outside `before`) that it or one of its children holds, and,
    after it started a child with the real data root, those no process
    holds (that child created and released them). Entries of unrelated
    processes are not attributed."""
    mine = _written_under(data_root)
    new = _watched_entries(data_root) - before - mine
    held = _held_by(new, _descendant_pids() | {os.getpid()})
    if _REAL_ROOT_CHILD.is_set():
        _REAL_ROOT_CHILD.clear()
        held |= new - _held_by(new - held, None)
    return sorted(mine | held)


_REAL_HOME_GUARD: dict[str, Path] = {}
_REAL_HOME_BEFORE: dict[str, str] = {}


def pytest_sessionstart(session: pytest.Session) -> None:
    """F14: record the real HOME before any fixture redirects it."""
    home = Path.home()
    data_root = default_data_root()
    _REAL_HOME_GUARD.update(home=home, data_root=data_root)
    _REAL_HOME_BEFORE.update(_real_home_snapshot(home, data_root))
    _WATCHED_ROOTS.extend(
        [
            str(data_root) + os.sep,
            str(home / ".rush") + os.sep,
            str(home / ".claude.json"),
            str(home / ".codex" / "config.toml"),
        ]
    )
    sys.addaudithook(_record_real_root_write)


# Every skipped report of this session: node id and phase.
_SKIPPED: list[str] = []


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Zero-skip rule: a skip in setup (a fixture), call (an in-body
    `pytest.skip` or `importorskip`) or teardown, and an xfail, is recorded."""
    if report.skipped:
        _SKIPPED.append(f"{report.nodeid} ({report.when})")


def pytest_collectreport(report: pytest.CollectReport) -> None:
    """Zero-skip rule: a module-level skip or `importorskip` is recorded."""
    if report.skipped:
        _SKIPPED.append(f"{report.nodeid} (collection)")


def _fail_session(session: pytest.Session, title: str, lines: list[str]) -> None:
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:
        print("\n".join([title, *lines]), file=sys.stderr)
    else:
        reporter.write_sep("=", title, red=True)
        for line in lines:
            reporter.write_line(line, red=True)
    session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """F14: fail the session, naming each path, if the real HOME changed.
    Zero-skip rule: fail it, naming each one, if anything was skipped."""
    if _SKIPPED:
        _fail_session(
            session,
            "ZERO SKIP GUARD",
            ["skipped (the owner rule is zero skips):", *_SKIPPED],
        )
    data_root = _REAL_HOME_GUARD["data_root"]
    after = _real_home_snapshot(_REAL_HOME_GUARD["home"], data_root)
    changed = _session_changes(_REAL_HOME_BEFORE, after)
    if changed:
        _fail_session(
            session, "REAL HOME GUARD", ["tests changed the real HOME:", *changed]
        )


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


@pytest.fixture(scope="session")
def _session_download_cache(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("shared-cache", numbered=False)


@pytest.fixture(autouse=True)
def _shared_download_cache(
    _session_download_cache: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every per-test HOME shares one session npm cache: the engine npm
    downloads (~370 MB into `$HOME/.npm`) happen once, not once per test.
    Separate from `_isolated_home` so a module that overrides that keeps it."""
    monkeypatch.setenv("npm_config_cache", str(_session_download_cache))


_ENTRIES_BEFORE = pytest.StashKey[set[str]]()
_THREADS_BEFORE = pytest.StashKey[set[threading.Thread]]()
# Shared deadline for joining the threads a test started and left running.
_THREAD_JOIN_SECONDS = 2.0


@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item: pytest.Item) -> Generator[None]:
    item.stash[_THREADS_BEFORE] = set(threading.enumerate())
    item.stash[_ENTRIES_BEFORE] = _watched_entries(_REAL_HOME_GUARD["data_root"])
    return (yield)


def _join_new_threads(before: set[threading.Thread]) -> None:
    """Give every thread started since `before` until one shared deadline to
    finish, so a write it makes after the test returns is still this test's."""
    deadline = time.monotonic() + _THREAD_JOIN_SECONDS
    for thread in set(threading.enumerate()) - before:
        if thread is not threading.current_thread():
            thread.join(max(0.0, deadline - time.monotonic()))


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item: pytest.Item) -> Generator[None]:
    """F14: fail, naming the test, when this pytest process (any thread) or
    a child it still runs created an entry under the real Rush data root
    since the previous test's check: in this test's setup (a session or
    module fixture included), call or teardown, or in a thread that
    outlived an earlier test. Runs once every fixture of the test is
    finalized, so no test's monkeypatch is still in effect."""

    def created_message() -> str:
        _join_new_threads(item.stash[_THREADS_BEFORE])
        created = _created_entries(
            _REAL_HOME_GUARD["data_root"], item.stash[_ENTRIES_BEFORE]
        ) + sorted(_written_under(_REAL_HOME_GUARD["home"] / ".rush"))
        if not created:
            return ""
        return "\n".join(
            [
                f"{item.nodeid} wrote under the real Rush data root or ~/.rush:",
                *created,
            ]
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
        'from rush.entry import main\n\nif __name__ == "__main__":\n    main()\n',
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
