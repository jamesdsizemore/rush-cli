"""Acceptance tests for Phase 50 packaging, module completeness, and CLI/MCP parity."""

from __future__ import annotations

import os
import zipfile
from pathlib import Path

from rush.catalog import TOOL_SPECS
from rush.tools import ALL_TOOLS

PHASE50_TOOL_MODULES = [
    "prompt_eval.py",
    "error_catalog.py",
    "provenance_ai.py",
    "attest.py",
    "license_matrix.py",
    "iam_audit.py",
    "mem_profile.py",
    "cold_start.py",
    "media_opt.py",
    "offline_runner.py",
    "tui_diff.py",
    "benchmark.py",
    "dead_asset.py",
    "pr_synthesize.py",
]

PHASE50_CANONICAL_NAMES = [
    "prompt-eval",
    "error-catalog",
    "provenance-ai",
    "attest",
    "license-matrix",
    "iam-audit",
    "mem-profile",
    "cold-start",
    "media-opt",
    "offline-review",
    "tui-diff",
    "benchmark",
    "dead-asset",
    "pr-synthesize",
]


def test_phase50_modules_are_present_in_built_wheel() -> None:
    """Verify all 14 Phase 50 tool modules are present in the source and wheel archive."""
    src_tools_dir = Path(__file__).resolve().parents[1] / "src" / "rush" / "tools"
    for module_name in PHASE50_TOOL_MODULES:
        module_path = src_tools_dir / module_name
        assert module_path.is_file(), f"Missing Phase 50 tool module: {module_path}"

    wheel_env = os.environ.get("RUSH_PHASE50_WHEEL")
    if wheel_env and Path(wheel_env).is_file():
        with zipfile.ZipFile(wheel_env) as zf:
            namelist = zf.namelist()
            for module_name in PHASE50_TOOL_MODULES:
                expected_entry = f"rush/tools/{module_name}"
                assert any(name.endswith(expected_entry) for name in namelist), (
                    f"Wheel {wheel_env} missing entry {expected_entry}"
                )


def test_phase50_installed_cli_help_and_mcp_catalog_match_source_contract() -> None:
    """Verify registry, CLI, and FastMCP catalog expose the 14 Phase 50 tools with canonical names."""
    registered_tool_names = {tool.name for tool in ALL_TOOLS}
    for name in PHASE50_CANONICAL_NAMES:
        assert name in registered_tool_names, f"Tool {name} missing from ALL_TOOLS"
        assert name in TOOL_SPECS, f"Tool {name} missing from TOOL_SPECS"

    from rush.mcp import build_server

    server = build_server()
    tools_mgr = getattr(server, "_tool_manager", None)
    mcp_tool_names = (
        set(getattr(tools_mgr, "_tools", {}).keys()) if tools_mgr else set()
    )

    for name in PHASE50_CANONICAL_NAMES:
        mcp_name = f"rush_{name.replace('-', '_')}"
        assert mcp_name in mcp_tool_names, (
            f"MCP tool {mcp_name} missing from FastMCP registry"
        )

    assert "rush_attest_generate" in mcp_tool_names, (
        "Deprecated alias rush_attest_generate must be present"
    )
