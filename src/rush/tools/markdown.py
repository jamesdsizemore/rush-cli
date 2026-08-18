"""Check Markdown files with externally discovered markdownlint-cli2."""

from __future__ import annotations

from pathlib import Path

from .base import ToolFn, ToolResult
from .common import elapsed_ms, now_ms, run_engine
from .routing import collect_files


class MarkdownTool(ToolFn):
    name = "markdown"

    @property
    def mcp_description(self) -> str:
        return "Check Markdown at <path> without rewriting files; missing markdownlint-cli2 returns status='skipped'."

    def __call__(self, path: Path) -> ToolResult:
        return self.run(path)

    def run(self, path: Path, *, config=None) -> ToolResult:
        from ..engines import ENGINES

        start = now_ms()
        files = collect_files(path, {"md", "mdx"})
        if not files:
            return ToolResult(
                tool=self.name,
                engine=None,
                engine_version=None,
                status="skipped",
                duration_ms=elapsed_ms(start),
                summary=f"markdown: no supported source files found under {path}",
                findings=[],
                raw=None,
            )
        result = run_engine(
            ENGINES["markdownlint-cli2"],
            path,
            [str(file) for file in files],
            tool_name=self.name,
        )
        result["duration_ms"] = elapsed_ms(start)
        return result
