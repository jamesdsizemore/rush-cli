# Recipe book

## Before PR

```bash
rush review . && rush lint . && rush format . --check && rush test . && rush security .
```

This shell chain stops on `fail`/`error`, but not `warn`/`skipped`; inspect JSON for stricter policy.

## Check docs and workflows

```bash
rush markdown docs
rush yaml .
rush actions .github/workflows
```

## Diagnose a skip

```bash
rush --log-level debug typecheck . --json
mypy --version   # if Python type checking is required
```

## Assistant prompt

“Use Rush to lint and test this project. Explain every skipped check and do not install anything.”

## CI policy

Capture each JSON result and reject `skipped` for required checks. See [Scripts](integrations/scripts-and-automation.md).
