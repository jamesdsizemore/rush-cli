"""Phase 60 Workstream P60.1.2 Maintainability Governance Tests.

Validates machine-readable maintainability baseline and exemption schema (T-60.07 through T-60.09).
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE_FILE = PROJECT_ROOT / "governance" / "maintainability-baseline.toml"
EXEMPTIONS_FILE = PROJECT_ROOT / "governance" / "maintainability-exemptions.toml"

REQUIRED_EXEMPTION_KEYS = {
    "symbol",
    "value",
    "owner",
    "rationale",
    "compensating_test",
    "expires_at",
}


def validate_exemption_entry(entry: dict[str, Any]) -> None:
    """Validate that an exemption entry contains strictly the required schema keys."""
    missing = REQUIRED_EXEMPTION_KEYS - set(entry.keys())
    if missing:
        raise ValueError(f"Exemption entry missing required keys: {sorted(missing)}")
    extra = set(entry.keys()) - REQUIRED_EXEMPTION_KEYS
    if extra:
        raise ValueError(f"Exemption entry contains unknown keys: {sorted(extra)}")


def test_every_target_has_pinned_ruff_version_command_value_and_threshold() -> None:
    """T-60.07: Maintainability baseline pins Ruff 0.16.3, command, and exact targets."""
    assert BASELINE_FILE.exists(), f"Baseline file {BASELINE_FILE} does not exist"

    data = tomllib.loads(BASELINE_FILE.read_text(encoding="utf-8"))
    metadata = data.get("metadata", {})

    assert metadata.get("tool") == "ruff"
    assert metadata.get("version") == "0.16.3"
    assert metadata.get("threshold") == 10
    assert metadata.get("command")
    assert metadata.get("captured_at")

    targets = data.get("targets", [])
    assert len(targets) == 8, f"Expected 8 target hotspots, got {len(targets)}"

    expected_targets = {
        "discover_workspaces": {
            "file": "src/rush/discovery/workspace.py",
            "baseline_c901": 23,
            "target_c901": 10,
        },
        "BlastRadiusAnalyzer.analyze": {
            "file": "src/rush/tools/blast_radius.py",
            "baseline_c901": 15,
            "target_c901": 10,
        },
        "SessionContinuityTool.run": {
            "file": "src/rush/tools/continuity.py",
            "baseline_c901": 18,
            "target_c901": 10,
        },
        "SessionContinuityTool._provider_resume": {
            "file": "src/rush/tools/continuity.py",
            "baseline_c901": 13,
            "target_c901": 10,
        },
        "DbDriftAuditor.audit_drift": {
            "file": "src/rush/tools/db_drift.py",
            "baseline_c901": 21,
            "target_c901": 10,
        },
        "LintTool.run": {
            "file": "src/rush/tools/lint.py",
            "baseline_c901": 12,
            "target_c901": 10,
        },
        "ReviewTool.run": {
            "file": "src/rush/tools/review.py",
            "baseline_c901": 16,
            "target_c901": 10,
        },
        "_register_tools": {
            "file": "src/rush/mcp.py",
            "baseline_c901": 16,
            "target_c901": 10,
        },
    }

    target_map = {t["symbol"]: t for t in targets}
    for symbol, expected in expected_targets.items():
        assert symbol in target_map, f"Target symbol '{symbol}' missing from baseline"
        actual = target_map[symbol]
        assert actual["file"] == expected["file"]
        assert actual["baseline_c901"] == expected["baseline_c901"]
        assert actual["target_c901"] == expected["target_c901"]


def test_exemption_schema_requires_symbol_value_owner_rationale_test_and_expiry() -> (
    None
):
    """T-60.08: Exemption schema strictly enforces 6 required fields with zero extra keys."""
    assert EXEMPTIONS_FILE.exists(), f"Exemptions file {EXEMPTIONS_FILE} does not exist"

    data = tomllib.loads(EXEMPTIONS_FILE.read_text(encoding="utf-8"))
    assert data.get("schema_version") == "1.0.0"

    exemptions = data.get("exemptions", [])
    for entry in exemptions:
        validate_exemption_entry(entry)

    # Unit-test the validator itself to ensure invalid schemas are rejected
    import pytest

    with pytest.raises(ValueError, match="missing required keys"):
        validate_exemption_entry({"symbol": "foo", "value": 12})

    with pytest.raises(ValueError, match="unknown keys"):
        validate_exemption_entry(
            {
                "symbol": "foo",
                "value": 12,
                "owner": "alice",
                "rationale": "test",
                "compensating_test": "tests/test_foo.py",
                "expires_at": "2026-10-01T00:00:00Z",
                "extra_field": True,
            }
        )


def test_phase60_starts_with_no_exemptions() -> None:
    """T-60.09: Phase 60 starts with zero exemptions."""
    assert EXEMPTIONS_FILE.exists(), f"Exemptions file {EXEMPTIONS_FILE} does not exist"

    data = tomllib.loads(EXEMPTIONS_FILE.read_text(encoding="utf-8"))
    exemptions = data.get("exemptions")
    assert exemptions is not None, "Exemptions list must be present"
    assert exemptions == [], "Phase 60 requires strictly zero exemptions"
    assert len(exemptions) == 0


def test_cli_and_mcp_meet_c901_threshold() -> None:
    """T-60.18: Verify CLI and MCP boundaries comply with McCabe C901 <= 10."""
    import shutil
    import subprocess
    import sys

    ruff_path = (
        PROJECT_ROOT
        / ".venv"
        / ("Scripts" if sys.platform == "win32" else "bin")
        / ("ruff.exe" if sys.platform == "win32" else "ruff")
    )
    ruff_cmd = str(ruff_path) if ruff_path.exists() else shutil.which("ruff")
    assert ruff_cmd, "ruff executable not found"

    cmd = [
        ruff_cmd,
        "check",
        "--select",
        "C901",
        "--config",
        "lint.mccabe.max-complexity = 10",
        "--output-format",
        "concise",
        "src/rush/cli.py",
        "src/rush/mcp.py",
        "src/rush/cli_support",
        "src/rush/mcp_support",
    ]
    proc = subprocess.run(
        cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, (
        f"Ruff C901 check failed (returncode={proc.returncode}):\n{proc.stdout}\n{proc.stderr}"
    )
    assert "C901" not in proc.stdout, f"Expected 0 findings, got:\n{proc.stdout}"
    assert "All checks passed!" in proc.stdout, (
        f"Expected clean pass, got:\n{proc.stdout}"
    )


def test_continuity_facade_meets_c901_threshold() -> None:
    """T-60.19: Verify SessionContinuityTool facade and rush.continuity comply with McCabe C901 <= 10."""
    import shutil
    import subprocess
    import sys

    ruff_path = (
        PROJECT_ROOT
        / ".venv"
        / ("Scripts" if sys.platform == "win32" else "bin")
        / ("ruff.exe" if sys.platform == "win32" else "ruff")
    )
    ruff_cmd = str(ruff_path) if ruff_path.exists() else shutil.which("ruff")
    assert ruff_cmd, "ruff executable not found"

    cmd = [
        ruff_cmd,
        "check",
        "--select",
        "C901",
        "--config",
        "lint.mccabe.max-complexity = 10",
        "--output-format",
        "concise",
        "src/rush/tools/continuity.py",
        "src/rush/continuity",
    ]
    proc = subprocess.run(
        cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, (
        f"Ruff C901 check failed (returncode={proc.returncode}):\n{proc.stdout}\n{proc.stderr}"
    )
    assert "C901" not in proc.stdout, f"Expected 0 findings, got:\n{proc.stdout}"
    assert "All checks passed!" in proc.stdout, (
        f"Expected clean pass, got:\n{proc.stdout}"
    )


def test_review_facade_meets_c901_threshold() -> None:
    """T-60.20: Verify ReviewTool facade and rush.review comply with McCabe C901 <= 10."""
    import shutil
    import subprocess
    import sys

    ruff_path = (
        PROJECT_ROOT
        / ".venv"
        / ("Scripts" if sys.platform == "win32" else "bin")
        / ("ruff.exe" if sys.platform == "win32" else "ruff")
    )
    ruff_cmd = str(ruff_path) if ruff_path.exists() else shutil.which("ruff")
    assert ruff_cmd, "ruff executable not found"

    cmd = [
        ruff_cmd,
        "check",
        "--select",
        "C901",
        "--config",
        "lint.mccabe.max-complexity = 10",
        "--output-format",
        "concise",
        "src/rush/tools/review.py",
        "src/rush/review",
    ]
    proc = subprocess.run(
        cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, (
        f"Ruff C901 check failed (returncode={proc.returncode}):\n{proc.stdout}\n{proc.stderr}"
    )
    assert "C901" not in proc.stdout, f"Expected 0 findings, got:\n{proc.stdout}"
    assert "All checks passed!" in proc.stdout, (
        f"Expected clean pass, got:\n{proc.stdout}"
    )
