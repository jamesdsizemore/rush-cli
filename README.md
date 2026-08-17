# rush

> Agentic code-quality CLI + stdio MCP server. Companion to
> [headcleaner](https://github.com/.../headcleaner-cli).

**Phase 3 status:** skeleton only. See `task_plan.md` for the 6-phase roadmap.

## Install

```bash
uv tool install rush-cli   # or: uvx rush
```

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
- [`findings.md`](findings.md) — research + decisions
- [`task_plan.md`](task_plan.md) — phase tracker
- [`progress.md`](progress.md) — session log

## License

MIT
