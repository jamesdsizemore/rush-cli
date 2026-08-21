# The everyday workflow

## When to use it

## Workflow Suites & Pre-PR Routines

### 1. Fast Inner-Loop Checks (`rush check`)
Run in-development checks (lint, format verification, type checking) concurrently in milliseconds:
```bash
rush check .
```

### 2. Live File Watching (`rush watch`)
Keep Rush running in the background to automatically re-evaluate your project whenever source files change:
```bash
# Watch files with default 300ms debounce
rush watch .

# Watch files and trigger specific tool or suite
rush watch . --tool lint --debounce 500
```

### 3. Automated Safe Fixes (`rush fix`)
```bash
# Preview automated fixes without modifying disk
rush fix . --dry-run

# Apply safe formatting and linter fixes
rush fix .
```

### 4. Deep Security & Supply Chain Audit (`rush audit`)
```bash
rush audit .
```

### 5. Strict Pre-Merge Gate (`rush gate`)
Run the full gate suite (lint, format, typecheck, test, security) before merging:
```bash
rush gate . --fail-fast
```

### 6. Granular Inspection & Planning
Before deciding which checks are mandatory for this repository, inspect rather than guess:

```bash
rush capabilities . --json
rush plan . --profile nonbrowser --json
```

These commands do not run checks. They explain whether a local report is ready, a tool is configured, an engine is merely discoverable on `PATH`, a prerequisite is missing, or a capability is intentionally blocked. Treat `installed` as available to run—not proof that it has run or passed.

After an edit with a known file list, you can keep the local review focused without granting Git access or asking Rush to infer change history:

```bash
rush review . --changed-file src/example.py --json
```

Repeat `--changed-file` for each intended file. Paths outside the target are rejected; an omitted flag reviews the whole target as before.

## What each step tells you

1. **TDD Guard (`rush tdd`)** verifies that tests exist and define contracts for newly added or modified source modules.
2. **Review (`rush review`)** reads source code and reports deterministic maintainability signals. Generates interactive HTML dashboards via `--export-html` and SARIF via `--export-sarif`.
3. **Lint (`rush lint`)** asks applicable installed linters (Ruff, ESLint, Globstar, ast-grep) about source correctness and AST patterns.
4. **Format check (`rush format --check`)** detects files that would be reformatted without changing them.
5. **Complexity (`rush complexity`)** enforces modular boundaries (Tach), monitors code decay (Sentrux), and evaluates token density (Clines).
6. **AI Anti-Slop (`rush slop`)** scans for hallucinated code, repetitive comments, and empty boilerplate (aislop, sloppylint).
7. **Test (`rush test`)** invokes applicable installed test runners (pytest, Vitest, Newman).
8. **Security (`rush security`)** checks dependencies (pip-audit, npm-audit, Trivy), SAST (Semgrep, Bearer), and agent hooks (Medusa).

Use `--json` when a script or CI job needs stable fields:

```bash
rush lint . --json
```

## After an AI coding session

1. Verify TDD compliance with `rush tdd .`.
2. Review the actual changed scope with `rush review . --changed-file <file>`.
3. Check for AI hallucinations with `rush slop .`.
4. Run sub-second staged hook checks with `rush hook run`.
5. Compute composite PR quality scorecard with `rush score compute`.
6. Run repository-level tests and security scans.

## Good stopping condition

Required checks are `ok`; intentional advisory findings are understood; no required check is merely `skipped`; quality scorecard score is >= 85%; and the Git diff contains only expected changes. Teams decide which optional engines are required. See [CI overview](../integrations/ci-overview.md).

