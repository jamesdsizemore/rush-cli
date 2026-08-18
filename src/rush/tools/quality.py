"""Shared safety guards for expensive test-quality tools."""

from __future__ import annotations

from pathlib import Path

from .base import ToolFn, ToolResult
from .common import elapsed_ms, now_ms, skipped_result


class GuardedQualityTool(ToolFn):
    """Safe default for optional quality workflows before engine execution."""

    required_option: str | None = None
    default_reason: str = "requires configured project command"

    def __call__(self, path: Path) -> ToolResult:
        return self.run(path)

    def run(self, path: Path, *, config=None, **options: object) -> ToolResult:
        start = now_ms()
        if self.required_option and not options.get(self.required_option):
            result = skipped_result(
                self.name,
                None,
                f"{self.default_reason}; pass --{self.required_option.replace('_', '-')}",
            )
        else:
            result = skipped_result(self.name, None, self.default_reason)
        result["duration_ms"] = elapsed_ms(start)
        return result
