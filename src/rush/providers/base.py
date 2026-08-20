"""Pluggable LLM provider interface and data models for AI-augmented code review."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal

ProviderName = Literal["anthropic", "openai", "stub"]


@dataclass(frozen=True)
class LLMResponse:
    provider: ProviderName
    model: str
    content: str
    raw: dict[str, Any] | None = None


class LLMProvider(ABC):
    """Abstract base class for LLM review providers."""

    name: ProviderName
    default_model: str

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if environment credentials exist."""
        ...

    @abstractmethod
    def summarize_findings(
        self,
        findings: list[dict[str, Any]],
        *,
        allow_network: bool = False,
    ) -> LLMResponse | None:
        """Summarize findings with explicit network permission boundary."""
        ...
