"""Phase 00 catalog maturity truth tests."""

from __future__ import annotations

import pytest

from rush.catalog import TOOL_MATURITY_VALUES, TOOL_SPECS
from rush.config import RushConfigError, _parse
from rush.mcp import build_server_instructions


def test_every_catalogued_tool_has_a_declared_valid_maturity() -> None:
    assert len(TOOL_SPECS) == 35
    assert all(spec.maturity in TOOL_MATURITY_VALUES for spec in TOOL_SPECS.values())
    assert TOOL_SPECS["coverage"].maturity == "importer"
    assert TOOL_SPECS["codeql"].maturity == "importer"
    assert TOOL_SPECS["pbt"].maturity == "importer"
    assert TOOL_SPECS["semantic-drift"].maturity == "browser_runtime"
    assert TOOL_SPECS["secrets"].maturity == "real_adapter"
    assert TOOL_SPECS["iac"].maturity == "real_adapter"
    assert TOOL_SPECS["iac"].engine_names == ("tflint", "checkov")
    assert TOOL_SPECS["ai-eval"].maturity == "real_adapter"
    assert TOOL_SPECS["tdd"].maturity == "real_adapter"


def test_rejects_config_for_non_configurable_browser_tools(
    tmp_path,
) -> None:

    with pytest.raises(RushConfigError, match="does not accept tool configuration"):
        _parse({"tools": {"semantic-drift": {}}}, tmp_path / "rush.toml")


def test_mcp_instructions_disclose_catalog_maturity() -> None:
    assert "Maturity" in build_server_instructions()
