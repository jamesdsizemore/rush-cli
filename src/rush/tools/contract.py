"""Contract-test tool."""

from .quality import GuardedQualityTool


class ContractTool(GuardedQualityTool):
    name = "contract"
    default_reason = "requires an existing pact or contract-test configuration"

    @property
    def mcp_description(self):
        return "Run configured contract tests without provider deployment."
