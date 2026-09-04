"""Unit tests for LicenseMatrixTool with SPDX expressions and strict metrics."""

from __future__ import annotations

import json
from pathlib import Path

from rush.tools.license_matrix import LicenseMatrixScanner, LicenseMatrixTool
from rush.tools.schemas import LicenseMatrixMetrics


def test_license_matrix_metadata() -> None:
    tool = LicenseMatrixTool()
    assert tool.name == "license-matrix"
    assert "license" in tool.mcp_description.lower()
    assert len(tool.mcp_description) < 200


def test_license_matrix_pyproject_tomllib_allowed(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[project]
name = "test-pkg"
version = "0.1.0"
dependencies = [
    "click>=8.0.0",
    "pydantic>=2.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=9.0",
]
""",
        encoding="utf-8",
    )

    tool = LicenseMatrixTool()
    res = tool.run(
        tmp_path,
        package_licenses={
            "click": "BSD-3-Clause",
            "pydantic": "MIT",
            "pytest": "MIT",
        },
    )

    assert res["tool"] == "license-matrix"
    assert res["status"] == "ok"
    assert res["findings"] == []
    metrics = res.get("metrics") or {}
    assert metrics["packages_audited"] == 3
    assert metrics["compliance_score"] == 1.0
    assert metrics["incompatible_count"] == 0

    # Strict schema validation
    validated_metrics = LicenseMatrixMetrics.model_validate(metrics)
    assert validated_metrics.compliance_score == 1.0


def test_license_matrix_compound_spdx_expressions(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[project]
dependencies = [
    "dual-pkg>=1.0",
    "gpl-pkg>=1.0",
]
""",
        encoding="utf-8",
    )

    tool = LicenseMatrixTool()
    res = tool.run(
        tmp_path,
        package_licenses={
            "dual-pkg": "MIT OR GPL-3.0-only",  # Developer can select MIT
            "gpl-pkg": "GPL-3.0-or-later",
        },
    )

    assert res["status"] == "fail"
    metrics = res.get("metrics") or {}
    assert metrics["incompatible_count"] == 1
    assert metrics["compliance_score"] == 0.5

    # Check findings
    findings = res["findings"]
    assert len(findings) == 1
    assert findings[0]["rule_id"] == "license-copyleft-risk"
    assert "gpl-pkg" in findings[0]["message"]


def test_license_matrix_committed_fixture_evaluation() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    fixture_path = (
        repo_root
        / "tests"
        / "fixtures"
        / "phase50"
        / "licenses"
        / "compound_licenses.json"
    )
    assert fixture_path.is_file()

    items = json.loads(fixture_path.read_text(encoding="utf-8"))
    tool = LicenseMatrixTool()

    for item in items:
        pkg = item["package"]
        expr = item["license_expression"]
        expected = item["expected_status"]

        # Run on a dummy dir with explicit override
        res = tool.run(
            repo_root,
            package_licenses={pkg: expr},
        )
        report = res["raw"]["packages"]
        match = [p for p in report if p["package"] == pkg]
        assert len(match) == 1

        if expected == "compliant":
            assert match[0]["category"] == "permissive"
            assert match[0]["risk"] == "LOW"
        else:
            assert match[0]["is_copyleft"] is True
            assert match[0]["risk"] in ("HIGH", "MEDIUM")


def test_license_matrix_package_json_and_cargo_toml(tmp_path: Path) -> None:
    pkg_json = tmp_path / "package.json"
    pkg_json.write_text(
        """
{
  "name": "sample-node",
  "dependencies": {
    "lodash": "^4.17.21"
  },
  "devDependencies": {
    "typescript": "^5.0.0"
  }
}
""",
        encoding="utf-8",
    )

    cargo = tmp_path / "Cargo.toml"
    cargo.write_text(
        """
[package]
name = "sample-rust"
version = "0.1.0"

[dependencies]
serde = "1.0"
""",
        encoding="utf-8",
    )

    tool = LicenseMatrixTool()
    res = tool.run(tmp_path)

    assert res["tool"] == "license-matrix"
    metrics = res.get("metrics") or {}
    assert metrics["packages_audited"] == 3


def test_license_matrix_legacy_scanner_backward_compatibility(
    tmp_path: Path,
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[project]
dependencies = [
    "click>=8.0",
]
""",
        encoding="utf-8",
    )

    scanner = LicenseMatrixScanner(project_root=tmp_path)
    res = scanner.scan_licenses()

    assert res["total_packages"] == 1
    assert res["copyleft_violations_count"] == 0
    assert "packages" in res
