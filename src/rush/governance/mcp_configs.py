"""IDE MCP server configuration generator (.cursor, .vscode)."""

from __future__ import annotations

import json
from pathlib import Path


class McpConfigGenerator:
    """Generates standard MCP client configurations for Cursor and VS Code."""

    @staticmethod
    def generate_cursor_config(repo_root: Path) -> Path:
        cursor_dir = repo_root / ".cursor"
        cursor_dir.mkdir(parents=True, exist_ok=True)
        config_file = cursor_dir / "mcp.json"

        config = {
            "mcpServers": {
                "rush": {
                    "command": "rush",
                    "args": ["mcp", "serve"],
                    "env": {},
                }
            }
        }
        config_file.write_text(json.dumps(config, indent=2), encoding="utf-8")
        return config_file

    @staticmethod
    def generate_vscode_config(repo_root: Path) -> Path:
        vscode_dir = repo_root / ".vscode"
        vscode_dir.mkdir(parents=True, exist_ok=True)
        config_file = vscode_dir / "mcp.json"

        config = {
            "mcpServers": {
                "rush": {
                    "command": "rush",
                    "args": ["mcp", "serve"],
                }
            }
        }
        config_file.write_text(json.dumps(config, indent=2), encoding="utf-8")
        return config_file
