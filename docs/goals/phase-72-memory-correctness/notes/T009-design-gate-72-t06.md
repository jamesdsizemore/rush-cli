# T009: Design gate for 72-T06 (goal-judge report, recorded verbatim)

Everything below the line is the goal-judge's T009 report, copied unchanged except for two inline PM proof annotations. Part (A) is the note body and Part (B) is the receipt.

## PM re-checks (run on 07775f1)

1. `tests/test_phase70_t6.py:220` asserts `len(MEMORY_OPERATIONS) == 22`, and `tests/test_phase70_t20.py:870` asserts `len(VALID_OPERATIONS) == 22`. `typing.get_args(MemoryOperation)` has 22 members.
2. The MCP strict validator rejects `request` on `write` and `request.schema_version` on `list`. The output is in the code map.

verified-by: `sed -n 218,222p tests/test_phase70_t6.py`; `sed -n 868,871p tests/test_phase70_t20.py`; `.venv/bin/python -c "import typing; from rush.tools.memory import MemoryOperation; print(len(typing.get_args(MemoryOperation)))"` printed `22`.

The PM did not re-run the rest of this report. The T033 RED author re-checks the code map at HEAD before writing tests (stop_if).

---

I approved the T009 design gate for 72-T06. Everything below was mapped read-only at 07775f1. Nothing was edited and no test suite was run. Three facts changed the plan packet's scope:

- **The MCP route is narrower than the plan assumes.** The strict MCP validator rejects any `request` on `write`, `promote` and `maintain`, so `source_id`, `expected_version` and `candidate_refs` cannot be reached over MCP today.
- **Adding the `history` and `explain` operations breaks existing contract tests.** `tests/test_phase70_t6.py:220-221` has a module-level count assert, and `tests/test_phase70_t20.py:870` asserts 22 operations.
- **The two new CLI leaves need more files than the packet lists.** `memory history` and `memory explain` need entries in the governance manifest, the T27 CLI matrix and the adapter count test.

So the implementation package needs 13 files instead of the packet's 4, and `cli.py` is required. Part (A) is the note body for `notes/T009-design-gate-72-t06.md`. Part (B) is the receipt.

---

# (A) T009 — Design gate for 72-T06: canonical public query and administration

Base: worktree `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72`, HEAD `07775f1`. Read-only; nothing was edited and no test suite was run.

Sources read:
- Plan §2 (L13-97, including §2.1 items 1-5), §3 (L98-111), §4, §5 72-T01/T06/T07 and §8 (L457-475).
- `memory-program-contract.md` C01, C02, C05, C06, C09 and C10.
- Phase 73 plan L25, L111, L119-123 (the exact signatures 73-T02 will produce).
- `AGENTS.md` and `notes/T002-baseline-reconciliation.md` (the PM section is authoritative).

## 0. Earlier units that change these symbols

The RED author (T033) re-checks each of these at HEAD before writing tests.

| Earlier unit | Symbol T06 consumes | What T06 assumes |
|---|---|---|
| 73-T02/POLICY | `src/rush/memory/authorization.py`: `load_policy_readonly(*, data_root=None)`, `grant_memory_scope(...)`, `revoke_memory_scope(...)`, `resolve_memory_scope(*, project_root, operation, owner_scope=None, requested_sources=(), session_binding=None, data_root=None) -> dict` | The return includes `access` (`read`/`write`/`denied`), `reason`, `grant_id`, `policy_revision`, `project_id`, `worktree_id`, owner, `approved_sources` and `allowed_operations`. `allowed_operations` is free-form strings. The policy lock identity is `memory-policy:<canonical policy path>`, using `dashboard/state.py::cross_process_project_lock`. |
| 72-T01 | `retrieval.py::VisibilityDecision`, `evaluate_artifact_visibility(store, artifact, *, access, mode="ordinary", now=None, memo=None)`, item `reference`, and owner/source threading through `MemoryTool.run`, `_query` and `_compact_query` | T06 calls this decision. It never re-implements it. T06 adds one applicability and task-binding check inside it (section 3, H6). |
| 72-T02 | Paging-cursor primitives (`_encode_cursor` / `_decode_cursor` in `retrieval.py:248/255`), the exact-once `recall_page`, and the budget admission-minimum helper | T06 composes multi-subject pages on top of these. It reuses the admission helper unchanged. |
| 72-T03 | `relations.py::add_relation` (owner policy) and `related_artifacts` | T06 extracts a connection-level insert helper from `add_relation` with the same checks (H6). |
| 72-T04 | Maintenance owner scoping | v2 `maintain` passes the grant's owner and reuses the T04 functions. |
| 72-T05 | Preference `scope`/`task_id` and the overlay grant | T06 reuses the same `task_id` field name if T05 introduced one. |

## 1. Testable behavior

1. `MemoryOperation`, `VALID_OPERATIONS`, the dispatch table and the MCP tags gain exactly two operations, `history` and `explain` (22 → 24).
2. A v2 request is a nested `request` containing `schema_version: 2` (a strict integer).
   - It is accepted for `list`, `ask`, `expand`, `related`, `history`, `explain`, `write`, `edit`, `archive`, `delete`, `promote`, `link` and `maintain`.
   - `history` and `explain` are v2-only.
   - `recall` and every other operation reject a v2 request with `E_INPUT`.
3. Validation rejects before any effect (no store opened, no file created). Rejected inputs:
   - unknown keys;
   - a boolean used as an integer;
   - explicit `null` where not allowed;
   - legacy and v2 forms in the same call: any of `subject`, a non-empty `query`, `session_allowlist`, `content`, `source`, `symbol_ref`, `candidate_sources`, `task`, `owner_scope`, `include_archived=True`, `user_stated=True` or any list filter alongside a v2 request.
4. Read fields:
   - `subjects`: unique, non-empty subset of the seven subjects. Omitted means all seven in `MemorySubject` order.
   - `query`: string, default `""`. `ask` requires it non-empty.
   - `owner_scope`, `sources`, `trust_tiers`, `freshness` (values `current`, `stale`, `unknown`, `not_applicable`), `archive_mode` (`active` by default, or `historical`).
   - `limit`: strict integer 1-100, default 20.
   - `max_tokens` / `max_bytes`: strict integers ≥1. Omitted means 2048 / 8192 (`retrieval.py:66-67`).
   - `cursor`: non-empty string or `null`.
   - `task_id`: optional non-empty string.
5. Budgets:
   - The six bad values (`true`, `1.5`, `"2048"`, `null`, `0`, `-1`) are rejected for either budget with `E_INPUT`. Filesystem and SQLite stay unchanged.
   - A cap below the computed admission minimum is rejected with `E_INPUT` (field named) before any extraction.
   - An admitted response, success or `E_BUDGET`, fits both caps including the envelope and the cursor.
6. Scope resolution:
   - An omitted owner resolves to the single authorized grant owner for the canonical project. More than one matching grant gives `E_INPUT` (`field=owner_scope`).
   - An explicit owner without a grant gives `E_OWNER`.
   - Omitted sources means exactly the grant's approved sources. Supplied sources must be a subset; otherwise `E_SCOPE`.
   - `[]`, `null`, `[""]`, non-strings and duplicates give `E_INPUT`.
   - No policy, no grant or a missing operation gives `E_PERMISSION` with no items and no counts.
7. Each read item carries `reference` (`artifact_id`, `artifact_version`, `content_hash`, `project_id`, `worktree_id`, `owner_scope`, `source`, `subject`, `trust_tier`, provenance, freshness). It also keeps the legacy compact fields (`id`, `version`, `excerpt`, `source`, `trust`, `freshness`, `relations`) plus `applicability` and `exclusion_reasons` (empty in active mode).
8. History and historical mode:
   - `archive_mode: "historical"` and `history` require an `allowed_operations` entry `"history"` in addition to the base operation.
   - `history` returns immutable versions oldest first, with tombstones labelled, owner and source checked before any content, and receipts per version.
9. `explain` takes exactly one of `artifact_id` (optionally with `artifact_version`) or a non-empty `query`. It returns `supporting`, `contrary`, `attempted` and `affected` reference lists plus `unknowns`. It makes no model call and never generates rationale text.
10. Mutations:
    - Preview by default; a preview never constructs a writable store.
    - Apply requires `apply: true`, the existing `ExecutionPermissions` (`cache_write`), a current grant with `access=write` for that operation, the exact owner and the expected versions.
    - Apply holds the policy lock, then a single `BEGIN IMMEDIATE`, through commit. Any failure rolls everything back.
11. Effect identity: the receipt key is (`invocation_id`, `effect_id`).
    - Same key and same request digest: returns the original result with `replayed: true` and writes nothing.
    - Same key, different digest: `E_VERSION` with `reason: "effect_identity_reused"` and zero writes.
    - Independent writes with identical content stay distinct.
12. Corrections and restore:
    - `edit` with `correction.kind = "reject"` appends a version with applicability `rejected`, same content and same trust.
    - `"correct"` appends a version with new content; the existing STATED demotion is kept.
    - `"supersede"` creates a new artifact and a `supersedes` edge, and marks the original `superseded` by appending a version.
    - The result reports `affected` relations, summaries and task guidance.
    - Rejected, superseded and pending records leave ordinary recall.
    - `archive` with `archived: false` restores.
13. A v2 `delete` naming two IDs with one stale revision rolls back both.
14. A v2 `promote` from a reviewed source creates a new candidate and decision in one transaction. The original's content, version and trust are unchanged.
15. Mutating a row that does not exist or belongs to a foreign owner gives `E_NOT_VISIBLE` with an identical body in both cases.
16. A conflict or refusal echoes `data.retained` (the submitted request without `apply`) so the user's form survives.
17. The restricted `--memory-session` bridge rejects admin operations, `history`, `explain` and any request containing `schema_version`, with `E_PERMISSION`, before constructing a store.
18. CLI `--input` routes and real stdio MCP return the same v2 `raw` for the same read and the same `code` / `schema_version` for the same invalid request.
19. `TypedArtifactStore.apply_import_records` and `preview_import_records` behave as specified in H9, including the five PAS cases in section 5.

## 2. Code and caller map at 07775f1

The map uses `graft callers --depth all` and `git grep`.

### `src/rush/tools/memory.py`

| Symbol | Location |
|---|---|
| `MemoryOperation` | L72 |
| `VALID_OPERATIONS` | L98 |
| `_CODE_STATUS` | L132 |
| `_COMPACT_REQUEST_KEYS` | L150 |
| `*_REQUEST_KEYS` constants | L162-299 |
| `_PROMOTE_REQUEST_KEYS` (includes `source_id` / `expected_version` / `candidate_refs`) | L287 |
| `_SUBJECT_FAMILY` | L304 |
| `__call__` | L337 |
| `run` (dispatch table) | L401-630 |
| `_list_filtered` | L665 |
| `_parse_mutation_request` | L793 |
| `_query` (writable store; requires subject and query) | L844 |
| `_compact_query` (constructs a writable `TypedArtifactStore(root)`) | L885-1057 |
| `_expand`, `_link`, `_related` | L1059, L1157, L1226 |
| `_envelope_result` (schema 1 envelope) | L1406 |
| `_parse_owner_scope` | L1431 |
| `_run_write` | L1455 |
| `_run_promote` | L1566-1789 (candidate creation and promotion are two separate commits) |
| `_run_maintain` | L1791 |
| `_run_delete` | L2690 |
| `_edit_or_archive` | L2886-3063 |
| `_result` | L3113 |
| `_MUTATION_VIEW_OPERATIONS` / `_with_mutation_view` | L3284 / L3287 |

Callers of `run`: `__call__`, `cli.py` (L3460-3721 plus the generic `--input` leaves L3799-3880), `dashboard/server.py` (L2655-3187, L3881), `tui.py` (L582 `memory_run`; operation calls L3205-4386), `tool_registry` (bridge), and `scripts/benchmarks/{memory,memory_datasets,run}.py` (legacy paths only; must stay unchanged).

### `src/rush/memory/store.py`

| Symbol | Location |
|---|---|
| `TrustTier` (includes `IMPORTED`) | L39 |
| `MemoryArtifact` | L324 |
| `_VERSION_TABLE_STATEMENTS` | L354 |
| `mutation_receipts` (`operation_id` primary key) | L550 |
| `_SCHEMA_SQL` | L563 |
| `idx_memory_origin`, unique (`origin_kind`, `origin_id`) | L591 |
| `_write_version` | L630 |
| `_row_to_artifact` | L722 |
| `_init_db` | L973 |
| `_write_receipt` (`INSERT OR REPLACE`) | L1103 |
| `get_receipt` | L1127 |
| `read_artifact_receipts_readonly` (reuse for history) | L1147 |
| `search_candidates` / `scope_artifacts` | L1175 / L1230 |
| `delete_batch` | L1302 |
| `edit` | L1435 |
| `archive` | L1529 |
| `open_readonly` / `open_readonly_view` | L1821 / L1844 |
| `preview_mutation` | L1888 |
| `upgrade` | L1964 |
| `_prepare_write` | L2122 (evicts a STATED row with a conflicting `symbol_ref`; import must never use it) |
| `_insert_row` / `write` | L2167 / L2214 |
| `promote` | L2553 |
| `promote_stored_artifact(conn, ...)` | L2771 (connection-level; reuse) |

Callers of `_write_receipt`: `archive`, `create_handoff_session`, `delete_batch`, `edit`, `promote` and `write`. Callers of `get_receipt`: `dashboard/state.py:2294`, `workflows/project_run.py:2629`. `mutation_receipts` is also used by `store.py:2426` (handoff, `INSERT OR IGNORE`). The dashboard `MutationLedger` reserves `receipt_operation_id` values at `server.py:2654/2691/2742/2809`; these must keep working.

### Other source files

- **`src/rush/memory/retrieval.py`:** `DEFAULT_LIMIT=8` (legacy compact default, unchanged), `DEFAULT_MAX_TOKENS=2048`, `DEFAULT_MAX_BYTES=8192` (L64-67), `_candidate_to_item` L300 (compact item shape), `_measure_page` L325, `_trial_page_bytes` L344, `_page` L378, `recall_page` L399.
- **`src/rush/memory/relations.py`:** `add_relation` L89 runs its own `BEGIN IMMEDIATE`; `RELATION_KINDS`.
- **`src/rush/memory/consolidation.py`:** `summary_is_current` L140 reads `content.member_versions`. That is enough to compute affected summaries; no edit needed.
- **`src/rush/mcp_support/request_models.py`:**
  - Memory models L223-475.
  - `MEMORY_FIELDS` L543: `write`/`promote`/`maintain` have no `request`. Verified: `write` with a request is rejected ("Extra inputs are not permitted"), and `list` with `schema_version` 2 in its request is rejected.
    verified-by: (PM) `validate_and_normalize('rush_memory', {'operation':'write','path':'.','request':{'source_id':'x'}})` returned E_INPUT, `request: Extra inputs are not permitted`. The `list` probe with `request={'schema_version':2}` returned E_INPUT, `request.schema_version: Extra inputs are not permitted`.
  - `_memory_tag` L668, `_memory_spec` L677, `memory_request_model_keys` L718, `_flatten` / `_published` L794/L843, `_reject` L974, `validate_and_normalize` L1025.
  - Callers: `mcp.py:277-317` (`call_tool`) and `tests/test_phase70_t6.py`.
- **`src/rush/mcp_support/tool_registry.py`:** `_MEMORY_BRIDGE_OPERATIONS` L603 and `build_memory_bridge_handler` L606-661, which constructs `TypedArtifactStore(root)` before `load_session`. Callers: `register_memory_bridge_tool` → `mcp.build_server`; `tests/test_memory_handoff.py` (3 tests); `tests/test_phase70_t19.py:809`; `tests/test_phase70_t20.py:846`.
- **`src/rush/cli.py`:**
  - `memory_group` L3401.
  - `ask` / `recall` / `list` / `write` / `promote` / `maintain` L3441-3721 (positional, no `--input`).
  - `_MEMORY_OPERATION_HELP` L3741, `_memory_input_request` L3784, `_build_memory_operation_command` L3797.
  - The leaf loop L3866-3886 registers `expand`, `link`, `related`, `consolidate`, `verify-attempt`, `prepare`, `resume`, `intent`, `recipe`, `plan-checks`, `last-success-diagnose`, `handoff`, `receive`, `delete`, `edit`, `archive`.
- **Reuse points:** `src/rush/token_economy/telemetry.py:358 read_artifact_expansion_receipts_readonly`; `src/rush/setup/provision.py:124 default_data_root` (macOS `HOME/Library/Application Support/Rush`; Linux `XDG_DATA_HOME` or `~/.local/share/rush`).

### Files missing from the packet's list (required)

| File | Why it changes |
|---|---|
| `src/rush/cli.py` | `memory history` / `memory explain` leaves and `--input` on `list`/`ask`/`write`/`promote`/`maintain` for CLI parity. **cli.py is required.** |
| `src/rush/memory/retrieval.py` | Applicability and task-binding check inside `evaluate_artifact_visibility`; v2 multi-subject composer. |
| `src/rush/memory/relations.py` | Connection-level relation insert for the supersede transaction. |
| `src/rush/governance/public_operations.py` | Entries for `memory history` and `memory explain` (admin, MemoryTool). |
| `governance/public-operations.toml` | Regenerate with `scripts/build_remediation_manifests.py --operations`; never hand-edit. Enforced by `tests/test_phase51_public_operations.py:101`. |
| `tests/fixtures/phase70/cli-outcomes.json` | Cases `memory.history` and `memory.explain`, modelled on `memory.archive` at L4235; `tests/test_phase70_t27.py:644/1002` require set equality with the live Click registry. |
| `tests/test_phase70_t6.py` | `MEMORY_OPERATIONS` gains `history` and `explain` (L220 count 22 → 24, a module-level assert); key-parity rows. |
| `tests/test_phase70_t20.py` | L866-871: count 22 → 24; rename the test to `test_rush_memory_schema_operation_count_is_24`. |
| `tests/test_phase54_operation_adapters.py` | L118/L123: total 194 → 196; L126: `admin_count` 95 → 97. |

Callers that must stay green unmodified:
- `tests/test_memory_handoff.py`, `tests/test_memory_versions.py`, `tests/test_phase70_t28d_*.py`, `tests/test_phase70_tui_usability.py`, `tests/test_dashboard_memory_tokens.py`;
- `tests/test_memory_public_contract.py` (existing tests);
- `tests/test_phase61_memory_tool.py`, `tests/test_mcp.py`, `tests/test_phase60_characterization.py:257`;
- the benchmark scripts.

## 3. Design of the hard parts

### H1. Dispatch and mixed-form detection (`tools/memory.py`)

- `run`, after the operation check: `v2 = isinstance(request, dict) and "schema_version" in request`.
- If `v2`:
  - Reject when the operation is not in `_V2_OPERATIONS`.
  - Reject when `type(request["schema_version"]) is not int` or its value is not 2.
  - Reject when any legacy argument is non-default (section 1 item 3).
  - All three rejections return `E_INPUT` with `field="schema_version"` or the legacy field name.
  - Then `self._run_v2(started, root, operation, request, granted, invocation_id=invocation_id, project_id=..., run_id=..., agent_id=..., session_id=...)`.
- If not `v2`: the current legacy dispatch runs unchanged.
- `history` and `explain` without a v2 request give `E_INPUT` (`field="request"`).
- Each v2 handler validates with its key-set constant `_V2_<OP>_REQUEST_KEYS` and the field rules below. It reuses the existing store methods; there is no second permission or admin dispatcher.
- `_MUTATION_VIEW_OPERATIONS` stays as is. `_with_mutation_view` works on the v2 envelope because `"operation"` and `"data"` are present.

v2 result builder `_v2_result(started, operation, code, *, items=(), next_cursor=None, complete=False, unknowns=(), data=None, extra=None)`:

```
raw = {"schema_version": 2, "operation": op, "code": code,
       "items": [...], "next_cursor": str|None, "complete": bool,
       "unknowns": [...], "data": {...}, **extra}
```

- Status comes from `_CODE_STATUS`. The outer ToolResult is unchanged.
- Read operations add `"budget": {"max_tokens", "max_bytes", "tokens", "bytes", "encoding"}`.
- `explain` adds `supporting`, `contrary`, `attempted` and `affected` at top level.
- Error data is `{"message": str, "field": str | None}`, plus `reason` / `retained` on conflicts.
- `E_NOT_VISIBLE` data is exactly `{"message": "artifact not visible", "field": null}` for both missing and denied.

### H2. Access resolution and error codes

`_resolve_v2_access(root, operation, request, *, historical)`:

1. Call `authorization.resolve_memory_scope(project_root=root, operation=<op>, owner_scope=<parsed owner or None>, requested_sources=<sources or ()>)` with the default data root.
2. For `archive_mode == "historical"` and for `history`, also resolve `operation="history"`.
3. Mutations require `access == "write"`.

Codes are mapped from the scenario, not from wording:

| Scenario | Code |
|---|---|
| Missing policy, no grant for the root, revoked, expired or moved | `E_PERMISSION` |
| Grant present but operation not allowed | `E_PERMISSION` |
| Explicit owner not granted | `E_OWNER` |
| Sources not a subset of the grant | `E_SCOPE` |
| Owner omitted and more than one grant matches | `E_INPUT` (`field="owner_scope"`) |

- The policy is read-only (`load_policy_readonly` semantics). A missing policy creates no files.
- Grant operation names are the MemoryOperation names plus `"history"` (historical permission) and `"import"` (for `apply_import_records`). Flagged decision FD1.
- A non-visible row (missing or foreign owner) gives `E_NOT_VISIBLE` through T01's decision.

### H3. Multi-subject listing and cursor (`retrieval.py` composer `v2_page`)

1. Iterate subjects in `MemorySubject` order.
2. Per subject:
   - Non-empty query: T02's exact-once `recall_page` ordering.
   - Empty query (browse): keyset order (`created_at`, `id`) over `scope_artifacts`.
3. Every row passes `evaluate_artifact_visibility(..., access, mode="ordinary"|"historical")` before ranking and packing. Freshness and trust filters apply after the decision. `freshness` filters on T01's `freshness`.
4. Stop at `limit` or budget. The remaining budget passed down is the cap minus the serialized size of the v2 envelope with the current items and a worst-case cursor.
5. Paging cursor: HMAC through T02's `_encode_cursor` with payload `{"v":2,"op","subjects","query","owner":"kind:id","sources","trust_tiers","freshness","archive_mode","task_id","namespace":root,"generation","policy_revision","subject_index","inner"}`.
6. A binding mismatch, a generation change, a policy-revision change or a tampered cursor gives `E_RESTART`, with `data.restart = <original filters>`. Revocation gives `E_PERMISSION`.
7. `complete` is true only when every subject is exhausted. A partial page never claims complete.

### H4. Budget admission

- T02's admission-minimum helper runs before any store open.
- The minimum covers the complete canonical v2 `E_BUDGET` envelope plus the framing T02 defines, measured with the same serializer and tokenizer.
- A cap below the minimum gives `E_INPUT` (`field` = the cap). It is counted as an admission failure with no successful-context receipt.
- After packing, the whole v2 `raw` is re-measured. Over cap, items are trimmed with the cursor positioned at the first dropped item. If zero items plus the cursor cannot fit: `E_BUDGET`, no cursor, `complete: false`, with `data.required = {"bytes", "tokens"}` only when it fits.

### H5. Mutation transaction and effect receipts (`store.py`)

Additive migration `_migrate_t06_columns(conn)`, called from `_init_db` and `upgrade`:

- `memory_artifacts`: add `applicability TEXT` and `task_binding TEXT`.
- `memory_artifact_versions`: add `applicability`, `task_binding`, `correction`, `owner_scope_kind`, `owner_scope_id` (all `TEXT`).
- `mutation_receipts`: add `operation`, `invocation_id`, `effect_id`, `request_digest`, `result` (all `TEXT`), plus `CREATE UNIQUE INDEX IF NOT EXISTS idx_mutation_receipts_effect ON mutation_receipts(invocation_id, effect_id) WHERE invocation_id IS NOT NULL AND effect_id IS NOT NULL`.

Rules:
- `NULL` applicability means `active` for legacy rows.
- `open_readonly_view` returns `migration_required` when `applicability` is absent. It never migrates on read.
- `_write_version` gains keyword-only `applicability=None`, `task_binding=None`, `correction=None`, `owner_scope=None` and records them. `_row_to_artifact` and `MemoryArtifact` gain `applicability: str | None = None` and `task_binding: dict | None = None`.
- New `_write_effect_receipt(conn, *, operation, invocation_id, effect_id, request_digest, artifact_id, revision, kind, result)` uses plain `INSERT`, never `REPLACE`, and generates `operation_id = uuid4().hex`.
- New `find_effect_receipt(conn, invocation_id, effect_id)`.

Request digest:

```
"sha256:" + sha256(json.dumps({"operation": op, "root": str(root), "request": request minus "apply"},
                              sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
```

Apply sequence:

1. Validate.
2. Acquire the policy lock: `cross_process_project_lock(f"memory-policy:{policy_path}", data_root=<data root>)`, or 73-T02's exported helper for the same identity if one exists.
3. Re-resolve the policy. Denied gives `E_PERMISSION`; a revision differing from the one checked at request time gives `E_VERSION` (`reason: "policy_changed"`).
4. Store method with `effect=` set: `BEGIN IMMEDIATE`, then look up the effect receipt.
   - Same digest: return the stored result with `replayed: true`.
   - Different digest: `E_VERSION` (`reason: "effect_identity_reused"`).
5. Otherwise run the existing scope, owner and version checks, write, write the receipt, commit, release the lock.

Constraints:
- The lock order is policy, then store.
- v2 apply requires a caller-supplied non-empty `invocation_id` (`E_INPUT` otherwise) and `request.effect_id` (non-empty string, at most 200 characters).
- A preview returns `invocation_id` (supplied or a fresh uuid4) and `request_digest`, and persists nothing.
- `store.edit`, `archive` and `delete_batch` gain `effect=None, correction=None, applicability=None`.
- New `promote_from_source(...)` does candidate insert, `promote_stored_artifact`, both receipts and commit in a single transaction.
- `write` gains `effect=None, task_binding=None`.
- The legacy keywords (`receipt_operation_id(s)`) and the legacy paths are unchanged.

### H6. Corrections, applicability and affected records

Correction shape: `correction = {kind: "correct"|"reject"|"supersede", reason: non-empty string, supersedes: [{artifact_id, artifact_version}] (min 1; must name the edited artifact at expected_version)}`.

| Kind | Content | Effect |
|---|---|---|
| `reject` | Forbidden | Appends version N+1 with the same content and trust and `applicability='rejected'` |
| `correct` | Required | Like `edit`, with `correction` stored on the version |
| `supersede` | Required | Inserts a new artifact (same subject and owner, source = the grant's single source or `request.source`, trust from `default_entry_tier("local_tool")`, `applicability='active'`); appends original version N+1 with `applicability='superseded'`; inserts a `supersedes` edge from new@1 to original@N+1 through `relations.insert_relation_tx(conn, ...)` (extracted from `add_relation`, which now wraps it in its own `BEGIN IMMEDIATE`) |

`affected` for a correction:
- `relations`: rows in `memory_relations` touching the original, as `{sequence, kind, source_ref, target_ref}`.
- `summaries`: visible rows whose `content.member_versions` contains the original ID.
- `task_guidance`: visible rows with a non-null `task_binding` linked to the original by any edge.
- All three are filtered through the same visibility decision.

Invalidation needs no new mechanism: appending a version invalidates `summary_is_current`, embeddings keyed by version, and cursor generation.

`evaluate_artifact_visibility` in ordinary mode treats applicability `rejected`, `superseded` or `pending`, and a `task_binding.task_id` different from the request's `task_id` (or an absent request `task_id`), as `usable_as_current = False`. The reason codes are `rejected`, `superseded`, `pending_review` and `task_mismatch`. In historical mode the row stays visible and labelled.

### H7. History

- Request: `{schema_version: 2, artifact_id, owner_scope?, sources?, limit 1-100 = 20, cursor?, max_tokens?, max_bytes?}`.
- New read-only method `artifact_versions(self, artifact_id, *, after_version=0, limit) -> list[Row]` reads `memory_artifact_versions` ascending. It works through `open_readonly_view`; no store gives an empty, complete result.
- Owner per version is `owner_scope_kind/id`, else the current row, else `legacy_owner_scope(root)`.
- Owner and source are checked before content; a mismatch gives `E_NOT_VISIBLE`.
- Item fields: `reference`, `content` (parsed JSON), `created_at`, `deleted`, `applicability`, `correction`, `exclusion_reasons`, and `receipts` (`read_artifact_receipts_readonly` plus `read_artifact_expansion_receipts_readonly`, each bounded at 8).
- A version whose item exceeds the budget is returned with `content_omitted: {"reason": "budget", "expand": {"artifact_id", "artifact_version", "archive_mode": "historical"}}`.

### H8. Explain (no model call)

Request: `{schema_version: 2, artifact_id XOR query, artifact_version?, subjects?, limit?, owner_scope?, sources?, max_tokens?, max_bytes?}`. Supplying both, or neither, gives `E_INPUT`.

Targets: the visible current artifact, or the first `limit` ordinary matches for the query.

Buckets (visible references only; denied neighbours are never counted):

| Bucket | Contents |
|---|---|
| `supporting` | The targets, plus outgoing `validated_by`, `implements`, `depends_on`, `caused_by` and `fixed_by` endpoints |
| `contrary` | `contradicts` in either direction, and `supersedes` edges whose target is the target |
| `attempted` | Visible `failure` and `episodic` records linked by any edge (query mode also includes `failure` and `episodic` query matches) |
| `affected` | Same computation as H6 |

`unknowns` entries:
- `{"code": "no_recorded_rationale", "artifact_id"}` when supporting has only the target itself;
- `{"code": "freshness_unknown", "artifact_id"}`;
- `{"code": "no_matches"}`.

### H9. Atomic import seam (contract the CODEC gate T010 consumes)

Read-only preview, which never creates a file, lock or key:

```python
@classmethod
def preview_import_records(cls, project_root: Path, *, records: Sequence[Mapping[str, Any]],
                           access: Mapping[str, Any], capsule_digest: str,
                           destination_source: str) -> dict[str, Any]
```

Apply:

```python
def apply_import_records(self, *, records: Sequence[Mapping[str, Any]],
                         preview_binding: Mapping[str, Any], expected_versions: Mapping[str, int],
                         invocation_id: str, effect_id: str, access: Mapping[str, Any]) -> dict[str, Any]
```

Both return `{"code": ...}` dictionaries and never raise for a business-rule rejection. Their codes are `OK`, `E_INPUT`, `E_PERMISSION`, `E_OWNER`, `E_SCOPE`, `E_VERSION` and `E_STORE_BUSY`.

**Canonical record** (validated CODEC output). Exact keys; anything else is `E_INPUT`.
- Required: `foreign_origin_id` (non-empty string, at most 256 characters), `subject` (MemorySubject), `content` (JSON object), `authority_kind` (`"constraint"`, `"decision"` or `"evidence"`).
- Optional: `symbol_ref` (string or null), `source_anchor` (`{path, revision, digest}` or null), `claimed` (`{trust_tier, status, owner, author, created_at}`, provenance only).
- A `preference` or `architectural_decision` record must use `authority_kind` `constraint` or `decision`.
- Content containing Trojan Source characters rejects the whole import (`E_INPUT` naming `foreign_origin_id`), with zero writes.
- Duplicate `foreign_origin_id` values give `E_INPUT`.

**`preview_binding`:**

```
{"schema_version": 1, "capsule_digest": "sha256:<64 hex>", "selection": [sorted unique foreign_origin_id],
 "destination": {"root", "project_id", "worktree_id", "owner_scope": {"kind","id"}, "source"},
 "policy_revision": int, "grant_id": str, "existing_versions": {local_id: int}}
```

**Preview result:** `{"code": "OK", "binding": <the binding above>, "proposed": [{"foreign_origin_id", "subject", "applicability", "trust_tier": "IMPORTED", "status": "new"|"collision"}], "collisions": [{"foreign_origin_id", "local_id", "artifact_version", "reason": "same_origin"|"foreign_id_is_local_id"}], "required_consent": "import"}`.

**Collisions:**
- `same_origin`: a row with `origin_kind='import'` and `origin_id=f"{capsule_digest}:{foreign_origin_id}"` already exists.
- `foreign_id_is_local_id`: a row whose `id` equals the foreign ID already exists.
- `expected_versions` must equal `binding.existing_versions` exactly; otherwise `E_INPUT` (`binding_mismatch`).

**Apply algorithm:**
1. Validate the records and the binding.
   - `selection` must equal the records' IDs.
   - `binding.destination.root` must equal `self.project_root`, and its project and worktree must match `access`.
   - `destination.source` must be in `access.approved_sources`, and `access.access` must be `"write"`.
   - `access.grant_id` and `policy_revision` must equal the binding's.
   - `invocation_id` must be a UUID string (C10).
2. Acquire the policy lock, then re-resolve: `resolve_memory_scope(project_root, operation="import", owner_scope=destination owner, requested_sources=[destination.source])`. Denied gives `E_PERMISSION`.
3. `BEGIN IMMEDIATE`, then look up the effect receipt for (`invocation_id`, `effect_id`).
   - Same digest: return the stored mapping with `replayed: true`.
   - Different digest: `E_VERSION` (`effect_identity_reused`).
   - The digest covers the operation `"import"`, the root, the binding, the records and `expected_versions`.
4. A current policy revision different from `binding.policy_revision` gives `E_VERSION` (`policy_changed`).
5. Recompute the collisions. A colliding local ID missing from `expected_versions`, or one whose current version differs from it, gives `E_VERSION` (`artifact_changed`).
6. For each record:
   - Collision: mapping status `collision_unresolved` (existing `local_id` and version); never replaced.
   - New record:
     - ID: `local_id = uuid4().hex`, regenerated if it equals the foreign ID.
     - Content and anchors: `sanitize_value` on the content; `symbol_ref` kept; `content_hash = None` (an external digest is never trusted).
     - Authority: `trust_tier = "IMPORTED"`; `applicability = "pending"` for constraints and decisions, `"active"` for evidence.
     - Ownership and source: owner and source come from `destination` (the grant), never from `claimed`.
     - Origin: `origin_kind = "import"`, `origin_id = f"{capsule_digest}:{foreign_origin_id}"`.
     - Write path: inserted through `_insert_row` plus a version row that stores the provenance `{claimed, source_anchor, foreign_origin_id, capsule_digest}` in `correction`-free version metadata. `_prepare_write` is never called, so no STATED eviction can happen.
7. Write one effect receipt (`kind="import"`, `result=` the mapping), then commit. Any exception rolls back everything: zero rows and no receipt.

**Result:** `{"code": "OK", "applied": true, "replayed": bool, "receipt_id", "invocation_id", "effect_id", "request_digest", "policy_revision", "mapping": [{"foreign_origin_id", "local_id", "artifact_version", "status": "imported"|"collision_unresolved", "applicability", "trust_tier"}]}`.

- Replay after a crash or retry returns the identical mapping.
- A distinct `effect_id` for the same capsule reports `collision_unresolved` for records already imported.
- A newer capsule digest creates separate pending artifacts; nothing is replaced.
- Confirming an imported constraint is v2 `promote` with `source_id` = the imported ID and `user_stated: true`. It creates a new local candidate and decision (`active`); the imported original stays `pending` and unchanged.

### H10. MCP models (`request_models.py`)

- `_memory_tag`: a dictionary request containing `schema_version` maps to tag `f"{op}:v2"`; `history` and `explain` map to their own tag.
- `MEMORY_FIELDS` gains `<op>:v2` entries with fields `{request: V2 model (required)}` only (plus `_MEMORY_COMMON`). Legacy top-level fields are therefore `extra_forbidden`, which yields `E_INPUT`.
- v2 models use `_STRICT`. Budgets and `limit` are `StrictInt` with `ge=1` (`limit` also `le=100`). Lists use `min_length=1` with a uniqueness validator. Explicit `null` is invalid except for `cursor`.
- Add `memory_v2_request_model_keys(op)`, which must equal `tools.memory._V2_<OP>_REQUEST_KEYS`.
- Legacy `write`/`promote`/`maintain` gain an optional `request` with keys exactly equal to `_WRITE_REQUEST_KEYS`, `_PROMOTE_REQUEST_KEYS` and `_MAINTAIN_REQUEST_KEYS`. This closes the T002 item 2 gap.
- `_reject` emits the v2 error envelope (`schema_version: 2`, `items: []`, `next_cursor: null`, `complete: false`, `unknowns: []`, `data: {message, field, details}`) when `arguments.request.schema_version` is exactly integer 2.
- The published schema `operation` enum gains `history` and `explain`; `_flatten` already produces `anyOf` for differing shapes.
- Bridge: return `E_PERMISSION` when `isinstance(request, dict) and "schema_version" in request`, before `TypedArtifactStore(root)`. The operation allowlist is unchanged.

### H11. CLI (`cli.py`)

- Add `("history", "history")` and `("explain", "explain")` to the leaf loop, plus `_MEMORY_OPERATION_HELP` entries.
- `list`, `ask`, `write`, `promote` and `maintain` gain `--input FILE`. Their positional arguments become `required=False`.
- Without `--input`, a missing positional raises `click.UsageError` with Click's exact message ("Missing argument 'SUBJECT'."), exit 2, so the cli-outcomes cases still hold.
- With `--input` and positionals both given, the call is forwarded to `MemoryTool`, which rejects the mixed form with `E_INPUT`.
- `--session` together with a v2 request is also a mixed form.
- Add the `public_operations.py` entries (`"memory history"` and `"memory explain"`: `None`, `"rush.tools.memory:MemoryTool"`, `"read-only"`, `"rush memory <leaf> --help"`, `"admin"`), then regenerate the TOML.

## 4. Cross-task conflicts

1. **73-T02/POLICY (T003):** `allowed_operations` must accept the strings `history`, `explain`, `import` and every MemoryOperation name. `resolve_memory_scope(owner_scope=None)` must give a distinguishable denied reason for ambiguous owner, owner mismatch and source not a subset. The policy lock should be exported as one helper. If T003 restricts the vocabulary, T06 stops and the PM amends.
2. **72-T01 (T004):** T06 edits `evaluate_artifact_visibility` only to add the applicability and task-binding reason codes. Legacy routes keep T01's authority path. The PAS test name `test_foreign_owner_and_verified_claim_do_not_authorize` may be claimed by T01. If it already exists at T033 time, T033 writes the import-side assertions as `test_foreign_owner_and_verified_claim_do_not_authorize_on_import`, and the PM records the split.
3. **72-T02 (T005):** v2 depends on T02's admission helper, cursor primitives and `payload_hash` column. T06's migration must come after T02's in `_init_db`, and `open_readonly_view` keeps both requirements.
4. **72-T03 (T006):** `add_relation` gets refactored into `insert_relation_tx`. It must keep T03's owner and endpoint checks exactly; T06 must not weaken them.
5. **72-T05 (T008):** reuse T05's `task_id` and scope naming if present.
6. **73-T09/CODEC (T010):** it consumes H9 exactly and calls `preview_import_records` and `apply_import_records` from the `capsule` operation. It must not write rows itself.
7. **72-T07 (T011):** it migrates the dashboard and TUI forms to v2 operations and builds on the CLI leaves added here. The legacy dashboard `receipt_operation_id` flow stays working until then.
8. **Phase 70:** T28-D handlers and `MutationLedger` stay compatible (legacy kwargs untouched). **Phase 71 P07:** none in T06. **Phase 75:** consumes the same `invocation_id` (C10).
9. **Shared files:** `store.py`, `tools/memory.py` and `cli.py` have one writer at a time, per C09.

## 5. Test matrix

All tests use pytest `tmp_path` and `monkeypatch`. HOME is set to `tmp_path/"home"` and `XDG_DATA_HOME` to `tmp_path/"home/.local/share"`; then `data_root = default_data_root()`.

Grants are made with real `grant_memory_scope(..., consent=True, data_root=data_root)`:
- **Alice:** owner `{"kind":"user","id":"alice"}`; source `src-a`; operations `[list, ask, history, explain, expand, related, write, edit, archive, delete, promote, link, maintain, import]`.

Seeded records:
- Alice: `a-<subject>` for all seven subjects. Content contains `needle` for `active_context`, `failure` and `skill_pattern`; `plain` otherwise.
- Bob: `b-<subject>`, owner `{"kind":"user","id":"bob"}`, source `src-a`, content contains `needle`.

The fixture tree and DB digest are taken with `sha256` over the sorted file list and bytes.

Every RED failure must be an assertion failure or an `AttributeError`/`ImportError` raised inside the test body. Each rejection test asserts `raw["schema_version"] == 2` and `raw["data"]["field"]`, so it fails at 07775f1.

### File `tests/test_phase72_memory_public.py` (new)

| Test ID | Fixture | Action | Assertion | Expected RED failure |
|---|---|---|---|---|
| `test_t06_query_admin_permissions_and_versions` | Alice + Bob × 7 | v2 list; ask needle; edit a-failure 1→2; replay; different digest; restore; delete {a-failure:2, a-episodic:1} with a-episodic stale; promote; explain | Exactly 7 IDs; exact needle IDs; no `b-`; version 1 kept in history; same `receipt_id` and no version 3; `E_VERSION` `effect_identity_reused`; restored; both rows still present; separate candidate and decision, original unchanged; unknowns `no_recorded_rationale` | raw `schema_version` 1 / `E_INPUT` unknown key |
| `test_t06_v2_list_browse_all_subjects_exact_ids` | same | list, subjects omitted, query `""` | IDs == 7 `a-*` in subject order; `complete` true | E_INPUT |
| `test_t06_v2_ask_needle_exact_ids` | same | ask `needle` | Exactly 3 `a-*` IDs | E_INPUT |
| `test_t06_v2_explicit_bob_owner_denied` | same | list with owner Bob | `E_OWNER`; items `[]`; no `b-` anywhere in raw JSON | code ≠ E_OWNER |
| `test_t06_v2_omitted_owner_and_sources_resolve_single_grant` | same | list without owner or sources | Every `item.reference.owner_scope` is Alice and source is `src-a` | KeyError/assert |
| `test_t06_v2_ambiguous_owner_rejected` | Alice + a second grant (owner agent:x) on the same root | list without owner | `E_INPUT`, `field=owner_scope`, no items | assert |
| `test_t06_v2_invalid_sources_rejected[None\|[]\|[""]\|[1]\|["src-a","src-a"]]` | same | list | `E_INPUT`, `field=sources`, digest unchanged | assert |
| `test_t06_v2_sources_not_subset_E_SCOPE` | same | `sources=["src-z"]` | `E_SCOPE`, no items | assert |
| `test_t06_v2_no_policy_denied_no_files` | Seeded store, no grant | list, history, explain | `E_PERMISSION`; home tree and DB digest unchanged | assert |
| `test_t06_v2_budget_defaults` | Alice | list without budgets | `raw.budget.max_tokens == 2048`, `max_bytes == 8192` | KeyError |
| `test_t06_v2_invalid_budget_rejected_before_effects[field × (True,1.5,"2048",None,0,-1)]` (12 cases) | Root with no `.rush` plus a seeded root | list | `E_INPUT`, `field` matches; no `.rush` created; DB digest unchanged | assert field |
| `test_t06_v2_budget_below_admission_minimum[max_bytes=1\|max_tokens=1]` | seeded | list | `E_INPUT` with `field`; no items | assert |
| `test_t06_v2_limit_validation[0\|101\|True\|None\|"5"]` | seeded | list | `E_INPUT`, `field=limit` | assert |
| `test_t06_v2_mixed_legacy_and_v2_rejected[subject\|session_allowlist\|include_archived]` | seeded | `run(...)` with a legacy argument and a v2 request | `E_INPUT`, `field` names the legacy argument; DB digest unchanged | assert |
| `test_t06_v2_unknown_key_and_bool_schema_version_rejected` | seeded | `{"schema_version": True}` and `{"schema_version": 2, "zzz": 1}` | `E_INPUT`, `field` = `schema_version` / `zzz` | assert |
| `test_t06_empty_store_read_creates_nothing` | Grant, no DB | list, history, explain | OK / empty / `complete` true; no `.rush` | assert |
| `test_t06_history_requires_history_grant` | Grant without `history` | history a-failure | `E_PERMISSION`, no content | op unsupported |
| `test_t06_history_returns_immutable_versions` | Edit twice, then archive | history | Versions [1, 2, 3, 4] with exact content and `reference`; archive version labelled | op unsupported |
| `test_t06_historical_list_labels_exclusions` | Archived a-episodic | list active vs historical | Active excludes it; historical includes it with `exclusion_reasons` containing `archived` | assert |
| `test_t06_edit_preview_readonly_then_apply` | seeded | Edit preview; edit apply | Preview: DB digest unchanged and `request_digest` present; apply: version 2, history keeps version 1 | assert |
| `test_t06_edit_replay_same_effect_same_receipt` | seeded | Apply twice with the same `invocation_id`/`effect_id` | Same `receipt_id`; `replayed` true; current version 2 | assert |
| `test_t06_edit_same_effect_different_digest_conflict` | seeded | Second apply with other content | `E_VERSION` `effect_identity_reused`; DB digest unchanged | assert |
| `test_t06_independent_same_content_writes_distinct` | seeded | Two v2 writes, same content, different effects | Two distinct IDs persisted | assert |
| `test_t06_edit_stale_version_conflict_retains_form` | seeded | Edit with `expected_version` 9 | `E_VERSION`; `data.retained.content` == submitted; DB digest unchanged | assert |
| `test_t06_archive_restore_via_archived_false` | seeded | Archive, then archive with `archived: false` | Hidden, then visible again; versions advance | assert |
| `test_t06_delete_two_revisions_one_stale_rolls_back_both` | seeded | delete {a-failure:1, a-episodic:7} | `E_VERSION`; both rows present; DB digest unchanged | assert |
| `test_t06_promote_separate_candidate_original_unchanged` | seeded | Promote `source_id` a-domain_knowledge, `user_stated` | New candidate ID ≠ source; source content, version and trust unchanged; one transaction (2 effect rows or 1 with both kinds) | assert |
| `test_t06_correction_reject_excluded_from_recall` | seeded | Edit with `correction.kind = "reject"` | Version 2 with applicability `rejected`, content and trust unchanged; absent from ordinary list and present in historical | assert |
| `test_t06_correction_supersede_replacement_and_edge` | seeded | `supersede` | New artifact active; original version 2 `superseded`; `supersedes` edge new@1 → original@2 | assert |
| `test_t06_correction_reports_affected` | Summary row with `member_versions {a-episodic:1}` plus a `depends_on` edge | Reject a-episodic | `affected.summaries` and `affected.relations` contain exact references | assert |
| `test_t06_explain_by_id_buckets` | `contradicts` and `validated_by` edges | explain a-failure | Exact `supporting` / `contrary` references | op unsupported |
| `test_t06_explain_exactly_one_of_id_or_query` | seeded | Both / neither | `E_INPUT` | op unsupported |
| `test_t06_explain_absent_rationale_unknowns` | No edges | explain | `unknowns == [{"code":"no_recorded_rationale","artifact_id":...}]`; no free-text rationale keys | op unsupported |
| `test_t06_mutation_without_operation_grant_no_effects` | Grant lacks `edit` | Edit apply | `E_PERMISSION`; DB digest unchanged | assert |
| `test_t06_mutation_foreign_or_missing_target_not_visible` | seeded | Edit b-failure; edit `nope` | Both `E_NOT_VISIBLE` with identical `data` | assert |
| `test_t06_policy_lock_held_through_commit` | seeded | Patch `_write_effect_receipt` to start a thread running `revoke_memory_scope`, wait 0.3 s and assert the thread is alive, then continue | Apply commits; the revoke completes only after it; the next read gives `E_PERMISSION` | AttributeError |
| `test_t06_revoked_between_preview_and_apply` | seeded | Preview, revoke, apply | `E_PERMISSION`; DB digest unchanged | assert |
| `test_t06_restricted_bridge_rejects_admin_and_v2` | Seeded root plus a handoff session | Bridge with edit/delete/history/explain, and expand with `schema_version` 2 | All `E_PERMISSION`; DB digest unchanged; on an unseeded root no `.rush` is created | assert (expand passes through today) |
| `test_t06_mcp_validator_v2_variants_and_enum` | none | `validate_and_normalize` / `published_schema` | v2 list accepted; operation enum contains `history` and `explain`; v2 rejection envelope has `schema_version` 2 | assert |
| `test_t06_mcp_legacy_write_promote_maintain_request_reachable` | none | Validate legacy promote with request `{source_id, expected_version, candidate_refs}` | Accepted | rejected today |
| `test_t06_stdio_mcp_and_cli_same_refs_and_codes` | seeded; child `rush mcp serve` with env HOME / `XDG_DATA_HOME` | Same v2 list via stdio and via `CliRunner memory list --input`; invalid budget via both | `raw` equal; codes and `schema_version` equal | assert |
| `test_t06_cli_history_explain_leaves_and_list_input` | seeded | `memory history --input`; `memory explain --input`; `memory list SUBJ Q --input f` | Valid v2 raw; mixed form gives `E_INPUT` | UsageError / no such command |
| `test_t06_v2_list_pagination_exact_once_across_subjects` | seeded | limit 3, page until done | Pages 3/3/1; union == 7 with no duplicates; last page `complete`; tampered cursor gives `E_RESTART` | assert |
| `test_t06_v2_cursor_bound_to_scope` | seeded | Reuse the cursor with `sources` changed | `E_RESTART`, `data.restart` present | assert |
| `test_t06_write_v2_source_must_be_granted` | seeded | write `source=src-z` | `E_SCOPE`, no row | assert |
| `test_t06_link_v2_foreign_endpoint_not_visible` | seeded | link a-failure → b-failure | `E_NOT_VISIBLE`, no relation row | assert |
| `test_t06_maintain_v2_scoped_to_grant_owner` | Duplicate candidates for both owners | maintain preview | Candidate IDs are Alice-only | assert |
| `test_t06_expand_related_v2_respect_grant` | seeded | Expand / related on b-failure | `E_NOT_VISIBLE` | assert |
| `test_t06_items_carry_reference_fields` | seeded | list | Each item's `reference` has the exact key set listed in section 1 item 7 | KeyError |

### File `tests/test_memory_public_contract.py` (extend; new IDs only)

| Test ID | Action | Assertion |
|---|---|---|
| `test_t06_legacy_and_v2_list_coexist_same_ids` | Legacy list with `session_allowlist`, then v2 list | Legacy raw is a schema-1 list; v2 IDs are the same set |
| `test_t06_legacy_edit_then_v2_history_versions_agree` | Legacy edit with `receipt_operation_id`, then v2 history | Versions [1, 2]; legacy receipt still retrievable |
| `test_t06_new_cli_leaves_in_public_manifest` | `build_operations_inventory` | `memory history` / `memory explain` present, `canonical_impl` MemoryTool, `kind` admin |
| `test_t06_cli_mcp_v2_payload_match_inprocess[edit\|history\|explain]` | `_mcp_call` / `_cli_call` on twin roots | Normalized raw equal, excluding `project_id`/`worktree_id` and receipt IDs |
| `test_t06_mutation_receipts_columns_and_dashboard_ids` | Dashboard `_dispatch_memory_edit` with reserved ID | `PRAGMA table_info(mutation_receipts)` includes the five new columns; `get_receipt(reserved)` is not None |

Each of these fails at RED: no v2, no `history`, no new leaves, no new columns.

### File `tests/test_phase72_portable_memory_policy.py` (create, or extend if T01 created it; new IDs only)

All rows use canonical record fixtures built directly against the store, with real `grant_memory_scope` and `resolve_memory_scope(operation="import")`.

| Test ID | Assertion |
|---|---|
| `test_foreign_owner_and_verified_claim_do_not_authorize` (or the `_on_import` name per section 4.2; PM verified-by: grep matched plan line 471, the required §8 case list) | `claimed {trust_tier: STATED, status: verified, owner: bob}` is stored with trust `IMPORTED`, owner Alice from the grant, and freshness not current; it is absent from ordinary recall when anchored |
| `test_imported_constraint_needs_local_applicability_review` | A constraint is `pending` and absent from ordinary recall; v2 promote with `user_stated` creates a new active candidate; the original stays pending and unchanged; claimed test outcomes are not copied into the candidate |
| `test_preview_no_files_then_atomic_apply` | Preview on a root with no DB creates no files and returns the binding; apply creates every row plus one receipt |
| `test_changed_capsule_policy_and_artifact_version_conflict` | Changed digest under the same effect gives `E_VERSION`; a revision bump gives `E_VERSION` (`policy_changed`); a changed collision version gives `E_VERSION` (`artifact_changed`); DB digest unchanged in each case |
| `test_replay_and_distinct_import_identity` | Same identity returns the same mapping (`replayed`); a new `effect_id` gives `collision_unresolved`; a new digest gives distinct new local IDs that never equal the foreign IDs |
| `test_t06_import_crash_before_commit_no_rows_or_receipt` | Patching `_write_effect_receipt` to raise leaves 0 import rows and no receipt |
| `test_t06_import_never_evicts_local_stated_same_symbol` | A local STATED row with the same `symbol_ref` survives |
| `test_t06_import_rejects_trojan_content_zero_writes` | `E_INPUT` naming the `foreign_origin_id` |
| `test_t06_import_record_schema_strict[unknown_key\|missing_foreign_id\|decision_subject_evidence_kind\|duplicate_id]` | `E_INPUT` |
| `test_t06_import_policy_lock_held_through_commit` | A revoke thread is blocked until commit |

Expected RED failure for every row: `AttributeError` on `preview_import_records` / `apply_import_records` / `_write_effect_receipt`.

Plan §8 PAS cases assigned elsewhere:
- `test_export_personal_scope_and_required_secret_redaction` → 73-T09/CODEC.
- `test_import_review_cli_tui_dashboard_same_state` → 72-T07.

## 6. Worker packages

These are the same packages carried in the receipt's `worker_package` field in part (B); the receipt copies are authoritative.

### Embedded decisions taken (flagged, plan-consistent; not owner decisions)

- **FD1:** Grant operation vocabulary is the MemoryOperation names plus `history` and `import`.
- **FD2:** Omitted `subjects` means all seven.
- **FD3:** The CLI `--input` route on `list`/`ask`/`write`/`promote`/`maintain`.
- **FD4:** Explain bucket-to-relation-kind mapping (H8).
- **FD5:** Confirming an imported constraint is v2 `promote` and leaves the original pending (the plan's "existing review/promotion semantics").
- **FD6:** v2 mutation identity uses top-level `invocation_id` plus `request.effect_id`, and replay returns the stored result with `replayed: true`.
- **FD7:** A supersede edge targets the original's new superseded version, so T03 traversal currency holds.

---

# (B) Receipt

```json
{
  "goalbuddy_receipt_v1": {
    "result": "done",
    "task_id": "T009",
    "board_path": "/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/docs/goals/phase-72-memory-correctness/state.yaml",
    "decision": "approved",
    "full_outcome_complete": false,
    "rationale": "72-T06 is fully mapped at 07775f1 and ready to implement. The packet's 4 files are not enough. The MCP strict validator cannot reach write/promote/maintain requests. Adding the history and explain operations breaks hard-coded operation counts in test_phase70_t6, test_phase70_t20 and test_phase54. The new CLI leaves need governance manifest and T27 matrix entries. cli.py is required for CLI parity. The design gives an exact v2 request/result, error mapping, a policy-then-store transaction with effect-identity receipts, corrections and applicability, history, explain, and an exact apply_import_records/preview_import_records contract for the CODEC gate. The tests cover 5 PAS cases plus 48 public and 5 contract rows.",
    "worker_package": {
      "red": {
        "objective": "Write the T009 section 5 test matrix for 72-T06 against the current HEAD. First re-check the section 0 drift table (authorization.py signatures from 73-T02; evaluate_artifact_visibility from T01; the cursor and admission helpers from T02; add_relation from T03). Then prove by execution that every new test fails individually. Import not-yet-existing symbols inside test bodies.",
        "allowed_files": [
          "tests/test_phase72_memory_public.py",
          "tests/test_memory_public_contract.py",
          "tests/test_phase72_portable_memory_policy.py"
        ],
        "verify": [
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -c \"import subprocess,sys; r=subprocess.run([sys.executable,'-m','pytest','tests/test_phase72_memory_public.py','tests/test_memory_public_contract.py::test_t06_legacy_and_v2_list_coexist_same_ids','tests/test_memory_public_contract.py::test_t06_legacy_edit_then_v2_history_versions_agree','tests/test_memory_public_contract.py::test_t06_new_cli_leaves_in_public_manifest','tests/test_memory_public_contract.py::test_t06_cli_mcp_v2_payload_match_inprocess','tests/test_memory_public_contract.py::test_t06_mutation_receipts_columns_and_dashboard_ids','tests/test_phase72_portable_memory_policy.py::test_foreign_owner_and_verified_claim_do_not_authorize','tests/test_phase72_portable_memory_policy.py::test_imported_constraint_needs_local_applicability_review','tests/test_phase72_portable_memory_policy.py::test_preview_no_files_then_atomic_apply','tests/test_phase72_portable_memory_policy.py::test_changed_capsule_policy_and_artifact_version_conflict','tests/test_phase72_portable_memory_policy.py::test_replay_and_distinct_import_identity','tests/test_phase72_portable_memory_policy.py::test_t06_import_crash_before_commit_no_rows_or_receipt','tests/test_phase72_portable_memory_policy.py::test_t06_import_never_evicts_local_stated_same_symbol','tests/test_phase72_portable_memory_policy.py::test_t06_import_rejects_trojan_content_zero_writes','tests/test_phase72_portable_memory_policy.py::test_t06_import_record_schema_strict','tests/test_phase72_portable_memory_policy.py::test_t06_import_policy_lock_held_through_commit','-q','-p','no:cacheprovider'],capture_output=True,text=True); print(r.stdout[-4000:]); s=(r.stdout.strip().splitlines() or [''])[-1]; sys.exit(0 if r.returncode==1 and ' failed' in s and not any(w in s for w in (' passed',' skipped',' error',' xfail',' xpass')) else 1)\"  # if T01 already owns test_foreign_owner_and_verified_claim_do_not_authorize, substitute ...::test_foreign_owner_and_verified_claim_do_not_authorize_on_import"
        ],
        "stop_if": [
          "authorization.py is absent, or resolve_memory_scope/grant_memory_scope signatures differ from Phase 73 plan L123.",
          "evaluate_artifact_visibility, or T02's cursor/admission helpers, are absent at HEAD.",
          "A test cannot be made to fail for a T06-specific reason (it would pass at HEAD).",
          "Files outside allowed_files are needed.",
          "Verification fails twice."
        ]
      },
      "implement": {
        "objective": "Implement 72-T06 exactly per T009 section 3 (H1-H11) until every T033 RED test passes. Also update the existing contract-count tests and regenerate governance/public-operations.toml with scripts/build_remediation_manifests.py --operations. Dispatch on Opus (trust boundary). Do not edit RED tests.",
        "allowed_files": [
          "src/rush/tools/memory.py",
          "src/rush/memory/store.py",
          "src/rush/memory/retrieval.py",
          "src/rush/memory/relations.py",
          "src/rush/mcp_support/request_models.py",
          "src/rush/mcp_support/tool_registry.py",
          "src/rush/cli.py",
          "src/rush/governance/public_operations.py",
          "governance/public-operations.toml",
          "tests/fixtures/phase70/cli-outcomes.json",
          "tests/test_phase70_t6.py",
          "tests/test_phase70_t20.py",
          "tests/test_phase54_operation_adapters.py"
        ],
        "verify": [
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_memory_public.py tests/test_memory_public_contract.py tests/test_phase61_memory_tool.py tests/test_mcp.py -q -p no:cacheprovider",
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_portable_memory_policy.py -q -p no:cacheprovider",
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase70_t6.py tests/test_phase70_t20.py tests/test_phase54_operation_adapters.py tests/test_phase51_public_operations.py tests/test_phase70_t27.py tests/test_memory_handoff.py tests/test_memory_versions.py tests/test_memory_relations.py tests/test_memory_consolidation.py tests/test_phase60_characterization.py -q -p no:cacheprovider",
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/ -q -m '' -p no:cacheprovider  # no failure beyond the T001 baseline, zero SKIPPED",
          "rtk proxy uv run --python 3.12 --extra dev ruff check src tests scripts",
          "rtk proxy uv run --python 3.12 --extra dev ruff format --check src tests scripts",
          "rtk proxy uv run --python 3.12 --extra dev mypy src/rush",
          "rtk proxy git diff --check",
          "rush_check on changed files"
        ],
        "stop_if": [
          "A needed file is outside allowed_files (the PM amends with gate-note justification).",
          "The 73-T02 operation vocabulary or denied-reason vocabulary cannot express history/explain/import or ambiguous/owner/source denial (section 4.1).",
          "T03's add_relation cannot be split into insert_relation_tx without weakening its checks.",
          "A legacy route's output or authority would need to change to pass.",
          "A RED test appears defective (return it to the PM; never edit it).",
          "After fix round 2 the PM finishes directly."
        ]
      }
    },
    "owner_decisions_needed": [],
    "evidence": [
      "graft skeleton src/rush/tools/memory.py, src/rush/memory/store.py, src/rush/mcp_support/request_models.py and tool_registry.py (all line numbers cited in note section 2)",
      "graft callers --depth all for _compact_query, _list_filtered, _edit_or_archive, _run_promote, build_memory_bridge_handler, validate_and_normalize and _write_receipt",
      "Executed .venv python: len(VALID_OPERATIONS)==22 and memory_model_tags()==VALID_OPERATIONS; validate_and_normalize rejects write+request and list request.schema_version (extra_forbidden), rejects promote request, accepts compact max_bytes=0",
      "tests/test_phase70_t6.py:220-221 (module-level count assert), test_phase70_t20.py:866-871, test_phase54_operation_adapters.py:118-126 (194 total / 95 admin), test_phase51_public_operations.py:101 (toml regeneration), test_phase70_t27.py:644/1002 (matrix equals live registry)",
      "store.py:550 mutation_receipts (INSERT OR REPLACE at L1114); _prepare_write L2122 evicts a STATED symbol conflict; promote_stored_artifact L2771 is connection-level",
      "Phase 73 plan L123 gives the exact C01 signatures; contract C01 L42 gives the lock identity and order; C10 L162 gives invocation_id as a UUID",
      "Disk 20 GiB free before work"
    ],
    "subgoal_contract": null,
    "parallel_safety": null,
    "blocked_tasks": [],
    "missing_evidence": [
      "T003/T004/T005/T006/T008 gate notes do not exist yet; the section 0 assumptions must be re-checked by T033 at HEAD",
      "No tests were executed for the design (read-only gate; full suite running elsewhere)"
    ],
    "required_board_updates": [
      "T033.allowed_files and verify replaced by worker_package.red",
      "T034.allowed_files expanded to the 13 files in worker_package.implement; verify replaced",
      "T003 card: add constraint that allowed_operations must accept history, explain, import and all MemoryOperation names, with distinct denied reasons (no_policy, no_grant, revoked, expired, operation_not_allowed, owner_mismatch, source_not_subset, ambiguous_owner) and one exported policy-lock helper",
      "T004 card: record the PAS test-name ownership rule for test_foreign_owner_and_verified_claim_do_not_authorize",
      "T010 card input: note section 3 H9 is the binding apply_import_records/preview_import_records contract"
    ],
    "summary": "T06 approved with a corrected scope. It needs 13 implementation files, not 4. cli.py is required, plus retrieval.py, relations.py, the governance manifest and generator, the T27 matrix, and three existing count tests that adding history and explain would break. The note fixes the strict v2 request/result, error codes, the policy-then-store transaction with idempotent effect receipts, corrections and applicability, history, explain, and an exact import seam for the CODEC gate. The test matrix has 48 public, 5 contract and 10 import tests. No owner decisions are needed; 7 embedded choices are flagged.",
    "note": "notes/T009-design-gate-72-t06.md"
  }
}
```

## PM amendment (2026-10-05): T010 A1-A6

The T010 CODEC gate requires these changes to this unit's packages. They override FD1 and its fixtures where they conflict.

- A1 apply_import_records gains expected_store_revision:int, compared with store_generation(conn) after the replay lookup; mismatch gives E_VERSION store_changed; included in the digest
- A2 gains confirm_foreign_ids: Sequence[str]=(), a subset of the constraint-kind IDs; in the same transaction it applies FD5 (new local active candidate and decision; original stays pending; claimed outcomes not copied); mapping reports confirmed_local_id; included in the digest
- A4 the H9 step-2 re-resolve uses operation='write' (T003 GRANT_OPERATIONS has no 'import'); fixtures grant only T003 operations, never 'import' or 'explain'
- A5 preview_import_records adds store_state and store_revision from the same read-only snapshot
- A6 the binding accepts an optional preview_digest stored in the receipt; add read-only find_import_effect_readonly(project_root, invocation_id, effect_id) -> dict|None that creates nothing.
