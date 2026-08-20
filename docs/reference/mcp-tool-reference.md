# MCP tool reference

`rush mcp serve` registers each catalog tool as `rush_<name>` using the same Python tool objects as the CLI. Tool names include hyphens where the command does, for example `rush_semantic-drift`.

## Common result

Every tool returns canonical ToolResult data documented in [Result reference](result-reference.md). A missing optional engine is a structured `skipped` result, not an installation request.

## Inputs

Most tools expose:

```json
{"path":"/absolute/path/to/project"}
```

Special callable signatures verified by implementation include:

- `rush_review`: `path`, `use_llm=false`, `use_graft=false`.
- `rush_format`: `path`, check-mode option as generated from its callable signature.
- `rush_semantic-drift`: `path`, `allow_browser=false`, `allow_slow=false`.

Other guarded placeholder objects expose only `path` through their current `__call__`; their internal required permission is therefore not grantable over the current MCP schema. Inspect `tools/list` from the running server instead of guessing parameters.

## Complete tool names

```text
rush_review, rush_lint, rush_format, rush_test, rush_security,
rush_typecheck, rush_dead, rush_complexity, rush_slop,
rush_markdown, rush_actions, rush_yaml, rush_sql, rush_templates,
rush_containerfile, rush_iac, rush_secrets, rush_sbom, rush_codeql,
rush_coverage, rush_pbt, rush_flaky, rush_contract, rush_snapshot,
rush_visual, rush_mutation, rush_e2e, rush_fuzz, rush_load,
rush_semantic-drift, rush_commit-msg, rush_ci, rush_release
```

## Protocol guarantees

- stdio only; no HTTP/SSE listener.
- stdout is JSON-RPC only.
- NDJSON diagnostics go to stderr.
- engine subprocess stdin is detached so it cannot consume MCP frames.
- the client-provided process environment must preserve required Windows/runtime variables; environment replacement can break child engines.

See [MCP client setup](../integrations/mcp-client-setup.md) and [MCP development](../developer/mcp-development.md).
