# Troubleshooting Guide & Common Resolutions

This guide addresses common error messages, unexpected behaviors, and troubleshooting steps across all 38 tools and 121 engines in Rush CLI.

---

## 1. Common Issues & Solutions

### Tool Returns `status: "skipped"`
- **Cause**: The external engine binary is not installed on your system or is missing from `PATH`.
- **Solution**: Install the required engine locally (e.g. `npm install -g eslint`, `pip install semgrep`, `brew install trivy`). Run `rush capabilities . --json` to verify engine discovery.

### Tool Returns `status: "skipped"` with Missing Permission Message
- **Cause**: The command requires an explicit execution permission flag (e.g. running mutation testing without `--allow-slow`, or running a browser test without `--allow-browser`).
- **Solution**: Pass the required permission flag:
  ```bash
  rush mutation . --allow-slow
  rush e2e . --allow-browser
  rush sbom . -o sbom.json --allow-artifact-write
  ```

### Tool Returns `status: "error"` Due to Malformed Report
- **Cause**: The imported JSON/XML/SARIF report file is corrupted or contains an invalid schema.
- **Solution**: Inspect the report file or re-generate it using the native engine.

### MCP Server Fails to Connect in AI Editor (Cursor/Claude Code)
- **Cause**: The editor launched `rush mcp serve` with an incorrect working directory or missing environment variables.
- **Solution**: In your editor MCP settings, use absolute paths to `uv` and specify the workspace directory explicitly.

---

## 2. Diagnostics Commands

```bash
# Inspect capabilities and discovered engines
rush capabilities . --json

# Run command with verbose logging to stderr
rush review . --verbose
```

See [Troubleshooting Matrix](TROUBLESHOOTING_MATRIX.md) and [User Guide Troubleshooting](user-guide/troubleshooting.md).

## Troubleshooting Context & Ship Errors (Phases 41–43)

### `rush hallu-guard` reports phantom imports
Ensure that the imported package is listed in `pyproject.toml` dependencies and installed in your active virtual environment.

### `rush ship env` reports missing declarations
Add the missing environment variable keys referenced by `os.getenv` into `.env.example`.

### `rush context retrieve` returns chunk not found
Chunks are stored in `.rush/cache/ccr.db`. Ensure the hash is correct and that the cache has not been manually deleted.
