# Tutorial: add Rush to CI

**Outcome:** run a bounded set of required checks without installing every supported ecosystem.

1. Pick checks based on repository languages and risk. Do not select every catalog command.
2. Install Rush and the exact engine set in a locked CI environment.
3. Run JSON-capable commands:
   ```bash
   rush lint . --json
   rush format . --check --json
   rush test . --json
   rush security . --json
   ```
4. Remember that `skipped` exits 0. If the check is mandatory, parse `status` and reject `skipped` explicitly.
5. Keep representative real-engine jobs bounded; use parser fixtures for broad adapter coverage.

**Expected:** deterministic output and no implicit installs. See the complete [GitHub Actions guide](../integrations/github-actions.md).

**Next:** add an engine-specific job only when the repository actually adopts that language/tool.
