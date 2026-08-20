# GitHub Actions Integration Guide

Complete GitHub Actions workflow configuration patterns for Rush CLI.

---

## 1. Complete Multi-Stage Quality Workflow

Create `.github/workflows/quality.yml`:

```yaml
name: Quality & Security Gate

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  rush-quality:
    name: Rush Checks
    runs-on: ubuntu-latest

    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true

      - name: Install Dependencies
        run: uv sync --all-extras --frozen

      - name: TDD Guard
        run: uv run rush tdd . --json > tdd_results.json

      - name: Code Review Heuristics & Reports
        run: |
          uv run rush review . --export-html review.html --export-sarif review.sarif --json > review_results.json
          uv run rush security . --export-sarif security.sarif --json > security_results.json

      - name: Upload Security SARIF to GitHub Code Scanning
        uses: github/codeql-action/upload-sarif@v3
        if: always()
        with:
          sarif_file: security.sarif
          category: rush-security

      - name: Upload Review HTML Artifact
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: rush-review-report
          path: review.html

      - name: Linting & AST Analysis
        run: uv run rush lint . --check --json > lint_results.json

      - name: Modular Architecture & Slop Audits
        run: |
          uv run rush complexity . --json > complexity_results.json
          uv run rush slop . --json > slop_results.json

      - name: Formatting Compliance
        run: uv run rush format . --check --json > format_results.json

      - name: Secret Audits
        run: uv run rush secrets . --json > secrets_results.json

      - name: Unit Tests
        run: uv run rush test . --json > test_results.json

      - name: Enforce Zero Failures or Errors
        run: |
          python -c '
          import json, sys, glob
          failed = False
          for report in glob.glob("*_results.json"):
              with open(report) as f:
                  res = json.load(f)
                  if res.get("status") in ("fail", "error"):
                      print(f"❌ {report}: {res.get(\"summary\")}")
                      failed = True
                  else:
                      print(f"✅ {report}: {res.get(\"summary\")}")
          if failed:
              sys.exit(1)
          '
```

---

## 2. Advanced Workflows (Nightly Mutation & Browser E2E)

Create `.github/workflows/nightly.yml`:

```yaml
name: Nightly Deep Verification

on:
  schedule:
    - cron: "0 2 * * *" # Every night at 2:00 AM UTC
  workflow_dispatch:

jobs:
  deep-checks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --all-extras --frozen

      - name: Polyglot Mutation Testing
        run: uv run rush mutation . --allow-slow --json

      - name: Playwright Browser E2E
        run: |
          npx playwright install --with-deps
          uv run rush e2e . --allow-browser --json

      - name: LLM Prompt Evaluation & Safety Guardrails
        run: uv run rush ai-eval . --allow-slow --json
```

See [CI Overview](ci-overview.md) and [Scripts & Automation](scripts-and-automation.md).
