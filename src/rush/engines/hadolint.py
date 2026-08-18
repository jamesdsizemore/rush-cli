"""Hadolint adapter for Dockerfile checks."""

from .text_lint import TextLintEngine


class HadolintEngine(TextLintEngine):
    name = "hadolint"
    binary = "hadolint"
    file_extensions = ("dockerfile", "containerfile")
