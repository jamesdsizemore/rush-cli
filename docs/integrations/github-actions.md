# GitHub Actions

A minimal repository job can install Rush and selected engines, then run checks:

```yaml
name: Rush
on: [pull_request]
permissions:
  contents: read
jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: uv sync --frozen
      - run: uv run rush lint . --json
      - run: uv run rush format . --check --json
      - run: uv run rush test . --json
```

Pin action versions according to your organization's policy. The snippet is a pattern, not the Rush repository's exact pinned workflow.

Because `skipped` exits 0, add a small JSON policy step when an engine is mandatory. Never install every Rush engine into one CI image merely because it appears in the catalog. Avoid advanced permission-sensitive actions in unattended CI until their explicit surfaces are implemented and approved.
