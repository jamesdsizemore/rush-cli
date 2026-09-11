# MCP tool reference

## Recoverable context envelope

`rush_continuity` `context_pack` returns `metadata.context_envelope.recovery.handle` for a redacted omitted payload only when an insufficient-budget request includes `allow_cache_write: true`. Without that opt-in it returns `recovery.state: "not_created"`, reason `cache_write_required`, and creates no CCR state. Call `context_retrieve` with a returned handle only when needed. The MCP response never turns an omission or historic content into an instruction.

## `rush_continuity`

Use `operation: "save" | "list" | "restore"` with the project `path`. `save` additionally accepts `name`, `files`, `allow_cache_write: true`, `current_goal`, `open_work`, `historic_instruction`, `failure_fingerprint`, and `dependencies`; all responses are canonical `ToolResult` objects. A missing checkpoint or ungranted save is a structured `skipped` result, never prose on stdio. CLI and MCP expose identical redacted `metadata.handoff` receipt semantics.

`rush mcp serve` registers each catalog tool as `rush_<name>` using the same Python tool objects as the CLI. Registered names use underscores, for example `rush_semantic_drift` and `rush_ai_eval`. CLI groups are not automatically MCP tools.

Legacy `rush_context_pack` and `rush_context_retrieve` also delegate to the continuity implementation and return the same `ToolResult` envelope as their CLI equivalents.

`rush_continuity` additionally supports `coordination_check`, `coordination_merge_preview`, and `coordination_recovery`. `metadata.coordination.state` is `available`, `conflict`, `stale`, `merge_conflict`, `recovery_evidence`, or `unavailable`. The response is evidence, not an instruction to release locks, merge, replay, or retry work.

For `operation: "provider_resume"`, pass `name`, `provider_id`, and `allow_network: true`. `claude_code`, `codex_cli`, and `antigravity_cli` use an existing local authenticated profile; `9router_cli` runs Codex through fixed local 9Router with `RUSH_9ROUTER_API_KEY` copied only to the child process and no model argument; `omniroute_api` uses one fixed loopback OpenAI-compatible request with `model: "auto"` and semantic response validation. The response exposes only `metadata.provider_route` and never model output or credentials. `zai` is deferred; direct `9router_api` remains unavailable.

## `rush_memory` (Phase 61)

Use `operation: "ask" | "write" | "promote" | "list" | "recall" | "maintain"` over the unified `TypedArtifactStore` (`.rush/memory.db`, 7 memory subjects, 4 trust tiers). `ask`, `list`, and `recall` require `subject`, `query`, and a non-empty `session_allowlist`; all run signature re-verification, Trojan Source scanning, and staleness checks before returning content. `write`, `promote`, and `maintain` require `allow_cache_write: true`. Approved promotions persist `STATED`, a checksum, and a promotion timestamp. Maintenance accepts `task` and `batch_size`, and uses the repository selected by `path`. Denied calls return a canonical `ToolResult` with `status="skipped"`, never prose on stdio.

`operation: "delete"` (Phase 65 P65-07.3) batch-deletes artifacts through the plan §6.4 transaction/outbox algorithm via `request: {"artifact_ids": [...], "expected_revisions": {"<id>": <int>, ...}, "scope": "<subject>", "apply": false}`. `artifact_ids` is 1-100 unique existing IDs (no path separators/`..`/external file paths); `expected_revisions` must map exactly those IDs to their current revisions -- a stale revision on any one member refuses the whole batch (`code: "E_VERSION"`); `scope` is the subject every listed artifact must currently have -- a mismatched member refuses the whole batch (`code: "E_SCOPE"`), never a partial delete. `apply` defaults `false` (preview, never writes; returns each affected ID's revision, dependent-relation reference count, and any Rush-owned blob path). Apply requires `allow_cache_write: true` for the database mutation, which replaces each row's stored bytes with a content-free tombstone version and removes the live row so `expand` immediately sees it as gone (`code: "E_NOT_VISIBLE"`, identical to "never existed"). A Rush-owned handoff-packet blob among the affected IDs is additionally unlinked only when `allow_artifact_write: true` is also granted; otherwise the response's `data.blob_cleanup` reports `"cleanup_pending"` for that ID and the file is left in place, never claimed as atomically erased. External source files are never deleted.

`operation: "edit"` (Phase 65 P65-07 §6.4) edits one artifact's content under compare-and-swap via `request: {"scope": "<subject>", "id": "<artifact_id>", "expected_version": <int>, "content": {...}, "apply": false}`. A stale `expected_version` (`code: "E_VERSION"`) or an `id` whose actual subject differs from `scope` (`code: "E_SCOPE"`) refuses atomically. `apply` defaults `false` (preview, never writes; returns the current revision and trust tier). Apply requires `allow_cache_write: true`; it writes through the same `update_content` compare-and-swap path every store mutation uses, preserving the prior version as history, and if the artifact's `trust_tier` was `"STATED"` (previously promoted), resets it to an unpromoted candidate (clears `signature`/`promoted_at`) -- an edit is never itself a re-promotion.

`operation: "archive"` (Phase 65 P65-07 §6.4) sets or clears an archived marker via `request: {"scope": "<subject>", "id": "<artifact_id>", "expected_version": <int>, "apply": false, "archived": true}` -- same `scope`/`expected_version` atomic refusal as `edit`. `apply` defaults `false` (preview, never writes). Apply requires `allow_cache_write: true`; the marker change is itself a versioned store mutation, so content/history stay fully retained -- only excluded from `ask`/`list`/`recall`'s normal results. Pass `include_archived: true` on `list` for authorized inspection. `archived` defaults `true`; call again with `archived: false` and the row's new current `expected_version` to reverse it. Never deletes external source files or artifact content.

## `rush_scan` (Phase 65)

Single-`dict` envelope over `ScanTool` (plan §6.1: `{"schema_version": 1, "operation": ..., ...}` in, `{"schema_version": 1, "operation": ..., "data": ..., "error": ...}` out), matching `rush_project`'s wiring. Supports `operation: "plan" | "run" | "status" | "rescan"` (P65-06 landed `rescan`); `cancel`/`resume` are P65-08's CLI-only workflow functions (`rush scan cancel`/`rush scan resume`) and are rejected here as an unknown operation — no MCP equivalent exists yet. `plan(project, full=true, exclude=[], targets={}, severity="warn", concurrency=2, timeout_seconds=300)` stages an immutable plan covering every catalog candidate and returns its `plan_id` and full candidate list with dispositions; it does not execute anything. `run(project, plan_id, install=false, allow_cache_write, allow_artifact_write, ...)` requires `allow_cache_write` and `allow_artifact_write`, executes every `applicable` candidate exactly once, and returns `run_id`, `run_state`, the scheduled candidates, and the aggregate `ToolResult`; a failed post-install probe or missing input never silently shrinks the reported denominator. `status(project, run_id, after_sequence=0, limit=50, cursor=null)` returns the run's `totals` (coverage: candidate/scheduled/executed/finding counts) and a paginated, HMAC-signed cursor over the scheduled candidates. `rescan(project, run_id)` re-executes `run_id`'s own staged plan against current source (`rush.workflows.project_run.rescan_project_run`) and returns the new run plus a `comparison` of `resolved`/`persisting`/`new`/`unverified` finding IDs against the baseline — an engine missing from the current run marks its prior findings `unverified`, never `resolved`. The CLI's `rush scan --full` composes `plan` + `run` + `status` into one call for convenience; this MCP tool does not auto-compose them — call each operation explicitly.

## `rush_scan_handoff` (Phase 65 P65-06)

Single-`dict` envelope over `ScanHandoffTool` (plan §6.1), matching `rush_scan`/`rush_project`'s wiring. Supports `operation: "prepare" | "dispatch" | "status" | "acknowledge" | "complete"`. `prepare(project, run_id, agent_id, finding_ids=[], max_tokens=2048, max_bytes=8192)` builds a bounded handoff packet (every unresolved finding by default, or exactly the given `finding_ids`) and returns `handoff_id`/`session_capability`/`state: "prepared"`; a source that changed since `run_id` refuses the request rather than handing off a stale reference. `dispatch`/`acknowledge`/`complete` advance the same handoff through `delivered` → `acknowledged` → `agent_reported_complete` using the returned `session_capability`/`delivery_nonce` — an agent's own claim of success is recorded as `agent_reported_complete`, never auto-promoted to `resolved`/`verified` (only a real rescan does that). `status(project, handoff_id)` returns the current lifecycle state without ever exposing `session_capability` or `delivery_nonce`. A response's `data.state` always reflects the real, non-fabricated lifecycle state so the next required operation is unambiguous.

## `rush_agent_connection` (Phase 65 P65-05)

Single-`dict` envelope over `AgentConnectionTool` (`src/rush/tools/agent_connection.py`), the MCP-exposed equivalent of `rush agent list/connect/doctor`. Discovers `claude-desktop`, `claude-code`, `cursor`, `windsurf`, `zed`, and `codex`, registers Rush into a selected client's own config file (format-preserving, backed up first, never touching an unrelated setting), and activates a Phase 63 memory scope for `(project-or-user, session, agent)`. A config failure on one client is reported against that client alone and never marks a different client as failed or connected. `consent` gates whether real tool-observation payloads are ever recorded for that scope; `connected: true` is only reported after explicit acknowledgment, never from a config write alone.

## `rush_project` (Phase 65)

Single-`dict` envelope over `ProjectTool` (plan §6.1: `{"schema_version": 1, "operation": ..., ...}` in, `{"schema_version": 1, "operation": ..., "data": ..., "error": ...}` out), matching `rush_scan`'s wiring. `operation: "snapshot"` (P65-07.2, request: `project`, `session_id`) returns one shared evidence view: overview/readiness, a run/coverage/finding summary, a memory summary (counts by subject, deleted count, admin capabilities `write`/`promote`/`maintain`/`delete`), token totals, a best-effort Git summary, and categorized artifact references. Token totals separate four distinct numbers, never blending an estimate into a real count: `provider_reported` (`total_tokens` stays `null` — "unknown", never `0` — when no run manifest ever reported real per-tool usage), `tokenizer_counted` (real `cl100k_base` counts summed from persisted agent-handoff packets), `cache_hits` (real, opt-in-recorded memory-reuse event costs), and `estimated_avoided` (the existing token-economy ledger's raw-vs-compressed savings estimate). `operation: "artifacts"` (P65-07.2/.3, request: `project`, `session_id`, `categories` (list, optional exact-match filter), `limit` (1-1000, default 100), `offset` (default 0)) returns the same categorized `scan_outputs`/`handoffs`/`memory` reference lists `snapshot` embeds, each list independently filtered then sliced. A scan output's `category` is passed through verbatim — an unrecognized future category is still returned, never dropped. Never includes raw finding evidence, tool stdout, or memory content; a deleted memory artifact still appears (`deleted: true`, no retained content) for provenance. Both operations are read-only and require no permission grant.

## Common result

Catalog tools return canonical ToolResult data documented in [Result reference](reference/result-reference.md); some custom MCP operations return strings or specialized dictionaries. A missing optional engine is a structured `skipped` result, not an installation request.

## Inputs

Most tools accept:

```json
{
  "path": "/absolute/path/to/project",
  "allow_network": false,
  "allow_download": false,
  "allow_cache_write": false,
  "allow_build": false,
  "allow_slow": false,
  "allow_artifact_write": false,
  "allow_browser": false
}
```

Special callable options include:

- `rush_review`: `path`, `use_llm=false`, `use_graft=false`, `changed_files=null`.
- `rush_format`: required `path`, `check=false`.
- `rush_commit_msg`: `path`, `message=""`.
- `rush_sbom`: required `path`, `output_path=null`, `overwrite=false`, and the seven permission flags above, each `false`.
- `rush_snapshot`: required `path` and opaque `options`; `accept=false`, `report_path=null`, and the seven permission flags above, each `false`.
- `rush_ai_eval`: required `path` and the seven permission flags above, each `false`.

## Complete tool names

Current runtime registration: 74 names (`collect_runtime_contracts`). Exact parameter/type/default schemas are in the [generated MCP reference](reference/mcp-tool-reference.md).

```text
rush_actions, rush_ai_eval, rush_api_diff, rush_arch_guard, rush_attest, rush_attest_generate, rush_benchmark, rush_blast_radius, rush_ci, rush_codeql, rush_cold_start, rush_commit_msg, rush_complexity, rush_containerfile, rush_context_gain_stats, rush_context_mistakes_check, rush_context_pack, rush_context_retrieve, rush_continuity, rush_contract, rush_coverage, rush_db_drift, rush_dead, rush_dead_asset, rush_doctor, rush_e2e, rush_error_catalog, rush_fix, rush_flaky, rush_format, rush_fuzz, rush_hallu_guard, rush_iac, rush_iam_audit, rush_license_matrix, rush_lint, rush_load, rush_markdown, rush_media_opt, rush_mem_profile, rush_memory, rush_mesh_acquire_lock, rush_mesh_release_lock, rush_mutation, rush_offline_review, rush_pbt, rush_pr_synthesize, rush_prompt_eval, rush_provenance_ai, rush_release, rush_review, rush_sbom, rush_secrets, rush_security, rush_semantic_drift, rush_ship_clean, rush_ship_env, rush_ship_gate, rush_simplify, rush_slop, rush_snapshot, rush_sql, rush_strictify, rush_swarm_merge, rush_tdd, rush_templates, rush_test, rush_test_heal, rush_token_outline, rush_trace, rush_tui_diff, rush_typecheck, rush_visual, rush_yaml
```

## Protocol guarantees


- stdio only; no HTTP/SSE listener.
- stdout is JSON-RPC only.
- NDJSON diagnostics go to stderr.
- engine subprocess stdin is detached (`stdin=DEVNULL`) so it cannot consume MCP frames.
- the client-provided process environment must preserve required Windows/runtime variables.

See [MCP client setup](integrations/mcp-client-setup.md) and [MCP development](developer/mcp-development.md).

## Phase 41–43 FastMCP Tool Additions

* **Historical `rush_session_save` name:** not registered; use `rush_continuity` with `operation="save"` and explicit `allow_cache_write=true`.
* **`rush_ship_clean(path=".", apply=false, allow_artifact_write=false)`**: Previews only unchanged Rush-owned ordinary files registered under `.rush/runs/` in `.rush/cleanup.json`. Apply requires both `apply=true` and `allow_artifact_write=true`; absent, modified, redirected, nonregular, and unregistered paths are preserved or reported as refused. Result reports preview, removed, refused, byte, registry-update, and optional error fields.
* **`rush_ship_env()`**: Audit codebase environment variable usage against `.env.example`.
* **`rush_ship_gate()`**: Run 7-vector pre-flight release readiness cockpit.
* **`rush_token_outline(path, focus_symbol="")`**: Generate a code outline; current custom output can leak secrets (F07), pending P64-05.
* **`rush_context_retrieve(chunk_hash, path=".")`**: Retrieve uncompressed content from CCR chunk store by hash.
* **`rush_hallu_guard(path="")`**: Audit code imports against installed packages and stdlib.
* **`rush_context_mistakes_check()`**: Check git revert history for past mistakes and anti-patterns.

* **`rush_context_pack(path, symbol="", budget=4000, allow_cache_write=false)`**: Pack graph-pruned context outline under a strict token budget.

* **`rush_context_gain_stats()`**: Return local token/compression estimates; no measured provider billing or cache-hit guarantee.

* **`rush_blast_radius(path, depth=5)`**: Calculate downstream transitive blast radius for a changed file.
* **`rush_arch_guard()`**: Validate codebase against clean architecture layer boundaries.

* **`rush_test_heal(target, runs=5)`**: Current implementation repeats identical pytest runs and makes a comment-only patch (F12); verified diagnosis/repair remains planned in P64-12.
* **`rush_api_diff(base="main")`**: Detect breaking public API contract changes against base Git ref.

* **`rush_db_drift()`**: Audit ORM models against migrations to detect schema drift.
* **`rush_simplify(file, max_complexity=10)`**: Decompose high-complexity functions into modular helpers.
* **`rush_strictify(file)`**: Synthesize runtime type guards for unvalidated parameters.

* **`rush_trace()`**: Scan codebase and specs to output requirement traceability matrix.
* **`rush_mesh_acquire_lock(path, agent_id, capability=None)`**: Acquire non-blocking multi-agent file lock.
* **`rush_mesh_release_lock(path, agent_id, capability=None)`**: Release multi-agent file lock.
* **`rush_swarm_merge(base_code, ours_code, theirs_code)`**: Execute 3-way AST merge conflict resolution.

## Phase 50a FastMCP Tool Additions

* **`rush_attest(path, artifact_path="", output_path="", verify="", builder_id="https://rush-cli.org/builder/v1", trusted_roots=[], allowed_signers=[], allowed_builders=[], allow_network=false, allow_download=false, allow_cache_write=false, allow_build=false, allow_slow=false, allow_artifact_write=false, allow_browser=false)`**: Generate in-toto Statement v1 / SLSA Provenance v1 unsigned draft for an artifact.
* **`rush_attest_generate(path, artifact_path="", output_path="", verify="", builder_id="https://rush-cli.org/builder/v1", trusted_roots=[], allowed_signers=[], allowed_builders=[], allow_network=false, allow_download=false, allow_cache_write=false, allow_build=false, allow_slow=false, allow_artifact_write=false, allow_browser=false)`**: *(Deprecated compatibility alias)* Registered with the same schema as `rush_attest` and delegates directly to it.
* **`rush_license_matrix(path, package_licenses=None, allowed_licenses=["MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "Unlicense", "CC0-1.0", "0BSD", "PSF-2.0", "Python-2.0", "Zlib"], allow_network=false, allow_download=false, allow_cache_write=false, allow_build=false, allow_slow=false, allow_artifact_write=false, allow_browser=false)`**: Audit dependency licenses across manifests.
* **`rush_iam_audit(path, output_policy_file="", allow_network=false, allow_download=false, allow_cache_write=false, allow_build=false, allow_slow=false, allow_artifact_write=false, allow_browser=false)`**: Synthesize least-privilege AWS IAM JSON policy from static SDK usage.
* **`rush_dead_asset(path, export_manifest=None, allow_artifact_write=false)`**: Scan repository for unreferenced media, font, and static assets.
* **`rush_pr_synthesize(path, base_ref="main", export_path=None, allow_artifact_write=false)`**: Synthesize structured pull request card from Git diff and tool results.
* **`rush_prompt_eval(path, options, allow_network=false, allow_download=false, allow_cache_write=false, allow_build=false, allow_slow=false, allow_artifact_write=false, allow_browser=false)`**: Evaluate recorded golden prompt runs. `options` is required and opaque in the registered MCP schema; inspect the generated schema rather than assuming inner fields.
* **`rush_error_catalog(path, export_path=None, allow_artifact_write=false)`**: Extract errors and generate RFC 7807 problem details.
* **`rush_provenance_ai(path, allow_network=false, allow_download=false, allow_cache_write=false, allow_build=false, allow_slow=false, allow_artifact_write=false, allow_browser=false)`**: Audit Git commit trailers, calculate 30/60/90-day line survival rates, and correlate defects.
* **`rush_mem_profile(path, options, allow_network=false, allow_download=false, allow_cache_write=false, allow_build=false, allow_slow=false, allow_artifact_write=false, allow_browser=false)`**: Scan unclosed resources and run dynamic memory probes. `options` is required and opaque in the registered MCP schema.
* **`rush_cold_start(path, options, allow_network=false, allow_download=false, allow_cache_write=false, allow_build=false, allow_slow=false, allow_artifact_write=false, allow_browser=false)`**: Analyze module import cold-start latency. `options` is required and opaque in the registered MCP schema.
* **`rush_media_opt(path, options, allow_network=false, allow_download=false, allow_cache_write=false, allow_build=false, allow_slow=false, allow_artifact_write=false, allow_browser=false)`**: Audit, sanitize SVGs, and optimize raster media assets. `options` is required and opaque in the registered MCP schema.
* **`rush_offline_review(path, options, model="codellama", runner_path=None, allow_network=false, allow_download=false, allow_cache_write=false, allow_build=false, allow_slow=false, allow_artifact_write=false, allow_browser=false)`**: Air-gapped local LLM review using Ollama or llama-cli discovered on PATH. `options` is required and opaque in the registered MCP schema.
* **`rush_tui_diff(path, options, allow_network=false, allow_download=false, allow_cache_write=false, allow_build=false, allow_slow=false, allow_artifact_write=false, allow_browser=false)`**: Compute Git finding deltas across commits. `options` is required and opaque in the registered MCP schema.
* **`rush_benchmark(path, options, allow_network=false, allow_download=false, allow_cache_write=false, allow_build=false, allow_slow=false, allow_artifact_write=false, allow_browser=false)`**: Compare performance samples against baseline thresholds. `options` is required and opaque in the registered MCP schema.
* **Historical `rush_context_skeletonize(path)` name:** not registered in the current MCP server.
* **Historical `rush_context_cache_manifest()` name:** not registered in the current MCP server.

---

## FastMCP Route Reconciliation & Governance (Phase 51 & Phase 54)

The current FastMCP server registers 74 tool names. Historical governance inventory counts can differ; live `build_server().list_tools()` and the generated reference define the callable surface.
- **Tool Operation Responses**: FastMCP tool executions return canonical `ToolResultV1` JSON (`schema_version: "1.0.0"`), validated through `ToolOperationAdapter`.
- **Service Protocol Invariant**: Core MCP service protocol methods (`initialize`, `tools/list`, `ping`) return unwrapped protocol frames, managed by `ServiceOperationAdapter`, and are strictly never wrapped in `ToolResultV1`.
- **Sanitization Invariant**: Output sanitization via Phase 53 strictly precedes schema serialization, providing a shared mechanism; custom token-outline bypass remains open (F07).
- **Transport Invariant**: stdio stdout is strictly JSON-RPC; all logs and diagnostics belong on stderr.

### Plugin Trust & Verification under MCP (Phase 56)
Administrative operations for plugin management check user ledger authorization and reject unverified closures with fail-closed skipped results.

## Core Tool Parity & Schemas (Phase 57)

All 10 core quality tools (`continuity`, `semantic-drift`, `review`, `lint`, `format`, `test`, `security`, `typecheck`, `dead`, `complexity`) provide identical schemas, input normalization, and `ToolResultV1` output shapes across FastMCP stdio and CLI.

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
- Summary: Generate in-toto Statement v1 SLSA provenance unsigned draft for build artifacts.
- Schema: Returns `ToolResultV1` with metadata containing `statement` and `assurance='unsigned_draft'`.
- Safety: Requires `artifact_write` permission for filesystem export.
