# Model Context Protocol (MCP) Server Architecture & Development

## Continuity provider registration

Do not add transport-specific provider logic. `provider_resume` is routed through `SessionContinuityTool`, so CLI and MCP share permission checks, projection, structured states, and output suppression. OmniRoute's fixed-loopback adapter and the `9router_cli` Codex-through-fixed-local-9Router adapter live there. The latter copies its process-only key into the Codex child environment, does not select a model, and must retain shared-route tests.

## Continuity registration

`SessionContinuityTool` belongs in `ALL_TOOLS`; `_register_tools` exposes it as `rush_continuity` through its shared `__call__`. Do not add separate session-save MCP handlers, because they would bypass the common result and permission contract.

This guide explains how Rush exposes 53 catalogued tools plus custom compatibility routes as 74 registered Model Context Protocol (MCP) names over local standard input/output (`stdio`) for AI coding assistants. `scripts/sync_docs.py --check` compares every registered parameter/default/type tuple with the documentation receipt.

---

## 1. FastMCP Server Architecture (`src/rush/mcp.py`)

Rush uses the `mcp` Python library (FastMCP) to register tools. Each tool is registered with `tool.__call__` named `rush_<canonical_name>` (hyphens normalized to underscores, e.g. `rush_error_catalog`, `rush_license_matrix`, `rush_iam_audit`, `rush_provenance_ai`, `rush_dead_asset`, `rush_pr_synthesize`, `rush_attest`, `rush_mem_profile`, `rush_cold_start`, `rush_offline_review`, `rush_benchmark`), with `rush_attest_generate` preserved as an explicit alias. Duplicate wrapper functions are strictly prohibited.

---

## 2. FastMCP Tool Invocations (`ToolFn.__call__`)

When an AI assistant calls a catalog tool, FastMCP routes the invocation through the registered tool's real `ToolFn.__call__()` signature. Signatures vary by tool; do not document a synthetic shared options object. For example, the current error-catalog surface is:

```python
def __call__(
    self, path: Path, *,
    allow_artifact_write: bool = False,
    export_path: Path | str | None = None,
) -> ToolResult:
    ...
```

---

## 3. Strict Stdio Transport Invariants

1. **Pure JSON-RPC on `stdout`**: `stdout` is strictly reserved for JSON-RPC messages. `print()`, engine output, or logger banners must **never** be written to `stdout`.
2. **Diagnostics on `stderr`**: Logging, debug messages, and trace information are written exclusively to `stderr`.
3. **Detached Subprocess Stdin**: All external engine subprocesses are executed with `stdin=subprocess.DEVNULL`. This prevents any external CLI binary from consuming or locking the MCP client's stdin stream.

See [MCP Reference](../MCP_REFERENCE.md) and [MCP Client Setup](../integrations/mcp-client-setup.md).
