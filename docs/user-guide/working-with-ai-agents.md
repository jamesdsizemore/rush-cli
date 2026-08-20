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

- “Run `rush_tdd` to verify that my new features include test coverage before opening a PR.”
- “Run `rush_slop` to detect AI boilerplate, empty stubs, or redundant docstrings.”
- “Run `rush_complexity` to check for modular architecture violations with Tach.”
- “Use `rush_review` on the files I changed. Export the report to `artifacts/review.html`.”
- “Run relevant lint and test checks. Tell me which result was skipped and why.”
- “Check this repository for dependency findings, agent hook vulnerabilities with Medusa, and unredacted secrets.”
- “Inspect the GitHub Actions files and summarize only actionable results.”

## Boundaries

The assistant receives Rush's structured local results via FastMCP. Rush opens no external network port and runs standard JSON-RPC over stdio. External engines run as contained local subprocesses with `stdin=DEVNULL`. Do not grant browser, network, slow, fuzz, baseline, release, or publication authority implicitly.
