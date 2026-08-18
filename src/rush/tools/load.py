"""Load-test tool."""

from .quality import GuardedQualityTool


class LoadTool(GuardedQualityTool):
    name = "load"
    required_option = "allow_network"
    default_reason = "load testing requires an explicit scenario"

    @property
    def mcp_description(self):
        return "Run load testing only with --allow-network."
