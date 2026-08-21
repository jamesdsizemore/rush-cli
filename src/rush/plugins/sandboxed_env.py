"""Environment variable sanitizer for untrusted plugin execution."""

from __future__ import annotations

import os

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


class SandboxedEnvironment:
    """Strips all high-privilege credentials and sensitive keys from the environment."""

    @staticmethod
    def get_sanitized_env() -> dict[str, str]:
        env = dict(os.environ)
        for key in SENSITIVE_ENV_KEYS:
            env.pop(key, None)
        env["PYTHONUNBUFFERED"] = "1"
        env["NO_COLOR"] = "1"
        return env
