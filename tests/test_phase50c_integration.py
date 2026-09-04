"""Integration tests for Phase 50c tools (attest, mem-profile, cold-start, offline-review, benchmark).

Verifies CLI --json wire format, FastMCP server registration, and permission enforcement.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from rush.cli import cli
from rush.mcp import build_server
from rush.permissions import ExecutionPermissions
from rush.tools import (
    AttestationTool,
    BenchmarkTool,
    ColdStartTool,
    MemProfileTool,
)


def test_cli_attest_json_output(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    (dist_dir / "app-0.1.0-py3-none-any.whl").write_bytes(b"wheel binary artifact")

    runner = CliRunner()
    result = runner.invoke(cli, ["attest", str(tmp_path), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["tool"] == "attest"
    assert data["status"] == "ok"
    assert (
        "in-toto" in data["summary"]
        or "SLSA" in data["summary"]
        or "draft" in data["summary"]
    )
    assert isinstance(data["findings"], list)


def test_cli_mem_profile_json_output(tmp_path: Path) -> None:
    (tmp_path / "module.py").write_text(
        "with open('f.txt', 'w') as f:\n    f.write('hi')\n", encoding="utf-8"
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["mem-profile", str(tmp_path), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["tool"] == "mem-profile"
    assert data["status"] == "ok"
    assert isinstance(data["findings"], list)


def test_cli_cold_start_json_output(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("import sys\nimport os\n", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(cli, ["cold-start", str(tmp_path), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["tool"] == "cold-start"
    assert data["status"] == "ok"
    assert isinstance(data["findings"], list)


def test_cli_offline_review_json_output(tmp_path: Path) -> None:
    (tmp_path / "code.py").write_text("a = 1", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(cli, ["offline-review", str(tmp_path), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["tool"] == "offline-review"
    assert data["status"] == "skipped"
    assert (
        "No external local LLM runner" in data["summary"]
        or "llama-cli discovered" in data["summary"]
    )


def test_cli_benchmark_json_output(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["benchmark", "check", str(tmp_path), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["tool"] == "benchmark"
    assert data["status"] == "skipped"
    assert "baseline" in data["summary"].lower()


@pytest.mark.anyio
async def test_mcp_phase50c_tools_registered_and_callable(tmp_path: Path) -> None:
    server = build_server()
    tools = await server.list_tools()
    tool_map = {t.name: t for t in tools}

    expected_tools = [
        "rush_attest",
        "rush_mem_profile",
        "rush_cold_start",
        "rush_offline_review",
        "rush_benchmark",
    ]
    for expected in expected_tools:
        assert expected in tool_map, f"FastMCP tool {expected} must be registered"
        desc = tool_map[expected].description or ""
        assert len(desc) < 200, (
            f"Description for {expected} exceeds 200 chars: {len(desc)}"
        )

    dist_dir = tmp_path / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    (dist_dir / "sample.whl").write_bytes(b"sample package")

    attest_tool = AttestationTool()
    res = attest_tool(tmp_path)
    assert res["tool"] == "attest"
    assert res["status"] == "ok"


def test_phase50c_permission_gates(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    (dist_dir / "app.whl").write_bytes(b"content")

    attest_tool = AttestationTool()
    res_attest = attest_tool.run(
        tmp_path,
        output_path="test-draft.json",
        permissions=ExecutionPermissions(artifact_write=False),
    )
    assert res_attest["status"] == "skipped"
    assert not (tmp_path / "test-draft.json").exists()

    res_traversal = attest_tool.run(
        tmp_path,
        output_path="../escaped.json",
        permissions=ExecutionPermissions(artifact_write=True),
    )
    assert res_traversal["status"] == "error"

    bench_tool = BenchmarkTool()
    res_bench = bench_tool.run(
        tmp_path,
        samples=[10.0, 12.0],
        record=True,
        permissions=ExecutionPermissions(cache_write=False),
    )
    assert res_bench["status"] == "skipped"

    mem_tool = MemProfileTool()
    (tmp_path / "file.py").write_text("pass\n", encoding="utf-8")
    res_mem = mem_tool.run(
        tmp_path,
        dynamic=True,
        permissions=ExecutionPermissions(slow=False),
    )
    assert res_mem["status"] == "skipped"

    cold_tool = ColdStartTool()
    res_cold = cold_tool.run(
        tmp_path,
        dynamic=True,
        permissions=ExecutionPermissions(slow=False),
    )
    assert res_cold["status"] == "skipped"
