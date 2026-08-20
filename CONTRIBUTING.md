# Contributing to Rush

Thank you for improving Rush. Start with [Contributor onboarding](docs/developer/contributor-onboarding.md) and read the [Developer guide](docs/DEVELOPER_GUIDE.md) before changing a tool, engine, configuration field, CLI option, or MCP schema.

## Setup

```bash
uv sync --all-extras --frozen
unset VIRTUAL_ENV PYTHONPATH
.venv/Scripts/python.exe -m pytest tests/ -q
.venv/Scripts/ruff.exe check src tests
.venv/Scripts/ruff.exe format --check src tests
```

Use `.venv/bin` on macOS/Linux. Use Python 3.12 from the project environment, not an ambient interpreter.

## Contribution rules

- Make one focused, test-first change.
- Preserve catalog/registry/CLI/MCP/configuration parity.
- Keep external engines optional; never add implicit installers.
- Add deterministic native parser fixtures and malformed/missing/timeout evidence.
- Preserve stdout/stderr, redaction, path, and permission boundaries.
- Document honest maturity; do not call a placeholder supported.
- Do not rewrite history, install hooks, create tags, publish, commit, or push without explicit authorization.

## Pull request checklist

```bash
git diff --check
graft --dir .hermes/graft build .
graft --dir .hermes/graft check .
```

Also run full tests, Ruff, format, local Markdown link validation, dependency audit where relevant, and package gates for release-facing changes. Explain the user outcome, safety impact, tests, and any skipped optional-engine evidence in the PR.
