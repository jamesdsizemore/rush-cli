# Tutorial: set up a Python project

**Outcome:** run TDD checks, review, lint, format-check, type, modular complexity, anti-slop, test, and dependency checks on Python.

**Prerequisites:** Rush and a Python project with `pyproject.toml` or Python source.

1. Install chosen helpers in the project:
   ```bash
   uv add --dev ruff pytest pip-audit mypy tach pyrefly aislop
   ```
2. Run the safe sequence:
   ```bash
   rush tdd .
   rush review . --export-html artifacts/review.html
   rush lint .
   rush format . --check
   rush typecheck .
   rush complexity .
   rush slop .
   rush test .
   rush security .
   ```
3. For every `skipped` result, read the summary. Do not count it as a pass.
4. Fix a reported issue, rerun the specific command, then run the full sequence.

**Expected:** applicable installed engines execute; unrelated engines are not required. `warn` from review is advisory, while `fail` from lint/test/security needs triage.

**Next:** encode the sequence in [CI](ci-integration.md).
