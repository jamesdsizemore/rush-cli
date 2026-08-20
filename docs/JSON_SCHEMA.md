# JSON result schema

Rush does not currently publish a standalone JSON Schema artifact. The typed canonical contract is `ToolResult` and `Finding` in `src/rush/tools/base.py`; user-readable fields and exit semantics are in [Result reference](reference/result-reference.md). MCP derives schemas from callable annotations at server startup.
