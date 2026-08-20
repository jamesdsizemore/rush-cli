"""Read-only Phase 06 capability inventory contracts."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from rush.capabilities import build_plan, inspect_capabilities
from rush.cli import cli


def test_capabilities_detect_markers_without_executing_or_probing_versions(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'example'\n")
    (tmp_path / "coverage.json").write_text("{}")
    result = inspect_capabilities(tmp_path)

    assert result["path"] == str(tmp_path)
    assert result["languages"] == ["python"]
    assert result["reports"] == ["coverage.json"]
    assert result["tools"]["coverage"]["state"] == "applicable"
    assert result["tools"]["semantic-drift"]["state"] == "blocked"


def test_capabilities_detects_contained_codeql_sarif_without_execution(
    tmp_path: Path,
) -> None:
    (tmp_path / "codeql.sarif").write_text('{"version": "2.1.0", "runs": []}')

    result = inspect_capabilities(tmp_path)

    assert result["reports"] == ["codeql.sarif"]
    assert result["tools"]["codeql"] == {
        "maturity": "importer",
        "state": "applicable",
        "reason": "local report found",
    }


def test_capabilities_cli_emits_the_read_only_inventory(tmp_path: Path) -> None:
    result = CliRunner().invoke(cli, ["capabilities", str(tmp_path), "--json"])

    assert result.exit_code == 0
    assert '"tools"' in result.output


def test_plan_is_deterministic_and_excludes_browser_runtime(tmp_path: Path) -> None:
    (tmp_path / "codeql.sarif").write_text('{"version": "2.1.0", "runs": []}')
    first = build_plan(tmp_path, "nonbrowser")
    second = build_plan(tmp_path, "nonbrowser")

    assert first == second
    assert "semantic-drift" not in [step["tool"] for step in first["steps"]]
    codeql = next(step for step in first["steps"] if step["tool"] == "codeql")
    assert codeql["prerequisites"] == ["local report: codeql.sarif"]


def test_capabilities_distinguishes_configured_and_installed_without_execution(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "rush.toml").write_text("[tools.security]\ncheck = true\n")
    monkeypatch.setattr(
        "rush.capabilities.shutil.which",
        lambda binary: "/fixture/actionlint" if binary == "actionlint" else None,
    )

    result = inspect_capabilities(tmp_path)

    assert result["tools"]["security"]["state"] == "configured"
    assert result["tools"]["actions"] == {
        "maturity": "real_adapter",
        "state": "installed",
        "reason": "local engine on PATH: actionlint",
    }


def test_capabilities_cli_reports_malformed_local_config_without_a_traceback(
    tmp_path: Path,
) -> None:
    (tmp_path / "rush.toml").write_text("[tools\n")

    result = CliRunner().invoke(cli, ["capabilities", str(tmp_path), "--json"])

    assert result.exit_code == 2
    assert "malformed rush.toml" in result.output
    assert "Traceback" not in result.output
