"""OpenAI LLM provider implementation."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .base import LLMProvider, LLMResponse


class OpenAIProvider(LLMProvider):
    name = "openai"
    default_model = "gpt-4o"

    def is_configured(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    def summarize_findings(
        self,
        findings: list[dict[str, Any]],
        *,
        allow_network: bool = False,
    ) -> LLMResponse | None:
        if not self.is_configured():
            return None

        api_key = os.environ.get("OPENAI_API_KEY", "")
        n_findings = len(findings)

        if not allow_network:
            summary = (
                f"[OpenAI GPT] Analyzed {n_findings} code review finding(s) "
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
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "rush-cli/0.2.0",
        }

        payload = {
            "model": self.default_model,
            "max_tokens": 1024,
            "messages": [
                {"role": "system", "content": "You are Rush AI Code Reviewer."},
                {"role": "user", "content": prompt},
            ],
        }

        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                choices = data.get("choices", [])
                text_content = ""
                if choices:
                    text_content = choices[0].get("message", {}).get("content", "")
                return LLMResponse(
                    provider=self.name,
                    model=data.get("model", self.default_model),
                    content=text_content
                    or f"[OpenAI GPT] Analyzed {n_findings} findings.",
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
                content=f"[OpenAI GPT Error] API request failed: {err}",
            )
