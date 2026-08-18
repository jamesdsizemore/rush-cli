"""Release planning with an explicit no-publication default."""

from __future__ import annotations

from pathlib import Path

from .base import ToolFn, ToolResult
from .common import elapsed_ms, now_ms, skipped_result


class ReleaseTool(ToolFn):
    name = "release"

    @property
    def mcp_description(self) -> str:
        return (
            "Create a dry-run release plan; publishing requires explicit confirmation."
        )

    def __call__(self, path: Path) -> ToolResult:
        return self.run(path)

    def run(
        self, path: Path, *, publish: bool = False, confirm: bool = False, config=None
    ) -> ToolResult:
        start = now_ms()
        if publish and not confirm:
            result = skipped_result(
                self.name, None, "publication requires explicit confirmation"
            )
        elif publish:
            result = skipped_result(
                self.name,
                None,
                "publication execution is intentionally unavailable in this local tool",
            )
        else:
            result = ToolResult(
                tool=self.name,
                engine="builtin",
                engine_version=None,
                status="ok",
                duration_ms=0,
                summary="release dry-run plan; no tag, release, or upload was created",
                findings=[],
                raw=None,
                artifacts=[],
                metadata={"dry_run": True, "publish": False},
            )
        result["duration_ms"] = elapsed_ms(start)
        return result
