"""Visual regression tool."""

from .quality import GuardedQualityTool


class VisualTool(GuardedQualityTool):
    name = "visual"
    required_option = "accept"
    default_reason = "visual baselines are never updated by default"

    @property
    def mcp_description(self):
        return "Check visual baselines; updates require --accept."
