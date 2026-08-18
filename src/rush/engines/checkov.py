"""Checkov adapter available for aggregated IaC policy checks."""

from .text_lint import TextLintEngine


class CheckovEngine(TextLintEngine):
    name = "checkov"
    binary = "checkov"
    file_extensions = ("tf",)
    command_prefix = ("-d",)
