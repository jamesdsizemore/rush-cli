"""Configuration preservation contracts."""

from __future__ import annotations

import pytest

from rush.config import RushConfigError, _parse


def test_preserves_catalogued_tool_configuration(tmp_path) -> None:
    config = _parse(
        {"tools": {"typecheck": {"engine_args": ["--strict"], "check": True}}},
        tmp_path / "rush.toml",
    )

    assert config.tools["typecheck"].engine_args == ["--strict"]
    assert config.tools["typecheck"].check is True


def test_rejects_unknown_tool_configuration(tmp_path) -> None:
    with pytest.raises(RushConfigError, match="unknown tool"):
        _parse({"tools": {"typo-tool": {}}}, tmp_path / "rush.toml")


def test_parses_review_source_policy_markers_and_exclusions(tmp_path) -> None:
    config = _parse(
        {
            "review": {
                "scaffold_markers": ["TODO: replace this scaffold"],
                "source_policy_exclude": ["generated/**"],
            }
        },
        tmp_path / "rush.toml",
    )

    assert config.review.scaffold_markers == ["TODO: replace this scaffold"]
    assert config.review.source_policy_exclude == ["generated/**"]


def test_detect_project_stacks_python(tmp_path) -> None:
    from rush.discovery.stack import detect_project_stacks

    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    stacks = detect_project_stacks(tmp_path)
    assert any(s.language == "python" for s in stacks)


def test_detect_project_stacks_typescript(tmp_path) -> None:
    from rush.discovery.stack import detect_project_stacks

    (tmp_path / "package.json").write_text('{"name": "test"}', encoding="utf-8")
    (tmp_path / "tsconfig.json").write_text("{}", encoding="utf-8")
    stacks = detect_project_stacks(tmp_path)
    assert any(s.language == "typescript" for s in stacks)


def test_generate_initial_config(tmp_path) -> None:
    from rush.tools.init_config import generate_initial_config

    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    cfg = generate_initial_config(tmp_path)
    assert "[project]" in cfg
    assert "[cache]" in cfg


def test_setup_wizard_non_interactive(tmp_path) -> None:
    from rush.tools.setup_wizard import run_setup_wizard

    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    res = run_setup_wizard(tmp_path, non_interactive=True)
    assert "python" in res["stacks"]
    assert len(res["skipped"]) > 0


def test_install_engine_package_security_rejection() -> None:
    from rush.tools.setup_wizard import install_engine_package

    with pytest.raises(ValueError, match="Invalid or hostile package name"):
        install_engine_package("npm", "malicious; rm -rf /")

