# Ecosystem Integrations Hub

## Coding-provider continuity

Implemented continuation integrations are user-owned Claude Code, Codex, and Antigravity (`agy`) CLIs plus OmniRoute's fixed localhost OpenAI-compatible API. Z.AI is deferred. 9Router is a CLI/gateway whose actual continuation route still needs its explicit API key and selected model.

Rush integrates cleanly into your existing developer workflows, AI coding assistants, continuous integration pipelines, and editor task runners.

---

## 1. AI Coding Assistants & MCP Clients

Rush acts as a local Model Context Protocol (MCP) server over standard input/output (`stdio`), providing assistants with 34 deterministic verification tools:

- **Claude Desktop & Claude Code**: Configure `rush mcp serve` in `claude_desktop_config.json`.
- **Cursor & Windsurf**: Configure `rush mcp serve` in `.cursor/mcp.json` or editor settings.
- **Zed & Hermes**: Connect directly using stdio context server definitions.

See [MCP Overview](integrations/mcp-overview.md) and [MCP Client Setup Guide](integrations/mcp-client-setup.md).

---

## 2. Continuous Integration (CI)

Rush unifies multiple language linters, security scanners, and test suites into clean, single-step CI jobs:

- **GitHub Actions**: `.github/workflows/rush.yml`
- **GitLab CI**: `.gitlab-ci.yml`
- **CircleCI & Bitbucket Pipelines**: Custom docker/system runner steps.

See [CI Overview](integrations/ci-overview.md) and [GitHub Actions Guide](integrations/github-actions.md).

---

## 3. Editor & IDE Tasks

Run Rush directly from VS Code, JetBrains IDEs, Neovim, or Emacs without leaving your editor:

- **VS Code Tasks**: `.vscode/tasks.json`
- **JetBrains External Tools**: PyCharm, IntelliJ, WebStorm
- **Neovim & Vim**: Lua / Vimscript command mappings

See [Editor Integration Guide](EDITOR_INTEGRATION.md).

---

## 4. Git Hooks & Local Automation

Enforce code quality and documentation parity automatically on every commit:

- **Git Pre-Commit Hook**: Configured in `.githooks/pre-commit` to prevent unverified commits.
- **Shell Automation**: Standardized JSON piping and exit status verification.

See [Scripts & Automation Guide](integrations/scripts-and-automation.md) and [Pre-Commit Guide](PRE_COMMIT.md).
