# Tutorial: Connecting an AI Coding Assistant via MCP

**Goal:** Configure Claude Desktop, Cursor, Claude Code, or Windsurf to call Rush quality and security tools over local stdio.

---

## 1. FastMCP Local Server Test

Before configuring your client, verify that the Rush stdio server boots cleanly:

```bash
uv run rush mcp serve
```
*(Press Ctrl+C to stop. Notice that no banners or logs are printed to stdout, keeping JSON-RPC pure.)*

---

## 2. Connect Your AI Assistant

Add to your editor's MCP configuration (`.cursor/mcp.json` or `claude_desktop_config.json`):

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
      ]
    }
  }
}
```

---

## 3. Test Prompts with Your AI Assistant

Once connected, test with these prompts:
- *"Run rush_review on this repository and tell me if there are any scaffold TODOs or overly complex files."*
- *"Run rush_security to check for vulnerable dependencies and unredacted secrets."*
- *"Run rush_lint on src/ and fix any issues reported by the linters."*

See [Working with AI Agents](../user-guide/working-with-ai-agents.md) and [MCP Overview](../integrations/mcp-overview.md).
