"""Configuration preservation contracts."""

from __future__ import annotations

from rush.config import _parse


def test_preserves_language_specific_tool_configuration(tmp_path) -> None:
    config = _parse(
        {"tools": {"go-test": {"engine_args": ["-race"], "check": True}}},
        tmp_path / "rush.toml",
    )

    assert config.tools["go-test"].engine_args == ["-race"]
    assert config.tools["go-test"].check is True
