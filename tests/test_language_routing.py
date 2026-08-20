"""Language project-marker routing contracts."""

from __future__ import annotations

from pathlib import Path

from rush.tools.lint import LintTool
from rush.tools.routing import detect_project_languages
from rush.tools.test import TestTool
from rush.tools.typecheck import TypecheckTool


def test_detects_multiple_ecosystems_in_stable_catalog_order(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module example\n")
    (tmp_path / "Cargo.toml").write_text("[package]\nname = 'example'\n")
    (tmp_path / "package.json").write_text("{}")

    assert detect_project_languages(tmp_path) == ["javascript", "go", "rust"]


def test_detects_marker_file_globs_and_does_not_choose_arbitrarily(
    tmp_path: Path,
) -> None:
    (tmp_path / "app.sln").write_text("")
    (tmp_path / "build.gradle.kts").write_text("")
    (tmp_path / "flake.nix").write_text("{}")

    assert detect_project_languages(tmp_path) == ["jvm", "dotnet", "nix"]


def test_unmarked_directory_has_no_detected_ecosystems(tmp_path: Path) -> None:
    assert detect_project_languages(tmp_path) == []


def test_test_tool_does_not_execute_feasibility_gated_language_adapters(
    tmp_path: Path,
) -> None:
    (tmp_path / "go.mod").write_text("module example\n")
    (tmp_path / "Cargo.toml").write_text("[package]\nname = 'example'\n")

    result = TestTool().run(tmp_path)

    assert result["status"] == "skipped"
    assert "feasibility-gated" in result["summary"]


def test_typecheck_does_not_execute_feasibility_gated_language_adapter(
    tmp_path: Path,
) -> None:
    (tmp_path / "go.mod").write_text("module example\n")

    result = TypecheckTool().run(tmp_path)

    assert result["status"] == "skipped"
    assert "feasibility-gated" in result["summary"]


def test_lint_does_not_execute_feasibility_gated_language_adapter(
    tmp_path: Path,
) -> None:
    (tmp_path / "go.mod").write_text("module example\n")

    result = LintTool().run(tmp_path)

    assert result["status"] == "skipped"
    assert "feasibility-gated" in result["summary"]
