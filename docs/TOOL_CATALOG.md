# Tool catalog

The catalog in `src/rush/catalog.py` is the shared source for CLI help, stdio
MCP registration, configuration validation, and engine metadata.

Core tools: `review`, `lint`, `format`, `test`, `security`.

Expanded quality tools include `typecheck`, `dead`, `complexity`, `coverage`,
`e2e`, `mutation`, `fuzz`, and content/infrastructure/supply-chain tools.
Workflow tools are non-mutating: `commit-msg`, `ci`, and `release`.

`semantic-drift` is experimental and skipped by default. Every external engine
is optional; missing engines return `skipped`, not an installation action.
