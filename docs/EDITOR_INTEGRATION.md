# Editor integration

Rush ships no editor extension. Configure an editor task to run a non-mutating command in the workspace:

```text
rush lint . --json
rush format . --check --json
```

For coding assistants with MCP support, use [MCP client setup](integrations/mcp-client-setup.md). Use absolute executable/project paths when GUI applications inherit a limited `PATH`.
