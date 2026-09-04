"""v0.2 catalog and result-schema contracts."""

from __future__ import annotations

from rush.catalog import TOOL_SPECS
from rush.tools import ALL_TOOLS
from rush.tools.base import ToolResult

PHASE50_OPTION_TYPES: dict[str, dict[str, type]] = {
    "attest": {"artifact_path": str, "output_path": str, "builder_id": str},
    "license-matrix": {"allowed_licenses": tuple},
    "iam-audit": {"services": tuple, "output_policy_file": str},
    "prompt-eval": {
        "golden_path": str,
        "pass_rate_threshold": float,
        "max_cost_threshold": float,
        "max_tokens_threshold": int,
    },
    "mem-profile": {"dynamic": bool},
    "cold-start": {"dynamic": bool},
    "media-opt": {"sanitize": bool, "optimize": bool},
    "offline-review": {
        "model_path": str,
        "expected_sha256": str,
        "defect_threshold": float,
    },
    "tui-diff": {"base_ref": str},
    "benchmark": {
        "threshold_percent": float,
        "record": bool,
        "operation": str,
        "baseline_name": str,
    },
    "error-catalog": {"export_path": str},
    "provenance-ai": {"max_commits": int},
    "dead-asset": {"export_manifest": str},
    "pr-synthesize": {"base_ref": str, "export_path": str},
}


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


def test_tool_option_spec_declares_closed_types_and_constraints() -> None:
    from rush.catalog import ToolOptionSpec

    spec_str = ToolOptionSpec(name="prefix", value_type=str, default="ERR_")
    assert spec_str.name == "prefix"
    assert spec_str.value_type is str
    assert spec_str.default == "ERR_"

    spec_int = ToolOptionSpec(
        name="since_days", value_type=int, default=90, minimum=1, maximum=3650
    )
    assert spec_int.minimum == 1
    assert spec_int.maximum == 3650

    spec_path = ToolOptionSpec(name="output_module", value_type=str, path_kind="file")
    assert spec_path.path_kind == "file"


def test_tool_spec_exposes_immutable_option_specs() -> None:
    from rush.catalog import ToolOptionSpec, ToolSpec

    opt = ToolOptionSpec(name="opt1", value_type=str, default="val")
    spec = ToolSpec(
        name="test-tool",
        category="security",
        description="test desc",
        mcp_description="mcp desc",
        engine_names=(),
        option_specs=(opt,),
    )
    assert isinstance(spec.option_specs, tuple)
    assert spec.option_specs == (opt,)


def test_phase50_option_specs_cover_every_admitted_behavior() -> None:
    """Every Phase 50 public option is declared once with its exact type."""
    for tool_name, expected_options in PHASE50_OPTION_TYPES.items():
        declared = {
            option.name: option.value_type
            for option in TOOL_SPECS[tool_name].option_specs
        }
        assert declared == expected_options
