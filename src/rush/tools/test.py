"""Test tool — engine dispatch per project type.

Architecture §4.3. Phase 3 stub. Phase 4 will detect pyproject.toml vs
package.json and dispatch to pytest / vitest / npm test.
"""

from __future__ import annotations

from pathlib import Path

from .base import ToolFn, ToolName, ToolResult
from .common import elapsed_ms, now_ms


class TestTool(ToolFn):
    name: ToolName = "test"

    @property
    def mcp_description(self) -> str:
        return (
            "Run tests for project at <path>. Returns {status, findings[], summary}. "
            "Engines: pytest (Python), vitest/npm (JS/TS). status='skipped' means engine not on PATH."
        )

    def __call__(self, path: Path) -> ToolResult:
        return self.run(path)

    def run(self, path: Path, *, config=None) -> ToolResult:
        # Phase 3 stub. Phase 4 will detect project type and dispatch.
        start = now_ms()
        return ToolResult(
            tool="test",
            engine=None,
            engine_version=None,
            status="skipped",
            duration_ms=elapsed_ms(start),
            summary=f"test: stub (Phase 4 will detect project + run pytest/vitest for {path})",
            findings=[],
            raw=None,
        )
