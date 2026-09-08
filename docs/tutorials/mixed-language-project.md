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
uv run rush tdd .
uv run rush review . --json
```
Rush evaluates TDD compliance, file sizes, scaffold markers (`TODO`, `FIXME`), and maintainability across all files deterministically, generating an interactive HTML report.

### Step 2: Multi-Language Linting & Formatting
```bash
uv run rush lint . --json
uv run rush format . --check --json
```
Rush automatically discovers and invokes:
- **Python**: Ruff, Flake8-Bugbear, ast-grep, Globstar
- **TypeScript**: ESLint, Biome, Prettier
- **Infrastructure**: Hadolint, TFLint

### Step 3: Architecture, Complexity & AI Anti-Slop
```bash
uv run rush complexity . --json
uv run rush slop . --json
```
Rush checks Python modular boundaries with Tach, tracks decay with Sentrux, measures token costs with Clines, and scans 10 languages for AI boilerplate with aislop.

### Step 4: Polyglot Security & Secret Audit
```bash
uv run rush security . --json
uv run rush secrets . --json
```
Rush runs pip-audit, npm audit, Semgrep, Trivy, Medusa, Gitleaks, and TruffleHog, merging all findings into coordinate-sorted `ToolResult` JSON output with redacted credentials.

### Step 5: Multi-Language Test Suites & Diff Coverage
```bash
uv run rush test . --json
uv run rush coverage . --allow-slow --json
```
Rush runs pytest for the Python backend and Vitest for the TypeScript frontend, while verifying diff coverage with Undercover.

---

### Step 7: Asset Hygiene & PR Evidence Card Synthesis (Phase 50b)
```bash
uv run rush dead-asset . --json
uv run rush pr-synthesize . --json
```
Rush identifies unreferenced images/fonts and synthesizes a comprehensive PR card with risk tiering and CODEOWNERS reviewer routing.

### Step 6: Polyglot Quality Catalog & Cloud Infrastructure Audit (Phase 50a)
```bash
uv run rush error-catalog . --json
uv run rush license-matrix . --json
uv run rush iam-audit . --json
```
Rush extracts exceptions across Python, TypeScript, and Rust, audits dependency licenses across `pyproject.toml` and `package.json`, and verifies least-privilege cloud IAM policies while detecting wildcard actions in `infra/*.tf`.

## 3. Key Takeaway

You run standard, consistent commands (`tdd`, `review`, `lint`, `complexity`, `slop`, `security`, `test`) regardless of how many languages exist in the repo.

See [Tutorials Overview](../TUTORIALS.md) and [CI Integration Guide](ci-integration.md).

### Step 8: Cold-Start Profiling & Honest Provenance (Phase 50c)
```bash
uv run rush cold-start . --json
uv run rush attest . --json
```
