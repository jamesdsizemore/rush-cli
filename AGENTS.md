# Rush contributor guide

## Project contract

- Python **3.12** package managed with `uv`.
- Rush is a local CLI and **stdio-only** MCP server. stdout is JSON-RPC while
  `rush mcp serve` is running; diagnostics and logs belong on stderr.
- CLI commands and MCP registrations must call the same implementations in
  `src/rush/tools/`. Do not duplicate tool logic in the transport layer.
- Quality engines are discovered from the environment, not bundled as Rush
  dependencies. A missing engine returns a structured `skipped` result.

## Development

Hermes can expose another Python environment on PATH. Always verify with the
project interpreter:

```bash
unset VIRTUAL_ENV PYTHONPATH
.venv/Scripts/python.exe -m pytest tests/ -q
.venv/Scripts/ruff.exe check src tests
.venv/Scripts/ruff.exe format --check src tests
```

Use `run_subprocess()` for external engine commands. It captures output and
passes `stdin=DEVNULL`, preventing a child engine from consuming the MCP
transport.

## Scope and safety

- Keep results in the canonical ToolResult shape: tool, engine/version, status,
  duration, summary, findings.
- Never write secrets to logs or tool output; redact them as `[REDACTED]`.
- Workflow tools must never rewrite Git history, install hooks, create tags,
  publish releases, or upload packages without explicit user-controlled flags.
- Keep `research/` local and untracked.

## v0.2 configuration

Every `[tools.<name>]` table in `rush.toml` must match a canonical `TOOL_SPECS`
entry. Update the catalog, configuration guide, and example together when
adding a tool.
- Do not commit, publish, or alter release versions unless explicitly asked.
