"""Phase 59 Workstream P59.5 Contract Tests: Engine Taxonomy, Isolation, and Conformance."""

from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path
from typing import Any

import pytest

from rush.engines.support_policy import (
    AllSkippedViolationError,
    EngineSupportPolicy,
    FixedPathEnvironment,
    ReleaseGateFailureError,
)
from rush.tools.common import clear_binary_cache, resolve_binary


def _resolve_fixture_path(path_str: str) -> Path:
    base = path_str.split("::")[0]
    return Path(base)


def test_every_engine_has_one_taxonomy_entry() -> None:
    """T-59.19: Every engine family has exactly one entry in engine-support.toml."""
    policy = EngineSupportPolicy.load()
    assert len(policy.records) == 19, (
        f"Expected 19 engine families, got {len(policy.records)}"
    )

    valid_classes = {"mandatory", "supported-optional", "best-effort"}
    for family, record in policy.records.items():
        assert record.family == family, (
            f"Record family '{record.family}' mismatch with key '{family}'"
        )
        assert record.support_class in valid_classes, (
            f"Engine '{family}' has invalid support_class '{record.support_class}'"
        )
        assert record.executable.strip(), f"Engine '{family}' executable is empty"
        assert record.version_command.strip(), (
            f"Engine '{family}' version_command is empty"
        )
        assert isinstance(record.can_pass_all_skipped, bool), (
            f"Engine '{family}' can_pass_all_skipped must be bool"
        )
        assert record.clean_fixture.strip(), f"Engine '{family}' clean_fixture is empty"
        assert _resolve_fixture_path(record.clean_fixture).exists(), (
            f"Engine '{family}' clean fixture '{record.clean_fixture}' does not resolve to an existing file"
        )
        assert record.finding_fixture.strip(), (
            f"Engine '{family}' finding_fixture is empty"
        )
        assert _resolve_fixture_path(record.finding_fixture).exists(), (
            f"Engine '{family}' finding fixture '{record.finding_fixture}' does not resolve to an existing file"
        )
        if record.malformed_fixture is not None:
            assert _resolve_fixture_path(record.malformed_fixture).exists(), (
                f"Engine '{family}' malformed fixture '{record.malformed_fixture}' does not resolve to an existing file"
            )


def test_supported_family_has_success_failure_and_malformed_jobs() -> None:
    """T-59.20: Every supported-optional family has clean, finding, and malformed fixtures."""
    policy = EngineSupportPolicy.load()
    supported_optional = [
        rec
        for rec in policy.records.values()
        if rec.support_class == "supported-optional"
    ]
    assert len(supported_optional) >= 11, (
        f"Expected at least 11 supported-optional engines, got {len(supported_optional)}"
    )

    for rec in supported_optional:
        assert rec.clean_fixture, f"Engine '{rec.family}' missing clean_fixture"
        assert _resolve_fixture_path(rec.clean_fixture).exists(), (
            f"Engine '{rec.family}' clean_fixture path '{rec.clean_fixture}' does not exist"
        )

        assert rec.finding_fixture, f"Engine '{rec.family}' missing finding_fixture"
        assert _resolve_fixture_path(rec.finding_fixture).exists(), (
            f"Engine '{rec.family}' finding_fixture path '{rec.finding_fixture}' does not exist"
        )

        assert rec.malformed_fixture, f"Engine '{rec.family}' missing malformed_fixture"
        assert _resolve_fixture_path(rec.malformed_fixture).exists(), (
            f"Engine '{rec.family}' malformed_fixture path '{rec.malformed_fixture}' does not exist"
        )


def test_supported_family_all_skipped_fails() -> None:
    """T-59.21: Supported-optional engine with all skipped results raises AllSkippedViolationError."""
    policy = EngineSupportPolicy.load()

    # Test each supported-optional family
    for family in ("ruff", "mypy", "pytest", "cargo", "vitest", "eslint"):
        all_skipped_results: list[dict[str, Any]] = [
            {"name": "test_one", "status": "skipped", "reason": "binary absent"},
            {"name": "test_two", "status": "skipped", "reason": "binary absent"},
        ]
        with pytest.raises(AllSkippedViolationError) as exc_info:
            policy.validate_execution_result(family, all_skipped_results)
        assert f"Engine family '{family}' cannot pass with all-skipped results" in str(
            exc_info.value
        )

        # Non-all-skipped results must pass validation
        mixed_results: list[dict[str, Any]] = [
            {"name": "test_one", "status": "ok", "summary": "clean"},
            {"name": "test_two", "status": "skipped", "reason": "optional subtest"},
        ]
        policy.validate_execution_result(family, mixed_results)

    # Best-effort family with all-skipped results is allowed
    best_effort_skipped: list[dict[str, Any]] = [
        {"name": "test_one", "status": "skipped", "reason": "onnxruntime absent"},
    ]
    policy.validate_execution_result("onnxruntime", best_effort_skipped)


def test_fixed_path_ignores_ambient_tools(tmp_path: Path) -> None:
    """T-59.22: FixedPathEnvironment isolates discovery from ambient host binaries."""
    empty_dir = tmp_path / "empty_isolated_path"
    empty_dir.mkdir(parents=True, exist_ok=True)

    # In regular host environment, at least one of ruff or mypy is resolvable
    clear_binary_cache()
    host_ruff = resolve_binary("ruff")
    host_mypy = resolve_binary("mypy")
    assert host_ruff is not None or host_mypy is not None

    # Inside FixedPathEnvironment with empty dir, ambient binaries must NOT resolve
    with FixedPathEnvironment(empty_dir):
        assert resolve_binary("ruff") is None
        assert resolve_binary("mypy") is None

    # After exit, cache is reset and host resolution returns
    clear_binary_cache()
    assert resolve_binary("ruff") == host_ruff
    assert resolve_binary("mypy") == host_mypy


def test_release_gate_mypy_is_provisioned_and_non_skipped(monkeypatch) -> None:
    """T-59.23: Mypy release gate executes --version and src/rush, failing closed."""
    policy = EngineSupportPolicy.load()

    executed_commands: list[list[str]] = []

    def mock_run_success(
        cmd: list[str], **_kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        executed_commands.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="Success\n", stderr="")

    monkeypatch.setattr(
        "rush.engines.support_policy.resolve_binary", lambda _bin: "/bin/mypy"
    )
    monkeypatch.setattr("subprocess.run", mock_run_success)

    # Successful run executes both version and verification
    result = policy.verify_release_gate("mypy")
    assert result is True
    assert len(executed_commands) == 2
    assert executed_commands[0] == ["/bin/mypy", "--version"]
    assert executed_commands[1] == ["/bin/mypy", "src/rush"]

    # Missing mypy binary fails closed
    monkeypatch.setattr("rush.engines.support_policy.resolve_binary", lambda _bin: None)
    with pytest.raises(ReleaseGateFailureError) as exc_missing:
        policy.verify_release_gate("mypy")
    assert "not installed or available on PATH" in str(exc_missing.value)

    # Failing mypy verification raises ReleaseGateFailureError
    def mock_run_failure(
        cmd: list[str], **_kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        if "src/rush" in cmd:
            return subprocess.CompletedProcess(
                cmd, 1, stdout="", stderr="Found 1 type error"
            )
        return subprocess.CompletedProcess(cmd, 0, stdout="mypy 1.11.0\n", stderr="")

    monkeypatch.setattr(
        "rush.engines.support_policy.resolve_binary", lambda _bin: "/bin/mypy"
    )
    monkeypatch.setattr("subprocess.run", mock_run_failure)
    with pytest.raises(ReleaseGateFailureError) as exc_failed:
        policy.verify_release_gate("mypy")
    assert "verification failed" in str(exc_failed.value)


def test_remediation_phase59_manifest_integrity() -> None:
    """T-59.25: engine-support.toml manifest satisfies all governance schema requirements."""
    manifest_path = Path("governance/engine-support.toml")
    assert manifest_path.exists(), "engine-support.toml not found"

    with open(manifest_path, "rb") as f:
        data = tomllib.load(f)

    manifest_meta = data.get("manifest", {})
    assert "policy_version" in manifest_meta
    assert manifest_meta.get("total_engine_families") == 19

    engines = data.get("engines", [])
    assert len(engines) == 19

    families = set()
    for engine in engines:
        fam = engine.get("family")
        assert fam, "Engine family missing"
        assert fam not in families, f"Duplicate engine family: {fam}"
        families.add(fam)

        assert engine.get("support_class") in (
            "mandatory",
            "supported-optional",
            "best-effort",
        )
        assert engine.get("executable")
        assert engine.get("version_command")
        assert isinstance(engine.get("can_pass_all_skipped"), bool)
        assert "permitted_skip_reason" in engine
        assert "fixture_matrix" in engine

        matrix = engine["fixture_matrix"]
        assert "clean" in matrix
        assert "finding" in matrix

        if engine["support_class"] == "mandatory":
            assert engine["can_pass_all_skipped"] is False
            assert engine["permitted_skip_reason"] == "none"
        elif engine["support_class"] == "supported-optional":
            assert engine["can_pass_all_skipped"] is False
            assert "malformed" in matrix
        elif engine["support_class"] == "best-effort":
            assert engine["can_pass_all_skipped"] is True
