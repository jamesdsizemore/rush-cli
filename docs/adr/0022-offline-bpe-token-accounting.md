Current status: historical decision; Current dependency authority is `pyproject.toml`/`uv.lock` (tiktoken 0.14.0), and current token commands are listed in [CLI reference](../CLI_REFERENCE.md). The old pins, model/pricing names, latency, and overflow guarantees below are historical; local token estimates do not prove actual provider billing or universal tokenizer equivalence. [Phase 63](../phase-plans/phase-63-memory-capabilities-vibecoder-plan.md) requires measured token effects.

# ADR-0022: Offline BPE Token Accounting via tiktoken

## Status
Accepted

## Context
Tools calculating prompt token budgets (`rush token-cost`, `rush context-diet`) and dynamic MCP pagination (`rush_paginate_findings`) require exact BPE token calculations matching production frontier models without making external API network requests.

## Decision
1. Embed `tiktoken==0.9.0` directly within Rush's runtime.
2. Bundle pre-compiled BPE encoding vocabularies (`cl100k_base`, `o200k_base`) alongside static pricing metadata in `src/rush/data/model_pricing.json`.
3. Enforce sub-millisecond offline token counting and inference cost forecasting for Claude 3.7, GPT-4o, DeepSeek-V3/R1, and Gemini 2.5.

## Consequences
- 100% deterministic, offline token accounting with zero API latency.
- Precise context window budgeting preventing agent overflow errors.
