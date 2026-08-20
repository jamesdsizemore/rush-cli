# Tutorial: connect an AI coding assistant

**Outcome:** let a compatible assistant call local Rush tools over stdio.

**Prerequisites:** a working Rush checkout and an MCP-capable client.

1. Verify `uv run --directory /absolute/path/to/rush-cli rush mcp serve` starts without writing a banner to stdout.
2. Add a generic stdio server entry using command `uv` and arguments `run --directory ... rush mcp serve`.
3. Restart the client and confirm tools named `rush_review`, `rush_lint`, and `rush_test` appear.
4. Ask: “Run Rush review on this project and explain skipped checks.”
5. Require approval before any action outside ordinary read/check behavior.

**Expected:** structured ToolResult data; debug logs only on stderr. No port opens.

**Next:** [Working with AI agents](../user-guide/working-with-ai-agents.md).
