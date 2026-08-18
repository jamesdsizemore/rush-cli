"""Safe local CI workflow configuration inspection."""

from __future__ import annotations

from pathlib import Path

from .base import ToolFn, ToolResult
from .common import elapsed_ms, now_ms, skipped_result


class CiTool(ToolFn):
    name = "ci"

    @property
    def mcp_description(self) -> str:
        return "Inspect local CI workflow configuration without accessing credentials or remote status."

    def __call__(self, path: Path) -> ToolResult:
        return self.run(path)

    def run(self, path: Path, *, config=None) -> ToolResult:
        start = now_ms()
        workflows = path / ".github" / "workflows"
        if not workflows.is_dir():
            result = skipped_result(
                self.name, None, "no local GitHub Actions workflow directory found"
            )
        else:
            files = sorted(p for p in workflows.glob("*.y*ml") if p.is_file())
            result = ToolResult(
                tool=self.name,
                engine="builtin",
                engine_version=None,
                status="ok",
                duration_ms=0,
                summary=f"ci: found {len(files)} workflow file(s)",
                findings=[],
                raw=None,
                artifacts=[],
            )
        result["duration_ms"] = elapsed_ms(start)
        return result
