# CLI reference

Current authority: generated Click metadata from `uv run rush --help` and `uv run rush COMMAND --help` at source baseline `997b56e`. Examples assume the editable source checkout and therefore use `uv run rush`. Phase 65 owns standalone installation and the integrated beginner workflow; Phase 66 owns the persistent TUI and complete web workflow.

## Discovering commands

`rush --help` lists the everyday set — `status`, `check`, `lint`, `review`, `security`, `test`, `memory`, `setup`, `install`, `agent`, `mcp` — plus a category index. Registered commands fall under one of seven categories: `quality`, `security`, `test`, `workflow`, `memory`, `services`, `administration`. Use `rush help` to list the categories, `rush help CATEGORY` to list the commands in one, and `rush --help-all` to list all registered command names at once (including everyday-set members and category-only names).

## `session resume`

`rush session resume NAME --provider {claude_code|codex_cli|antigravity_cli|9router_cli|omniroute_api} --allow-network [--json]` projects a bounded checkpoint receipt to an installed user-owned CLI or fixed loopback provider route. `9router_cli` starts Codex with fixed local 9Router environment variables and no model argument; it requires `RUSH_9ROUTER_API_KEY` but never retains it. Z.AI is intentionally deferred; `9router_api` returns canonical `skipped`.

## Session continuity

`rush session save NAME --file PATH --allow-cache-write --json`, `rush session list --json`, and `rush session restore NAME --json` are the session lifecycle. Save is denied by default; every `--json` response is a `ToolResult`.

## Memory (Phase 61)

`rush memory ask|write|promote|list|recall|maintain` queries and writes the unified `TypedArtifactStore` (`.rush/memory.db`). `ask`, `list`, and `recall` take positional `SUBJECT QUERY` and require `--session SOURCE`; all apply signature, staleness, and Trojan Source checks. `write`, `promote`, and `maintain` require `--allow-cache-write`. Approved promotions persist the `STATED` tier and checksum. For expiry maintenance, run `rush memory maintain --task expiry_sweep --allow-cache-write --json` from the repository.

Bare `rush memory [--offset N --generation TOKEN] [--include-internal] [--json]` (no subcommand) is a read-only overview: this project's 20 most recent useful memory records, newest first (archived, expired, and internal bookkeeping rows hidden by default; pass `--include-internal` to also show them). `--offset`/`--generation` page through older rows — `--offset` above 0 requires the `--generation` continuation token the previous page printed. A store needing migration reports `migration_required`; an unreadable store reports `corrupt`.

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

Most catalog commands also accept `--result-view [full|compact]` (full, the default, prints the whole result and writes nothing; compact stores the full redacted result in `.rush/cache/ccr.db`, requires `--allow-cache-write`, and is not allowed with `--no-cache`), `--limit N` (compact view: findings per page, 1-50, default 50), `--max-bytes N` (compact view: size budget of the whole printed result, 4096-65536 bytes, default 32768), and `--no-cache` (bypass and do not write to the result cache).

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
| `typecheck PATH` | Static type checks. | mypy, TypeScript `tsc`; `--environment project\|isolated` selects which interpreter analyzes Python (`project` uses `.venv` and requires `--allow-build`; default prefers `project`, falling back to `isolated` without `--allow-build`), `--typecheck-config FILE` names an explicit tsconfig/mypy/pyrefly config inside the project root. | Read-only; missing helper skips. |
| `dead PATH` | Find unused code and dependencies. | Vulture, Knip, FawltyDeps, Ts-prune. | Advisory/read-only. |
| `complexity PATH` | Complexity, bundle weight, binary footprint and memory evidence. | Radon, jscpd, Depcruise, Scaphandre, Readability, Memray, Statoscope, Bloaty. | Metrics/findings; read-only. |
| `slop PATH` | Deterministic code-noise and AI filler signals. | sloppylint, Markdown-Unfluff plus JS/TS fallback. | Advisory; no authorship inference. |
| `fix [PATH]` | [Bounded Ruff remediation](../phase-plans/phase-64-implementation-evidence.md#p64-01--preserve-checkoutindex-during-fixes-f01) for selected Python targets. | Ruff. | Dry run preserves Git state; apply requires `--allow-artifact-write`. P64-04 remains planned. |

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
| `check PATH` | Run the check suite: format (check-only), lint, typecheck, dead, slop, test; the test step needs `--allow-build`. | `--fail-fast`/`--no-fail-fast` (default: every step runs and is reported), `--result-view`, `--limit`, `--max-bytes`, Permissions, `--json` | none |
| `status [PATH]` | Show the project's status without changing anything. | `--session`, `--result HANDLE` (read a stored result), `--view [result\|bytes]`, `--cursor`, `--offset`, `--limit`, `--max-bytes`, `--json` | none |
| `audit PATH` | Deep security, dependency, secret, and supply chain suite. | Permissions | none |
| `gate PATH` | Strict pre-merge gating suite (lint, format, typecheck, test, security). | `--fail-fast`, Permissions | none |
| `fix PATH` | [Bounded Ruff remediation](../phase-plans/phase-64-implementation-evidence.md#p64-01--preserve-checkoutindex-during-fixes-f01) for selected Python targets. | `--dry-run`, `--force`, `--allow-artifact-write` | Dry-run preview; apply is denied without artifact-write permission. |
| `setup [PATH]` | Preview project setup (config, registration, engine provisioning) and apply it after consent: `rush setup PATH` previews; `--save-plan FILE --allow-artifact-write` writes the reviewed plan and prints the exact apply command; `--apply --yes --plan-file FILE --plan-id ID` (plus the plan's own `--allow-*` grants) applies it non-interactively. | `--interactive`/`--non-interactive`, `--apply`, `--yes`, `--plan-file`, `--plan-id`, `--save-plan`, `--agent claude\|codex`, `--install-guidance`, `--enable-agent-hooks`, `--verify-host`, `--allow-*`, `--json`, `--install` (accepted for compatibility, no effect) | Preview writes nothing; `--save-plan` writes the plan file; `--apply` performs the reviewed config/registration/engine writes |
| `init [PATH]` | Generate starter `rush.toml` for detected project stacks. | `--force` | Writes `rush.toml` |
| `config check PATH` | Validate `rush.toml` schema and tool configuration keys. | none | none |
| `doctor PATH` | Audit environment health, toolchain integrity, and anti-shadowing. | none | none |
| `watch PATH` | Real-time file system watcher with debouncing. | `--suite`, `--tool`, `--debounce` | none |
| `ui [PATH ...]` | At a TTY, persistent Rich UI with background checks and keyboard navigation. `--json` runs checks once, emits JSON, and exits; redirected stdout without `--json` runs checks once and prints a text summary. | `--json`, Permissions | none |
| `dashboard [PATH]` | Authenticated, CSRF-hardened local web dashboard on `127.0.0.1` behind a single-use bootstrap URL; mutations require an explicit grant per action. See [the dashboard/TUI review](../reports/69-dashboard-tui-codex-implementation-review.md) for unresolved findings. | `--port`, `--reconnect`, Permissions | starts local server, opens browser to a per-server session URL |
| `gain` | Live-updating Rich HUD of token compression and dollar savings; re-renders until Ctrl+C. `context gain` is a live alias for the same command, not a one-shot summary. | none | none |
| `trust PATH` | Authorize repository in local trust ledger to allow custom plugins. | `--revoke` | Updates `~/.rush/trusted_repositories.json` |
| `plugin list PATH` | List configured custom plugins in `rush.toml`. | none | none |
| `plugin run NAME PATH` | Execute custom plugin against target path. | `--json` | Executes declared command if trusted |

### `rush status` and bare `rush`

`rush status [PATH]` and bare `rush` (no subcommand) print the same read-only view: project root, registration/config state, detected engines, current activity, latest attempt, published result, agent registration/activation state, and useful memory count. Neither writes anything. On an unregistered project, the summary opens with a one-line banner (`warn -- unregistered project /path/to/project; no analysis has run; project is not registered.`) followed by:

```text
Project
  root: /path/to/project
  registration: unregistered
  configured: no
Config
  rush.toml: missing
Engines
  none detected
Activity
  idle
Latest attempt
  none
Published result
  none
Agents
  claude-desktop: not_detected, activation unverified
  claude-code: not_detected, activation unverified
  cursor: not_detected, activation unverified
  windsurf: not_detected, activation unverified
  zed: not_detected, activation unverified
  codex: not_detected, activation unverified
Memory
  absent
Next actions
  project is not registered: rush setup /path/to/project
```

`rush status --json` returns the canonical `ToolResult`; `--result HANDLE` with `--view result|bytes`, `--cursor`, `--offset`, `--limit`, `--max-bytes` retrieves a stored result page, the same contract as `rush context retrieve`.

### `rush check`'s six steps

`rush check PATH` runs `format` (check-only), `lint`, `typecheck`, `dead`, `slop`, then `test` in that order; every step runs and is reported by default (`--fail-fast` stops at the first failing step and reports the rest not run). The `test` step needs `--allow-build`; without it, `test` is `skipped` with the permission reason. Example against a project with one unused function and no test config:

```text
[CHECK] Status: warn
check: executed 5 tool(s) with status 'warn'
  1. format    ok      format [ruff]: all formatted
  2. lint      ok      lint [ruff]: clean
  3. typecheck ok      typecheck [mypy+pyrefly]: 0 finding(s)
  4. dead      warn    dead [vulture]: 1 finding(s)
  5. slop      skipped skipped: requires permission: --allow-download (aislop's npm package is not in the local npm cache) (permission_denied)
  6. test      skipped test: no pyproject.toml or package.json found above /path/to/project
6/6 steps
  - [warn] unused function 'f' (60% confidence)
1/1 findings
```

### Deduplicated diagnostics

`lint` and `check` collapse identical repeated findings emitted by the same producer at the same physical file (matched by inode identity, falling back to the lexical path when the file is missing) into one; a finding that differs in end location, message, fix, evidence, or producer stays separate, and results spanning multiple engines/languages keep each engine's own counts distinct.

### Memory contribution in scan/check summaries

When a scan or check run's tools actually read or wrote memory records, its summary line ends with one clause built from that run's own `metadata.memory` union: `memory: read {N} prior record(s), wrote {M} record(s)`, for example `"probe-suite: executed 2 tool(s) with status 'ok'; memory: read 1 prior record, wrote 1 record"`. The clause is omitted entirely when neither happened; the record ids are in `metadata.memory.used`/`.written` for `--json`/detail output.

## `rush agent list|connect|disconnect|doctor|hook` (Phase 65 P65-05)

- `rush agent list [--json]` reports every supported client's (`claude-desktop`, `claude-code`, `windsurf`, `zed`, `codex`) exact discovered state without writing anything.
- `rush agent connect AGENT_ID --session ID [--project PATH] [--rush-binary PATH] [--consent] [--acknowledge] [--install-guidance] [--profile core|full] [--yes] --allow-cache-write --allow-artifact-write [--json]` registers Rush into that agent's own config file (format-preserving, backed up first) and activates a Phase 63 memory scope for `(project-or-user, session, agent)`.
- `rush agent disconnect AGENT_ID [--project PATH] [--json]` removes Rush's own, unchanged components for `AGENT_ID` — the MCP entry, the instruction block (or this agent from a shared block), and Rush skill/hook resources recorded as Rush-owned. Anything changed since Rush wrote it is kept and reported as a conflict. Running it again is a no-op.
- `rush agent doctor [--session ID] [--project PATH] [--json]` re-probes every client's real on-disk config and the memory scope's current state, without writing anything.
- `rush agent hook {claude|codex}` is the post-edit hook entrypoint the Rush Claude Code/Codex plugins run. It reads the host's JSON event on stdin, prints nothing, and runs no check unless agent hooks are enabled for this host and project; it always exits 0 so a hook never changes the edit's result.

Registered MCP reaches `rush_agent_connection(request)`, the single-`dict` envelope over `AgentConnectionTool.handle_request` (`src/rush/tools/agent_connection.py`).

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
| `governance sync` | Compile canonical `AGENTS.md` into multi-IDE rule files (`.clinerules`, etc.). | none | Writes IDE rule files |
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

`uv run rush mcp serve [--project ID_OR_PATH] [--session SOURCE] [--memory-session SESSION] [--profile core|full]` starts a local stdio server and blocks until stdin closes. It opens no HTTP port. `--project` anchors every relative path to that one registered project (an unknown project fails at startup); `--session` supplies the default `session_id` for project/scan tools when a caller omits it. `--profile core` registers exactly seven agent tools (`rush_status`, `rush_check`, `rush_lint`, `rush_review`, `rush_security`, `rush_test`, `rush_memory`); `--profile full` (the default) registers every tool, and a call outside the running profile's registered set returns "Unknown tool". `--profile` is ignored with `--memory-session`. See [MCP overview](../integrations/mcp-overview.md).

## Result and exit behavior

`ok` and `skipped` exit 0; `warn` and `fail` exit 1; `error` exits 2. A mandatory check that skips must be rejected by inspecting JSON, because exit code 0 alone is intentionally non-fatal. See [Result reference](result-reference.md). For example, `rush lint /no/such/path` (no such target) returns `error` and exits 2; `rush check` with only an advisory finding returns `warn` and exits 1.


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
