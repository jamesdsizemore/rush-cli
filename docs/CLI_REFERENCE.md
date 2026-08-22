# CLI reference

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

Every catalog path command takes `PATH` and `--json`. `review` also takes `--llm`, `--use-graft`, and repeatable `--changed-file`; `format` also takes `--check`.

```bash
rush COMMAND PATH [--json]
rush review PATH [--llm] [--use-graft] [--changed-file RELATIVE_PATH]... [--json]
rush format PATH [--check] [--json]
rush ai-eval PATH [--json]
rush mcp serve
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
| `fix PATH` | Safely auto-remediate formatting and linter issues. | Ruff, Biome, ESLint, Prettier, ast-grep. | Applies safe fixes across files; supports `--dry-run` and `--force`. |

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

The following explicit permission flags are available across tools:
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
| `setup PATH` | Polyglot technology stack auto-discovery and toolchain installer. | `--non-interactive` | Installs local engines via package managers |
| `init PATH` | Generate tailored `rush.toml` for detected project stacks. | `--overwrite` | Writes `rush.toml` |
| `config check PATH` | Validate `rush.toml` schema and tool configuration keys. | none | none |
| `doctor PATH` | Audit environment health, toolchain integrity, and anti-shadowing. | none | none |
| `watch PATH` | Real-time file system watcher with debouncing. | `--suite`, `--tool`, `--debounce` | none |
| `ui PATH` | Launch interactive terminal UI (TUI) for finding exploration. | Permissions | none |
| `dashboard PATH` | Authenticated, CSRF-hardened local web dashboard on 127.0.0.1. | `--port`, Permissions | none |
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

## Advanced Scoping, Caching & Monorepo Options

The following flags are supported across evaluation commands:
- `--workspace`, `-w <NAME>`: Scope execution to a specific monorepo workspace package.
- `--all-workspaces`: Execute evaluation across all discovered monorepo packages in topological order.
- `--cache / --no-cache`: Enable or disable flag-salted SQLite result caching (`.rush/cache.db`).
- `--cache-dir <PATH>`: Custom cache directory location.
- `--clear-cache`: Purge cached tool results before execution.
- `--staged`: Restrict analysis scope to git staged files.
- `--since <REF>`: Restrict analysis scope to files modified since the specified git revision.
- `--branch <NAME>`: Restrict analysis scope to files modified on the given git branch.

## Workflow commands

| Command | Current behavior |
|---|---|
| `commit-msg PATH [-m MESSAGE]` | Validates Conventional Commit message passed via `-m/--message` or read from file. commitlint reference test suite. Never rewrites history. |
| `ci PATH` | Inspects local workflow files and checks OpenSSF Scorecard supply chain posture. |
| `release PATH` | Creates a dry-run inventory/plan and verifies signatures and SLSA build attestations via Cosign, Cejel, and SLSA Verifier. |
| `tdd PATH` | Verifies Test-Driven Development (TDD) compliance and test existence for modified modules. |
| `doctor PATH` | Diagnoses environment health, installed quality engines, PATH precedence, and virtual environment status. |

## MCP

`rush mcp serve` starts a local stdio server and blocks until stdin closes. It opens no HTTP port. See [MCP overview](integrations/mcp-overview.md).

## Result and exit behavior

`ok` and `skipped` exit 0; `warn` and `fail` exit 1; `error` exits 2. A mandatory check that skips must be rejected by inspecting JSON, because exit code 0 alone is intentionally non-fatal. See [Result reference](reference/result-reference.md).


## Context Intelligence & Ship Commands (Phases 41–43)

### `rush session save <name>`
Save a developer session checkpoint snapshot to `.rush/sessions/`.
* `--file, -f`: Specify active files to include.

### `rush session list`
List all saved session checkpoints in `.rush/sessions/`.

### `rush session restore <name>`
Restore a saved session checkpoint by name.

### `rush ship clean`
Purge temporary scratch directories, caches, and build artifacts.
* `--dry-run`: Preview files to be removed without deleting.

### `rush ship env`
Lint codebase environment variable usage against `.env.example`.

### `rush ship docs`
Audit documentation links and CLI reference parity across `docs/`.

### `rush ship gate`
Run the unified 7-vector pre-flight release readiness cockpit concurrently.

### `rush ship migration`
Audit SQL migration files for table-locking hazards via `sqlglot`.

### `rush ship semver <old_file> <new_file>`
Check for breaking public API signature changes.

### `rush ship pack`
Audit source tree for accidental secret leaks before packaging.

### `rush token outline <path>`
Generate a token-efficient AST skeleton outline of a code file.

### `rush context retrieve <chunk_hash>`
Retrieve raw uncompressed content from the CCR chunk database.

### `rush context mistakes`
Display historical Git-revert mistake guardrails.

### `rush hallu-guard`
Audit codebase for hallucinated or phantom package imports.

### `rush context pack`
Pack graph-pruned context envelope under a strict token budget.
* `--path, -p`: Target file path to pack (required).
* `--symbol, -s`: Focus symbol to keep verbatim.
* `--budget, -b`: Maximum token budget (default: 4000).

### `rush context align-prompt`
Align prompt prefix above provider cache boundary (>=1024 tokens).
* `--system, -s`: System prompt string to align.

### `rush context gain`
Launch the interactive Rich terminal HUD displaying token compression and dollar savings.

### `rush context persona`
View or configure agent terse response persona style.
* `--set`: Set persona style (`terse` | `default`).

### `rush blast-radius`
Analyze downstream transitive blast radius and affected tests.
* `--path, -p`: Changed file path to analyze (required).
* `--depth, -d`: Maximum traversal depth (default: 5).

### `rush arch-guard`
Evaluate codebase against declarative architectural layer boundary rules.

### `rush test-heal`
Diagnose flaky test race conditions and suggest stabilization fixes.
* `--target, -t`: Target test file path (required).
* `--runs, -r`: Number of perturbation runs (default: 5).

### `rush api-diff`
Detect breaking public API signature changes against base Git ref.
* `--base, -b`: Base Git ref to compare against (default: main).
