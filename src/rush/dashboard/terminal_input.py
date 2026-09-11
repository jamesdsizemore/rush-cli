"""Bounded POSIX/Windows terminal input, size, and raw-mode handling for the
persistent interactive TUI (P66-03, F36).

Every function here is bounded to real terminal I/O primitives (`termios`,
`tty`, `msvcrt`, `shutil.get_terminal_size`) -- never a subprocess or shell
command. `raw_terminal()` is the single seam responsible for restoring the
caller's terminal to its original state, on a clean exit AND on any
exception propagating out of the `with` block.
"""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import ClassVar, Protocol

# Logical key names the TUI event loop understands. Anything else read from
# the terminal is passed through as the literal single character typed.
ESCAPE = "escape"
ENTER = "enter"
TAB = "tab"
UP = "up"
DOWN = "down"
LEFT = "left"
RIGHT = "right"
BACKSPACE = "backspace"

_POSIX = os.name == "posix"


class KeyReader(Protocol):
    """Injectable seam: production code gets a real reader from
    `make_key_reader()`; tests inject a scripted fake."""

    def read_key(self, timeout: float) -> str | None: ...

    def get_size(self) -> tuple[int, int]: ...


class _HasFileno(Protocol):
    """Structural type for anything with a real `.fileno()` -- a file
    object, `sys.stdin`, or a test's `os.fdopen` handle. Lets `_resolve_fd`
    narrow past `int`/`None` without an `object`-typed dead end."""

    def fileno(self) -> int: ...


def get_terminal_size(fallback: tuple[int, int] = (80, 24)) -> tuple[int, int]:
    """Returns (columns, rows). Never raises, even when detached from a
    real tty (pipes, CI) -- `shutil.get_terminal_size` already falls back
    to `fallback` in that case."""
    size = shutil.get_terminal_size(fallback=fallback)
    return (size.columns, size.lines)


def _resolve_fd(target: int | _HasFileno | None) -> int:
    """Resolves to a raw file descriptor, never through a `sys.stdin`
    Python-level object that some hosting environment (test runners,
    IDEs) may have replaced with a non-fd-backed proxy -- fd 0 itself is
    unaffected by that kind of Python-level swap, so reading/raw-mode
    always tracks the real terminal underneath."""
    if isinstance(target, int):
        return target
    if target is not None:
        return target.fileno()
    try:
        return sys.stdin.fileno()
    except (AttributeError, OSError, ValueError):
        return 0


@contextmanager
def raw_terminal(stream: int | _HasFileno | None = None) -> Iterator[None]:
    """POSIX cbreak-mode context manager. Restores the original terminal
    attributes in `finally` -- on a clean exit AND on any exception -- so a
    scan crash or an unhandled bug never leaves the caller's shell in raw
    mode. No-op on non-POSIX platforms or when the resolved fd isn't a
    real tty (unit tests, pipes, CI)."""
    fd = _resolve_fd(stream)
    if not _POSIX or not os.isatty(fd):
        yield
        return

    import termios
    import tty

    original = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, original)


class PosixKeyReader:
    """Reads one logical key at a time from a POSIX tty already placed in
    cbreak mode by `raw_terminal`. A bare Escape press is distinguished
    from an arrow/function-key escape sequence by a short (50ms) follow-up
    read -- never a blocking read that could hang the event loop."""

    _SEQUENCES: ClassVar[dict[str, str]] = {
        "[A": UP,
        "[B": DOWN,
        "[C": RIGHT,
        "[D": LEFT,
    }

    def __init__(self, stream: int | _HasFileno | None = None) -> None:
        self._fd = _resolve_fd(stream)

    def get_size(self) -> tuple[int, int]:
        return get_terminal_size()

    def read_key(self, timeout: float) -> str | None:
        import select

        fd = self._fd
        ready, _, _ = select.select([fd], [], [], timeout)
        if not ready:
            return None
        raw = os.read(fd, 1)
        if not raw:
            return None
        ch = raw.decode(errors="replace")
        if ch == "\x1b":
            ready, _, _ = select.select([fd], [], [], 0.05)
            if not ready:
                return ESCAPE
            rest = os.read(fd, 2).decode(errors="replace")
            return self._SEQUENCES.get(rest, ESCAPE)
        if ch in ("\r", "\n"):
            return ENTER
        if ch == "\t":
            return TAB
        if ch in ("\x7f", "\x08"):
            return BACKSPACE
        if (
            ch == "\x03"
        ):  # Ctrl+C: treat like Escape, never raise KeyboardInterrupt mid-render
            return ESCAPE
        return ch


class WindowsKeyReader:
    """Reads one logical key using `msvcrt` -- no raw-mode toggle needed;
    `msvcrt.getwch` already returns one character at a time without echo
    or line buffering on the Windows console."""

    _ARROW: ClassVar[dict[str, str]] = {"H": UP, "P": DOWN, "K": LEFT, "M": RIGHT}

    def get_size(self) -> tuple[int, int]:
        return get_terminal_size()

    def read_key(self, timeout: float) -> str | None:
        import time

        # `msvcrt` only exists on win32; typeshed gates its whole stub
        # behind this exact check, so mypy treats the body as unreachable
        # (and skips checking it) on every other `--python-platform`,
        # including this dev machine's darwin. This class is only ever
        # constructed by `make_key_reader()` on `os.name == "nt"`.
        if sys.platform != "win32":  # pragma: no cover - Windows-only path
            return None
        import msvcrt

        deadline = time.monotonic() + timeout
        while True:
            if msvcrt.kbhit():
                ch = msvcrt.getwch()
                if ch in ("\x00", "\xe0"):
                    ch2 = msvcrt.getwch()
                    return self._ARROW.get(ch2, ESCAPE)
                if ch == "\r":
                    return ENTER
                if ch == "\t":
                    return TAB
                if ch == "\x1b":
                    return ESCAPE
                if ch == "\x08":
                    return BACKSPACE
                return ch
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            time.sleep(min(0.01, remaining))


def make_key_reader(stream: int | _HasFileno | None = None) -> KeyReader:
    """Bounded factory: platform choice comes only from `os.name`, never
    from probing or executing an external command."""
    if os.name == "nt":
        return WindowsKeyReader()
    return PosixKeyReader(stream)
