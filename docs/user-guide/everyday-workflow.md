# The everyday workflow

## When to use it

Run this sequence after completing a feature or an AI-assisted edit and before opening a pull request:

```bash
rush review .
rush lint .
rush format . --check
rush test .
rush security .
```

Before deciding which checks are mandatory for this repository, inspect rather
than guess:

```bash
rush capabilities . --json
rush plan . --profile nonbrowser --json
```

These commands do not run checks. They explain whether a local report is ready,
a tool is configured, an engine is merely discoverable on `PATH`, a prerequisite
is missing, or a capability is intentionally blocked. Treat `installed` as
available to run—not proof that it has run or passed.

After an edit with a known file list, you can keep the local review focused
without granting Git access or asking Rush to infer change history:

```bash
rush review . --changed-file src/example.py --json
```

Repeat `--changed-file` for each intended file. Paths outside the target are
rejected; an omitted flag reviews the whole target as before.

## What each step tells you

1. **Review** reads Python source and reports deterministic maintainability signals. `warn` means inspect the findings; it is not human approval.
2. **Lint** asks applicable installed linters about source correctness and style. Fix `fail` findings, or document why a rule does not apply.
3. **Format check** detects files that would be reformatted without changing them. If it fails, run the project's formatter and inspect the diff.
4. **Test** invokes applicable installed test runners. Read failing test names and engine output before changing code.
5. **Security** checks supported dependency data. Investigate advisory identifiers and upgrade paths.

Use `--json` when a script or CI job needs stable fields:

```bash
rush lint . --json
```

## After an AI coding session

Review the actual changed scope first, then run repository-level tests when appropriate. Rush does not infer authorship and does not certify AI-generated code. It gives the same evidence regardless of who wrote the code.

## Good stopping condition

Required checks are `ok`; intentional advisory findings are understood; no required check is merely `skipped`; and the Git diff contains only expected changes. Teams decide which optional engines are required. See [CI overview](../integrations/ci-overview.md).
