# Engine directory

An **engine** is an optional helper executable Rush knows how to call. Rush does not install engines. Applicability is based on file extensions and project markers; an absent engine produces `skipped` with an install hint.

Python install commands work on Windows, macOS, and Linux inside an appropriate Python environment. npm commands are cross-platform when Node/npm is installed. For standalone binaries, use the upstream project's release instructions for your platform; Rush's catalog intentionally says `install ...` rather than inventing an unverified package-manager command.

## Python and JavaScript/TypeScript

| Engine | What / who | Commands | Catalog install hint | Applicability and recovery |
|---|---|---|---|---|
| Ruff (`ruff`) | Python lint and format | `lint`, `format` | `pip install ruff` | `.py/.pyi`, `pyproject.toml`; verify `ruff --version`. |
| ESLint (`eslint`) | JS/TS lint | `lint` | `npm install -g eslint` | JS/TS extensions, `package.json`; project config may be required. Prefer project-local install when team versions matter. |
| Prettier (`prettier`) | JS/TS/data formatting | `format` | `npm install -g prettier` | JS/TS/JSON/YAML/Markdown and `package.json`; verify project configuration. |
| pytest (`pytest`) | Python tests | `test`, `pbt`, `flaky`, `snapshot`, `coverage` | `pip install pytest` | Python project marker; supports executed test quality modes under `--allow-slow`. |
| Vitest (`vitest`) | JS/TS tests | `test` | `npm install -D vitest` | JS/TS and `package.json`; verify `npx vitest --version`. |
| pip-audit (`pip-audit`) | Python dependency advisories | `security` | `pip install pip-audit` | `pyproject.toml`/`requirements.txt`; lock/install metadata must be usable. |
| npm audit (`npm-audit`, binary `npm`) | npm dependency advisories | `security` | ships with npm | `package.json`; requires npm and appropriate lock/dependency metadata. |
| mypy (`mypy`) | Python types | `typecheck` | `pip install mypy` | Python files/project; project plugins/types may be needed. |
| TypeScript (`tsc`) | JS/TS types | `typecheck` | `npm install -D typescript` | JS/TS and `package.json`; normally needs `tsconfig.json`. |
| Vulture (`vulture`) | Python dead code | `dead` | `pip install vulture` | Python files/project; treat findings as candidates. |
| Knip (`knip`) | JS/TS unused files/exports/deps | `dead` | `npm install -D knip` | JS/TS project; configure framework entry points to reduce false positives. |
| Radon (`radon`) | Python complexity metrics | `complexity` | `pip install radon` | Python files; metrics are evidence, not an automatic design verdict. |
| jscpd (`jscpd`) | JS/TS duplication | `complexity` | `npm install -D jscpd` | JS/TS project; generated trees are excluded by Rush collectors. |
| sloppylint (`sloppylint`) | Python code-noise heuristics | `slop` | `pip install sloppylint` | Python files; JS/TS may use a built-in fallback. Do not infer authorship. |

## AI, LLM & Agent Safety (Phase 09)

| Engine | What / who | Command | Catalog install hint | Applicability and recovery |
|---|---|---|---|---|
| Promptfoo (`promptfoo`) | LLM redteaming and evaluation | `ai-eval` | `npm install -g promptfoo` | Prompts, agent configs, `promptfooconfig.yaml`; evaluate prompt assertions and redteam attacks. |
| Garak (`garak`) | LLM vulnerability scanner | `ai-eval` | `pip install garak` | LLM endpoints and prompt pipelines; probes for jailbreaks, prompt injection, and hallucination. |
| DeepEval (`deepeval`) | Unit testing for LLMs/RAG | `ai-eval` | `pip install deepeval` | Python test suites; evaluates faithfulness, answer relevancy, and hallucination metrics. |
| Guardrails (`guardrails`) | Policy and structure validator | `ai-eval` | `pip install guardrails-ai` | Guardrail specs, `.co` Colang files, Pydantic guardrail models; verifies runtime policy bounds. |

## Modern SAST & Deep Secret Detection (Phase 10)

| Engine | What / who | Command | Catalog install hint | Applicability and recovery |
|---|---|---|---|---|
| Bearer (`bearer`) | Privacy & PII data flow SAST | `security` | `install bearer` | Polyglot codebases; identifies sensitive data leaks, privacy violations, and OWASP Top 10 API risks. |
| TruffleHog (`trufflehog`) | High-entropy & verified secrets | `secrets` | `install trufflehog` | Git history and filesystems; 800+ detector types with live verification gating. |
| Horusec (`horusec`) | Multi-language static analyzer | `security` | `install horusec` | Polyglot codebases (Go, Java, Python, JS, TF, C#); comprehensive vulnerability scanning. |
| Secretlint (`secretlint`) | Fast pre-commit secret linter | `secrets` | `npm install -g secretlint` | Fast local workspace scanning for leaked tokens and private keys. |
| detect-secrets (`detect-secrets`) | Baseline-managed secret auditor | `secrets` | `pip install detect-secrets` | Uses `.secrets.baseline` to manage known vs new credentials. |

## Cloud-Native, Kubernetes & Policy-as-Code (Phase 12)

| Engine | What / who | Command | Catalog install hint | Applicability and recovery |
|---|---|---|---|---|
| Terrascan (`terrascan`) | OPA Rego IaC security linter | `iac` | `install terrascan` | Terraform and Kubernetes manifests; checks 500+ security policies. |
| Kube-score (`kube-score`) | Kubernetes reliability & security analyzer | `iac` | `install kube-score` | Kubernetes YAML files; evaluates pod affinity, security context, and limits. |
| Conftest (`conftest`) | Custom OPA Rego policy testing | `iac` | `install conftest` | Structured configuration files (YAML, JSON, TF); verifies custom policies. |
| Polaris (`polaris`) | Workload configuration auditor | `iac` | `install polaris` | Kubernetes workload definitions; identifies privilege escalation and security holes. |
| KubeLinter (`kube-linter`) | Kubernetes production readiness | `iac` | `install kube-linter` | Kubernetes manifests; flags missing readiness probes and service configs. |

## API Security, Contract Evolution & Schema Fuzzing (Phase 13)

| Engine | What / who | Command | Catalog install hint | Applicability and recovery |
|---|---|---|---|---|
| Schemathesis (`schemathesis`) | Property-based API contract fuzzer | `contract` | `pip install schemathesis` | OpenAPI / GraphQL specs; generates property tests to find 500s and contract violations. |
| Zally (`zally`) | RESTful API design quality linter | `yaml` | `install zally` | OpenAPI/Swagger specs; validates API design guidelines, casing, and semantics. |
| GraphQL-Inspector (`graphql-inspector`) | GraphQL schema diff & validator | `lint` | `npm install -g @graphql-inspector/cli` | GraphQL schemas; detects breaking changes and dead schema fields. |
| Cherrybomb (`cherrybomb`) | OpenAPI OWASP Top 10 validator | `security` | `install cherrybomb` | OpenAPI specifications; detects BOLA, broken authentication, and rate limiting issues. |
| Newman (`newman`) | Postman collection CLI runner | `test` | `npm install -g newman` | Postman collections; executes API scenario integration tests. |

## Architecture, Code Modernization & Software Sustainability (Phase 14)

| Engine | What / who | Command | Catalog install hint | Applicability and recovery |
|---|---|---|---|---|
| Dependency-Cruiser (`depcruise`) | Architectural boundary validator | `complexity` | `npm install -D dependency-cruiser` | JS/TS codebases; enforces architecture boundaries and detects circular dependencies. |
| Refurb (`refurb`) | Python modernization & elegance | `lint` | `pip install refurb` | Python codebases; suggests modern language idioms and cleaner stdlib APIs. |
| Biome (`biome`) | High-speed JS/TS linter and formatter | `lint` | `npm install -D @biomejs/biome` | JS/TS/JSON files; ultra-fast formatting and linting engine. |
| Scaphandre (`scaphandre`) | Energy consumption and carbon estimator | `complexity` | `install scaphandre` | Host metrics and RAPL; measures software power draw in Watts. |
| FawltyDeps (`fawltydeps`) | Python import and dependency auditor | `dead` | `pip install fawltydeps` | Python packages; finds undeclared imports and unused requirements. |
| Ts-prune (`ts-prune`) | TypeScript dead export finder | `dead` | `npm install -D ts-prune` | TypeScript projects; identifies unused module exports and dead interfaces. |

## Modern Web Standards, Accessibility & Safe DAST (Phase 15)

| Engine | What / who | Command | Catalog install hint | Applicability and recovery |
|---|---|---|---|---|
| Pa11y (`pa11y`) | Automated WCAG 2.1 AA/AAA accessibility | `security` | `npm install -g pa11y` | HTML files/URLs; evaluates contrast, ARIA, and markup semantics. |
| HTML-Validate (`html-validate`) | W3C HTML validator | `templates` | `npm install -D html-validate` | HTML/Vue/Svelte templates; detects malformed elements and missing tags. |
| Lighthouse (`lighthouse`) | Core Web Vitals & performance | `visual` | `npm install -g lighthouse` | Web URLs; audits LCP, CLS, FID, and SEO benchmarks under `--allow-browser`. |
| OWASP ZAP (`zap-cli`) | Dynamic Application Security Testing | `security` | `pip install zapcli` | Web endpoints; runs safe active/passive vulnerability scans under `--allow-network`. |
| Deadfinder (`deadfinder`) | Broken route & 404 crawler | `security` | `install deadfinder` | SPA web applications; crawls endpoints for broken links. |
| Broken-Link-Checker (`blc`) | Recursive anchor validator | `lint` | `npm install -g broken-link-checker` | HTML sites; verifies all internal and external hyperlinks. |
| PageSpeed (`pagespeed-insights`) | Real-world web performance | `visual` | `npm install -g psi` | Web endpoints; assesses performance metrics against real-world data. |

## Advanced Polyglot Mutation Testing & Fault Injection (Phase 16)

| Engine | What / who | Command | Catalog install hint | Applicability and recovery |
|---|---|---|---|---|
| Stryker (`stryker`) | JS/TS/C# mutation testing | `mutation` | `npm install -D @stryker-mutator/core` | JavaScript, TypeScript, C# projects; tests test suite resilience under `--allow-slow`. |
| Cosmic Ray (`cosmic-ray`) | Python mutation testing | `mutation` | `pip install cosmic-ray` | Python packages; injects AST faults to verify test coverage efficacy. |
| Infection (`infection`) | PHP AST mutation testing | `mutation` | `composer require --dev infection/infection` | PHP codebases; executes mutation testing against PHPUnit/Pest. |
| Pitest (`mvn org.pitest:pitest-maven`) | Java/Kotlin bytecode mutation | `mutation` | `install pitest` | JVM projects; tests branch and mutation coverage on bytecode. |
| Cargo-mutants (`cargo-mutants`) | Rust mutation testing | `mutation` | `cargo install cargo-mutants` | Rust crates; mutates AST expressions without cargo clean rebuilds. |

## UI/UX, Visual Regression & Web Asset Optimization (Phase 17)

| Engine | What / who | Command | Catalog install hint | Applicability and recovery |
|---|---|---|---|---|
| Lost Pixel (`lost-pixel`) | Storybook/Ladle visual diffing | `visual` | `npm install -D lost-pixel` | UI component stories; catches unintended visual regressions. |
| BackstopJS (`backstopjs`) | Responsive multi-viewport visual test | `visual` | `npm install -g backstopjs` | Web apps; captures multi-screen layout regressions under `--allow-browser`. |
| Playwright (`playwright`) | Headless browser end-to-end testing | `e2e`, `visual` | `npm install -D @playwright/test` | Web applications; requires `--allow-browser`. |
| Axe-core (`axe`) | Accessibility testing engine | `semantic-drift`, `security` | `npm install -D @axe-core/cli` | DOM/accessibility standards inspection under `--allow-browser`. |
| Semantic-drift (`semantic-drift`) | DOM and accessibility drift detection | `semantic-drift` | `rush semantic-drift` | Browser-driven correctness verification under `--allow-browser` and `--allow-slow`. |
| Stylelint (`stylelint`) | CSS/SCSS/CSS-in-JS linter | `lint` | `npm install -D stylelint` | CSS/SCSS/Less stylesheets; enforces style conventions and valid rules. |
| A11yWatch (`a11ywatch`) | Multi-page accessibility crawler | `security` | `npm install -g a11ywatch-cli` | Full websites; crawls site hierarchy for accessibility regressions. |
| Squoosh (`squoosh-cli`) | Web image compressor | `format` | `npm install -g @squoosh/cli` | PNG/JPG/WebP/AVIF images; compresses assets without perceptual quality loss. |
| Critical (`critical`) | Above-the-fold CSS inliner | `format` | `npm install -g critical` | HTML pages; extracts and inlines critical render path stylesheets. |
| Font-Spider (`font-spider`) | Web font glyph compressor | `format` | `npm install -g font-spider` | Font files; analyzes HTML to prune unused glyphs from web fonts. |

## Content and infrastructure

| Engine | What / who | Command | Catalog install hint | Applicability and recovery |
|---|---|---|---|---|
| markdownlint-cli (`markdownlint`) | Markdown rules | `markdown` | `npm install -D markdownlint-cli` | `.md/.mdx`; Rush uses owned contained config rather than custom rules. |
| Lychee (`lychee`) | Broken link checker | `markdown` | `install lychee` | `.md/.html`; offline checking by default; `--allow-network` for live URLs. |
| Actionlint (`actionlint`) | GitHub Actions workflows | `actions` | `install actionlint` | `.github/workflows`; download an upstream release for Windows/macOS/Linux and verify `actionlint -version`. |
| Spectral (`spectral`) | YAML/OpenAPI rules | `yaml` | `npm install -D @stoplight/spectral-cli` | `.yml/.yaml`; remote `$ref` is rejected. |
| SQLFluff (`sqlfluff`) | SQL lint | `sql` | `pip install sqlfluff` | `.sql`; dialect/config requirements can cause engine errors. |
| djLint (`djlint`) | HTML/Jinja templates | `templates` | `pip install djlint` | `.html/.jinja/.j2`; reference test adapter. |
| Hadolint (`hadolint`) | Dockerfile lint | `containerfile` | `install hadolint` | Dockerfile/Containerfile; use an official platform binary/package and verify `hadolint --version`. |
| TFLint (`tflint`) | Terraform lint | `iac` | `install tflint` | `.tf`/`.terraform`; use official install for your OS. Rush avoids implicit plugin setup. |
| Checkov (`checkov`) | Terraform policy checks | `iac` | `pip install checkov` | `.tf`; Rush uses local Terraform-only JSON mode with downloads/external modules disabled. |
| Kubeconform (`kubeconform`) | Kubernetes manifest validator | `iac` | `install kubeconform` | `.yaml/.yml`; schema validation for Kubernetes resources. |

## Security, supply chain, and workflow (Phase 11)

| Engine | What / who | Command | Catalog install hint | Applicability and recovery |
|---|---|---|---|---|
| OSV-Scanner (`osv-scanner`) | Multi-ecosystem advisories | `security` | `install osv-scanner` | Known lockfiles (`poetry.lock`, `package-lock.json`, `Cargo.lock`, `go.sum`, etc.); offline scan default. |
| Semgrep (`semgrep`) | SAST code scanning | `security` | `pip install semgrep` | Code files; local auto rules default; `--allow-network` for registry rules. |
| Trivy (`trivy`) | Vulnerability scanner | `security` | `install trivy` | Filesystem scan; offline by default; `--allow-download` for updates. |
| Grype (`grype`) | Vulnerability scanner | `security` | `install grype` | Offline directory vulnerability scanning. |
| Gitleaks (`gitleaks`) | Secret patterns | `secrets` | `install gitleaks` | Repository-wide; normalized messages redact values. |
| cdxgen (`cdxgen`) | CycloneDX SBOM | `sbom` | `npm install -g @cyclonedx/cdxgen` | Generates safe SBOM artifacts; `--overwrite` requires `--allow-artifact-write`. |
| Scorecard (`scorecard`) | OpenSSF supply chain posture | `ci` | `install scorecard` | Repository-wide; evaluates branch protection, dangerous workflows, and pin dependencies. |
| ScanCode (`scancode`) | License & copyright toolkit | `sbom` | `pip install scancode-toolkit` | Code and dependency tree; deep copyleft and license risk identification. |
| SLSA Verifier (`slsa-verifier`) | SLSA provenance verifier | `release` | `install slsa-verifier` | Artifact verification against cryptographic build provenance attestations. |
| GUAC (`guacone`) | Supply chain graph analysis | `sbom` | `install guac` | Graph-based vulnerability and provenance queries across software supply chain metadata. |
| pip-licenses (`pip-licenses`) | Python license compliance | `sbom` | `pip install pip-licenses` | Python environment packages; audits dependency license copyleft risks. |
| Cosign (`cosign`) | Signature verification | `release` | `install cosign` | Local blob signature and provenance verification. |
| Commitlint (`commitlint`) | Conventional Commit messages | `commit-msg` | `npm install -D @commitlint/cli` | Validates commit messages passed via `-m/--message` or file. |

## AST Linters, Patterns & Database Schemas (Phase 18)

| Engine | What / who | Command | Catalog install hint | Applicability and recovery |
|---|---|---|---|---|
| ast-grep (`ast-grep`) | Tree-sitter AST structural query | `lint` | `npm install -g @ast-grep/cli` | Polyglot AST search and structural code rule enforcement. |
| Flake8-Bugbear (`flake8-bugbear`) | Subtle Python design bug finder | `lint` | `pip install flake8-bugbear` | Python AST linter catching mutable defaults and subtle design defects. |
| MegaLinter (`megalinter`) | Polyglot linter orchestrator | `lint` | `install megalinter` | Universal repository orchestrator running 100+ linters in unified report. |
| Comby (`comby`) | Syntactic structural pattern matcher | `lint` | `install comby` | Syntax-aware structural pattern matching and refactoring audits. |
| Atlas (`atlas`) | Schema migration safety linter | `sql` | `install atlas` | Declarative database schema and migration lock risk verification. |
| Squawk (`squawk`) | PostgreSQL migration lock linter | `sql` | `npm install -g squawk-cli` | Detects exclusive table locks and dangerous DDL operations. |
| Prisma-lint (`prisma-lint`) | Prisma ORM schema linter | `lint` | `npm install -D prisma-lint` | Enforces relational mapping and model naming conventions in schema.prisma. |

## Documentation, Performance, Protocols & Vibecoder Quality Guardrails (Phase 19)

| Engine | What / who | Command | Catalog install hint | Applicability and recovery |
|---|---|---|---|---|
| Vale (`vale`) | Documentation & prose style linter | `lint` | `install vale` | Syntax-aware editorial guide and style rule enforcement. |
| CSpell (`cspell`) | Identifier & code spell checker | `lint` | `npm install -g cspell` | Catches spelling mistakes across source code, strings, and comments. |
| Alex (`alex`) | Inclusive language linter | `lint` | `npm install -g alex` | Flags insensitive or inconsiderate terminology in markdown/docs. |
| Readability (`readability-cli`) | Flesch-Kincaid prose analyzer | `complexity` | `npm install -g readability-cli` | Evaluates reading ease and grade-level complexity. |
| RedPen (`redpen`) | Technical documentation validator | `lint` | `install redpen` | Enforces vocabulary consistency and sentence length thresholds. |
| No-Jargon (`no-jargon`) | Corporate buzzword detector | `lint` | `npm install -g no-jargon` | Flags marketing clichés and corporate buzzwords. |
| Markdown-Unfluff (`markdown-unfluff`) | AI filler pattern cleaner | `lint` | `pip install markdown-unfluff` | Detects redundant AI bullet points and repetitive prose fluff. |
| Memray (`memray`) | Python memory profiler | `complexity` | `pip install memray` | High-resolution memory allocation and leak profiling. |
| Statoscope (`statoscope`) | JS bundle size & duplicate auditor | `complexity` | `npm install -D @statoscope/cli` | Validates bundle weights and flags duplicate npm packages. |
| Bloaty (`bloaty`) | Native binary footprint dissector | `complexity` | `install bloaty` | Dissects ELF/Mach-O/Wasm binary sections and symbol sizes. |
| Buf (`buf`) | Protobuf & gRPC schema linter | `lint` | `install buf` | Protocol Buffers linting and breaking change detection. |
| Dockle (`dockle`) | Container CIS benchmark linter | `security` | `install dockle` | CIS Docker benchmark and container image layer auditor. |
| wasm-tools (`wasm-tools`) | WebAssembly bytecode validator | `lint` | `install wasm-tools` | Validates Wasm/WAT binary structures and module interfaces. |
| PyClean (`pyclean`) | Bytecode cache cleaner | `format` | `pip install pyclean` | Cleans `.pyc` files and `__pycache__` directories. |
| Diff-Cover (`diff-cover`) | Diff-only coverage validator | `coverage` | `pip install diff-cover` | Enforces test coverage thresholds on modified lines of code. |
| Git-Guard (`git-guard`) | Working tree hygiene auditor | `lint` | `ships with git` | Audits uncommitted changes and untracked files. |
| Semantic-Release (`semantic-release`) | Automated version calculator | `release` | `npm install -g semantic-release` | Computes semver bumps from Conventional Commit histories. |
| PR-Agent (`pr-agent`) | PR diff summary generator | `review` | `pip install pr-agent` | Generates structured PR feedback and diff descriptions. |
| Safe-Env (`safe-env`) | Environment secret sanity checker | `security` | `npm install -g safe-env` | Flags insecure default secrets and placeholder values in `.env`. |
| Wait-On (`wait-on`) | Service readiness poller | `e2e` | `npm install -g wait-on` | Polls local HTTP and TCP endpoints for service readiness. |
| NCU (`ncu`) | Dependency freshness checker | `security` | `npm install -g npm-check-updates` | Checks for outdated npm packages and major version upgrades. |

## Missing-engine experience

```json
{"tool":"typecheck","engine":"mypy","status":"skipped","summary":"mypy executable not found", ...}
```

Install only if that check is part of your project policy. Then launch Rush from the same environment and verify the binary directly. Desktop MCP clients often have a different `PATH` from an interactive shell; use absolute paths or environment configuration when needed.
