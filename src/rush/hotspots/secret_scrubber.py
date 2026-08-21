"""Commit message credential and secret scrubber."""

from __future__ import annotations

import re

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password|bearer|auth)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-\.]{8,})['\"]?"),
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),
    re.compile(r"sk-[a-zA-Z0-9]{48}"),
]


class SecretScrubber:
    """Masks sensitive tokens in commit messages and log streams."""

    @staticmethod
    def scrub_text(text: str) -> str:
        scrubbed = text
        for pat in SECRET_PATTERNS:
            if pat.groups >= 1:
                scrubbed = pat.sub(r"\1: [REDACTED]", scrubbed)
            else:
                scrubbed = pat.sub("[REDACTED]", scrubbed)
        return scrubbed

