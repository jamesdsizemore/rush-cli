# Model Context Protocol (MCP) Overview

## Continuity provider operation

`rush_continuity` exposes `provider_resume` through the shared continuity tool. Implemented provider IDs are `claude_code`, `codex_cli`, `antigravity_cli`, `9router_cli`, and fixed-loopback `omniroute_api`; explicit network permission applies identically to CLI and MCP. `9router_cli` runs Codex through fixed local 9Router with a one-process credential and no model argument, while Z.AI returns deferred without invocation.

The Model Context Protocol (MCP) connects AI models and coding assistants to local tools, development environments, and live diagnostics securely.

---

## 1. Why Rush Exposes MCP

AI assistants frequently struggle with hallucinated tool names, incompatible CLI options, and unexpected hangs. Rush provides:

1. **Consistent Surface**: Exposes catalog and custom tools from the live MCP registration path.
2. **Crash & Transport Safety**: Executes external tools with `stdin=subprocess.DEVNULL` to protect standard input streams from getting hijacked.
3. **Structured JSON Output**: Returns normalized `ToolResult` shapes with coordinate-exact line numbers and SHA-256 finding fingerprints.
4. **Automated Secret Redaction**: Prevents credentials, private keys, or API tokens from polluting the AI model's context window.

---

## 2. FastMCP tool catalog

Rush registers each current catalog tool through the shared invocation executor and also registers named custom tools. Tool names replace catalog hyphens with underscores, for example `rush_semantic_drift` and `rush_ai_eval`. Use MCP discovery against the running server for the complete current set and parameter schemas.

See [MCP Client Setup](mcp-client-setup.md) and [MCP Reference](../reference/mcp-tool-reference.md).
