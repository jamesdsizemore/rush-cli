# ADR-001: stdio-only MCP

**Status:** accepted

## Context

Rush needs a local coding-assistant surface without daemon, authentication, port, or deployment complexity.

## Decision

Expose FastMCP over local stdio only through `rush mcp serve`. Reserve stdout for JSON-RPC; send diagnostics to stderr; detach engine stdin.

## Consequences

Clients must launch a local process and preserve its environment. HTTP/SSE and remote access are out of scope. Real stdio integration tests are mandatory.
