"""Contained importer for a user-supplied coverage.py JSON report."""

from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree

from .base import ToolFn, ToolResult
from .common import elapsed_ms, error_result, now_ms, skipped_result


class CoverageTool(ToolFn):
    """Import a local coverage report; never runs tests or an external engine."""

    name = "coverage"

    @property
    def mcp_description(self) -> str:
        return "Import a contained local coverage.py JSON report; never runs tests."

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
                self.name, None, "requires an explicit local coverage JSON report"
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
                "coverage-report",
                f"refusing coverage report outside target: {report_path}",
                duration_ms=elapsed_ms(start),
            )
        if not report.is_file():
            result = skipped_result(
                self.name, "coverage-report", "coverage report is absent"
            )
            result["duration_ms"] = elapsed_ms(start)
            return result
        try:
            report_text = report.read_text(encoding="utf-8")
            percent, report_format = _coverage_percent(report, report_text)
        except (
            ElementTree.ParseError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ):
            return error_result(
                self.name,
                "coverage-report",
                "coverage report is malformed or unsupported",
                duration_ms=elapsed_ms(start),
            )

        return ToolResult(
            tool=self.name,
            engine="coverage-report",
            engine_version=None,
            status="ok" if percent >= 100 else "warn",
            duration_ms=elapsed_ms(start),
            summary=f"coverage: {percent:g}% line coverage from imported report",
            findings=[],
            raw=None,
            metrics={"line_percent": percent},
            artifacts=[str(report_path)],
            metadata={
                "evidence_source": "imported-local-report",
                "report_format": report_format,
            },
        )


def _coverage_percent(report: Path, report_text: str) -> tuple[float, str]:
    if report.suffix.lower() in {".lcov", ".info"}:
        hits = [
            int(line.rsplit(",", 1)[1])
            for line in report_text.splitlines()
            if line.startswith("DA:")
        ]
        if not hits:
            raise ValueError("LCOV report has no line records")
        return 100 * sum(hit > 0 for hit in hits) / len(hits), "lcov"
    if report.suffix.lower() == ".xml":
        root = ElementTree.fromstring(report_text)
        if root.tag != "coverage":
            raise ValueError("unsupported XML coverage report")
        return 100 * float(root.attrib["line-rate"]), "cobertura"

    payload = json.loads(report_text)
    return float(payload["totals"]["percent_covered"]), "coverage.py-json"
