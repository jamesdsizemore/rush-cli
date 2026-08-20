"""Contained Pact contract-report importer."""

from __future__ import annotations

import json
from pathlib import Path

from .base import ToolFn, ToolResult
from .common import elapsed_ms, error_result, now_ms, skipped_result


class ContractTool(ToolFn):
    """Import a local Pact report; never contacts a provider or broker."""

    name = "contract"

    @property
    def mcp_description(self) -> str:
        return "Import a contained local Pact report; never contacts a live target."

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
                self.name, None, "requires an explicit local Pact report"
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
                "pact-report",
                f"refusing contract report outside target: {report_path}",
                duration_ms=elapsed_ms(start),
            )
        if not report.is_file():
            result = skipped_result(
                self.name, "pact-report", "contract report is absent"
            )
            result["duration_ms"] = elapsed_ms(start)
            return result
        try:
            payload = json.loads(report.read_text(encoding="utf-8"))
            summary = payload["summary"]
            errors = int(summary["errors"])
            warnings = int(summary.get("warnings", 0))
            if errors < 0 or warnings < 0:
                raise ValueError("negative counts")
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return error_result(
                self.name,
                "pact-report",
                "contract report is malformed or unsupported",
                duration_ms=elapsed_ms(start),
            )

        status = "fail" if errors else "warn" if warnings else "ok"
        return ToolResult(
            tool=self.name,
            engine="pact-report",
            engine_version=None,
            status=status,
            duration_ms=elapsed_ms(start),
            summary=f"contract: {errors} error(s), {warnings} warning(s) in imported report",
            findings=[],
            raw=None,
            metrics={"errors": errors, "warnings": warnings},
            artifacts=[str(report_path)],
            metadata={
                "evidence_source": "imported-local-report",
                "report_format": "pact",
            },
        )
