"""Review LLM egress and prompt integration.

Handles opt-in LLM summary calls, origin validation, outcome verification,
and synthetic finding generation.
"""

from __future__ import annotations

import urllib.error
from collections.abc import Sequence
from typing import Any

from rush.providers import (
    APPROVED_PROVIDER_ORIGINS,
    ProviderOutcome,
    get_configured_provider,
)
from rush.tools.base import Finding, LlmStatus


def _is_valid_llm_response(
    outcome: str,
    content: str,
    effective_origin: str,
    allowed_origins: frozenset[str],
) -> bool:
    """Validate that LLM response is completed, non-empty, and from an approved origin."""
    return (
        outcome == ProviderOutcome.COMPLETED.value
        and bool(content.strip())
        and effective_origin in allowed_origins
    )


def _maybe_call_llm(
    findings: Sequence[Finding],
    *,
    provider: Any | None = None,
    allow_network: bool = True,
    allowed_origins: frozenset[str] | None = None,
) -> dict[str, Any] | None:
    """Call configured LLM provider if credentials exist.

    Phase 57 / Architecture §10.1:
      - Validates provider outcome, non-empty completion, and approved effective HTTPS origin.
      - Sets review_kind="llm" ONLY when outcome=="completed", content is non-empty, and effective origin is approved.
      - Falls back to heuristic review (or error) otherwise.
    """
    origins = (
        allowed_origins if allowed_origins is not None else APPROVED_PROVIDER_ORIGINS
    )

    active_provider = provider if provider is not None else get_configured_provider()
    if active_provider is None:
        return None

    raw_findings = [dict(f) if isinstance(f, dict) else f.to_dict() for f in findings]
    try:
        response = active_provider.summarize_findings(
            raw_findings, allow_network=allow_network
        )
    except (OSError, TimeoutError, urllib.error.URLError, ValueError, KeyError):
        return None

    if response is None:
        return None

    outcome = getattr(response, "outcome", "")
    content = getattr(response, "content", "")
    effective_origin = getattr(response, "effective_origin", "")
    model = getattr(response, "model", "")
    provider_name = getattr(
        response, "provider", getattr(active_provider, "name", "unknown")
    )

    if _is_valid_llm_response(outcome, content, effective_origin, origins):
        return {
            "provider": provider_name,
            "summary": content,
            "model": model,
            "review_kind": "llm",
            "outcome": outcome,
            "effective_origin": effective_origin,
        }

    return None


def format_review_prompt(findings: list[Finding] | list[dict[str, Any]]) -> str:
    """Format review findings into a human-readable prompt string."""
    lines = ["Review findings:"]
    for f in findings:
        path = f.get("path", "") if isinstance(f, dict) else getattr(f, "path", "")
        line = f.get("line", 0) if isinstance(f, dict) else getattr(f, "line", 0)
        rule = f.get("rule", "") if isinstance(f, dict) else getattr(f, "rule", "")
        msg = f.get("message", "") if isinstance(f, dict) else getattr(f, "message", "")
        lines.append(f"- {path}:{line} [{rule}] {msg}")
    return "\n".join(lines)


def parse_llm_findings(llm_summary: dict[str, Any]) -> list[Finding]:
    """Parse synthetic findings from LLM summary response."""
    summary = llm_summary.get("summary", "")
    if not summary:
        return []
    return [
        Finding(
            path="",
            line=0,
            rule="llm-summary",
            severity="info",
            message=summary,
        )
    ]


def apply_llm_review(
    findings: Sequence[Finding],
    use_llm: bool,
) -> tuple[LlmStatus, str | None, list[Finding]]:
    """Execute LLM review step if enabled, returning kind, provider, and extra findings."""
    if not use_llm:
        return "heuristic", None, []

    llm_summary = _maybe_call_llm(findings, allow_network=True)
    if llm_summary and llm_summary.get("review_kind") == "llm":
        extra = parse_llm_findings(llm_summary)
        return "llm", llm_summary.get("provider"), extra

    return "heuristic", None, []


# Canonical public alias
maybe_call_llm = _maybe_call_llm

__all__ = [
    "_is_valid_llm_response",
    "_maybe_call_llm",
    "apply_llm_review",
    "format_review_prompt",
    "maybe_call_llm",
    "parse_llm_findings",
]
