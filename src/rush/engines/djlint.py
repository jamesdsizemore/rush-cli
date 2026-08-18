"""djLint adapter in non-mutating check mode."""

from .text_lint import TextLintEngine


class DjlintEngine(TextLintEngine):
    name = "djlint"
    binary = "djlint"
    file_extensions = ("html", "jinja", "j2")
    command_prefix = ("--check",)
