# CLI Cookbook & Command Recipes

This cookbook provides copy-pasteable command patterns for everyday engineering tasks across all 36 tools and 121 engines in Rush CLI.

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
