# Rush

**Agentic code-quality tools for coding agents.** Rush is a Python CLI and MCP server that gives AI coding agents (and you) a fast, local way to review, lint, format, test, and secure a codebase — plus token-saving context tools built for how agents actually work.

[![Release](https://img.shields.io/github/v/release/jamesdsizemore/rush-cli?style=flat-square&color=00ffff&label=release)](https://github.com/jamesdsizemore/rush-cli/releases)
[![Python 3.12](https://img.shields.io/badge/python-3.12-3776AB.svg?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![MCP: stdio](https://img.shields.io/badge/MCP-stdio%20server-00ffff.svg?style=flat-square&logo=anthropic&logoColor=white)](https://modelcontextprotocol.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json&style=flat-square)](https://github.com/astral-sh/ruff)

<p align="center">
  <img src="https://skillicons.dev/icons?i=py,rust,ts,docker,githubactions,sqlite,git,postgres,graphql&theme=dark" alt="Supported languages and ecosystems" />
</p>

[Install](#install) · [Quickstart](#quickstart) · [Connect an AI agent](#connect-an-ai-agent-mcp) · [What it does](#what-it-does) · [Configuration](#configuration) · [Contributing](#contributing)

---

## Why Rush

AI coding agents move fast and occasionally make a mess: hallucinated imports, empty placeholder functions, huge test-failure traces that blow your context budget, and the occasional overconfident `rm -rf`. Rush sits between you and that mess — a local-first toolbelt an agent (or you, from the terminal) can call before anything ships:

- **Catch it before it ships** — deterministic AST review, linting, formatting, and test running across Python and JS/TS, dispatched to real engines (Ruff, ESLint, Biome, pytest, and more).
- **Keep agents on a leash** — a command-safety firewall that blocks destructive shell commands, isolated git worktrees for patch attempts, and a failure ledger so agents stop repeating the same broken fix.
- **Give agents a real memory** — a typed, queryable store per project (not a stuffed context window) that survives across sessions and agents, with a trust gate so nothing gets treated as fact until it's corroborated.
- **Stop burning tokens** — context packing, AST skeletons, and compact result formats so you're not pasting whole files and 10,000-line stack traces into a chat window.
- **Talk to your agent directly** — a stdio MCP server so Claude Code, Cursor, Windsurf, Zed, and other MCP-capable agents can call Rush's tools natively, not just from a shell.

Rush runs entirely on your machine. It doesn't upload your code anywhere, and it doesn't install anything in the background — it drives quality/security engines that are already on your `PATH`.

---

## Install

The fastest way to get `rush` on your machine is the install script — it downloads a checksum-verified, self-contained binary. No Python, no `uv`, no repo checkout required.

**macOS / Linux:**
```sh
curl -fsSL https://raw.githubusercontent.com/jamesdsizemore/rush-cli/main/scripts/install.sh | sh
```

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/jamesdsizemore/rush-cli/main/scripts/install.ps1 | iex
```

This installs `rush` to a user-owned directory, adds it to your shell (or tells you how to), and automatically connects any supported coding agent it finds on your machine (Claude Desktop, Claude Code, Cursor, Windsurf, Zed, Codex CLI). Once installed, re-run the `rush install` command directly any time you want different flags, upgrade, repair, or connect a specific project:

```bash
# Skip agent connection / memory consent entirely
rush install --agents none --memory off

# Connect a specific project instead of leaving selection pending
rush install --agents all --memory on --project /path/to/your/project
```

> **Windows on ARM64** isn't available yet — a dependency (`cryptography`) doesn't currently publish a prebuilt wheel for that platform. Every other combination (macOS Intel/Apple Silicon, Linux x86_64/ARM64, Windows x86_64) is fully supported.

**Verify it worked:**
```bash
rush --version
rush doctor      # checks your environment and toolchain health
```

<details>
<summary><strong>Prefer to build from source? (uv or pip)</strong></summary>

```bash
git clone https://github.com/jamesdsizemore/rush-cli.git
cd rush-cli

# with uv (recommended for development)
uv sync --all-extras --frozen
uv run rush --version

# or with pip
python -m venv .venv
source .venv/bin/activate   # .venv\Scripts\activate on Windows
pip install -e ".[dev]"
```
</details>

---

## Quickstart

```bash
# Set up a project: writes a rush.toml tailored to your stack
rush init .

# Sync one set of rules to every IDE/agent config you use
rush governance sync

# Review the codebase — deterministic AST checks, no network calls
rush review .

# Preview safe auto-fixes (formatting + lint) without touching files
rush fix . --dry-run

# Run the full pre-flight release gate: tests, coverage, lint, security, drift
rush ship gate
```

Every command prints a consistent result — status, findings, and a one-line summary — whether you're reading it in a terminal or an agent is parsing it as JSON (`--json` on most commands).

---

## Connect an AI agent (MCP)

Rush speaks [MCP](https://modelcontextprotocol.io) over stdio, so any MCP-capable agent can call its tools directly instead of shelling out.

**Claude Desktop** — add to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "rush": {
      "command": "rush",
      "args": ["mcp", "serve"]
    }
  }
}
```

**Cursor** (`~/.cursor/mcp.json`) and **Windsurf** (`~/.codeium/windsurf/mcp_config.json`) use the same shape:
```json
{
  "mcpServers": {
    "rush": {
      "command": "rush",
      "args": ["mcp", "serve"]
    }
  }
}
```

If your client can't resolve `rush` from `PATH`, point `command` at the absolute path `rush doctor` reports. For every other client, see the [MCP client setup guide](docs/integrations/mcp-client-setup.md). The full tool list — schemas included — is always available live from the running server (`tools/list`) and documented in the [MCP reference](docs/MCP_REFERENCE.md); a few of the most-used tools:

| Tool | What it does |
|---|---|
| `rush_context_pack` | Packs the relevant symbols and AST skeletons for a task into a token budget |
| `rush_blast_radius` | Reports what a change would affect — files, routes, tests |
| `rush_hallu_guard` | Checks that an agent's proposed imports actually exist in the codebase |
| `rush_context_mistakes_check` | Looks up whether a similar approach already failed before |
| `rush_mesh_acquire_lock` / `rush_mesh_release_lock` | Cooperative file locks for multiple agents working the same repo |
| `rush_test_heal` | Investigates a flaky test in an isolated sandbox |

---

## What it does

Rush ships as one CLI with a lot of focused tools behind it (`rush --help` for the full list). Grouped by what you'd actually reach for:

**Code quality**
`review` · `lint` · `format` · `fix` · `typecheck` · `dead` · `complexity` · `simplify` · `slop` (AI hallucination/placeholder detector) · `tdd`

**Testing**
`test` · `e2e` · `mutation` · `pbt` (property-based) · `flaky` · `coverage` · `contract` · `fuzz` · `load` · `test-heal`

**Security & supply chain**
`security` (dependency vulnerabilities) · `secrets` (with automatic redaction) · `sbom` · `codeql` · `attest` (draft SLSA provenance) · `license-matrix` · `iam-audit`

**Agent safety**
`guard` (blocks destructive commands like `git reset --hard`/`rm -rf`) · isolated git-worktree sandboxes for patch attempts · `swarm-merge` (3-way AST merge for concurrent agents) · a failure ledger that stops agents from retrying known-bad fixes

**Memory**
`memory write` / `recall` / `ask` — a typed store (`.rush/memory.db`, one per project, WAL-mode SQLite) across 7 kinds: episodic, preference, failure, architectural decisions, domain knowledge, skill patterns, and active context. Nothing an agent writes is trusted outright — `memory promote` runs it through a corroboration gate that also screens for instruction-override/exfiltration patterns before anything is treated as fact. `context mistakes` mines actual git-revert history so an agent doesn't retry a fix that was already tried and reverted. `session save`/`restore` and `continuity` checkpoint a working session and resume it later. The `rush_memory` MCP tool bridges a bounded handoff between agents instead of each one keeping its own siloed context.

Static analysis feeds directly into it: `memory plan-checks` ranks which checks actually matter for a change using real evidence pulled from memory — a prior test that failed against this exact code, measured coverage, a `blast-radius`/`api-diff` structural relation, a version-bound security finding — never a fabricated "this is covered" from a check that only ever ran in config. `memory last-success-diagnose` compares a current failure against the last time this code path actually passed. Scan results themselves become typed memory artifacts on handoff, so a finding an agent hands off is a durable, queryable record, not just terminal output that evaporates.

**Token economy & context**
`context pack` (AST-aware, budget-constrained context) · `context align-prompt` (prompt-cache-friendly formatting) · `context gain` (live token/cost savings HUD) · `token count` · `blast-radius`

**Governance & multi-IDE**
`governance sync` — compile one `AGENTS.md` into `.cursorrules`, `.windsurfrules`, `.clinerules`, and Claude Code config in one command

**Dashboards**
`dashboard` — a local, authenticated web UI · `ui` — the same views as a terminal app (Rich TUI), both backed by the same project data (scans, findings, memory, token use, git history)

Every one of these has real engines behind it where a standard tool exists (Ruff, ESLint, pytest, Gitleaks, Syft, and dozens more) and a deterministic built-in fallback where it doesn't. `rush capabilities .` shows exactly what's usable in your environment before you run anything. A couple of honest gaps: `rush hook run` exists today, but `hook install`/`hook verify` aren't wired up yet, and `dead-asset` reports candidates without a `--prune` flag to delete them for you.

---

## Configuration

Rush reads `rush.toml` from your project root — `rush init .` generates one tailored to your stack. Everything is optional; sensible defaults apply if you skip it:

```toml
log_level = "warn"

[project]
src = ["src"]
test = ["tests"]
exclude = ["**/.venv/**", "**/node_modules/**"]

[review]
max_file_lines = 400
scaffold_markers = ["TODO", "FIXME", "HACK"]

[tools.lint]
check = true
```

Full field reference: [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md).

---

## Safety notes

- Rush never installs packages or runs network calls on its own — quality/security engines are discovered from your `PATH`; you decide what's installed.
- Destructive git operations (rewriting history, force-pushing, tagging, publishing) never happen implicitly — only when you explicitly ask.
- The stdio MCP server keeps `stdout` reserved for JSON-RPC; all logging goes to `stderr`.
- Full threat model and guarantees: [`docs/SAFETY.md`](docs/SAFETY.md).

---

## Contributing

1. `uv run --python 3.12 --extra dev ruff check src tests scripts` and `ruff format --check` should both pass.
2. New engines/tools need tests under `tests/test_<name>.py`.
3. See [`docs/developer/contributor-onboarding.md`](docs/developer/contributor-onboarding.md) for the full guide.

## License

[MIT](LICENSE)
