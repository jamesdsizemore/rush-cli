"""Review tool — heuristics + optional LLM call.

Architecture §10. Phase 3 stub: returns a minimal ToolResult.
Phase 4 will add the 4 heuristics and the --llm opt-in.

MCP schema design: only `path` and `use_llm` are exposed to MCP agents
(no `config` argument). The `config` is loaded internally by the CLI
dispatch helper and never crosses the MCP boundary.
"""

from __future__ import annotations

from pathlib import Path

from .base import ToolFn, ToolName, ToolResult
from .common import elapsed_ms, now_ms


class ReviewTool(ToolFn):
    name: ToolName = "review"

    @property
    def mcp_description(self) -> str:
        return (
            "Review code at <path> for size, TODO density, missing docstrings, "
            "naming, complexity. Returns {status, findings[], summary}. "
            "Default: heuristic. Pass use_llm=true to call configured model."
        )

    # MCP-facing signature. JSON-schema for agents is derived from THIS method.
    def __call__(self, path: Path, use_llm: bool = False) -> ToolResult:
        return self.run(path, use_llm=use_llm)

    # CLI / internal entry point that also accepts a config.
    def run(self, path: Path, *, use_llm: bool = False, config=None) -> ToolResult:
        # Phase 3 stub. Phase 4 will run the 4 heuristics from architecture §10.
        start = now_ms()
        return ToolResult(
            tool="review",
            engine="heuristic-v1",
            engine_version=None,
            status="ok",
            duration_ms=elapsed_ms(start),
            summary=f"review: stub (Phase 4 will implement heuristics for {path})",
            findings=[],
            raw=None,
            review_kind="llm" if use_llm else "heuristic",
            review_provider=None,
        )
