"""Integration tests for Phase 50b tools across CLI and FastMCP transports.

Verifies canonical JSON schemas, CLI options, FastMCP registrations,
read-only invariants, and fail-closed permission checks for:
- rush provenance-ai / rush_provenance_ai
- rush dead-asset / rush_dead_asset
- rush pr-synthesize / rush_pr_synthesize
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from click.testing import CliRunner

from rush.cli import cli
from rush.mcp import build_server
from rush.permissions import ExecutionPermissions
from rush.tools.dead_asset import DeadAssetTool
from rush.tools.pr_synthesize import PrSynthesizeTool
from rush.tools.provenance_ai import ProvenanceAiTool


def _init_git_repo(repo_dir: Path) -> None:
    subprocess.run(
        ["git", "init", "-b", "main"], cwd=repo_dir, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test Committer"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "committer@example.com"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    (repo_dir / "index.py").write_text("print('hello')\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "commit",
            "-m",
            "feat: initial commit\n\nCo-authored-by: Claude <noreply@anthropic.com>\nModel: claude-3-7-sonnet",
        ],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )


def test_cli_provenance_ai_json_output(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["provenance-ai", str(tmp_path), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["tool"] == "provenance-ai"
    assert data["status"] == "ok"
    assert "findings" in data
    assert data["raw"]["commits_audited"] >= 1
    assert data["raw"]["ai_assisted_count"] >= 1


def test_cli_dead_asset_json_output(tmp_path: Path) -> None:
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir(parents=True)
    (assets_dir / "dead_banner.png").write_bytes(b"image_content")
    (tmp_path / "main.py").write_text("print('no assets referenced')", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(cli, ["dead-asset", str(tmp_path), "--json"])
    assert result.exit_code == 1  # warn status due to dead asset
    data = json.loads(result.output)
    assert data["tool"] == "dead-asset"
    assert data["status"] == "warn"
    assert data["raw"]["dead_assets_count"] == 1
    assert data["metadata"]["potential_savings_bytes"] == len(b"image_content")


def test_cli_pr_synthesize_json_output(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / "feature.py").write_text("def f(): pass\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: add feature"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["pr-synthesize", str(tmp_path), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["tool"] == "pr-synthesize"
    assert data["status"] == "ok"
    assert data["metadata"]["risk_tier"] == "low"
    assert "pr_card" in data["raw"]


def test_mcp_phase50b_tools_registered_and_callable(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    server = build_server()
    tools = server._tool_manager._tools

    assert "rush_provenance_ai" in tools
    assert "rush_dead_asset" in tools
    assert "rush_pr_synthesize" in tools

    # Test direct ToolFn invocation via call interface
    prov_res = ProvenanceAiTool()(tmp_path)
    assert prov_res["tool"] == "provenance-ai"
    assert prov_res["status"] == "ok"

    dead_res = DeadAssetTool()(tmp_path)
    assert dead_res["tool"] == "dead-asset"
    assert dead_res["status"] == "skipped"

    pr_res = PrSynthesizeTool()(tmp_path, base_ref="HEAD")
    assert pr_res["tool"] == "pr-synthesize"
    assert pr_res["status"] == "ok"


def test_phase50b_tools_fail_closed_on_unauthorized_artifact_write(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)

    # Dead asset export manifest without permission
    assets = tmp_path / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    dead_pic = assets / "pic.png"
    dead_pic.write_bytes(b"pic")
    manifest_file = tmp_path / "manifest.json"

    dead_tool = DeadAssetTool()
    res_manifest = dead_tool.run(
        tmp_path,
        export_manifest=manifest_file,
        permissions=ExecutionPermissions(artifact_write=False),
    )
    assert res_manifest["status"] == "skipped"
    assert not manifest_file.exists()
    assert dead_pic.exists()

    # PR synthesize export without permission
    pr_tool = PrSynthesizeTool()
    export_out = tmp_path / "summary.md"
    res_export = pr_tool.run(
        tmp_path,
        export_path=export_out,
        permissions=ExecutionPermissions(artifact_write=False),
    )
    assert res_export["status"] == "skipped"
    assert not export_out.exists()
