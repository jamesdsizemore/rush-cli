"""Contained mutation-test report importer."""

from __future__ import annotations

import json
from pathlib import Path

from .base import ToolFn, ToolResult
from .common import elapsed_ms, error_result, now_ms, skipped_result


class MutationTool(ToolFn):
    """Import a local mutation report; never runs a mutation engine."""

    name = "mutation"

    @property
    def mcp_description(self) -> str:
        return "Import a contained local mutation report; never runs mutation tests."

    def __call__(self, path: Path) -> ToolResult:
        return self.run(path)

    def run(
        self,
        path: Path,
        *,
        report_path: Path | None = None,
        config=None,
        **options: object,
    ) -> ToolResult:
        start = now_ms()
        if report_path is None and path.is_file():
            report_path = path
        if report_path is None:
            result = skipped_result(
                self.name, None, "requires an explicit local mutation report"
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
                "mutation-report",
                f"refusing mutation report outside target: {report_path}",
                duration_ms=elapsed_ms(start),
            )
        if not report.is_file():
            result = skipped_result(
                self.name, "mutation-report", "mutation report is absent"
            )
            result["duration_ms"] = elapsed_ms(start)
            return result
        try:
            payload = json.loads(report.read_text(encoding="utf-8"))
            metrics = {
                name: int(payload[name]) for name in ("killed", "survived", "timeout")
            }
            if any(value < 0 for value in metrics.values()):
                raise ValueError("negative metric")
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return error_result(
                self.name,
                "mutation-report",
                "mutation report is malformed or unsupported",
                duration_ms=elapsed_ms(start),
            )
        escaped = metrics["survived"] + metrics["timeout"]
        return ToolResult(
            tool=self.name,
            engine="mutation-report",
            engine_version=None,
            status="fail" if escaped else "ok",
            duration_ms=elapsed_ms(start),
            summary=f"mutation: {escaped} mutant(s) survived or timed out",
            findings=[],
            raw=None,
            metrics=metrics,
            artifacts=[str(report_path)],
            metadata={
                "evidence_source": "imported-local-report",
                "report_format": "mutation-json",
            },
        )
