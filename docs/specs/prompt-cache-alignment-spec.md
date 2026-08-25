# Specification: Multi-Provider Prompt Cache Prefix Alignment

## 1. Overview
`CacheAligner` locally pads a prefix to its configured token threshold and returns alignment metadata. It does not call a provider, observe cache hits, or guarantee a cache-hit rate.

## 2. CLI & API Reference
* `rush context align-prompt --system "<PROMPT>"`
* `aligner.align_prompt(system_prompt, tools, messages)`
