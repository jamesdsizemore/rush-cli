"""Check Dockerfile and Containerfile sources."""

from .content import ContentTool


class ContainerfileTool(ContentTool):
    name = "containerfile"
    engine_name = "hadolint"
    extensions = ("dockerfile", "containerfile")

    @property
    def mcp_description(self) -> str:
        return "Check container files without rewriting; missing hadolint returns status='skipped'."
