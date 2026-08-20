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

---

## 4. Test Quality, TDD & Verification

```bash
# 1. Enforce Test-Driven Development (TDD) compliance
rush tdd .

# 2. Run unit & integration tests
rush test . --json

# 3. Run polyglot mutation testing under slow permission
rush mutation . --allow-slow --json

# 4. Run diff-based structural coverage verification
rush coverage . --allow-slow --json

# 5. Launch headless browser E2E test suite
rush e2e . --allow-browser --json
```

---

## 5. Modular Architecture, AST Anti-Slop & Continuous Sensors

```bash
# 1. Check Python modular boundaries with Tach and token metrics with Clines
rush complexity . --json

# 2. Scan polyglot codebase for AI filler slop and hallucinated structures
rush slop . --json

# 3. Verify offline cryptographic trust certificates before release
rush release . --json
```

---

## 6. HTML Dashboard & SARIF 2.1.0 Artifact Generation

```bash
# 1. Export interactive dark-mode HTML inspection dashboard
rush review . --export-html artifacts/review.html

# 2. Export SARIF 2.1.0 for GitHub Code Scanning
rush security . --export-sarif artifacts/security.sarif
```

---

## 7. Model Context Protocol (MCP) Server for AI Agents

```bash
# Start local stdio MCP server for Cursor, Claude Code, or Windsurf
rush mcp serve
```

See [Recipe Book](RECIPE_BOOK.md) and [Tutorials](TUTORIALS.md).
