# MCP client setup

Rush has verified generic stdio behavior. Client-specific configuration formats change independently, so this guide does not claim a vendor-specific schema without repository evidence.

## Generic template

```json
{
  "command": "uv",
  "args": [
    "run",
    "--directory",
    "/absolute/path/to/rush-cli",
    "rush",
    "mcp",
    "serve"
  ],
  "env": {"RUSH_LOG_LEVEL": "warn"}
}
```

On Windows, use a valid absolute Windows path understood by the client. The client must preserve ordinary process environment variables; replacing the entire environment with only `RUSH_LOG_LEVEL` can break Python and child processes.

## Verify

1. Run `uv run --directory /absolute/path/to/rush-cli rush --help` manually.
2. Start the client and list tools; expect 32 `rush_...` tools.
3. Call `rush_review` on an existing path.
4. If it fails, enable `RUSH_LOG_LEVEL=debug` and inspect stderr only.

Do not add shell wrappers that echo banners to stdout; they corrupt JSON-RPC. See [Troubleshooting](../user-guide/troubleshooting.md).
