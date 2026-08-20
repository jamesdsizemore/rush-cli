# Tutorial: Adding Rush to Continuous Integration

**Goal:** Create a robust, locked CI workflow that runs Rush checks on pull requests with zero dependency drift.

---

## 1. Quick GitHub Actions Setup

Create `.github/workflows/rush-ci.yml`:

```yaml
name: Rush CI Gate

on:
  pull_request:
  push:
    branches: [main]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Setup uv
        uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true

      - name: Install Pinned Dependencies
        run: uv sync --all-extras --frozen

      - name: Run Rush Checks
        run: |
          uv run rush review . --json
          uv run rush lint . --check --json
          uv run rush format . --check --json
          uv run rush security . --json
          uv run rush test . --json
```

---

## 2. Policy Assertion for Mandatory Checks

Ensure that mandatory checks did not skip due to a missing engine:

```bash
uv run rush security . --json | python -c "
import json, sys
res = json.load(sys.stdin)
if res.get('status') == 'skipped':
    print('Error: Security scanner was skipped in CI!')
    sys.exit(1)
"
```

See [CI Overview](../integrations/ci-overview.md) and [GitHub Actions Guide](../integrations/github-actions.md).
