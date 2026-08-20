"""Provider registry and active provider discovery."""

from __future__ import annotations

from .anthropic import AnthropicProvider
from .base import LLMProvider
from .openai import OpenAIProvider

PROVIDERS: tuple[LLMProvider, ...] = (
    AnthropicProvider(),
    OpenAIProvider(),
)


def get_configured_provider() -> LLMProvider | None:
    """Return the first configured provider based on environment variables."""
    for provider in PROVIDERS:
        if provider.is_configured():
            return provider
    return None
