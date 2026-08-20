"""Contained importer for a user-supplied CodeQL SARIF report."""

from __future__ import annotations

import json
from pathlib import Path

from ..engines.iac_parser import StructuredIacReportError, parse_structured_iac_report
from .base import ToolFn, ToolResult
from .common import elapsed_ms, error_result, now_ms, skipped_result


class CodeqlTool(ToolFn):
    """Import a contained CodeQL SARIF report; never builds or runs CodeQL."""

    name = "codeql"

    @property
    def mcp_description(self) -> str:
        return "Import a contained local CodeQL SARIF report; never runs CodeQL."

    def __call__(self, path: Path) -> ToolResult:
        return self.run(path)

    def run(
        self, path: Path, *, report_path: Path | None = None, config=None
    ) -> ToolResult:
        start = now_ms()
        if report_path is None and path.is_file():
            report_path = path
        if report_path is None:
            result = skipped_result(
                self.name, None, "requires an explicit local CodeQL SARIF report"
            )
            result["duration_ms"] = elapsed_ms(start)
            return result

        root = path.resolve() if path.is_dir() else path.parent.resolve()
        report = report_path.resolve()
        try:
            report.relative_to(root)
        except ValueError:
            return error_result(
                self.name,
                "codeql-sarif",
                f"refusing CodeQL report outside target: {report_path}",
                duration_ms=elapsed_ms(start),
            )
        if not report.is_file():
            result = skipped_result(
                self.name, "codeql-sarif", "CodeQL report is absent"
            )
            result["duration_ms"] = elapsed_ms(start)
            return result

        try:
            report_text = report.read_text(encoding="utf-8")
            if not _is_codeql_sarif(report_text):
                raise StructuredIacReportError("report is not produced by CodeQL")
            findings = parse_structured_iac_report(report_text, root)
        except (OSError, json.JSONDecodeError, StructuredIacReportError):
            return error_result(
                self.name,
                "codeql-sarif",
                "CodeQL SARIF report is malformed or unsupported",
                duration_ms=elapsed_ms(start),
            )

        if any(item["severity"] == "error" for item in findings):
            status = "fail"
        elif any(item["severity"] == "warn" for item in findings):
            status = "warn"
        else:
            status = "ok"
        return ToolResult(
            tool=self.name,
            engine="codeql-sarif",
            engine_version=None,
            status=status,
            duration_ms=elapsed_ms(start),
            summary=f"CodeQL: {len(findings)} finding(s) from imported SARIF report",
            findings=findings,
            raw=None,
            metrics={"findings": len(findings)},
            artifacts=[str(report_path)],
            metadata={
                "evidence_source": "imported-local-report",
                "report_format": "sarif-2.1.0",
            },
        )


def _is_codeql_sarif(report_text: str) -> bool:
    """Accept only SARIF 2.1.0 reports whose runs identify CodeQL."""

    report = json.loads(report_text)
    if not isinstance(report, dict):
        return False
    runs = report.get("runs")
    if report.get("version") != "2.1.0" or not isinstance(runs, list) or not runs:
        return False
    for run in runs:
        driver = run.get("tool", {}).get("driver", {}) if isinstance(run, dict) else {}
        name = driver.get("name") if isinstance(driver, dict) else None
        if not isinstance(name, str) or not name.lower().startswith("codeql"):
            return False
    return True
