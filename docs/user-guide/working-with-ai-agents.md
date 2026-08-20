# Work with an AI coding assistant

A compatible assistant can launch Rush locally and ask it to inspect a project. MCP is the protocol used for that conversation; you do not need to operate a server or open a port.

## Setup

Configure a generic stdio process:

```text
command: uv
args: run --directory /absolute/path/to/rush-cli rush mcp serve
```

Client configuration formats differ. Use [MCP client setup](../integrations/mcp-client-setup.md) and your client's current documentation.

## Useful requests

- “Use Rush to review the Python files I changed. Explain each warning.”
- “Run relevant lint and test checks. Tell me which result was skipped and why.”
- “Check this repository for dependency and secret findings without changing files.”
- “Inspect the GitHub Actions files and summarize only actionable results.”

## Boundaries

The assistant receives Rush's structured local results. Rush opens no network server. External engines still run as local subprocesses and may have their own behavior. `review --llm` is not a working AI review; MCP does not change that. Do not grant browser, network, slow, fuzz, baseline, release, or publication authority implicitly.
