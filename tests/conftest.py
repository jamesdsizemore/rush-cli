"""Shared pytest fixtures.

Architecture §11.2.
"""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import subprocess
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from rush.dashboard.server import stop_all_dashboard_contexts
from rush.runtime.binaries import clear_binary_cache

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_HOST_PATH = os.environ.get("PATH", "")
_POSIX_BASE_DIRS = ("/usr/bin", "/bin", "/usr/sbin", "/sbin")

_LEFT_SERVING = (
    "test left an HTTP server serving: call server.shutdown() before "
    "server.server_close()"
)


def _serving_threads() -> set[threading.Thread]:
    return {t for t in threading.enumerate() if "(serve_forever)" in t.name}


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
