"""Phase 02 Checkov v3.3.9 and dual-IaC reference-adapter contracts."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import checkov
from rush.engines.checkov import CheckovEngine
from rush.tools.base import ToolResult
from rush.tools.common import run_engine
from rush.tools.iac import IacTool


def test_checkov_uses_local_terraform_json_argv_and_sanitized_environment(
    monkeypatch, tmp_path: Path
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout='{"results": {"failed_checks": [], "parsing_errors": []}}',
            stderr="",
        )

    monkeypatch.setattr(checkov, "resolve_binary", lambda _binary: "C:/bin/checkov")
    monkeypatch.setattr(checkov, "run_subprocess", fake_run)
    monkeypatch.setenv("BC_API_KEY", "must-not-reach-child")
    monkeypatch.setenv("DOWNLOAD_EXTERNAL_MODULES", "true")

    raw = CheckovEngine().run(tmp_path, [str(tmp_path / "main.tf")], cwd=tmp_path)

    assert raw == {
        "exit_code": 0,
        "stdout": '{"results": {"failed_checks": [], "parsing_errors": []}}',
        "stderr": "",
    }
    assert calls[0][0] == [
        "C:/bin/checkov",
        "--directory",
        str(tmp_path),
        "--framework",
        "terraform",
        "--output",
        "json",
        "--skip-download",
        "--download-external-modules",
        "false",
    ]
    env = calls[0][1]["env"]
    assert isinstance(env, dict)
    assert env["DOWNLOAD_EXTERNAL_MODULES"] == "false"
    assert "BC_API_KEY" not in env
    assert "PRISMA_API_URL" not in env


def test_checkov_normalizes_failed_checks_and_clean_reports(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(CheckovEngine, "version", lambda _self: "3.3.9")
    failing = CheckovEngine().normalize(
        {
            "exit_code": 1,
            "stdout": """{
                "results": {
                    "failed_checks": [{
                        "check_id": "CKV_AWS_1",
                        "check_name": "Example policy",
                        "severity": "HIGH",
                        "file_path": "/main.tf",
                        "file_line_range": [4, 7]
                    }],
                    "parsing_errors": []
                }
            }""",
            "stderr": "",
        },
        tmp_path,
        "iac",
    )
    clean = CheckovEngine().normalize(
        {
            "exit_code": 0,
            "stdout": '{"results": {"failed_checks": [], "parsing_errors": []}}',
            "stderr": "",
        },
        tmp_path,
        "iac",
    )

    assert failing["status"] == "warn"
    assert failing["findings"] == [
        {
            "rule": "CKV_AWS_1",
            "severity": "error",
            "message": "Example policy",
            "path": str(tmp_path / "main.tf"),
            "line": 4,
        }
    ]
    assert clean["status"] == "ok"
    assert clean["findings"] == []


def test_checkov_rejects_malformed_or_partial_engine_reports(tmp_path: Path) -> None:
    engine = CheckovEngine()

    malformed = engine.normalize(
        {"exit_code": 1, "stdout": "not-json", "stderr": ""}, tmp_path, "iac"
    )
    partial = engine.normalize(
        {
            "exit_code": 1,
            "stdout": '{"results": {"failed_checks": [], "parsing_errors": ["bad tf"]}}',
            "stderr": "",
        },
        tmp_path,
        "iac",
    )

    assert malformed["status"] == "error"
    assert malformed["metadata"]["terminal_reason"] == "malformed_output"
    assert partial["status"] == "error"
    assert partial["metadata"]["terminal_reason"] == "engine_error"


def test_checkov_missing_and_timeout_are_structured(
    monkeypatch, tmp_path: Path
) -> None:
    engine = CheckovEngine()
    monkeypatch.setattr("rush.tools.common.engine_on_path", lambda _binary: False)
    missing = run_engine(engine, tmp_path, tool_name="iac")

    monkeypatch.setattr("rush.tools.common.engine_on_path", lambda _binary: True)

    def raise_timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("checkov", 180)

    monkeypatch.setattr(engine, "run", raise_timeout)
    timed_out = run_engine(engine, tmp_path, tool_name="iac")

    assert missing["status"] == "skipped"
    assert timed_out["status"] == "error"
    assert timed_out["metadata"]["terminal_reason"] == "timeout"


def test_iac_aggregates_tflint_and_checkov_in_declared_order(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "main.tf"
    source.write_text('resource "aws_s3_bucket" "example" {}\n')
    calls: list[str] = []

    def fake_run_engine(engine, path, args, *, tool_name):
        calls.append(engine.name)
        return ToolResult(
            tool=tool_name,
            engine=engine.name,
            engine_version=None,
            status="warn",
            duration_ms=1,
            summary=engine.name,
            findings=[
                {
                    "rule": engine.name,
                    "severity": "medium",
                    "message": engine.name,
                    "path": str(path / "main.tf"),
                    "line": 1,
                    "column": None,
                }
            ],
            raw=None,
        )

    monkeypatch.setattr("rush.tools.iac.run_engine", fake_run_engine)

    result = IacTool().run(tmp_path)

    assert calls == ["tflint", "checkov"]
    assert result["engine"] == "tflint+checkov"
    assert [finding["provenance"] for finding in result["findings"]] == [
        "iac/checkov",
        "iac/tflint",
    ]
