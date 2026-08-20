# Testing guide

## Layers

1. **Unit contracts:** status, normalization, redaction, config, deterministic helpers.
2. **Parser fixtures:** native clean/findings/malformed reports without requiring binaries.
3. **Invocation tests:** fake process boundary verifies exact argv/environment/timeout.
4. **Routing tests:** markers, mixed languages, missing engines, aggregation order.
5. **CLI tests:** generated help, options, JSON, exit codes.
6. **MCP stdio tests:** real initialize/list/call with stdout/stderr integrity.
7. **Installed-engine tests:** marked, optional, bounded representative engines.
8. **Packaging tests:** wheel/sdist build and isolated import/entry-point smoke.
9. **Clean-clone and remote CI:** locked install and reproducibility.

## Commands

```bash
unset VIRTUAL_ENV PYTHONPATH
.venv/Scripts/python.exe -m pytest tests/ -q
.venv/Scripts/ruff.exe check src tests
.venv/Scripts/ruff.exe format --check src tests
git diff --check
```

Use `.venv/bin` on POSIX. A new adapter is not promoted to real maturity without deterministic parser/invocation evidence and missing/malformed paths.
