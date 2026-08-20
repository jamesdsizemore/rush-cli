# Alternatives, Comparisons, and Complements

Rush provides a unified, local-first, safe front door across 77 specialized quality engines, linters, security scanners, test runners, and AI evaluators. This document clarifies how Rush compares to and complements adjacent tools in the modern developer ecosystem.

---

## 1. Rush vs. Adjacent Tool Categories

| Tool Category | Examples | Where They Excel | Rush's Distinct Value |
|---|---|---|---|
| **Direct Engine CLI** | Ruff, ESLint, pytest, Semgrep, Trivy, Hadolint | Native CLI flags, auto-fix mutations, deep ecosystem-specific configurations. | Unified `ToolResult` JSON output, offline safety defaults, normalized findings, redacted secrets, single stdio MCP server for AI agents. |
| **Polyglot Linter Orchestrators** | MegaLinter, Super-Linter | Running exhaustive linting pipelines in remote CI containers. | Lightweight local execution, instant startup (<50ms), stdio MCP integration, zero container overhead, dual-mode report imports. |
| **Git Hook Frameworks** | pre-commit, husky, lefthook | Managing Git lifecycle hooks, staged file filters, and auto-stash workflows. | Rush runs as the unified command target inside pre-commit hooks (e.g. `rush lint . --check`), eliminating multi-language hook sprawl. |
| **AI Coding Assistants** | Claude Code, Cursor, Copilot, Hermes | Generating code, refactoring architectures, answering natural language questions. | Rush acts as the local MCP verification backend, giving AI assistants safe, deterministic tools (`rush_review`, `rush_lint`, `rush_security`, `rush_ai-eval`). |
| **Code Knowledge Graphs** | Graft, Sourcegraph, CodeGraph | Tracing symbols, call hierarchies, cross-file references, and code connectivity. | Graft answers "How is this code connected?" while Rush answers "What quality and safety evidence exists?" Rush optionally integrates Graft context (`--use-graft`). |

---

## 2. When to Use Specialized Native Tools Directly

Use native tools directly when:
- You need destructive autofix workflows across entire codebases (`ruff format`, `prettier --write`, `eslint --fix`).
- You need deep interactive debuggers or terminal UIs (`pytest --pdb`, `memray live`).
- You are tuning complex engine-specific rule sets or developing custom OPA policies (`conftest verify`).

---

## 3. When to Use Rush

Use Rush when:
- **Pre-PR Confidence**: Running a single, deterministic check suite across code, infrastructure, security, and tests.
- **AI Agent Tooling**: Giving LLMs and agents a standard Model Context Protocol (MCP) server that prevents infinite loops, transport corruption, and runaway downloads.
- **Polyglot Repositories**: Normalizing findings across Python, TypeScript, Go, Rust, SQL, Kubernetes, Docker, and OpenAPI into one canonical JSON schema.
- **Clean CI Gates**: Exporting consistent `ok`, `warn`, `fail`, `error`, `skipped` exit codes with structured findings and execution metadata.
