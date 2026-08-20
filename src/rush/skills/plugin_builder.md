# AI Agent Skill: Rush Custom Plugin Builder

## Description
This skill enables coding agents to construct declarative, secure, and compliant custom plugins for Rush.

## Output Contract
Every plugin script must output a single JSON object to stdout formatted as a canonical `ToolResult`:
```json
{
  "tool": "my-plugin-name",
  "engine": "custom",
  "engine_version": "1.0.0",
  "status": "ok",
  "duration_ms": 15,
  "summary": "my-plugin-name: 0 findings reported",
  "findings": [
    {
      "file": "src/module.py",
      "line": 42,
      "column": 5,
      "rule": "RULE_001",
      "message": "Detailed finding description",
      "severity": "warn"
    }
  ]
}
```

## Security Requirements
1. The script must never access network services unless explicitly permitted.
2. The script must output diagnostics and logs to `stderr`, keeping `stdout` pure JSON.
3. The script must declare its configuration table in `rush.toml`:
```toml
[plugins.my-plugin-name]
command = "python scripts/my_plugin.py"
description = "Custom AST pattern linter"
file_extensions = [".py"]
```
