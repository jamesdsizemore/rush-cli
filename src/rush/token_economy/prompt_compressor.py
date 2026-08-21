"""Whitespace and comment noise reducer for prompt context."""

from __future__ import annotations

import re


class PromptCompressor:
    """Reduces repetitive indentation, trailing spaces, and redundant blank lines in prompt context."""

    @staticmethod
    def clean_text(text: str) -> str:
        if not text:
            return ""
        collapsed = re.sub(r"\n{3,}", "\n\n", text)
        lines = [line.rstrip() for line in collapsed.splitlines()]
        return "\n".join(lines)
