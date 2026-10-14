"""Every rush module must import cleanly as the first import of a fresh interpreter.

The frozen binary's entry (`from rush.entry import main`) imports rush.runtime
before rush.cli, so any import cycle that only resolves when rush.cli (or
rush.tools) is imported first breaks the shipped artifact at startup.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"


def _modules() -> list[str]:
    names = []
    for path in sorted((SRC / "rush").rglob("*.py")):
        parts = path.relative_to(SRC).with_suffix("").parts
        if parts[-1] == "__init__":
            parts = parts[:-1]
        names.append(".".join(parts))
    return names


def _fresh(code: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = str(SRC)
    return subprocess.run(
        [sys.executable, "-c", code, *args],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.mark.parametrize("module", _modules())
def test_every_rush_module_imports_first_in_a_fresh_interpreter(module: str) -> None:
    proc = _fresh(f"import {module}")
    assert proc.returncode == 0, proc.stderr


def test_entry_main_runs_version_and_gate_dispatch_in_a_fresh_interpreter() -> None:
    from rush import __version__, entry
    from rush.runtime.subprocesses import WINDOWS_GATE_ARG

    assert entry.WINDOWS_GATE_ARG == WINDOWS_GATE_ARG

    run_main = "import sys; sys.argv = ['rush', *sys.argv[1:]]; from rush.entry import main; main()"

    version = _fresh(run_main, "--version")
    assert version.returncode == 0, version.stderr
    assert version.stdout.strip() == __version__

    gate = _fresh(run_main, WINDOWS_GATE_ARG, "0", "true")
    assert "ImportError" not in gate.stderr, gate.stderr
    if sys.platform != "win32":
        assert gate.returncode != 0
        assert "Windows-only gate called on a non-Windows platform" in gate.stderr, (
            gate.stderr
        )
