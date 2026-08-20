# Practical Examples & Common Workflows

This guide provides concrete, real-world examples for running Rush across different project types, frameworks, and continuous delivery setups.

---

## 1. Quick Quality Inspection

```bash
# 1. Review Python code maintainability and heuristics
rush review src/

# 2. Review only files modified in your feature branch
rush review . --changed-file src/rush/cli.py

# 3. Run source linters across Python and TypeScript
rush lint . --json

# 4. Check formatting without modifying files
rush format . --check
```

---

## 2. Security & Supply Chain Scans

```bash
# 1. Run multi-ecosystem vulnerability & SAST scans
rush security . --json

# 2. Deep secret scan with automatic secret redaction
rush secrets . --json

# 3. Generate CycloneDX Software Bill of Materials (SBOM)
rush sbom . -o sbom.json --allow-artifact-write --json

# 4. Evaluate LLM prompt security and agent safety guardrails
rush ai-eval . --allow-slow --json
```

---

## 3. Infrastructure, Databases & Cloud-Native

```bash
# 1. Check Terraform and Kubernetes manifests for security policies
rush iac . --json

# 2. Lint Dockerfile against CIS benchmarks
rush containerfile . --json

# 3. Audit SQL queries and verify database migration lock safety
rush sql . --json

# 4. Validate GitHub Actions workflows
rush actions .github/workflows/
```

---

## 4. Test Quality & Verification

```bash
# 1. Run unit & integration tests
rush test . --json

# 2. Run polyglot mutation testing under slow permission
rush mutation . --allow-slow --json

# 3. Import existing coverage XML report for unified normalization
rush coverage coverage.xml --json

# 4. Launch headless browser E2E test suite
rush e2e . --allow-browser --json
```

---

## 5. Model Context Protocol (MCP) Server for AI Agents

```bash
# Start local stdio MCP server for Cursor, Claude Code, or Windsurf
rush mcp serve
```

See [Recipe Book](RECIPE_BOOK.md) and [Tutorials](TUTORIALS.md).
