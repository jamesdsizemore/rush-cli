"""Contained property-test report importer."""

from __future__ import annotations

import json
from pathlib import Path

from .base import ToolFn, ToolResult
from .common import elapsed_ms, error_result, now_ms, skipped_result


class PbtTool(ToolFn):
    """Import a local seeded property-test report; never executes property tests."""

    name = "pbt"

    @property
    def mcp_description(self) -> str:
        return "Import a contained local property-test report; never executes tests."

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
                self.name, None, "requires an explicit local property-test report"
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
                "property-report",
                f"refusing property report outside target: {report_path}",
                duration_ms=elapsed_ms(start),
            )
        if not report.is_file():
            result = skipped_result(
                self.name, "property-report", "property-test report is absent"
            )
            result["duration_ms"] = elapsed_ms(start)
            return result
        try:
            payload = json.loads(report.read_text(encoding="utf-8"))
            seed = int(payload["seed"])
            failures = payload.get("failures", [])
            if not isinstance(failures, list):
                raise TypeError("failures must be a list")
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return error_result(
                self.name,
                "property-report",
                "property-test report is malformed or unsupported",
                duration_ms=elapsed_ms(start),
            )

        findings = [
            {
                "path": str(report_path),
                "line": 0,
                "rule": "property-failure",
                "severity": "error",
                "message": f"{item.get('property', 'property')}: {item.get('message', 'failed')}"
                if isinstance(item, dict)
                else "property test failed",
            }
            for item in failures
        ]
        return ToolResult(
            tool=self.name,
            engine="property-report",
            engine_version=None,
            status="fail" if findings else "ok",
            duration_ms=elapsed_ms(start),
            summary=f"pbt: {len(findings)} failure(s) in imported seeded report",
            findings=findings,
            raw=None,
            artifacts=[str(report_path)],
            metadata={
                "evidence_source": "imported-local-report",
                "report_format": "property-json",
                "seed": seed,
            },
        )
