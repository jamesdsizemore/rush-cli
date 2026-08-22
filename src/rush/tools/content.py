"""Shared non-mutating content/infrastructure tool routing."""

from __future__ import annotations

from pathlib import Path

from .base import ToolFn, ToolResult
from .common import elapsed_ms, now_ms, run_engine
from .routing import collect_files


class ContentTool(ToolFn):
    """Route one content family to one discovered external checker."""

    engine_name: str
    extensions: tuple[str, ...]

    def __call__(self, path: Path) -> ToolResult:
        return self.run(path)

    def run(self, path: Path, *, config=None) -> ToolResult:
        from ..engines import ENGINES

        start = now_ms()
        files = collect_files(path, self.extensions)
        if not files:
            return ToolResult(
                tool=self.name,
                engine=None,
                engine_version=None,
                status="skipped",
                duration_ms=elapsed_ms(start),
                summary=f"{self.name}: no supported source files found under {path}",
                findings=[],
                raw=None,
            )
        result = run_engine(
            ENGINES[self.engine_name],
            path,
            [str(file.resolve()) for file in files],
            tool_name=self.name,
        )

        result["duration_ms"] = elapsed_ms(start)
        return result
