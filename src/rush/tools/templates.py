"""Check template files."""

from .content import ContentTool


class TemplatesTool(ContentTool):
    name = "templates"
    engine_name = "djlint"
    extensions = ("html", "jinja", "j2")

    @property
    def mcp_description(self) -> str:
        return "Check templates without rewriting; missing djlint returns status='skipped'."
