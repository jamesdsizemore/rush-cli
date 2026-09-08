# Install Rush

Rush is a Python 3.12 command-line application. Current installation is an editable source checkout managed by [uv](https://docs.astral.sh/uv/). A standalone, package-manager, and clean-machine installer is planned in [Phase 65, P65-01](../phase-plans/phase-65-project-provisioning-scan-and-agent-workflow-plan.md#p65-01--verified-standalone-release-artifacts-f28).

## Before you begin

You need Git, Python 3.12 or newer, and uv. You do **not** need every optional quality tool. Rush reports a missing optional checker as `skipped` and tells you what is unavailable.

## Windows

1. Install Git for Windows.
2. Install uv using the current official uv instructions.
3. Open Git Bash or a terminal and run:

```bash
git clone https://github.com/jamesdsizemore/rush-cli.git
cd rush-cli
uv sync --all-extras --frozen
uv run rush --version
```

Expected success: a Rush version such as `rush, version 0.1.0` and exit code 0.

If Windows launches the wrong Python, use `uv run rush ...` from the checkout. For contributor tests, clear `VIRTUAL_ENV` and `PYTHONPATH`; see [Contributor onboarding](../developer/contributor-onboarding.md).

## macOS

Install Git and uv, then:

```bash
git clone https://github.com/jamesdsizemore/rush-cli.git
cd rush-cli
uv sync --all-extras --frozen
uv run rush --help
```

Run Rush as `uv run rush` from this checkout. Current setup does not install a standalone `rush` command on `PATH`.

## Linux

Use your distribution's Git package and the official uv installer:

```bash
git clone https://github.com/jamesdsizemore/rush-cli.git
cd rush-cli
uv sync --all-extras --frozen
uv run rush review .
```

## Standalone and package-manager installation

**Status: planned — implementation [P65-01](../phase-plans/phase-65-project-provisioning-scan-and-agent-workflow-plan.md#p65-01--verified-standalone-release-artifacts-f28).** Current Homebrew, Scoop, Winget, wheel, and archive assets are not verified installation routes. Use the editable source checkout above. Phase 65 retains the accepted cross-platform installer requirement and its clean-OS verification gates.

## Optional quality tools

Install only the helpers your project needs. For example:

```bash
# Python project
uv add --dev ruff pytest pip-audit mypy

# JavaScript/TypeScript project
npm install --save-dev eslint prettier vitest typescript
```

Current `rush setup` does not provide a verified installer for these dependencies. Install chosen helpers yourself. See the [engine directory](../reference/engine-directory.md) for supported helpers and prerequisites. Integrated detection, installation, readiness, and agent connection remain planned in [Phase 65, P65-02 through P65-10](../phase-plans/phase-65-project-provisioning-scan-and-agent-workflow-plan.md).

## Corporate proxy and offline environments

Rush has no custom proxy or package mirror implementation. Configure Git, uv, pip, npm, and each external engine according to your organization's approved mirrors. A fully offline run requires Rush and every chosen engine to be installed in advance. Do not infer that a command is offline-safe merely because Rush itself opens no service; some external scanners have their own data requirements.

## Recovery checklist

- `uv: command not found`: install uv and start a new terminal.
- Wrong Python: run `uv python install 3.12`, then `uv sync --all-extras --frozen`.
- `rush: command not found`: use `uv run rush` from the checkout.
- A check says `skipped`: read its summary and install only that optional engine if you need the check.
- MCP client cannot start Rush: use an absolute checkout path and the template in [MCP client setup](../integrations/mcp-client-setup.md).

Next: [Your first run](first-run.md).
