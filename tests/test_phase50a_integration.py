"""Phase 50a end-to-end integration tests for error-catalog, license-matrix, and iam-audit."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from rush.cli import cli
from rush.mcp import build_server
from rush.tools import ALL_TOOLS


def test_cli_error_catalog_json_output(tmp_path: Path) -> None:
    runner = CliRunner()
    src_file = tmp_path / "app.py"
    src_file.write_text(
        "def run():\n    raise ValueError('invalid input')\n",
        encoding="utf-8",
    )

    res = runner.invoke(cli, ["error-catalog", str(tmp_path), "--json"])
    assert res.exit_code == 0
    data = json.loads(res.output)
    assert data["tool"] == "error-catalog"
    assert data["status"] == "ok"
    assert isinstance(data["findings"], list)
    assert len(data["findings"]) >= 1
    assert any(f["rule_id"] == "ERR_VALUE" for f in data["findings"])


def test_cli_license_matrix_json_output(tmp_path: Path) -> None:
    runner = CliRunner()
    pkg_json = tmp_path / "package.json"
    pkg_json.write_text(
        json.dumps({"name": "test-pkg", "dependencies": {"lodash": "^4.17.21"}}),
        encoding="utf-8",
    )

    res = runner.invoke(cli, ["license-matrix", str(tmp_path), "--json"])
    assert res.exit_code in (0, 1)
    data = json.loads(res.output)
    assert data["tool"] == "license-matrix"
    assert "metrics" in data
    assert data["metrics"]["total_packages"] >= 1


def test_cli_iam_audit_json_output(tmp_path: Path) -> None:
    runner = CliRunner()
    app_file = tmp_path / "storage_client.py"
    app_file.write_text(
        "import boto3\ns3 = boto3.client('s3')\ns3.get_object(Bucket='b', Key='k')\n",
        encoding="utf-8",
    )

    res = runner.invoke(cli, ["iam-audit", str(tmp_path), "--json"])
    assert res.exit_code == 0
    data = json.loads(res.output)
    assert data["tool"] == "iam-audit"
    assert data["status"] == "ok"
    assert "policy" in data.get("raw", {})
    actions = data["raw"]["actions"]
    assert "s3:GetObject" in actions


def test_mcp_phase50a_tools_registered_and_callable() -> None:
    server = build_server()
    registered_names = {t.name for t in server._tool_manager.list_tools()}

    expected_tools = {
        "rush_error_catalog",
        "rush_license_matrix",
        "rush_iam_audit",
    }
    for tool_name in expected_tools:
        assert tool_name in registered_names, (
            f"Expected {tool_name} to be registered in MCP server"
        )


def test_phase50a_tools_fail_closed_on_unauthorized_artifact_write(
    tmp_path: Path,
) -> None:
    error_tool = next(t for t in ALL_TOOLS if t.name == "error-catalog")
    py_file = tmp_path / "service.py"
    py_file.write_text("raise RuntimeError('fatal')\n", encoding="utf-8")

    # error-catalog without permission must return skipped for markdown export
    res = error_tool.run(tmp_path, export_path="catalog.md")
    assert res["status"] == "skipped"
    assert (
        "artifact-write" in res["summary"].lower()
        or "permission" in res["summary"].lower()
    )
    assert not (tmp_path / "catalog.md").exists()
