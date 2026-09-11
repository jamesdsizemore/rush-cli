# Tool catalog

## `continuity` — workflow, real adapter

Manages local session checkpoints through `save`, `list`, and `restore`. It is implemented by `SessionContinuityTool`, has no external engine, and uses explicit cache-write permission for `save`; it is registered as MCP `rush_continuity`.

## `memory` — workflow, real adapter (Phase 61)

Queries and writes the unified `TypedArtifactStore` (`.rush/memory.db`) through `ask`, `write`, `promote`, `list`, `recall`, and `maintain`. It is implemented by `MemoryTool`, has no external engine, and is registered as MCP `rush_memory` and CLI `rush memory`. `write`/`promote`/`maintain` are `stateful-mutation` operations requiring cache-write permission. `ask`/`list`/`recall` require an explicit session allowlist and return content only after recall defenses pass.

## `scan` — workflow, real adapter (Phase 65)

Plans and executes a full-project scan across every catalog candidate through `plan`, `run`, and `status`. It is implemented by `ScanTool` over `rush.workflows.project_run`, has no external engine of its own (it schedules the existing `ALL_TOOLS` catalog), and is registered as MCP `rush_scan` and CLI `rush scan --project ID_OR_PATH`. `plan` is a preview; `run` is a `stateful-mutation` operation requiring `allow_cache_write` and `allow_artifact_write`, and persists one immutable run manifest per invocation. `status` paginates the run's scheduled candidates behind the same HMAC-signed cursor `rush_project`'s `list` uses.

The live `TOOL_SPECS` catalog contains 53 user-visible tools (distinct from 74 registered MCP names). **Maturity matters:** a listed tool can be a real adapter, importer, or browser runtime.

Current execution limitations: catalog engines are candidates, not proof every named adapter runs on every command. Lint/format can falsely report success (F09/F10). Mutation/fuzz/load/contract live paths run version probes, not workloads (F11). AI eval lacks required gates (F08). Imported-report modes remain separate; require native execution evidence until [P64-06–P64-11](phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md) delivers the accepted fixes. See [Known issues](KNOWN_ISSUES.md).

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
| `fix` | quality | real adapter | automated safe multi-engine code remediation and formatting (Ruff, Biome, ESLint, Prettier, ast-grep) |
| `doctor` | workflow | real adapter | environment health, PATH precedence, virtual environment, and toolchain integrity diagnostics |
| `guard` | security | real adapter | destructive command interceptor, repository path boundary confinement, and secret redactor |
| `token` | quality | real adapter | fast BPE token counter, Python AST outline compressor |
| `sync` | quality | real adapter | OpenAPI contract validator, TypeScript interface generator |
| `hygiene` | quality | real adapter | polyglot dead code detector, 3-way AST merge conflict resolver |
| `codegraph` | quality | real adapter | polyglot CPG symbol slicer, SQLite index store, call path tracer |
| `bundle` | quality | real adapter | chunk calculator, raw/gzip/brotli transfer size measurement, performance budget gate |
| `hotspots` | quality | real adapter | Git commit churn analyzer, McCabe cyclomatic complexity risk matrix, bus factor calculator |
| `governance` | workflow | real adapter | canonical AGENTS.md compiler to multi-IDE rules, repo scaffolder, subagent guard |
| `hook` | workflow | real adapter | sub-second staged AST linter, Trojan Source detector, hook tamper guard |
| `score` | workflow | real adapter | 6-pillar composite quality scorecard, SARIF 2.1.0 exporter, SVG badge generator, multi-model consensus reconciler |
| `prompt-eval` | test | real adapter | golden task evaluation matrix, tool sequence and patch matching, token/cost budgets, pass rate thresholds |
| `error-catalog` | security | real adapter | Python, TypeScript, and Rust AST/regex exception extractor; deterministic RFC 7807 problem details and Markdown docs generator |
| `provenance-ai` | workflow | real adapter | Git commit trailer attribution (Co-authored-by, Generated-by), line survival rates (30/60/90d), defect correlation |
| `attest` | security | real adapter | in-toto Statement v1 unsigned provenance draft for a local artifact with SHA-256 digest |
| `license-matrix` | security | real adapter | multi-manifest dependency license auditor across pyproject.toml, package.json, and Cargo.toml with SPDX normalization and copyleft tiering |
| `iam-audit` | security | real adapter | static multi-cloud SDK (AWS, GCP, Azure) and Terraform wildcard usage auditor and least-privilege IAM policy synthesizer |
| `mem-profile` | quality | real adapter | static AST unclosed resource detection and optional dynamic memory probe under `--allow-slow` |
| `cold-start` | quality | real adapter | static Python AST import inventory and dynamic `-X importtime` module timing under `--allow-slow` |
| `media-opt` | quality | real adapter | SVG script security audit/sanitization and Pillow PNG/WebP raster optimization under `--allow-artifact-write` |
| `offline-review` | security | real adapter | air-gapped local LLM review runner (discovers Ollama or llama-cli on PATH; skips if absent) |
| `tui-diff` | workflow | real adapter | Git commit and finding delta computer with Rich terminal rendering and raw MCP payloads |
| `benchmark` | test | real adapter | performance sample comparison against baseline thresholds in `.rush/baselines.json` |
| `dead-asset` | quality | real adapter | static asset vs source reference scanner, potential savings calculator, and read-only manifest generator |
| `pr-synthesize` | workflow | real adapter | Git diff and ToolResult evidence parser synthesizing structured GitHub pull request markdown cards |


Generated help is authoritative for options. See [CLI reference](reference/cli-reference.md), [Engine directory](reference/engine-directory.md), and [Permissions](safety/permissions.md).



### Wire Format Options
* `--format json`: Standard JSON ToolResult payload (default).
* `--format toon`: Ultra-compact Token-Oriented Object Notation pipe-table formatting.
* `--format yaml`: YAML formatted findings.
* `--format ndjson`: Newline-delimited JSON stream.

### Custom Plugin Quality Engine (Phase 56)
- **Engine**: User-defined or third-party quality plugins.
- **Execution Model**: `HardenedPluginExecutor` with user trust ledger gating, transitive closure verification, immutable snapshot isolation, and `ToolResultV1` output compliance.

## Tool Cache Purity Catalog (Phase 57)

- **Pure Operations (Cache Eligible)**: `tool.lint`, `tool.typecheck`, `tool.complexity`, `tool.dead`, `tool.continuity`, `tool.semantic_drift`.
- **Side-Effecting Operations (Cache Bypassed)**: `tool.format` (in-place writes), `tool.test` (runtime execution), `tool.fix` (code patching), `admin.*`, `service.*`.

## Phase 58 Architecture: Capability Locks, CAS Memory, and Fail-Closed Patch Verification

These Phase 58 component contracts are not whole-application safety guarantees. Checkpoint symlink reads, governance symlink writes, sandbox fallback and patch cleanup remain open ([application review](reports/phase-64-66-application-review.md) F03–F05/F43; [Phase 64 runtime plan](phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md) P64-03/P64-04).

1. **Capability Locks & Verifier Custody (`rush.mcp_mesh`)**:
   - Callers retain high-entropy capability tokens (`LockCapabilityInput`) delivered exclusively via protected channels (`stdin`, `descriptor`, or sensitive MCP parameters); argv and environment leakage are rejected fail-closed.
   - `MeshLockManager` stores verifier-only records (`LockLeaseRecord`) generated via `rush.io.VerifierRecord` (PBKDF2-HMAC-SHA256, 100k rounds) with monotonic generation counters and `rush.io.PhysicalRoot` containment under `.rush/locks`.
   - Renewal and release verify caller capability in constant time (`hmac.compare_digest`); wrong, low-entropy, or stale tokens fail closed.

2. **CAS Map Transactions & Persistent Memory (`rush.memory`)**:
   - `CASMapTransaction` enforces optimistic concurrency with monotonic version numbers and atomic file replacement (`rush.io.AtomicFile`) using sanitized JSON payloads (`SanitizedJsonValue`).
   - Store states are truthfully separated into distinct typed exceptions: `StoreNotFoundError`, `StoreCorruptionError` (retaining raw bytes and SHA-256 digest), `StoreValidationError`, `StoreIOError`, and `CASConflictError` (exhausted retries fail closed).
   - `PreferenceStore`, `InvariantGraph`, and `MerkleInvalidator` eliminate silent empty dict fallbacks.

3. **Atomic Checkpoint Journals & Unified Store Persistence (`rush.memory.checkpoint_journal`)**:
   - `checkpoint_journal.py` is a thin compatibility view over `TypedArtifactStore` (`rush.memory.store`, Phase 61): `save_checkpoint()`/`restore_checkpoint()` write/read each checkpoint as one `MemoryArtifact` row (`family="handoff"`, `subject="active_context"`); canonical data lives in `.rush/memory.db`, not a per-checkpoint JSON file.
   - `save_checkpoint()` still writes a physical `.json` artifact via `rush.io.AtomicFile` and returns its `Path` (`dest.exists()` holds), preserving the pre-Phase-61 contract for existing callers; explicit schema version `1.0.0` is unchanged.
   - Corrupted or unparseable checkpoint files are preserved on disk, cryptographically digested with SHA-256, and surfaced in `list_checkpoints()` with status `corrupt` — unchanged by the Phase 61 migration.

4. **Contained Patch Verification & Atomic Rollback (`rush.patch`)**:
   - `PatchContract` cryptographically binds base commit, tree digest, patch content hash, sandbox directory under `rush.io.PhysicalRoot`, command plans, and policy review classes (`standard`, `policy-changing`, `privileged`).
   - Workspaces must be clean before sandboxing or patch application; dirty checkouts fail closed with `DirtyWorkspaceError`.
   - `PatchVerifier` requires at least one passing executed test command; zero executed commands return `outcome='unavailable'` and `False` (zero commands never verify).
   - Current rollback uses broad `git reset --hard`/`git clean -fd` and can destroy unrelated changes. It does not restore an exact pre-invocation index/worktree. Status: planned — bounded restoration in P64-01/P64-04, [Phase 64 runtime plan](phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md); [application review](reports/phase-64-66-application-review.md) F01/F43.

5. **Runtime Output Boundary Adapter Enforcement (`rush.contracts.operations`)**:
   - 100% of public operations declared in `governance/public-operations.toml` enforce their target adapters (`ToolOperationAdapter`, `AdminOperationAdapter`, `ServiceOperationAdapter`) at runtime boundaries while preserving native JSON-RPC service protocol messages.
### `tool.attest`
- Tool Name: `attest`
- Description: Generate in-toto Statement v1 SLSA provenance unsigned draft for build artifacts.
- Status: Production (Phase 59)
- Output: Canonical `ToolResultV1` with draft Statement v1.
