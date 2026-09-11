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


def test_capabilities_detects_javascript_project_regardless_of_unrelated_ruff_on_path(
    tmp_path: Path, monkeypatch
) -> None:
    """A JS-only project's language list must not depend on which engines the
    host machine happens to have on PATH (ruff is a Python engine)."""
    (tmp_path / "package.json").write_text('{"name": "demo-js"}')
    monkeypatch.setattr(
        "rush.capabilities.shutil.which",
        lambda binary: "/fixture/ruff" if binary == "ruff" else None,
    )

    result = inspect_capabilities(tmp_path)

    assert result["languages"] == ["javascript"]
    assert result["tools"]["lint"]["state"] == "installed"
    assert "ruff" in result["tools"]["lint"]["reason"]


def test_capabilities_detects_requirements_only_python_project(
    tmp_path: Path,
) -> None:
    """A Python project pinned only by requirements.txt (no pyproject.toml)
    must still be detected as Python by shared discovery inventory."""
    (tmp_path / "requirements.txt").write_text("requests==2.31.0\n")

    result = inspect_capabilities(tmp_path)

    assert result["languages"] == ["python"]
    assert any(stack["language"] == "python" for stack in result["stacks"])


def test_capabilities_detects_dart_project(tmp_path: Path) -> None:
    (tmp_path / "pubspec.yaml").write_text("name: demo\n")

    result = inspect_capabilities(tmp_path)

    assert result["languages"] == ["dart"]


def test_capabilities_detects_mixed_language_monorepo(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'api'\n")
    (tmp_path / "package.json").write_text('{"name": "web"}')
    (tmp_path / "go.mod").write_text("module demo\n\ngo 1.22\n")

    result = inspect_capabilities(tmp_path)

    assert result["languages"] == ["python", "javascript", "go"]
    stack_languages = {stack["language"] for stack in result["stacks"]}
    assert {"python", "javascript", "go"} <= stack_languages


def test_capabilities_handles_empty_tools_config_table(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    (tmp_path / "rush.toml").write_text("[tools]\n")

    result = inspect_capabilities(tmp_path)

    assert result["tools"]["lint"]["state"] != "configured"
