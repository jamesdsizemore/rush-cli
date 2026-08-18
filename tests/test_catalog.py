"""v0.2 catalog and result-schema contracts."""

from __future__ import annotations

from rush.catalog import TOOL_SPECS
from rush.tools import ALL_TOOLS
from rush.tools.base import ToolResult


def test_catalog_matches_registered_tool_names() -> None:
    """Every registered tool has one metadata record and no duplicate name."""
    registered_names = [tool.name for tool in ALL_TOOLS]

    assert len(registered_names) == len(set(registered_names))
    assert set(TOOL_SPECS) == set(registered_names)


def test_catalog_descriptions_are_safe_for_mcp() -> None:
    """Catalog metadata remains usable as short MCP tool documentation."""
    for spec in TOOL_SPECS.values():
        assert spec.name
        assert spec.description
        assert len(spec.mcp_description) < 200


def test_tool_result_declares_v0_2_optional_extensions() -> None:
    """New metrics/artifacts/metadata fields retain the v0.1 result keys."""
    annotations = ToolResult.__annotations__

    assert {"tool", "status", "duration_ms", "summary", "findings"} <= set(annotations)
    assert {"metrics", "artifacts", "metadata"} <= set(annotations)
