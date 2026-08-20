"""Contained JUnit flaky-test report importer."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from xml.etree import ElementTree

from .base import ToolFn, ToolResult
from .common import elapsed_ms, error_result, now_ms, skipped_result


class FlakyTool(ToolFn):
    """Import a local JUnit report; never repeats tests or alters baselines."""

    name = "flaky"

    @property
    def mcp_description(self) -> str:
        return "Import a contained JUnit report for duplicate-case flakiness evidence."

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
                self.name, None, "requires an explicit local JUnit report"
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
                "junit-report",
                f"refusing flaky report outside target: {report_path}",
                duration_ms=elapsed_ms(start),
            )
        if not report.is_file():
            result = skipped_result(self.name, "junit-report", "flaky report is absent")
            result["duration_ms"] = elapsed_ms(start)
            return result
        try:
            testcases = list(ElementTree.parse(report).iter("testcase"))
        except ElementTree.ParseError:
            return error_result(
                self.name,
                "junit-report",
                "flaky report is malformed XML",
                duration_ms=elapsed_ms(start),
            )

        identities = [
            f"{case.attrib.get('classname', '')}::{case.attrib.get('name', '')}"
            for case in testcases
        ]
        duplicates = sorted(
            name for name, count in Counter(identities).items() if count > 1
        )
        findings = [
            {
                "path": str(report_path),
                "line": 0,
                "rule": "flaky-duplicate-case",
                "severity": "warning",
                "message": f"JUnit report repeats test case {identity}",
            }
            for identity in duplicates
        ]
        return ToolResult(
            tool=self.name,
            engine="junit-report",
            engine_version=None,
            status="warn" if findings else "ok",
            duration_ms=elapsed_ms(start),
            summary=(
                f"flaky: {len(findings)} repeated test case(s) in imported report"
                if findings
                else "flaky: no repeated test cases in imported report"
            ),
            findings=findings,
            raw=None,
            artifacts=[str(report_path)],
            metadata={
                "evidence_source": "imported-local-report",
                "report_format": "junit",
            },
        )
