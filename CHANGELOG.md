# Changelog

All notable changes to Rush are documented here.

## [0.3.0] - 2026-09-03

### Fixed
- **ToolResult Schema Kernel & Vocabulary Reconciliation (Finding R-011)**: Implemented canonical `ToolResultV1` and `FindingV1` contracts in `src/rush/contracts/results.py`. Reconciled finding severity vocabulary to canonical `info`, `warning`, `error` with deterministic legacy mapping (`warn`->`warning`, `fail`->`error`), and strictly rejected unmappable values with structured `ValidationErrorV1(code="INVALID_SEVERITY")` to eliminate silent default coercion. Unknown top-level keys are rejected with `UNKNOWN_TOP_LEVEL_KEY` while non-core properties are namespaced within `extensions`. Output serialization is byte-deterministic with compact separators and sorted keys, preceded by Phase 53 sanitization.
- **Public Operations Contract Reconciliation**: Formalized `BaseOperationAdapter` hierarchy and `OperationRegistry` in `src/rush/contracts/operations.py`, reconciling 100% of the 146 operations from `governance/public-operations.toml` (`67 tool`, `62 admin`, `17 service`). Ensured tools target `ToolResultV1`, admin commands target named admin contracts, and service protocol methods (`initialize`, `tools/list`) remain unwrapped JSON-RPC protocol frames.
- **Universal Recursive Sanitization & Write Boundaries (Finding R-002)**: Implemented recursive `sanitize_value` in `src/rush/safety/redactor.py` covering dictionary values AND keys, sequences, strings, and exceptions. Colliding redacted keys are deterministically suffixed with `__collision_{i}` to eliminate silent data loss. Output generators (SARIF, HTML, ResultCache, CLI JSON) and persistent disk writers (governance synchronizers, mesh locks, security audit logs, SQLite patch memory, session flights, preferences, invariant graphs, attestations, IAM policies, and benchmarks) now enforce deep sanitization before writes. Subprocess outputs are sanitized strictly *before* character truncation.
- **Fail-Safe Exception Diagnostics & Transport Purity (Finding R-008)**: Corrected `LogRecord.exc_info` tuple formatting in `NdjsonHandler.emit` (`src/rush/logging.py`) so exception tracebacks are formatted safely without AttributeError crashes. Applied secret redaction to log messages and stack traces, added a structured stderr fallback emitter on unexpected format failures, and guaranteed that standard logging operations never pollute `sys.stdout`.
- **Package Identity & Installed Artifacts (Finding R-001)**: Eliminated all 74 occurrences of invalid `src.rush` imports across 15 production files and 14 test files in favor of canonical `rush` imports. Wheel and sdist packages now install and start cleanly in scrubbed virtual environments outside the repository checkout with zero origin leakage.
- **Pytest Collection Isolation**: Removed root `.` from `pyproject.toml` `pythonpath`, isolating test discovery strictly to `src/` to prevent repository root leakage into import paths.
- **Version Authority Consolidation (Finding R-012)**: Replaced disparate hardcoded version literals across providers (Anthropic, OpenAI), SARIF exporters, TypeScript generators, scaffolder templates, PR synthesizers, and TUI footers with a single version authority derived from `importlib.metadata.version("rush-cli")` in `src/rush/__init__.py`.

### Added
- **AtomicFile & Physical Containment I/O Kernel (Phase 55)**:
  - `src/rush/io/physical_paths.py`: `PhysicalRoot` and `ContainmentError` enforcing strict physical workspace boundary containment defeating symlinks, parent traversal (`..`), Windows directory junctions, and reparse points (`stat.FILE_ATTRIBUTE_REPARSE_POINT`).
  - `src/rush/io/atomic_file.py`: `AtomicFile` guaranteeing fail-closed atomic replacement via same-directory unique temporary files (`.rush_tmp_`), explicit `flush()`, `os.fsync()` durability, and manager-owned cleanup accepting exclusively sanitized contracts (`SanitizedBytes`, `SanitizedJsonValue`, `SanitizationResult`).
  - `src/rush/io/verifier_record.py`: `VerifierRecord` and `VerifierError` providing one-way non-recoverable capability verification using PBKDF2-HMAC-SHA256 (100k rounds, 32-byte salt), constant-time `hmac.compare_digest`, and Shannon entropy validation (>= 2.5 bits/symbol).

- **Remediation Scope & Release Gates (Phase 51)**:
  - First-party coverage boundary classifying 1,090 repository files (`governance/first-party-coverage.toml`).
  - Public operations inventory reconciling 129 Click subcommands and 73 FastMCP tools (`governance/public-operations.toml`).
  - Engine support taxonomy covering 19 families with strict skip prohibitions (`governance/engine-support.toml`).
  - Cross-phase remediation contracts mapping findings R-001 through R-016 (`governance/remediation-contracts.toml`).
  - Independent installed artifact probe harness (`scripts/probe_installed_artifacts.py`) integrated into CI matrix and release workflows.
- **Phase 52 Contract Test Suites**:
  - `tests/test_phase52_package_identity.py`: Verifies zero `src.rush` imports and pytest collection isolation.
  - `tests/test_phase52_version_contract.py`: Verifies metadata version resolution and consumer alignment.
  - `tests/test_phase52_installed_artifacts.py`: Verifies wheel and sdist installation and execution parity from external working directories.
- **Phase 53 Contract Test Suites**:
  - `tests/test_phase53_sanitizer_contract.py`: Verifies deep recursive sanitization across values, keys, collisions, URL credentials, and input immutability.
  - `tests/test_phase53_output_boundaries.py`: Verifies pre-truncation subprocess sanitization and SARIF/HTML/Cache output boundaries.
  - `tests/test_phase53_governance_writers.py`: Verifies sanitization of governance configs, agent sync rules, tamper hooks, and MCP mesh lock managers on success and abort.
  - `tests/test_phase53_state_writers.py`: Verifies sanitization of 25 state, security, and release writers on success and abort.
  - `tests/test_phase53_logging_diagnostics.py`: Verifies redacted NDJSON exception diagnostics, stdout purity, and structured formatting fallbacks.
- **Phase 54 Contract Test Suites**:
  - `tests/test_phase54_result_schema.py`: Verifies 8 core fields, `FindingV1` canonical severities, namespaced extensions, unknown key rejection, byte-deterministic serialization, legacy mappings, and structured validation errors.
  - `tests/test_phase54_operation_adapters.py`: Verifies `ToolOperationAdapter`, `AdminOperationAdapter`, `ServiceOperationAdapter`, and 100% manifest reconciliation across 146 operations.

## [0.2.0] - 2026-08-21

### Added

- Phase 20–40 Comprehensive Architecture:
  - Phase 20: AI anti-slop detection (`rush slop`), modular boundaries (`TachEngine`), and AST-level continuous sensors.
  - Phase 21: Incremental cache with TTL, content hash validation, and Git scoping (`rush cache`).
  - Phase 22: Unified automated remediation framework (`rush fix`).
  - Phase 23: Sanitized stack onboarding, interactive wizard, and config generation (`rush init`, `rush stack`).
  - Phase 24: Hardened workflow suites (`rush check`, `rush ci`) and environment diagnostics (`rush doctor`, `rush capabilities`).
  - Phase 25: Real-time multi-threaded file system watcher with debounce (`rush watch`).
  - Phase 26: Monorepo, workspace boundary detection, and affected-package graphs (`rush workspace`).
  - Phase 27: Authenticated in-memory CSRF/DNS-rebinding hardened dashboard (`rush dashboard`) and terminal UI (`rush tui`).
  - Phase 28: Trust-gated plugin system, SHA-256 integrity verification, and agent skills (`rush plugins`, `rush skills`).
  - Phase 29: Isolated AI patch remediation with sandbox rollbacks and session memory (`rush patch`, `rush memory`).
  - Phase 30: Standalone packaging, semver calculation, changelog generation, and CI scaffolding (`rush release`).
  - Phase 31: Agent safety interceptor and isolated worktree sandboxing (`rush safety`).
  - Phase 32: Token economy counter, prompt compressor, outline diet, and cache advisor (`rush token`).
  - Phase 33: Full-stack type synchronization for ORM models, OpenAPI schemas, and environment parity (`rush sync`).
  - Phase 34: Codebase hygiene, dead code removal, unused import cleanup, and AST merge resolution (`rush hygiene`).
  - Phase 35: Polyglot AST slicing and semantic codegraph exploration (`rush codegraph`).
  - Phase 36: Frontend bundle size, dead asset detection, and barrel file optimization (`rush bundle`).
  - Phase 37: Git churn hotspots, bus-factor calculation, and structural coupling metrics (`rush hotspots`).
  - Phase 38: Multi-agent governance, rule compiler, and scaffold generator (`rush governance`).
  - Phase 39: Sub-second Git pre-commit intelligence, trojan source scanner, and hook guard (`rush hook`).
  - Phase 40: Multi-model consensus reconciliation (`rush consensus`) and unified quality scorecard (`rush score`).
- A complete audience-separated documentation system covering installation,
  first run, user workflows, tutorials, command/result/configuration/engine/MCP
  references, integrations, safety/privacy, contributor development, maintainer
  runbooks, ADRs, examples, troubleshooting, and release operations across 188 documentation files.

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
