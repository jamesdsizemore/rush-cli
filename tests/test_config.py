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
