"""Shared pytest fixtures.

Architecture §11.2.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest


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
