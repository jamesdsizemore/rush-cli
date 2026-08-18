"""Experimental semantic-drift detector with explicit execution guards."""

from __future__ import annotations

from pathlib import Path

from .base import ToolFn, ToolName, ToolResult
from .common import elapsed_ms, now_ms


class SemanticDriftTool(ToolFn):
    """Guard experimental browser/.NET drift detection behind explicit consent."""

    name: ToolName = "semantic-drift"

    @property
    def mcp_description(self) -> str:
        return (
            "Experimental semantic drift detection. Requires both allow_browser and "
            "allow_slow; otherwise returns a structured skipped result."
        )

    def __call__(
        self, path: Path, allow_browser: bool = False, allow_slow: bool = False
    ) -> ToolResult:
        return self.run(path, allow_browser=allow_browser, allow_slow=allow_slow)

    def run(
        self, path: Path, *, allow_browser: bool = False, allow_slow: bool = False
    ) -> ToolResult:
        start = now_ms()
        if not (allow_browser and allow_slow):
            return ToolResult(
                tool=self.name,
                engine="semantic-drift",
                engine_version=None,
                status="skipped",
                duration_ms=elapsed_ms(start),
                summary=(
                    "semantic drift is experimental; pass both --allow-browser and "
                    "--allow-slow to permit configured local analysis"
                ),
                findings=[],
                raw=None,
            )
        return ToolResult(
            tool=self.name,
            engine="semantic-drift",
            engine_version=None,
            status="skipped",
            duration_ms=elapsed_ms(start),
            summary="semantic drift needs a configured local .NET or Playwright target",
            findings=[],
            raw=None,
        )
