# Changelog

All notable changes to Rush are documented here.

## Unreleased — 0.2.0

### Added

- A complete audience-separated documentation system covering installation,
  first run, user workflows, tutorials, command/result/configuration/engine/MCP
  references, integrations, safety/privacy, contributor development, maintainer
  runbooks, ADRs, examples, troubleshooting, and release operations.
- Explicit capability-maturity documentation for all 33 commands and 27 engine
  entries, including guarded placeholders and incomplete CLI permission/input
  surfaces.
- Catalog-validated per-tool `rush.toml` configuration, example configuration,
  and dedicated configuration, engine, and tool-catalog references.
- Experimental `semantic-drift` detection with explicit browser/slow-run
  execution guards and structured skipped defaults.
- Best-effort deterministic language routing for Go, Rust, Ruby, JVM, Swift,
  PHP, .NET, Elixir, Dart, Scala, and Nix markers across lint/type/test flows.
- Non-mutating developer-workflow tools: `commit-msg`, local `ci` workflow
  inspection, and dry-run-only `release` planning.
- Optional `commitlint` discovery metadata and opt-in pre-commit guidance.
- Catalog metadata, canonical result extensions, deterministic multi-engine
  aggregation, and catalog-driven CLI/MCP transport foundations.
- v0.2 scope, engine-discovery policy, safety guards, and capability
  traceability documentation.
- Contained Phase 04 test-quality report importers for coverage (coverage.py
  JSON, LCOV, Cobertura XML), mutation, property, flaky JUnit, Pact contract,
  snapshot, fuzz, and load evidence, with truthful importer-only documentation.
- Contained Phase 05 CodeQL SARIF 2.1.0 import: explicit local report evidence
  only, with engine identity, malformed-report, and target-containment checks;
  Rush never runs CodeQL, builds a database, or downloads query packs.
- Phase 06 read-only capability inventory and deterministic non-browser
  planning. States distinguish local configuration, PATH discovery, report
  applicability, explicit browser/feasibility blocks, and missing prerequisites
  without running or version-probing an engine.
- ADR-0002 review-evidence lifecycle: deterministic fingerprints, provenance,
  `unknown`/`existing`/`new` freshness, serial child-status retention, partial
  result labeling, and explicit in-memory baseline comparison. No baseline file
  is created or updated by default.
- Phase 07 explicit execution permission framework (`--allow-network`,
  `--allow-download`, `--allow-cache-write`, `--allow-build`, `--allow-slow`,
  `--allow-artifact-write`, `--allow-browser`) and dual-mode evidence reporting
  across all test quality, security, and build tools.
- Phase 07 reference adapter promotions for 15 tools and security scanners
  (Semgrep, Lychee, Trivy, Grype, Cosign, Kubeconform) with offline-safe defaults.
- Phase 08 browser runtime evidence subsystem (Playwright, axe-core, semantic drift,
  E2E, visual comparison) with stdio process isolation and permission gates.
- Phase 09 AI, LLM & Agentic Systems Safety: `rush ai-eval <path>` CLI and FastMCP
  tool with adapters for Promptfoo, Garak, DeepEval, and Guardrails.
- Phase 10 Modern SAST, Privacy & Deep Secret Detection: adapters for Bearer (privacy/PII data flow),
  TruffleHog (high-entropy/verified secrets), Horusec (polyglot SAST), Secretlint,
  and detect-secrets with normalized keyword redaction.
- Phase 11 Supply Chain Security, Attestation & Governance: adapters for OpenSSF Scorecard,
  ScanCode (legal license/copyleft), SLSA Verifier (provenance attestation), GUAC (supply chain graph),
  and pip-licenses (Python package licensing).
- Phase 12 Cloud-Native, Kubernetes & Policy-as-Code: adapters for Terrascan (OPA Rego IaC),
  Kube-score (Kubernetes manifest reliability), Conftest (custom OPA policy testing),
  Polaris (workload security configuration), and KubeLinter.
- Phase 13 API Security, Contract Evolution & Schema Fuzzing: adapters for Schemathesis (property-based API fuzzing),
  Zally (REST API design linter), GraphQL-Inspector (schema breaking changes), Cherrybomb (OpenAPI OWASP Top 10),
  and Newman (Postman CLI scenario runner).
- Phase 14 Architecture, Code Modernization & Software Sustainability: adapters for Dependency-Cruiser
  (architectural boundary/cycles), Refurb (Python idiom modernization), Biome (fast JS/TS linter/formatter),
  Scaphandre (energy and carbon estimation), FawltyDeps (Python import/dependency auditor), and Ts-prune (unused TS exports).
- Phase 15 Modern Web Standards, Accessibility & Safe DAST: adapters for Pa11y (WCAG 2.1 accessibility),
  HTML-Validate (W3C HTML), Lighthouse (Core Web Vitals/SEO), OWASP ZAP (DAST vulnerability scan),
  Deadfinder (404 route finder), Broken-Link-Checker (recursive link audit), and PageSpeed.
- Phase 16 Advanced Polyglot Mutation Testing & Fault Injection: adapters for Stryker Mutator (JS/TS/C#),
  Cosmic Ray (Python), Infection (PHP AST mutation), Pitest (JVM bytecode mutation), and Cargo-mutants (Rust).
- Phase 17 UI/UX, Visual Regression & Web Asset Optimization: adapters for Lost Pixel (Storybook diff),
  BackstopJS (multi-viewport responsive visual testing), Stylelint (CSS/SCSS linter), A11yWatch (crawler),
  Squoosh (image compression), Critical (CSS extraction), and Font-Spider (glyph compression).
- Phase 18 Advanced AST Linters, Pattern Matchers & Database Schemas: adapters for ast-grep (Tree-sitter AST queries),
  Flake8-Bugbear (Python AST subtle bug finder), MegaLinter (universal polyglot orchestrator), Comby (syntactic pattern matcher),
  Atlas (declarative schema migration safety), Squawk (PostgreSQL migration lock linter), and Prisma-lint (Prisma ORM convention linter).
- Phase 19 Documentation Style, Performance, Protocols & Vibecoder Quality Guardrails: adapters for Vale (prose style),
  CSpell (code spell checker), Alex (inclusive language), Readability (Flesch-Kincaid prose analyzer), RedPen (technical vocabulary),
  No-Jargon (corporate buzzwords), Markdown-Unfluff (AI repetition cleaner), Memray (Python memory profiler), Statoscope (bundle analyzer),
  Bloaty (binary footprint dissector), Buf (Protobuf linter), Dockle (container CIS benchmark), wasm-tools (WebAssembly validator),
  PyClean (cache cleaner), Diff-Cover (diff coverage threshold), Git-Guard (working tree hygiene), Semantic-Release (automated release calculator),
  PR-Agent (PR diff summary), Safe-Env (environment secret sanity), Wait-On (service readiness poller), and NCU (dependency freshness).

### Changed

- Reworked the root README into product onboarding and corrected stale result
  field names, configuration-consumer claims, model-review claims, and advanced
  command examples against the implementation and generated CLI help.
- Shared lint/format source discovery and status precedence now use the routing
  module rather than duplicated per-tool helpers.

## 0.1.0-alpha — 2026-08-17

### Added

- `rush` CLI commands for deterministic `review`, engine-backed `lint`,
  check-only `format`, `test`, and `security`.
- Local stdio MCP server via `rush mcp serve`, exposing the same five canonical
  tool implementations as the CLI.
- Python engines: Ruff, pytest, and pip-audit; JS/TS engines: ESLint, Prettier,
  Vitest, and npm audit.
- Structured ToolResult output and `--json` CLI output.
- MCP setup guide, real stdio protocol integration test, and NDJSON stderr
  diagnostics controlled by `RUSH_LOG_LEVEL`.

### Fixed

- Venv-local engine resolution takes precedence over polluted PATH entries.
- External engines cannot inherit or consume MCP JSON-RPC stdin.
- pip-audit 2.10 `dependencies` JSON envelopes normalize into security
  findings.
