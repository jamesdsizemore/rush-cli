# T010: Design gate for 73-T09/CODEC, recorded verbatim from the goal-judge report

Below the line is the goal-judge's T010 report, copied unchanged.

Before T033 starts, the PM folds the gate's 72-T06 package amendments (A1-A6) into the T033/T034 cards. Owner decisions OD1-OD3 are pending.

Not re-run by the PM: this report's claims. The T036 RED author re-checks the code map at HEAD (stop_if).

---

T010 design gate for 73-T09/CODEC: **approved, but it cannot start yet.** Two things must happen first: the owner answers OD1-OD3, and the PM amends the 72-T06 gate packages (A1-A6) before T033 starts. Without those amendments the plan's import contract cannot be met through `apply_import_records` alone.

I edited nothing and ran no test suite. Read-only commands I ran: `scripts/sync_docs.py --check`, two redactor and token probes in the worktree `.venv`, and a `curl` of the pinned upstream PAS source (`session.rs`, `storage.rs` at `0c9515a`, which matches the plan text). Free disk is 21 GiB.

Part (A) is the note body for `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/docs/goals/phase-72-memory-correctness/notes/T010-design-gate-73-t09-codec.md`. Part (B) is the receipt.

---

# (A) T010: Design gate for 73-T09/CODEC (Rush capsule and PAS schema-1 codec)

Base: worktree `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72`. HEAD is `17f7645` (board only); product bytes are `07775f1`. Read-only.

Sources read:
- Plan 73: L413-512 (§7 fixed wire contract L417-428, mapping approval L429-432, amendments L433-440, 73-T09 L441-487, §8 boundary L490-507) and L195-203 (the 73-T04 checkpoint schema).
- Plan 72 §8 (L457-475).
- `memory-program-contract.md` C01 and C02.
- PAS report.
- `AGENTS.md`, `docs/templates/task-block-template.md` and ADR 0010.
- Board notes T002 (PM section), T003 and T009 (in full for H2, H5, H9-H11, §4 and §5).

## 0. Checkpoint boundary (owner decision D3)

**In this checkpoint, from 73-T09:**
- the strict `rush_v1` codec and the strict PAS schema-1 codec;
- the loss manifest (Rush `manifest` and PAS sidecar ledger);
- read-only `preview_export` / `preview_import`;
- the export policy (owner/source/visibility/overlay/secret rules, re-checked immediately before emission);
- `import`, written only through 72-T06 `apply_import_records`;
- one `MemoryOperation` `capsule`, the `rush memory capsule` CLI, and the MCP schema;
- `authorization.py`, limited to the capsule-mapping extension (`approve_capsule_mapping`, `revoke_capsule_mapping`, `resolve_capsule_mapping`, strict `purpose=capsule_import` record validation) plus the CLI-only `rush memory capsule mapping create|revoke`.

**Stays with Phase 73 (D3):**
- `src/rush/integrations/agent_hooks.py`;
- `src/rush/tools/agent_connection.py` journey projection;
- T08 views (`cli_support/rendering.py`, `tui.py`, `dashboard/server.py`, `application.js`);
- real-host and offline-machine acceptance;
- `docs/reports/memory-agent-adoption-acceptance.md`.

This checkpoint alone is not a 73-T09 PASS. The plan's own release gates also stay open: 75-T03/T04 rendered-budget counting and 75-T01 receipts (plan 73 §8, row 73-T09).

**`bridge` is not named in D3, but it is in the fixed action enum.** The packages follow D3 literally: four actions plus mapping. This is flagged as OD1.

## 1. Earlier-unit symbols CODEC consumes

The T036 RED author re-checks each one at HEAD.

| Unit | Symbol | Assumption |
|---|---|---|
| 73-T02/POLICY (T003) | `GRANT_OPERATIONS={"ask","bootstrap","expand","list","write","history","overlay_read"}`, `MemoryPolicyError(code,reason)`, `policy_path`, `hold_policy_lock(*,data_root)`, `load_policy_readonly` (with a `mappings` view), `grant_memory_scope`, `revoke_memory_scope`, `resolve_memory_scope(*,project_root,operation,owner_scope=None,requested_sources=(),session_binding=None,data_root=None)`, `user_overlay_owner_scope`, T003's internal locked-CAS writer and hex encode/decode helpers | Mutations resolve `"write"`. Lock id is `memory-policy:<path>`, reentrant per thread. Writers raise `E_CONSENT`/`E_VERSION`/`E_POLICY_INVALID`/`E_POLICY_REDACTION`. |
| 72-T01 | `retrieval.evaluate_artifact_visibility(store, artifact, *, access, mode="ordinary")`, `VisibilityDecision`, item `reference` | Every exported artifact passes this decision. CODEC never re-implements it. |
| 72-T03 | `relations.related_artifacts` (owner-checked) | Source of optional evidence, depth 1. |
| 72-T05 | Overlay store `TypedArtifactStore` rooted at `default_data_root()/user`, read through `open_readonly_view`, plus the overlay grant | Personal-scope export. |
| 72-T06 (T009 H9, plus amendments A1-A6 in §5) | `TypedArtifactStore.preview_import_records`, `apply_import_records`, new `find_import_effect_readonly`, `applicability` semantics, FD5 promote semantics | CODEC writes rows only through these. |

Existing source used unchanged:
- `store.open_readonly_view` L1844, `store_generation` L824, `_inspect_text_for_trojan_chars` L690, `MemorySubject` L30, `TrustTier` L39;
- `trust.resolve_symbol_ref` L108 (`path::Symbol`);
- `retrieval._count_tokens` L244 and `DEFAULT_ENCODING="cl100k_base"` L68;
- `io.atomic_file.AtomicFile.write_bytes` L69 and `SanitizedBytes.from_bytes` L36 (which sanitizes text);
- `io.physical_paths.PhysicalRoot.open_contained` L30;
- `safety.redactor.sanitize_value` / `SecretRedactor.redact_text`;
- `dashboard.state.cross_process_project_lock`;
- `workflows.projects.read_registry_strict`;
- `runtime.subprocesses.run_subprocess` L873;
- `rush.__version__`.

## 2. Testable behavior

1. **Operation set.** `MemoryOperation` / `VALID_OPERATIONS` / model tags gain exactly `capsule` (24 after T06 → 25). `request.action` is one of `preview_export|export|preview_import|import` (OD1). `request.format` is `rush_v1|pas_v1`, default `rush_v1`. Other actions, `bridge` (until OD1 is settled), unknown keys, explicit `null`, bool-as-int, `schema_version`, and any non-default legacy top-level argument (including top-level `invocation_id`) give `E_INPUT` before any effect.
2. **Per-action key sets are exact.**
   - `preview_export`: `{action, output}`, optional `{format, invocation_id, max_bytes, max_tokens}` (+ OD3 selectors).
   - `export`: adds required `{expected_digest, invocation_id}`.
   - `preview_import`: `{action, input}`, optional `{format, invocation_id, max_bytes, max_tokens, mapping_id, confirm_constraint_ids}`.
   - `import`: adds required `{expected_digest, expected_store_revision, invocation_id, apply: true}`.
   - `apply` is accepted only on `import`, and only as `true`.
   - `input` and `output` must be absolute path strings. The CLI makes them absolute against its cwd without resolving symlinks.
3. **Limits.**
   - `max_bytes` / `max_tokens` are strict ints ≥1, default 65536 / 8192.
   - Values above 1048576 / 131072 give `E_INPUT`.
   - A payload over the explicit limits, or over the hard caps, gives `E_BUDGET` before effects. The response carries `required_bytes`, `required_tokens`, the limits, `tokenizer_basis` and the unchanged mandatory ID list. Mandatory data is never truncated.
4. **Previews create nothing:** no store, lock, output, parent directory, authorization file or data root. The tree and data-root digests are unchanged.
5. **Preview digest.** `preview_digest` is the 64-hex SHA-256 of the canonical JSON of the bound fields (§4.4). Apply, export and import recompute and compare. A mismatch gives `E_VERSION`, with a reason from `preview_changed|store_changed|policy_changed|destination_changed|mapping_changed`, and zero effects.
6. **Export reads only visible artifacts:**
   - only eligible current artifacts of the resolved owner and approved sources, with `list` and `expand` granted;
   - overlay preferences only with explicit inclusion (OD3) and the overlay grant;
   - grants, binding IDs, capabilities, credentials and absolute roots never appear.
7. **Secrets block or omit, never leak.** A mandatory secret-bearing field gives `E_EXPORT_BLOCKED` with `{artifact_id, pointer, reason:"secret_bearing"}`, no output, and no secret in the result, logs or stderr. An optional secret-bearing item is omitted and listed in `manifest.redactions`.
8. **`rush_v1` bytes are deterministic** (same snapshot, same invocation → identical bytes). `payload_sha256` verifies. Unicode is preserved byte-exact.
9. **Import is strict.** It rejects these with `E_CAPSULE_INVALID` and zero writes:
   - unknown `schema_version`/`format`, duplicate keys, invalid UTF-8, lone surrogates, a BOM, NaN/Infinity;
   - a payload or item digest mismatch, nesting over 16, more than 128 evidence records, more than 10 PAS checkpoints, more than 50 files per checkpoint;
   - absolute paths, `..` or NUL in paths, symlinked or non-regular input, archive/compressed magic;
   - a present but mismatched/incomplete sidecar.
10. **Import writes pending, unverified records.** It writes only through `apply_import_records`: trust `IMPORTED`, `applicability=pending` for constraints and decisions, freshness `unknown`, owner and source from the grant. Selected `confirm_constraint_ids` create FD5 active local candidates in the same transaction; the imported originals stay pending.
11. **Replay.** Same invocation and same preview digest returns the original receipt (`replayed:true`), even after store or policy revision changes, as long as the grant still resolves. Same invocation with a different digest gives `E_VERSION effect_identity_reused`. A revoked grant gives `E_PERMISSION`, never replay.
12. **Mapping.** A foreign or moved origin requires an approved mapping. Missing, unknown, revoked, mismatched or grant-inactive mappings give `E_PERMISSION` with a reason. Preview still returns `OK`, listing `apply_blockers`.
13. **PAS export writes exactly two files:** a valid PAS schema-1 file in serde pretty format, plus `<output>.rush-manifest.json`, which is written last. Combined bytes and tokens are within limits. Every unrepresentable field appears in the ledger. A failed second replace restores the first only when its bytes are unchanged; otherwise it returns `E_RECOVERY_REQUIRED`.
14. **Mapping CLI.** `rush memory capsule mapping create|revoke` is CLI-only. Without `--approve` it is a no-write preview. A stale `--expected-policy-revision` gives `E_VERSION` and leaves the bytes unchanged.
15. **Restricted receiver.** The `--memory-session` bridge denies `capsule`.
16. **CLI and MCP agree.** Both return the same `raw` for the same request and the same `code`/`field` for the same invalid request.

## 3. Code and caller map at 07775f1

**Create:** `src/rush/memory/capsule.py`. It does not exist and has no callers. Its callers will be `MemoryTool._capsule` (tools/memory.py) and `cli.py` (mapping commands only).

**Edit:**

| File | Symbol / site (07775f1 lines; T06 will shift them) | Change |
|---|---|---|
| `src/rush/tools/memory.py` | `MemoryOperation` L72-95 (22 members), `VALID_OPERATIONS` L98, `_CODE_STATUS` L139, dispatch in `run` L401-630, `_envelope_result` L1406, `check_permissions` pattern L1166 | Add `"capsule"`; add `_CAPSULE_ACTION_KEYS` (dict action → (required, optional)) and `_CAPSULE_REQUEST_KEYS` (their union); add codes `E_CAPSULE_INVALID:"error"`, `E_EXPORT_BLOCKED:"fail"`, `E_RECOVERY_REQUIRED:"fail"`; add `_capsule(...)` that rejects mixed legacy arguments, checks `ExecutionPermissions` (`artifact_write` for export, `cache_write` for import), and calls `capsule.run_capsule(...)` lazily. Result via `_envelope_result(started,"capsule",code,data)`. |
| `src/rush/mcp_support/request_models.py` | `_action_union` L383 (accepts the whole allowlist per branch; not reusable), `_REQUEST_MODELS` L398, `_NESTED_ACTIONS` L484, `MEMORY_FIELDS` L542, `_memory_tag` L668, `memory_request_model_keys` L718 | New per-action strict branch models discriminated by `action`, with `StrictInt` `ge=1`, `le` = hard cap. Register `_REQUEST_MODELS["capsule"]`, `_NESTED_ACTIONS["capsule"]` and `MEMORY_FIELDS["capsule"]=("capsule", _request_field("capsule"))`. `memory_request_model_keys("capsule") == _CAPSULE_REQUEST_KEYS`. |
| `src/rush/mcp_support/tool_registry.py` | `_MEMORY_BRIDGE_OPERATIONS` L603 | No edit expected (plan-listed). The bridge deny is proved by test. |
| `src/rush/cli.py` | `memory_group`, `_memory_input_request` L3784, leaf loop L3866-3886 | New `@memory_group.group("capsule")` with leaves `preview_export`, `export`, `preview_import`, `import`, and subgroup `mapping` with `create` and `revoke`. Flags follow the fixed contract (§4.7). Actions route `_run_tool("memory", project, extra_kwargs={"operation":"capsule","request":...})`; mapping calls `authorization` directly. |
| `src/rush/memory/authorization.py` (T003-created) | `mappings` map | Mapping schema, writers and resolver (§4.6). |
| `src/rush/governance/public_operations.py` | entries L193-355 | `"memory capsule": (None, "rush.tools.memory:MemoryTool", "stateful-mutation", "rush memory capsule --help", "admin")`. |
| `governance/public-operations.toml` | generated | Regenerate with `scripts/build_remediation_manifests.py --operations`; enforced by `tests/test_phase51_public_operations.py`. |
| `src/rush/theme.py` | `_OPERATION_FAMILIES["memory"]` L443 | `"capsule": "mutation"`. |
| `tests/fixtures/phase70/cli-outcomes.json` | T27 matrix | Six cases: `memory.capsule.preview_export`, `.export`, `.preview_import`, `.import`, `.mapping.create`, `.mapping.revoke`. `test_phase70_t27._walk` L470 is recursive, so all six are mandatory. |
| `tests/test_phase70_t6.py` | L220 module-level count, L786 parity, key-parity rows | Add a `capsule` row; count 24 → 25; key-parity row `("capsule","_CAPSULE_REQUEST_KEYS")`. |
| `tests/test_phase70_t20.py` | L870 | 24 → 25; rename the test `..._is_25`. |
| `tests/test_phase54_operation_adapters.py` | L118/L123/L126 (194/95 now; 196/97 after T06) | 197 total / 98 admin. `build_operations_inventory` L52-65 walks depth 2 only, so the `capsule` group is one row. |
| `docs/reports/phase-64-66-documentation-coverage.md` | L4 contracts JSON | Must refresh. `sync_docs._cli_contracts` L279 walks recursively, so it gains `rush memory capsule`, the 4 action leaves, `mapping`, `mapping create` and `mapping revoke`. `main` has `--check` only, so regenerate via `collect_runtime_contracts(repo_root)` and update the user-guide receipt sha256 fields. |
| `docs/user-guide/working-with-ai-agents.md` | | Embedded decision FD7 (§7). |

Must stay green unmodified:
- `tests/test_memory_handoff.py`, `tests/test_phase61_handoff.py`, `tests/test_dashboard_memory_tokens.py`, `tests/test_memory_operation_metadata.py`;
- the existing `tests/test_memory_public_contract.py` and `tests/test_mcp.py` tests;
- `tests/test_phase51_public_operations.py`, `tests/test_phase70_t25.py`, `tests/test_sync_docs.py`;
- the T06 test `tests/test_phase72_memory_public.py`.

Not existing and not touched (Phase 73): `tests/test_phase73_discovery.py`, `tests/test_memory_activation_ui.py`.

Current state facts:
- No `next_action` or task-state producer exists in `src` (grep: only `tools/status.py` `next_actions`). Canonical task state is the proposed 73-T04 `episodic` `content.kind="checkpoint"` schema (plan 73 L199). This drives OD2.
- `sync_docs --check` today fails only on three uncommitted board notes missing receipts (T003, T009, T012).

## 4. Design

### 4.1 Module `src/rush/memory/capsule.py`

Imports are stdlib plus `rush.memory.{store,retrieval,relations,authorization}`, `rush.io.*` and `rush.safety.redactor`. `tiktoken` is used through `retrieval._count_tokens`.

Public functions:
- `run_capsule(*, project_root, request, permissions) -> tuple[str, dict]`;
- pure codecs `encode_rush_v1(obj)->bytes`, `decode_rush_v1(raw)->dict`, `encode_pas(session)->bytes`, `decode_pas(raw)->dict`, `pas_constraint_id(session_id, pointer, text)`;
- `build_import_records(capsule)->list[dict]`;
- `preview_digest(fields)->str`.

Constants: `HARD_MAX_BYTES=1048576`, `HARD_MAX_TOKENS=131072`, `DEFAULT_MAX_BYTES=65536`, `DEFAULT_MAX_TOKENS=8192`, `MAX_NESTING=16`, `MAX_EVIDENCE=128`, `MAX_PAS_CHECKPOINTS=10`, `MAX_FILES_PER_CHECKPOINT=50`, `TOKENIZER_BASIS="tiktoken:cl100k_base"` (an estimate; Phase 75-T03/T04 own final counting).

Canonical JSON: `json.dumps(o, sort_keys=True, separators=(",",":"), ensure_ascii=False, allow_nan=False).encode("utf-8")`. No Unicode normalization. No trailing newline.

### 4.2 `rush_v1` schema

Top level (exact): `schema_version:1`, `format:"rush_v1"`, `capsule_id`, `created_at`, `origin`, `scope`, `task`, `evidence`, `manifest`, `payload_sha256`.

- `capsule_id` = the invocation UUID.
- `created_at` = RFC3339 UTC with microseconds and `Z`, taken from the `memory_changes.created_at` of the snapshot's `store_generation` row, so preview and export agree.
- `origin` = `{producer:"rush", rush_version, project_id, worktree_id, git:{commit|null, branch|null, dirty}|null, store_revision}`. Git comes from `run_subprocess` running `git rev-parse HEAD`, `git symbolic-ref --short -q HEAD` and `git status --porcelain`; it is `null` outside a repo.
- `scope` = `{owner_scope:{kind,id}, sources:[...], user_overlay_included: bool}`. Descriptive only.
- `task` = `{task_id, task_lineage_id, description, objective, completed[], remaining[], next_action, constraints[{constraint_id,text,origin_ref}], decisions[{id,text,origin_ref}], failed_approaches[{id,text,origin_ref}], attempted[...], blockers[...], discoveries[...], last_verified_checkpoint:{check_id,command,exit_code,status,source_revision,receipt_id}|null}`.
  - `origin_ref` = `{artifact_id, artifact_version}` of the checkpoint.
  - Field sources (OD2-a): description←description, objective←objective, completed←implemented, remaining←unresolved, constraints←requirements, decisions←decisions, failed_approaches←disproved, attempted←attempted, blockers←blockers, discoveries←discoveries.
  - `last_verified_checkpoint` is the newest `checks[]` entry with `exit_code==0` and a non-empty `receipt_id`.
- `evidence[]`, ordered by `(artifact_id, artifact_version)`: `{artifact_id, artifact_version, content_hash, subject, source, owner_scope, provenance:{trust_tier,origin_kind,origin_id,created_at}, freshness, required: bool, body, body_sha256, code: {path, symbol, source_revision, file_sha256, excerpt, excerpt_sha256}|null}`.
  - `body` = the artifact `content` object exactly; `body_sha256` = sha256 of its canonical JSON.
  - `code` is present when `symbol_ref` is `path::Symbol` resolving through `PhysicalRoot(project).open_contained` to a top-level def/class. The excerpt is the exact AST node lines, at most 32768 bytes. Otherwise `code:null`, and the manifest records `code_excerpt_unavailable` with a reason.
- `manifest` = `{selected:[ids], omitted_optional:[{artifact_id,artifact_version,reason,retrieval_route:{operation:"expand",artifact_id,artifact_version}}], local_only_refs:[...], redactions:[{artifact_id,pointer,reason}], required_body_coverage:{required:n,delivered:n}, mapping_required_when:"origin project/worktree differs", source_paths:[relative], encoding:"utf-8", tokenizer_basis, token_count_kind:"estimate", delivered_bytes, delivered_tokens, omitted_bytes, omitted_tokens}`.
  - Counts are converged by re-serializing up to 4 times; failure to converge is `E_BUDGET` with `reason:"count_not_converged"`.
- `payload_sha256` = lowercase 64-hex sha256 of the canonical JSON of every other top-level field.
- File bytes = canonical JSON of the whole object.

**Selection:**
- **Task.** Find eligible `episodic` artifacts whose `content.kind=="checkpoint"` and `content.schema_version==1` under the resolved owner and sources. Pick the task (OD3 `task_id`, or the single task whose newest checkpoint `event_kind` is not `task_end`/`task_cancel`). Take that lineage's newest checkpoint by `(created_at, artifact_version, id)`. Zero open tasks gives `E_EXPORT_BLOCKED no_open_task`. More than one without a selector gives `E_INPUT field=task_id` with a candidate list of `task_id` and `next_action`.
- **Required evidence:** every `{artifact_id, artifact_version}` object found anywhere in the checkpoint content, plus the checkpoint itself. If one is not visible under T01, gives `E_EXPORT_BLOCKED {ref, reason:"not_visible"|"version_changed"|"not_applicable"}` with no content. Requirements referencing rejected or superseded artifacts are excluded and listed as `not_applicable`.
- **Optional evidence:** `related_artifacts` depth 1 of the required set, eligible, added greedily in sorted order while within limits. Non-fitting items go to `omitted_optional` with `reason:"budget"`. Overlay preferences are optional, labelled `scope_kind:"user_overlay"`.
- **Mandatory missing** (empty description, objective or next_action, or a required body over 32768 bytes) gives `E_EXPORT_BLOCKED {field, reason}`.

**Secret filtering before serialization.** For every string leaf of each selected item, `SecretRedactor.redact_text(s) != s` means secret-bearing. Mandatory gives `E_EXPORT_BLOCKED`; optional is omitted and listed. After serialization, `SanitizedBytes.from_bytes(b).data == b` is asserted; on mismatch, `E_EXPORT_BLOCKED reason:"secret_detected_after_serialization"` and no write.

Gate-run probe: sha256 hex, `sha256:`-prefixed hex, UUIDs, RFC3339 and relative paths are untouched. `/Users/j/Developer/desk-assistant-project-v2`, `token:abc`, `password=…` and an AKIA key are redacted. No absolute roots are emitted.

No redacted derivatives are produced, because the contract has no explicit-redaction field.

### 4.3 PAS schema-1 codec

Pinned upstream, fetched by the gate with curl from `crates/pas-agent-core/src/session.rs` and `storage.rs` at `0c9515a6…`:
- `Session` has `schema_version` (serde default 1), `id` (Uuid), `project_name`, `created_at`/`updated_at` (chrono `DateTime<Utc>`), `task` (TaskState, all fields `serde(default)`, `next_action: Option`), `git: Option<GitRef>` (default null; GitRef `serde(default)` with nullable branch/commit and `dirty: bool`), `checkpoints` (default `[]`).
- A checkpoint is `{id, timestamp, message, task_snapshot, git (default null), files_changed (default [])}`. A file is `{path, status}`. `FileStatus` is `"Added"|"Modified"|"Deleted"|"Untracked"|{"Renamed":{"from":...}}`.
- The writer is `serde_json::to_string_pretty`.

**Decode** (strict, beyond PAS's own leniency per plan):
- Apply the documented defaults for absent fields.
- Error on: missing `id`/`project_name`/`created_at`/`updated_at`/`task`; unknown keys at any level; `schema_version != 1`; an unknown status string or object; a non-UUID id; a non-RFC3339 timestamp; caps exceeded; a path or `Renamed.from` that is absolute or contains `..` or NUL.
- Keep exact strings, order and explicit nulls.

**Encode:** struct declaration order, `json.dumps(o, indent=2, ensure_ascii=False)`, no trailing newline. Explicit defaults and nulls are always emitted.

**Rush → PAS mapping:**
- `id` ← `capsule_id`.
- `project_name` ← the registry entry's `name` if a non-empty string, else the final component of the canonical root.
- `created_at`/`updated_at` ← `created_at`.
- `task.{description, objective, completed, remaining, next_action, blockers, constraints, discoveries}` ← text lists.
- `task.decisions` ← decisions, then each failed approach as `"Failed approach (do not retry): <text>"`.
- The last verified check (field named in plan 73 L421/L423; verified-by: grep) is appended to `discoveries` as `"Origin-reported check (re-run locally; not verified here): <command> exited <code> at <revision>"`.
- `git` ← `origin.git`; `checkpoints: []`.
- If any required text cannot be represented, export is rejected (`E_EXPORT_BLOCKED reason:"pas_unrepresentable"`).

**Sidecar** `<output>.rush-manifest.json` (canonical JSON):
- `{schema_version:1, pas_sha256, pas_session_id, rush_capsule_sha256, loss_ledger:[{rush_field, pas_field|null, representation:"exact"|"prefixed_text"|"unrepresentable", ids:[...]}], rush_only_evidence:[artifact ids], rush_capsule:<full rush_v1 object>}`.
- The ledger covers every Rush-only field: constraint IDs, origin_refs, `attempted`, last-verified details (plan 73 L423 field; verified-by: grep), `evidence`, `manifest`, `scope`, `origin` minus git, `capsule_id`, `payload_sha256`.

**Import from PAS:**
- If a sidecar sibling is present (lstat, regular file), require `sha256(PAS bytes)==pas_sha256`, `pas_session_id==id`, a verifying rush capsule `payload_sha256`, and a PAS file equal to `encode_pas(map(rush_capsule))`. Otherwise `E_CAPSULE_INVALID` (`sidecar_mismatch|stale_sidecar|incomplete_pair`). With a valid sidecar, records come from the embedded `rush_v1` capsule at full fidelity.
- A standalone PAS file gives a limited import with `continuation_complete:false` and `missing_continuation_facts` (`["rush_evidence"]` plus `"next_action"` when null). No mapping applies, because there is no origin identity.
- Constraint IDs: `"pas-c-" + sha256((session_id+"\x00"+pointer+"\x00"+text).encode("utf-8")).hexdigest()`, where pointer is `/task/constraints/<i>`. Decisions use `pas-d-` the same way.

### 4.4 Preview digest and target pre-state

`preview_digest = sha256(canonical_json({...}))`, 64 lowercase hex, over:
- `apply_intent` (`export` or `import`), `format`, `invocation_id`, `limits:{max_bytes,max_tokens}`;
- `scope:{project_id, worktree_id, owner_scope, sources, grant_id, policy_revision, mapping_id|null, user_overlay_included}`;
- `selected:[[id,version],...]` and `confirm_constraint_ids` (sorted);
- for export: `source:{store_state, store_revision, git}`, `output_sha256` (intended bytes) and `target:{path, state:"absent"|"sha256:<hex>", sidecar:{...}|null}`;
- for import: `input:{sha256, sidecar_sha256|"absent"}`, `target:{store_state:"absent"|"present", store_revision, existing_versions}`.

The invocation UUID is supplied by preview when omitted.

### 4.5 Apply ordering (fixed by plan L463)

**Export:**
1. Validate the request.
2. `hold_policy_lock`.
3. Resolve `list` and `expand`. A denial gives `E_PERMISSION` with the reason and no content.
4. `cross_process_project_lock("memory-capsule-target:"+canonical output path)`.
5. Re-snapshot through `open_readonly_view`, re-run the export policy and serialization, and recompute the digest. Target state handling:
   - pre-state equal to the preview → write;
   - target bytes already equal `output_sha256` (and the sidecar is complete) → `replayed:true`, no write;
   - otherwise `E_VERSION destination_changed`.
6. `AtomicFile(PhysicalRoot(parent)).write_bytes(name, SanitizedBytes)`.
7. Release in reverse order.

Containment for the output:
- The parent must exist, and `parent.resolve()==parent.absolute()`. Nothing is created.
- `open_contained` rejects a symlinked target.

**PAS pair:**
- Both files are staged in the same directory. An in-memory journal holds the old bytes or absent markers and the intended digests.
- The PAS file is replaced first; the sidecar is the commit marker.
- On sidecar failure, restore the old PAS bytes (or unlink) only if the current PAS bytes equal the intended digest. Otherwise keep both and return `E_RECOVERY_REQUIRED`.
- A retry with the original preview accepts PAS == intended plus sidecar == old as "resume" and writes the sidecar only.
- Read side: a pair whose sidecar `pas_sha256` does not match is rejected.

**Import:**
1. Validate the request; read and verify the input bytes, sidecar and item hashes. This is pure.
2. `hold_policy_lock`.
3. `resolve_memory_scope(operation="write", owner_scope, [destination_source])`. A denial gives `E_PERMISSION`, so a revoked grant never replays.
4. `resolve_capsule_mapping` when the origin is not the current canonical pair. Non-approved gives `E_PERMISSION` with the reason.
5. `find_import_effect_readonly(root, invocation_id, effect_id)`:
   - stored `preview_digest == expected_digest` → return the stored receipt (`replayed:true`);
   - otherwise `E_VERSION effect_identity_reused`.
6. Fresh preview: `preview_import_records` plus `store_state`/`store_revision` (A5). Recompute the digest; a mismatch gives `E_VERSION` with a specific reason.
7. Only now, `TypedArtifactStore(root)`. If the store was absent, this initializes it under the lock; a later race failure reports `store_initialized:true` with zero rows.
8. `apply_import_records(records, preview_binding={...,"preview_digest":expected_digest}, expected_versions, expected_store_revision, confirm_foreign_ids, invocation_id, effect_id, access)`. This runs one `BEGIN IMMEDIATE`: replay lookup first, then the store-revision, policy-revision and collision-version checks, the writes and the receipt, then commit.
9. Release.

Identifiers:
- `effect_id = "capsule:" + sha256("\x00".join(["import", invocation_id, project_id, worktree_id, canonical_root])).hexdigest()`.
- `capsule_digest = "sha256:" + payload_sha256`, or `"sha256:" + sha256(PAS bytes)` for a standalone PAS file.
- Foreign origin IDs: `task:<task_id>`, `constraint:<id>`, `decision:<id>`, `failed:<id>`, `evidence:<artifact_id>@<v>`, or the `pas-*` IDs. Uniqueness and the 256-character limit are checked.

Record mapping (H9 kinds):
- constraint → `preference` / `constraint`;
- decision → `architectural_decision` / `decision`;
- failed approach → `failure` / `evidence`;
- task → `episodic` / `evidence`, `content.kind:"imported_task"` (never `checkpoint`);
- PAS checkpoint → `episodic` / `evidence`, `content.kind:"imported_pas_checkpoint"`;
- evidence → its subject (a `preference` or `architectural_decision` subject takes `constraint`/`decision`);
- `source_anchor` = `{path, revision, digest}` from `code`;
- `claimed` = the provenance.

Preview `freshness` is always `"unknown"`, plus `local_source_check: matches|differs|absent|not_checked` (read-only hash through `open_contained`). `contradictions` lists proposed records whose `symbol_ref` equals a current local active artifact with a different content hash.

### 4.6 Mapping (authorization.py)

Record under `data.mappings[mapping_id]`:

```
{mapping_id, purpose:"capsule_import", principal, origin_project_id, origin_worktree_id, target_project_id, target_worktree_id, target_root_hex, owner_scope:{kind,id_hex}, grant_id, approved_revision, approved_at, revoked, revoked_revision, revoked_at}
```

- The origin IDs are validated as a canonical UUID and 64 lowercase hex before storage.
- A missing `purpose` reads as `capsule_import`, compatible with C01.
- Records with `purpose:"worktree_delta"` are left to 73-T06 as an object-only check. Any other purpose gives `record_invalid`.

Functions:
- `approve_capsule_mapping(*, project_root, origin_project_id, origin_worktree_id, expected_policy_revision, consent, data_root=None)`:
  - follows T003's writer skeleton (consent, lock, strict reload, CAS, redaction precheck);
  - requires `resolve(write)=granted` for the target, else `MemoryPolicyError("E_PERMISSION", reason)`;
  - an identical active mapping is a no-op;
  - the same origin and target with a new grant supersedes in one write.
- `revoke_capsule_mapping(*, mapping_id, expected_policy_revision, consent, data_root=None)`: unknown gives `E_MAPPING_NOT_FOUND`; a foreign principal gives `E_PRINCIPAL`.
- `resolve_capsule_mapping(*, mapping_id, project_root, origin_project_id, origin_worktree_id, data_root=None)`: read-only, never raises. State is one of `approved|unknown|revoked|origin_mismatch|target_mismatch|grant_inactive|policy_missing|policy_invalid`.

The revision bump invalidates bound previews through `policy_revision` in the digest.

CLI:
- `rush memory capsule mapping create --input FILE --project PATH --expected-policy-revision N [--approve] [--json]`. The origin comes from a `rush_v1` file or a valid PAS sidecar; standalone PAS gives `E_INPUT no_origin_identity`.
- `rush memory capsule mapping revoke --mapping-id ID --expected-policy-revision N [--approve] [--json]`.
- `--approve` is the consent and config-mutation permission. These commands are not reachable over MCP.

### 4.7 Routes

- **CLI actions:** `rush memory capsule preview_export|export|preview_import|import`.
  - Options: `--project PATH` (default `.`), `--format`, `--input`, `--output`, `--max-bytes`, `--max-tokens`, `--mapping-id`, `--expected-digest`, `--expected-store-revision`, repeatable `--confirm-constraint-id`, `--invocation-id`, `--apply`, the permission flags and `--json`.
  - Each leaf registers only its own action's flags, so inapplicable flags are Click usage errors (exit 2). Unknown and mixed request fields fail in `MemoryTool`.
  - Help text lists the actions, formats, required flags, defaults and hard caps.
- **MCP:** `rush_memory(operation="capsule", path, request={...}, allow_*)`.
- **Permissions:** `export` needs `artifact_write`; `import` needs `cache_write`; previews need no `ExecutionPermissions`. Grant operations: export `list` and `expand`; `preview_import` `list` (it reports `apply_access` from `write`); `import` `write`.

### 4.8 Error codes

| Code | Status | Used for |
|---|---|---|
| `OK` | | Success |
| `E_INPUT` | error | Request shape, OD3 ambiguity |
| `E_PERMISSION` | fail | Grant, mapping, missing permission |
| `E_OWNER` / `E_SCOPE` | fail | Passthrough from the policy |
| `E_VERSION` | fail | `preview_changed`, `store_changed`, `policy_changed`, `destination_changed`, `mapping_changed`, `effect_identity_reused`, `artifact_changed` |
| `E_BUDGET` | warn | Budget |
| `E_CAPSULE_INVALID` | error | Invalid capsule file (new) |
| `E_EXPORT_BLOCKED` | fail | Mandatory content missing, not visible or secret-bearing (new) |
| `E_RECOVERY_REQUIRED` | fail | Incomplete PAS pair or concurrent edit (new) |
| `E_STORE_CORRUPT` / `E_UNAVAILABLE` | | From `open_readonly_view` |

No error carries content or secret values.

## 5. Cross-task conflicts and required amendments

1. **72-T06 (T009 H9). The PM must amend T033 and T034 before T033 starts.** These are blocking:
   - **A1:** `apply_import_records` gains `expected_store_revision:int`, compared with `store_generation(conn)` after the replay lookup; mismatch gives `E_VERSION store_changed`. It is included in the digest.
   - **A2:** gains `confirm_foreign_ids: Sequence[str]=()`, a subset of the constraint-kind IDs. In the same transaction it applies FD5 (a new local active candidate and decision; the original stays pending; claimed outcomes are not copied). The mapping reports `confirmed_local_id`. Included in the digest.
   - **A4:** the H9 step-2 re-resolve uses `operation="write"`, because T003's `GRANT_OPERATIONS` has no `"import"`. T009 FD1 and its fixtures, which grant `import`/`explain`, conflict with T003. T003's writer would reject such grants, so the PM must reconcile this before T033.
   - **A5:** the `preview_import_records` result adds `store_state` and `store_revision` from the same read-only snapshot.
   - **A6:** the binding accepts an optional `preview_digest`, stored in the receipt. Add a read-only `find_import_effect_readonly(project_root, invocation_id, effect_id) -> dict|None` that creates nothing.
2. **73-T02/POLICY (T003):** `mappings` writers are added here, reusing T003's writer skeleton. A target lock identity of `memory-capsule-target:<path>` is taken under the policy lock. It is not a dashboard project identity, but it uses the same primitive; T003 forbids dashboard project locks under the policy lock (FD3).
3. **73-T04 (Phase 73, out of tranche):** CODEC reads its checkpoint schema before T04 exists. OD2 covers this.
4. **72-T07 (T011):** its import-review projections consume CODEC's `preview_import` data (§4.5).
5. **75 (T012 / 75-T03/T04):** the token basis is a cl100k estimate. The final counting release gate stays open (tracked in plan 73 §8, row 73-T09).
6. **Shared files** (`tools/memory.py`, `cli.py`, `request_models.py`) have one writer at a time under C09. Counts are 25 operations and 197/98 adapters, assuming T06 lands as gated.

## 6. Test matrix

All tests use `tmp_path` HOME/XDG; `data_root=default_data_root()`; `register_project(root, data_root=data_root)`; Alice's grant on `src-a` with `[list,expand,write]`; Bob's rows as foreign owner. Checkpoint rows are seeded with `TypedArtifactStore.write`, using the OD2-a schema. Filesystem and DB digests are taken before and after. Every new test must fail at RED by assertion or by an in-body `ImportError`/`AttributeError`. Tests that would pass today first assert `"capsule" in get_args(MemoryOperation)`. No skips; `posix_only` is allowed only for uid checks.

**`tests/test_memory_capsule.py` (new):**
1. `test_rush_capsule_offline_required_bodies_and_hashes`: after deleting the origin `.rush`, the capsule alone yields the exact selected IDs/versions and body digests, `payload_sha256` verifies, and the bytes are identical across two exports.
2. `test_tiny_budget_rejects_without_output`: `max_bytes=64` gives `E_BUDGET` with `required_bytes`, and the tree is unchanged.
3. `test_secret_or_private_required_body_rejects`: a required body with an AKIA key gives `E_EXPORT_BLOCKED`, no file, the secret absent from the result, caplog and stderr; an optional secret item is omitted and listed in `redactions`.
4. `test_unknown_schema_duplicate_key_and_tamper_rejected[…]`: each §2 item 9 case gives `E_CAPSULE_INVALID`, DB digest unchanged.
5. `test_preview_readonly_and_import_cas`: preview creates no store, lock, data root or output; a changed store gives `E_VERSION store_changed`; the exact new records are pending and `IMPORTED`.
6. `test_retry_same_invocation_is_idempotent`: one receipt, the same mapping, `replayed:true`.
7. `test_foreign_or_moved_worktree_needs_approved_mapping`: a moved root gives `E_PERMISSION mapping_required`; freshness is `unknown`; `local_source_check` reports `matches` only after exact hash validation.
8. `test_unverified_constraints_not_instructions`: imported constraints are pending and absent from ordinary recall and ask.
9. `test_import_requires_apply_and_preview_bound_constraint_ids`: no apply gives `E_INPUT`; an altered or omitted selection gives `E_VERSION`; a bulk selection confirms exactly the enumerated set.
10. `test_explicit_budget_increase_and_hard_caps`: an explicit 2x limit passes; hard cap + 1 gives `E_INPUT`; an oversize payload gives `E_BUDGET` with the scope unchanged.
11. `test_cli_mcp_capsule_parity`: the CLI `_run_tool` route and `make_tool_wrapper` give an equal `raw` for preview, and the same code and field for each invalid shape.
12. `test_policy_revocation_race_blocks_capsule_commit`: a revoke thread blocks until commit, then a replay gives `E_PERMISSION`.
13. `test_two_process_same_store_revision_one_import`: subprocesses give exactly one commit and one `store_changed`.
14. `test_committed_import_replay_precedes_revision_conflict`.
15. `test_preview_absent_store_and_apply_atomic_initialization`.
16. `test_capsule_request_strict_shape[...]`: all §2 items 1-2 rejections, with no effect.
17. `test_restricted_memory_session_denies_capsule`.
18. `test_export_destination_byte_cas_and_replay`: changed bytes give `E_VERSION`; intended bytes give replay; a symlinked output or parent is rejected.
19. `test_export_store_or_policy_change_requires_new_preview`.
20. `test_mandatory_missing_task_or_next_action_blocks_export`.
21. `test_owner_and_source_scope_never_exported`: Bob's content never appears; a required ref to Bob's row gives `E_EXPORT_BLOCKED not_visible` with no content.
22. `test_capsule_registry_help_and_schema`: count 25; the published enum includes `capsule`; `rush memory capsule --help` lists the actions, formats and limits; the governance row exists.

**`tests/test_memory_capsule_pas.py` (new; fixtures in `tests/fixtures/memory_capsule/`, hand-written from the gate-fetched pinned `session.rs`):**
1. `test_pas_schema1_unicode_status_roundtrip`: `decode_pas`→`encode_pas` is byte-identical for every status including `Renamed{from}`, with Unicode and order preserved.
2. `test_pas_loss_manifest_and_required_rejection`.
3. `test_pas_unknown_version_or_partial_sidecar_rejected`.
4. `test_pas_sidecar_exact_byte_pair_binding`: swapped valid pairs give zero effects.
5. `test_pas_nullable_git_next_action_and_serde_defaults`.
6. `test_pas_second_replace_failure_preserves_concurrent_edit`.
7. `test_pas_constraint_ids_deterministic`.
8. `test_pas_renamed_path_containment_rejected`.
9. `test_pas_crash_incomplete_pair_rejected_then_resumed`.
10. `test_pas_export_combined_budget`.
11. `test_standalone_pas_import_limited_unverified`.

**Extensions (new IDs only):**
- `tests/test_memory_authorization.py`: `test_capsule_mapping_create_preview_and_apply`, `test_capsule_mapping_stale_policy_revision_zero_writes`, `test_capsule_mapping_requires_current_grant`, `test_capsule_mapping_forged_id_and_unauthorized_worktree_remap`, `test_capsule_mapping_revoke_invalidates_import_preview`, `test_capsule_mapping_record_strict_loader`.
- `tests/test_phase72_portable_memory_policy.py`: `test_export_personal_scope_and_required_secret_redaction` (no overlay without inclusion; inclusion without the overlay grant gives `E_PERMISSION`; with both, rows are labelled; a required secret blocks). This ID was assigned to CODEC by T009.
- `tests/test_memory_public_contract.py`: `test_capsule_in_public_manifest_as_admin_memory_tool`.
- `tests/test_mcp.py`: `test_rush_memory_schema_publishes_capsule_actions`.

## 7. Embedded decisions (flagged; plan-consistent; not owner-level)

- **FD1:** CLI shape is a `capsule` group with action-named leaves plus a `mapping` subgroup. Governance gets 1 row; T27 gets 6 cases.
- **FD2:** Grant operations: export → `list` and `expand`; `preview_import` → `list`; `import` and mapping → `write`.
- **FD3:** Target lock identity is `memory-capsule-target:<path>`.
- **FD4:** Optional evidence is relations depth 1; there are no redacted derivatives.
- **FD5:** `capsule_id` = invocation UUID; `created_at` = the snapshot's change time.
- **FD6:** New codes `E_CAPSULE_INVALID`, `E_EXPORT_BLOCKED`, `E_RECOVERY_REQUIRED`.
- **FD7:** `docs/user-guide/working-with-ai-agents.md` documents only the shipped capsule CLI/MCP route, written last after the route passes. It carries no host or journey claims and does not name the excluded editor product (T25 `_CURSOR_RE` check).

## 8. Worker packages

These are carried in the receipt. **T036 (RED; high)** and **T037 (implement; Opus; trust boundary).**

---

# (B) Receipt

```json
{
  "goalbuddy_receipt_v1": {
    "result": "done",
    "task_id": "T010",
    "board_path": "/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/docs/goals/phase-72-memory-correctness/state.yaml",
    "decision": "approved",
    "full_outcome_complete": false,
    "rationale": "The design is mapped against 07775f1 and the pinned PAS source; the packages cover the whole D3 boundary. Three blockers remain. (1) The fixed wire contract lacks selectors for task, owner, overlay and destination source (OD3). (2) No canonical task-state producer exists; the 73-T04 schema lacks description, objective, decisions, blockers and discoveries (OD2). (3) T009 H9 cannot meet plan 73's import contract without amendments A1-A6, and its 'import' grant operation conflicts with T003. Bridge is flagged (OD1). T036 must not start until OD1-OD3 are answered and the A1-A6 amendments are on T033 and T034.",
    "worker_package": {
      "red": {
        "card": "T036",
        "objective": "Write the full 73-T09/CODEC test matrix from notes/T010 section 6 and prove each new test FAILS by execution before any production change.",
        "allowed_files": [
          "tests/test_memory_capsule.py",
          "tests/test_memory_capsule_pas.py",
          "tests/fixtures/memory_capsule/pas_session_full.json",
          "tests/fixtures/memory_capsule/pas_session_serde_defaults.json",
          "tests/test_memory_authorization.py",
          "tests/test_phase72_portable_memory_policy.py",
          "tests/test_memory_public_contract.py",
          "tests/test_mcp.py"
        ],
        "verify": [
          "cd /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72 && rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -c \"import subprocess,sys; r=subprocess.run([sys.executable,'-m','pytest','tests/test_memory_capsule.py','tests/test_memory_capsule_pas.py','-q','-p','no:cacheprovider'],capture_output=True,text=True); print(r.stdout[-4000:]); s=(r.stdout.strip().splitlines() or [''])[-1]; sys.exit(0 if r.returncode==1 and ' failed' in s and not any(w in s for w in (' passed',' skipped',' error',' xfail',' xpass')) else 1)\"",
          "cd /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72 && rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -c \"import subprocess,sys; r=subprocess.run([sys.executable,'-m','pytest','tests/test_memory_authorization.py','tests/test_phase72_portable_memory_policy.py','tests/test_memory_public_contract.py','tests/test_mcp.py','-k','capsule or personal_scope','-q','-p','no:cacheprovider'],capture_output=True,text=True); print(r.stdout[-4000:]); s=(r.stdout.strip().splitlines() or [''])[-1]; sys.exit(0 if r.returncode==1 and ' failed' in s and not any(w in s for w in (' passed',' skipped',' error',' xfail',' xpass')) else 1)\"",
          "cd /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72 && rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -c \"import subprocess,sys; r=subprocess.run([sys.executable,'-m','pytest','tests/test_memory_authorization.py','tests/test_phase72_portable_memory_policy.py','tests/test_memory_public_contract.py','tests/test_mcp.py','-k','not (capsule or personal_scope)','-q','-p','no:cacheprovider'],capture_output=True,text=True); print(r.stdout[-3000:]); s=(r.stdout.strip().splitlines() or [''])[-1]; sys.exit(0 if r.returncode==0 and 'skipped' not in s and ' error' not in s else 1)\"",
          "cd /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72 && rtk proxy uv run --python 3.12 --extra dev ruff check tests && rtk proxy uv run --python 3.12 --extra dev ruff format --check tests && rtk git diff --check"
        ],
        "stop_if": [
          "OD1, OD2 or OD3 is unanswered, or answered differently from the recommendation the matrix assumes: stop and return to the PM for a gate delta.",
          "72-T06 is not merged with amendments A1-A6 (find_import_effect_readonly, expected_store_revision, confirm_foreign_ids, preview store_state/store_revision, preview_digest binding, operation='write'), or any section 1 earlier-unit symbol differs at HEAD.",
          "tests/test_phase72_portable_memory_policy.py does not exist yet (T06 creates it).",
          "Any new test passes at RED, errors at collection, or needs a skip/xfail.",
          "Any production file, tests/test_phase70_t6.py, tests/test_phase70_t20.py, tests/test_phase54_operation_adapters.py or tests/fixtures/phase70/cli-outcomes.json would need editing (those belong to T037).",
          "A PAS fixture field cannot be traced to the pinned 0c9515a session.rs shape recorded in notes/T010 section 4.3.",
          "Free disk below 8 GiB; a temp dir is made without cleanup; a new venv would be built."
        ]
      },
      "implement": {
        "card": "T037",
        "model": "opus",
        "objective": "Implement the 73-T09/CODEC checkpoint exactly per notes/T010 sections 2-5: capsule.py codecs, preview, export policy, import through apply_import_records only, the authorization.py capsule mapping, MemoryTool 'capsule', the rush memory capsule CLI and the MCP schema, until every T036 test and existing contract passes.",
        "allowed_files": [
          "src/rush/memory/capsule.py",
          "src/rush/memory/authorization.py",
          "src/rush/tools/memory.py",
          "src/rush/cli.py",
          "src/rush/mcp_support/tool_registry.py",
          "src/rush/mcp_support/request_models.py",
          "src/rush/governance/public_operations.py",
          "governance/public-operations.toml",
          "src/rush/theme.py",
          "tests/fixtures/phase70/cli-outcomes.json",
          "tests/test_phase70_t6.py",
          "tests/test_phase70_t20.py",
          "tests/test_phase54_operation_adapters.py",
          "docs/reports/phase-64-66-documentation-coverage.md",
          "docs/user-guide/working-with-ai-agents.md"
        ],
        "verify": [
          "cd /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72 && rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -c \"import subprocess,sys; r=subprocess.run([sys.executable,'-m','pytest','tests/test_memory_capsule.py','tests/test_memory_capsule_pas.py','tests/test_memory_authorization.py','tests/test_phase72_portable_memory_policy.py','tests/test_phase72_memory_public.py','tests/test_memory_public_contract.py','tests/test_memory_operation_metadata.py','tests/test_mcp.py','tests/test_phase61_handoff.py','tests/test_memory_handoff.py','tests/test_dashboard_memory_tokens.py','tests/test_phase70_t6.py','tests/test_phase70_t20.py','tests/test_phase54_operation_adapters.py','tests/test_phase51_public_operations.py','tests/test_phase70_t27.py','tests/test_phase70_t25.py','tests/test_sync_docs.py','-q','-p','no:cacheprovider'],capture_output=True,text=True); print(r.stdout[-4000:]); s=(r.stdout.strip().splitlines() or [''])[-1]; sys.exit(0 if r.returncode==0 and 'skipped' not in s and ' error' not in s else 1)\"",
          "cd /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72 && rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev rush memory capsule --help",
          "cd /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72 && rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -c \"import subprocess,sys,re; r=subprocess.run([sys.executable,'-m','pytest','tests/','-q','-m','','-p','no:cacheprovider'],capture_output=True,text=True); out=r.stdout; print(out[-3000:]); fails=set(re.findall(r'^(?:FAILED|ERROR) (\\S+)',out,re.M)); base={'tests/test_phase70_t28f_review1.py::test_plus_minus_expand_and_collapse_detail_in_git_and_memory','tests/test_phase70_tui_usability_ef.py::test_t28e_tokens_git_artifacts'}; last=(out.strip().splitlines() or [''])[-1]; print('NEW FAILURES:',sorted(fails-base)); sys.exit(0 if fails<=base and 'skipped' not in last and ' error' not in last else 1)\"",
          "cd /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72 && rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -c \"import subprocess,sys; r=subprocess.run([sys.executable,'scripts/sync_docs.py','--check'],capture_output=True,text=True); bad=[l for l in r.stderr.splitlines() if l.strip() and not (l.startswith('docs/goals/phase-72-memory-correctness/notes/') and l.endswith(': missing coverage receipt'))]; print(r.stdout); print('\\n'.join(bad)); sys.exit(0 if not bad else 1)\"",
          "cd /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72 && rtk proxy uv run --python 3.12 --extra dev ruff check src tests scripts && rtk proxy uv run --python 3.12 --extra dev ruff format --check src tests scripts && rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev mypy src/rush && rtk git diff --check"
        ],
        "stop_if": [
          "OD1-OD3 are unanswered or changed, or T036 RED proof is absent.",
          "Any write would bypass apply_import_records, or src/rush/memory/store.py, retrieval.py or relations.py (T01/T06-owned) would need an edit: stop for a gate delta.",
          "72-T06 HEAD lacks amendments A1-A6, or T003 authorization symbols differ from notes/T010 section 1.",
          "Any T036 test would be weakened, deleted or skipped.",
          "A third fix round would be needed: the orchestrator finishes it.",
          "A file outside allowed_files changes; agent_hooks, agent_connection, rendering, tui, dashboard or the acceptance report would be touched (D3).",
          "Free disk below 8 GiB; a temp dir is made without cleanup; a new venv would be built."
        ]
      }
    },
    "evidence": [
      "tools/memory.py:72-95 has 22 MemoryOperation members; _CODE_STATUS at L139; _envelope_result at L1406; the cache_write denial pattern at L1166",
      "request_models.py:383 _action_union lets every branch accept the whole allowlist, so per-action strictness needs new models; _NESTED_ACTIONS L484; MEMORY_FIELDS L542; memory_request_model_keys L718",
      "tool_registry.py:603 _MEMORY_BRIDGE_OPERATIONS=('receive','expand','related','resume')",
      "governance/public_operations.py:52-65 inventory walks depth 2 only; tests/test_phase51_public_operations.py:15 requires 'memory capsule'; tests/test_phase70_t27.py:470 _walk is recursive; tests/test_phase54_operation_adapters.py:118-127 is 194/81/95/18 at 07775f1",
      "scripts/sync_docs.py:279 _cli_contracts recurses; main L777 is --check only; sync_docs --check today reports only the 3 board-note receipt errors",
      "io/atomic_file.py:36 SanitizedBytes.from_bytes sanitizes; probe: sha256 hex, UUID and RFC3339 are untouched, desk-assistant path / token:abc / password= / AKIA are redacted",
      "store.py: store_generation L824, open_readonly_view L1844, _inspect_text_for_trojan_chars L690; retrieval.py _count_tokens L244, DEFAULT_ENCODING cl100k_base L68",
      "grep: no next_action or task-state producer in src (only tools/status.py next_actions); plan 73 L199 73-T04 checkpoint JSON lacks description/objective/decisions/blockers/discoveries",
      "curl of pinned pas-agent 0c9515a session.rs/storage.rs confirms the plan's schema, the serde defaults, the FileStatus Renamed{from} shape and to_string_pretty",
      "T003 GRANT_OPERATIONS excludes 'import'; T009 H9 step 2 resolves operation='import' (conflict)",
      "tests/test_memory_authorization.py exists untracked (T015 active); tests/test_memory_capsule*.py, test_phase72_portable_memory_policy.py, test_phase73_discovery.py and test_memory_activation_ui.py are absent"
    ],
    "subgoal_contract": null,
    "parallel_safety": null,
    "blocked_tasks": ["T036", "T037"],
    "missing_evidence": [
      "Owner answers to OD1-OD3",
      "72-T06 merged with amendments A1-A6",
      "73-T02/POLICY authorization.py at HEAD (T015/T016 in progress)",
      "75-T03/T04 rendered-budget counting and real-host/offline acceptance (outside this checkpoint; plan 73 §8 row 73-T09)"
    ],
    "required_board_updates": [
      "Amend T009/T033/T034 (72-T06) before T033 starts: A1 expected_store_revision; A2 confirm_foreign_ids (in-transaction FD5); A4 re-resolve operation 'write' and remove 'import'/'explain' from fixture grant operations (T003 vocabulary); A5 preview_import_records returns store_state/store_revision; A6 optional binding.preview_digest stored in the receipt, plus read-only find_import_effect_readonly.",
      "Copy worker_package.red to T036 and worker_package.implement to T037; T037 assignee Opus.",
      "Route OD1-OD3 to the owner; gate T036 on the answers.",
      "Add coverage receipts for the board notes (T003/T009/T010/T012) when committing them, so sync_docs --check becomes fully clean.",
      "Record that the 73-T09 PASS stays open (D3); this checkpoint is CODEC only."
    ],
    "owner_decisions_needed": [
      {
        "id": "OD1",
        "question": "D3 omits 'bridge', but the fixed wire contract's action enum includes it. Where does bridge preview/apply land?",
        "options": [
          "(a) Bridge in CODEC now: add the bridge action, --instructions, marker-pair parsing, byte-preserving CAS and T03's four bridge tests, plus test_bridge_structural_injection_is_inert and test_bridge_surrounding_bytes_and_reread; adds AGENTS.md/CLAUDE.md/GEMINI.md write targets; the observed reread receipt stays T03/T08 acceptance.",
          "(b) Bridge in Phase 73 T03 exactly as D3 lists: CODEC ships 4 actions; T03 adds 'bridge' to the same capsule operation and parser later, and updates the capsule contract tests then."
        ],
        "packages_assume": "(b), per binding D3"
      },
      {
        "id": "OD2",
        "question": "The capsule task (description, objective, completed, remaining, next action, constraints, decisions, failed approaches, blockers, discoveries, last verified check (plan 73 L421 field list; verified-by: grep)) has no canonical producer. 73-T04's fixed checkpoint JSON lacks description, objective, decisions, blockers and discoveries. How is it sourced?",
        "options": [
          "(a) Amend 73-T04's fixed checkpoint JSON to add description/objective strings and decisions/blockers/discoveries lists of {id,text,authority,provenance}; CODEC reads that schema now (fixtures seed rows directly) and T04 must write it.",
          "(b) Pull 73-T04's checkpoint/event write schema and route into this tranche ahead of CODEC, with the same added fields."
        ],
        "packages_assume": "(a)"
      },
      {
        "id": "OD3",
        "question": "The fixed wire contract has no selector for the task, the owner (when more than one grant matches), explicit user-overlay inclusion (plan 72 §8 requires explicit inclusion), or the import destination source (H9 needs exactly one). How are they supplied?",
        "options": [
          "(a) Add optional request.task_id/--task-id, request.owner_scope/--owner, request.include_user_overlay/--include-user-overlay and request.destination_source/--source, each required only when ambiguous, and bind them into the preview digest.",
          "(b) Add the same four fields as always-explicit required fields on their actions."
        ],
        "packages_assume": "(a)"
      }
    ]
  }
}
```
