"""Phase 00 direct dependency policy tests."""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_all_direct_runtime_dev_and_build_requirements_use_exact_pins() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    requirements = [
        *pyproject["project"]["dependencies"],
        *pyproject["project"]["optional-dependencies"]["dev"],
        *pyproject["build-system"]["requires"],
    ]

    assert requirements
    assert all("==" in requirement for requirement in requirements)
    assert pyproject["build-system"]["requires"] == ["hatchling==1.32.0"]


def test_uv_lock_tracks_the_project_runtime_and_dev_requirements() -> None:
    lock_text = (ROOT / "uv.lock").read_text(encoding="utf-8")

    assert 'name = "rush-cli"' in lock_text
    for requirement in ("mcp", "click", "rich", "pytest", "pip-audit", "ruff"):
        assert f'name = "{requirement}"' in lock_text
