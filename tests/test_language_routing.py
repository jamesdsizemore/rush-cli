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


def test_test_tool_aggregates_multiple_detected_language_engines(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "go.mod").write_text("module example\n")
    (tmp_path / "Cargo.toml").write_text("[package]\nname = 'example'\n")

    monkeypatch.setattr(
        "rush.tools.test.run_engine",
        lambda engine, path, args, tool_name: {
            "tool": tool_name,
            "engine": engine.name,
            "engine_version": None,
            "status": "skipped",
            "duration_ms": 0,
            "summary": "fixture engine unavailable",
            "findings": [],
            "raw": None,
        },
    )

    result = TestTool().run(tmp_path)

    assert result["status"] == "skipped"
    assert result["engine"] == "go-test+cargo-test"


def test_typecheck_tool_routes_detected_language_projects(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module example\n")

    result = TypecheckTool().run(tmp_path)

    assert result["engine"] == "go-vet"


def test_lint_tool_routes_detected_language_projects(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module example\n")

    result = LintTool().run(tmp_path)

    assert result["engine"] == "golangci-lint"
