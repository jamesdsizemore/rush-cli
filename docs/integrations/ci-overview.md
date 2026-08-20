# Continuous Integration (CI) Architecture & Strategy

Rush provides a unified, deterministic quality gateway for Continuous Integration pipelines across all 36 tools and 121 engines.

---

## 1. The Bounded-Engine CI Strategy

Modern polyglot repositories often struggle with bloated CI containers that install dozens of heavy language runtimes. Rush solves this with a **bounded-engine strategy**:

1. **Stack-Specific Provisioning**: Install only the engines required for your repository's stack (e.g. `ruff` for Python, `eslint` for TypeScript, `hadolint` for Dockerfiles).
2. **Unified Output**: Inspect standard `ToolResult` JSON output across all pipeline stages.
3. **Structured Policy Gates**: Differentiate between informational warnings (`warn`), test failures (`fail`), infrastructure errors (`error`), and absent optional engines (`skipped`).
4. **Offline Safety**: Rush runs engines offline by default. No background downloads or external telemetry will slow down or flake your CI builds.

---

## 2. CI Pipeline Stages

```mermaid
flowchart LR
    A[Checkout Code] --> B[Setup Python & uv]
    B --> C[Rush Review & Lint]
    C --> D[Rush Security & Secrets]
    D --> E[Rush Tests & Coverage]
    E --> F[Artifact / Build Gate]
```

---

## 3. Handling `status: "skipped"` in CI

By design, Rush exits with code 0 on `skipped` because optional engines might not be needed in every developer environment. In CI pipelines where an engine is mandatory, add a JSON policy check:

```bash
uv run rush lint . --json | python -c '
import json, sys
data = json.load(sys.stdin)
if data.get("status") in ("fail", "error", "skipped"):
    print(f"CI Gate Failed: {data.get(\"summary\")}")
    sys.exit(1)
'
```

See [GitHub Actions Guide](github-actions.md) and [Scripts and Automation](scripts-and-automation.md).
