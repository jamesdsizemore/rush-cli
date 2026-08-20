# Rush — Expansive Unified App Review Scanner Integration Plan

> **Approval gate — plan only.** This is the one authoritative plan. It retains every existing Rush scanner/tool and every researched candidate below. No code, dependency, catalog, CI, commit, push, tag, or release changes are authorized until explicit approval.
>
> **Hard ordering rule:** Programs 0–7 contain no browser process, screenshot, DOM inspection, E2E, visual, accessibility-runtime, Lighthouse, or DAST work. **Program 8 is the only browser-evidence program and is last.**

## Product contract

Rush is a local, coding-agent-oriented app review CLI. `rush review` aggregates applicable scanners into one evidence-backed result; focused commands remain first-class and use the same implementations.

```text
rush review . --json                         # source/repository scanners
rush review . --profile full --json          # all completed non-browser scanners
rush review . --url http://127.0.0.1:3000 --allow-browser  # Program 8 only
```

The product includes all of these domains together:

- conventional code review: lint, formatting, types, dead code, duplication, complexity, architecture, diff impact, project health;
- application and dependency security: secrets, SAST, vulnerabilities, CI workflow security, SBOM, artifacts, provenance;
- tests and reliability: test execution/import, coverage, mutation, property testing, contracts, fuzzing, load, flaky evidence;
- configuration and deployment: IaC, policy, Kubernetes, Helm, Ansible, SQL, templates, APIs, containers;
- language-native review: Go, Rust, C/C++, JVM, .NET, Ruby/Rails, PHP, Dart/Flutter, Swift, Elixir, Scala, Nix;
- content/readiness: Markdown, spelling, prose, links, generated scaffolding, source-level placeholder/fake-action/state/token/component rules;
- **last:** browser runtime, E2E, UI/UX, accessibility, responsive layout, visual regression, frontend performance, DOM-level anti-slop, and DAST.

No family replaces another. UI/UX/anti-slop are scanner families; they do not displace conventional code/security/test review.

## Safety and truth contract

A scanner is real only when it has: local discovery, bounded invocation, parseable output/importer, normalized findings, structured missing-engine/permission/data state, fixtures for clean/findings/malformed/error/missing paths, catalog/CLI/MCP parity, and docs.

- External engines are discovered locally; Rush never silently installs binaries, packages, browsers, rule packs, databases, images, runtimes, or dependencies.
- `run_subprocess()` is required for engines and keeps `stdin=DEVNULL` to protect MCP stdio JSON-RPC.
- Missing engine/data/configuration is `skipped` with a reason, not clean.
- No scanner mutates source/config/lockfiles/baselines/packages/artifacts/release/Git history by default.
- Engines with network, project-build, fuzz, load, image-pull, cluster, interaction, or browser effects have explicit separate permissions.
- A report importer parses a user-produced report; it must not be marketed as a runner.
- Engine identity, data freshness, target, report provenance, and original rule/advisory are retained even when Rush correlates findings.

## Shared finding and evidence contract

All scanners emit canonical `ToolResult` values. `review` adds coverage metadata rather than changing the existing base result semantics.

```python
class ReviewFinding(TypedDict, total=False):
    id: str                  # stable domain/engine/rule/location fingerprint
    domain: str              # code, security, dependency, test, infra, docs,
                             # artifact, provenance, ui, a11y, ux, slop, visual
    priority: str            # blocker, high, medium, low
    confidence: str          # high, medium, low
    path: str
    line: int
    column: int
    rule: str
    message: str
    user_impact: str
    package: str
    advisory: str
    route: str               # Program 8 only
    selector: str            # Program 8 only
    viewport: str            # Program 8 only
    evidence: list[EvidenceRef]
    reproduction: list[str]
    suggested_action: str
    verification: str
```

`review_coverage` records `ran`, `not-applicable`, `missing-engine`, `missing-data`, `permission-blocked`, `imported`, `stale`, or `error` for every selected domain. The agent brief is a deterministic Markdown rendering of the same IDs, priority order, evidence, repair direction, and verification commands.

## Research-backed candidate inventory

Research was performed before this plan using official repositories/releases and official documentation. The configured Exa route was unavailable, so no claims depend on it.

| Candidate | Verified role | Current research signal | Integration class |
|---|---|---|---|
| Semgrep | Multi-language source pattern/SAST analysis | LGPL-2.1; v1.173.0, Aug 2026 | Core local-rules adapter |
| OSV-Scanner | Cross-ecosystem dependency vulnerability scanning | Apache-2.0; v2.5.1, Aug 2026 | Core adapter |
| zizmor | GitHub Actions security analysis | MIT; v1.29.0, Aug 2026 | Core adapter |
| Trivy | Local filesystem/image/IaC vulnerabilities, misconfigurations, SBOM | Apache-2.0; v0.74.0, Aug 2026 | Core artifact adapter |
| Syft / Grype | SBOM generation / local SBOM-artifact vulnerability scanning | Apache-2.0; v1.51.0 / v0.117.0, Aug 2026 | Core artifact adapters |
| Scorecard | Repository security posture | Apache-2.0; v5.5.0, Apr 2026 | Core optional adapter |
| Cosign / SLSA verifier | Signature / build provenance verification | Apache-2.0; current releases | Core provenance adapters |
| detect-secrets / TruffleHog | Baseline secret detection / optional verification | Apache-2.0 / AGPL-3.0 | Adapter / explicit feasibility gate |
| Checkov / KICS / Conftest | IaC scan / IaC scan / local policy | Apache-2.0 / Apache-2.0 / maintained | Core adapters |
| kubeconform / KubeLinter / Helm | Manifest validation / manifest lint / chart lint | Apache-2.0 / Apache-2.0 / Apache-2.0 | Core adapters |
| ansible-lint / TFLint | Playbook / Terraform review | GPL-3.0 / MPL-2.0 | External optional / existing repair |
| coverage.py, pytest-cov, c8 | Python and JS coverage evidence | Existing ecosystem tools | Core adapters/importers |
| mutmut / Stryker | Python / JS-TS mutation evidence | BSD-3-Clause / Apache-2.0 | Core slow adapters |
| Schemathesis / Pact JS | API schema property / consumer contract evidence | MIT / license reviewed per package | Core adapter / importer-first |
| Locust / k6 | Load evidence | MIT / AGPL-3.0 | Core optional / feasibility gate |
| OSS-Fuzz / Go fuzz / cargo-fuzz / Atheris / Jazzer | Fuzz evidence and language fuzz targets | Apache-2.0 / language-specific | Importer / explicit target adapters |
| CodeQL | Deep semantic analysis | MIT; active | Build/database-gated adapter |
| golangci-lint / gosec / govulncheck | Go quality/security/vulnerability | GPL-3.0 / Apache-2.0 / BSD-3-Clause | Optional / core / core |
| Clippy / cargo-audit | Rust quality/security | Apache-2.0 / RustSec ecosystem | Core adapters |
| clang-tidy / Cppcheck | C/C++ static analysis | LLVM-family / GPL-3.0 | Build-gated / external optional |
| SpotBugs | JVM bug analysis | LGPL-2.1 | Build-artifact-gated adapter |
| RuboCop / Brakeman | Ruby quality / Rails security | MIT / license gate | Core / feasibility |
| Psalm / PHP Depend | PHP static analysis / design metrics | MIT / BSD-3-Clause, older release | Core / maintenance gate |
| Dart analyzer / SwiftLint | Dart-Flutter / Swift review | BSD-3-Clause / MIT | Core adapters |
| codespell / Vale / Lychee | Spelling / prose / links | GPL-2.0 / MIT / Apache-2.0 | Optional / core / core |
| Playwright / axe-core / Lighthouse / pixelmatch | E2E-runtime / accessibility / web performance / visual diff | Apache-2.0 / MPL-2.0 / Apache-2.0 / ISC | **Program 8 only** |
| Accessibility Insights / Pa11y | Accessibility depth/comparison | MIT / LGPL-3.0 | **Program 8 only** |
| Nuclei / OWASP ZAP | DAST | feasibility / established project | **Program 8 only** |

GPL/AGPL/LGPL candidates are not bundled; this is an external-binary compatibility/review decision, not a reason to delete their adapter path. Inactive/older candidates are retained as explicit maintenance gates, never silently presented as core support.

# Canonical implementation sequence

## Program 0 — truthful adapter foundation

**Purpose:** make the existing wide catalog honest and create the one adapter/result path every later scanner must use. No browser concepts, dependencies, or artifacts are introduced here.

**Owned files**

- Modify `src/rush/tools/review.py`, `src/rush/tools/base.py`, `src/rush/tools/__init__.py`
- Modify `src/rush/catalog.py`, `src/rush/cli.py`, `src/rush/mcp.py`, `src/rush/config.py`
- Create `src/rush/review/coordinator.py`, `models.py`, `coverage.py`, `policy.py`, `evidence.py`
- Create `src/rush/engines/structured.py`, `src/rush/importers/`
- Create `tests/test_review_coordinator.py`, `test_catalog_truth.py`, `test_structured_engine_output.py`, `test_review_policy.py`, `test_review_cli_mcp.py`

**Exact contract**

1. Split current review heuristics into a first-party source scanner without behavior loss.
2. `ReviewCoordinator` runs completed/applicable tool implementations only and aggregates by deterministic priority/domain/order.
3. Catalog metadata declares `adapter`, `importer`, `configured`, `experimental`, `feasibility`, or `unimplemented`; catalog prose cannot outclaim test-backed implementation.
4. Add strict JSON/SARIF/JUnit/LCOV/Cobertura/CycloneDX/SPDX parser primitives and bounded sanitized evidence references.
5. Establish all non-browser permissions: `allow_slow`, `allow_fuzz`, `allow_network`, `allow_project_build`, `allow_image_pull`, `allow_cluster`.
6. CLI and MCP invoke the same coordinator and focused tools, never transport-layer copies.

**Tests and exit**

- Existing Python/TS fixtures aggregate current lint/type/dead/complexity/test/security results.
- Every current tool/candidate has truthful catalog state.
- malformed output, missing binary, permission block, stale/imported data, and unknown configuration become structured results.
- No focused command regresses; CLI/MCP parity tests pass.

## Program 1 — conventional code, security, dependency, workflow, and source anti-slop scanners

**Purpose:** immediately fill the core scanner gaps that matter before any runtime evidence.

| ID | Integration | Exact Rush behavior | Owned seam and required fixtures |
|---|---|---|---|
| P1.1 | Existing review/source heuristics | Preserve current checks; add parser-safe architecture/repository rules: missing references where resolvable, unsafe TODO/HACK density, stale scaffold markers, error-handling gaps only with deterministic syntax evidence. | `review/source.py`, `review/architecture.py`; Python/TS positive, negative, and parser-unavailable fixtures. |
| P1.2 | Ruff + ESLint | Existing check-only engines feed `code` findings; preserve engine/rule/line. | Existing adapters plus `review/code_health.py`; clean/findings/missing fixtures. |
| P1.3 | mypy + tsc | Existing type diagnostics feed high-priority code findings; no install/build. | Existing adapters and type mapper; Python/TS diagnostics fixtures. |
| P1.4 | Vulture + Knip | Existing unused-code scans; advisory unless reachability is proven. | `review/dead_code.py`; export/entrypoint false-positive fixtures. |
| P1.5 | Radon + jscpd | Existing complexity/duplication scans; thresholded/configurable. | `review/maintainability.py`; threshold/config/duplicate fixtures. |
| P1.6 | First-party source anti-slop/readiness | Observable source rules: placeholder/filler literals, empty/hash actions, fake handlers, generated scaffold, missing loading/error/empty branch patterns, token sprawl, duplicated component markup. Never claim authorship or subjective visual quality. | `review/slop_source.py`, `design_tokens.py`, `components.py`, `state_completeness.py`; positive/negative/suppressed fixtures per rule. |
| P1.7 | pytest + Vitest | Existing test engines become explicit `test` evidence; no-tests and missing engines remain visible. | Existing adapters plus test mapper; fail/pass/no-tests fixtures. |
| P1.8 | pip-audit + npm audit | Existing dependency scan retained; advisory, package, lockfile, cache/freshness state retained. | `tools/security.py`; Python/Node advisory/offline/missing fixtures. |
| P1.9 | Gitleaks | Existing secret scan retained with values redacted before any result/brief/artifact. | Existing adapter plus redaction tests. |
| P1.10 | Semgrep | `semgrep scan --json --config <user-local-rules>` only. No remote registry config, autofix, build, or silent rule download. | `engines/semgrep.py`, `tools/sast.py`; JSON/SARIF/local-rule/missing-rule/no-network fixtures. |
| P1.11 | OSV-Scanner | Scan relevant local manifests/lockfiles; record database/cache/network freshness rather than claiming complete coverage. | `engines/osv_scanner.py`, `tools/vuln.py`; Python/Node/Go/Rust fixtures. |
| P1.12 | actionlint + zizmor | Keep correctness and add local GitHub Actions security scan; findings remain engine-attributable. | `engines/zizmor.py`, `tools/actions_security.py`; workflow fixtures. |
| P1.13 | Deterministic repair brief | Render JSON findings into a compact coding-agent brief containing impact, exact source evidence, safe repair class, and verification. | `review/agent_brief.py`; JSON/Markdown ID-order parity/redaction fixtures. |

**Exit:** `rush review .` gives useful code, security, dependency, workflow, tests, and source-readiness evidence with no runtime process of any kind.

## Program 2 — infrastructure, configuration, policy, templates, SQL, and documentation scanners

| ID | Integration | Exact Rush behavior | Owned seam and required fixtures |
|---|---|---|---|
| P2.1 | TFLint | Repair existing Terraform integration/catalog truth; local `.tf` check only. | Existing TFLint adapter/tool; valid/invalid/missing fixtures. |
| P2.2 | Checkov | JSON local IaC scan of explicit applicable paths; no downloads/module initialization. | `engines/checkov.py`, `tools/iac.py`; clean/findings/malformed/missing fixtures. |
| P2.3 | KICS | Local IaC scan separate from Checkov; correlate presentation only, never erase engine findings. | `engines/kics.py`; same-target dual-engine fixtures. |
| P2.4 | Conftest | Evaluate only repository-local Rego against explicit local input; no remote policy bundle. | `engines/conftest.py`, `tools/policy.py`; pass/fail/bad-policy fixtures. |
| P2.5 | kubeconform | Local manifest/CRD validation; remote schemas require network permission. | `engines/kubeconform.py`, `tools/kubernetes.py`; multi-doc/CRD/remote-block fixtures. |
| P2.6 | KubeLinter | Static local manifest/chart best-practice scan, no cluster. | `engines/kube_linter.py`; findings/clean fixtures. |
| P2.7 | Helm lint | Local `helm lint` only; no repo update, dependency download, install, upgrade, or cluster action. | `engines/helm.py`, `tools/helm.py`; chart/missing-dependency fixtures. |
| P2.8 | ansible-lint | External optional adapter; analyze playbooks/roles only, never execute or autofix. | `engines/ansible_lint.py`; playbook/missing-engine fixtures. |
| P2.9 | Spectral/API source mapping | Preserve Spectral; map OpenAPI findings to API/config domain. | Existing YAML tool + `review/api_source.py`; OpenAPI fixture. |
| P2.10 | SQLFluff + djLint + Hadolint | Preserve existing SQL/template/container scans as review inputs. | Existing adapters/mappers; applicability fixtures. |
| P2.11 | markdownlint + codespell | Preserve Markdown lint; add codespell as an external optional scanner with language-aware ignores. | `engines/codespell.py`, `tools/docs.py`; prose/code false-positive fixtures. |
| P2.12 | Vale | Local config/style only, no remote sync. | `engines/vale.py`; style/missing-config fixtures. |
| P2.13 | Lychee | Local files/anchors by default; external links require `allow_network`. | `engines/lychee.py`, `tools/links.py`; local/external-policy fixtures. |
| P2.14 | First-party config readiness | Deterministically detect bad env validation, schema/route mismatch, unsafe exact CORS/client config patterns. | `review/config_readiness.py`; positive/negative fixtures. |

**Exit:** configuration, deployment, policy, docs, links, SQL, templates, containers, IaC, Kubernetes, and Ansible are real review domains—not catalog placeholders.

## Program 3 — supply-chain, artifacts, secrets, provenance, and repository posture scanners

| ID | Integration | Exact Rush behavior | Owned seam and required fixtures |
|---|---|---|---|
| P3.1 | Trivy filesystem/config | Scan explicit local filesystem/config target. No image pull, DB update, or remote repository mode by default. | `engines/trivy.py`, `tools/artifact.py`; vulnerability/misconfig/data-state fixtures. |
| P3.2 | Trivy local image archive | Scan only a user-supplied local OCI layout/archive; remote image needs later explicit permission. | Extend Trivy adapter; local archive/policy fixtures. |
| P3.3 | Syft | Generate CycloneDX/SPDX from local filesystem/artifact; preserve cdxgen as independent producer. | `engines/syft.py`, `tools/sbom.py`; producer/version/target fixtures. |
| P3.4 | SBOM normalization | Normalize cdxgen/Syft report shape but retain producer, component, version, target digest. | `importers/sbom.py`, `review/sbom.py`; two-producer fixtures. |
| P3.5 | Grype | Scan local filesystem/SBOM/artifact only; retain advisory evidence separate from Trivy. | `engines/grype.py`, `tools/artifact_vuln.py`; SBOM/advisory fixtures. |
| P3.6 | Artifact finding correlation | Group same package/advisory/version for display without suppressing original engine outputs. | `review/correlate.py`; collision/near-match/non-match fixtures. |
| P3.7 | detect-secrets | Import/run baseline-oriented local scan; Gitleaks remains intact. | `engines/detect_secrets.py`; baseline/redaction fixtures. |
| P3.8 | TruffleHog | Feasibility gate first: AGPL compatibility, verification/network behavior, parser. Never default verification. | Research decision then adapter; policy blocker tests before executable path. |
| P3.9 | OpenSSF Scorecard | Local repository posture mode plus separately permissioned remote mode. | `engines/scorecard.py`, `tools/posture.py`; local/remote/blocked fixtures. |
| P3.10 | Cosign | Verify user-supplied local artifact/signature/identity only; never sign/upload. | `engines/cosign.py`, `tools/provenance.py`; valid/invalid/redaction fixtures. |
| P3.11 | SLSA verifier | Verify user-supplied provenance/artifact; never build/publish. | `engines/slsa_verifier.py`; predicate/artifact relation fixtures. |
| P3.12 | Commit/CI/release evidence | Preserve commitlint/CI/release tools; aggregate posture/provenance/SBOM gaps with no Git/release mutation. | Existing workflow tools + `review/release_evidence.py`; no-tag/no-publish tests. |

**Exit:** a coding agent receives distinct dependency, SBOM, artifact, secret, posture, signature, and provenance evidence rather than a vague security score.

## Program 4 — coverage, mutation, API, contracts, fuzz, load, flaky, and non-browser reliability scanners

| ID | Integration | Exact Rush behavior | Owned seam and required fixtures |
|---|---|---|---|
| P4.1 | Coverage report importer | Parse existing LCOV/Cobertura/coverage JSON/JUnit; no test execution by default. | `importers/coverage.py`, `tools/coverage.py`; each format/malformed fixture. |
| P4.2 | coverage.py / pytest-cov | Execute declared local command only with `allow_slow`; no config/source write. | `engines/coverage_py.py`; Python threshold/report fixtures. |
| P4.3 | c8 | Import/run JS coverage under same explicit policy. | `engines/c8.py`; LCOV line/branch/function fixtures. |
| P4.4 | Property-based evidence | Detect/execute only declared existing property suites; no generated project changes. | `tools/pbt.py`; configured/missing-suite fixtures. |
| P4.5 | mutmut | Python mutation run in isolated temporary workspace with `allow_slow`; source checksum unchanged. | `engines/mutmut.py`; mutant/no-write/timeout fixtures. |
| P4.6 | Stryker | JS/TS mutation under `allow_slow`, local config only, no package install. | `engines/stryker.py`; JSON/missing/timeout fixtures. |
| P4.7 | Schemathesis | Offline schema analysis first; live target only later with explicit target/network policy. | `engines/schemathesis.py`, `tools/contract.py`; offline/blocked-target fixtures. |
| P4.8 | Pact evidence | Parse user-owned contract reports first; runner adapter only after output/license research gate. | `importers/pact.py`; provider/consumer/failure fixtures. |
| P4.9 | Flaky evidence | Import JUnit/history reports and fingerprint repeated test failure; no rerun loop. | `importers/flaky.py`, `tools/flaky.py`; history fixtures. |
| P4.10 | Language fuzz adapters | Go fuzz, cargo-fuzz, Atheris, Jazzer each get individual target/duration/`allow_fuzz` adapter contracts. | Per-engine adapters after per-CLI research; no-target/permission/report fixtures. |
| P4.11 | OSS-Fuzz importer | Parse supplied reports/corpora/crash metadata only; never market local OSS-Fuzz runner. | `importers/oss_fuzz.py`; crash/evidence/redaction fixtures. |
| P4.12 | Locust | User-supplied local/approved scenario and explicit target/network permission. | `engines/locust.py`, `tools/load.py`; scenario/policy/summary fixtures. |
| P4.13 | k6 | Feasibility first because AGPL; same scenario/target/network rules if approved. | Decision then adapter; license/policy/parser fixtures. |
| P4.14 | Non-browser reliability correlation | Correlate failed test, coverage gap, API/schema finding, and source missing-state evidence only when identity is reliable. | `review/reliability.py`; same-cause vs unrelated-failure fixtures. |

**Exit:** current coverage/mutation/e2e/pbt/fuzz/load/visual/snapshot/flaky/contract placeholders are either real non-browser adapters/importers now, or deferred explicitly to Program 8 only where they require runtime/browser evidence.

## Program 5 — language-native and semantic code review scanners

| Ecosystem | Integrations and exact gate | Required test/acceptance |
|---|---|---|
| Deep semantic | CodeQL SARIF importer first; database creation/query execution only with explicit local query config and `allow_project_build`. | SARIF provenance/flow fixture; no database/build without permission. |
| Go | golangci-lint external optional (GPL), gosec core JSON adapter, govulncheck with cache/freshness state. | Go module quality/security/advisory/offline fixtures. |
| Rust | Clippy check-only, cargo-audit/RustSec with advisory state; no `cargo fix`/lock write. | Workspace diagnostics/advisory/missing data fixtures. |
| C/C++ | clang-tidy requires explicit compile database; Cppcheck optional GPL local adapter. | Missing `compile_commands.json` coverage state; XML/JSON fixtures. |
| JVM | SpotBugs analyzes explicit classes/artifacts; Checkstyle/PMD research comparison before adapter. | XML/SARIF/absent-artifact fixtures; no build by default. |
| .NET | Analyzer/vulnerability feasibility with SDK discovery and explicit restore/build permission. | No restore/network/build without exact permission. |
| Ruby/Rails | RuboCop check-only; Brakeman license/output gate; bundler-audit research gate. | Ruby/Rails markers, structured finding, missing marker fixtures. |
| PHP | Psalm core static/security adapter; PHP Depend maintenance gate; Composer audit research gate. | PHP project/SARIF/metrics/advisory fixtures. |
| Dart/Flutter | Local Dart analyzer only; no package fetch. | Dart diagnostics/project marker fixtures. |
| Swift | SwiftLint check-only local adapter. | Swift report/missing-engine fixtures. |
| Elixir | Credo and Dialyzer separate feasibility adapters; no automatic Mix fetch. | Static/type contracts and project marker fixtures. |
| Scala | Scalafix/Scalastyle feasibility; build/output contract first. | No build default and structured report proof. |
| Nix | Make existing statix route real; evaluate deadnix/nixfmt separately. | Nix fixtures/output/format no-write proof. |

**Exit:** no ecosystem is called supported merely because routing recognizes its files. Each listed ecosystem has a real adapter, explicit feasibility result, structured fixture, and coverage state.

## Program 6 — review intelligence, diff-aware orchestration, evidence freshness, and scanner governance

| ID | Capability | Exact contract | Required acceptance |
|---|---|---|---|
| P6.1 | Capabilities scanner | `rush capabilities PATH --json` detects repository markers, locally installed engine versions, config, reports, permissions, and explains unavailable scans. | Read-only fixture matrix; no engine execution. |
| P6.2 | Scan planner | `rush plan PATH --profile ...` resolves applicable completed scanners, estimated scope, missing prerequisites, and permissions before execution. | Planned scanner set equals coordinator selection. |
| P6.3 | Diff-aware selection | `review --changed BASE` reads local Git diff for source/lockfile/IaC/artifact impact routing. | No fetch/rewrite; mixed-change fixtures. |
| P6.4 | Finding correlation | Stable engine/rule/location/package/report fingerprints group presentation but preserve originals. | Same issue vs same text/different target fixtures. |
| P6.5 | Freshness scanner | Label fresh/cached/offline/imported/stale/missing/blocked evidence. | Stale-clean is not clean fixture. |
| P6.6 | Baseline/regression | Explicit user-owned canonical finding baseline; no implicit create/update. | Stable IDs/expired suppression/path containment fixtures. |
| P6.7 | CI export | Same coordinator emits JSON/SARIF/JUnit bundles; no separate CI logic. | CLI/MCP/CI schema parity fixtures. |
| P6.8 | Scanner governance | `rush doctor` checks catalog truth, version compatibility, parser drift, candidate lifecycle, docs parity. | Catalog cannot claim adapter state without adapter/test evidence. |

## Program 7 — advanced non-browser artifact, cluster, and workflow posture scanners

| ID | Integration | Exact behavior | Required acceptance |
|---|---|---|---|
| P7.1 | kube-bench | Explicit kubeconfig/context plus `allow_cluster`; distinct from local manifest scanners. | No credential/context read or process without permission. |
| P7.2 | Remote image mode | Trivy remote image reference requires `allow_image_pull` plus network permission; Program 3 local archive remains default. | Target/digest/pull-policy fixtures. |
| P7.3 | Provenance aggregate | Correlate Cosign/SLSA/SBOM/artifact vulnerability into release evidence, never sign/release. | Missing vs verified evidence fixtures. |
| P7.4 | Dependency diff risk | Read-only lockfile/manifest diff: changed package/version/advisory impact. | No fetch/rewrite and deterministic diff fixtures. |
| P7.5 | Secure workflow policy packs | Repository-local policy on Actions/IaC/artifacts; exceptions require reason/expiry and remain visible. | Unknown/expired waiver failure fixtures. |

**Exit:** advanced target/artifact posture is safe and explicit before any browser process is introduced.

# Program 8 — Browser evidence, UI/UX, accessibility, visual, E2E, frontend performance, DOM anti-slop, and DAST — LAST

**This program starts only after Programs 0–7 are complete and validated.** It does not replace any preceding scanner; it consumes the completed coordinator/evidence/policy/finding infrastructure.

## P8.0 Browser target, lifecycle, and journey policy

**Owned files**

- Create `src/rush/browser/runner.py`, `lifecycle.py`, `routes.py`, `artifacts.py`, `sanitize.py`
- Create `src/rush/review/app_config.py`, `target.py`, `journeys.py`
- Modify review/CLI/MCP/config/catalog only through existing Program 0 seams
- Create `tests/test_browser_policy.py`, `test_app_lifecycle.py`, `test_journey_dsl.py`, synthetic local fixture app

**Contract**

- Browser requires supplied loopback URL and `--allow-browser`; non-loopback requires `--allow-network`.
- App start uses only user-provided `--start COMMAND` plus `--allow-project-run`; Rush never guesses a package-manager/dev command.
- Browser binary/runtime must already be locally available; no download/`npx` bootstrap.
- Default interaction scope is same-origin GET navigation and harmless UI state changes only.
- Forms, uploads, authentication, destructive controls, mutation endpoints, external navigation, and active scans require separately explicit permission/allow-list.
- Route depth, route count, total duration, trace/screenshot/console/artifact size are bounded.
- Child process cleanup covers ready success, startup failure, timeout, and interrupted review.

**Acceptance:** no browser, app process, network target, form submit, or artifact write is possible without the matching flag and fixture proof.

## P8.1 Runtime and route scanners

| ID | Scanner | Exact scope | Owned files and fixtures |
|---|---|---|---|
| P8.1 | Playwright runtime | Local page load: uncaught page errors, sanitized console errors, failed same-origin assets/requests, title/URL evidence, trace/screenshot manifest. | `engines/playwright.py`, `review/runtime.py`, `tools/app.py`; console/error/asset/missing-engine/policy fixtures. |
| P8.2 | First-party route/navigation | Static router/link discovery plus safe same-origin navigation. Detect broken internal links, unresolved route targets, empty primary `href`, unreachable declared routes. | `review/routes.py`, `browser/routes.py`; bad-link/unreachable/deny-route fixtures. |
| P8.3 | Safe journey/E2E | Structured DSL only: `go`, `click`, `fill`, `expect`, `screenshot`, `wait-for`; no scripts/shell. Submission/mutation requires `allow_interactions`. | `tools/e2e.py`; safe journey/rejected verb/mutation-blocked fixtures. |
| P8.4 | Runtime reliability correlation | Correlate browser exception/failed request/failed journey with Program 4 test/coverage and Program 1 source evidence where reliable. | Extend `review/reliability.py`; same-cause/non-match fixtures. |

## P8.2 UI/UX, accessibility, and responsive scanners

| ID | Scanner | Exact scope | Owned files and fixtures |
|---|---|---|---|
| P8.5 | axe-core | Local installed axe asset in browser context; labels, names, roles, landmarks, headings, contrast, duplicate IDs, form semantics. | `engines/axe.py`, `review/accessibility.py`; rule/selector/route/unavailable fixtures. |
| P8.6 | Keyboard/focus | Bounded Tab/Shift-Tab/Escape review of safe configured tasks: focus visibility/order, modal trap/escape, inaccessible controls. | `review/keyboard.py`; focus trap/invisible focus/no destructive action fixtures. |
| P8.7 | Responsive geometry | Deterministic desktop/tablet/mobile matrix: page/element overflow, clipping, hidden primary content/nav, overlap, off-screen focus, too-small tap targets. | `review/responsive.py`; mobile-only/desktop-only screenshot/geometry fixtures. |
| P8.8 | Form/feedback | Under safe configured interactions, identify visible actions without loading/disabled/success/error feedback and runtime fake/no-op behavior. No default submission. | `review/feedback.py`; safe fake-action/state feedback fixtures. |
| P8.9 | Accessibility Insights and Pa11y | Comparative/importer feasibility adapters. Add only if findings coverage/actionability exceeds axe without duplicate default noise. | `importers/accessibility_insights.py`, Pa11y decision; same-fixture comparison tests. |

## P8.3 Visual, performance, and DOM anti-slop scanners

| ID | Scanner | Exact scope | Owned files and fixtures |
|---|---|---|---|
| P8.10 | pixelmatch / screenshot compare | Compare explicit user-owned baseline only. Default is read-only; baseline create/update needs `--accept-baseline` and path containment. | `engines/pixelmatch.py`, `review/visual.py`, `tools/visual.py`; diff/no-baseline/implicit-write block fixtures. |
| P8.11 | Snapshot scanner | Focused snapshot reports use same read-only visual evidence pipeline; no duplicate visual implementation. | `tools/snapshot.py`; snapshot identity/baseline-policy fixtures. |
| P8.12 | Lighthouse | Local URL plus browser permission only; normalize actionable metrics and record local machine/viewport context. | `engines/lighthouse.py`, `review/performance.py`; thresholds/missing-engine/context fixtures. |
| P8.13 | DOM anti-slop/readiness | Raise only observable rules when DOM confirms source evidence: visible placeholders/filler/fake metrics/starter UI, duplicate CTAs, nonfunctional visible controls, missing empty/error/loading feedback, token/component inconsistency. Never claims AI authorship or subjective aesthetic truth. | `review/slop_dom.py`; visible-vs-hidden/allow-list/suppression fixtures. |
| P8.14 | Screenshot/trace index | Attach safe relative screenshots/diffs/traces to canonical finding IDs, route, viewport, scanner. | `review/artifact_index.py`; no raw requests/cookies/oversize artifact fixtures. |
| P8.15 | Semantic drift | Preserve existing experimental semantic-drift tool, invoke only for configured local browser target with its existing explicit browser/slow flags. | Existing engine + review mapper; safety/target fixture. |

## P8.4 Browser-adjacent active security scanners

| ID | Scanner | Exact scope | Owned files and fixtures |
|---|---|---|---|
| P8.16 | Nuclei | Feasibility first. User-selected local/approved target and repository-local curated templates only; no automatic template fetch or broad external scan. | Research record then `engines/nuclei.py`; template provenance/destructive-template exclusion fixtures. |
| P8.17 | OWASP ZAP | Explicit local target, duration bound, passive mode only. Active mode needs separate `--allow-active-dast`. | `engines/zap.py`, `tools/dast.py`; passive/active-blocked/alert-parser fixtures. |
| P8.18 | Live Schemathesis mode | Program 4 schema scanner gains an explicit approved target/allow-list/interaction mode; headers/bodies/tokens redacted. | Extend contract policy; target/redaction/mutation block fixtures. |

**Program 8 exit:** `rush review . --url <loopback> --allow-browser` adds real, safe runtime/UI/UX/a11y/responsive/visual/performance/DOM-slop/DAST evidence to the already complete code-review scanner stack. Every browser finding includes route/selector/viewport/artifact evidence where available, and all skipped browser coverage is explicit.

## Profiles

| Profile | Included programs |
|---|---|
| `fast` | Program 1 source-only installed code scanners. |
| `standard` | Programs 1–3 applicable local scanners. |
| `quality` | Programs 1–5 applicable local scanners. |
| `full` | Programs 1–7 applicable local scanners. Still no browser without URL and permission. |
| `app` | Program 8 only as an additive layer over completed selected non-browser profile; requires explicit browser flags. |
| `release` | full + explicit approved Program 7/8 target modes; permissions remain separate. |

Profiles choose scanner sets. They never grant permissions.

## Per-adapter delivery checklist

For every scanner row:

1. Record official CLI/version/license/output/exit code/data/network/build/write behavior and overlap decision in local `research/`.
2. Add RED fixtures: clean, findings, malformed output, command failure, missing engine, bad target/configuration, permission block, and sensitive-output redaction.
3. Implement `resolve_binary()` discovery and safe `run_subprocess()` command with explicit args/timeout/working directory.
4. Parse structured output into canonical findings with original engine/rule/advisory and provenance.
5. Add catalog state, configuration validation, focused CLI/MCP same-implementation registration, coordinator applicability, and coverage state.
6. Add optional local synthetic real-engine smoke test; do not make full CI install every ecosystem runtime.
7. Document only completed behavior and exact install prerequisites.

After each approved scoped delivery:

```bash
unset VIRTUAL_ENV PYTHONPATH
.venv/Scripts/python.exe -m pytest tests/ -q
.venv/Scripts/ruff.exe check src tests
.venv/Scripts/ruff.exe format --check src tests
git diff --check
rtk git diff --stat
graft --dir .hermes/graft build . >/dev/null
graft --dir .hermes/graft check .
```

`research/` remains local/untracked. Never stage all files; use explicit scoped paths.

## Completion definition

Rush is complete against this plan only when:

- all existing focused commands remain and every catalog item is truthfully classified;
- Programs 0–7 provide real, fixture-tested expansive code/security/dependency/IaC/test/language/artifact/docs/workflow review before any browser implementation;
- Program 8 is completed last and adds browser/UI/UX/anti-slop/a11y/visual/performance/DAST without replacing preceding coverage;
- every scanner is safe by default, locally discovered, parseable, attributable, and explicit about missing/stale/imported/blocked evidence;
- `rush review` produces a compact coding-agent repair packet with exact evidence and verification steps;
- CLI and MCP invoke the same completed implementations;
- no scanner is silently dropped, reduced to a catalog claim, or represented as clean when unavailable.

## Approval checkpoint

On approval, start **Program 0** only. The next implementation decision is then whether to deliver all of Program 1 as one tightly tested tranche or in small explicit commits. Browser evidence is not touched until Programs 0–7 meet their exit criteria.
