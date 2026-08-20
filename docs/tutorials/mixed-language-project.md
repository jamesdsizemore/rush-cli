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

### Step 1: Universal Code Review
```bash
rush review .
```
Rush evaluates file sizes, scaffold markers (`TODO`, `FIXME`), and maintainability across all files deterministically.

### Step 2: Multi-Language Linting & Formatting
```bash
rush lint . --json
rush format . --check --json
```
Rush automatically discovers and invokes:
- **Python**: Ruff, Flake8-Bugbear, ast-grep
- **TypeScript**: ESLint, Biome, Prettier
- **Infrastructure**: Hadolint, TFLint

### Step 3: Polyglot Security & Secret Audit
```bash
rush security . --json
rush secrets . --json
```
Rush runs pip-audit, npm audit, Semgrep, Trivy, Gitleaks, and TruffleHog, merging all findings into coordinate-sorted `ToolResult` JSON output with redacted credentials.

### Step 4: Multi-Language Test Suites
```bash
rush test . --json
```
Rush runs pytest for the Python backend and Vitest for the TypeScript frontend, aggregating test durations and failure messages.

---

## 3. Key Takeaway

You run the exact same 4 commands (`review`, `lint`, `security`, `test`) regardless of how many languages exist in the repo.

See [Tutorials Overview](../TUTORIALS.md) and [CI Integration Guide](ci-integration.md).
