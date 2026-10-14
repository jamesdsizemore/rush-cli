"""RED guard for W1: no test spawns a child via os.fork()/pty.fork()/os.forkpty(),
and the process-children helpers never trip Python's multi-threaded fork
DeprecationWarning even with a background thread alive."""

from __future__ import annotations

import os
import threading
import time
import tokenize
import warnings
from pathlib import Path

from _process_children import spawn_child, spawn_pty_child

_TESTS_DIR = Path(__file__).resolve().parent
_FORK_CALLS = {("os", "fork"), ("pty", "fork"), ("os", "forkpty")}


def test_no_test_file_contains_a_raw_fork_call() -> None:
    """Every `os.fork(`, `pty.fork(` or `os.forkpty(` call in any file under
    tests/, found by tokens, so comments and strings never count and a call
    in any form (assigned or not) always does."""
    offenders = []
    for path in sorted(_TESTS_DIR.rglob("*.py")):
        with path.open("rb") as handle:
            tokens = [
                t
                for t in tokenize.tokenize(handle.readline)
                if t.type in (tokenize.NAME, tokenize.OP)
            ]
        for a, dot, b, paren in zip(tokens, tokens[1:], tokens[2:], tokens[3:]):
            if (a.string, b.string) in _FORK_CALLS and (dot.string, paren.string) == (
                ".",
                "(",
            ):
                rel = path.relative_to(_TESTS_DIR)
                offenders.append(f"{rel}:{a.start[0]}: {a.line.strip()}")
    assert offenders == []


def _sleep_briefly(seconds: float) -> None:
    time.sleep(seconds)


def test_spawn_child_raises_no_deprecation_warning_with_a_background_thread_alive() -> (
    None
):
    stop = threading.Event()
    bg = threading.Thread(target=stop.wait)
    bg.start()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            proc = spawn_child(__name__, "_sleep_briefly", [0.05])
        try:
            assert proc.wait(timeout=5) == 0
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
    finally:
        stop.set()
        bg.join()


def test_spawn_pty_child_raises_no_deprecation_warning_with_a_background_thread_alive() -> (
    None
):
    stop = threading.Event()
    bg = threading.Thread(target=stop.wait)
    bg.start()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            pid, master_fd = spawn_pty_child(__name__, "_sleep_briefly", [0.05])
        try:
            _, status = os.waitpid(pid, 0)
            assert status == 0
        finally:
            os.close(master_fd)
    finally:
        stop.set()
        bg.join()
