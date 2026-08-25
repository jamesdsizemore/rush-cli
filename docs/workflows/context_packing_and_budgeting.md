# Workflow: Graph-Pruned Context Packing & Budgeting

## 1. Overview
`rush context pack --json` returns a canonical continuity `ToolResult`: selected source evidence, estimated local tokens, omissions, and recovery state. It skeletonizes the selected target file; it does not claim graph/PageRank ranking or provider-token savings. An insufficient budget returns `skipped` with an explicit omission reason.

## 2. Usage Examples
```bash
# Pack context for authenticate method with a 2000 token limit
rush context pack --path src/rush/cli.py --symbol run_stdio --budget 2000

# Call via FastMCP
rush_context_pack(path="src/rush/cli.py", symbol="run_stdio", budget=2000)
```
