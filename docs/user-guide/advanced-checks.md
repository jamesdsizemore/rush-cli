# Advanced Quality, Security & Verification Checks

Rush exposes advanced verification capabilities so their safety boundaries, resource requirements, and execution modes are explicit and transparent.

---

## 1. Advanced Check Capabilities & Permission Matrix

These tools operate in **dual modes**: importing local structured reports or executing live engines under explicit permissions:

| Command | Category | Required Permissions | Supported Engines & Dual-Mode Behavior |
|---|---|---|---|
| `ai-eval` | Security & AI Safety | `--allow-slow` | Evaluates prompt safety, LLM security, and guardrails via **Promptfoo**, **Garak**, **DeepEval**, and **NeMo Guardrails**. |
| `coverage` | Test Confidence | `--allow-slow` | Imports local `coverage.py` JSON, LCOV, or Cobertura XML, or executes pytest coverage / **Diff-Cover** / **Undercover** under `--allow-slow`. |
| `mutation` | Test Confidence | `--allow-slow` | Imports mutation reports, or executes polyglot mutation engines: **Stryker** (JS/TS/C#), **Cosmic Ray** (Python), **Infection** (PHP), **Pitest** (JVM), **Cargo-mutants** (Rust), or **mutmut**. |
| `contract` | Test Confidence | `--allow-slow` | Imports Pact reports, or executes property-based API contract fuzzing with **Schemathesis**, **Zally**, or pact-verifier. |
| `e2e` | Browser Runtime | `--allow-browser` | Executes headless browser end-to-end tests via **Playwright** with **Wait-On** readiness polling. |
| `visual` | UI/UX & Visual | `--allow-browser` & `--allow-slow` | Runs visual regression audits via **Lost Pixel**, **BackstopJS**, **Lighthouse**, or **PageSpeed** (`--accept` requires `--allow-artifact-write`). |
| `semantic-drift`| Browser Runtime | `--allow-browser` & `--allow-slow` | Runs DOM and accessibility drift verification using **Playwright** and **axe-core**. |
| `pbt` | Test Confidence | `--allow-slow` | Imports property-based test reports, or executes **Hypothesis** under `--allow-slow`. |
| `flaky` | Test Confidence | `--allow-slow` | Imports duplicate JUnit test reports, or executes pytest-rerun under `--allow-slow`. |
| `snapshot` | Test Confidence | `--allow-slow` | Imports snapshot reports, or runs pytest-snapshot (`--accept` requires `--allow-artifact-write`). |
| `fuzz` | Test Confidence | `--allow-slow` | Imports seeded fuzzing reports, or runs Atheris under `--allow-slow`. |
| `load` | Performance | `--allow-network` | Imports load test summaries, or executes **k6** load generation under `--allow-network`. |
| `codeql` | Security & SAST | `--allow-build` | Imports CodeQL SARIF 2.1.0 reports, or executes local CodeQL database analysis under `--allow-build`. |
| `sbom` | Supply Chain | `--allow-artifact-write` | Generates CycloneDX SBOMs via **cdxgen**, **ScanCode**, **GUAC**, or **pip-licenses** (writing `-o` requires `--allow-artifact-write`). |
| `tdd` | Test Confidence | None (Offline) | Enforces Red-Green-Refactor cycles and verifies test existence for newly introduced code files. |
| `slop` | Code Quality & AST | None (Offline) | Scans for AI hallucinations, repetitive stubs, and empty boilerplates via **aislop**, **sloppylint**, and **Markdown-Unfluff**. |
| `complexity` | Architecture & Maintainability | None (Offline) | Evaluates modular boundaries (**Tach**), code decay (**Sentrux**), token density (**Clines**), and cyclomatic metrics (**Radon**). |
| `release` | Supply Chain & Attestation | None (Offline) | Verifies offline cryptographic trust certificates via **Cejel** and version increments via **Semantic-Release**. |

---

## 2. Using Dual-Mode Tools

### Mode A: Report Import Mode
When a report file already exists (from an earlier build step or CI job), pass the report path directly:
```bash
rush coverage coverage.json --json
rush codeql results.sarif --json
rush contract pact-summary.json --json
```

### Mode B: Live Execution Mode
When running the engine live from Rush, supply the explicit permission flag:
```bash
rush mutation src/ --allow-slow --json
rush e2e e2e/ --allow-browser --json
rush ai-eval prompts/ --allow-slow --json
rush load load-test.js --allow-network --json
```

---

## 3. Generating Standalone HTML & SARIF Reports

Rush allows exporting rich visual and machine-readable artifacts from any check:

```bash
# Export interactive HTML inspection report
rush review . --export-html artifacts/review.html

# Export SARIF 2.1.0 report for GitHub Security or IDEs
rush security . --export-sarif artifacts/security.sarif
```

See [Permissions Specification](../safety/permissions.md) and [Result Reference](../reference/result-reference.md).
