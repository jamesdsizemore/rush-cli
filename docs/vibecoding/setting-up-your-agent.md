# Setting Up Your AI Agent with Rush

Rush exposes a local stdio **Model Context Protocol (MCP)** server. Current setup is manual and requires the editable source checkout described in [Install Rush](../getting-started/installation.md). Automatic installation, readiness checks, and agent connection are **planned — implementation [Phase 65, P65-10](../phase-plans/phase-65-project-provisioning-scan-and-agent-workflow-plan.md#p65-10--one-command-installation-and-readiness-integration-f35-f42).**

---

## 1. Step 1: Initialize Rush in Your Repository

Open your terminal at your repository root and run:

```bash
# Generate the initial rush.toml configuration
uv run --directory /absolute/path/to/rush-cli rush init /absolute/path/to/project

# Compile canonical AGENTS.md rules for all AI coding tools
uv run --directory /absolute/path/to/rush-cli rush governance sync
```

`rush init` creates `rush.toml`. Review `rush governance sync --help` and its generated diff before using governance output in a repository.

---

## 2. Step 2: Configure FastMCP for Your AI Tool

Rush includes a built-in stdio FastMCP server. Configure clients with an absolute Rush source-checkout path.

### A. Cursor Setup
1. Open Cursor **Settings** (`Cmd+,` or `Ctrl+,`).
2. Navigate to **Features** → **MCP Servers** → **Add New MCP Server**.
3. Fill in:
   - **Name**: `rush`
   - **Type**: `command`
   - **Command**: `uv run --directory /absolute/path/to/rush-cli rush mcp serve`

---

### B. Claude Code / Claude Desktop Setup
Add Rush to your Claude configuration (`~/.claude.json` or `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "rush": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/rush-cli", "rush", "mcp", "serve"]
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
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/rush-cli", "rush", "mcp", "serve"]
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
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/rush-cli", "rush", "mcp", "serve"]
    }
  }
}
```

---

## 3. Step 3: Test Your Connection

In your AI chat window, prompt your assistant:

> *"Use the `rush_capabilities` tool to inspect this repository and tell me what engines are installed."*

Your assistant should query Rush over local stdio. Confirm the discovered tool exists before invocation; server discovery is the current authority for tool names and schemas.

---

## Next Steps

- Learn how to purge AI boilerplate in [Slop-Busting & Hallucination Defense](slop-busting-and-hallucination-defense.md).
- Discover automated formatting in [Instant Fix & Auto-Remediation](instant-fix-and-auto-remediation.md).
