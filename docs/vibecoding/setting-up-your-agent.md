# Setting Up Your AI Agent with Rush

Rush communicates seamlessly with all major AI coding assistants through the open **Model Context Protocol (MCP)** and canonical **`AGENTS.md`** rule files.

Setting up your environment takes less than two minutes.

---

## 1. Step 1: Initialize Rush in Your Repository

Open your terminal at your repository root and run:

```bash
# Generate the initial rush.toml configuration
rush init .

# Compile canonical AGENTS.md rules for all AI coding tools
rush governance sync
```

This creates:
- `rush.toml`: Your project's quality settings.
- `AGENTS.md`: The single source of truth for all AI assistants.
- `.cursorrules`, `.clinerules`, `.windsurfrules`: Tailored instructions for your specific IDEs.

---

## 2. Step 2: Configure FastMCP for Your AI Tool

Rush includes a built-in stdio FastMCP server (`rush mcp serve`) that exposes all Rush tools directly to your AI assistant.

### A. Cursor Setup
1. Open Cursor **Settings** (`Cmd+,` or `Ctrl+,`).
2. Navigate to **Features** → **MCP Servers** → **Add New MCP Server**.
3. Fill in:
   - **Name**: `rush`
   - **Type**: `command`
   - **Command**: `rush mcp serve`

---

### B. Claude Code / Claude Desktop Setup
Add Rush to your Claude configuration (`~/.claude.json` or `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "rush": {
      "command": "rush",
      "args": ["mcp", "serve"]
    }
  }
}
```

---

### C. Cline / Roo Code Setup
1. In the Cline extension panel in VS Code, click the **MCP Servers** icon.
2. Click **Configure MCP Servers**.
3. Add the following entry:

```json
{
  "mcpServers": {
    "rush": {
      "command": "rush",
      "args": ["mcp", "serve"]
    }
  }
}
```

---

### D. Windsurf / Cascade AI Setup
Add Rush to your Windsurf Cascade MCP settings (`~/.codeium/windsurf/mcp_config.json`):

```json
{
  "mcpServers": {
    "rush": {
      "command": "rush",
      "args": ["mcp", "serve"]
    }
  }
}
```

---

## 3. Step 3: Test Your Connection

In your AI chat window, prompt your assistant:

> *"Use the `rush_capabilities` tool to inspect this repository and tell me what engines are installed."*

Your assistant will query Rush over local stdio and list all available quality tools in real-time!

---

## Next Steps

- Learn how to purge AI boilerplate in [Slop-Busting & Hallucination Defense](slop-busting-and-hallucination-defense.md).
- Discover automated formatting in [Instant Fix & Auto-Remediation](instant-fix-and-auto-remediation.md).
