# Git Pre-Commit Hook Integration

Enforce code quality, formatting, security, and documentation synchronization automatically before commits are written to Git history.

---

## 1. Native Rush Git Hook (`.githooks/pre-commit`)

Rush includes a built-in pre-commit hook that verifies documentation parity and executes fast quality checks:

```bash
# Configure git to use the repository hooks directory
git config core.hooksPath .githooks
```

The hook script executes:
1. `python scripts/sync_docs.py --check` (Zero-drift documentation audit across all 128 doc files)
2. `pytest tests/test_docs_parity_and_sync.py -q` (Automated pytest doc parity suite)

---

## 2. Using with the `pre-commit` Framework (`.pre-commit-config.yaml`)

If your team uses the Python `pre-commit` framework:

```yaml
repos:
  - repo: local
    hooks:
      - id: rush-review
        name: Rush Review
        entry: uv run rush review .
        language: system
        pass_filenames: false

      - id: rush-lint
        name: Rush Lint
        entry: uv run rush lint .
        language: system
        pass_filenames: false

      - id: rush-format
        name: Rush Format (Check)
        entry: uv run rush format . --check
        language: system
        pass_filenames: false

      - id: rush-doc-sync
        name: Rush Documentation Parity
        entry: uv run python scripts/sync_docs.py --check
        language: system
        pass_filenames: false
```

---

## 3. Best Practices for Pre-Commit Hooks

- **Fast & Deterministic**: Keep pre-commit hooks limited to fast commands (`review`, `lint`, `format --check`, `doc-sync`).
- **Avoid Heavy/Slow Checks in Hooks**: Run heavy checks (mutation tests, browser E2E, load tests) in CI rather than pre-commit hooks to avoid slowing down developer commit loops.
- **Inspect `status: skipped`**: If a required linter skips locally due to a missing engine, install the engine in your local development virtual environment.

---

## 4. Built-in Pre-Commit Intelligence & Tamper Guard (`rush hook run`)

Rush provides an ultra-fast staged execution engine specifically designed for pre-commit hooks:

```bash
# Execute sub-second staged checks directly
rush hook run
```

### Checks Performed by `rush hook run`:
1. **Branch Protection**: Prohibits direct commits to `main`, `master`, and `release`.
2. **Staged Python AST Linting**: Validates syntax in microseconds without running slow external processes.
3. **Trojan Source Unicode Guard**: Detects invisible or reversing bidirectional override characters (`U+202E`, `U+2066`, etc.).
4. **Merge Conflict Marker Guard**: Blocks staged files containing unresolved `<<<<<<<`, `=======`, or `>>>>>>>` markers.
5. **Cryptographic Tamper Detection**: Verifies SHA-256 signatures of `.git/hooks/` against `.rush/hook_signatures.json`.

See [Everyday Workflow](user-guide/everyday-workflow.md) and [Scripts & Automation](integrations/scripts-and-automation.md).


## Pre-Commit Hooks for Context & Release Safety (Phases 41–43)

You can invoke Rush's fast pre-flight vectors directly in git workflows:
* `rush hallu-guard`: Blocks commits with hallucinated dependencies.
* `rush ship env`: Blocks commits missing `.env.example` declarations.
* `rush ship pack`: Blocks commits with unredacted secret leaks.

### Architecture Boundary Pre-Commit Hook
* `rush arch-guard`: Prevent unauthorized cross-layer imports from entering git history.


### API Compatibility Pre-Commit Gate
* `rush api-diff`: Ensure no unintended breaking API changes are committed.

