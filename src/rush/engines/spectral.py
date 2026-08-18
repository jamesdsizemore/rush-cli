"""Spectral YAML/OpenAPI adapter."""

from .text_lint import TextLintEngine


class SpectralEngine(TextLintEngine):
    name = "spectral"
    binary = "spectral"
    file_extensions = ("yml", "yaml")
    command_prefix = ("lint",)
