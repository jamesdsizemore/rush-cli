# Contributor onboarding

## Clone and install

```bash
git clone https://github.com/jamesdsizemore/rush-cli.git
cd rush-cli
uv sync --all-extras --frozen
```

Run the full loop from [Developer guide](../DEVELOPER_GUIDE.md). Do not use a global interpreter for evidence.

## Windows

Use Git Bash commands or the equivalent shell, but invoke the project executables explicitly:

```bash
unset VIRTUAL_ENV PYTHONPATH
.venv/Scripts/python.exe -m pytest tests/ -q
.venv/Scripts/ruff.exe check src tests
```

A globally set `PYTHONPATH` can load incompatible packages. If an engine is not found, compare `PATH` inside the shell/client that launches Rush.

## macOS and Linux

```bash
unset VIRTUAL_ENV PYTHONPATH
.venv/bin/python -m pytest tests/ -q
.venv/bin/ruff check src tests
```

## First change

Choose one bounded issue, write or update the narrow failing test, make the minimum change, run focused tests, then full gates. Never install every optional external engine to make fixture tests pass; installed-engine tests are marked and bounded.
