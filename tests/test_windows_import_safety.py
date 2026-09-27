"""Every `rush` module imports on Windows, where POSIX-only stdlib modules
(`fcntl`, `termios`, ...) do not exist. A module-level import of one breaks
Rush itself there (and `tests/conftest.py`), not only one feature.

Simulated on this host in a fresh interpreter: stdlib and third-party
dependencies load first under the real platform (their own platform
branches are not Rush's), then the POSIX-only modules are made unimportable
and `sys.platform` reads `win32` while every `rush` module is imported."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap

POSIX_ONLY = ("fcntl", "termios", "tty", "pwd", "grp", "resource")

_LIST_RUSH_MODULES = textwrap.dedent(
    """
    import importlib, json, pkgutil, sys
    import rush
    names = [info.name for info in pkgutil.walk_packages(rush.__path__, "rush.")]
    for name in names:
        importlib.import_module(name)
    deps = sorted(
        m for m in sys.modules
        if m != "rush" and not m.startswith("rush.") and m != "__main__"
    )
    print(json.dumps({"rush": names, "deps": deps}))
    """
)

_IMPORT_AS_WINDOWS = textwrap.dedent(
    """
    import importlib, json, sys
    spec = json.loads(sys.stdin.read())
    for name in spec["deps"]:
        if name.split(".")[0] not in spec["posix_only"]:
            try:
                importlib.import_module(name)
            except Exception:
                pass
    for name in spec["posix_only"]:
        sys.modules[name] = None  # `import name` now raises ImportError
    sys.platform = "win32"
    failures = []
    for name in ["rush", *spec["rush"]]:
        try:
            importlib.import_module(name)
        except Exception as exc:
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
    print("\\n".join(failures))
    sys.exit(1 if failures else 0)
    """
)


def _python(code: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", code],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def test_every_rush_module_imports_without_posix_only_modules() -> None:
    listed = _python(_LIST_RUSH_MODULES)
    assert listed.returncode == 0, listed.stderr
    spec = json.loads(listed.stdout.splitlines()[-1])
    assert len(spec["rush"]) > 100
    spec["posix_only"] = list(POSIX_ONLY)

    proc = _python(_IMPORT_AS_WINDOWS, json.dumps(spec))

    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_probe_detects_a_module_level_posix_import() -> None:
    """The simulation is live: a module-level `import fcntl` fails under it."""
    spec = {"rush": [], "deps": [], "posix_only": list(POSIX_ONLY)}
    probe = _IMPORT_AS_WINDOWS.replace(
        'for name in ["rush", *spec["rush"]]:', 'for name in ["fcntl", "termios"]:'
    )

    proc = _python(probe, json.dumps(spec))

    assert proc.returncode == 1
    assert "fcntl: ModuleNotFoundError" in proc.stdout
    assert "termios: ModuleNotFoundError" in proc.stdout
