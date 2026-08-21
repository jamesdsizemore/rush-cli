"""Anthropic / OpenAI prompt cache breakpoint analyzer."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CacheBreakpointSuggestion:
    optimal_prefix_length: int
    estimated_cache_savings_percent: float
    reason: str


class PromptCacheAdvisor:
    """Analyzes system prompt and tool definitions to recommend stable prefix cache breakpoints."""

    @staticmethod
    def analyze_prefix(prefix_text: str) -> CacheBreakpointSuggestion:
        length = len(prefix_text)
        if length < 1024:
            return CacheBreakpointSuggestion(
                optimal_prefix_length=length,
                estimated_cache_savings_percent=0.0,
                reason="Prefix is under 1,024 tokens; below typical cache minimum threshold.",
            )
        return CacheBreakpointSuggestion(
            optimal_prefix_length=length,
            estimated_cache_savings_percent=85.0,
            reason="Stable prefix meets cache breakpoint threshold; eligible for 85-90% read discounts.",
        )
