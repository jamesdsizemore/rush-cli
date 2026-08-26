# Workflow: Graph-Pruned Context Packing & Budgeting

## Insufficient-budget branch

1. Read the `context_pack` envelope.
2. If it is `skipped` and recovery is `available`, preserve the returned handle in the handoff. If recovery is `not_created/cache_write_required`, either grant cache-write permission deliberately or keep the omission explicit; do not fabricate a handle.
3. Call `context_retrieve` only for that handle when omitted evidence becomes necessary.

The recovery chunk is redacted before permitted storage and never causes automatic budget expansion. An omitted payload is not delivered, so overflow telemetry is `not_measured` with `provider_cost: null` and creates no savings-ledger event.

## 1. Overview
`rush context pack --json` returns a canonical continuity `ToolResult`: selected source evidence, estimated local tokens, omissions, and recovery state. It skeletonizes the selected target file; it does not claim graph/PageRank ranking or provider-token savings. An insufficient budget returns `skipped` with an explicit omission reason.

## 2. Usage Examples
```bash
# Pack context for authenticate method with a 2000 token limit
rush context pack --path src/rush/cli.py --symbol run_stdio --budget 2000

# Call via FastMCP
rush_context_pack(path="src/rush/cli.py", symbol="run_stdio", budget=2000)
```
