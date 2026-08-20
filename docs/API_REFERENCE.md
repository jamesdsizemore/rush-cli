# Python API reference

Rush's supported product surfaces are the CLI and local stdio MCP server, not a stable public Python SDK. Contributors use `ToolFn.run`, ToolResult/Finding, `ALL_TOOLS`, `ENGINES`, and catalog/config modules as internal contracts documented in [Developer guide](DEVELOPER_GUIDE.md). Importing internals couples callers to unreleased implementation details.
