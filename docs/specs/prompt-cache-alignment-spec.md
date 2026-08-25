# Specification: Multi-Provider Prompt Cache Prefix Alignment

## Relation to context recovery

Prompt-cache alignment does not override context-budget boundaries. A redacted CCR recovery handle is the evidence-preserving fallback for omitted context; it is not cache padding, a provider call, or a reason to send more prompt material.

## 1. Overview
`CacheAligner` locally pads a prefix to its configured token threshold and returns alignment metadata. It does not call a provider, observe cache hits, or guarantee a cache-hit rate.

## 2. CLI & API Reference
* `rush context align-prompt --system "<PROMPT>"`
* `aligner.align_prompt(system_prompt, tools, messages)`
