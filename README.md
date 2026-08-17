# rush

> Agentic code-quality CLI + stdio MCP server. Companion to
> [headcleaner](https://github.com/.../headcleaner-cli).

**Status:** v0.1.0-alpha. Rush runs real Python and JS/TS quality engines
through the CLI and the same canonical implementations through its local stdio
MCP server.

## Install

```bash
# From this checkout
uv sync

# Windows (PowerShell or Git Bash)
.venv/Scripts/rush.exe --help

# macOS/Linux
.venv/bin/rush --help
```

For a persistent global command from this checkout, use
`scripts/install.ps1` on Windows or `scripts/install.sh` on macOS/Linux. Rush
discovers quality engines from your environment; install Ruff, pytest,
pip-audit, ESLint, Prettier, Vitest, or npm separately when you want their
respective checks.

## Quick start

```bash
rush --help
rush review ./src
rush lint ./src --json
rush test ./tests
rush mcp serve            # stdio MCP server (for coding agents)
```

## Documentation

- [`requirements.md`](requirements.md) — what ships in v0.1
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — how it's built
- [`docs/MCP.md`](docs/MCP.md) — agent configuration and MCP protocol contract
- [`AGENTS.md`](AGENTS.md) — contributor and transport constraints
- [`CHANGELOG.md`](CHANGELOG.md) — alpha release notes
- [`findings.md`](findings.md) — research + decisions
- [`task_plan.md`](task_plan.md) — phase tracker
- [`progress.md`](progress.md) — session log

## License

MIT
