"""OpenAI LLM provider implementation."""

from __future__ import annotations

import json
import os
import urllib.error
from typing import Any

from .. import __version__
from .base import (
    LLMProvider,
    ProviderEgressError,
    ProviderOutcome,
    ProviderResult,
    safe_provider_post,
)


class OpenAIProvider(LLMProvider):
    name = "openai"
    default_model = "gpt-4o"
    endpoint_url = "https://api.openai.com/v1/chat/completions"
    effective_origin = "https://api.openai.com"

    def is_configured(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    def summarize_findings(
        self,
        findings: list[dict[str, Any]],
        *,
        allow_network: bool = False,
    ) -> ProviderResult | None:
        if not self.is_configured():
            return None

        api_key = os.environ.get("OPENAI_API_KEY", "")
        n_findings = len(findings)

        if not allow_network:
            summary = (
                f"[OpenAI GPT] Analyzed {n_findings} code review finding(s) "
                f"using {self.default_model}."
            )
            return ProviderResult(
                outcome=ProviderOutcome.SKIPPED.value,
                content=summary,
                model=self.default_model,
                provider=self.name,
                effective_origin=self.effective_origin,
            )

        prompt = (
            f"You are Rush AI Code Reviewer. Summarize and suggest remediations for the following {n_findings} findings:\n\n"
            + json.dumps(findings[:50], indent=2)
        )

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": f"rush-cli/{__version__}",
        }

        payload = {
            "model": self.default_model,
            "max_tokens": 1024,
            "messages": [
                {"role": "system", "content": "You are Rush AI Code Reviewer."},
                {"role": "user", "content": prompt},
            ],
        }

        try:
            _status, body = safe_provider_post(
                self.endpoint_url,
                headers=headers,
                data=json.dumps(payload),
            )
            data = json.loads(body.decode("utf-8"))
            choices = data.get("choices", [])
            text_content = ""
            finish_reason = ""
            if choices:
                choice = choices[0]
                text_content = choice.get("message", {}).get("content", "") or ""
                finish_reason = choice.get("finish_reason", "")

            if not text_content.strip():
                return ProviderResult(
                    outcome=ProviderOutcome.ERROR.value,
                    content="",
                    model=data.get("model", self.default_model),
                    finish_reason=finish_reason,
                    error_message="Empty completion received from OpenAI API",
                    provider=self.name,
                    effective_origin=self.effective_origin,
                    raw=data,
                )

            return ProviderResult(
                outcome=ProviderOutcome.COMPLETED.value,
                content=text_content,
                model=data.get("model", self.default_model),
                finish_reason=finish_reason,
                provider=self.name,
                effective_origin=self.effective_origin,
                raw=data,
            )
        except ProviderEgressError:
            raise
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            OSError,
            TimeoutError,
            json.JSONDecodeError,
            KeyError,
            ValueError,
        ) as err:
            return ProviderResult(
                outcome=ProviderOutcome.ERROR.value,
                content="",
                model=self.default_model,
                error_message=f"[OpenAI GPT Error] API request failed: {err}",
                provider=self.name,
                effective_origin=self.effective_origin,
            )
