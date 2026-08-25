# Model Context Protocol (MCP) Server Architecture & Development

## Continuity provider registration

Do not add transport-specific provider logic. `provider_resume` is routed through `SessionContinuityTool`, so CLI and MCP share permission checks, projection, structured states, and output suppression. OmniRoute's fixed-loopback adapter lives there; a 9Router adapter must likewise be implemented and tested in that shared tool before it is registered.

## Continuity registration

`SessionContinuityTool` belongs in `ALL_TOOLS`; `_register_tools` exposes it as `rush_continuity` through its shared `__call__`. Do not add separate session-save MCP handlers, because they would bypass the common result and permission contract.

This guide explains how Rush exposes its 38 catalogued tools as a Model Context Protocol (MCP) server over local standard input/output (`stdio`) for AI coding assistants.

---

## 1. FastMCP Server Architecture (`src/rush/mcp.py`)

Rush uses the `mcp` Python library (FastMCP) to register tools. Each tool is named `rush_<canonical_name>` (e.g. `rush_lint`, `rush_security`, `rush_ai_eval`).

```python
# Server creation
mcp = FastMCP("rush", instructions="Deterministic code review and quality verification engine.")

# Tool registration from canonical catalog
for tool_name, tool_obj in ALL_TOOLS.items():
    safe_name = f"rush_{tool_name.replace('-', '_')}"
    mcp.tool(name=safe_name, description=tool_obj.description)(tool_obj)
```

---

## 2. FastMCP Tool Invocations (`ToolFn.__call__`)

When an AI assistant calls an MCP tool, FastMCP routes the invocation to `ToolFn.__call__()`:

```python
def __call__(
    self,
    path: str = ".",
    allow_network: bool = False,
    allow_download: bool = False,
    allow_cache_write: bool = False,
    allow_build: bool = False,
    allow_slow: bool = False,
    allow_artifact_write: bool = False,
    allow_browser: bool = False,
    **kwargs: Any,
) -> dict[str, Any]:
    perms = ExecutionPermissions(
        allow_network=allow_network,
        allow_download=allow_download,
        allow_cache_write=allow_cache_write,
        allow_build=allow_build,
        allow_slow=allow_slow,
        allow_artifact_write=allow_artifact_write,
        allow_browser=allow_browser,
    )
    result = self.run(Path(path), permissions=perms, **kwargs)
    return dict(result)
```

---

## 3. Strict Stdio Transport Invariants

1. **Pure JSON-RPC on `stdout`**: `stdout` is strictly reserved for JSON-RPC messages. `print()`, engine output, or logger banners must **never** be written to `stdout`.
2. **Diagnostics on `stderr`**: Logging, debug messages, and trace information are written exclusively to `stderr`.
3. **Detached Subprocess Stdin**: All external engine subprocesses are executed with `stdin=subprocess.DEVNULL`. This prevents any external CLI binary from consuming or locking the MCP client's stdin stream.

See [MCP Reference](../MCP_REFERENCE.md) and [MCP Client Setup](../integrations/mcp-client-setup.md).
