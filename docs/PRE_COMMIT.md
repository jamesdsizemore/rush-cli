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

See [Everyday Workflow](user-guide/everyday-workflow.md) and [Scripts & Automation](integrations/scripts-and-automation.md).
