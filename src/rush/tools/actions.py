"""Check GitHub Actions workflow files."""

from .content import ContentTool


class ActionsTool(ContentTool):
    name = "actions"
    engine_name = "actionlint"
    extensions = ("yml", "yaml")

    @property
    def mcp_description(self) -> str:
        return "Check GitHub Actions workflows without rewriting; missing actionlint returns status='skipped'."
