# Model Context Protocol (MCP) Client Configuration Guide

## Provider-resume setup

No MCP client configuration, OAuth setting, or persistent Rush credential is required for provider continuation. Clients call the local `rush_continuity` tool and must request permission for supported user-owned CLI routes or fixed-loopback API routes. For `9router_cli`, set `RUSH_9ROUTER_API_KEY` only in the MCP server's process environment; Rush copies it only to the one Codex child process and never chooses a model.

Current setup is manual. Configure Rush as a local Model Context Protocol (MCP) server after completing the editable source installation. Automatic client discovery and connection remain **planned — implementation [Phase 65, P65-10](../phase-plans/phase-65-project-provisioning-scan-and-agent-workflow-plan.md#p65-10--single-beginner-journey-and-agent-connection-f35-f42).**

---

## 1. FastMCP Transport Architecture

Rush runs as a dedicated local child process using the Model Context Protocol over standard input/output (`stdio`).

```text
AI Coding Assistant (Client)
       │ (JSON-RPC requests over stdin)
       ▼
rush mcp serve (Server)
       │ (Detached subprocesses with stdin=DEVNULL)
       ├── rush_review, rush_lint, rush_security, rush_ai_eval, etc.
       ▼
JSON-RPC responses on stdout (Diagnostics on stderr)
```

---

## 2. Configuration for Specific MCP Clients

### Claude Desktop (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "rush": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "C:\\absolute\\path\\to\\rush-cli",
        "rush",
        "mcp",
        "serve"
      ],
      "env": {
        "RUSH_LOG_LEVEL": "warn"
      }
    }
  }
}
```

### Cursor IDE (`.cursor/mcp.json`)
```json
{
  "mcpServers": {
    "rush": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/absolute/path/to/rush-cli",
        "rush",
        "mcp",
        "serve"
      ]
    }
  }
}
```

### Zed Editor (`~/.config/zed/settings.json`)
```json
{
  "context_servers": {
    "rush": {
      "command": {
        "path": "uv",
        "args": ["run", "--directory", "/absolute/path/to/rush-cli", "rush", "mcp", "serve"]
      }
    }
  }
}
```

---

## 3. Verification Protocol

1. Start your MCP client.
2. Verify tools from the live server appear with the `rush_` prefix. The generated catalog is authoritative; do not use a copied fixed list as completeness evidence.
3. Invoke `rush_review` with an absolute project path and verify structured `ToolResult` JSON output.

See [MCP Overview](mcp-overview.md) and [MCP Reference](../reference/mcp-tool-reference.md).
