"""Contained snapshot-comparison report importer."""

from __future__ import annotations

import json
from pathlib import Path

from .base import ToolFn, ToolResult
from .common import elapsed_ms, error_result, now_ms, skipped_result


class SnapshotTool(ToolFn):
    """Import a local snapshot comparison; never writes a baseline."""

    name = "snapshot"

    @property
    def mcp_description(self) -> str:
        return "Import a local snapshot comparison; never creates or updates baselines."

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
                self.name,
                None,
                "requires an explicit local snapshot comparison report; never accepts a baseline",
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
                "snapshot-report",
                f"refusing snapshot report outside target: {report_path}",
                duration_ms=elapsed_ms(start),
            )
        if not report.is_file():
            result = skipped_result(
                self.name, "snapshot-report", "snapshot report is absent"
            )
            result["duration_ms"] = elapsed_ms(start)
            return result
        try:
            payload = json.loads(report.read_text(encoding="utf-8"))
            metrics = {name: int(payload[name]) for name in ("matched", "mismatched")}
            if any(value < 0 for value in metrics.values()):
                raise ValueError("negative metric")
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return error_result(
                self.name,
                "snapshot-report",
                "snapshot report is malformed or unsupported",
                duration_ms=elapsed_ms(start),
            )
        return ToolResult(
            tool=self.name,
            engine="snapshot-report",
            engine_version=None,
            status="fail" if metrics["mismatched"] else "ok",
            duration_ms=elapsed_ms(start),
            summary=f"snapshot: {metrics['mismatched']} mismatch(es) in imported comparison",
            findings=[],
            raw=None,
            metrics=metrics,
            artifacts=[str(report_path)],
            metadata={
                "evidence_source": "imported-local-report",
                "report_format": "snapshot-json",
                "baseline_mutated": False,
            },
        )
