# CLI Cookbook & Command Recipes

This cookbook provides copy-pasteable command patterns for everyday engineering tasks across all 37 tools and 121 engines in Rush CLI.

---

## 1. Daily Development & Feature Work

### Pre-PR Local Quality Pass
Run deterministic review, linters, non-mutating format checks, and unit tests:
```bash
rush review .
rush lint .
rush format . --check
rush test .
```

### Review Changed Files Only (with Git Scope)
Review only files modified in your branch without running full repo heuristics:
```bash
rush review . --changed-file src/rush/cli.py --changed-file src/rush/tools/quality.py
```

### Review with Local Graft Knowledge Graph
Incorporate call-graph and symbol connectivity evidence into heuristic reviews:
```bash
rush review . --use-graft
```

---

### Export Standalone HTML & SARIF 2.1.0 Reports
Generate visual inspection artifacts for human reviewers and CI systems:
```bash
rush review . --export-html report.html --export-sarif review.sarif
rush security . --export-html security.html
```

### Enforce Test-Driven Development (TDD)
Verify that tests exist and define contracts before merging implementation code:
```bash
rush tdd .
```

---

## 2. Code Quality, Linters & Modernization (Phases 14, 18, 19, 20)

### Check Code Style and AST Patterns
```bash
rush lint . --json
```
*Engines:* Ruff (Python), ESLint (JS/TS), Globstar (Tree-Sitter custom patterns), Stylelint (CSS/SCSS), ast-grep (Tree-sitter AST), MegaLinter (polyglot orchestrator), Comby (structural pattern matcher), Flake8-Bugbear (AST bug finder), Buf (Protobuf), wasm-tools (WebAssembly).

### Check Dead Code, Unused Imports & Exports
```bash
rush dead . --json
```
*Engines:* Vulture (Python dead code), Knip (JS/TS unused files/deps), FawltyDeps (undeclared/unused Python dependencies), Ts-prune (unused TypeScript exports).

### Modular Architecture, Complexity & Binary Footprint
```bash
rush complexity . --json
```
*Engines:* Tach (modular boundaries & cycle enforcement), Sentrux (code decay sensors), Clines (token density & complexity), Radon (cyclomatic complexity), jscpd (copy-paste duplication), Depcruise (architectural dependency cycles), Memray (Python memory allocation), Statoscope (JS bundle analysis), Bloaty (binary section/symbol footprint), Scaphandre (energy/carbon estimation).

### Vibecoder AI Anti-Slop & Repetition Cleaner
```bash
rush slop . --json
```
*Engines:* aislop (AST anti-pattern scanner across 10 languages), sloppylint (AI filler patterns, repetitive comments, hallucinated structures), Markdown-Unfluff (prose fluff and AI noise).

---

## 3. Security, Secret Detection & AI Safety (Phases 09, 10, 11)

### Comprehensive Security & SAST Audit
```bash
rush security . --json
```
*Engines:* pip-audit, npm audit, OSV-Scanner, Semgrep (offline SAST), Trivy, Grype, Bearer (privacy/PII data flows), Horusec, Pa11y (accessibility), OWASP ZAP (DAST), Dockle (container CIS benchmarks), Safe-Env (environment secret sanity), NCU (npm-check-updates).

### Deep Secret Detection (Normalized & Redacted)
```bash
rush secrets . --json
```
*Engines:* Gitleaks, TruffleHog (verified high-entropy credentials), Secretlint, detect-secrets, Safe-Env.

### AI, LLM & Agentic Evaluation
```bash
rush ai-eval . --allow-slow --json
```
*Engines:* Promptfoo (prompt injection & grading), Garak (LLM vulnerability scanner), DeepEval (RAG faithfulness/hallucination tests), NeMo Guardrails (agent safety policies).

---

## 4. Cloud-Native, IaC, Databases & Containers (Phases 12, 18)

### Infrastructure-as-Code & Kubernetes Security
```bash
rush iac . --json
```
*Engines:* TFLint (Terraform), Checkov (cloud security policies), Kubeconform (Kubernetes schemas), Terrascan (OPA Rego policies), Kube-score (manifest reliability), Conftest (custom OPA policy), Polaris (workload security), KubeLinter.

### Database Schema Migration & Lock Analysis
```bash
rush sql . --json
```
*Engines:* SQLFluff (SQL style), Atlas (declarative migration safety), Squawk (PostgreSQL migration locking analysis).

### Containerfile & CIS Benchmark Validation
```bash
rush containerfile . --json
```
*Engines:* Hadolint (Dockerfile best practices), Dockle (container image CIS compliance).

---

## 5. Test Confidence, Mutation & Browser E2E (Phases 13, 15, 16, 17)

### Polyglot Mutation Testing
```bash
rush mutation . --allow-slow --json
```
*Engines:* Stryker (JS/TS/C#), Cosmic Ray (Python), Infection (PHP), Pitest (JVM), Cargo-mutants (Rust).

### API Contract Fuzzing & Schema Evolution
```bash
rush contract . --allow-slow --json
```
*Engines:* Schemathesis (property-based OpenAPI/GraphQL fuzzing), Zally (API design rules).

### Browser E2E & Visual Regression
```bash
rush e2e . --allow-browser --json
rush visual . --allow-browser --allow-slow --json
```
*Engines:* Playwright, Wait-On (service readiness), Lost Pixel (Storybook diff), BackstopJS (multi-viewport visual regression).

---

## 6. Software Supply Chain, SBOM & Workflow (Phases 11, 19)

### SBOM Generation & License Compliance
```bash
rush sbom . --json
rush sbom . -o my-sbom.json --overwrite --allow-artifact-write --json
```
*Engines:* cdxgen (CycloneDX), ScanCode (license copyleft), GUAC (supply chain graph), pip-licenses.

### Conventional Commit Message Validation
```bash
rush commit-msg . -m "feat(security): add trufflehog scanner adapter"
```

### Dry-Run Release Planning & Attestation
```bash
rush release . --json
```
*Engines:* Cosign (cryptographic signatures), SLSA Verifier (provenance attestations), Semantic-Release (automated semver calculation).

---

## 7. Workflow Suites, Watcher & Dashboards (Phases 21–27)

### Fast Inner-Loop Developer Check
Run lint, format verification, and type checking in parallel:
```bash
rush check .
```

### Security & Supply Chain Audit Suite
```bash
rush audit .
```

### Strict Pre-Merge Gate (with Fail-Fast)
```bash
rush gate . --fail-fast
```

### Automated Code Remediation & Dry-Run Preview
```bash
# Preview proposed fixes without altering files
rush fix . --dry-run

# Apply safe automated fixes across engines
rush fix .
```

### Real-Time File Watcher
```bash
# Watch files and auto-trigger fast check suite
rush watch .

# Watch files and trigger a specific tool with custom debounce
rush watch . --tool lint --debounce 500
```

### Interactive Terminal TUI & Web Dashboard
```bash
# Launch interactive terminal findings explorer
rush ui .

# Launch authenticated local web dashboard on 127.0.0.1
rush dashboard . --port 8080
```

---

## 8. Monorepos, Plugins & Trust Gating (Phases 26, 28)

### Monorepo Scoped Evaluation
```bash
# Evaluate a single package in a monorepo
rush lint . -w @myorg/frontend

# Evaluate all packages in topological order
rush test . --all-workspaces
```

### Custom Plugin Execution & Repository Trust
```bash
# Authorize local repository in trust ledger (Control 6)
rush trust .

# List custom plugins defined in rush.toml
rush plugin list .

# Execute a custom plugin
rush plugin run custom-ast-linter .
```

---

## 9. Autonomous Agent Safety & Sandboxing (Phases 29, 31)

### Intercept Destructive Shell Commands & Verify Boundary Paths
```bash
# Intercept dangerous rm/drop/reset commands before agent execution
rush guard check-cmd "rm -rf /"

# Enforce repository boundary path confinement
rush guard check-path "src/rush/main.py"
```

### Apply AI Remediation Patches in Isolated Git Worktrees
```bash
# Preview patch application in isolated worktree sandbox
rush patch apply patch.diff --dry-run

# Apply patch with circuit breaker
rush patch apply patch.diff --circuit-breaker
```

---

## 10. Token Economy & Polyglot CodeGraph (Phases 32, 35)

### Fast BPE Token Counting & AST Outline Compression
```bash
# Count BPE tokens for target source file
rush token count src/rush/cli.py

# Generate compressed AST outline (stripping bodies to save LLM tokens)
rush outline src/rush/cli.py
```

### Extract Verbatim CodeGraph Slices with Line Numbers
```bash
# Extract verbatim source slice and call paths from CPG database
rush codegraph slice "CompositeScorecardCalculator"
```

---

## 11. Full-Stack Static Sync & 3-Way AST Merge Resolution (Phases 33, 34)

### Verify OpenAPI Contracts & Generate TypeScript Interfaces
```bash
# Verify contract and generate TypeScript interfaces
rush sync openapi api/spec.json --output-ts types/api.ts
```

### Detect Dead Code & Resolve 3-Way AST Git Conflicts
```bash
# Scan for dead exports and unreferenced polyglot symbols
rush hygiene dead-code

# Semantically reconcile conflicting AST source files
rush conflict solve branch_a.py branch_b.py
```

---

## 12. Bundle Budgets, Hotspots, Pre-Commit & Quality Scorecards (Phases 36–40)

### Analyze Frontend Bundle Transfer Sizes & Budget Gates
```bash
# Measure build chunk transfer sizes (raw, gzip, brotli)
rush bundle analyze ./dist
```

### Compute Git Commit Churn & Defect Risk Matrix
```bash
# Calculate composite defect risk combining churn and cyclomatic complexity
rush hotspots analyze
```

### Synchronize Multi-IDE Agent Governance & Scaffold Projects
```bash
# Compile canonical AGENTS.md to .cursorrules, .clinerules, etc.
rush governance sync

# Initialize new repository with canonical AI governance templates
rush scaffold init
```

### Execute Staged Pre-Commit Intelligence
```bash
# Run microsecond AST linting, Trojan Source detection, and conflict marker checks
rush hook run
```

### Calculate 6-Pillar Composite Quality Scorecard & Consensus
```bash
# Compute deterministic 0-100% score and letter grade
rush score compute --type-safety 95 --test-coverage 90 --security 100

# Reconcile multi-model AI code review findings with weighted consensus
rush consensus reconcile
```


