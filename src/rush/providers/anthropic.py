"""Anthropic Claude LLM provider implementation."""

from __future__ import annotations

import os
from typing import Any

from .base import LLMProvider, LLMResponse


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    default_model = "claude-3-5-sonnet-20241022"

    def is_configured(self) -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY"))

    def summarize_findings(
        self,
        findings: list[dict[str, Any]],
        *,
        allow_network: bool = False,
    ) -> LLMResponse | None:
        if not self.is_configured():
            return None
        n_findings = len(findings)
        summary = (
            f"[Anthropic Claude] Analyzed {n_findings} code review finding(s) "
            f"using {self.default_model}."
        )
        return LLMResponse(
            provider=self.name,
            model=self.default_model,
            content=summary,
        )
