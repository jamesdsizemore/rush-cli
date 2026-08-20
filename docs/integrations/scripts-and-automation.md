# Shell Scripts, Automation & Tooling Integration

How to integrate Rush CLI into local shell scripts, Makefiles, git hooks, and automated developer tooling.

---

## 1. Exit Codes & Status Checking in Scripts

Rush maps execution outcomes to standard POSIX process exit codes:

| Outcome / Status | Exit Code | Description |
|---|---|---|
| `ok` | 0 | All checks passed cleanly with 0 findings. |
| `warn` | 0 | Warnings found, but no blocking policy errors. |
| `fail` | 1 | Linters found errors, security vulnerabilities detected, or tests failed. |
| `error` | 2 | Infrastructure error (e.g. malformed configuration, corrupted report file, timeout). |
| `skipped` | 0 | Optional engine is not installed or permission was denied. |

---

## 2. Bash / POSIX Shell Scripting Pattern

```bash
#!/usr/bin/env bash
set -eo pipefail

echo "Running Rush Quality Gateway..."

# Run review and fail immediately if code review heuristics fail
rush review .

# Run linting with JSON capture
LINT_OUTPUT=$(rush lint . --check --json)
LINT_STATUS=$(echo "$LINT_OUTPUT" | python -c "import json, sys; print(json.load(sys.stdin).get('status'))")

if [ "$LINT_STATUS" = "fail" ] || [ "$LINT_STATUS" = "error" ]; then
    echo "❌ Lint checks failed:"
    echo "$LINT_OUTPUT" | python -m json.tool
    exit 1
fi

echo "✅ All automated checks passed."
```

---

## 3. Makefile Integration

```makefile
.PHONY: check test security ci-clean

check:
	rush review .
	rush lint . --check
	rush format . --check

test:
	rush test .

security:
	rush security .
	rush secrets .

ci-clean: check test security
	@echo "All local verification gates clean."
```

See [Pre-Commit Guide](../PRE_COMMIT.md) and [CI Overview](ci-overview.md).
