# CLI reference

Current authority: generated Click metadata from `uv run rush --help` and `uv run rush COMMAND --help` at source baseline `997b56e`. Examples assume the editable source checkout and therefore use `uv run rush`. Phase 65 owns standalone installation and the integrated beginner workflow; Phase 66 owns the persistent TUI and complete web workflow.

## `session resume`

`rush session resume NAME --provider {claude_code|codex_cli|antigravity_cli|9router_cli|omniroute_api} --allow-network [--json]` projects a bounded checkpoint receipt to an installed user-owned CLI or fixed loopback provider route. `9router_cli` starts Codex with fixed local 9Router environment variables and no model argument; it requires `RUSH_9ROUTER_API_KEY` but never retains it. Z.AI is intentionally deferred; `9router_api` returns canonical `skipped`.

## Session continuity

`rush session save NAME --file PATH --allow-cache-write --json`, `rush session list --json`, and `rush session restore NAME --json` are the session lifecycle. Save is denied by default; every `--json` response is a `ToolResult`.

## Memory (Phase 61)

`rush memory ask|write|promote|list|recall|maintain` queries and writes the unified `TypedArtifactStore` (`.rush/memory.db`). `ask`, `list`, and `recall` take positional `SUBJECT QUERY` and require `--session SOURCE`; all apply signature, staleness, and Trojan Source checks. `write`, `promote`, and `maintain` require `--allow-cache-write`. Approved promotions persist the `STATED` tier and checksum. For expiry maintenance, run `rush memory maintain --task expiry_sweep --allow-cache-write --json` from the repository.

Use `rush --help` and `rush COMMAND --help` as the generated source of truth. Global options are `--version`, `--log-level debug|info|warn|error`, and `--help`. `RUSH_LOG_LEVEL` sets the log-level default.

## Which command should I run?

```text
Need a quick maintainability pass? -> review
Need source style/correctness?      -> lint / format --check / typecheck
Need confidence from tests?        -> test, then evidence/advanced checks
Need dependency/secret evidence?   -> security / secrets / sbom / ai-eval
Need project-file checks?          -> markdown / yaml / sql / templates / containerfile / iac / actions
Need workflow inspection?          -> commit-msg / ci / release
```

## Common syntax and options

Command parameters are command-specific. Check generated help before invocation. `review` takes required `PATH`, `--llm`, `--use-graft`, repeatable `--changed-file`, permission flags, and `--json`; `format` also exposes `--check`.

```bash
uv run rush COMMAND --help
uv run rush review PATH [--llm] [--use-graft] [--changed-file RELATIVE_PATH]... [--json]
uv run rush format PATH [--check] [--json]
uv run rush ai-eval PATH [--json]
uv run rush mcp serve
```

`PATH` must exist. Human output is the default; `--json` returns the canonical result. Most commands do not modify files. The exception is `format` without `--check`, which can invoke formatter write modes; use version control and inspect the diff.

## Core code-quality commands

| Command | Purpose / when | Optional helpers | Results and modification |
|---|---|---|---|
| `review PATH` | Deterministic Python heuristics before review or after edits. | PR-Agent, local Graft with `--use-graft`; `--llm` is a no-call stub; repeat `--changed-file` for target-contained scope only. | `ok`/`warn`; read-only; no Git-diff inference. |
| `lint PATH` | Source linting. | Ruff, ESLint, Stylelint, ast-grep, Flake8-Bugbear, MegaLinter, Comby, Prisma-lint, Vale, CSpell, Alex, RedPen, No-Jargon, Markdown-Unfluff, Buf, wasm-tools, Git-Guard. | May `fail` on findings; read-only. |
| `format PATH --check` | Verify formatter conformance. | Ruff format, Prettier, Squoosh, Critical, Font-Spider, PyClean. | Check-only with `--check`; omit only when you intentionally allow formatting. |
| `test PATH` | Run applicable project tests. | pytest, Vitest, Newman. | `fail` on test failures; test code may have project-defined side effects. |
| `security PATH` | Dependency vulnerability, privacy SAST, container and env checks. | pip-audit, npm audit, OSV-Scanner, Semgrep, Trivy, Grype, Bearer, Horusec, Pa11y, OWASP ZAP, Deadfinder, A11yWatch, Dockle, Safe-Env, NCU. | Read-only normalization; scanner behavior depends on installed tool. |
| `typecheck PATH` | Static type checks. | mypy, TypeScript `tsc`. | Read-only; missing helper skips. |
| `dead PATH` | Find unused code and dependencies. | Vulture, Knip, FawltyDeps, Ts-prune. | Advisory/read-only. |
| `complexity PATH` | Complexity, bundle weight, binary footprint and memory evidence. | Radon, jscpd, Depcruise, Scaphandre, Readability, Memray, Statoscope, Bloaty. | Metrics/findings; read-only. |
| `slop PATH` | Deterministic code-noise and AI filler signals. | sloppylint, Markdown-Unfluff plus JS/TS fallback. | Advisory; no authorship inference. |
| `fix [PATH]` | Current remediation command; checkout/index preservation repair remains pending. | Ruff, Biome, ESLint, Prettier, ast-grep. | Do not run on valued work until [P64-01](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md#p64-01--preserve-checkoutindex-during-fixes-f01) is implemented and verified. Current options include `--dry-run` and `--force`. |

## AI, LLM & Agent Safety (Phase 09)

| Command | Purpose | Optional helpers | Notes |
|---|---|---|---|
| `ai-eval PATH` | Evaluate LLM prompts, agent workflows, and guardrails. | Promptfoo, Garak, DeepEval, Guardrails. | Tests prompt injection, jailbreaks, RAG faithfulness, and safety policies. |

## Project-file and infrastructure commands

| Command | Checks | Optional helper | Modification |
|---|---|---|---|
| `markdown` | Markdown and prose style rules | markdownlint-cli, Lychee, Vale, Alex, No-Jargon | none |
| `yaml` | YAML/OpenAPI under owned rules; remote references blocked | Spectral, Zally | none |
| `sql` | SQL lint and schema migration safety | SQLFluff, Atlas, Squawk | none |
| `templates` | HTML/Jinja templates | djLint, HTML-Validate | none |
| `containerfile` | Dockerfile/Containerfile and CIS benchmark | Hadolint, Dockle | none |
| `iac` | Terraform and Kubernetes lint/policy | TFLint, Checkov, Kubeconform, Terrascan, Kube-score, Conftest, Polaris, KubeLinter | none |
| `actions` | GitHub Actions YAML | Actionlint | none |

| Command | Purpose | Notes |
|---|---|---|
| `secrets PATH` | Scan for secrets, leaked credentials, and default dev values. | Gitleaks, TruffleHog, Secretlint, detect-secrets, Safe-Env. Values are redacted from normalized findings. |
| `codeql PATH` | Import SARIF 2.1.0 report or execute CodeQL CLI. | CodeQL (`--allow-build` required for execution). |
| `sbom PATH [-o OUTPUT] [--overwrite]` | Generate SBOM and audit license copyleft risk. | cdxgen, ScanCode, GUAC, pip-licenses. `--overwrite` requires `--allow-artifact-write`. |

## Capabilities and planning

`rush capabilities PATH --json` reads local project markers, allowed `rush.toml` tables, known local report filenames, and `PATH`; it does not execute, install, or version-probe an engine. States distinguish configured, installed, applicable, missing, and blocked. `rush plan PATH --profile default|nonbrowser --json` expands that inventory deterministically with report/engine prerequisites; browser-runtime capabilities remain absent from `nonbrowser`.

## Test-confidence and advanced commands

`coverage`, `pbt`, `flaky`, `contract`, `snapshot`, `mutation`, `fuzz`, and `load` operate in dual modes:
1. **Imported mode**: Pass the report file as `PATH` or specify `--report-path <file>`. Imports local structured reports (coverage.py JSON/LCOV/Cobertura, JUnit, Pact, snapshot JSON, mutmut, Atheris, k6).
2. **Executed mode**: Run under explicit permission flags (e.g. `--allow-slow`, `--allow-network`, `--allow-build`, `--allow-artifact-write`).

`e2e`, `visual`, and `semantic-drift` provide browser runtime evidence:
- `e2e PATH`: Playwright E2E runner; requires `--allow-browser`.
- `visual PATH`: Visual baseline check; requires `--allow-browser` and `--allow-slow` (and `--allow-artifact-write` for `--accept`).
- `semantic-drift PATH`: DOM/accessibility drift verification; requires `--allow-browser` and `--allow-slow`.

## Permission Flags

Evaluation commands expose permission flags according to their own generated help. Common flags are:
- `--allow-network`: Permit network requests.
- `--allow-download`: Permit downloading vulnerability feeds or schemas.
- `--allow-cache-write`: Permit writing local caches.
- `--allow-build`: Permit compiling project code or analysis databases.
- `--allow-slow`: Permit long-running analysis or execution.
- `--allow-artifact-write`: Permit overwriting or creating report/baseline artifacts.
- `--allow-browser`: Permit launching browser engines.

## Workflow suites and developer commands

| Command | Purpose | Options | Modification |
|---|---|---|---|
| `check PATH` | Fast inner-loop workflow suite (lint, format --check, typecheck). | Permissions | none |
| `audit PATH` | Deep security, dependency, secret, and supply chain suite. | Permissions | none |
| `gate PATH` | Strict pre-merge gating suite (lint, format, typecheck, test, security). | `--fail-fast`, Permissions | none |
| `fix PATH` | Confined automated remediation for formatting and linter errors. | `--dry-run`, `--force` | Modifies code within workspace |
| `setup [PATH]` | Current stack inspection/setup prototype. Integrated, verified installation remains planned in [P65-02](../phase-plans/phase-65-project-provisioning-scan-and-agent-workflow-plan.md#p65-02--install-complete-applicable-toolchains-f3031). | `--non-interactive`, `--json` | Current package-manager identities and execution branches are not accepted installation evidence |
| `init [PATH]` | Generate starter `rush.toml` for detected project stacks. | `--force` | Writes `rush.toml` |
| `config check PATH` | Validate `rush.toml` schema and tool configuration keys. | none | none |
| `doctor PATH` | Audit environment health, toolchain integrity, and anti-shadowing. | none | none |
| `watch PATH` | Real-time file system watcher with debouncing. | `--suite`, `--tool`, `--debounce` | none |
| `ui [PATH]` | Current one-shot Rich terminal summary. Persistent navigation remains planned in [P66-03](../phase-plans/phase-66-interactive-tui-and-local-web-plan.md#p66-03--persistent-colorful-animated-tui-f36). | Permissions | none |
| `dashboard [PATH]` | Current local web prototype. Its browser/server API is broken at this baseline; repair and complete workflow remain planned in [P66-01 through P66-07](../phase-plans/phase-66-interactive-tui-and-local-web-plan.md). | `--port`, Permissions | starts local server only after synchronous checks |
| `trust PATH` | Authorize repository in local trust ledger to allow custom plugins. | `--revoke` | Updates `~/.rush/trusted_repositories.json` |
| `plugin list PATH` | List configured custom plugins in `rush.toml`. | none | none |
| `plugin run NAME PATH` | Execute custom plugin against target path. | `--json` | Executes declared command if trusted |

## Advanced Autonomous Agent, Hygiene & Governance Commands (Phases 29–40)

| Command | Purpose | Key Flags & Arguments | Modification |
|---|---|---|---|
| `patch apply PATH` | Apply AI-generated remediation patches in isolated Git worktree sandbox. | `--dry-run`, `--circuit-breaker` | Applies patch in isolated worktree |
| `guard check-cmd CMD` | Intercept destructive/harmful shell commands before execution. | none | none |
| `guard check-path PATH` | Enforce repository boundary path confinement. | none | none |
| `token count PATH` | Fast byte-pair encoding (BPE) token counting for LLM context windows. | none | none |
| `outline PATH` | AST code outline compression (stripping docstrings/bodies for context optimization). | none | none |
| `sync openapi PATH` | Verify OpenAPI spec against backend implementation and generate TypeScript types. | `--output-ts <PATH>` | Writes TS interface if output specified |
| `hygiene dead-code` | Scan project for unreferenced polyglot symbols and dead exports. | none | none |
| `conflict solve FILE_A FILE_B` | 3-way AST merge resolver reconciling conflicting source files. | none | Outputs resolved source |
| `codegraph slice SYMBOL` | Extract verbatim symbol source slice with line numbers from CPG database. | none | none |
| `bundle analyze DIST_DIR` | Measure build chunk transfer sizes (raw, gzip, brotli) and evaluate budget gates. | none | none |
| `hotspots analyze` | Compute composite defect risk scores combining commit churn and McCabe complexity. | none | none |
| `governance sync` | Compile canonical `AGENTS.md` into multi-IDE rule files (`.cursorrules`, `.clinerules`, etc.). | none | Writes IDE rule files |
| `scaffold init` | Initialize repository with canonical `AGENTS.md` and `rush.toml` templates. | none | Writes scaffold templates |
| `hook run` | Sub-second pre-commit intelligence suite across staged files (AST lint, Trojan Source, conflict markers). | none | none |
| `score compute` | Calculate deterministic 0–100% 6-pillar repository health score and letter grade. | `--type-safety`, `--test-coverage`, `--code-health`, `--security`, `--token-economy`, `--governance` | none |
| `consensus reconcile` | Reconcile multi-model AI code review findings with weighted agreement voting. | none | none |

## Command-specific scoping, caching, and monorepo options

These flags exist on selected commands only. `uv run rush COMMAND --help` is authoritative for each command:
- `--workspace`, `-w <NAME>`: Scope execution to a specific monorepo workspace package.
- `--all-workspaces`: Execute evaluation across all discovered monorepo packages in topological order.
- `--cache / --no-cache`: Enable or disable flag-salted SQLite result caching (`.rush/cache.db`).
- `--cache-dir <PATH>`: Custom cache directory location.
- `--clear-cache`: Purge cached tool results before execution.
- `--staged`: Restrict analysis scope to git staged files.
- `--since <REF>`: Restrict analysis scope to files modified since the specified git revision.
- `--branch <NAME>`: Restrict analysis scope to files modified on the given git branch.

## Polyglot Quality & Security Commands (Phase 50a)

| Command | Purpose | Key Flags & Arguments | Modification |
|---|---|---|---|
| `error-catalog PATH` | Extract exceptions across Python AST, TypeScript, and Rust, mapping to RFC 7807 problem details. | Shared evaluation/import/report flags shown by generated help; no `--export-docs`, `--output-module`, or `--operation` CLI option. | Current CLI returns result data; its help text still mentions an unavailable markdown export. |
| `license-matrix [PATH]` | Audit dependencies across `pyproject.toml`, `package.json`, and `Cargo.toml` for copyleft risk. | Permissions and `--json`; no `--allowed-licenses` or `--export-path` CLI option. | Current CLI returns result data. |
| `iam-audit [PATH]` | Statically inspect cloud SDKs and Terraform wildcard permissions to synthesize minimal IAM policy. | `-o/--output PATH`, permissions, `--json`. | Output requires `--allow-artifact-write`. |

## Workflow commands

| Command | Current behavior |
|---|---|
| `commit-msg PATH [-m MESSAGE]` | Validates Conventional Commit message passed via `-m/--message` or read from file. commitlint reference test suite. Never rewrites history. |
| `ci PATH` | Inspects local workflow files and checks OpenSSF Scorecard supply chain posture. |
| `release PATH` | Creates a dry-run inventory/plan and verifies signatures and SLSA build attestations via Cosign, Cejel, and SLSA Verifier. |
| `tdd PATH` | Verifies Test-Driven Development (TDD) compliance and test existence for modified modules. |
| `doctor PATH` | Diagnoses environment health, installed quality engines, PATH precedence, and virtual environment status. |

## MCP

`uv run rush mcp serve` starts a local stdio server and blocks until stdin closes. It opens no HTTP port. See [MCP overview](../integrations/mcp-overview.md).

## Result and exit behavior

`ok` and `skipped` exit 0; `warn` and `fail` exit 1; `error` exits 2. A mandatory check that skips must be rejected by inspecting JSON, because exit code 0 alone is intentionally non-fatal. See [Result reference](result-reference.md).


### `rush provenance-ai`
Audit Git commit trailers for AI attribution and compute code survival curves.

### `rush dead-asset`
Scan repository for unreferenced static media, fonts, and assets with potential space savings calculation.

### `rush pr-synthesize`
Synthesize semantic PR markdown card from Git diff, risk tiering, and CODEOWNERS routing.

### `rush attest`
Generate in-toto Statement v1 SLSA provenance draft for built distribution artifacts in `dist/`.

### `rush mem-profile`
Scan Python code for unclosed resources (files, sockets, handles) and sample RSS memory.

### `rush cold-start`
Detect heavy top-level imports and analyze import latency waterfall.

### `rush offline-review`
Run air-gapped local ONNX code review model over codebase files.

### `rush benchmark`
Compare performance execution samples against recorded thresholds in `.rush/baselines.json`.

### Plugin CLI Commands (Phase 56)
- `rush trust plugin <name>`: Authorize plugin closure.
- `rush trust plugin <name> --revoke`: Revoke authorization.
- `rush plugin run <name> [PATH]`: Execute plugin against specified path from verified snapshot.

## Invocation Flags and Exit Behavior (Phase 57)

- `--no-cache`: Explicit bypass performing 0 cache reads and 0 cache writes.
- Exit Codes: 0 (OK/Skipped), 1 (Warning), 2 (Error/Blocked). Admin commands preserve explicit integer codes.

## Phase 58 Architecture: Capability Locks, CAS Memory, and Fail-Closed Patch Verification

Rush implements closed-loop resilience, fail-closed security, and physical containment across multi-agent concurrency, persistent memory, and AI-driven patch remediation (Findings R-009, R-010, R-011, R-016):

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

4. **Contained Patch Verification (`rush.patch`) — current safety repair pending**:
   - `PatchContract` cryptographically binds base commit, tree digest, patch content hash, sandbox directory under `rush.io.PhysicalRoot`, command plans, and policy review classes (`standard`, `policy-changing`, `privileged`).
   - Workspaces must be clean before sandboxing or patch application; dirty checkouts fail closed with `DirtyWorkspaceError`.
   - `PatchVerifier` requires at least one passing executed test command; zero executed commands return `outcome='unavailable'` and `False` (zero commands never verify).
   - Current promotion cleanup contains broad `git reset --hard`, `git clean -fd`, and worktree cleanup. Do not promote this as safe public behavior. Invocation-owned restoration is required by [P64-04](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md#p64-04--real-isolated-patch-application-f05-f2425-f43).

5. **Runtime Output Boundary Adapter Enforcement (`rush.contracts.operations`)**:
   - 100% of public operations declared in `governance/public-operations.toml` enforce their target adapters (`ToolOperationAdapter`, `AdminOperationAdapter`, `ServiceOperationAdapter`) at runtime boundaries while preserving native JSON-RPC service protocol messages.
### `rush attest` CLI Reference (Phase 59)
Command options: `-a/--artifact-path`, `-o/--out`, `--builder-id`, `--verify`, `--trusted-root`, `--allowed-signer`, permissions, and `--json`.
