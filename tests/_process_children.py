"""Real child-process helpers, replacing in-test os.fork()/pty.fork()/os.forkpty().

Forking this (multi-threaded) test process trips
`DeprecationWarning: This process is multi-threaded, use of fork()/forkpty()
may lead to deadlocks in the child` whenever another test has left a thread
alive. These helpers start a genuine child process via `subprocess.Popen`
instead -- calling a named module-level function with JSON-serializable
arguments -- so callers keep a real, killable, waitable child with none of
the deadlock risk.
"""

from __future__ import annotations

import json
import os
import pty
import subprocess
import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_SRC_DIR = _TESTS_DIR.parent / "src"

# ponytail: spawn_pty_child only hands back (pid, master_fd), so its local
# Popen would otherwise be garbage-collected while the child is still
# running -- Popen.__del__ then emits "subprocess N is still running"
# (ResourceWarning). Keeping a reference here avoids that; the OS-level
# child is still reaped by the caller's own os.waitpid on the returned pid.
_LIVE_PTY_CHILDREN: dict[int, subprocess.Popen] = {}


def _child_env(env: dict[str, str] | None) -> dict[str, str]:
    child_env = dict(env if env is not None else os.environ)
    existing = child_env.get("PYTHONPATH", "")
    parts = [str(_TESTS_DIR), str(_SRC_DIR), *([existing] if existing else [])]
    child_env["PYTHONPATH"] = os.pathsep.join(parts)
    return child_env


def _child_code(module: str, func: str, args: list) -> str:
    return (
        "import json\n"
        f"from {module} import {func}\n"
        f"{func}(*json.loads({json.dumps(json.dumps(args))}))\n"
    )


def spawn_child(
    module: str, func: str, args: list, *, env: dict[str, str] | None = None
) -> subprocess.Popen:
    """Run `func(*args)` from `module` in a real child process.

    `args` must be JSON-serializable; `module` must be importable with
    `tests/` and `src/` on `PYTHONPATH` (set automatically, merged with
    `env` if given).
    """
    return subprocess.Popen(
        [sys.executable, "-c", _child_code(module, func, args)],
        env=_child_env(env),
    )


def spawn_pty_child(
    module: str, func: str, args: list, *, env: dict[str, str] | None = None
) -> tuple[int, int]:
    """Run `func(*args)` in a child that claims the pty slave as its
    controlling terminal with TIOCSCTTY.

    Returns `(pid, master_fd)`: the parent reads/writes `master_fd` and
    waits on `pid`, the same shape callers got from `pty.fork()`.
    """
    master_fd, slave_fd = pty.openpty()
    code = (
        "import fcntl, termios\nfcntl.ioctl(0, termios.TIOCSCTTY, 0)\n"
        + _child_code(module, func, args)
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        env=_child_env(env),
        start_new_session=True,
        close_fds=True,
    )
    os.close(slave_fd)
    _LIVE_PTY_CHILDREN[proc.pid] = proc
    return proc.pid, master_fd
