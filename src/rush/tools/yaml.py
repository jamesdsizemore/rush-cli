"""Check YAML and OpenAPI files."""

from .content import ContentTool


class YamlTool(ContentTool):
    name = "yaml"
    engine_name = "spectral"
    extensions = ("yml", "yaml")

    @property
    def mcp_description(self) -> str:
        return (
            "Check YAML without rewriting; missing spectral returns status='skipped'."
        )
