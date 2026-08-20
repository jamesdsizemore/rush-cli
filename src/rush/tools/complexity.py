"""Measure Python and JavaScript/TypeScript complexity with discovered engines."""

from __future__ import annotations

from pathlib import Path

from .base import ToolFn, ToolResult
from .common import elapsed_ms, now_ms, run_engine
from .routing import aggregate_results, collect_files


class ComplexityTool(ToolFn):
    name = "complexity"

    @property
    def mcp_description(self) -> str:
        return "Measure Python and JS/TS complexity at <path>. Uses radon or jscpd; missing engines return status='skipped'."

    def __call__(self, path: Path) -> ToolResult:
        return self.run(path)

    def run(self, path: Path, *, config=None) -> ToolResult:
        from ..engines import ENGINES

        start = now_ms()
        engines = (
            ENGINES["radon"],
            ENGINES["jscpd"],
            ENGINES["tach"],
            ENGINES["clines"],
            ENGINES["sentrux"],
        )
        files = collect_files(
            path,
            {
                ext
                for engine in engines
                for ext in getattr(engine, "file_extensions", ())
                if ext
            }
            or {"py", "js", "ts", "rs", "go"},
        )
        if not files:
            return ToolResult(
                tool=self.name,
                engine=None,
                engine_version=None,
                status="skipped",
                duration_ms=elapsed_ms(start),
                summary=f"complexity: no supported source files found under {path}",
                findings=[],
                raw=None,
            )
        results = []
        for engine in engines:
            targets = [
                file
                for file in files
                if file.suffix.lower().lstrip(".") in engine.file_extensions
            ]
            if targets:
                results.append(
                    run_engine(
                        engine,
                        path,
                        [str(target) for target in targets],
                        tool_name=self.name,
                    )
                )
        result = aggregate_results(self.name, results)
        result["duration_ms"] = elapsed_ms(start)
        return result
