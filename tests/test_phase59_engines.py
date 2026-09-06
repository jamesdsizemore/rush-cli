"""Phase 59 Workstream P59.5 Contract Tests: Deterministic Engine Discovery Matrix."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from rush.engines.support_policy import (
    AmbientPathPollutionError,
    EngineSupportPolicy,
    FixedPathEnvironment,
)


def test_engine_discovery_and_capability_matrix(tmp_path: Path) -> None:
    """T-59.24 (R-014): Deterministic capability discovery across taxonomy without ambient PATH pollution."""
    policy = EngineSupportPolicy.load()

    empty_dir = tmp_path / "isolated_empty_bin"
    empty_dir.mkdir(parents=True, exist_ok=True)

    # Within an isolated empty environment, external tools are absent and built-ins present
    with FixedPathEnvironment(empty_dir):
        matrix = policy.discover_capabilities()

        # Built-in and stdlib engines must be available
        assert matrix["python-ast"] is True
        assert matrix["tomllib"] is True
        assert matrix["statistics"] is True

        # Supported optional engines without binaries must NOT be discovered
        for ext_tool in (
            "ruff",
            "mypy",
            "pytest",
            "cargo",
            "vitest",
            "eslint",
            "prettier",
            "pip-audit",
            "trivy",
            "semgrep",
            "gitleaks",
        ):
            assert matrix[ext_tool] is False, (
                f"Engine '{ext_tool}' was discovered from ambient PATH inside isolated environment!"
            )
            assert policy.discover_engine(ext_tool) is None

    # Within an environment containing explicit provisioned mock binaries
    provisioned_dir = tmp_path / "provisioned_bin"
    provisioned_dir.mkdir(parents=True, exist_ok=True)

    exe_ext = ".exe" if os.name == "nt" else ""
    mock_ruff = provisioned_dir / f"ruff{exe_ext}"
    mock_ruff.write_text("#!/bin/sh\necho 'ruff 0.6.9'\n")
    if os.name != "nt":
        mock_ruff.chmod(0o755)

    with FixedPathEnvironment(provisioned_dir):
        matrix_prov = policy.discover_capabilities()
        assert matrix_prov["ruff"] is True
        assert matrix_prov["mypy"] is False

        # Verify binary resolved strictly to provisioned directory
        resolved_ruff = policy.discover_engine("ruff")
        assert resolved_ruff is not None
        assert Path(resolved_ruff).resolve() == mock_ruff.resolve()

        # Verify assertion of no ambient pollution
        policy.assert_no_ambient_pollution("ruff", provisioned_dir)

        # Verifying against an incorrect allowed root raises AmbientPathPollutionError
        with pytest.raises(AmbientPathPollutionError):
            policy.assert_no_ambient_pollution("ruff", empty_dir)
