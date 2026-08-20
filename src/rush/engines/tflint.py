"""TFLint v0.64.0 adapter for safe local Terraform checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..tools.base import Finding, ToolResult
from ..tools.common import error_result, resolve_binary, run_subprocess
from .base import Engine, EngineResult
from .iac_parser import StructuredIacReportError, parse_structured_iac_report


class TflintEngine(Engine):
    """Run TFLint JSON checks without initialization or module traversal."""

    name = "tflint"
    binary = "tflint"
    file_extensions = ("tf",)

    def run(self, path: Path, args: list[str], cwd: Path | None = None) -> EngineResult:
        """Inspect the target directory; TFLint no longer accepts file arguments."""
        del args
        target = path if path.is_dir() else path.parent
        proc = run_subprocess(
            [
                resolve_binary(self.binary) or self.binary,
                "--chdir",
                str(target),
                "--format",
                "json",
                "--call-module-type",
                "none",
            ],
            cwd=cwd,
            timeout=120,
        )
        return EngineResult(
            exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        exit_code = raw.get("exit_code", 0)
        try:
            report = json.loads(raw.get("stdout", ""))
            findings = _parse_tflint_findings(report, path)
        except (json.JSONDecodeError, StructuredIacReportError, TypeError, ValueError):
            return error_result(
                tool_name,
                self.name,
                "tflint returned malformed JSON",
                duration_ms=raw.get("duration_ms", 0),
                terminal_reason="malformed_output",
            )
        if report["errors"]:
            return error_result(
                tool_name,
                self.name,
                "tflint returned structured engine errors",
                duration_ms=raw.get("duration_ms", 0),
                terminal_reason="engine_error",
            )
        if exit_code not in (0, 2):
            return error_result(
                tool_name,
                self.name,
                "tflint exited without a findings result",
                duration_ms=raw.get("duration_ms", 0),
                terminal_reason="nonzero_exit",
            )
        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status="warn" if findings else "ok",
            duration_ms=raw.get("duration_ms", 0),
            summary=f"tflint: {len(findings)} issue(s)",
            findings=findings,
            raw=None,
        )


def _parse_tflint_findings(report: Any, path: Path) -> list[Finding]:
    if not isinstance(report, dict):
        raise StructuredIacReportError("TFLint JSON report must be an object")
    issues = report.get("issues")
    errors = report.get("errors")
    if not isinstance(issues, list) or not isinstance(errors, list):
        raise StructuredIacReportError("TFLint JSON report fields must be lists")

    results: list[dict[str, Any]] = []
    columns: list[int] = []
    for issue in issues:
        if not isinstance(issue, dict):
            raise StructuredIacReportError("TFLint issue must be an object")
        rule = issue.get("rule")
        issue_range = issue.get("range")
        if not isinstance(rule, dict) or not isinstance(issue_range, dict):
            raise StructuredIacReportError("TFLint issue is missing rule or range")
        start = issue_range.get("start")
        if not isinstance(start, dict) or not isinstance(start.get("column"), int):
            raise StructuredIacReportError("TFLint issue has no valid column")
        results.append(
            {
                "file_path": issue_range.get("filename"),
                "file_line_range": [start.get("line")],
                "check_id": rule.get("name"),
                "severity": rule.get("severity"),
                "check_name": issue.get("message"),
            }
        )
        columns.append(start["column"])

    findings = parse_structured_iac_report(
        json.dumps({"results": results}), _root(path)
    )
    for finding, column in zip(findings, columns, strict=True):
        finding["column"] = column
    return findings


def _root(path: Path) -> Path:
    return path if path.is_dir() else path.parent
