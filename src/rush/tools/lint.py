"""Lint tool — engine dispatch per file extension.

Architecture §4.3. Phase 3 stub. Phase 4 will wire ruff (Python) and eslint
(JS/TS) through tools/common.py:run_engine.
"""

from __future__ import annotations

from pathlib import Path

from .base import ToolFn, ToolName, ToolResult
from .common import elapsed_ms, now_ms


class LintTool(ToolFn):
    name: ToolName = "lint"

    @property
    def mcp_description(self) -> str:
        return (
            "Lint Python/JS/TS files at <path>. Returns {status, findings[], summary}. "
            "Engines: ruff (Python), eslint (JS/TS). status='skipped' means engine not on PATH."
        )

    def __call__(self, path: Path, engine_args: list[str] | None = None) -> ToolResult:
        return self.run(path, engine_args=engine_args)

    def run(self, path: Path, *, engine_args: list[str] | None = None, config=None) -> ToolResult:
        # Phase 3 stub. Phase 4 will dispatch per file extension.
        start = now_ms()
        return ToolResult(
            tool="lint",
            engine=None,
            engine_version=None,
            status="skipped",
            duration_ms=elapsed_ms(start),
            summary=f"lint: stub (Phase 4 will dispatch ruff/eslint for {path})",
            findings=[],
            raw=None,
        )
