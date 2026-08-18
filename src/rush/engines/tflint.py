"""TFLint adapter for Terraform checks."""

from .text_lint import TextLintEngine


class TflintEngine(TextLintEngine):
    name = "tflint"
    binary = "tflint"
    file_extensions = ("tf",)
