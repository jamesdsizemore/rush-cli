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
- *"Run rush_tdd to verify that all my new changes have unit test coverage before I open a PR."*
- *"Run rush_slop on src/ to check for AI boilerplate, redundant comments, or stub routines."*
- *"Run rush_complexity to check if my changes violate any modular boundary rules with Tach."*
- *"Run rush_review on this repository and tell me if there are any scaffold TODOs or overly complex files."*
- *"Run rush_security to check for vulnerable dependencies, agent hook security risks via Medusa, and unredacted secrets."*
- *"Run rush_lint on src/ and fix any issues reported by the linters."*

See [Working with AI Agents](../user-guide/working-with-ai-agents.md) and [MCP Overview](../integrations/mcp-overview.md).

## Using Context Intelligence & HalluGuard with AI Agents

When configuring your AI coding agent with Rush's FastMCP server:
* Call `rush_token_outline(path="...")` to read compact AST skeletons instead of consuming large whole-file token budgets.
* Call `rush_hallu_guard(path="...")` to verify all imports in generated code are grounded in installed packages.
* Call `rush_context_retrieve(chunk_hash="...")` to decompress and inspect large tool logs stored in CCR.
* Call `rush_context_mistakes_check()` to review past Git revert regressions and avoid repeat errors.
