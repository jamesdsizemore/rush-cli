# ADR-0023: Async Local Model Bridge via httpx

## Status
Accepted

## Context
Multi-model consensus verification (`rush consensus`) and local inference evaluation require non-blocking asynchronous communication with local runtimes (Ollama, vLLM, LM Studio) and remote model endpoints.

## Decision
1. Standardize on `httpx==0.28.1` for asynchronous HTTP/1.1 and HTTP/2 transport.
2. Enforce strict connection timeouts (10 seconds), connection pooling, and structured error fallbacks when local daemons are unreachable.
3. Ensure model dispatch loops never block the FastMCP stdio transport thread.

## Consequences
- Fast, non-blocking multi-model queries during agent review loops.
- Resilient error handling when local AI models or endpoints are offline.
