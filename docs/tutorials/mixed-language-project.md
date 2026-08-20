# Tutorial: Multi-Language & Polyglot Repository Verification

**Goal:** Run unified quality, linting, security, and testing passes across a mixed-language repository (e.g. Python backend + TypeScript frontend + Docker/Terraform infrastructure) without configuring separate shell scripts.

---

## 1. Project Scenario

Assume a monorepo containing:
- `backend/` (Python with `pyproject.toml`)
- `frontend/` (TypeScript with `package.json`)
- `infra/` (Terraform `*.tf` and `Dockerfile`)

---

## 2. Step-by-Step Execution

### Step 1: Universal Code Review & TDD Verification
```bash
rush tdd .
rush review . --export-html artifacts/polyglot-report.html
```
Rush evaluates TDD compliance, file sizes, scaffold markers (`TODO`, `FIXME`), and maintainability across all files deterministically, generating an interactive HTML report.

### Step 2: Multi-Language Linting & Formatting
```bash
rush lint . --json
rush format . --check --json
```
Rush automatically discovers and invokes:
- **Python**: Ruff, Flake8-Bugbear, ast-grep, Globstar
- **TypeScript**: ESLint, Biome, Prettier
- **Infrastructure**: Hadolint, TFLint

### Step 3: Architecture, Complexity & AI Anti-Slop
```bash
rush complexity . --json
rush slop . --json
```
Rush checks Python modular boundaries with Tach, tracks decay with Sentrux, measures token costs with Clines, and scans 10 languages for AI boilerplate with aislop.

### Step 4: Polyglot Security & Secret Audit
```bash
rush security . --json
rush secrets . --json
```
Rush runs pip-audit, npm audit, Semgrep, Trivy, Medusa, Gitleaks, and TruffleHog, merging all findings into coordinate-sorted `ToolResult` JSON output with redacted credentials.

### Step 5: Multi-Language Test Suites & Diff Coverage
```bash
rush test . --json
rush coverage . --allow-slow --json
```
Rush runs pytest for the Python backend and Vitest for the TypeScript frontend, while verifying diff coverage with Undercover.

---

## 3. Key Takeaway

You run standard, consistent commands (`tdd`, `review`, `lint`, `complexity`, `slop`, `security`, `test`) regardless of how many languages exist in the repo.

See [Tutorials Overview](../TUTORIALS.md) and [CI Integration Guide](ci-integration.md).
