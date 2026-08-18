"""Secret scanning through externally discovered gitleaks."""

from __future__ import annotations

from pathlib import Path

from .base import ToolFn, ToolResult
from .common import elapsed_ms, now_ms, run_engine


class SecretsTool(ToolFn):
    name = "secrets"

    @property
    def mcp_description(self) -> str:
        return "Scan for secrets without exposing values; missing gitleaks returns status='skipped'."

    def __call__(self, path: Path) -> ToolResult:
        return self.run(path)

    def run(self, path: Path, *, config=None) -> ToolResult:
        from ..engines import ENGINES

        start = now_ms()
        result = run_engine(ENGINES["gitleaks"], path, [], tool_name=self.name)
        result["duration_ms"] = elapsed_ms(start)
        return result
