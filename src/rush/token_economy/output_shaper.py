"""Terse persona output shaper eliminating conversational fluff and filler words."""

import re
from typing import ClassVar


class OutputShaper:
    """Enforces concise, high-signal bulleted outputs for FastMCP and CLI when terse style is active."""

    FILLER_PATTERNS: ClassVar[list[str]] = [
        r"(?i)^sure[,!]?\s*(i can help with that[.]?\s*)?",
        r"(?i)^certainly[,!]?\s*",
        r"(?i)^as an ai[a-z ]*[,!]?\s*",
        r"(?i)^i would be happy to[a-z ]*[,!]?\s*",
        r"(?i)^here is the requested (information|data|output):?\s*",
        r"(?i)^i have completed the requested task[.]?\s*",
    ]

    def shape_response(self, text: str, style: str = "terse") -> str:
        if style != "terse":
            return text

        cleaned = text.strip()
        for pat in self.FILLER_PATTERNS:
            cleaned = re.sub(pat, "", cleaned).strip()

        return cleaned
