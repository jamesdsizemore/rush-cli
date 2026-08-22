"""High-speed Shannon entropy and regex secret redactor."""

from __future__ import annotations

import math
import re

SECRET_PATTERNS = [
    (re.compile(r"sk-ant-[a-zA-Z0-9_\-]{20,}"), "[REDACTED_ANTHROPIC_KEY]"),
    (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "[REDACTED_OPENAI_KEY]"),
    (re.compile(r"ghp_[a-zA-Z0-9]{20,}"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"gho_[a-zA-Z0-9]{20,}"), "[REDACTED_GITHUB_OAUTH]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED_AWS_ACCESS_KEY]"),
    (
        re.compile(
            r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+ PRIVATE KEY-----"
        ),
        "[REDACTED_PRIVATE_KEY]",
    ),
]


class SecretRedactor:
    """Redacts secrets, API keys, and sensitive tokens from logs, diffs, and tool outputs."""

    @staticmethod
    def redact_text(text: str) -> str:
        if not text:
            return text

        redacted = text
        for pattern, replacement in SECRET_PATTERNS:
            redacted = pattern.sub(replacement, redacted)
        return redacted

    @staticmethod
    def calculate_entropy(data: str) -> float:
        """Calculates Shannon entropy to detect high-randomness secret strings."""
        if not data:
            return 0.0
        entropy = 0.0
        for x in set(data):
            p_x = float(data.count(x)) / len(data)
            if p_x > 0:
                entropy += -p_x * math.log2(p_x)
        return entropy
