# Recipe Book & Advanced Engineering Scenarios

This recipe book provides battle-tested command workflows for multi-language repositories, pre-flight checks, CI automation, and AI pair programming.

---

## 1. Multi-Language Quality Audit (Python + TypeScript + Rust)

```bash
# 1. Run all linters (Ruff, ESLint, Stylelint, ast-grep)
rush lint . --json > lint_results.json

# 2. Check formatting compliance across all languages
rush format . --check --json > format_results.json

# 3. Type check Python (mypy) and TypeScript (tsc)
rush typecheck . --json > typecheck_results.json

# 4. Run test suites (pytest + Vitest)
rush test . --json > test_results.json
```

---

## 2. Pre-Flight Security & Supply Chain Hardening

```bash
# 1. Dependency vulnerability audit
rush security . --json

# 2. High-entropy secret scanning with TruffleHog and Gitleaks
rush secrets . --json

# 3. Generate CycloneDX SBOM artifact
rush sbom . -o release-sbom.json --overwrite --allow-artifact-write --json

# 4. Audit OpenSSF Scorecard supply chain posture
rush ci . --json
```

---

## 3. Infrastructure, Database & Kubernetes Validation

```bash
# 1. Validate Terraform and Kubernetes manifests against OPA Rego policies
rush iac . --json

# 2. Check Dockerfile against CIS Docker benchmarks
rush containerfile . --json

# 3. Analyze PostgreSQL migration locks with Squawk
rush sql migrations/ --json

# 4. Verify GitHub Actions workflow syntax
rush actions .github/workflows/ --json
```

---

## 4. Test Confidence & AI Safety Verification

```bash
# 1. Run mutation tests on critical business logic
rush mutation src/ --allow-slow --json

# 2. Run API schema fuzzing against OpenAPI specifications
rush contract openapi.yaml --allow-slow --json

# 3. Evaluate AI assistant prompt safety and guardrails
rush ai-eval prompts/ --allow-slow --json

# 4. Run browser E2E test scenarios
rush e2e e2e/ --allow-browser --json
```

---

## 5. Automated CI Script Pattern

```bash
#!/usr/bin/env bash
set -e

# Run checks and stop on any failure status
for cmd in "review ." "lint ." "format . --check" "test ." "security ."; do
  echo "Executing: rush $cmd"
  rush $cmd --json | python -c '
import json, sys
data = json.load(sys.stdin)
if data.get("status") in ("fail", "error"):
    print(f"Error: {data.get(\"summary\")}")
    sys.exit(1)
'
done
echo "All quality gates passed!"
```

See [CLI Cookbook](CLI_COOKBOOK.md) and [Examples](EXAMPLES.md).
