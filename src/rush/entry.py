"""Standalone (PyInstaller) entry point.

A frozen rush.exe has no `-c`, so the Windows owned-process gate re-runs rush
itself with the hidden `WINDOWS_GATE_ARG` first argument; everything else is
the normal CLI.
"""

from __future__ import annotations

import sys

# Must equal rush.runtime.subprocesses.WINDOWS_GATE_ARG; kept literal so the
# gate check imports nothing (tests/test_import_order.py asserts they match).
WINDOWS_GATE_ARG = "__rush_windows_gate__"


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == WINDOWS_GATE_ARG:
        from .runtime.subprocesses import windows_gate

        sys.exit(windows_gate(sys.argv[2:]))
    from .cli import cli

    cli()
