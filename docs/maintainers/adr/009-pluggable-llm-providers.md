# ADR-009: Pluggable LLM Providers Architecture

## Status
Accepted

## Context
Rush AI review extensions must be modular, allowing different AI models (Claude, OpenAI, local models) without coupling the core CLI/MCP transport layers to third-party SDKs.

## Decision
1. Introduce `src/rush/providers/` with `LLMProvider` abstract contract.
2. Ensure default execution remains 100% deterministic and offline.
3. Keep all provider logging strictly on `stderr` to protect stdio MCP transport.

## Consequences
- AI provider isolation from core engine dispatcher.
- Extensibility for local and hosted model backends.
