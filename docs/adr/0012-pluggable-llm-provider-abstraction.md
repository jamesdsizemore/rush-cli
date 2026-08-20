# ADR 0012: Pluggable LLM Provider Abstraction Layer

## Context
Rush `review` operates deterministically using local AST and pattern heuristics. When AI model review is optionally requested via `--llm`, invocations must not pollute core CLI or MCP stdio transports, nor tightly couple Rush to any single AI provider.

## Decision
1. Implement `src/rush/providers/` with an abstract base class `LLMProvider`:
   - `AnthropicProvider`: Calls Anthropic Claude messages API with bounded token limits and prompt injection defense.
   - `OpenAIProvider`: Calls OpenAI chat completions API.
2. Abstract provider resolution behind `get_provider(name)` dynamically detecting configured API keys.
3. Keep default execution offline and deterministic unless an explicit provider flag is passed.

## Consequences
- Clean separation between core quality engine execution and AI model invocations.
- Stdio transport safety is preserved by ensuring all provider diagnostics and logs stream to `stderr`.
