"""actionlint adapter."""

from .text_lint import TextLintEngine


class ActionlintEngine(TextLintEngine):
    name = "actionlint"
    binary = "actionlint"
    file_extensions = ("yml", "yaml")
