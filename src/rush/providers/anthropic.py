"""Anthropic Claude LLM provider implementation."""

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


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    default_model = "claude-3-5-sonnet-20241022"
    endpoint_url = "https://api.anthropic.com/v1/messages"
    effective_origin = "https://api.anthropic.com"

    def is_configured(self) -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY"))

    def summarize_findings(
        self,
        findings: list[dict[str, Any]],
        *,
        allow_network: bool = False,
    ) -> ProviderResult | None:
        if not self.is_configured():
            return None

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        n_findings = len(findings)

        if not allow_network:
            summary = (
                f"[Anthropic Claude] Analyzed {n_findings} code review finding(s) "
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
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            "user-agent": f"rush-cli/{__version__}",
        }

        payload = {
            "model": self.default_model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
        }

        try:
            _status, body = safe_provider_post(
                self.endpoint_url,
                headers=headers,
                data=json.dumps(payload),
            )
            data = json.loads(body.decode("utf-8"))
            text_content = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    text_content += block.get("text", "")
            finish_reason = data.get("stop_reason", "")

            if not text_content.strip():
                return ProviderResult(
                    outcome=ProviderOutcome.ERROR.value,
                    content="",
                    model=data.get("model", self.default_model),
                    finish_reason=finish_reason,
                    error_message="Empty completion received from Anthropic API",
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
                error_message=f"[Anthropic Claude Error] API request failed: {err}",
                provider=self.name,
                effective_origin=self.effective_origin,
            )
