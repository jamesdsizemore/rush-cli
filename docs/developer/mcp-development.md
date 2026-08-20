# MCP development

FastMCP registers the same tool objects used by CLI. `__call__` is the schema surface; `run(..., config=...)` is internal.

Rules:

- use JSON-schema-safe annotations and defaults;
- never expose the config object;
- keep descriptions short and capability-accurate;
- stdout is JSON-RPC only; diagnostics are stderr NDJSON;
- all engine subprocesses detach stdin;
- preserve required process environment when clients supply overrides;
- optional ToolResult fields must validate when omitted/null;
- keep tool names and catalog/registry parity tested.

Real-server tests must initialize an official stdio client, list schemas, call representative tools (including one real subprocess path), verify canonical structured content, capture stderr with a real file on Windows, and enforce timeout/cleanup. Avoid running Rush's own recursive test suite as the MCP test target; use isolated fixtures.
