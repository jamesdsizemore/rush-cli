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
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/ruff.exe format --check src tests scripts
```

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

## Agent guidelines & anti-patterns

### Understanding genuine innovation
- **Do not mistake commodity tooling for innovation**: Re-labeling existing
  developer tasks (linters, E2E runners, git commits, database seeders, basic
  error handling) with buzzwords like "Autonomous" or "Agentic" is not
  innovation. If an existing Chrome extension, framework, or standard coding
  assistant already does it, it is not an innovation.
- **Do not substitute academic jargon for practical value**: Dumping compiler
  theory (SMT solvers, BDI models, Tarjan SCC algorithms) does not constitute
  product capability.
- **Zero recycling of rejected ideas**: Once an idea or direction is rejected,
  it is permanently blacklisted. Never re-word, re-skin, or re-package it.

### Understanding what "Agentic" means
- **Automation is not Agentic**: Simply running a script, linter, test suite, or
  calling an API on demand is deterministic automation, not agentic capability.
- **Agentic means closed-loop autonomy**: An agentic capability provides the AI
  agent itself with the substrate to perceive environment state, maintain grounded
  memory, plan under uncertainty, execute in isolation, observe feedback, and
  autonomously self-correct without human intervention.
- **Agent-side vs User-side**: Agentic features live on the *agent's* side of the
  system (enhancing how the AI reasons, navigates, remembers, and verifies), not
  as consumer UI widgets or product gimmicks for the end-user.

### Scope boundaries
- **No UI/Frontend design**: Rush is strictly a local CLI, FastMCP server, and
  backend/systems quality substrate. Never propose or build UI design tools,
  visual mockups, color/theme pickers, or Figma-style visual canvases.
- **No unprompted Git hooks**: Never install, propose, or configure Git hooks.


