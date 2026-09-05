"""Environment variable sanitizer for untrusted plugin execution."""

from __future__ import annotations

import os
from collections.abc import Mapping

from rush.safety.redactor import SECRET_PATTERNS

SENSITIVE_ENV_KEYS = {
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "DEEPSEEK_API_KEY",
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "DATABASE_URL",
    "SLACK_BOT_TOKEN",
    "STRIPE_SECRET_KEY",
    "HEROKU_API_KEY",
    "SSH_AUTH_SOCK",
}

SENSITIVE_KEY_SUBSTRINGS = (
    "KEY",
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "PASSWD",
    "AUTH",
    "CREDENTIAL",
    "PRIVATE",
    "BEARER",
)


class SandboxedEnvironment:
    """Strips all high-privilege credentials and sensitive keys from the environment."""

    @staticmethod
    def is_sensitive_key(key: str) -> bool:
        """Check if an environment variable key indicates sensitive credentials."""
        upper = key.upper()
        if key in SENSITIVE_ENV_KEYS or upper in SENSITIVE_ENV_KEYS:
            return True
        return any(sub in upper for sub in SENSITIVE_KEY_SUBSTRINGS)

    @staticmethod
    def contains_secret_value(value: str) -> bool:
        """Check if an environment variable value matches secret or credential patterns."""
        if not value or not isinstance(value, str):
            return False
        return any(pattern.search(value) is not None for pattern, _ in SECRET_PATTERNS)

    @classmethod
    def get_sanitized_env(
        cls, base_env: Mapping[str, str] | None = None
    ) -> dict[str, str]:
        """Scrub all API keys, secrets, and credentials, preserving only safe standard system environment variables."""
        source = dict(os.environ if base_env is None else base_env)
        sanitized: dict[str, str] = {}

        for k, v in source.items():
            if cls.is_sensitive_key(k):
                continue
            if cls.contains_secret_value(v):
                continue
            sanitized[k] = v

        sanitized["PYTHONUNBUFFERED"] = "1"
        sanitized["NO_COLOR"] = "1"
        return sanitized
