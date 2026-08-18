"""Coverage report tool."""

from .quality import GuardedQualityTool


class CoverageTool(GuardedQualityTool):
    name = "coverage"
    default_reason = "requires a configured coverage command"

    @property
    def mcp_description(self):
        return "Collect configured coverage reports without rewriting source files."
