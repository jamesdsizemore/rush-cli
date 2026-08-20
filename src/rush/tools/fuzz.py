"""Contained fuzz-test report importer."""

from __future__ import annotations

import json
from pathlib import Path

from .base import ToolFn, ToolResult
from .common import elapsed_ms, error_result, now_ms, skipped_result


class FuzzTool(ToolFn):
    """Import a local fuzz report; never builds or launches a fuzzer."""

    name = "fuzz"

    @property
    def mcp_description(self) -> str:
        return "Import a contained local fuzz report; never executes a fuzzer."

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
                self.name, None, "requires an explicit local fuzz report"
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
                "fuzz-report",
                f"refusing fuzz report outside target: {report_path}",
                duration_ms=elapsed_ms(start),
            )
        if not report.is_file():
            result = skipped_result(self.name, "fuzz-report", "fuzz report is absent")
            result["duration_ms"] = elapsed_ms(start)
            return result
        try:
            payload = json.loads(report.read_text(encoding="utf-8"))
            metrics = {name: int(payload[name]) for name in ("crashes", "timeouts")}
            seed = int(payload["seed"])
            if any(value < 0 for value in metrics.values()):
                raise ValueError("negative metric")
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return error_result(
                self.name,
                "fuzz-report",
                "fuzz report is malformed or unsupported",
                duration_ms=elapsed_ms(start),
            )
        failures = metrics["crashes"] + metrics["timeouts"]
        return ToolResult(
            tool=self.name,
            engine="fuzz-report",
            engine_version=None,
            status="fail" if failures else "ok",
            duration_ms=elapsed_ms(start),
            summary=f"fuzz: {failures} crash(es) or timeout(s) in imported report",
            findings=[],
            raw=None,
            metrics=metrics,
            artifacts=[str(report_path)],
            metadata={
                "evidence_source": "imported-local-report",
                "report_format": "fuzz-json",
                "seed": seed,
            },
        )
