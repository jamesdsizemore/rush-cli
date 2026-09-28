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
from contextlib import contextmanager, suppress
from typing import ClassVar, Protocol

# Logical key names the TUI event loop understands. Anything else read from
# the terminal is passed through as the literal single character typed.
ESCAPE = "escape"
ENTER = "enter"
TAB = "tab"
SHIFT_TAB = "shift_tab"
UP = "up"
DOWN = "down"
LEFT = "left"
RIGHT = "right"
BACKSPACE = "backspace"
# The input stream reached end-of-file (the terminal/pty closed): a distinct
# logical key so the event loop can react instead of polling a dead fd.
EOF = "eof"
# A bracketed paste (POSIX `ESC[200~ ... ESC[201~`) or a multi-character
# Windows console drain arrives as ONE event: this prefix plus the pasted
# text, literal and uninterpreted -- never a sequence of individual keys.
PASTE_PREFIX = "paste:"
# ponytail: fixed cap on retained paste payload (bytes on POSIX, characters
# on Windows); anything past it is still consumed and discarded so it can
# never leak out as keystrokes. Raise it if real pastes need more.
_PASTE_MAX = 64 * 1024
_BRACKETED_PASTE_ON = b"\x1b[?2004h"
_BRACKETED_PASTE_OFF = b"\x1b[?2004l"
_PASTE_END = b"\x1b[201~"

_POSIX = os.name == "posix"

# U01 fix: the read side of `raw_terminal`'s SIGWINCH wakeup pipe, set only
# while a real POSIX tty's `with raw_terminal():` block is active (`None`
# otherwise). `PosixKeyReader.read_key` selects on it alongside the real
# input fd so a resize interrupts an in-progress poll immediately instead of
# waiting out the remaining timeout.
_ACTIVE_WAKEUP_FD: list[int | None] = [None]


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
    real tty (unit tests, pipes, CI).

    U01 fix: also wires a self-pipe as the process's SIGWINCH wakeup fd
    (`signal.set_wakeup_fd`) for the duration of the block, so
    `PosixKeyReader.read_key`'s `selectors` wait wakes immediately on a
    real resize instead of waiting out its poll timeout. The prior signal
    handler and wakeup fd are restored, and both pipe descriptors closed,
    in `finally` -- on a clean exit AND on any exception, same as the
    termios restore this context manager already guaranteed."""
    fd = _resolve_fd(stream)
    if not _POSIX or not os.isatty(fd):
        yield
        return
    if (
        sys.platform == "win32"
    ):  # pragma: no cover - unreachable, _POSIX excludes win32 above; satisfies mypy's per-platform stub check
        yield
        return

    import signal
    import termios
    import tty

    original = termios.tcgetattr(fd)
    wakeup_read, wakeup_write = os.pipe()
    os.set_blocking(wakeup_write, False)
    prior_wakeup_fd = signal.set_wakeup_fd(wakeup_write)
    prior_handler = signal.getsignal(signal.SIGWINCH)
    try:
        # The wakeup fd alone delivers the notification `read_key` selects
        # on; the handler itself only needs to exist so the signal doesn't
        # terminate the process (Python requires one registered to arm
        # `set_wakeup_fd`'s delivery for a signal that isn't already
        # ignored/default-handled).
        signal.signal(signal.SIGWINCH, lambda *_: None)
        tty.setcbreak(fd)
        # Bracketed paste: the terminal wraps pasted text in
        # `ESC[200~ ... ESC[201~` so `PosixKeyReader` can deliver it as one
        # literal paste event instead of executing it as keystrokes.
        with suppress(OSError):
            os.write(fd, _BRACKETED_PASTE_ON)
        _ACTIVE_WAKEUP_FD[0] = wakeup_read
        yield
    finally:
        _ACTIVE_WAKEUP_FD[0] = None
        with suppress(OSError):
            os.write(fd, _BRACKETED_PASTE_OFF)
        with suppress(OSError, ValueError):
            signal.set_wakeup_fd(prior_wakeup_fd)
        with suppress(OSError, ValueError):
            signal.signal(signal.SIGWINCH, prior_handler)
        with suppress(OSError):
            os.close(wakeup_read)
        with suppress(OSError):
            os.close(wakeup_write)
        # TCSANOW, not TCSADRAIN: the bracketed-paste disable just written
        # must not block the restore until the terminal side reads it (a
        # stalled reader would otherwise leave the shell in cbreak mode).
        # cbreak never changes output flags, so queued output is unaffected.
        termios.tcsetattr(fd, termios.TCSANOW, original)


class PosixKeyReader:
    """Reads one logical key at a time from a POSIX tty already placed in
    cbreak mode by `raw_terminal`. A bare Escape press is distinguished
    from an arrow/function-key escape sequence by a short (50ms) follow-up
    read -- never a blocking read that could hang the event loop."""

    # CSI body (everything after ESC "[") for each logical key this reader
    # decodes -- arrows, Shift+Tab (`CSI Z`, the real xterm sequence), and
    # the numeric-tilde function-key family (`CSI 1 1 ~` .. `CSI 2 4 ~`,
    # the common convention across xterm-compatible terminals for F1-F12).
    _SEQUENCES: ClassVar[dict[str, str]] = {
        "[A": UP,
        "[B": DOWN,
        "[C": RIGHT,
        "[D": LEFT,
        "[Z": SHIFT_TAB,
        "[11~": "f1",
        "[12~": "f2",
        "[13~": "f3",
        "[14~": "f4",
        "[15~": "f5",
        "[17~": "f6",
        "[18~": "f7",
        "[19~": "f8",
        "[20~": "f9",
        "[21~": "f10",
        "[23~": "f11",
        "[24~": "f12",
        # Linux console F1-F5 (`ESC [ [ A..E`).
        "[[A": "f1",
        "[[B": "f2",
        "[[C": "f3",
        "[[D": "f4",
        "[[E": "f5",
    }

    # SS3 body (the byte after ESC "O"): F1-F4 and application-mode arrows,
    # as sent by Terminal.app, iTerm2, and xterm.
    _SS3: ClassVar[dict[str, str]] = {
        "P": "f1",
        "Q": "f2",
        "R": "f3",
        "S": "f4",
        "A": UP,
        "B": DOWN,
        "C": RIGHT,
        "D": LEFT,
    }

    def __init__(self, stream: int | _HasFileno | None = None) -> None:
        self._fd = _resolve_fd(stream)

    def get_size(self) -> tuple[int, int]:
        return get_terminal_size()

    def read_key(self, timeout: float) -> str | None:
        import selectors

        fd = self._fd
        wakeup_fd = _ACTIVE_WAKEUP_FD[0]
        sel = selectors.DefaultSelector()
        # ponytail: a fresh selector per call is the simplest correct
        # option for a bounded, short-timeout poll; upgrade to a
        # persistent selector reused across calls if per-tick allocation
        # measurably matters.
        try:
            sel.register(fd, selectors.EVENT_READ)
            if wakeup_fd is not None:
                sel.register(wakeup_fd, selectors.EVENT_READ)
            events = sel.select(timeout)
        finally:
            sel.close()
        if not events:
            return None
        ready_fds = {key.fd for key, _ in events}
        if fd not in ready_fds:
            # Only the SIGWINCH wakeup fd fired -- drain it and return
            # immediately so the caller's tick loop re-checks terminal
            # size right away instead of waiting out the rest of `timeout`.
            if wakeup_fd is not None:
                with suppress(OSError):
                    os.read(wakeup_fd, 8)
            return None
        raw = os.read(fd, 1)
        if not raw:
            return EOF
        first = raw[0]
        if first == 0x1B:  # ESC
            return self._read_escape_sequence(fd)
        if first in (0x0D, 0x0A):
            return ENTER
        if first == 0x09:
            return TAB
        if first in (0x7F, 0x08):
            return BACKSPACE
        if (
            first == 0x03
        ):  # Ctrl+C: treat like Escape, never raise KeyboardInterrupt mid-render
            return ESCAPE
        if first < 0x80:
            return raw.decode()
        # UTF-8 multibyte lead byte: read exactly the continuation-byte
        # count this lead byte declares, so a split multibyte character
        # (e.g. an accented letter) decodes as one real character instead
        # of one-byte-at-a-time mangled replacement characters.
        if 0xC0 <= first < 0xE0:
            continuation = 1
        elif 0xE0 <= first < 0xF0:
            continuation = 2
        elif 0xF0 <= first < 0xF8:
            continuation = 3
        else:
            return raw.decode(errors="replace")
        rest = self._read_bounded(fd, continuation)
        return (raw + rest).decode(errors="replace")

    def _read_bounded(self, fd: int, count: int, *, timeout: float = 0.05) -> bytes:
        """Reads up to `count` more bytes, each gated by a short
        follow-up `select` -- never a blocking read that could hang the
        event loop on a fragmented/incomplete sequence (slow SSH, a
        partial paste)."""
        import select

        got = b""
        while len(got) < count:
            ready, _, _ = select.select([fd], [], [], timeout)
            if not ready:
                break
            chunk = os.read(fd, count - len(got))
            if not chunk:
                break
            got += chunk
        return got

    def _read_escape_sequence(self, fd: int) -> str:
        """A bare Escape press is distinguished from an arrow/function-key
        escape sequence by a short (50ms) follow-up read. CSI sequences
        (`ESC [ ...`) are read incrementally, one byte at a time, until a
        final byte (a letter or `~`) or a bound is hit -- real CSI bodies
        here are at most 4 bytes, so fragmented input never hangs waiting
        for a byte count that assumed the wrong sequence length."""
        nxt = self._read_bounded(fd, 1)
        if not nxt:
            return ESCAPE
        body = nxt.decode(errors="replace")
        if body == "O":
            final = self._read_bounded(fd, 1).decode(errors="replace")
            return self._SS3.get(final, ESCAPE)
        if body == "[":
            for _ in range(8):
                more = self._read_bounded(fd, 1)
                if not more:
                    break
                c = more.decode(errors="replace")
                body += c
                if c.isalpha() or c == "~":
                    break
        if body == "[200~":
            return PASTE_PREFIX + self._read_paste(fd)
        key = self._SEQUENCES.get(body)
        if key is not None:
            return key
        # xterm modifier form `CSI <n> ; <mod> <final>` (Ctrl+F1 is
        # `ESC [ 1;5 P`, Ctrl+Up `ESC [ 1;5 A`, Ctrl+F5 `ESC [ 15;5 ~`):
        # drop the modifier and decode as the unmodified key.
        number, sep, modifier = body[1:-1].partition(";")
        final = body[-1:]
        if sep and number.isdigit() and modifier.isdigit():
            if final == "~":
                return self._SEQUENCES.get(f"[{number}~", ESCAPE)
            if number == "1":
                return self._SEQUENCES.get(f"[{final}") or self._SS3.get(final, ESCAPE)
        return ESCAPE

    def _read_paste(self, fd: int) -> str:
        """Reads a bracketed-paste payload up to its `ESC[201~` terminator
        and returns it decoded as UTF-8 (`errors="replace"`), literally --
        embedded escape/control bytes are text, never interpreted. At most
        `_PASTE_MAX` bytes are kept; the rest is still consumed. Each read
        asks for only as many bytes as can complete the terminator, so it
        never swallows keystrokes typed after the paste; a stalled stream
        ends the paste at `_read_bounded`'s short timeout, never hangs."""
        kept = bytearray()
        tail = b""  # unflushed bytes that may still start the terminator
        while True:
            # Longest suffix of `tail` that is a proper prefix of the
            # terminator: that many terminator bytes may already be in.
            partial = next(
                (
                    k
                    for k in range(len(_PASTE_END) - 1, 0, -1)
                    if tail.endswith(_PASTE_END[:k])
                ),
                0,
            )
            chunk = self._read_bounded(fd, len(_PASTE_END) - partial)
            if not chunk:
                kept += tail
                break
            tail += chunk
            if tail.endswith(_PASTE_END):
                kept += tail[: -len(_PASTE_END)]
                break
            keep = len(_PASTE_END) - 1
            if len(tail) > keep:
                kept += tail[:-keep]
                tail = tail[-keep:]
            del kept[_PASTE_MAX:]
        return bytes(kept[:_PASTE_MAX]).decode(errors="replace")


class WindowsKeyReader:
    """Reads one logical key using `msvcrt` -- no raw-mode toggle needed;
    `msvcrt.getwch` already returns one character at a time without echo
    or line buffering on the Windows console."""

    # BIOS/console extended scan codes (the byte following a `\x00`/`\xe0`
    # prefix from `getwch()`): arrows, plus F2 (0x3C), F3 (0x3D), and
    # Shift+Tab (0x0F) -- U01 fix, per the documented DOS/Windows console
    # scan-code table (real Windows console behavior unverified in this
    # environment; see this packet's own receipt for that named gap).
    _ARROW: ClassVar[dict[str, str]] = {
        "H": UP,
        "P": DOWN,
        "K": LEFT,
        "M": RIGHT,
        "\x3c": "f2",
        "\x3d": "f3",
        "\x0f": SHIFT_TAB,
    }

    def __init__(self) -> None:
        # Characters drained from the console that belong to later keys
        # (a multi-character drain that was not a paste).
        self._pending: list[str] = []

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
            if self._pending or msvcrt.kbhit():
                ch = self._pending.pop(0) if self._pending else msvcrt.getwch()
                if ch in ("\x00", "\xe0"):
                    ch2 = self._pending.pop(0) if self._pending else msvcrt.getwch()
                    return self._ARROW.get(ch2, ESCAPE)
                # Drain everything already available: more than one
                # printable character in a single drain is a paste,
                # delivered literally as one event (at most `_PASTE_MAX`
                # characters kept, the rest still consumed).
                drained = [ch, *self._pending]
                self._pending = []
                while msvcrt.kbhit():
                    extra = msvcrt.getwch()
                    if len(drained) < _PASTE_MAX:
                        drained.append(extra)
                if sum(c.isprintable() for c in drained) > 1:
                    return PASTE_PREFIX + "".join(drained)
                self._pending = drained[1:]
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
