# Model Context Protocol (MCP) Overview

## Continuity provider operation

`rush_continuity` exposes `provider_resume` through the shared continuity tool. The only implemented provider IDs are `claude_code`, `codex_cli`, and `antigravity_cli`; explicit network permission applies identically to CLI and MCP. 9Router and OmniRoute resume work is not exposed, while Z.AI returns deferred without invocation.

The Model Context Protocol (MCP) connects AI models and coding assistants to local tools, development environments, and live diagnostics securely.

---

## 1. Why Rush Exposes MCP

AI assistants frequently struggle with hallucinated tool names, incompatible CLI options, and unexpected hangs. Rush provides:

1. **Consistent Surface**: Exposes all 34 quality, security, and verification tools under a single schema contract.
2. **Crash & Transport Safety**: Executes external tools with `stdin=subprocess.DEVNULL` to protect standard input streams from getting hijacked.
3. **Structured JSON Output**: Returns normalized `ToolResult` shapes with coordinate-exact line numbers and SHA-256 finding fingerprints.
4. **Automated Secret Redaction**: Prevents credentials, private keys, or API tokens from polluting the AI model's context window.

---

## 2. FastMCP Tool Catalog

Rush exposes 34 FastMCP tools matching the canonical CLI commands:

- **Quality & Review**: `rush_review`, `rush_lint`, `rush_format`, `rush_typecheck`, `rush_dead`, `rush_complexity`, `rush_slop`, `rush_markdown`, `rush_templates`, `rush_sql`, `rush_yaml`, `rush_actions`, `rush_containerfile`.
- **Security & Safety**: `rush_security`, `rush_secrets`, `rush_iac`, `rush_sbom`, `rush_ai_eval`, `rush_codeql`.
- **Testing & Confidence**: `rush_test`, `rush_coverage`, `rush_mutation`, `rush_pbt`, `rush_flaky`, `rush_contract`, `rush_snapshot`, `rush_visual`, `rush_e2e`, `rush_fuzz`, `rush_load`, `rush_semantic_drift`.
- **Workflow & Release**: `rush_commit_msg`, `rush_ci`, `rush_release`.

See [MCP Client Setup](mcp-client-setup.md) and [MCP Reference](../MCP_REFERENCE.md).
