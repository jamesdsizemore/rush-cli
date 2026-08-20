# Editor & IDE Integration Guide

Rush can be integrated into any modern code editor as a command-line task runner or as a Model Context Protocol (MCP) server for editor-embedded AI assistants.

---

## 1. Visual Studio Code & Cursor Integration

### VS Code Tasks (`.vscode/tasks.json`)
Configure automated check tasks that run in the background:

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "Rush: Full Project Review",
      "type": "shell",
      "command": "uv run rush review .",
      "group": {
        "kind": "build",
        "isDefault": true
      },
      "presentation": {
        "reveal": "always",
        "panel": "shared"
      }
    },
    {
      "label": "Rush: Lint & Format Check",
      "type": "shell",
      "command": "uv run rush lint . && uv run rush format . --check",
      "group": "test",
      "problemMatcher": []
    },
    {
      "label": "Rush: Security & Secrets Scan",
      "type": "shell",
      "command": "uv run rush security . && uv run rush secrets .",
      "group": "test",
      "problemMatcher": []
    }
  ]
}
```

### Cursor & Windsurf AI Assistant Configuration (`mcp.json`)
Connect Rush to Cursor's Composer or Chat interface over stdio:

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

---

## 2. JetBrains IDEs (PyCharm, WebStorm, IntelliJ)

1. Open **Settings / Preferences** -> **Tools** -> **External Tools**.
2. Click **+** to add a new tool:
   - **Name**: `Rush Review`
   - **Program**: `uv`
   - **Arguments**: `run rush review "$ProjectFileDir$"`
   - **Working directory**: `$ProjectFileDir$`
3. Assign a keybinding under **Keymap** -> **External Tools** -> **Rush Review**.

---

## 3. Zed Editor Integration

Add to `~/.config/zed/settings.json`:

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

## 4. Neovim (`nvim-lint` or terminal runners)

Using Lua in Neovim:

```lua
vim.keymap.set('n', '<leader>rr', ':!uv run rush review .<CR>', { desc = 'Run Rush Review' })
vim.keymap.set('n', '<leader>rl', ':!uv run rush lint .<CR>', { desc = 'Run Rush Lint' })
vim.keymap.set('n', '<leader>rs', ':!uv run rush security .<CR>', { desc = 'Run Rush Security' })
```

For AI agent setup, see [MCP Client Setup](integrations/mcp-client-setup.md).
