"""Check Terraform infrastructure as code."""

from .content import ContentTool


class IacTool(ContentTool):
    name = "iac"
    engine_name = "tflint"
    extensions = ("tf",)

    @property
    def mcp_description(self) -> str:
        return "Check Terraform without rewriting; missing tflint returns status='skipped'."
