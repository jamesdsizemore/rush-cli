"""Type-check Python and JavaScript/TypeScript source with discovered engines."""

from __future__ import annotations

from pathlib import Path

from .base import ToolFn, ToolResult
from .common import elapsed_ms, now_ms, run_engine
from .routing import aggregate_results, collect_files, detect_project_languages


class TypecheckTool(ToolFn):
    name = "typecheck"

    @property
    def mcp_description(self) -> str:
        return "Type-check Python and JS/TS at <path>. Uses mypy or tsc; missing engines return status='skipped'."

    def __call__(self, path: Path) -> ToolResult:
        return self.run(path)

    def run(self, path: Path, *, config=None) -> ToolResult:
        from ..engines import ENGINES
        from ..engines.language import LANGUAGE_TYPE_ENGINES

        start = now_ms()
        language_results = [
            run_engine(LANGUAGE_TYPE_ENGINES[language], path, [], tool_name=self.name)
            for language in detect_project_languages(path)
            if language in LANGUAGE_TYPE_ENGINES
        ]
        if language_results:
            result = aggregate_results(self.name, language_results)
            result["duration_ms"] = elapsed_ms(start)
            return result
        engines = (ENGINES["mypy"], ENGINES["tsc"])
        files = collect_files(
            path, {ext for engine in engines for ext in engine.file_extensions}
        )
        if not files:
            return ToolResult(
                tool=self.name,
                engine=None,
                engine_version=None,
                status="skipped",
                duration_ms=elapsed_ms(start),
                summary=f"typecheck: no supported source files found under {path}",
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
