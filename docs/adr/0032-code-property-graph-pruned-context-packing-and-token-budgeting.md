Current status: historical decision; Current context packing is documented in [context packing and budgeting](../workflows/context_packing_and_budgeting.md). Its local graph and token-budget mechanisms do not establish the 80% savings or elimination of overflow claims below. [Phase 63](../phase-plans/phase-63-memory-capabilities-vibecoder-plan.md) supplies the capability and benchmark contract; preserve exact target code and report measured budget effects.

# ADR-0032: Code Property Graph Pruned Context Packing and Token Budgeting

## Status
Accepted (v0.2.0 / Phase 42)

## Context
AI coding agents frequently dump entire source files into LLM prompts, leading to context window exhaustion, cache invalidation, and attention degradation on multi-file refactors.

## Decision
1. Implement `rush context pack` (`src/rush/tools/context_pack.py`) and FastMCP tool `rush_context_pack`.
2. Traverse the SQLite Code Property Graph (`.rush/codegraph.db`) to extract target symbols and their direct caller/callee signatures.
3. Skeletonize peripheral files into stripped interfaces while preserving the verbatim implementation of the edit target.
4. Enforce strict token limits using local BPE token accounting (`tiktoken`).
5. Output structured XML with prompt-caching breakpoint boundaries (`<rush_context>`).

## Consequences
- **Positive**: Reduces prompt token consumption by up to 80%, optimizes LLM attention focus, and eliminates context overflow errors.
- **Negative**: Requires BPE tokenizer dependency (`tiktoken`) in the virtual environment.
- **Safety**: Local in-memory graph traversal with zero external API calls.
