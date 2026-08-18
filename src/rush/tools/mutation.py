"""Mutation testing tool."""

from .quality import GuardedQualityTool


class MutationTool(GuardedQualityTool):
    name = "mutation"
    required_option = "allow_slow"
    default_reason = "mutation testing is disabled by default"

    @property
    def mcp_description(self):
        return "Run configured mutation tests only with --allow-slow."
