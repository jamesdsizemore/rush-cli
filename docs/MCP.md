# MCP server

Rush exposes its five code-quality tools through a **local stdio-only** MCP
server. It does not start an HTTP or SSE service, listen on a port, or persist
credentials.

## Start command

```bash
rush mcp serve
```

The server reserves stdout for JSON-RPC protocol frames. Operational logs use
stderr only. Set `RUSH_LOG_LEVEL=debug` when diagnosing startup or engine
execution; do not route stderr back into the protocol stream.

## Agent configuration

Use the installed `rush` command when it is on the agent's `PATH`:

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

For a repository-local Windows uv environment, point at the executable
explicitly:

```json
{
  "mcpServers": {
    "rush": {
      "command": "C:\\Users\\james\\developer\\rush-cli\\.venv\\Scripts\\rush.exe",
      "args": ["mcp", "serve"]
    }
  }
}
```

This shape works with MCP clients that accept `command` and `args`, including
Claude Desktop, Cursor, VS Code MCP integrations, and coding-agent clients.
Use the configuration file and location documented by that client.

## Tools

| MCP tool | Canonical Rush tool | Main engines |
|---|---|---|
| `rush_review` | `review` | deterministic heuristics |
| `rush_lint` | `lint` | Ruff / ESLint |
| `rush_format` | `format` | Ruff format / Prettier |
| `rush_test` | `test` | pytest / Vitest |
| `rush_security` | `security` | pip-audit / npm audit |

Every tool takes a `path` argument. The public MCP schemas do not expose
Rush's internal configuration object. Missing optional external engines return
a structured `skipped` result instead of a protocol error.

## Result contract

Tool calls return JSON text containing the same canonical payload as
`rush <tool> --json`:

```json
{
  "tool": "lint",
  "engine": "ruff",
  "engine_version": "0.16.3",
  "status": "ok",
  "duration_ms": 42,
  "summary": "ruff: no issues",
  "findings": []
}
```

`status` is one of `ok`, `warn`, `fail`, `error`, or `skipped`. A `fail` result
is a completed scan that found issues; it is not an MCP transport failure.

## Safety and process behavior

### Workflow tools

The MCP catalog exposes `commit-msg`, `ci`, and `release` as local safety
tools. `commit-msg` validates supplied text only; `ci` inspects local workflow
configuration; and `release` returns a dry-run plan. No workflow result exposes
credential values, rewrites history, creates tags, or publishes artifacts.

- Engines never inherit the server's stdin, preventing child tools from
  consuming or blocking the JSON-RPC transport.
- Engine stdout and stderr are captured and returned only as structured
  results; Rush does not print engine output to MCP stdout.
- Review is deterministic by default. Any future LLM mode remains opt-in and
  must source credentials from the environment only.
