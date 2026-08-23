# Workflow: Graph-Pruned Context Packing & Budgeting

## 1. Overview
`ContextPacker` (`rush context pack`) constructs tight, token-bounded context packages by extracting target symbol implementations verbatim and eliding surrounding peripheral functions into AST skeletons under a hard budget cap.

## 2. Usage Examples
```bash
# Pack context for authenticate method with a 2000 token limit
rush context pack --path src/rush/cli.py --symbol run_stdio --budget 2000

# Call via FastMCP
rush_context_pack(path="src/rush/cli.py", symbol="run_stdio", budget=2000)
```
