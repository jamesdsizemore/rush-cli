# Model Context Protocol (MCP) Client Configuration Guide

Configure Rush as a local Model Context Protocol (MCP) server across Claude Desktop, Claude Code, Cursor, Windsurf, Zed, and other AI coding assistants.

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
        "C:\\Users\\james\\developer\\rush-cli",
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
        "${workspaceFolder}",
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
        "args": ["run", "rush", "mcp", "serve"]
      }
    }
  }
}
```

---

## 3. Verification Protocol

1. Start your MCP client.
2. Verify the catalogued tools, including `rush_continuity`, appear with the `rush_` prefix:
   - `rush_review`, `rush_lint`, `rush_format`, `rush_test`, `rush_security`, `rush_typecheck`, `rush_dead`, `rush_complexity`, `rush_slop`, `rush_markdown`, `rush_actions`, `rush_yaml`, `rush_sql`, `rush_templates`, `rush_containerfile`, `rush_iac`, `rush_secrets`, `rush_sbom`, `rush_ai_eval`, `rush_codeql`, `rush_coverage`, `rush_pbt`, `rush_flaky`, `rush_contract`, `rush_snapshot`, `rush_visual`, `rush_mutation`, `rush_e2e`, `rush_fuzz`, `rush_load`, `rush_semantic_drift`, `rush_commit_msg`, `rush_ci`, `rush_release`, `rush_continuity`.
3. Invoke `rush_review` with `{"path": "."}` and verify structured `ToolResult` JSON output.

See [MCP Overview](mcp-overview.md) and [MCP Reference](../MCP_REFERENCE.md).
