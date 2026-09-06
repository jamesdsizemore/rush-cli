"""Runtime binary resolution and discovery caching.

Architecture §4.4 — enforces requirement C10 (engine discovery, never hard-fail).
"""

from __future__ import annotations

import os
import shutil
import sys
from functools import lru_cache
from pathlib import Path


def _venv_scripts_dir() -> Path | None:
    """If we're running inside a uv-managed venv, return its Scripts/bin dir.

    shutil.which() with no explicit `path=` reads $PATH, which on Windows
    doesn't include the venv's Scripts/ when the venv is invoked by
    absolute path (vs activated via `source .venv/bin/activate`). Adding
    the venv's Scripts dir to the search list makes `engine_on_path()`
    find ruff/pytest/pip-audit installed via `uv pip install`.
    """
    scripts = Path(sys.prefix) / ("Scripts" if os.name == "nt" else "bin")
    if scripts.is_dir():
        return scripts
    return None


@lru_cache(maxsize=256)
def _resolve_binary_cached(binary: str) -> str | None:
    common = sys.modules.get("rush.tools.common")
    scripts_fn = (
        getattr(common, "_venv_scripts_dir", _venv_scripts_dir)
        if common is not None
        else _venv_scripts_dir
    )
    scripts = scripts_fn()
    if scripts is not None:
        ext = ".exe" if os.name == "nt" else ""
        candidate = scripts / (binary + ext)
        if candidate.is_file():
            return str(candidate)
    return shutil.which(binary)


def clear_binary_cache() -> None:
    """Clear the in-memory binary resolution cache."""
    _resolve_binary_cached.cache_clear()


def resolve_binary(binary: str) -> str | None:
    """Return an executable from the active venv Scripts/bin, then PATH.

    This resolver is the only engine-discovery policy. Configuration cannot
    supply an executable path, which prevents a project file from selecting an
    arbitrary local binary. Results are cached in-memory for fast repeated lookups.
    """
    return _resolve_binary_cached(binary)


def engine_on_path(binary: str) -> bool:
    """True if `binary` is findable on PATH or in the active venv's Scripts/."""
    common = sys.modules.get("rush.tools.common")
    resolver = (
        getattr(common, "resolve_binary", resolve_binary)
        if common is not None
        else resolve_binary
    )
    return resolver(binary) is not None


__all__ = [
    "_resolve_binary_cached",
    "_venv_scripts_dir",
    "clear_binary_cache",
    "engine_on_path",
    "resolve_binary",
]
