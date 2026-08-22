# Specification: Multi-Provider Prompt Cache Prefix Alignment

## 1. Overview
`CacheAligner` (`src/rush/token_economy/cache_aligner.py`) structures prompt prefixes to exceed provider-specific cache thresholds (>= 1,024 tokens) and injects ephemeral cache-control headers, guaranteeing >= 85% KV cache hit rates.

## 2. CLI & API Reference
* `rush context align-prompt --system "<PROMPT>"`
* `aligner.align_prompt(system_prompt, tools, messages)`
