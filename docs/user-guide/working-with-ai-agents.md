# Work with an AI coding assistant

A compatible assistant can launch Rush locally and ask it to inspect a project. MCP is the protocol used for that conversation; you do not need to operate a server or open a port.

## Setup

Configure a generic stdio process:

```text
command: uv
args: run --directory /absolute/path/to/rush-cli rush mcp serve
```

Client configuration formats differ. Use [MCP client setup](../integrations/mcp-client-setup.md) and your client's current documentation.

## Closed-Loop Remediation & Session Memory (Phase 29)

Agents can autonomously query findings, inspect proposed unified diff patches, and apply safe fixes with path confinement (Control 7):

- **`rush_get_patch`**: Retrieve the unified diff patch associated with a specific finding.
- **`rush_apply_fix`**: Atomically apply a validated unified diff to workspace files with traversal protection and sensitive path shielding (`.git/`, `.env`, `.rush/cache.db`).
- **`rush_session_context`**: Query multi-turn evaluation history from `.rush/session_memory.json`. Context is framed in strict XML tags (`<rush_session_memory>`) with XML escaping to prevent prompt injection and context hijacking.

## Useful requests

- “Run `rush_check` for a fast inner-loop validation pass.”
- “Run `rush_tdd` to verify that my new features include test coverage before opening a PR.”
- “Run `rush_slop` to detect AI boilerplate, empty stubs, or redundant docstrings.”
- “Run `rush_complexity` to check for modular architecture violations with Tach.”
- “Use `rush_review` on the files I changed. Export the report to `artifacts/review.html`.”
- “Check this repository for dependency findings, agent hook vulnerabilities with Medusa, and unredacted secrets.”
- “Retrieve and apply the suggested patch for the lint finding on line 42.”

## Boundaries & Safety

The assistant receives Rush's structured local results via FastMCP. Rush opens no external network port and runs standard JSON-RPC over stdio. External engines run as contained local subprocesses with `stdin=DEVNULL`. Do not grant browser, network, slow, fuzz, baseline, release, or publication authority implicitly. Untrusted repository plugins are strictly gated behind `rush trust` (Control 6).
