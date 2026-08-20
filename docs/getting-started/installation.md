# Install Rush

Rush is a Python 3.12 command-line application. The recommended development and source-install workflow uses [uv](https://docs.astral.sh/uv/), a Python package and environment manager.

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

If `rush` is not on `PATH`, continue using `uv run rush`, or install the built wheel into an isolated uv tool environment.

## Linux

Use your distribution's Git package and the official uv installer:

```bash
git clone https://github.com/jamesdsizemore/rush-cli.git
cd rush-cli
uv sync --all-extras --frozen
uv run rush review .
```

## Install from a wheel

A release or local build may provide a `.whl` file. Install it into an isolated environment rather than a system Python:

```bash
uv tool install /absolute/path/to/rush-0.1.0-py3-none-any.whl
rush --version
```

Rush is not documented as a published package until a release artifact is actually available. Building from source is covered in [CI and packaging](../developer/ci-and-packaging.md).

## Optional quality tools

Install only the helpers your project needs. For example:

```bash
# Python project
uv add --dev ruff pytest pip-audit mypy

# JavaScript/TypeScript project
npm install --save-dev eslint prettier vitest typescript
```

Rush never performs these installs. See the [engine directory](../reference/engine-directory.md) for every supported helper.

## Corporate proxy and offline environments

Rush has no custom proxy or package mirror implementation. Configure Git, uv, pip, npm, and each external engine according to your organization's approved mirrors. A fully offline run requires Rush and every chosen engine to be installed in advance. Do not infer that a command is offline-safe merely because Rush itself opens no service; some external scanners have their own data requirements.

## Recovery checklist

- `uv: command not found`: install uv and start a new terminal.
- Wrong Python: run `uv python install 3.12`, then `uv sync --all-extras --frozen`.
- `rush: command not found`: use `uv run rush` from the checkout.
- A check says `skipped`: read its summary and install only that optional engine if you need the check.
- MCP client cannot start Rush: use an absolute checkout path and the template in [MCP client setup](../integrations/mcp-client-setup.md).

Next: [Your first run](first-run.md).
