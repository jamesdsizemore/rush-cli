"""Format tool — engine dispatch per file extension.

Architecture §4.3. Phase 3 stub. Phase 4 will wire ruff format (Python)
and prettier --write (JS/TS + others).
"""

from __future__ import annotations

from pathlib import Path

from .base import ToolFn, ToolName, ToolResult
from .common import elapsed_ms, now_ms


class FormatTool(ToolFn):
    name: ToolName = "format"

    @property
    def mcp_description(self) -> str:
        return (
            "Format Python/JS/TS files at <path>. Returns {status, findings[], summary}. "
            "Engines: ruff format (Python), prettier (JS/TS). Pass check=true to only verify."
        )

    def __call__(self, path: Path, check: bool = False) -> ToolResult:
        return self.run(path, check=check)

    def run(self, path: Path, *, check: bool = False, config=None) -> ToolResult:
        # Phase 3 stub. Phase 4 will dispatch + use `check` arg.
        start = now_ms()
        return ToolResult(
            tool="format",
            engine=None,
            engine_version=None,
            status="skipped",
            duration_ms=elapsed_ms(start),
            summary=f"format: stub (Phase 4 will dispatch ruff format/prettier for {path}; check={check})",
            findings=[],
            raw=None,
        )
