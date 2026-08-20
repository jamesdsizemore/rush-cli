"""Checkov v3.3.9 adapter for safe local Terraform policy checks."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ..tools.base import Finding, ToolResult
from ..tools.common import error_result, resolve_binary, run_subprocess
from .base import Engine, EngineResult
from .iac_parser import StructuredIacReportError, parse_structured_iac_report


class CheckovEngine(Engine):
    """Run Checkov's local Terraform JSON mode without inherited credentials."""

    name = "checkov"
    binary = "checkov"
    file_extensions = ("tf",)

    def run(self, path: Path, args: list[str], cwd: Path | None = None) -> EngineResult:
        """Scan one local Terraform directory with downloads and remote data disabled."""
        del args, cwd
        target = path if path.is_dir() else path.parent
        proc = run_subprocess(
            [
                resolve_binary(self.binary) or self.binary,
                "--directory",
                str(target),
                "--framework",
                "terraform",
                "--output",
                "json",
                "--skip-download",
                "--download-external-modules",
                "false",
            ],
            cwd=target,
            timeout=180,
            env=_checkov_environment(),
        )
        return EngineResult(
            exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        try:
            report = json.loads(raw.get("stdout", ""))
            findings, parsing_errors = _parse_checkov_report(report, path)
        except (json.JSONDecodeError, StructuredIacReportError, TypeError, ValueError):
            return error_result(
                tool_name,
                self.name,
                "checkov returned malformed JSON",
                duration_ms=raw.get("duration_ms", 0),
                terminal_reason="malformed_output",
            )
        if parsing_errors:
            return error_result(
                tool_name,
                self.name,
                "checkov reported Terraform parsing errors",
                duration_ms=raw.get("duration_ms", 0),
                terminal_reason="engine_error",
                partial=True,
            )

        exit_code = raw.get("exit_code", 0)
        expected_exit_code = 1 if findings else 0
        if exit_code != expected_exit_code:
            return error_result(
                tool_name,
                self.name,
                "checkov exit code did not match its JSON findings",
                duration_ms=raw.get("duration_ms", 0),
                terminal_reason="nonzero_exit",
            )
        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status="warn" if findings else "ok",
            duration_ms=raw.get("duration_ms", 0),
            summary=f"checkov: {len(findings)} issue(s)",
            findings=findings,
            raw=None,
        )


def _checkov_environment() -> dict[str, str]:
    """Pass only process essentials; never inherit Checkov or platform credentials."""
    process_keys = (
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "TEMP",
        "TMP",
        "HOME",
        "USERPROFILE",
    )
    environment = {key: os.environ[key] for key in process_keys if key in os.environ}
    environment["DOWNLOAD_EXTERNAL_MODULES"] = "false"
    return environment


def _parse_checkov_report(report: Any, path: Path) -> tuple[list[Finding], list[str]]:
    reports = report if isinstance(report, list) else [report]
    if not reports or not all(isinstance(item, dict) for item in reports):
        raise StructuredIacReportError("Checkov JSON report must be an object or list")

    results: list[dict[str, Any]] = []
    parsing_errors: list[str] = []
    for item in reports:
        payload = item.get("results")
        if not isinstance(payload, dict):
            raise StructuredIacReportError("Checkov JSON report has no results object")
        failed_checks = payload.get("failed_checks")
        errors = payload.get("parsing_errors")
        if not isinstance(failed_checks, list) or not isinstance(errors, list):
            raise StructuredIacReportError("Checkov result fields must be lists")
        if not all(isinstance(error, str) for error in errors):
            raise StructuredIacReportError("Checkov parsing errors must be strings")
        parsing_errors.extend(errors)
        for check in failed_checks:
            if not isinstance(check, dict):
                raise StructuredIacReportError("Checkov failed check must be an object")
            results.append(
                {
                    "file_path": _checkov_path(check),
                    "file_line_range": check.get("file_line_range"),
                    "check_id": check.get("check_id"),
                    "severity": check.get("severity"),
                    "check_name": check.get("check_name"),
                }
            )
    findings = parse_structured_iac_report(
        json.dumps({"results": results}), _root(path)
    )
    return findings, parsing_errors


def _checkov_path(check: dict[str, Any]) -> str | None:
    source_path = check.get("file_abs_path") or check.get("file_path")
    if not isinstance(source_path, str):
        return None
    candidate = Path(source_path)
    if not candidate.is_absolute() and source_path.startswith(("/", "\\")):
        return source_path.lstrip("/\\")
    return source_path


def _root(path: Path) -> Path:
    return path if path.is_dir() else path.parent
