"""Contract tests for Package Identity & Canonical Imports (Phase 52: P52.1.1 & P52.2.1)."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_RUSH_PATTERN = re.compile(r"^\s*(from|import)\s+src\.rush", re.MULTILINE)


def test_first_party_python_contains_no_src_rush_import() -> None:
    """Verify that zero first-party Python source or test files import 'src.rush'."""
    violations: list[str] = []

    # Check all production files in src/
    for py_file in sorted((PROJECT_ROOT / "src").rglob("*.py")):
        content = py_file.read_text(encoding="utf-8")
        matches = SRC_RUSH_PATTERN.findall(content)
        if matches:
            rel = py_file.relative_to(PROJECT_ROOT).as_posix()
            violations.append(f"{rel} ({len(matches)} occurrences)")

    # Check all test files in tests/
    for py_file in sorted((PROJECT_ROOT / "tests").rglob("*.py")):
        content = py_file.read_text(encoding="utf-8")
        matches = SRC_RUSH_PATTERN.findall(content)
        if matches:
            rel = py_file.relative_to(PROJECT_ROOT).as_posix()
            violations.append(f"{rel} ({len(matches)} occurrences)")

    assert not violations, (
        f"Found {len(violations)} files with invalid 'src.rush' imports:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


def test_broken_src_rush_import_fails_in_isolated_install() -> None:
    """Verify that importing through 'src.rush' is rejected when sys.path is strictly isolated."""
    from scripts.probe_installed_artifacts import check_import_integrity

    broken_code = "from src.rush.tools.common import run_subprocess"
    clean_code = "from rush.tools.common import run_subprocess"

    assert check_import_integrity(broken_code) is False
    assert check_import_integrity(clean_code) is True


def test_pytest_configuration_does_not_expose_repository_root_as_src_package() -> None:
    """Verify that pytest.ini_options does not include '.' in pythonpath."""
    pyproject_file = PROJECT_ROOT / "pyproject.toml"
    data = tomllib.loads(pyproject_file.read_text(encoding="utf-8"))

    ini_options = data.get("tool", {}).get("pytest", {}).get("ini_options", {})
    pythonpath = ini_options.get("pythonpath", [])

    assert "." not in pythonpath, (
        f"pyproject.toml [tool.pytest.ini_options].pythonpath must not contain '.': {pythonpath}"
    )
    assert "src" in pythonpath, (
        f"pyproject.toml [tool.pytest.ini_options].pythonpath must contain 'src': {pythonpath}"
    )


def test_installed_collection_uses_one_rush_origin() -> None:
    """Verify that imported rush symbols resolve exclusively to rush/, never src.rush."""
    import sys

    import rush
    import rush.catalog
    import rush.cli

    # Verify single canonical module identity
    assert rush.__name__ == "rush"
    assert rush.catalog.__name__ == "rush.catalog"
    assert rush.cli.__name__ == "rush.cli"

    # Verify no dual-namespace contamination in sys.modules
    assert "src.rush" not in sys.modules
    assert "src.rush.cli" not in sys.modules
    assert "src.rush.catalog" not in sys.modules

    rush_file = Path(rush.__file__).resolve().as_posix()
    assert rush_file.endswith("/rush/__init__.py")
