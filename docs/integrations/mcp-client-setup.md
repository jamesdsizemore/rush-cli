# Model Context Protocol (MCP) Client Configuration Guide

## Provider-resume setup

No MCP client configuration, OAuth setting, or persistent Rush credential is required for provider continuation. Clients call the local `rush_continuity` tool and must request permission for supported user-owned CLI routes or fixed-loopback API routes. For `9router_cli`, set `RUSH_9ROUTER_API_KEY` only in the MCP server's process environment; Rush copies it only to the one Codex child process and never chooses a model.

`rush agent list/connect/doctor` (Phase 65 [P65-05](../phase-plans/phase-65-project-provisioning-scan-and-agent-workflow-plan.md#p65-05--discoverconnect-every-supported-local-agent-and-activate-memory-f35)) discovers Claude Desktop, Claude Code, Cursor, Windsurf, Zed, and Codex CLI, and registers Rush into each one's own config file without touching any other setting in that file. `rush install --agents all --memory on` ([Phase 65, P65-10](../phase-plans/phase-65-project-provisioning-scan-and-agent-workflow-plan.md#p65-10--one-command-installation-and-readiness-integration-f35-f42)) runs this automatically -- see §0 below. `rush_agent_connection` is registered against `src/rush/mcp.py`, the MCP-exposed equivalent of the CLI command below, wrapping the same `AgentConnectionTool` (`src/rush/tools/agent_connection.py`).

---

## 0. One-command install

Per plan [section 3.1](../phase-plans/phase-65-project-provisioning-scan-and-agent-workflow-plan.md#31-installation-and-connection), a single streamed command downloads the OS/architecture release archive and its checksum manifest, verifies before extraction, installs a self-contained `rush` executable under a user-owned binary directory, and hands off to `rush install --agents all --memory on`:

```sh
curl -fsSL https://raw.githubusercontent.com/jamesdsizemore/rush-cli/main/scripts/install.sh | sh
```

```powershell
irm https://raw.githubusercontent.com/jamesdsizemore/rush-cli/main/scripts/install.ps1 | iex
```

Neither script depends on a source checkout, Python, or `uv`; both work from streamed stdin (no `$PSScriptRoot`/`$0`-relative assumptions). These become valid instructions once a real GitHub release exists -- publishing is authorized separately from this implementation.

`rush install` is also how an existing installation upgrades, repairs, or connects a project directly, with no extra flags required to authorize its own writes:

```bash
rush install --agents all --memory on --project /path/to/your/project
```

- Omitting `--project` completes global setup with project selection pending -- a successful install, not a failed one; the current working directory is never auto-registered.
- `--project <path-or-id>` selects an already-registered project, or registers an unregistered existing folder first (P65-03's own `add`/`select` operations). `--create NAME [--parent DIR]` creates and registers a new folder instead.
- `--agents none` skips agent connection entirely; `--memory off` still connects agents but withholds tool-observation consent. Per-agent state (`active`/`configured`/`restart_required`/`unsupported`) is always reported, and an already-active agent session is left completely untouched by a repeat install.
- A checksum mismatch, a failed extraction, or a newly installed binary that fails to start all leave the previous working executable exactly as it was -- nothing below the binary (agent config, project registry) is ever touched until the new binary is verified to actually run.

---

## 1. FastMCP Transport Architecture

Rush runs as a dedicated local child process using the Model Context Protocol over standard input/output (`stdio`).

```text
AI Coding Assistant (Client)
       │ (JSON-RPC requests over stdin)
       ▼
rush mcp serve (Server)
       │ (Detached subprocesses with stdin=DEVNULL)
       ├── rush_review, rush_lint, rush_security, rush_ai_eval, etc.
       ▼
JSON-RPC responses on stdout (Diagnostics on stderr)
```

---

## 2. Generated Config: What `rush agent connect` Writes

Running `rush agent connect <agent-id> --session <id> --allow-cache-write --allow-artifact-write`
resolves the *installed* Rush executable's absolute path (never this repo's own checkout, never a
project-local `.venv`/uv dependency) and writes exactly that path as `command`. Every unrelated key,
comment, and sibling server entry already in the file is left byte-for-byte untouched -- only the
`rush` entry's own value is added or replaced. A timestamped backup of the original file is written
next to it before any edit. The examples below show the config each supported client ends up with;
if you are still on the manual editable-source install described in §1, use `uv run --directory
<path-to-checkout> rush mcp serve` as `command`/`args` instead of the absolute installed path.

### Claude Desktop (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "rush": {
      "command": "/usr/local/bin/rush",
      "args": ["mcp", "serve"]
    }
  }
}
```
macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`. Windows:
`%APPDATA%\Claude\claude_desktop_config.json`. Linux (unofficial): `~/.config/Claude/claude_desktop_config.json`.
Claude Desktop must be **restarted** to pick up a config change.

### Claude Code (`~/.claude.json`)
```json
{
  "mcpServers": {
    "rush": {
      "command": "/usr/local/bin/rush",
      "args": ["mcp", "serve"]
    }
  }
}
```
`rush agent connect claude-code` prefers Claude Code's own native `claude mcp add`/`claude mcp remove`
commands (idempotent: remove-then-add) when the `claude` executable is on `PATH`, falling back to the
same format-preserving JSON edit otherwise. No restart needed -- Claude Code re-reads this file per
invocation.

### Cursor IDE (`~/.cursor/mcp.json`)
```json
{
  "mcpServers": {
    "rush": {
      "command": "/usr/local/bin/rush",
      "args": ["mcp", "serve"]
    }
  }
}
```
Restart Cursor after connecting.

### Windsurf (`~/.codeium/windsurf/mcp_config.json`)
```json
{
  "mcpServers": {
    "rush": {
      "command": "/usr/local/bin/rush",
      "args": ["mcp", "serve"]
    }
  }
}
```
Restart Windsurf after connecting.

### Zed Editor (`~/.config/zed/settings.json`)
```jsonc
{
  // any existing settings and comments are preserved exactly
  "context_servers": {
    "rush": {
      "command": {
        "path": "/usr/local/bin/rush",
        "args": ["mcp", "serve"]
      }
    }
  }
}
```
Zed's `settings.json` allows comments (JSONC); `rush agent connect` edits only the `rush` entry's own
byte range so existing comments elsewhere survive. Restart Zed after connecting.

### Codex CLI (`~/.codex/config.toml`)
```toml
[mcp_servers.rush]
command = "/usr/local/bin/rush"
args = ["mcp", "serve"]
```
No restart needed -- Codex CLI re-reads `config.toml` per invocation.

---

## 3. Discovery, Reconnecting, and Memory Scope/Consent

- `rush agent list` reports every supported client's exact state: `not_detected` (client not
  installed or never configured), `detected` (config file exists, no Rush entry yet), `registered`
  (Rush entry present and pointing at the resolved binary), `misconfigured` (a Rush entry exists but
  points somewhere else -- typically a stale dev-checkout path), `malformed` (the config file itself
  cannot be safely parsed), or `read_only` (the config file exists but Rush cannot write to it). A
  failure on one client is always reported against that client alone; it never marks a different
  client as failed or connected.
- **Reconnecting**: re-running `rush agent connect <agent-id>` is always safe -- it repairs a
  `misconfigured` entry and repeats a `registered` one without ever creating a second Rush entry in
  the same file.
- **Scope**: connection activates Phase 63 memory observation under an explicit
  `(user-or-project, session, agent)` scope. Pass `--project <path>` to bind observation to that
  project only; omit it for a user-scoped connection independent of any project. Two different
  projects, or two different agents in the same project, never share or overwrite each other's
  observation state.
- **Consent**: pass `--consent` to allow Rush to record real tool-observation payloads for that
  scope; without it, the connection is registered but no observation content is ever captured.
- **Acknowledgment**: a connection only reports `connected: true` after `--acknowledge` is passed
  (either on `connect` itself once you have verified the client picked it up, or the same effect via
  a later `rush agent doctor`) -- writing the config file is necessary but not sufficient for
  `connected` to be true.
- `rush agent doctor [--session <id>] [--project <path>]` re-probes every client's real on-disk
  config and reports the memory scope's current state for that session, without writing anything.

---

## 4. Verification Protocol

1. Start your MCP client.
2. Verify tools from the live server appear with the `rush_` prefix. The generated catalog is authoritative; do not use a copied fixed list as completeness evidence.
3. Invoke `rush_review` with an absolute project path and verify structured `ToolResult` JSON output.

See [MCP Overview](mcp-overview.md) and [MCP Reference](../reference/mcp-tool-reference.md).
