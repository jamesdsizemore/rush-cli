"""Phase 60 Workstream P60.7 Final Refactor and Complexity Reduction Verification.

Validates that maintainability hotspot reduction and modularity decomposition are
complete without exceptions (T-60.26).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE_FILE = PROJECT_ROOT / "governance" / "maintainability-baseline.toml"
EXEMPTIONS_FILE = PROJECT_ROOT / "governance" / "maintainability-exemptions.toml"


def test_hotspot_complexity_and_modularity_reduction() -> None:
    """T-60.26: Verify all 8 hotspots <= 10 C901, extracted modules own symbols, 0 exemptions."""
    # 1. Verify maintainability-baseline.toml targets and exemptions file
    assert BASELINE_FILE.exists(), f"Baseline file {BASELINE_FILE} missing"
    assert EXEMPTIONS_FILE.exists(), f"Exemptions file {EXEMPTIONS_FILE} missing"

    baseline_data = tomllib.loads(BASELINE_FILE.read_text(encoding="utf-8"))
    targets = baseline_data.get("targets", [])
    assert len(targets) == 8, f"Expected 8 baseline targets, got {len(targets)}"

    expected_symbols = {
        "discover_workspaces",
        "BlastRadiusAnalyzer.analyze",
        "SessionContinuityTool.run",
        "SessionContinuityTool._provider_resume",
        "DbDriftAuditor.audit_drift",
        "LintTool.run",
        "ReviewTool.run",
        "_register_tools",
    }
    actual_symbols = {t["symbol"] for t in targets}
    assert actual_symbols == expected_symbols, (
        f"Target symbol mismatch: expected {expected_symbols}, got {actual_symbols}"
    )

    # 2. Verify all 8 target symbols and modules comply with McCabe C901 <= 10
    ruff_path = (
        PROJECT_ROOT
        / ".venv"
        / ("Scripts" if sys.platform == "win32" else "bin")
        / ("ruff.exe" if sys.platform == "win32" else "ruff")
    )
    ruff_cmd = str(ruff_path) if ruff_path.exists() else shutil.which("ruff")
    assert ruff_cmd, "ruff executable not found"

    check_files = [
        "src/rush/cli.py",
        "src/rush/mcp.py",
        "src/rush/tools/continuity.py",
        "src/rush/tools/review.py",
        "src/rush/tools/common.py",
        "src/rush/tools/lint.py",
        "src/rush/tools/blast_radius.py",
        "src/rush/discovery/workspace.py",
        "src/rush/tools/db_drift.py",
        "src/rush/cli_support",
        "src/rush/mcp_support",
        "src/rush/continuity",
        "src/rush/review",
        "src/rush/runtime",
        "src/rush/tools/blast_radius_graph.py",
        "src/rush/discovery/workspace_graph.py",
        "src/rush/tools/db_drift_rules.py",
    ]

    cmd = [
        ruff_cmd,
        "check",
        "--select",
        "C901",
        "--config",
        "lint.mccabe.max-complexity = 10",
        "--output-format",
        "concise",
        *check_files,
    ]
    proc = subprocess.run(
        cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, (
        f"Ruff C901 check failed (returncode={proc.returncode}):\n{proc.stdout}\n{proc.stderr}"
    )
    assert "C901" not in proc.stdout, f"Expected 0 findings, got:\n{proc.stdout}"
    assert "All checks passed!" in proc.stdout, (
        f"Expected clean pass, got:\n{proc.stdout}"
    )

    # 3. Verify extracted directories/files exist and own their respective symbols
    # 3a. src/rush/cli_support/
    cli_support_dir = PROJECT_ROOT / "src" / "rush" / "cli_support"
    assert cli_support_dir.is_dir(), f"{cli_support_dir} is not a directory"
    from rush.cli_support import catalog_commands, options, rendering

    assert options._extract_permissions.__module__ == "rush.cli_support.options"
    assert options.permission_options.__module__ == "rush.cli_support.options"
    assert (
        catalog_commands.build_catalog_path_command.__module__
        == "rush.cli_support.catalog_commands"
    )
    assert rendering._run_tool.__module__ == "rush.cli_support.rendering"
    assert rendering._render_session_result.__module__ == "rush.cli_support.rendering"

    # 3b. src/rush/mcp_support/
    mcp_support_dir = PROJECT_ROOT / "src" / "rush" / "mcp_support"
    assert mcp_support_dir.is_dir(), f"{mcp_support_dir} is not a directory"
    from rush.mcp_support import tool_registry

    assert (
        tool_registry.register_all_tools.__module__ == "rush.mcp_support.tool_registry"
    )
    assert (
        tool_registry.register_custom_tools.__module__
        == "rush.mcp_support.tool_registry"
    )
    assert (
        tool_registry.make_tool_wrapper.__module__ == "rush.mcp_support.tool_registry"
    )
    assert (
        tool_registry.make_custom_wrapper.__module__ == "rush.mcp_support.tool_registry"
    )

    # 3c. src/rush/continuity/
    continuity_dir = PROJECT_ROOT / "src" / "rush" / "continuity"
    assert continuity_dir.is_dir(), f"{continuity_dir} is not a directory"
    from rush.continuity import context, coordination, providers, receipts

    # Context symbols
    ctx_sym = getattr(context, "pack_context", getattr(context, "_context_pack", None))
    assert ctx_sym is not None and ctx_sym.__module__ == "rush.continuity.context"
    # Coordination symbols
    assert coordination.check_coordination.__module__ == "rush.continuity.coordination"
    assert coordination.preview_merge.__module__ == "rush.continuity.coordination"
    assert (
        coordination.recover_coordination.__module__ == "rush.continuity.coordination"
    )
    # Providers symbols
    assert providers.resume_provider.__module__ == "rush.continuity.providers"
    assert providers.resume_omniroute.__module__ == "rush.continuity.providers"
    assert providers.provider_handoff.__module__ == "rush.continuity.providers"
    assert providers.windows_cmd_command.__module__ == "rush.continuity.providers"
    assert providers.provider_command.__module__ == "rush.continuity.providers"
    assert providers.provider_prompt.__module__ == "rush.continuity.providers"
    # Receipts symbols
    assert receipts.save_receipt.__module__ == "rush.continuity.receipts"
    assert receipts.restore_receipt.__module__ == "rush.continuity.receipts"

    # 3d. src/rush/review/
    review_dir = PROJECT_ROOT / "src" / "rush" / "review"
    assert review_dir.is_dir(), f"{review_dir} is not a directory"
    from rush.review import collection, llm, results

    collect_fn = getattr(
        collection,
        "collect_reviewable_files",
        getattr(collection, "_collect_reviewable_files", None),
    )
    assert collect_fn is not None and collect_fn.__module__ == "rush.review.collection"
    read_fn = getattr(
        collection,
        "read_file_safely",
        getattr(collection, "_read_file_safely", None),
    )
    assert read_fn is not None and read_fn.__module__ == "rush.review.collection"
    maybe_llm = getattr(llm, "maybe_call_llm", getattr(llm, "_maybe_call_llm", None))
    assert maybe_llm is not None and maybe_llm.__module__ == "rush.review.llm"
    assert results.assemble_review_result.__module__ == "rush.review.results"

    # 3e. src/rush/runtime/
    runtime_dir = PROJECT_ROOT / "src" / "rush" / "runtime"
    assert runtime_dir.is_dir(), f"{runtime_dir} is not a directory"
    from rush.runtime import binaries, result_helpers, subprocesses

    assert binaries.resolve_binary.__module__ == "rush.runtime.binaries"
    assert subprocesses.run_subprocess.__module__ == "rush.runtime.subprocesses"
    assert subprocesses.run_engine.__module__ == "rush.runtime.subprocesses"
    assert result_helpers.skipped_result.__module__ == "rush.runtime.result_helpers"
    assert result_helpers.error_result.__module__ == "rush.runtime.result_helpers"
    assert result_helpers.exit_code_for.__module__ == "rush.runtime.result_helpers"

    # 3f. src/rush/tools/blast_radius_graph.py
    blast_radius_graph_file = (
        PROJECT_ROOT / "src" / "rush" / "tools" / "blast_radius_graph.py"
    )
    assert blast_radius_graph_file.is_file(), f"{blast_radius_graph_file} missing"
    from rush.tools import blast_radius_graph

    assert (
        blast_radius_graph.build_reverse_import_graph.__module__
        == "rush.tools.blast_radius_graph"
    )
    assert (
        blast_radius_graph.walk_impacted_paths.__module__
        == "rush.tools.blast_radius_graph"
    )

    # 3g. src/rush/discovery/workspace_graph.py
    workspace_graph_file = (
        PROJECT_ROOT / "src" / "rush" / "discovery" / "workspace_graph.py"
    )
    assert workspace_graph_file.is_file(), f"{workspace_graph_file} missing"
    from rush.discovery import workspace_graph

    assert (
        workspace_graph.discover_workspace_packages.__module__
        == "rush.discovery.workspace_graph"
    )
    assert (
        workspace_graph.topological_sort_workspace_packages.__module__
        == "rush.discovery.workspace_graph"
    )

    # 3h. src/rush/tools/db_drift_rules.py
    db_drift_rules_file = PROJECT_ROOT / "src" / "rush" / "tools" / "db_drift_rules.py"
    assert db_drift_rules_file.is_file(), f"{db_drift_rules_file} missing"
    from rush.tools import db_drift_rules

    assert db_drift_rules.collect_models.__module__ == "rush.tools.db_drift_rules"
    assert db_drift_rules.collect_migrations.__module__ == "rush.tools.db_drift_rules"
    assert db_drift_rules.evaluate_drift.__module__ == "rush.tools.db_drift_rules"

    # 4. Verify maintainability-exemptions.toml has strictly 0 exemptions
    exemptions_data = tomllib.loads(EXEMPTIONS_FILE.read_text(encoding="utf-8"))
    exemptions = exemptions_data.get("exemptions", [])
    assert exemptions == [], f"Expected 0 exemptions, found: {exemptions}"
    assert len(exemptions) == 0
