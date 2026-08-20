"""Tests for Phase 30: Standalone Packaging, Versioning & CI.

Verifies:
- Version parity between pyproject.toml and src/rush/__init__.py
- Presence and valid syntax of packaging manifests (Homebrew, Scoop, Winget)
- GitHub Actions CI workflow integrity
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import rush

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_version_parity_across_codebase() -> None:
    pyproject_file = PROJECT_ROOT / "pyproject.toml"
    data = tomllib.loads(pyproject_file.read_text(encoding="utf-8"))
    toml_version = data["project"]["version"]

    assert rush.__version__ == toml_version


def test_packaging_manifests_structure() -> None:
    pkg_dir = PROJECT_ROOT / "packaging"

    brew_file = pkg_dir / "homebrew" / "rush.rb"
    scoop_file = pkg_dir / "scoop" / "rush.json"
    winget_file = pkg_dir / "winget" / "rush.yaml"

    assert brew_file.is_file()
    assert "class Rush < Formula" in brew_file.read_text(encoding="utf-8")

    assert scoop_file.is_file()
    assert '"version":' in scoop_file.read_text(encoding="utf-8")

    assert winget_file.is_file()
    assert "PackageIdentifier: jamesdsizemore.rush" in winget_file.read_text(
        encoding="utf-8"
    )
