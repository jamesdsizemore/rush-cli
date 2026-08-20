# Tool catalog

The catalog contains 35 user-visible tools. **Maturity matters:** a listed tool can be a real adapter, importer, or browser runtime.

| Tool | Category | Maturity | Engines / behavior |
|---|---|---|---|
| `review` | quality | real adapter | deterministic local heuristics with fingerprint/freshness/source-location evidence; PR-Agent structured PR summary; Graft and changed-file scope; pluggable LLM provider runtime |
| `lint` | quality | real adapter | Ruff, ESLint, Stylelint, ast-grep (Tree-sitter AST), Globstar, Flake8-Bugbear, MegaLinter, Comby, Prisma-lint, Vale (prose style), CSpell (code spellcheck), Alex (inclusive language), RedPen, No-Jargon, Markdown-Unfluff, Buf (Protobuf), wasm-tools, Git-Guard |
| `format` | quality | real adapter | Ruff format, Prettier, Squoosh (WebP/AVIF image compression), Critical (CSS extraction), Font-Spider (font glyph compression), PyClean (cache cleanup); `--check` is safe verification mode |
| `test` | test | real adapter | pytest, Vitest, Newman (Postman CLI runner); deterministic reference test suites |
| `security` | security | real adapter | pip-audit, npm audit, OSV-Scanner, Semgrep, Trivy, Grype, Bearer, Horusec, Medusa (agent hook auditor), Pa11y, OWASP ZAP, Deadfinder, A11yWatch, Dockle (container CIS), Safe-Env (environment sanity), NCU (dependency upgrade) |
| `typecheck` | quality | real adapter | mypy, tsc, Pyrefly; reference test suites |
| `dead` | quality | real adapter | Vulture, Knip, FawltyDeps (Python import/dependency auditor), Ts-prune (unused TS exports); reference test suites |
| `complexity` | quality | real adapter | Radon, jscpd, Tach (modular boundaries), Clines (token density), Sentrux (decay sensors), Depcruise (architectural cycles), Scaphandre (energy/carbon estimation), Readability (Flesch-Kincaid), Memray (memory profiling), Statoscope (JS bundle analysis), Bloaty (binary footprint) |
| `slop` | quality | real adapter | sloppylint, aislop (AST anti-pattern scanner), deterministic JS/TS fallback, Markdown-Unfluff |
| `markdown` | quality | real adapter | markdownlint-cli, Lychee, Vale, Alex, No-Jargon with contained config and offline default |
| `actions` | quality | real adapter | Actionlint with external child integrations disabled |
| `yaml` | quality | real adapter | Spectral, Zally with owned rules and remote-ref block |
| `sql` | quality | real adapter | SQLFluff (ANSI rules), Atlas (schema migration safety), Squawk (PostgreSQL lock analysis) |
| `templates` | quality | real adapter | djLint, HTML-Validate with reference test suites |
| `containerfile` | quality | real adapter | Hadolint, Dockle with owned CIS benchmark configurations |
| `iac` | security | real adapter | TFLint, Checkov, Kubeconform, Terrascan, Kube-score, Conftest, Polaris, KubeLinter |
| `secrets` | security | real adapter | Gitleaks, TruffleHog, Secretlint, detect-secrets, Safe-Env with normalized redaction |
| `sbom` | security | real adapter | cdxgen, ScanCode, GUAC, pip-licenses; requires `--allow-artifact-write` for overwrites |
| `ai-eval` | security | real adapter | Promptfoo, Garak, DeepEval, Guardrails evaluation for LLMs and agent safety |
| `codeql` | security | importer | contained CodeQL SARIF 2.1.0 report import, or local CodeQL CLI under `--allow-build` |
| `coverage` | test | importer | coverage.py JSON, LCOV, Undercover (diff coverage), Diff-Cover diff threshold, or Cobertura report import, or pytest/coverage runner under `--allow-slow` |
| `pbt` | test | importer | seeded local property-test JSON report import, or Hypothesis under `--allow-slow` |
| `flaky` | test | importer | local JUnit duplicate-case report import, or pytest-rerun under `--allow-slow` |
| `contract` | test | importer | Schemathesis property tests, local Pact summary report import, or pact-verifier under `--allow-slow` |
| `snapshot` | test | importer | local snapshot report import, or pytest-snapshot runner under `--allow-slow` (and `--allow-artifact-write` for `--accept`) |
| `visual` | test | real adapter | browser visual comparison runner, Lighthouse, PageSpeed, Lost Pixel, BackstopJS; requires `--allow-browser` and `--allow-slow` |
| `mutation` | test | real adapter | Stryker, Cosmic Ray, Infection, Pitest, Cargo-mutants, or mutmut runner under `--allow-slow` |
| `e2e` | test | real adapter | Playwright browser E2E runner, Wait-On readiness poller; requires `--allow-browser` |
| `fuzz` | test | importer | local seeded fuzz report import, or Atheris runner under `--allow-slow` |
| `load` | test | importer | local load report import, or k6 runner under `--allow-network` |
| `semantic-drift` | test | browser runtime | DOM/accessibility drift detection with Playwright/axe; requires `--allow-browser` and `--allow-slow` |
| `commit-msg` | workflow | real adapter | local Conventional Commit validation with `-m/--message` and file reading; commitlint reference test suite |
| `ci` | workflow | real adapter | local workflow inspection and OpenSSF Scorecard posture checks |
| `release` | workflow | real adapter | dry-run local artifact inventory, Cosign, Cejel (trust certificate), SLSA Verifier attestation, and Semantic-Release automated semver calculation |
| `tdd` | workflow | real adapter | TDD Guard Red-Green-Refactor cycle enforcement and automated test discovery |

Generated help is authoritative for options. See [CLI reference](reference/cli-reference.md), [Engine directory](reference/engine-directory.md), and [Permissions](safety/permissions.md).

