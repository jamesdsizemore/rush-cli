"""End-to-end test tool."""

from .quality import GuardedQualityTool


class E2eTool(GuardedQualityTool):
    name = "e2e"
    required_option = "allow_browser"
    default_reason = "browser execution is disabled by default"

    @property
    def mcp_description(self):
        return "Run configured E2E tests only with --allow-browser."
