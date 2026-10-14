"""The Python interpreter that runs a project's own code.

A frozen (PyInstaller) Rush's ``sys.executable`` is the rush binary itself,
so ``[sys.executable, "-m", "pytest"]`` would run ``rush -m pytest``. Every
child that runs project code resolves its interpreter here instead.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

PYTHON_PREREQUISITE = (
    "prerequisite missing: no Python interpreter for this project "
    "(no .venv/venv, no active virtualenv, no python3 or python on PATH)"
)

_VENV_DIRS = (".venv", "venv")
_PROJECT_MARKERS = ("pyproject.toml", "setup.py", "setup.cfg", ".git")


def _venv_python(venv: Path) -> str | None:
    candidate = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return str(candidate)
    return None


def _project_venv_python(start: Path) -> str | None:
    base = start if start.is_dir() else start.parent
    for directory in (base, *base.parents):
        for name in _VENV_DIRS:
            found = _venv_python(directory / name)
            if found is not None:
                return found
        if any((directory / marker).exists() for marker in _PROJECT_MARKERS):
            break
    return None


def _frozen_fallback_python() -> str | None:
    active = os.environ.get("VIRTUAL_ENV")
    if active:
        found = _venv_python(Path(active))
        if found is not None:
            return found
    for name in ("python3", "python"):
        on_path = shutil.which(name)
        if on_path is not None:
            return on_path
    return None


def project_python(start: Path | None = None) -> str | None:
    """The interpreter for the project at or above ``start``.

    Order: the project's own ``.venv``/``venv`` python (searched upward to the
    nearest project marker); from source, Rush's own interpreter; frozen, the
    active virtualenv (uv and virtualenv set ``VIRTUAL_ENV``), then
    ``python3``/``python`` on PATH. None when no interpreter exists -- callers
    report `PYTHON_PREREQUISITE`, never a garbage exit code.
    """
    if start is not None:
        found = _project_venv_python(start)
        if found is not None:
            return found
    if not getattr(sys, "frozen", False):
        return sys.executable
    return _frozen_fallback_python()
