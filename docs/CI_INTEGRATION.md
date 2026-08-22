# Continuous Integration (CI) Integration Guide

Rush is built for deterministic execution in Continuous Integration pipelines. It runs fast, generates standardized `ToolResult` JSON output, and isolates environment side effects.

---

## 1. Core CI Strategy

1. **Pin Rush & Explicit Engines**: Install only the engines required for your repository's stack (e.g. `ruff`, `eslint`, `actionlint`, `semgrep`).
2. **Deterministic Parity**: Ensure CI runs the exact same checks as developers execute locally before opening PRs.
3. **Machine-Readable Gates**: Inspect `status` inside `--json` output rather than relying solely on process exit codes (since `skipped` intentionally exits with code 0).
4. **Offline Safety**: Rush runs engines offline by default. CI never performs unexpected remote downloads or registry calls without explicit `--allow-*` permissions.

---

## 2. GitHub Actions Integration

Create `.github/workflows/rush.yml`:

```yaml
name: Rush Quality Gate

on:
  pull_request:
  push:
    branches: [main]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Set up uv
        uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true

      - name: Install Dependencies
        run: uv sync --all-extras --frozen

      - name: Run Rush Review & Lint
        run: |
          uv run rush review . --json > review.json
          uv run rush lint . --check --json > lint.json
          uv run rush format . --check --json > format.json

      - name: Run Security & Secret Scanners
        run: |
          uv run rush security . --json > security.json
          uv run rush secrets . --json > secrets.json

      - name: Run Test Suite
        run: uv run rush test . --json > test.json

      - name: Verify No Policy Skips or Failures
        run: |
          python -c '
          import json, sys, glob
          for path in glob.glob("*.json"):
              with open(path) as f:
                  data = json.load(f)
                  status = data.get("status")
                  if status in ("fail", "error"):
                      print(f"[FAIL] {path}: {data.get(\"summary\")}")
                      sys.exit(1)
          print("[PASS] All Rush CI gates passed cleanly.")
          '
```

---

## 3. GitLab CI Integration

```yaml
stages:
  - quality

rush_checks:
  stage: quality
  image: python:3.12-slim
  before_script:
    - pip install uv
    - uv sync --frozen
  script:
    - uv run rush review . --json
    - uv run rush lint . --check --json
    - uv run rush security . --json
    - uv run rush test . --json
```

---

## 4. Advanced Test Evidence in CI

For advanced quality verification (coverage, mutation, contracts, AI eval), use dual modes:
- **Import Mode**: Generate coverage XML or JUnit reports in existing pipeline steps, then pass the report path to `rush coverage report.xml --json` for standardized normalization.
- **Execution Mode**: Pass explicit permission flags in designated long-running or nightly CI workflows (`rush ai-eval . --allow-slow --json`, `rush load load.js --allow-network --json`).

See the [CI Overview](integrations/ci-overview.md), [GitHub Actions Guide](integrations/github-actions.md), and [Scripts Guide](integrations/scripts-and-automation.md).

## CI Pre-Flight Gate Integration (Phases 41–43)

Add `rush ship gate` and `rush hallu-guard` to your GitHub Actions pipeline:

```yaml
- name: Rush Grounding & Ship Gate
  run: |
    rush hallu-guard
    rush ship gate
```

### Architectural Boundary CI Gate
```yaml
- name: Architecture Boundary Check
  run: rush arch-guard
```


### API Breaking Change CI Gate
```yaml
- name: API Breaking Change Check
  run: rush api-diff --base origin/main
```



### Database Drift CI Gate
```yaml
- name: DB Migration Drift Check
  run: rush db-drift
```

