# Engine compatibility and integration contract

A catalog command is not automatically a live scanner. Rush labels every tool with one maturity:

- `real_adapter`: Rush discovers a local binary, invokes a bounded list-only command, parses output, and has fixture-backed reference tests.
- `importer`: imports structured reports with fallback to guarded execution under explicit permissions.
- `browser_runtime`: browser-dependent work guarded behind explicit `--allow-browser` and `--allow-slow` permissions.
- `catalog_only`: a visible command with no claimed live engine execution.
- `guarded_placeholder`: intentionally returns `skipped` until a future adapter/importer meets the contract.

## Explicit Execution Permissions (Phase 07.0)

Rush enforces execution permissions that are denied by default:
- `--allow-network`: permits live network communication.
- `--allow-download`: permits fetching vulnerability databases or schemas.
- `--allow-cache-write`: permits writing engine rule caches.
- `--allow-build`: permits project builds or database compilation (e.g. CodeQL).
- `--allow-slow`: permits long-running test, mutation, fuzz, contract, or drift executions.
- `--allow-artifact-write`: permits mutating or generating baseline artifacts and reports.
- `--allow-browser`: permits launching browser engines (Playwright, Chromium/WebKit/Firefox).

Every tool returns structured `metadata.execution` capturing:
- `mode`: `"imported"`, `"executed"`, or `"artifact"`
- `requested_permissions`: dictionary of required permissions
- `granted_permissions`: dictionary of permissions supplied by caller
- `producer`: engine/producer binary name
- `report_path`: path to imported report if applicable

## Engine Reference Adapters and Matrix

| Engine | Tool | Tested baseline / contract | Reference test suite |
|---|---|---|---|
| Ruff | `lint`, `format` | Ruff 0.6+ | `tests/test_ruff_reference.py` |
| ESLint | `lint` | ESLint 9.x | `tests/test_eslint_reference.py` |
| Prettier | `format` | Prettier 3.x (`--check` default) | `tests/test_prettier_reference.py` |
| pytest | `test` | pytest 8.x | `tests/test_pytest_reference.py` |
| Vitest | `test` | Vitest 1.x / 2.x | `tests/test_vitest_reference.py` |
| mypy | `typecheck` | mypy 1.10+ | `tests/test_mypy_reference.py` |
| tsc | `typecheck` | TypeScript 5.x | `tests/test_tsc_reference.py` |
| Vulture | `dead` | Vulture 2.11+ | `tests/test_vulture_reference.py` |
| Knip | `dead` | Knip 5.x | `tests/test_knip_reference.py` |
| Radon | `complexity` | Radon 6.0+ | `tests/test_radon_reference.py` |
| jscpd | `complexity` | jscpd 3.x | `tests/test_jscpd_reference.py` |
| sloppylint | `slop` | sloppylint 0.2+ | `tests/test_sloppylint_reference.py` |
| djLint | `templates` | djLint 1.34+ | `tests/test_djlint_reference.py` |
| commitlint | `commit-msg` | commitlint 19.x | `tests/test_commitlint_reference.py` |
| cdxgen | `sbom` | cdxgen 10.x | `tests/test_cdxgen_reference.py` |
| Gitleaks | `secrets` | Gitleaks 8.18+ (redacted findings) | `tests/test_gitleaks_reference.py` |
| pip-audit | `security` | pip-audit 2.7+ | `tests/test_pip_audit_reference.py` |
| npm-audit | `security` | npm 10.x | `tests/test_npm_audit_reference.py` |
| OSV-Scanner (`osv-scanner`) | `security` | OSV-Scanner 1.7+ | `tests/test_osv_reference.py` |
| Semgrep | `security` | Semgrep 1.80+ (offline auto config default) | `tests/test_semgrep_reference.py` |
| Lychee | `markdown` | Lychee 0.15+ (offline link check default) | `tests/test_lychee_reference.py` |
| Trivy | `security` | Trivy 0.55+ (offline scan default) | `tests/test_trivy_reference.py` |
| Grype | `security` | Grype 0.79+ (offline directory scan) | `tests/test_grype_reference.py` |
| Cosign | `release` | Cosign 2.4+ (local blob verification) | `tests/test_cosign_reference.py` |
| Kubeconform | `iac` | Kubeconform 0.6+ | `tests/test_kubeconform_reference.py` |
| Hadolint | `containerfile` | Hadolint 2.12+ (isolated config) | `tests/test_hadolint_reference.py` |
| actionlint | `actions` | actionlint 1.7+ (isolated config) | `tests/test_actionlint_reference.py` |
| markdownlint | `markdown` | markdownlint-cli 0.41+ | `tests/test_markdownlint_reference.py` |
| Spectral | `yaml` | Spectral 6.11+ | `tests/test_spectral_reference.py` |
| SQLFluff | `sql` | SQLFluff 3.0+ | `tests/test_sqlfluff_reference.py` |
| TFLint | `iac` | TFLint 0.51+ | `tests/test_tflint_reference.py` |
| Checkov | `iac` | Checkov 3.2+ | `tests/test_checkov_reference.py` |
| Playwright | `e2e` | Playwright 1.46+ (headless, `--allow-browser`) | `tests/test_playwright_reference.py` |
| axe-core | `semantic-drift` | axe 4.9+ (accessibility DOM check) | `tests/test_axe_reference.py` |
| Promptfoo | `ai-eval` | promptfoo 0.90+ | `tests/test_promptfoo_reference.py` |
| Garak | `ai-eval` | garak 0.10+ | `tests/test_garak_reference.py` |
| DeepEval | `ai-eval` | deepeval 0.21+ | `tests/test_deepeval_reference.py` |
| Guardrails | `ai-eval` | guardrails-ai 0.5+ | `tests/test_guardrails_reference.py` |
| Bearer | `security` | bearer 1.45+ (privacy data flow) | `tests/test_bearer_reference.py` |
| TruffleHog | `secrets` | trufflehog 3.80+ (verified detector) | `tests/test_trufflehog_reference.py` |
| Horusec | `security` | horusec 2.8+ (multi-language SAST) | `tests/test_horusec_reference.py` |
| Secretlint | `secrets` | secretlint 8.2+ | `tests/test_secretlint_reference.py` |
| detect-secrets | `secrets` | detect-secrets 1.4+ | `tests/test_detect_secrets_reference.py` |
| Scorecard | `ci` | scorecard 4.12+ (OpenSSF supply chain) | `tests/test_scorecard_reference.py` |
| ScanCode | `sbom` | scancode-toolkit 32.x (legal license) | `tests/test_scancode_reference.py` |
| SLSA Verifier | `release` | slsa-verifier 2.5+ (provenance check) | `tests/test_slsa_verifier_reference.py` |
| GUAC | `sbom` | guacone 0.8+ (supply chain graph) | `tests/test_guac_reference.py` |
| pip-licenses | `sbom` | pip-licenses 4.3+ (Python license audit) | `tests/test_pip_licenses_reference.py` |
| Terrascan | `iac` | terrascan 1.18+ (OPA Rego IaC) | `tests/test_terrascan_reference.py` |
| Kube-score | `iac` | kube-score 1.18+ (K8s reliability) | `tests/test_kube_score_reference.py` |
| Conftest | `iac` | conftest 0.55+ (structured policy) | `tests/test_conftest_reference.py` |
| Polaris | `iac` | polaris 8.5+ (K8s configuration) | `tests/test_polaris_reference.py` |
| KubeLinter | `iac` | kube-linter 0.6+ (K8s security) | `tests/test_kube_linter_reference.py` |
| Schemathesis | `contract` | schemathesis 3.36+ (API property test) | `tests/test_schemathesis_reference.py` |
| Zally | `yaml` | zally 2.1+ (REST API design linter) | `tests/test_zally_reference.py` |
| GraphQL-Inspector | `lint` | graphql-inspector 3.5+ (schema diff) | `tests/test_graphql_inspector_reference.py` |
| Cherrybomb | `security` | cherrybomb 1.1+ (OpenAPI OWASP) | `tests/test_cherrybomb_reference.py` |
| Newman | `test` | newman 6.2+ (Postman CLI runner) | `tests/test_newman_reference.py` |
| Depcruise | `complexity` | dependency-cruiser 16.4+ (architecture) | `tests/test_depcruise_reference.py` |
| Refurb | `lint` | refurb 2.0+ (Python modernization) | `tests/test_refurb_reference.py` |
| Biome | `lint` | biome 1.8+ (fast JS/TS linter) | `tests/test_biome_reference.py` |
| Scaphandre | `complexity` | scaphandre 0.5+ (energy profiling) | `tests/test_scaphandre_reference.py` |
| FawltyDeps | `dead` | fawltydeps 0.15+ (Python import auditor) | `tests/test_fawltydeps_reference.py` |
| Ts-prune | `dead` | ts-prune 0.10+ (unused TS exports) | `tests/test_ts_prune_reference.py` |
| Pa11y | `security` | pa11y 8.0+ (WCAG accessibility) | `tests/test_pa11y_reference.py` |
| HTML-Validate | `templates` | html-validate 8.19+ (W3C HTML) | `tests/test_html_validate_reference.py` |
| Lighthouse | `visual` | lighthouse 12.0+ (Web Vitals/SEO) | `tests/test_lighthouse_reference.py` |
| OWASP ZAP | `security` | zap-cli 2.14+ (DAST vulnerability scan) | `tests/test_zap_reference.py` |
| Deadfinder | `security` | deadfinder 0.4+ (404 route scanner) | `tests/test_deadfinder_reference.py` |
| BLC | `lint` | broken-link-checker 0.7+ (broken hyperlinks) | `tests/test_blc_reference.py` |
| PageSpeed | `visual` | psi 5.0+ (real-world web performance) | `tests/test_pagespeed_reference.py` |
| Stryker | `mutation` | stryker 8.2+ (JS/TS/C# mutation) | `tests/test_stryker_reference.py` |
| Cosmic Ray | `mutation` | cosmic-ray 8.3+ (Python mutation) | `tests/test_cosmic_ray_reference.py` |
| Infection | `mutation` | infection 0.29+ (PHP mutation) | `tests/test_infection_reference.py` |
| Pitest | `mutation` | pitest 1.15+ (Java/Kotlin mutation) | `tests/test_pitest_reference.py` |
| Cargo-mutants | `mutation` | cargo-mutants 24.7+ (Rust mutation) | `tests/test_cargo_mutants_reference.py` |
| Lost Pixel | `visual` | lost-pixel 3.19+ (Storybook visual diff) | `tests/test_lost_pixel_reference.py` |
| BackstopJS | `visual` | backstopjs 6.3+ (responsive visual regression) | `tests/test_backstop_reference.py` |
| Stylelint | `lint` | stylelint 16.8+ (CSS/SCSS linter) | `tests/test_stylelint_reference.py` |
| A11yWatch | `security` | a11ywatch 0.10+ (accessibility crawler) | `tests/test_a11ywatch_reference.py` |
| Squoosh | `format` | squoosh-cli 0.7+ (image compression) | `tests/test_squoosh_reference.py` |
| Critical | `format` | critical 7.1+ (critical CSS extraction) | `tests/test_critical_reference.py` |
| Font-Spider | `format` | font-spider 1.3+ (font compression) | `tests/test_font_spider_reference.py` |
| ast-grep | `lint` | ast-grep 0.25+ (Tree-sitter AST structural query) | `tests/test_ast_grep_reference.py` |
| Flake8-Bugbear | `lint` | flake8-bugbear 24.4+ (Python AST design bug finder) | `tests/test_flake8_bugbear_reference.py` |
| MegaLinter | `lint` | megalinter 8.0+ (universal polyglot orchestrator) | `tests/test_megalinter_reference.py` |
| Comby | `lint` | comby 1.8+ (syntactic structural pattern matcher) | `tests/test_comby_reference.py` |
| Atlas | `sql` | atlas 0.26+ (database migration safety linter) | `tests/test_atlas_reference.py` |
| Squawk | `sql` | squawk 0.27+ (PostgreSQL migration lock linter) | `tests/test_squawk_reference.py` |
| Prisma-lint | `lint` | prisma-lint 0.8+ (Prisma schema model conventions) | `tests/test_prisma_lint_reference.py` |
| Vale | `lint` | vale 3.5+ (syntax-aware prose style linter) | `tests/test_vale_reference.py` |
| CSpell | `lint` | cspell 8.13+ (code-aware identifier spell checker) | `tests/test_cspell_reference.py` |
| Alex | `lint` | alex 11.0+ (inclusive language linter) | `tests/test_alex_reference.py` |
| Readability | `complexity` | readability-cli 2.1+ (Flesch-Kincaid prose analyzer) | `tests/test_readability_reference.py` |
| RedPen | `lint` | redpen 1.10+ (technical documentation vocabulary) | `tests/test_redpen_reference.py` |
| No-Jargon | `lint` | no-jargon 0.2+ (corporate buzzword detector) | `tests/test_no_jargon_reference.py` |
| Markdown-Unfluff | `lint` | markdown-unfluff 0.5+ (AI filler pattern cleaner) | `tests/test_markdown_unfluff_reference.py` |
| Memray | `complexity` | memray 1.13+ (Python memory allocation profiler) | `tests/test_memray_reference.py` |
| Statoscope | `complexity` | statoscope 5.28+ (JS bundle weight & duplicate auditor) | `tests/test_statoscope_reference.py` |
| Bloaty | `complexity` | bloaty 1.1+ (binary size & section analyzer) | `tests/test_bloaty_reference.py` |
| Buf | `lint` | buf 1.40+ (Protobuf & gRPC schema linter) | `tests/test_buf_reference.py` |
| Dockle | `security` | dockle 0.4+ (container CIS benchmark linter) | `tests/test_dockle_reference.py` |
| wasm-tools | `lint` | wasm-tools 1.218+ (WebAssembly binary validator) | `tests/test_wasm_tools_reference.py` |
| PyClean | `format` | pyclean 3.0+ (bytecode cache cleaner) | `tests/test_pyclean_reference.py` |
| Diff-Cover | `coverage` | diff-cover 9.1+ (diff-only test coverage threshold) | `tests/test_diff_cover_reference.py` |
| Git-Guard (`git-guard`) | `lint` | git 2.46+ (working tree & untracked file hygiene) | `tests/test_git_guard_reference.py` |
| Semantic-Release | `release` | semantic-release 24.1+ (automated version bumping) | `tests/test_semantic_release_reference.py` |
| PR-Agent | `review` | pr-agent 0.20+ (PR diff summary generator) | `tests/test_pr_agent_reference.py` |
| Safe-Env | `security` | safe-env 0.4+ (environment secret sanity checker) | `tests/test_safe_env_reference.py` |
| Wait-On | `e2e` | wait-on 7.2+ (port & HTTP health endpoint poller) | `tests/test_wait_on_reference.py` |
| NCU | `security` | npm-check-updates 16.14+ (dependency upgrade checker) | `tests/test_ncu_reference.py` |
| aislop | `slop` | aislop 0.4+ (AST AI anti-pattern scanner) | `tests/test_aislop_reference.py` |
| Tach (`tach`) | `complexity` | tach 0.8+ (modular boundary checker) | `tests/test_tach_reference.py` |
| Undercover (`undercover`) | `coverage` | undercover 0.6+ (git diff coverage checker) | `tests/test_undercover_reference.py` |
| Medusa (`medusa`) | `security` | medusa 1.0+ (agent hook & prompt injection auditor) | `tests/test_medusa_reference.py` |
| Pyrefly (`pyrefly`) | `typecheck` | pyrefly 0.1+ (fast Rust Python type checker) | `tests/test_pyrefly_reference.py` |
| Globstar (`globstar`) | `lint` | globstar 0.3+ (Tree-Sitter custom pattern linter) | `tests/test_globstar_reference.py` |
| Clines (`clines`) | `complexity` | clines 0.2+ (token density & complexity analyzer) | `tests/test_clines_reference.py` |
| Cejel (`cejel`) | `release` | cejel 0.1+ (offline trust certificate verifier) | `tests/test_cejel_reference.py` |
| Sentrux (`sentrux`) | `complexity` | sentrux 0.5+ (codebase decay sensor) | `tests/test_sentrux_reference.py` |

## Browser Runtime Contract (Phase 08)

Browser runtime operations (`semantic-drift`, `e2e`, `visual`) strictly respect process boundaries:
- stdio JSON-RPC MCP transport is strictly isolated from child browser processes (`stdin=DEVNULL`).
- Explicit `--allow-browser` consent flag is required to launch browser runners.
- Long-running executions require `--allow-slow`.
- Baseline updates (e.g. `snapshot`, `visual` with `--accept`) require `--allow-artifact-write`.
