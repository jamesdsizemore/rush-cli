# CI overview

Use Rush in CI to standardize results, not to install every possible language runtime.

## Bounded-engine strategy

1. Identify the repository's languages and required evidence.
2. Pin Rush and only those external engines.
3. Run focused commands with `--json`.
4. Treat mandatory `skipped` as a policy failure by inspecting JSON.
5. Keep broad adapter correctness in fixture tests; run a representative real-engine subset in CI.

Rush's own workflow uses a locked Python environment for Ruff, tests, dependency audit, whitespace, and package build, plus a bounded Python-engine contract job. See [GitHub Actions](github-actions.md).
