"""Unit tests for LicenseMatrixTool (PR50.6)."""

from __future__ import annotations

from pathlib import Path

from rush.tools.license_matrix import LicenseMatrixScanner, LicenseMatrixTool


def test_license_matrix_metadata() -> None:
    tool = LicenseMatrixTool()
    assert tool.name == "license-matrix"
    assert "license" in tool.mcp_description.lower()
    assert len(tool.mcp_description) < 200


def test_license_matrix_pyproject_allowed(tmp_path: Path) -> None:
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
""",
        encoding="utf-8",
    )

    tool = LicenseMatrixTool()
    res = tool.run(tmp_path)

    assert res["tool"] == "license-matrix"
    assert res["status"] in ("ok", "warn")
    metrics = res.get("metrics") or {}
    assert metrics.get("total_packages", 0) >= 2


def test_license_matrix_package_json(tmp_path: Path) -> None:
    pkg_json = tmp_path / "package.json"
    pkg_json.write_text(
        """
{
  "name": "sample-node",
  "dependencies": {
    "lodash": "^4.17.21",
    "react": "^18.2.0"
  }
}
""",
        encoding="utf-8",
    )

    tool = LicenseMatrixTool()
    res = tool.run(tmp_path)

    assert res["tool"] == "license-matrix"
    metrics = res.get("metrics") or {}
    assert metrics.get("total_packages", 0) >= 2


def test_license_matrix_cargo_toml(tmp_path: Path) -> None:
    cargo = tmp_path / "Cargo.toml"
    cargo.write_text(
        """
[package]
name = "sample-rust"
version = "0.1.0"

[dependencies]
serde = "1.0"
tokio = "1.0"
""",
        encoding="utf-8",
    )

    tool = LicenseMatrixTool()
    res = tool.run(tmp_path)

    assert res["tool"] == "license-matrix"
    metrics = res.get("metrics") or {}
    assert metrics.get("total_packages", 0) >= 2


def test_license_matrix_copyleft_finding(tmp_path: Path) -> None:
    # Manifest with a copyleft dependency
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[project]
dependencies = [
    "pygpl-wrapper>=1.0",
]
""",
        encoding="utf-8",
    )

    tool = LicenseMatrixTool()
    res = tool.run(
        tmp_path,
        package_licenses={"pygpl-wrapper": "GPL-3.0-only"},
    )

    assert res["status"] == "fail"
    assert any(f.get("rule_id") == "license-copyleft-risk" for f in res["findings"])


def test_license_matrix_manual_review_finding(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[project]
dependencies = [
    "custom-lib>=1.0",
]
""",
        encoding="utf-8",
    )

    tool = LicenseMatrixTool()
    res = tool.run(
        tmp_path,
        package_licenses={"custom-lib": "Custom Dual / Proprietary (Review Needed)"},
    )

    assert res["status"] == "warn"
    assert any(f.get("rule_id") == "license-manual-review" for f in res["findings"])


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

    assert res["total_packages"] >= 1
    assert "copyleft_violations_count" in res
    assert "packages" in res
