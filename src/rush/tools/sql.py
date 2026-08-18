"""Check SQL files."""

from .content import ContentTool


class SqlTool(ContentTool):
    name = "sql"
    engine_name = "sqlfluff"
    extensions = ("sql",)

    @property
    def mcp_description(self) -> str:
        return "Check SQL without rewriting; missing sqlfluff returns status='skipped'."
