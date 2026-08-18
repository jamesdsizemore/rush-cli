"""SQLFluff adapter in report-only lint mode."""

from .text_lint import TextLintEngine


class SqlfluffEngine(TextLintEngine):
    name = "sqlfluff"
    binary = "sqlfluff"
    file_extensions = ("sql",)
    command_prefix = ("lint",)
