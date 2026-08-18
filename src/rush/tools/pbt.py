"""Property-based test tool."""

from .quality import GuardedQualityTool


class PbtTool(GuardedQualityTool):
    name = "pbt"
    default_reason = "requires existing property tests"

    @property
    def mcp_description(self):
        return "Run existing property tests without generating files."
