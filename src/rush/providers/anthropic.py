"""Anthropic Claude LLM provider implementation."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
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

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        n_findings = len(findings)

        if not allow_network:
            summary = (
                f"[Anthropic Claude] Analyzed {n_findings} code review finding(s) "
                f"using {self.default_model}."
            )
            return LLMResponse(
                provider=self.name,
                model=self.default_model,
                content=summary,
            )

        prompt = (
            f"You are Rush AI Code Reviewer. Summarize and suggest remediations for the following {n_findings} findings:\n\n"
            + json.dumps(findings[:50], indent=2)
        )

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            "user-agent": "rush-cli/0.2.0",
        }

        payload = {
            "model": self.default_model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
        }

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text_content = ""
                for block in data.get("content", []):
                    if block.get("type") == "text":
                        text_content += block.get("text", "")
                return LLMResponse(
                    provider=self.name,
                    model=data.get("model", self.default_model),
                    content=text_content
                    or f"[Anthropic Claude] Analyzed {n_findings} findings.",
                )
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            OSError,
            json.JSONDecodeError,
            KeyError,
            ValueError,
        ) as err:
            return LLMResponse(
                provider=self.name,
                model=self.default_model,
                content=f"[Anthropic Claude Error] API request failed: {err}",
            )
