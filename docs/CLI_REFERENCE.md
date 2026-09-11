# CLI reference

## Recover an omitted context pack

When `rush context pack --budget N --allow-cache-write --json` returns `skipped` with `metadata.context_envelope.recovery.state: "available"`, pass its handle to `rush context retrieve HANDLE --json`. Without explicit cache-write permission, an insufficient budget returns `recovery.state: "not_created"` with `cache_write_required` and writes no CCR data. Stored payloads are redacted before local persistence; an unknown handle remains a structured `skipped` result.

## Session checkpoints

Use `rush session save NAME --file PATH --allow-cache-write --json` to save a local checkpoint, `rush session list --json` to inspect it, and `rush session restore NAME --json` to retrieve it. All three return a canonical `ToolResult` with `--json`; save without `--allow-cache-write` returns `status: "skipped"` and writes nothing. A deliberate handoff adds `--goal TEXT`, repeatable `--open-work TEXT`, `--historic-instruction TEXT`, `--failure-fingerprint SHA256`, and repeatable repository-relative `--dependency PATH`; only the redacted receipt is persisted.

`rush context pack --path FILE [--symbol NAME] [--budget N] --json` and `rush context retrieve HASH --json` use the same canonical contract. A too-small budget or missing hash is structured `skipped`, never fabricated context.

`rush session resume NAME --provider 9router_cli --allow-network --json` runs the installed Codex CLI through fixed local 9Router. Set `RUSH_9ROUTER_API_KEY` only in the invoking process; Rush copies it only into that child process and does not send a model argument.

The catalogued `continuity` tool also accepts `coordination_check`, `coordination_merge_preview`, and `coordination_recovery` through its JSON/MCP contract. These are evidence-only operations: stale or held locks, merge conflicts, and failure/replay receipts require explicit human or agent follow-up; Rush does not unlock, merge, or retry automatically.

Use `rush session resume NAME --provider claude_code|codex_cli|antigravity_cli --allow-network --json` to hand a saved checkpoint to an already-authenticated local coding CLI. Rush sends only the current goal, open work, and freshness—not historic instructions, credentials, raw transcript, failed patch, or provider output. Z.AI is explicitly deferred and returns `skipped` without process invocation.

Use `rush --help` and `rush COMMAND --help` as the generated source of truth. Global options are `--version`, `--log-level debug|info|warn|error`, and `--help`. `RUSH_LOG_LEVEL` sets the log-level default.

## Operations Reconciliation & Inventory (Phase 51 & Phase 54)

Historical Phase 51/54 inventory below is not the current registration count. Current `collect_runtime_contracts()` observes 198 CLI paths including groups (29 groups, 169 leaves), 79 MCP tools, 54 catalog tools, and (Phase 65 P65-09) 121 engine registrations. Full parameter/type/default tuples are checked in the [current generated CLI reference](reference/cli-reference.md).
- **Historical Tool Operations (`kind = "tool"`)**: The old inventory counted 67 operations. When invoked with `--json`, return canonical `ToolResultV1` JSON (`schema_version: "1.0.0"`), validated through `ToolOperationAdapter`.
- **Historical Admin Operations (`kind = "admin"`)**: The old inventory counted 62 operations (e.g. `version`, `doctor`, `capabilities`). Return exit codes (`ClickExitCode`) or specialized admin data, validated through `AdminOperationAdapter`, and are not wrapped in `ToolResultV1`.
- **Historical Service Operations (`kind = "service"`)**: The old inventory counted 17 operations (e.g. `rush mcp serve`). Handle stdio and protocol streams, validated through `ServiceOperationAdapter`.
- **Effect Classification**: `read-only`, `idempotent-write`, or `stateful-mutation`.
- **Safe Probe**: Non-live, non-destructive probe command (`rush <cmd> --help`).

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
| `review PATH` | Deterministic Python heuristics before review or after edits. | PR-Agent, local Graft with `--use-graft`; `--llm` can call a configured provider; repeat `--changed-file` for target-contained scope only. | `ok`/`warn`; read-only; no Git-diff inference. |
| `lint PATH` | Source linting. | Ruff, ESLint, Stylelint, ast-grep, Flake8-Bugbear, MegaLinter, Comby, Prisma-lint, Vale, CSpell, Alex, RedPen, No-Jargon, Markdown-Unfluff, Buf, wasm-tools, Git-Guard. | May `fail` on findings; read-only. |
| `format PATH --check` | Verify formatter conformance. | Ruff format, Prettier, Squoosh, Critical, Font-Spider, PyClean. | Check-only with `--check`; omit only when you intentionally allow formatting. |
| `test PATH` | Run applicable project tests. | pytest, Vitest, Newman. | `fail` on test failures; test code may have project-defined side effects. |
| `security PATH` | Dependency vulnerability, privacy SAST, container and env checks. | pip-audit, npm audit, OSV-Scanner, Semgrep, Trivy, Grype, Bearer, Horusec, Pa11y, OWASP ZAP, Deadfinder, A11yWatch, Dockle, Safe-Env, NCU. | Read-only normalization; scanner behavior depends on installed tool. |
| `typecheck PATH` | Static type checks. | mypy, TypeScript `tsc`. | Read-only; missing helper skips. |
| `dead PATH` | Find unused code and dependencies. | Vulture, Knip, FawltyDeps, Ts-prune. | Advisory/read-only. |
| `complexity PATH` | Complexity, bundle weight, binary footprint and memory evidence. | Radon, jscpd, Depcruise, Scaphandre, Readability, Memray, Statoscope, Bloaty. | Metrics/findings; read-only. |
| `slop PATH` | Deterministic code-noise and AI filler signals. | sloppylint, Markdown-Unfluff plus JS/TS fallback. | Advisory; no authorship inference. |
| `fix PATH` | Bounded Ruff remediation for selected Python targets. | Ruff. | `--dry-run --force` preserves Git state; apply requires `--allow-artifact-write`. |

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

## Benchmark execution

`rush benchmark run` persists a job request and starts a detached worker by default, so a long model load or provider call has no stdout pipe, process handle, or monitoring loop in the invoking client. It does not download a model or call a provider unless the corresponding explicit option is supplied. Use `--foreground` only for a short, directly observed run.

```powershell
rush benchmark run --scenario local-granite-278m-c0
rush benchmark run --scenario local-granite-278m-c0 --allow-model-download granite-278m-embedding --local-runtime-executable C:\path\to\onnxruntime_perf_test.exe
rush benchmark run --all --allow-model-download granite-278m-embedding --allow-model-download bge-small-en-v1.5 --allow-model-download phi-4-mini-instruct --allow-model-download qwen2.5-coder-7b-instruct --local-runtime-executable C:\path\to\onnxruntime_perf_test.exe --local-runtime-executable C:\path\to\llama-bench.exe
rush benchmark run --scenario local-granite-278m-c0 --foreground
rush benchmark status
```

Default result storage is `%LOCALAPPDATA%\Rush\benchmarks\run`; the default model cache is `%LOCALAPPDATA%\Rush\benchmark-model-cache`; job state and worker logs are `%LOCALAPPDATA%\Rush\benchmarks\jobs`. Repeat `--allow-model-download`, `--local-runtime-executable`, and `--allow-live-route` to cover multiple candidates, runtimes, and live routes in one evidence campaign. `status` only reads durable job and scenario-result JSON; it never attaches to a worker. Router benchmarks require their exact `--allow-live-route` and a configured gateway endpoint; 9Router CLI presence alone never passes. OmniRoute's continuity adapter is separate: it uses the fixed loopback API and never reads `RUSH_BENCHMARK_OMNIROUTE_URL` or an API-key variable.

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
| `fix PATH` | Formats and lints Ruff-selected Python targets. | `--dry-run`, `--force`, `--allow-artifact-write` | Dry run is non-mutating. Apply requires artifact-write permission and restores invocation-owned targets on covered failure paths. |
| `setup PATH` | Reports detected stacks and recommended engines. | `--non-interactive` (default true; no false CLI spelling) | Current CLI cannot enter installation branch; installer planned in P65-02 |
| `init PATH` | Generate tailored `rush.toml` for detected project stacks. | `--overwrite` | Writes `rush.toml` |
| `config check PATH` | Validate `rush.toml` schema and tool configuration keys. | none | none |
| `doctor PATH` | Audit environment health, toolchain integrity, and anti-shadowing. | none | none |
| `watch PATH` | Real-time file system watcher with debouncing. | `--suite`, `--tool`, `--debounce` | none |
| `scan --project ID_OR_PATH` | Plan (and, with `--full`, execute) a full-project scan across every catalog candidate. | `--full`, `--install`, Permissions | `--full` persists an immutable run manifest under `<root>/.rush/runs/`; `--install` applies the project's provision plan first |
| `ui [PATH ...]` | Launch the persistent interactive terminal UI (project map, scans/findings, memory, tokens, Git, artifacts); accepts one or more project paths to switch between, defaults to the current directory. | Permissions | none |
| `dashboard PATH` | Launch the persistent, authenticated, CSRF-hardened local web dashboard on 127.0.0.1, sharing the same project actions as `rush ui`. | `--port`, `--no-open`, `--json`, `--reconnect`, `--server-id`, Permissions | none |
| `trust PATH` | Authorize repository in local trust ledger to allow custom plugins. | `--revoke` | Updates `~/.rush/trusted_repositories.json` |
| `plugin list PATH` | List configured custom plugins in `rush.toml`. | none | none |
| `plugin run NAME PATH` | Execute custom plugin against target path. | `--json` | Executes declared command if trusted |

### `rush fix PATH`

Status: P64-01 implements bounded target restoration for this route; Phase 64 remains in progress. Run `rush fix PATH --dry-run --force` to inspect native Ruff-selected files with `check --show-files --no-cache`, then read-only `format --diff --no-cache`, `check --diff --no-cache`, and ordinary `check --no-cache`. The ordinary check catches unfixable lint findings that diff output can miss. A no-change run returns `ok`; proposed formatting or any lint finding returns `warn`; invalid Python, Ruff process/config errors, failed AST validation, or snapshot/restore failures return `error`; unavailable Ruff returns `skipped`.

Prerequisite: Ruff must be discoverable. Dry run does not snapshot or write target files. Apply requires `--allow-artifact-write`; `--force` only bypasses the dirty-tree guard. Before any write, apply snapshots bytes and modes for selected regular Python targets. It refuses missing, redirected, symlink, and non-regular targets; it preserves Ruff excludes. On process/config/AST/cancellation/unexpected-exception paths, it restores invocation-owned targets or reports a bounded, redacted restore failure. Unrelated staged, unstaged, and untracked files remain outside its write set.

Evidence: `tests/test_fix.py::test_dry_run_preserves_index_and_unrelated_files` and `test_fix_cli_and_direct_dry_run_preserve_same_dirty_fixture` exercised real Ruff 0.16.3. The latter uses direct `FixTool.run` and the in-process Click `rush fix` route against one dirty fixture. A real-Ruff apply test preserves excluded `.venv/vendor.py`. Registered MCP reaches `rush_fix`; its `allow_artifact_write: bool = False` parameter denies apply without a grant and applies with `True`. No external installed `rush` binary ran.

### `rush scan --project ID_OR_PATH`

Status: P65-04/P65-06/P65-08 (Phase 65, [project provisioning, scan, and agent workflow plan](phase-plans/phase-65-project-provisioning-scan-and-agent-workflow-plan.md)). Wraps `ScanTool`'s canonical `plan`/`run`/`status` operations over the shared `rush.workflows.suites` aggregation. `rush scan --project ID_OR_PATH` builds and previews an immutable plan covering every catalog candidate with a reasoned disposition (`applicable`, `excluded_by_user`, `not_applicable`, `requires_input`, ...); no execution occurs and no run manifest is written. `--full` additionally executes that plan and persists one immutable run manifest under `<project_root>/.rush/runs/<run_id>/`; the response merges the run's `aggregate` `ToolResult`, a `coverage` object (candidate/scheduled/executed/finding totals, matching the manifest's own denominator — an unavailable engine never silently shrinks it), and `expansion_links` (`manifest_path` and the paginated `status` cursor) alongside `run_id`. `--install` applies the project's `setup`/`provision.py` plan (P65-02) before scanning, and requires the same `--allow-*` grants as `setup --install`. `run` additionally requires `--allow-cache-write` and `--allow-artifact-write`; without `--full` those grants are not required.

`cancel`, `resume`, `rescan`, and `handoff` are registered `scan` subcommands (P65-06/P65-08), each taking `RUN_ID` as a positional argument and `--project ID_OR_PATH` (required):
- `rush scan handoff RUN_ID --project ID_OR_PATH --agent AGENT_ID [--finding FINDING_ID ...] [--max-tokens N] [--max-bytes N] --allow-cache-write --allow-artifact-write [--json]` prepares a bounded agent handoff packet of `RUN_ID`'s unresolved findings (every unresolved finding by default; repeat `--finding` to scope to specific ones). Requires `--allow-cache-write` and `--allow-artifact-write`.
- `rush scan rescan RUN_ID --project ID_OR_PATH [--allow-* ...] [--json]` re-executes `RUN_ID`'s own staged plan against current source and reports each baseline finding as `resolved`, `persisting`, `new`, or `unverified` (an engine missing from the current run never reads as silently "resolved").
- `rush scan cancel RUN_ID --project ID_OR_PATH [--json]` requests cooperative cancellation of an in-flight run.
- `rush scan resume RUN_ID --project ID_OR_PATH [--allow-* ...] [--json]` resumes a run interrupted before completion; a stale/changed source or config since the original plan is refused, never silently resumed against the wrong baseline.

Registered MCP reaches `rush_scan(request)` for `plan`/`run`/`status`/`rescan`, and `rush_scan_handoff(request)` for the handoff lifecycle (`prepare`/`dispatch`/`status`/`acknowledge`/`complete`) — both single-`dict` envelopes over the same `handle_request` contract (plan §6.1). `rush_scan` does not auto-compose `--full`'s convenience workflow — callers stage `plan`, execute `run` with the returned `plan_id`, and poll `status` with the returned `run_id` for coverage totals and the paginated candidate cursor.

### `rush install [--agents all|none] [--memory on|off] [--project PATH_OR_ID] [--create NAME [--parent DIR]] [--init-git] [--session-id ID] [--version V] [--json]`

Status: P65-10 (Phase 65 §3.1/§6.2). The one-command global install: downloads and checksum-verifies the current platform's release archive, installs a self-contained `rush` executable under a user-owned binary directory, and (independent of any project choice) discovers/connects every supported local agent client and activates Phase 63 user-scoped memory. `--agents none` skips agent connection entirely; `--memory off` still connects agents but withholds tool-observation consent. Omitting `--project` completes a successful global install with no active project — the current working directory is never auto-registered. `--project PATH_OR_ID` selects or registers an existing folder and applies its provision plan (P65-02); `--create NAME [--parent DIR] [--init-git]` creates and registers a new project folder instead. A checksum mismatch, failed extraction, or a new binary that fails to start all leave the previously installed executable untouched, and no agent config is written before the binary is verified to run. Re-running `rush install` on an existing installation upgrades/repairs/connects idempotently — it never duplicates an agent registration or memory scope. Not registered over MCP (installation is a one-time host bootstrap step, not a per-session tool call).

### `rush agent list|connect|doctor` (Phase 65 P65-05)

- `rush agent list [--json]` reports every supported client's (`claude-desktop`, `claude-code`, `cursor`, `windsurf`, `zed`, `codex`) exact discovered state without writing anything.
- `rush agent connect AGENT_ID --session ID [--project PATH] [--rush-binary PATH] [--consent] [--acknowledge] --allow-cache-write --allow-artifact-write [--json]` registers Rush into that agent's own config file (format-preserving, backed up first) and activates a Phase 63 memory scope for `(project-or-user, session, agent)`. `--consent` allows real tool-observation payloads to be recorded for that scope; without it, only the connection itself is registered. `--acknowledge` is required before the connection reports `connected: true` — writing the config file is necessary but not sufficient.
- `rush agent doctor [--session ID] [--project PATH] [--json]` re-probes every client's real on-disk config and the memory scope's current state, without writing anything.

Registered MCP reaches `rush_agent_connection(request)`, the single-`dict` envelope over `AgentConnectionTool.handle_request` (`src/rush/tools/agent_connection.py`).

## Advanced Autonomous Agent, Hygiene & Governance Commands (Phases 29–40)

| Command | Purpose | Key Flags & Arguments | Modification |
|---|---|---|---|
| `patch apply PATH` | Status: planned — P64-04 in [Phase 64](phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md). This command is not registered. | Accepted future options: `--dry-run`, `--circuit-breaker` | Current `patch` group exposes only `memory` and `test`; unsafe sandbox/cleanup prerequisites remain open (F05/F43) |
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

Flags vary by registered command. Generic catalog commands expose `--workspace`, `--all-workspaces`, `--no-cache`, `--staged`, `--changed` and `--since`; dedicated review/lint/test commands have different surfaces. Use that command's `--help`. The following historical proposed shared flags are not universally implemented:
- `--workspace`, `-w <NAME>`: Scope execution to a specific monorepo workspace package.
- `--all-workspaces`: Execute evaluation across all discovered monorepo packages in topological order.
- `--no-cache` exists on generic catalog commands; `--cache` is not registered.
- `--cache-dir` is not a shared CLI option; `[cache].dir` is configuration.
- `--clear-cache` is not a shared CLI option; inspect `rush cache --help`.
- `--staged`: Restrict analysis scope to git staged files.
- `--since <REF>`: Restrict analysis scope to files modified since the specified git revision.
- `--branch` is not a shared CLI option. Generic commands expose `--since REF`.

## Workflow commands

| Command | Current behavior |
|---|---|
| `commit-msg PATH [-m MESSAGE]` | Validates Conventional Commit message passed via `-m/--message` or read from file. commitlint reference test suite. Never rewrites history. |
| `ci` | Registered group exposes `ci init`; legacy `ci PATH` is not registered. Inspect help before generating workflow files. |
| `release` | Registered group exposes `release check` for version parity; legacy `release PATH` is not registered. Signed-envelope verification belongs to `attest --verify PATH`. |
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

### `rush memory ask|write|promote|list|recall|maintain` (Phase 61)
Query and write the unified `TypedArtifactStore` (`.rush/memory.db`) — the same 7-subject/4-tier-trust store `rush session`'s checkpoints and every other memory-subsystem writer now persist through.
* `ask`/`list`/`recall`: use positional `SUBJECT QUERY` and at least one `--session SOURCE`. Every returned row passes signature, staleness, and Trojan Source checks. Missing session permission returns `skipped` without content.
* `write`: requires `--allow-cache-write` and never accepts `trust_tier=STATED` directly.
* `promote`: requires `--allow-cache-write`; approved candidates persist as `STATED` with a checksum and promotion timestamp after the screen, schema, grounding, and corroboration checks.
* `maintain`: requires `--task promotion_sweep|staleness_sweep|skill_admission_check|expiry_sweep` and `--allow-cache-write`. Runs a bounded sweep in the selected repository; defaults to 500 rows via `--batch-size`.

### `rush memory delete --input FILE` (Phase 65 P65-07.3)
Batch-deletes memory artifacts through the plan §6.4 transaction/outbox algorithm. `--input FILE` is a JSON object `{"artifact_ids": [...], "expected_revisions": {"<id>": <int>, ...}, "scope": "<subject>", "apply": false}`:
* `artifact_ids`: 1–100 unique existing IDs; no path separators, `..`, or external file paths.
* `expected_revisions`: exact `{id: current_revision}` map for every listed ID — a stale revision for *any one* member refuses the entire batch atomically (`E_VERSION`), never a partial delete.
* `scope`: the memory subject every listed artifact must currently have; a member whose actual subject differs refuses the entire batch (`E_SCOPE`) — deletion never crosses subjects it wasn't declared for.
* `apply` (default `false`, preview): preview never writes and returns each affected ID's revision, dependent `memory_relations` reference count, and (for a Rush-owned handoff-packet artifact) its on-disk blob path. Apply requires `--allow-cache-write` for the database mutation — it replaces each row's stored bytes with a content-free tombstone version (never retaining deleted content) and removes the live row so retrieval/`expand` see it as gone immediately. A Rush-owned handoff blob is additionally unlinked only when `--allow-artifact-write` is also granted; otherwise it is left on disk and reported `cleanup_pending` in the response's `blob_cleanup` (idempotent to retry later — never claimed as atomically erased across the DB/filesystem boundary). External source files are never deleted by this operation. Deleted artifacts remain listed (as `deleted: true`, with no retained content) by `rush project artifacts` for provenance.

### `rush memory edit --input FILE` (Phase 65 P65-07 §6.4)
Edits one memory artifact's content under compare-and-swap. `--input FILE` is a JSON object `{"scope": "<subject>", "id": "<artifact_id>", "expected_version": <int>, "content": {...}, "apply": false}`:
* `scope`/`id`/`expected_version`: a stale `expected_version` (`E_VERSION`) or an `id` whose actual subject differs from `scope` (`E_SCOPE`) refuses the edit atomically — never a partial write.
* `apply` (default `false`, preview): preview never writes, returning the current revision and trust tier. Apply requires `--allow-cache-write`; it writes the new content through the same versioned `update_content` compare-and-swap path every store mutation uses (preserving the prior version's content as history) and, if the artifact was previously promoted (`trust_tier="STATED"`), resets its trust back to an unpromoted candidate (clearing its signature and promotion timestamp) — an edit is never itself a re-promotion.

### `rush memory archive --input FILE` (Phase 65 P65-07 §6.4)
Sets or clears an archived marker on one memory artifact — never deletes content or history. `--input FILE` is a JSON object `{"scope": "<subject>", "id": "<artifact_id>", "expected_version": <int>, "apply": false, "archived": true}`:
* `scope`/`id`/`expected_version`: same atomic cross-scope/stale-version refusal as `edit` above (`E_SCOPE`/`E_VERSION`).
* `apply` (default `false`, preview): preview never writes. Apply requires `--allow-cache-write`; the marker change is itself a versioned store mutation (its own audit row), so full content/history stays retrievable — only excluded from `rush memory ask|list|recall`'s normal results. `rush memory list SUBJECT QUERY --include-archived` opts back into archived rows for authorized inspection.
* `archived` (default `true`): set `false` with the row's current `expected_version` to reverse a prior archive — fully idempotent-reversible, unlike `delete`.

### `rush project snapshot [--project-id ID] [--session ID]` (Phase 65 P65-07.2)
One shared evidence view over a registered project: overview/readiness, a run/coverage/finding summary, a memory summary (counts by subject, deleted count, and the admin capabilities `write`/`promote`/`maintain`/`delete`), token totals (see below), a best-effort Git HEAD/dirty summary, and categorized artifact references (same shape `rush project artifacts` returns). Read-only; resolves the target project the same way `rush project show` does. Token totals separate four distinct numbers, never blending an estimate into a real count: `provider_reported` (real per-tool metrics from run manifests; `total_tokens` stays `null`/"unknown" — never `0` — when no manifest ever reported one), `tokenizer_counted` (real `cl100k_base` counts summed from persisted agent-handoff packets), `cache_hits` (real, opt-in-recorded memory retrieval/expansion/packing/handoff/embedding event costs), and `estimated_avoided` (the existing token-economy ledger's raw-vs-compressed savings estimate).

### `rush project artifacts [--project-id ID] [--session ID] [--category NAME]... [--limit N] [--offset N]` (Phase 65 P65-07.2/.3)
Categorized, provenance-carrying references to everything a project has produced — scan-run outputs (`scan_outputs`), agent handoff packets (`handoffs`), and memory artifacts including tombstoned/deleted ones (`memory`). A scan output's `category` is whatever the scan classified it as, passed through verbatim — a category this command has never seen before (a future profiling/export engine) is still returned, never silently dropped, so new output never goes invisible before a bespoke viewer exists for it. Never includes raw finding evidence, tool stdout, or memory content — reference metadata only (an `id`/`artifact_ref` a caller can separately `memory expand`), so a secret embedded in raw tool output or memory content can never surface through this listing. `--category` (repeatable) filters each of the three lists independently by exact match; `--limit`/`--offset` (default 100/0, max 1000) then slice each filtered list independently.

### `rush ship clean`
Previews registered, unchanged Rush-owned ordinary files under `.rush/runs/`; it does not scan or remove arbitrary `scratch/`, `tmp/`, cache, or user files. Registry entries in `.rush/cleanup.json` bind path, digest, length, producer, and file identity. Apply requires both flags below; missing, modified, redirected, or nonregular entries are refused.
* `--apply`: Request deletion after preview.
* `--allow-artifact-write`: Required with `--apply`; default invocation is preview-only.

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
Print one Rich summary of local compression estimates, then exit. The persistent, live equivalent is the Tokens section of `rush ui` / `rush dashboard` (same `TelemetryStore` summary, per-run/session/agent views); these are not measured provider bills or cache-hit rates.

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

### `rush db-drift`
Audit ORM models against SQL migrations to detect unmigrated schema drift.

### `rush simplify`
Decompose high-complexity functions into clean helper sub-functions.
* `--file, -f`: Target file path (required).
* `--max-complexity, -m`: Maximum allowed cognitive complexity score (default: 10).

### `rush strictify`
Synthesize runtime type guards for unvalidated function arguments.
* `--file, -f`: Target file path (required).

### `rush trace`
Scan codebase and specs to output requirement-to-test traceability matrix.

### `rush flight-recorder`
Record and replay agent JSON-RPC sessions.
* `--replay, -r`: Replay a specific session ID.

### `rush swarm-merge`
Execute 3-way AST merge conflict resolution across concurrent agent changes.
* `--base`: Path to base file (required).
* `--ours`: Path to ours file (required).
* `--theirs`: Path to theirs file (required).

### `rush simulate-ci`
Emulate local GitHub Actions CI workflow execution.
* `--workflow, -w`: GitHub Actions workflow file to emulate (default: ci.yml).

### `rush attest`
Generate in-toto Statement v1 / SLSA Provenance v1 unsigned draft for an artifact.
* `path` (<click.types.Path object at 0x107c62120>): Target path. Default: `"."`.
* `--artifact-path, -a` (<click.types.Path object at 0x107c62090>): Target artifact path to attest. Default: `null`.
* `--out, -o` (<click.types.Path object at 0x107c62c60>): Contained output path for in-toto provenance JSON. Default: `null`.
* `--builder-id` (STRING): Builder ID URI. Default: `"https://rush-cli.org/builder/v1"`.
* `--verify` (<click.types.Path object at 0x107c62e40>): Verify signed provenance envelope against policy. Default: `null`.
* `--trusted-root` (STRING): Trusted root public key for verification. Default: `"Sentinel.UNSET"`.
* `--allowed-signer` (STRING): Allowed signer ID for verification. Default: `"Sentinel.UNSET"`.
* `--json`: Emit canonical result JSON. Permission flags are listed by `rush attest --help`.

### `rush license-matrix`
Audit project dependencies across `pyproject.toml`, `package.json`, and `Cargo.toml` for copyleft and license risks.
* `path` (<click.types.Path object at 0x107c39760>): Target path. Default: `"."`.
* `--json`: Emit canonical result JSON. Permission flags are listed by `rush license-matrix --help`.

### `rush iam-audit`
Audit multi-cloud SDK (AWS boto3, GCP, Azure) and Terraform wildcard usage and synthesize least-privilege cloud IAM JSON policy.
* `path` (<click.types.Path object at 0x107c39ac0>): Target path. Default: `"."`.
* `--output, -o` (<click.types.Path object at 0x107c39400>): Contained output path for synthesized IAM policy JSON. Default: `null`.
* `--json`: Emit canonical result JSON. Permission flags are listed by `rush iam-audit --help`.

### `rush dead-asset`
Scan for unreferenced media, font, and static files in the repository (strictly read-only).
* `path` (<click.types.Path object at 0x107c46270>): Target path. Default: `"Sentinel.UNSET"`.
* `--report-path` (<click.types.Path object at 0x107c46600>): Optional explicit report path for import mode. Default: `null`.
* `--export-sarif` (<click.types.Path object at 0x107c46a20>): Optional destination path to export SARIF 2.1.0 JSON report. Default: `null`.
* `--export-html` (<click.types.Path object at 0x107c46ab0>): Optional destination path to export standalone HTML report artifact. Default: `null`.
* `--no-cache` (BOOL): Bypass and do not write to result cache. Default: `false`.
* `--staged` (BOOL): Scan only files staged in git index. Default: `false`.
* `--changed` (BOOL): Scan only modified uncommitted files. Default: `false`.
* `--since` (STRING): Scan files changed since git ref. Default: `null`.
* `--workspace, -w` (STRING): Scope execution to a specific monorepo workspace package. Default: `null`.
* `--all-workspaces` (BOOL): Execute tool across all discovered monorepo workspaces. Default: `false`.
* `--json`: Emit canonical result JSON. Permission flags are listed by `rush dead-asset --help`.

### `rush pr-synthesize`
Synthesize structured semantic pull request markdown card from Git diff and tool results.
* `path` (<click.types.Path object at 0x107c46a50>): Target path. Default: `"Sentinel.UNSET"`.
* `--report-path` (<click.types.Path object at 0x107c471a0>): Optional explicit report path for import mode. Default: `null`.
* `--export-sarif` (<click.types.Path object at 0x107c471d0>): Optional destination path to export SARIF 2.1.0 JSON report. Default: `null`.
* `--export-html` (<click.types.Path object at 0x107c47230>): Optional destination path to export standalone HTML report artifact. Default: `null`.
* `--no-cache` (BOOL): Bypass and do not write to result cache. Default: `false`.
* `--staged` (BOOL): Scan only files staged in git index. Default: `false`.
* `--changed` (BOOL): Scan only modified uncommitted files. Default: `false`.
* `--since` (STRING): Scan files changed since git ref. Default: `null`.
* `--workspace, -w` (STRING): Scope execution to a specific monorepo workspace package. Default: `null`.
* `--all-workspaces` (BOOL): Execute tool across all discovered monorepo workspaces. Default: `false`.
* `--json`: Emit canonical result JSON. Permission flags are listed by `rush pr-synthesize --help`.

### `rush prompt-eval`
Evaluate recorded golden coding prompt execution runs against deterministic acceptance criteria.
* `path` (<click.types.Path object at 0x107c3a300>): Target path. Default: `"Sentinel.UNSET"`.
* `--report-path` (<click.types.Path object at 0x107c3ae10>): Optional explicit report path for import mode. Default: `null`.
* `--export-sarif` (<click.types.Path object at 0x107c3ae40>): Optional destination path to export SARIF 2.1.0 JSON report. Default: `null`.
* `--export-html` (<click.types.Path object at 0x107c3aea0>): Optional destination path to export standalone HTML report artifact. Default: `null`.
* `--no-cache` (BOOL): Bypass and do not write to result cache. Default: `false`.
* `--staged` (BOOL): Scan only files staged in git index. Default: `false`.
* `--changed` (BOOL): Scan only modified uncommitted files. Default: `false`.
* `--since` (STRING): Scan files changed since git ref. Default: `null`.
* `--workspace, -w` (STRING): Scope execution to a specific monorepo workspace package. Default: `null`.
* `--all-workspaces` (BOOL): Execute tool across all discovered monorepo workspaces. Default: `false`.
* `--json`: Emit canonical result JSON. Permission flags are listed by `rush prompt-eval --help`.

### `rush error-catalog`
Extract Python, TypeScript, and Rust exceptions and generate RFC 7807 problem details and markdown catalog.
* `path` (<click.types.Path object at 0x107c45040>): Target path. Default: `"Sentinel.UNSET"`.
* `--report-path` (<click.types.Path object at 0x107c45b50>): Optional explicit report path for import mode. Default: `null`.
* `--export-sarif` (<click.types.Path object at 0x107c45b80>): Optional destination path to export SARIF 2.1.0 JSON report. Default: `null`.
* `--export-html` (<click.types.Path object at 0x107c45be0>): Optional destination path to export standalone HTML report artifact. Default: `null`.
* `--no-cache` (BOOL): Bypass and do not write to result cache. Default: `false`.
* `--staged` (BOOL): Scan only files staged in git index. Default: `false`.
* `--changed` (BOOL): Scan only modified uncommitted files. Default: `false`.
* `--since` (STRING): Scan files changed since git ref. Default: `null`.
* `--workspace, -w` (STRING): Scope execution to a specific monorepo workspace package. Default: `null`.
* `--all-workspaces` (BOOL): Execute tool across all discovered monorepo workspaces. Default: `false`.
* `--json`: Emit canonical result JSON. Permission flags are listed by `rush error-catalog --help`.

### `rush provenance-ai`
Analyze Git commit trailers for AI co-authorship, calculate 30/60/90-day line survival rates, and correlate defects.
* `path` (<click.types.Path object at 0x107c45c10>): Target path. Default: `"Sentinel.UNSET"`.
* `--report-path` (<click.types.Path object at 0x107c45e80>): Optional explicit report path for import mode. Default: `null`.
* `--export-sarif` (<click.types.Path object at 0x107c46390>): Optional destination path to export SARIF 2.1.0 JSON report. Default: `null`.
* `--export-html` (<click.types.Path object at 0x107c46570>): Optional destination path to export standalone HTML report artifact. Default: `null`.
* `--no-cache` (BOOL): Bypass and do not write to result cache. Default: `false`.
* `--staged` (BOOL): Scan only files staged in git index. Default: `false`.
* `--changed` (BOOL): Scan only modified uncommitted files. Default: `false`.
* `--since` (STRING): Scan files changed since git ref. Default: `null`.
* `--workspace, -w` (STRING): Scope execution to a specific monorepo workspace package. Default: `null`.
* `--all-workspaces` (BOOL): Execute tool across all discovered monorepo workspaces. Default: `false`.
* `--json`: Emit canonical result JSON. Permission flags are listed by `rush provenance-ai --help`.

### `rush mem-profile`
Scan for unclosed resource leaks and execute dynamic memory profiling probes.
* `path` (<click.types.Path object at 0x107c3aa80>): Target path. Default: `"Sentinel.UNSET"`.
* `--report-path` (<click.types.Path object at 0x107c3b590>): Optional explicit report path for import mode. Default: `null`.
* `--export-sarif` (<click.types.Path object at 0x107c3b5c0>): Optional destination path to export SARIF 2.1.0 JSON report. Default: `null`.
* `--export-html` (<click.types.Path object at 0x107c3b620>): Optional destination path to export standalone HTML report artifact. Default: `null`.
* `--no-cache` (BOOL): Bypass and do not write to result cache. Default: `false`.
* `--staged` (BOOL): Scan only files staged in git index. Default: `false`.
* `--changed` (BOOL): Scan only modified uncommitted files. Default: `false`.
* `--since` (STRING): Scan files changed since git ref. Default: `null`.
* `--workspace, -w` (STRING): Scope execution to a specific monorepo workspace package. Default: `null`.
* `--all-workspaces` (BOOL): Execute tool across all discovered monorepo workspaces. Default: `false`.
* `--json`: Emit canonical result JSON. Permission flags are listed by `rush mem-profile --help`.

### `rush cold-start`
Analyze import latency and cold-start overhead for modules and dependencies.
* `path` (<click.types.Path object at 0x107c3b200>): Target path. Default: `"Sentinel.UNSET"`.
* `--report-path` (<click.types.Path object at 0x107c3bd10>): Optional explicit report path for import mode. Default: `null`.
* `--export-sarif` (<click.types.Path object at 0x107c3bd40>): Optional destination path to export SARIF 2.1.0 JSON report. Default: `null`.
* `--export-html` (<click.types.Path object at 0x107c444a0>): Optional destination path to export standalone HTML report artifact. Default: `null`.
* `--no-cache` (BOOL): Bypass and do not write to result cache. Default: `false`.
* `--staged` (BOOL): Scan only files staged in git index. Default: `false`.
* `--changed` (BOOL): Scan only modified uncommitted files. Default: `false`.
* `--since` (STRING): Scan files changed since git ref. Default: `null`.
* `--workspace, -w` (STRING): Scope execution to a specific monorepo workspace package. Default: `null`.
* `--all-workspaces` (BOOL): Execute tool across all discovered monorepo workspaces. Default: `false`.
* `--json`: Emit canonical result JSON. Permission flags are listed by `rush cold-start --help`.

### `rush media-opt`
Audit, sanitize SVG files, and optimize raster media assets.
* `path` (<click.types.Path object at 0x107c3b980>): Target path. Default: `"Sentinel.UNSET"`.
* `--report-path` (<click.types.Path object at 0x107c44140>): Optional explicit report path for import mode. Default: `null`.
* `--export-sarif` (<click.types.Path object at 0x107c44500>): Optional destination path to export SARIF 2.1.0 JSON report. Default: `null`.
* `--export-html` (<click.types.Path object at 0x107c44560>): Optional destination path to export standalone HTML report artifact. Default: `null`.
* `--no-cache` (BOOL): Bypass and do not write to result cache. Default: `false`.
* `--staged` (BOOL): Scan only files staged in git index. Default: `false`.
* `--changed` (BOOL): Scan only modified uncommitted files. Default: `false`.
* `--since` (STRING): Scan files changed since git ref. Default: `null`.
* `--workspace, -w` (STRING): Scope execution to a specific monorepo workspace package. Default: `null`.
* `--all-workspaces` (BOOL): Execute tool across all discovered monorepo workspaces. Default: `false`.
* `--json`: Emit canonical result JSON. Permission flags are listed by `rush media-opt --help`.

### `rush offline-review`
Execute air-gapped local LLM review using Ollama or llama-cli discovered on PATH (skips if absent).
* `path` (<click.types.Path object at 0x107c44590>): Target path. Default: `"Sentinel.UNSET"`.
* `--report-path` (<click.types.Path object at 0x107c44c50>): Optional explicit report path for import mode. Default: `null`.
* `--export-sarif` (<click.types.Path object at 0x107c44c80>): Optional destination path to export SARIF 2.1.0 JSON report. Default: `null`.
* `--export-html` (<click.types.Path object at 0x107c44ce0>): Optional destination path to export standalone HTML report artifact. Default: `null`.
* `--no-cache` (BOOL): Bypass and do not write to result cache. Default: `false`.
* `--staged` (BOOL): Scan only files staged in git index. Default: `false`.
* `--changed` (BOOL): Scan only modified uncommitted files. Default: `false`.
* `--since` (STRING): Scan files changed since git ref. Default: `null`.
* `--workspace, -w` (STRING): Scope execution to a specific monorepo workspace package. Default: `null`.
* `--all-workspaces` (BOOL): Execute tool across all discovered monorepo workspaces. Default: `false`.
* `--json`: Emit canonical result JSON. Permission flags are listed by `rush offline-review --help`.

### `rush tui-diff`
Compute Git finding deltas and render Rich comparison tables between commits.
* `path` (<click.types.Path object at 0x107c448c0>): Target path. Default: `"Sentinel.UNSET"`.
* `--report-path` (<click.types.Path object at 0x107c453d0>): Optional explicit report path for import mode. Default: `null`.
* `--export-sarif` (<click.types.Path object at 0x107c45400>): Optional destination path to export SARIF 2.1.0 JSON report. Default: `null`.
* `--export-html` (<click.types.Path object at 0x107c45460>): Optional destination path to export standalone HTML report artifact. Default: `null`.
* `--no-cache` (BOOL): Bypass and do not write to result cache. Default: `false`.
* `--staged` (BOOL): Scan only files staged in git index. Default: `false`.
* `--changed` (BOOL): Scan only modified uncommitted files. Default: `false`.
* `--since` (STRING): Scan files changed since git ref. Default: `null`.
* `--workspace, -w` (STRING): Scope execution to a specific monorepo workspace package. Default: `null`.
* `--all-workspaces` (BOOL): Execute tool across all discovered monorepo workspaces. Default: `false`.
* `--json`: Emit canonical result JSON. Permission flags are listed by `rush tui-diff --help`.

### `rush benchmark check`
Compare performance metrics against `.rush/baselines.json` regression thresholds.
* `path` (<click.types.Path object at 0x1076d8230>): Target path. Default: `"."`.
* `--threshold` (FLOAT): Percentage threshold for regression. Default: `5`.
* `--record` (BOOL): Record current samples as baseline in .rush/baselines.json. Default: `false`.
* `--json`: Emit canonical result JSON. Permission flags are listed by `rush benchmark check --help`.



### Historical `rush toon-inspect` name
Not registered. TOON is an internal serialization component, not this CLI command.

### Historical `rush skeletonize` name
Not registered. Current outline entrypoint: `rush token outline FILE_PATH`.

### Historical `rush context-cache` name
Not registered. Current context commands are listed by `rush context --help`.

### Historical `rush ccr-retrieve` name
Not registered. Current retrieval uses `rush context retrieve CHUNK_HASH`; it does not expose a semantic `--query` option.

### Historical `rush context-mistakes` name
Not registered. Current entrypoint: `rush context mistakes`.

## Output File Write Safety & Containment (Phase 55)

All file writing operations triggered by CLI exporter flags (`--export-html`, `--export-sarif`, `--allow-artifact-write`) are constrained to physical repository boundaries via `rush.io.PhysicalRoot` and written with `rush.io.AtomicFile` fsync durability.

### rush trust & rush plugin (Phase 56)
- `rush trust plugin <name>`: Authorize a plugin closure in the user-owned trust ledger.
- `rush trust plugin <name> --revoke`: Revoke authorization for a plugin closure.
- `rush plugin run <name> <path>`: Execute an authorized plugin from its verified snapshot; outputs `ToolResultV1` JSON when `--json` flag is provided.

## Invocation Semantics and Exit Codes (Phase 57)

All CLI commands resolve through `rush.invocation`:
- `--no-cache`: Explicitly sets `cache_policy = "bypass"`, performing strictly 0 cache reads and 0 cache writes.
- Exit codes: Tool commands exit with 0 for `ok` or `skipped`, 1 for `warn`, and 2 for `error` or blocked actions. Admin commands preserve native integer exit codes.
- Output formatting: Terminal and JSON outputs are recursively sanitized before rendering.

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
### `rush attest`
Generate in-toto Statement v1 SLSA provenance unsigned draft for build artifacts.
- `--artifact-path PATH`: Explicit path to built distribution package (.whl, .tar.gz).
- `--out PATH`, `-o PATH`: Contained destination for attestation JSON draft; requires `--allow-artifact-write`.
- `--builder-id URI`: Builder identity URI (default: `https://rush-cli.org/builder/v1`).
- `--verify PATH`: Verify a signed envelope against `--trusted-root` and `--allowed-signer` policy.
