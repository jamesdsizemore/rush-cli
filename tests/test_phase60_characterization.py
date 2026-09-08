"""Phase 60 Workstream P60.1.1 Characterization Tests.

Freezes pre-refactoring behavior across all target domains before decomposing
maintainability hotspots (T-60.01 through T-60.06).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner
from mcp.server.fastmcp import FastMCP

from rush.cli import cli
from rush.config import ReviewConfig, RushConfig
from rush.contracts.results import ToolResultV1
from rush.discovery.workspace import discover_workspaces
from rush.engines import ENGINES
from rush.mcp import ALL_TOOLS, _register_tools, mcp_server
from rush.permissions import ExecutionPermissions
from rush.tools.base import ToolResult
from rush.tools.blast_radius import BlastRadiusAnalyzer
from rush.tools.common import (
    error_result,
    exit_code_for,
    resolve_binary,
    run_engine,
    run_subprocess,
    skipped_result,
)
from rush.tools.continuity import SessionContinuityTool
from rush.tools.db_drift import DbDriftAuditor
from rush.tools.lint import LintTool
from rush.tools.review import ReviewTool


def test_cli_catalog_options_rendering_characterization(tmp_path: Path) -> None:
    """T-60.01: Freeze CLI command generation, options parsing, and rendering."""
    runner = CliRunner()

    # 1. Verify --help rendering and catalog tool options
    res_help = runner.invoke(cli, ["lint", "--help"])
    assert res_help.exit_code == 0
    assert "Lint Python/JS/TS files at <path>" in res_help.output
    assert "--json" in res_help.output
    assert "--allow-cache-write" in res_help.output
    assert "--workspace" in res_help.output

    # 2. Verify --version rendering
    res_ver = runner.invoke(cli, ["--version"])
    assert res_ver.exit_code == 0
    assert "0.3.0" in res_ver.output

    # 3. Verify clean execution emits valid canonical JSON
    clean_file = tmp_path / "clean_cli.py"
    clean_file.write_text("x: int = 1\n", encoding="utf-8")
    res_exec = runner.invoke(cli, ["lint", str(clean_file), "--json"])
    assert res_exec.exit_code == 0
    data = json.loads(res_exec.output)
    assert data["tool"] == "lint"
    assert data["engine"] == "ruff"
    assert data["status"] == "ok"
    assert data["findings"] == []
    assert "clean" in data["summary"]

    # 4. Verify dirty execution emits exit code 1 with findings
    dirty_file = tmp_path / "dirty_cli.py"
    dirty_file.write_text("import sys\n", encoding="utf-8")
    res_dirty = runner.invoke(cli, ["lint", str(dirty_file), "--json"])
    assert res_dirty.exit_code == 1
    dirty_data = json.loads(res_dirty.output)
    assert dirty_data["status"] in ("warn", "fail")
    assert len(dirty_data["findings"]) == 1
    assert dirty_data["findings"][0]["rule"] == "F401"


def test_mcp_registration_characterization() -> None:
    """T-60.02: Freeze FastMCP tool registration and parameter schema."""
    tools = mcp_server._tool_manager._tools
    assert len(tools) == 74

    # 1. Assert all 53 catalog tools are registered with exact descriptions and path property
    assert len(ALL_TOOLS) == 53
    for tool in ALL_TOOLS:
        tool_name = f"rush_{tool.name.replace('-', '_')}"
        assert tool_name in tools, f"Catalog tool {tool_name} missing from MCP server"
        mcp_tool = tools[tool_name]
        assert mcp_tool.description == tool.mcp_description
        assert "path" in mcp_tool.parameters.get("properties", {})

    # 2. Assert custom phase tools are registered with exact descriptions and parameters
    expected_custom_tools: dict[str, tuple[str, list[str]]] = {
        "rush_ship_clean": (
            "Clean scratch directories and build caches before release",
            ["dry_run"],
        ),
        "rush_ship_env": (
            "Audit codebase environment variable usage against .env.example",
            [],
        ),
        "rush_ship_gate": (
            "Run 7-vector pre-flight release readiness cockpit",
            [],
        ),
        "rush_token_outline": (
            "Generate token-efficient AST skeleton outline of a code file",
            ["focus_symbol", "path"],
        ),
        "rush_context_retrieve": (
            "Retrieve uncompressed content from CCR chunk store by hash",
            ["chunk_hash", "path"],
        ),
        "rush_hallu_guard": (
            "Audit code imports against installed packages and stdlib",
            ["path"],
        ),
        "rush_context_mistakes_check": (
            "Check git revert history for past mistakes and anti-patterns",
            [],
        ),
        "rush_context_pack": (
            "Pack graph-pruned context outline under a strict token budget",
            ["allow_cache_write", "budget", "path", "symbol"],
        ),
        "rush_context_gain_stats": (
            "Get real-time token economy savings and cost metrics",
            [],
        ),
        "rush_blast_radius": (
            "Calculate downstream transitive blast radius for a changed file",
            ["depth", "path"],
        ),
        "rush_arch_guard": (
            "Validate codebase against clean architecture layer boundaries",
            [],
        ),
        "rush_test_heal": (
            "Diagnose flaky test race conditions and suggest fixes",
            ["runs", "target"],
        ),
        "rush_api_diff": (
            "Detect breaking public API changes against base Git ref",
            ["base"],
        ),
        "rush_db_drift": (
            "Audit ORM models against migrations to detect schema drift",
            [],
        ),
        "rush_simplify": (
            "Decompose high-complexity functions into modular helpers",
            ["file", "max_complexity"],
        ),
        "rush_strictify": (
            "Synthesize runtime type guards for unvalidated parameters",
            ["file"],
        ),
        "rush_trace": (
            "Scan codebase and specs to output requirement traceability matrix",
            [],
        ),
        "rush_mesh_acquire_lock": (
            "Acquire non-blocking multi-agent file lock",
            ["agent_id", "capability", "path"],
        ),
        "rush_mesh_release_lock": (
            "Release multi-agent file lock",
            ["agent_id", "capability", "path"],
        ),
        "rush_swarm_merge": (
            "Execute 3-way AST merge conflict resolution",
            ["base_code", "ours_code", "theirs_code"],
        ),
        "rush_attest_generate": (
            "Deprecated alias for rush_attest",
            [
                "allow_artifact_write",
                "allow_browser",
                "allow_build",
                "allow_cache_write",
                "allow_download",
                "allow_network",
                "allow_slow",
                "allowed_builders",
                "allowed_signers",
                "artifact_path",
                "builder_id",
                "output_path",
                "path",
                "trusted_roots",
                "verify",
            ],
        ),
    }

    for name, (desc, params) in expected_custom_tools.items():
        assert name in tools, f"Custom tool {name} missing from MCP server"
        custom_tool = tools[name]
        assert custom_tool.description == desc
        actual_params = sorted(custom_tool.parameters.get("properties", {}).keys())
        assert actual_params == sorted(params), f"Parameter mismatch for {name}"

    # 3. Test _register_tools on an isolated server
    fresh_server = FastMCP("test-mcp-server")
    _register_tools(fresh_server)
    assert len(fresh_server._tool_manager._tools) == 74


def test_continuity_dispatch_provider_receipt_characterization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-60.03: Freeze continuity operations (save/list/restore/context_pack/provider_resume)."""
    tool = SessionContinuityTool()

    # 1. Operation 'save'
    fingerprint = "e" * 64
    save_res = tool.run(
        tmp_path,
        operation="save",
        name="char_ckpt",
        handoff={
            "current_goal": "Preserve session characterization",
            "open_work": ["verify characterization"],
            "failure_fingerprint": fingerprint,
        },
        permissions=ExecutionPermissions(cache_write=True),
    )
    assert save_res["status"] == "ok"
    assert save_res["tool"] == "continuity"
    handoff = save_res["metadata"]["handoff"]
    assert handoff["current_goal"] == "Preserve session characterization"
    assert handoff["open_work"] == ["verify characterization"]
    receipt = handoff["failure_receipt"]
    assert receipt == {
        "fingerprint": fingerprint,
        "state": "tombstoned",
    }
    v1_res = save_res.to_tool_result_v1()
    assert isinstance(v1_res, ToolResultV1)
    assert v1_res.schema_version == "1.0.0"

    # 2. Operation 'list'
    list_res = tool.run(tmp_path, operation="list")
    assert list_res["status"] == "ok"
    assert "1" in list_res["summary"]
    assert len(list_res["raw"]) == 1
    assert list_res["raw"][0]["checkpoint_id"] == "char_ckpt"

    # 3. Operation 'restore'
    restore_res = tool.run(tmp_path, operation="restore", name="char_ckpt")
    assert restore_res["status"] == "ok"
    assert restore_res["raw"]["name"] == "char_ckpt"
    assert (
        restore_res["metadata"]["handoff"]["current_goal"]
        == "Preserve session characterization"
    )

    missing_res = tool.run(tmp_path, operation="restore", name="nonexistent_ckpt")
    assert missing_res["status"] == "skipped"

    # 4. Operation 'context_pack'
    module_path = tmp_path / "app_service.py"
    module_path.write_text(
        "def compute_total() -> int:\n    return 42\n", encoding="utf-8"
    )
    pack_res = tool.run(
        tmp_path,
        operation="context_pack",
        context_path="app_service.py",
        token_budget=1500,
    )
    assert pack_res["status"] == "ok"
    assert pack_res["tool"] == "continuity"
    envelope = pack_res["metadata"]["context_envelope"]
    assert envelope["selected_evidence"][0]["path"] == "app_service.py"
    assert envelope["tokens"]["estimated"] > 0
    assert envelope["omissions"] == []

    # 5. Operation 'provider_resume'
    denied = tool.run(
        tmp_path,
        operation="provider_resume",
        name="char_ckpt",
        provider_id="claude_code",
    )
    assert denied["status"] == "skipped"
    assert denied["metadata"]["provider_route"]["state"] == "permission_denied"

    class MockProcess:
        returncode = 0
        stdout = '{"result": "OK"}'
        stderr = ""

    calls: list[Any] = []
    monkeypatch.setattr("shutil.which", lambda _: "C:/tools/claude.cmd")
    monkeypatch.setattr(
        "subprocess.run",
        lambda cmd, **kwargs: calls.append((cmd, kwargs)) or MockProcess(),
    )

    resume_res = tool.run(
        tmp_path,
        operation="provider_resume",
        name="char_ckpt",
        provider_id="claude_code",
        permissions=ExecutionPermissions(network=True),
    )
    assert resume_res["status"] == "ok"
    assert resume_res["metadata"]["provider_route"] == {
        "provider_id": "claude_code",
        "transport": "cli",
        "state": "completed",
    }
    assert len(calls) == 1


def test_review_collection_provider_result_characterization(tmp_path: Path) -> None:
    """T-60.04: Freeze review file collection, heuristic filtering, and canonical ToolResult."""
    repo = tmp_path / "review_suite"
    repo.mkdir()

    # 1. Clean file
    clean_file = repo / "clean.py"
    clean_file.write_text(
        '"""Clean module."""\n\n'
        "def clean_fn() -> int:\n"
        '    """Clean function."""\n'
        "    return 100\n",
        encoding="utf-8",
    )

    # 2. Dirty file (TODO comment + screaming snake non-constant variable)
    dirty_file = repo / "dirty.py"
    dirty_file.write_text(
        "# TODO: refactor this code\n"
        "NOT_A_CONSTANT = 1 + 2\n"
        "def unadorned():\n"
        "    return 200\n",
        encoding="utf-8",
    )

    # 3. File with configured scaffold marker
    scaffold_file = repo / "scaffold.py"
    scaffold_file.write_text(
        "def stub_fn():\n    # RUSH_SCAFFOLD_MARKER\n    pass\n",
        encoding="utf-8",
    )

    # 4. Large file (> 1MB cap)
    large_file = repo / "huge.py"
    large_file.write_bytes(b"# huge file line\n" * 70000)
    assert large_file.stat().st_size > 1_000_000

    # 5. Ignored directory file
    venv_dir = repo / ".venv"
    venv_dir.mkdir()
    (venv_dir / "venv_module.py").write_text("# ignored\n", encoding="utf-8")

    tool = ReviewTool()

    # Run with default configuration
    res_default = tool.run(repo)
    assert res_default["tool"] == "review"
    assert res_default["engine"] == "heuristic-v1"
    assert res_default["review_kind"] == "heuristic"
    assert res_default["review_provider"] is None
    assert isinstance(res_default["findings"], list)

    collected_paths = {f["path"] for f in res_default["findings"]}
    assert not any(".venv" in p for p in collected_paths)
    assert not any("huge.py" in p for p in collected_paths)
    assert any("dirty.py" in p for p in collected_paths)

    # Run with scaffold marker configuration
    cfg = RushConfig(review=ReviewConfig(scaffold_markers=["RUSH_SCAFFOLD_MARKER"]))
    res_scaffold = tool.run(repo, config=cfg)
    scaffold_findings = [
        f for f in res_scaffold["findings"] if f.get("rule") == "scaffold-marker"
    ]
    assert len(scaffold_findings) == 1
    assert "RUSH_SCAFFOLD_MARKER" in scaffold_findings[0]["message"]


def test_common_subprocess_result_characterization(tmp_path: Path) -> None:
    """T-60.05: Freeze binary resolution, subprocess execution, redaction, and result helpers."""
    # 1. resolve_binary
    py_bin = resolve_binary("python")
    assert py_bin is not None
    assert "python" in py_bin.lower()
    assert resolve_binary("nonexistent_binary_phase60_abc") is None

    # 2. run_subprocess
    proc = run_subprocess([sys.executable, "-c", "print('subprocess_stdout_check')"])
    assert isinstance(proc, subprocess.CompletedProcess)
    assert proc.returncode == 0
    assert proc.stdout.strip() == "subprocess_stdout_check"

    # 3. Bounded secret redaction in subprocess output
    secret_token = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz012345"
    proc_redacted = run_subprocess([sys.executable, "-c", f"print('{secret_token}')"])
    assert secret_token not in proc_redacted.stdout
    assert "[REDACTED_ANTHROPIC_KEY]" in proc_redacted.stdout

    # 4. run_engine with permission gating
    ruff_engine = ENGINES["ruff"]
    skipped_perm = run_engine(
        ruff_engine,
        tmp_path,
        permissions=ExecutionPermissions(slow=False),
        required_permissions=ExecutionPermissions(slow=True),
    )
    assert skipped_perm["status"] == "skipped"
    assert "requires permission: --allow-slow" in skipped_perm["summary"]
    assert skipped_perm["metadata"]["execution"]["mode"] == "executed"

    # 5. run_engine with missing binary
    class DummyEngine:
        name = "dummy_engine"
        binary = "nonexistent_binary_xyz_999"

    skipped_bin = run_engine(DummyEngine(), tmp_path)  # type: ignore[arg-type]
    assert skipped_bin["status"] == "skipped"
    assert "nonexistent_binary_xyz_999 not on PATH" in skipped_bin["summary"]

    # 6. skipped_result and error_result
    s_res = skipped_result(
        "test_tool", "test_engine", "not installed", metadata={"meta_k": "meta_v"}
    )
    assert s_res["status"] == "skipped"
    assert s_res["summary"] == "skipped: not installed"
    assert s_res["metadata"] == {"meta_k": "meta_v"}

    e_res = error_result(
        "test_tool",
        "test_engine",
        "process timeout",
        terminal_reason="timeout",
        partial=True,
    )
    assert e_res["status"] == "error"
    assert e_res["summary"] == "error: process timeout"
    assert e_res["metadata"]["terminal_reason"] == "timeout"
    assert e_res["metadata"]["partial"] is True

    # 7. exit_code_for
    assert exit_code_for("ok") == 0
    assert exit_code_for("skipped") == 0
    assert exit_code_for("warn") == 1
    assert exit_code_for("fail") == 1
    assert exit_code_for("error") == 2
    dummy_tool_res = ToolResult(
        tool="test",
        engine=None,
        engine_version=None,
        status="ok",
        duration_ms=10,
        summary="ok summary",
        findings=[],
        raw=None,
    )
    assert exit_code_for(dummy_tool_res) == 0
    assert exit_code_for({"status": "error"}) == 2


def test_lint_and_traversal_state_characterization(tmp_path: Path) -> None:
    """T-60.06: Freeze blast radius, workspace discovery, db drift, and lint tool execution."""
    # 1. BlastRadiusAnalyzer.analyze()
    mod_core = tmp_path / "core_mod.py"
    mod_core.write_text("def base_calc(): return 10\n", encoding="utf-8")
    mod_api = tmp_path / "api_mod.py"
    mod_api.write_text(
        "from core_mod import base_calc\ndef endpoint(): return base_calc()\n",
        encoding="utf-8",
    )
    mod_test = tmp_path / "test_api_mod.py"
    mod_test.write_text(
        "import core_mod\ndef test_fn(): assert core_mod.base_calc() == 10\n",
        encoding="utf-8",
    )

    analyzer = BlastRadiusAnalyzer(project_root=tmp_path)
    report = analyzer.analyze([mod_core], max_depth=3)
    assert sorted(report.affected_files) == ["api_mod.py", "test_api_mod.py"]
    assert "api_mod.py" in report.affected_routes
    assert report.recommended_tests == ["test_api_mod.py"]
    assert report.risk_score in ("LOW", "MEDIUM", "HIGH")

    # 2. discover_workspaces()
    (tmp_path / "pnpm-workspace.yaml").write_text(
        "packages:\n  - 'packages/*'\n", encoding="utf-8"
    )
    pkg_1 = tmp_path / "packages" / "pkg-1"
    pkg_1.mkdir(parents=True)
    (pkg_1 / "package.json").write_text(
        '{"name": "@rush/pkg-1", "dependencies": {}}', encoding="utf-8"
    )
    pkg_2 = tmp_path / "packages" / "pkg-2"
    pkg_2.mkdir(parents=True)
    (pkg_2 / "package.json").write_text(
        '{"name": "@rush/pkg-2", "dependencies": {"@rush/pkg-1": "*"}}',
        encoding="utf-8",
    )

    workspaces = discover_workspaces(tmp_path)
    ws_names = [w.name for w in workspaces]
    assert sorted(ws_names) == ["@rush/pkg-1", "@rush/pkg-2"]
    pkg2_obj = next(w for w in workspaces if w.name == "@rush/pkg-2")
    assert "@rush/pkg-1" in pkg2_obj.dependencies

    # 3. DbDriftAuditor.audit_drift()
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True)
    (src_dir / "models.py").write_text(
        "class CustomerModel:\n    id: int\n    email: str\n    loyalty_points: int\n",
        encoding="utf-8",
    )
    mig_dir = tmp_path / "migrations"
    mig_dir.mkdir(parents=True)
    (mig_dir / "001.sql").write_text(
        "CREATE TABLE customers (\n    id INTEGER,\n    email VARCHAR\n);\n",
        encoding="utf-8",
    )

    auditor = DbDriftAuditor(project_root=tmp_path)
    drift = auditor.audit_drift()
    assert drift["passed"] is False
    assert drift["drift_count"] == 1
    issue = drift["drift_issues"][0]
    assert issue["model"] == "CustomerModel"
    assert issue["unmigrated_fields"] == ["loyalty_points"]

    # 4. LintTool.run()
    lint_tool = LintTool()
    clean_lint_file = tmp_path / "clean_code.py"
    clean_lint_file.write_text("TOTAL_SCORE: int = 10\n", encoding="utf-8")
    lint_res_clean = lint_tool.run(clean_lint_file)
    assert lint_res_clean["status"] == "ok"
    assert lint_res_clean["tool"] == "lint"
    assert lint_res_clean["engine"] == "ruff"
    assert lint_res_clean["findings"] == []

    dirty_lint_file = tmp_path / "dirty_code.py"
    dirty_lint_file.write_text("import os\n", encoding="utf-8")
    lint_res_dirty = lint_tool.run(dirty_lint_file)
    assert lint_res_dirty["status"] in ("warn", "fail")
    assert len(lint_res_dirty["findings"]) == 1
    assert lint_res_dirty["findings"][0]["rule"] == "F401"
