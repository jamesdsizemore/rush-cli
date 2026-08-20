# Rush Scope & Architectural Boundaries

This document defines what is explicitly in-scope and out-of-scope for Rush CLI and its Model Context Protocol (MCP) server.

---

## 1. Explicitly In-Scope

- **Unified CLI & MCP Front Door**: Exposing 34 canonical commands and FastMCP tools (`rush_<name>`) with identical implementations.
- **Dynamic Engine Discovery**: Discovering 77 external engines from the environment with non-fatal `skipped` reporting for absent tools.
- **Normalized Canonical Findings**: Returning stable SHA-256 fingerprints, file coordinates, and standardized severity across all linters, security scanners, and test runners.
- **Automated Secret Redaction**: Masking tokens, passwords, and private keys as `[REDACTED]` in output.
- **Execution Permission System**: Gating slow, network, download, build, browser, and artifact-write operations behind explicit invocation flags (`--allow-*`).
- **Subprocess Isolation**: Executing external tools with `stdin=DEVNULL`, `shell=False`, and timeout limits to safeguard MCP stdio transports.
- **Dual-Mode Operation**: Importing structured reports (JSON/XML/SARIF) or executing live engine runners.

---

## 2. Explicitly Out-of-Scope

- **Engine Bundling**: Rush does not bundle external binaries (Node.js, Go, Rust, Java, or C++ executables) or download them at runtime.
- **Remote Network Daemon**: Rush is not an HTTP API, background daemon, or hosted service. MCP communication occurs strictly over local stdio pipes.
- **Destructive Auto-Fixing by Default**: Inspection commands are read-only. Formatting without `--check` is an intentional, explicit action.
- **Automated Git Mutation**: Rush does not commit, create Git tags, rewrite history, or push branches to remote repositories.

See [v0.2 Scope Specification](V0_2_SCOPE.md) and [Design Principles](DESIGN_PRINCIPLES.md).
