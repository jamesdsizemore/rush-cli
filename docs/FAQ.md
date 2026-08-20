# Frequently Asked Questions (FAQ)

Comprehensive answers to common architectural, operational, and user questions about Rush CLI and its Model Context Protocol (MCP) server.

---

### What is Rush?
Rush is a local-first CLI and stdio-only MCP server that provides a unified, deterministic interface across 77 specialized quality engines, security scanners, linters, test runners, and AI safety evaluators.

### Does Rush replace tools like Ruff, ESLint, Semgrep, or pytest?
No. Rush does not replace native quality engines. Instead, it acts as a safe, normalized front door that discovers existing tools on your `PATH`, runs them with isolated subprocess safety, normalizes findings to a canonical schema, and serves them to developers and AI coding agents.

### Does Rush install missing tools automatically?
No. Rush follows a strict no-implicit-install policy. When an optional engine is absent from your environment, Rush returns a structured `status: "skipped"` with an install hint (e.g. `npm install -D eslint` or `pip install semgrep`).

### How does Rush protect AI coding agents from crashing?
Rush runs as a dedicated stdio MCP server (`rush mcp serve`). It strictly isolates child process execution using `stdin=subprocess.DEVNULL`, so external CLI tools can never consume or corrupt MCP JSON-RPC protocol frames. All diagnostics are emitted to `stderr`, leaving `stdout` pure for JSON-RPC.

### How are secrets handled?
All findings and logs passed through Rush are normalized and automatically redacted. Credentials, private keys, high-entropy tokens, and passwords discovered by engines like TruffleHog or Gitleaks are replaced with `[REDACTED]` in output.

### What are the permission flags?
Rush enforces explicit execution permissions for potentially slow, heavy, or mutating operations:
- `--allow-network`: Live network communication (e.g. k6 load tests, URL link checks).
- `--allow-download`: Fetching vulnerability databases or schemas.
- `--allow-cache-write`: Writing engine rule caches.
- `--allow-build`: Compiling code or CodeQL analysis databases.
- `--allow-slow`: Long-running test, mutation, or fuzz runs.
- `--allow-artifact-write`: Overwriting or mutating baseline artifacts and report files.
- `--allow-browser`: Launching browser engines (Playwright, Chromium/WebKit/Firefox).

### Does `rush review --llm` send code to external AI providers?
No. In the current release, `rush review --llm` is a development stub that returns deterministic placeholder information and makes zero outbound network or API calls. Default review uses fast, deterministic local heuristics.

For more questions, see the [User Guide FAQ](user-guide/faq.md) and [Troubleshooting Guide](user-guide/troubleshooting.md).
