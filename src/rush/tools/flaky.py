"""Flaky-test report analysis tool."""

from .quality import GuardedQualityTool


class FlakyTool(GuardedQualityTool):
    name = "flaky"
    default_reason = "requires historical test reports; never repeats tests by default"

    @property
    def mcp_description(self):
        return "Analyze existing flaky-test reports without rerunning tests."
