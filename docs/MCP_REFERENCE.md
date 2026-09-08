# MCP tool reference

## Recoverable context envelope

`rush_continuity` `context_pack` returns `metadata.context_envelope.recovery.handle` for a redacted omitted payload only when an insufficient-budget request includes `allow_cache_write: true`. Without that opt-in it returns `recovery.state: "not_created"`, reason `cache_write_required`, and creates no CCR state. Call `context_retrieve` with a returned handle only when needed. The MCP response never turns an omission or historic content into an instruction.

## `rush_continuity`

Use `operation: "save" | "list" | "restore"` with the project `path`. `save` additionally accepts `name`, `files`, `allow_cache_write: true`, `current_goal`, `open_work`, `historic_instruction`, `failure_fingerprint`, and `dependencies`; all responses are canonical `ToolResult` objects. A missing checkpoint or ungranted save is a structured `skipped` result, never prose on stdio. CLI and MCP expose identical redacted `metadata.handoff` receipt semantics.

`rush mcp serve` registers each catalog tool as `rush_<name>` using the same Python tool objects as the CLI. Tool names include hyphens where the command does, for example `rush_semantic-drift` and `rush_ai-eval`.

Legacy `rush_context_pack` and `rush_context_retrieve` also delegate to the continuity implementation and return the same `ToolResult` envelope as their CLI equivalents.

`rush_continuity` additionally supports `coordination_check`, `coordination_merge_preview`, and `coordination_recovery`. `metadata.coordination.state` is `available`, `conflict`, `stale`, `merge_conflict`, `recovery_evidence`, or `unavailable`. The response is evidence, not an instruction to release locks, merge, replay, or retry work.

For `operation: "provider_resume"`, pass `name`, `provider_id`, and `allow_network: true`. `claude_code`, `codex_cli`, and `antigravity_cli` use an existing local authenticated profile; `9router_cli` runs Codex through fixed local 9Router with `RUSH_9ROUTER_API_KEY` copied only to the child process and no model argument; `omniroute_api` uses one fixed loopback OpenAI-compatible request with `model: "auto"` and semantic response validation. The response exposes only `metadata.provider_route` and never model output or credentials. `zai` is deferred; direct `9router_api` remains unavailable.

## `rush_memory` (Phase 61)

Use `operation: "ask" | "write" | "promote" | "list" | "recall" | "maintain"` over the unified `TypedArtifactStore` (`.rush/memory.db`, 7 memory subjects, 4-tier trust taxonomy). `write` never accepts `trust_tier: "STATED"` directly — only `promote` (via `evaluate_promotion()`'s composed screen) can move a record to `STATED`. `recall` applies signature re-verification, Trojan Source scanning, and staleness checking to every returned row before it re-enters an LLM context, and requires a non-empty session allowlist (fails closed on empty input). `search` (used internally by `ask`) skips that per-row defense cost and never returns `content` directly. `maintain` is reserved (`status="skipped"`, `reason="not implemented until Phase 62"`). All responses are canonical `ToolResult` objects, matching `rush_continuity`'s shape — a denied or absent case is `status="skipped"`, never prose on stdio.

## Common result

Every tool returns canonical ToolResult data documented in [Result reference](reference/result-reference.md). A missing optional engine is a structured `skipped` result, not an installation request.

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

- `rush_review`: `path`, `use_llm=false`, `use_graft=false`, `changed_files=[]`.
- `rush_format`: `path`, check-mode options.
- `rush_commit-msg`: `path`, `message=""`.
- `rush_sbom`: `path`, `output=null`, `overwrite=false`.
- `rush_snapshot`: `path`, `accept=false`, `report_path=null`.
- `rush_ai-eval`: `path`, standard permissions.

## Complete tool names

```text
rush_review, rush_lint, rush_format, rush_test, rush_security,
rush_typecheck, rush_dead, rush_complexity, rush_slop,
rush_markdown, rush_actions, rush_yaml, rush_sql, rush_templates,
rush_containerfile, rush_iac, rush_secrets, rush_sbom,
rush_coverage, rush_pbt, rush_flaky, rush_contract, rush_snapshot,
rush_visual, rush_mutation, rush_e2e, rush_fuzz, rush_load,
rush_semantic-drift, rush_commit-msg, rush_ci, rush_release,
rush_codeql, rush_ai-eval, rush_tdd, rush_fix, rush_doctor,
rush_guard, rush_token, rush_sync, rush_hygiene, rush_codegraph,
rush_bundle, rush_hotspots, rush_governance, rush_hook, rush_score,
rush_error_catalog, rush_license_matrix, rush_iam_audit
```

## Protocol guarantees


- stdio only; no HTTP/SSE listener.
- stdout is JSON-RPC only.
- NDJSON diagnostics go to stderr.
- engine subprocess stdin is detached (`stdin=DEVNULL`) so it cannot consume MCP frames.
- the client-provided process environment must preserve required Windows/runtime variables.

See [MCP client setup](integrations/mcp-client-setup.md) and [MCP development](developer/mcp-development.md).

## Phase 41–43 FastMCP Tool Additions

* **`rush_session_save(name, files)`**: Save developer context snapshot to `.rush/sessions/`.
* **`rush_ship_clean(dry_run=False)`**: Clean scratch directories and build caches before release.
* **`rush_ship_env()`**: Audit codebase environment variable usage against `.env.example`.
* **`rush_ship_gate()`**: Run 7-vector pre-flight release readiness cockpit.
* **`rush_token_outline(path, focus_symbol="")`**: Generate token-efficient AST skeleton outline of a code file.
* **`rush_context_retrieve(chunk_hash)`**: Retrieve uncompressed content from CCR chunk store by hash.
* **`rush_hallu_guard(path="")`**: Audit code imports against installed packages and stdlib.
* **`rush_context_mistakes_check()`**: Check git revert history for past mistakes and anti-patterns.

* **`rush_context_pack(path, symbol="", budget=4000)`**: Pack graph-pruned context outline under a strict token budget.

* **`rush_context_gain_stats()`**: Return real-time token economy savings, compression ratios, and dollar metrics as JSON.

* **`rush_blast_radius(path, depth=5)`**: Calculate downstream transitive blast radius for a changed file.
* **`rush_arch_guard()`**: Validate codebase against clean architecture layer boundaries.

* **`rush_test_heal(target, runs=5)`**: Diagnose flaky test race conditions in isolated sandbox and propose fixes.
* **`rush_api_diff(base="main")`**: Detect breaking public API contract changes against base Git ref.

* **`rush_db_drift()`**: Audit ORM models against migrations to detect schema drift.
* **`rush_simplify(file, max_complexity=10)`**: Decompose high-complexity functions into modular helpers.
* **`rush_strictify(file)`**: Synthesize runtime type guards for unvalidated parameters.

* **`rush_trace()`**: Scan codebase and specs to output requirement traceability matrix.
* **`rush_mesh_acquire_lock(path, agent_id)`**: Acquire non-blocking multi-agent file lock.
* **`rush_mesh_release_lock(path, agent_id)`**: Release multi-agent file lock.
* **`rush_swarm_merge(base_code, ours_code, theirs_code)`**: Execute 3-way AST merge conflict resolution.

## Phase 50a FastMCP Tool Additions

* **`rush_attest(path, target_artifact, export_path=None)`**: Generate in-toto Statement v1 / SLSA Provenance v1 unsigned draft for an artifact.
* **`rush_attest_generate(artifact_path="")`**: *(Deprecated compatibility alias)* Delegates directly to `rush_attest`.
* **`rush_license_matrix(path, project_license="", allowed_licenses=None, export_path=None)`**: Audit dependency licenses across manifests.
* **`rush_iam_audit(path, export_path=None)`**: Synthesize least-privilege AWS IAM JSON policy from static SDK usage.
* **`rush_dead_asset(path, export_manifest=None)`**: Scan repository for unreferenced media, font, and static assets (strictly read-only).
* **`rush_pr_synthesize(path, base_ref="main", export_path=None)`**: Synthesize structured pull request card from Git diff and tool results.
* **`rush_prompt_eval(path, pass_rate_threshold=1.0, max_tokens=None, max_cost=None)`**: Evaluate recorded golden prompt runs.
* **`rush_error_catalog(path, export_path=None)`**: Extract errors and generate RFC 7807 problem details.
* **`rush_provenance_ai(path, max_commits=500)`**: Audit Git commit trailers, calculate 30/60/90-day line survival rates, and correlate defects.
* **`rush_mem_profile(path, mode="static", probe_cmd=None)`**: Scan unclosed resources and run dynamic memory probes.
* **`rush_cold_start(path, mode="static", entry_point=None, threshold_ms=50.0)`**: Analyze module import cold-start latency.
* **`rush_media_opt(path, operation="audit")`**: Audit, sanitize SVGs, and optimize raster media assets.
* **`rush_offline_review(path, runner_path=None, model=None, model_path=None)`**: Air-gapped local LLM review using Ollama or llama-cli discovered on PATH.
* **`rush_tui_diff(path, base_ref=None, target_ref="HEAD")`**: Compute Git finding deltas across commits.
* **`rush_benchmark(path, metric=None, value=None, threshold_pct=10.0, record=False)`**: Compare performance samples against baseline thresholds.
* **`rush_context_skeletonize(path)`**: Extract compressed AST outline skeletons for a target source file.
* **`rush_context_cache_manifest()`**: Retrieve Merkle DAG content-addressable cache block manifests.

---

## FastMCP Route Reconciliation & Governance (Phase 51 & Phase 54)

All 73 FastMCP registered tools and 17 service operations are cataloged in `governance/public-operations.toml` and bound to runtime adapters in `rush.contracts.operations`:
- **Tool Operation Responses**: FastMCP tool executions return canonical `ToolResultV1` JSON (`schema_version: "1.0.0"`), validated through `ToolOperationAdapter`.
- **Service Protocol Invariant**: Core MCP service protocol methods (`initialize`, `tools/list`, `ping`) return unwrapped protocol frames, managed by `ServiceOperationAdapter`, and are strictly never wrapped in `ToolResultV1`.
- **Sanitization Invariant**: Output sanitization via Phase 53 strictly precedes schema serialization, guaranteeing that MCP responses never leak secrets to agent clients.
- **Transport Invariant**: stdio stdout is strictly JSON-RPC; all logs and diagnostics belong on stderr.

### Plugin Trust & Verification under MCP (Phase 56)
Administrative operations for plugin management check user ledger authorization and reject unverified closures with fail-closed skipped results.

## Core Tool Parity & Schemas (Phase 57)

All 10 core quality tools (`continuity`, `semantic-drift`, `review`, `lint`, `format`, `test`, `security`, `typecheck`, `dead`, `complexity`) provide identical schemas, input normalization, and `ToolResultV1` output shapes across FastMCP stdio and CLI.

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

4. **Contained Patch Verification & Atomic Rollback (`rush.patch`)**:
   - `PatchContract` cryptographically binds base commit, tree digest, patch content hash, sandbox directory under `rush.io.PhysicalRoot`, command plans, and policy review classes (`standard`, `policy-changing`, `privileged`).
   - Workspaces must be clean before sandboxing or patch application; dirty checkouts fail closed with `DirtyWorkspaceError`.
   - `PatchVerifier` requires at least one passing executed test command; zero executed commands return `outcome='unavailable'` and `False` (zero commands never verify).
   - Failed promotion or verification triggers automatic atomic rollback (`git reset --hard`, `git clean -fd`) restoring the working directory to its exact pre-patch commit and state.

5. **Runtime Output Boundary Adapter Enforcement (`rush.contracts.operations`)**:
   - 100% of public operations declared in `governance/public-operations.toml` enforce their target adapters (`ToolOperationAdapter`, `AdminOperationAdapter`, `ServiceOperationAdapter`) at runtime boundaries while preserving native JSON-RPC service protocol messages.
### `tool.attest`
- Summary: Generate in-toto Statement v1 SLSA provenance unsigned draft for build artifacts.
- Schema: Returns `ToolResultV1` with metadata containing `statement` and `assurance='unsigned_draft'`.
- Safety: Requires `artifact_write` permission for filesystem export.
