# Troubleshooting Guide & FAQs

When a tool fails, an engine warning appears, or an unexpected result occurs, this guide will help you understand what happened and how to fix it in seconds.

---

## Common Questions & Solutions

### 1. "Why did a tool say `[SKIPPED]`?"
**Explanation**: Rush discovers quality engines installed in your environment (on `PATH` or in `.venv/Scripts`). If an optional external tool (like `sqlfluff`, `actionlint`, or `djlint`) is not installed, Rush gracefully marks it as `[SKIPPED]` rather than crashing.

**Solution**:
- If you don't use that technology (e.g. you don't have SQL files in your project), you can safely ignore the skipped status.
- If you want to enable that check, install the engine into your environment:
  ```bash
  # Install Python engines
  uv pip install sqlfluff djlint detect-secrets

  # Install Node / CLI engines
  npm install -g markdownlint-cli typescript @stoplight/spectral-cli
  ```

---

### 2. "Why does my test fail with `Uncommitted changes detected` when running `rush fix`?"
**Explanation**: `rush fix` modifies source files to auto-format code and clean unused imports. To protect you from accidental data loss, Rush requires a clean Git working directory before applying automated edits.

**Solution**:
- Commit or stash your current changes first:
  ```bash
  git commit -am "wip: save work before auto-fix"
  rush fix .
  ```
- Or pass `--force` to bypass the uncommitted changes check:
  ```bash
  rush fix . --force
  ```

---

### 3. "How do I diagnose environment health and PATH precedence?"
**Solution**: Run the built-in diagnostic doctor:
```bash
rush doctor .
```
Rush will check:
- Which Python interpreter and virtual environment is active.
- Which quality engines are installed and their exact versions.
- Whether any conflicting binaries are shadowing your project's local tools.

---

### 4. "Why did an advanced check return `SKIPPED (Requires permission: --allow-slow)`?"
**Explanation**: To prevent surprise slowdowns or unauthorized network access, long-running operations (like browser end-to-end tests or mutation testing) require explicit permission flags.

**Solution**:
- Pass the required permission flag explicitly:
  ```bash
  rush e2e . --allow-browser
  rush mutation . --allow-slow
  rush load . --allow-network
  ```

---

## Getting More Help

- Explore the complete [Everyday Workflow](everyday-workflow.md).
- Dive into the [Agentic Rush Knowledge Base](../AGENTIC_RUSH.md).
- Check the [Subsystem & Bundle Architecture Diagrams](../BUNDLE_DIAGRAMS.md).
