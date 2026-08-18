"""Fuzz-test tool."""

from .quality import GuardedQualityTool


class FuzzTool(GuardedQualityTool):
    name = "fuzz"
    required_option = "allow_fuzz"
    default_reason = "fuzzing requires a declared target"

    @property
    def mcp_description(self):
        return "Run a declared fuzz target only with --allow-fuzz."
