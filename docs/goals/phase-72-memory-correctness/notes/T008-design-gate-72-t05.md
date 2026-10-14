# T008: Design gate for 72-T05, recorded verbatim from the goal-judge report

Below the line is the goal-judge's T008 report, copied unchanged.

## PM re-checks (run on 07775f1)

`PreferenceStore(root)` creates `root/.rush` when it is constructed. A TemporaryDirectory probe printed `ctor creates .rush: True`, which supports the gate's probe 1.

verified-by: `.venv/bin/python` probe constructing `PreferenceStore` in a temporary project directory.

Pending owner decisions OD-1 (what counts as user confirmation) and OD-2 (legacy preference authority) gate T030.

Not re-run by the PM: the rest of the report. The T030 RED author re-checks the code map at HEAD (stop_if).

---

# T008 judge report: design gate for 72-T05 (consented layered preferences and migration)

**Decision: approved, with conditions.** T030 must not start until the PM gets the owner's answers to OD-1 and OD-2 (below). I edited no files. The PM writes the note body below to `docs/goals/phase-72-memory-correctness/notes/T008-design-gate-72-t05.md` in `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72`.

---

## (A) Note body: `notes/T008-design-gate-72-t05.md`

# T008: Design gate for 72-T05 (consented layered preferences and migration)

Worktree `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72`. Product bytes are `07775f1`; HEAD `17f7645` adds board docs only. This gate is read-only and was written by a goal-judge agent.

### Probes run on 07775f1

All probes ran with `.venv/bin/python` inside `TemporaryDirectory`. No HOME was created.

1. **The `PreferenceStore` constructor creates `.rush/`.** It also creates a missing project root, through the `CASMapTransaction` constructor's `mkdir`.
2. **`PreferenceStore.get` creates `.rush/memory.db` on a read.** The call chain is `read_origin` → `TypedArtifactStore(project_root)`.
3. **A second migration overwrites the existing `.migrated` backup.** `Path.rename` replaces it on POSIX. The probe printed `backup overwritten: True`.
4. **A hard-deleted migrated row comes back on replay.** Sequence: `migrate` → `store.delete(id)` → `migrate` again. The replay returned 1 and the origin row was back. `mutation_receipts` held 0 rows, so no migration record exists.
5. **Migration is not one transaction.** `migrate_preference_store` (`migration.py:297-320`) calls `write_if_new` once per key, and each call commits separately.

### Scope

72-T05 delivers four things:
- project, task and personal preference layers with precedence;
- a personal overlay that needs its own consented grant;
- a reversible, replay-safe migration from `.rush/preferences.json`;
- one public MemoryTool `preference` operation.

72-T05 does **not** deliver:
- CLI, TUI or dashboard preference surfaces. Those belong to 72-T07 and depend on OD-1.
- Policy writers. Those belong to 73-T02/POLICY.
- Row-level `applicability`/`task_binding` columns and the canonical correction transaction. Those belong to 72-T06.

### Owner decisions (PM gets these before T030)

**OD-1: what counts as user confirmation for an "explicit" preference?** This also decides which surfaces can write personal or explicit rules.
- **(a) Plan-literal; the design below assumes it.** Explicit means the record is STATED through `promote_stored_artifact(user_stated=True)`, and its `corroboration_count` is 0. Writes need all of: `user_stated: true`, `apply: true`, the `cache_write` permission and a policy `write` grant for the destination owner. These writes can be reached through MCP and in-process calls, the same way `promote` works today. C01 makes no isolation claim against processes running as the same OS user.
- **(b) CLI-only.** Explicit records, personal writes and corrections of explicit rules go only through a new CLI leaf. MCP `preference` keeps `resolve` plus inferred `record`.
  - Extra files: `src/rush/cli.py`, `src/rush/governance/public_operations.py`, a regenerated `governance/public-operations.toml`, the counts in `tests/test_phase54_operation_adapters.py`, `src/rush/theme.py`, the T27 matrix, and the parity lists in `tests/test_memory_public_contract.py`.
  - This follows the 73-T06 precedent of a CLI-only `delta-source` route.

**OD-2: how do legacy un-promoted preferences rank in layered resolution?** These are migrated `.rush/preferences.json` values and values set with `rush context persona --set`.
- **(a) The design default.** They are advice until the user confirms them with a user-stated promotion. This follows "inference cannot promote itself" and "timestamps alone cannot manufacture approval".
- **(b)** They are explicit project preferences.
- The legacy `PreferenceStore.get`/`list_all` behaviour is unchanged either way.

## 1. Testable behavior

1. **Precedence.** Instruction hierarchy and authority are checked before scope. Only explicit records can be `selected`. Among applicable explicit records, task beats project, and project beats personal. Inferred records are only ever returned under `advice`, and never replace an explicit record at any scope.
2. **Same-scope conflict.** Two active explicit records in the same layer with different values give `status="unresolved"`, `selected=None` and `conflicts` listing both. Neither newer timestamps nor a `link` edge between them resolves it. Only a correction (`supersede`, `reject` or `correct`) does.
3. **Overlay needs its own grant.**
   - The overlay is read only when `resolve_memory_scope(project_root=root, operation="overlay_read", owner_scope=user_overlay_owner_scope(data_root=dr), requested_sources=[PERSONAL_PREFERENCE_SOURCE])` grants read.
   - A project grant alone gives `layers.personal.state="disabled"` and project-only results.
   - Revoked gives `"revoked"`, expired gives `"expired"`, and any other denial gives `"denied"`. In every non-granted case the overlay DB is never opened.
4. **The project layer is required.** If the project read resolves to denied, the result is `status="denied"` with that reason. No values come back and the overlay is never consulted.
5. **Recheck per call and before delivery.** Each resolve call re-resolves both grants. After the result is assembled, the module seam `_before_delivery()` runs and both grants are resolved again.
   - If `policy_revision` or access changed, the result is recomputed (at most 2 retries). After that it returns `status="restart"`.
   - A grant revoked mid-call never leaks values from the old scope.
6. **No cross-project or foreign leakage.**
   - A row owned by another owner in this project's store never appears: no value, ID, count or existence.
   - Another project's store is never opened.
   - A host or session attribution string never changes selection or access.
7. **Task binding.**
   - A task record applies only when its content `task_id`, `project_id` and `worktree_id` all equal the request's `task_id` and the resolved grant's `project_id`/`worktree_id`, and it has neither `ended_at` nor an `expires_at <= now`.
   - `end_task` excludes only that task's records.
8. **No upward copy or auto-import.**
   - Project and task writes never touch the overlay.
   - Personal rows are never copied into project DBs.
   - Nothing is imported from native host memory: `~/.claude/*`, `~/.codex/*` or `user/.rush/agent_memory.json`.
9. **Write rules.**
   - Inferred personal records are rejected with `E_INPUT/inferred_personal_forbidden`.
   - An explicit record without `user_stated` is rejected with `E_INPUT/explicit_requires_user_stated`.
   - Correcting an explicit record without `user_stated` is rejected with `E_INPUT/explicit_correction_requires_user_stated`.
10. **Corrections keep history.**
    - Reject, supersede and correct each keep the original version, its source, the reason, and an `affected` list of exact references to relations and summaries.
    - A stale `expected_version` returns `E_VERSION` with no effects, and the original version stays intact.
11. **Reads create nothing.** This covers the constructor, `get`, `list_all`, `resolve`, the MemoryTool `resolve` action and every preview. None of them creates a project root, `.rush`, `memory.db`, `-wal`/`-shm` files, the data root, `user/`, the policy file, or lock directories.
12. **Migration.**
    - All of a source's rows are written in one `BEGIN IMMEDIATE` transaction, together with a receipt `preference-migration:<sha256(source bytes)>`.
    - Counts and contents are checked before the backup rename.
    - An existing backup is never overwritten.
    - If the source changed since it was read, it is not renamed.
    - Replaying the same source changes 0 rows.
    - A deleted key (soft or hard delete) never comes back.
    - If the migration fails, the original file is untouched.

## 2. Code and caller map (07775f1)

**Edited by T05:**

| Symbol | Location | Role / callers |
|---|---|---|
| `PreferenceStore` | `src/rush/memory/preference_store.py:18-94` | Production caller: `cli.py:5562-5579` `context_persona_cmd` (`set`). Tests: `test_phase58_map_transactions.py:31,62,135` (uses `pref.tx.read()`; a corrupt file must still raise `StoreCorruptionError`); `test_phase53_state_writers.py:92,216`; `test_phase58_persistence.py:32`; `test_phase41_memory_ship.py:31`; `test_memory_compatibility_regressions.py:51,121,153`; `test_phase61_migration.py:43,220-221`; `test_cli_runtime_bindings.py:51` |
| `get_preference_readonly` | `preference_store.py:97-110` | `cli.py:5578` |
| `migrate_preference_store` | `src/rush/memory/migration.py:297-320` | Tests only: `test_memory_compatibility_regressions.py:50-168`, `test_phase61_migration.py:39-57` (asserts `.migrated` exists), `:218-238` (idempotent) |
| `_rename_migrated`, `_read_map_source` | `migration.py:276`, `:280` | Called by migration only |
| `MemoryOperation`, `VALID_OPERATIONS`, `run` dispatch, `_CODE_STATUS`, `_envelope_result`, `_WRITE_PERMISSION` | `src/rush/tools/memory.py:72`, `:98`, `:401-630`, `:139`, `:1406`, `:129` | Adds the `preference` operation |
| `_action_union`, `_REQUEST_MODELS`, `_NESTED_ACTIONS`, `MEMORY_FIELDS`, `memory_model_tags` | `src/rush/mcp_support/request_models.py:383`, `:398`, `:484`, `:543`, `:714` | The strict MCP model for `preference` |
| Operation-count tests | `tests/test_phase70_t6.py:220-221` (module-level 22 + set equality), `:300`, `:786`; `tests/test_phase70_t20.py:866-871` (`len == 22`) | Become 23 |

**Reused, not edited:**
- `store.py`:
  - `OwnerScope` `:249`, `legacy_owner_scope` `:290`, `owner_scope_for_row` `:309`, `MemoryArtifact` `:324` (has `corroboration_count`, `owner_scope`)
  - `_write_version` `:630`, `_row_to_artifact` `:722`
  - `TypedArtifactStore.__init__` `:952-960` (mkdir + `MerkleInvalidator` → `.rush/cache`)
  - `_write_receipt` `:1103`, `get_receipt` `:1127`, `scope_artifacts` `:1230`, `edit` `:1435` (demotes STATED→DERIVED), `get_version_content` `:1684`, `_require_owner` `:1780`, `open_readonly_view` `:1844`
  - `_find_stated_conflict` `:2044` (evicts only when `symbol_ref` is set), `_prepare_write` `:2122`, `_insert_row` `:2167`, `write` `:2214`, `promote` `:2553`, `promote_stored_artifact` `:2771`
  - tables `memory_relations` `:466`, `mutation_receipts` `:550`
- `trust.py`: `evaluate_promotion` `:149` (user_stated gives STATED with corroboration 0; corroboration ≥2 gives STATED), `count_corroboration` `:130`, `default_entry_tier` `:60`.
- `relations.RELATION_KINDS` `:32`, which includes `supersedes`, `contradicts` and `depends_on`.
- `consolidation` stores summary `member_versions` (`:104`).
- `setup/provision.py:124` `default_data_root`, used unchanged.
- `workflows/projects.py:413` `register_project`, which writes `.rush/` descriptor files into the project.
- `tests/conftest.py`: a real-HOME guard (`:597`) and `posix_only`/`windows_only` deselection (`:53-131`).

**Symbols from earlier units that T05 depends on.** The RED author re-checks these for drift.
- **73-T02/POLICY** (`rush.memory.authorization`, per T003 §3): `resolve_memory_scope`, `load_policy_readonly`, `grant_memory_scope`, `revoke_memory_scope`, `hold_policy_lock`, `user_overlay_owner_scope`, `MemoryPolicyError`, `GRANT_OPERATIONS`.
  - The resolve result keys are `{access, reason, operation, grant_id, grant_revision, policy_revision, project_id, worktree_id, project_root, owner_scope, approved_sources, allowed_operations, session_binding}`.
  - The overlay grant must be allowed to carry `["overlay_read","write"]`.
- **72-T01**: `retrieval.evaluate_artifact_visibility(store, artifact, *, access, mode="ordinary", now=None, memo=None)` → `VisibilityDecision{visible, usable_as_current, freshness, reason_codes, reference}`.
- **72-T02**: any signature change to `_write_version`/`_insert_row` (`payload_hash`). T05 writes only through these helpers, so it picks the change up.
- **72-T03/T04**: relation and maintenance owner scoping. Maintenance corroboration can still produce STATED with count ≥2, which T05 treats as inferred.

**Not edited:** `authorization.py`, `retrieval.py`, `relations.py`, `cli.py` (under OD-1(a)), `provision.py`.

## 3. Design of the hard parts

### H1. Constants and API (`preference_store.py`)

```python
PERSONAL_PREFERENCE_SOURCE = "personal-preferences"
PROJECT_PREFERENCE_SOURCE = "project-preferences"
LEGACY_PREFERENCE_SOURCE = "migration:preference_store"
class PreferenceError(Exception): code: str; reason: str | None
def _before_delivery() -> None: ...   # test seam, no-op
class PreferenceStore:
    def __init__(self, project_root: Path | None = None, *, data_root: Path | None = None) -> None
    tx  # functools.cached_property; built lazily on first writer use
    get/set/delete/list_all  # legacy key/value API, unchanged semantics
    def resolve(self, key: str | None = None, *, query: str | None = None, task_id: str | None = None, owner_scope: OwnerScope | None = None, now: float | None = None) -> dict
    def record(self, key: str, value: Any, *, scope: Literal["personal","project","task"], authority: Literal["explicit","inferred"], task_id: str | None = None, expires_at: float | None = None, user_stated: bool = False, attribution: dict[str,str] | None = None, owner_scope: OwnerScope | None = None) -> dict
    def correct(self, artifact_id: str, *, store: Literal["project","personal"], kind: Literal["reject","supersede","correct"], reason: str, expected_version: int, value: Any = _MISSING, user_stated: bool = False, owner_scope: OwnerScope | None = None) -> dict
    def end_task(self, task_id: str, *, owner_scope: OwnerScope | None = None) -> dict
```

- The data root is `Path(self.data_root or default_data_root()).resolve()`. `DataRootUnavailableError` gives `status="denied"`, `reason="data_root_unavailable"`.
- Exactly one of `key` and `query` must be given; otherwise `E_INPUT`.

### H2. Content schema

Scoped rows are `subject="preference"`, `family="memory"`, `symbol_ref=None`. `symbol_ref` stays `None` so STATED-conflict eviction can never delete an original. `origin_kind` and `origin_id` are `None`, so legacy `read_origin(...,"preference",key)` never sees scoped rows.

Content fields:

```
{key, value, scope, authority, applicability: "active"|"rejected"|"superseded",
 task_id, project_id, worktree_id, expires_at, ended_at, attribution, correction, supersedes: [{artifact_id, artifact_version}]}
```

- **Legacy rows** (`origin_kind=="preference"` with no `scope` key) are treated as project scope and skipped when the content is `{"deleted": true}`.
- **Store match.** A row whose scope does not match its store is ignored with reason `scope_store_mismatch`. A personal row must be in the overlay; project and task rows must be in the project store.
- **Sources and owners on write.** Project and task rows use `PROJECT_PREFERENCE_SOURCE` and the write grant's owner. Overlay rows use `PERSONAL_PREFERENCE_SOURCE` and `user_overlay_owner_scope(data_root=dr)`.

### H3. Authority classification

A record is **explicit** only if all four hold:
1. its content `authority` is `"explicit"`, or absent on a legacy row (subject to OD-2);
2. `trust_tier == "STATED"`;
3. `corroboration_count == 0`;
4. it passes T01 integrity.

Everything else is **inferred** and carries a reason: `content_inferred`, `unconfirmed` or `corroborated`. Because `edit` demotes, any content change removes explicit status until the record is re-promoted. Attribution (host/session) is never consulted.

### H4. Resolve algorithm (read-only)

1. Resolve the project grant: `resolve_memory_scope(project_root=root, operation="ask", owner_scope=owner_scope, data_root=dr)`. If it is denied, return `{"status":"denied","reason":r,"selected":None,...}` with no values.
2. Resolve the overlay grant: `operation="overlay_read"` with the explicit overlay owner and `[PERSONAL_PREFERENCE_SOURCE]`.
3. Read the project rows:
   - `view,state = TypedArtifactStore.open_readonly_view(root)`. A non-None `state` makes the project layer state that value, with no values.
   - `view.scope_artifacts("preference", source_allowlist=proj["approved_sources"], scan_offset=...)` loops in 512-row batches.
   - Each row goes through `_row_to_artifact`, then `evaluate_artifact_visibility(view, a, access=proj, mode="ordinary", now=now, memo=memo)`. Keep rows that are `visible` and either `usable_as_current`, or whose `reason_codes ⊆ {"rejected","superseded"}`; that second case only arises after T06.
4. Read the overlay rows only if overlay access is `read`, from `open_readonly_view(dr/"user")` with `access=ov`. A missing DB means an enabled but empty layer.
5. Work out each row's effective applicability: `getattr(a, "applicability", None)` if it is non-null and not `active` (the T06 column), otherwise the content `applicability`. Exclude expired, ended, wrong-task, wrong-project and wrong-worktree task rows, and `deleted` rows.
6. Group by `key`. In key mode, take that key. In query mode, take keys whose normalized text contains every query token. Normalization: casefold, split on non-alphanumerics, and strip a trailing `s` when the token is longer than 3 characters. The text is the key, `json.dumps(value)` and `correction.reason`.
7. Pick the layer: the highest layer (task > project > personal) that has at least one explicit active record.
   - One distinct value: `status="selected"`. `why` is one of `task_over_project`, `project_over_personal`, `only_layer`. Explicit records in lower layers are listed under `overridden`.
   - More than one distinct value: `status="unresolved"` with `conflicts`.
   - No explicit record anywhere but inferred ones exist: `status="advice_only"`.
   - Otherwise: `status="none"`.
   - Inferred records always go under `advice`. Explicit rejected records go under `rejections` as `{value, reason, ref}`; unconfirmed rejections go under `advice`.
8. Close the views, call `_before_delivery()`, re-resolve both grants, and compare access and `policy_revision`. If they differ, recompute (at most 2 retries); after that return `status="restart"`.

**Result keys:** `status`, `reason`, `key`/`query`, `selected` (`{value, ref, why}`), `matches` (query mode: a list of per-key results), `conflicts`, `overridden`, `advice`, `rejections`, `layers: {task, project, personal: {state, reason}}`, `policy_revision`, `migration_pending` (from a non-creating `lstat` of `.rush/preferences.json`).

**`ref`:** `{artifact_id, artifact_version, store: "project"|"personal", owner_scope, source, scope, task_id}`. It never contains a root path.

### H5. Writers (`record`, `correct`, `end_task`)

**Order of steps:**
1. Validate pure inputs (`E_INPUT`).
2. Pre-check the grant with a read-only resolve (`operation="write"`, destination owner, destination source). If it is denied, return `E_PERMISSION` having created nothing.
3. Under `with hold_policy_lock(data_root=dr):` re-resolve the grant (the authoritative check). Open the writer store, run one `BEGIN IMMEDIATE` and commit. This keeps C01's lock order: policy, then store.
4. After commit, call `note_committed_write` for each version written.

**`record`:**
- Insert v1 through `_prepare_write` + `_insert_row`. The entry tier is `default_entry_tier("local_tool")`.
- For explicit records, also call `promote_stored_artifact(conn, id, project_root=store.project_root, user_stated=True, expected_version=1)` to make v2 STATED. If that call is denied (screen, regex or schema), roll back and return `E_INPUT/<denial_reason>`.
- Task scope requires `task_id`; other scopes forbid it.
- `project_id`/`worktree_id` come from the resolved grant. They are `None` for personal records.

**`correct`:**
- Read the row inside the transaction. If it is missing, has the wrong subject, or has the wrong owner, return `E_NOT_VISIBLE`; these cases cannot be told apart. A version mismatch returns `E_VERSION` with zero effects. A row that is not active returns `E_INPUT/not_active`.
- **reject:** write v(n+1) with content `applicability:"rejected"` and `correction {kind, reason, at, of:{artifact_id, artifact_version:n}}`. Demote it exactly as `edit` does (UPDATE content, version and trust; set signature and `promoted_at` to NULL). If `user_stated`, promote it to v(n+2).
- **supersede** (needs `value`):
  1. Write the original at v(n+1) with `applicability:"superseded"` and `correction.superseded_by:{new_id, 2}`.
  2. Insert the replacement at v1 with `supersedes:[{orig, n+1}]`, the same scope, and authority explicit if `user_stated` (otherwise inferred), then promote it to v2.
  3. Insert a `memory_relations` row: `(new,2) -supersedes-> (orig,n+1)`, `origin_ref="preference-correction"`.
- **correct:** write v(n+1) with the new value and `correction{kind:"correct", reason, previous_version:n}`. If `user_stated`, promote it to v(n+2).
- **`affected`** lists `{relations: [edges where source_id or target_id = id], summaries: [rows whose content member_versions contains id]}`.

**`end_task`:** append `ended_at=now` to every active, owner-matched task row with this `task_id`, `project_id` and `worktree_id`. This demotes them like `edit`.

**Exact versions the tests pin:**
- Explicit record: v2, STATED, corroboration 0.
- Inferred record: v1, EXTERNAL_WRITE.
- User-stated reject of v2: v3 DERIVED then v4 STATED.
- Supersede of v2: original at v3, replacement at v2, edge from new@2 to orig@3.

### H6. Legacy API and file creation

- The constructor creates nothing.
- `_read()` returns `{}` when `.rush/preferences.json` does not `lexists`. Otherwise it uses a CAS read, so a corrupt file still raises.
- `get`, `list_all`, and the existence checks inside `set`/`delete` use `read_origin_readonly` and `read_origin_kind_readonly`.
- `set` writes through the lazily built `tx`. `AtomicFile` creates `.rush/` when it writes. `_update_migrated` keeps its writer path.

**What writes create:**
- `set`: `preferences.json`.
- `record`/`correct`/`end_task`: only the destination store (`root/.rush/memory.db` plus `cache`, or `dr/user/.rush/memory.db` plus `cache`) and the policy lock directory, and only after the pre-check grants access.
- Migration: the project `memory.db` plus the rename.

### H7. Migration

`migrate_preference_store(project_root) -> int` keeps its signature and return value.

**Why it takes no policy lock.** It is the legacy same-store, same-owner absorption route; T01's legacy-path rule covers it. It must not touch the real data root, which the existing tests rely on.

**Steps:**
1. **Sources.** Use `preferences.json` if it exists. Otherwise process every backup (`preferences.json.migrated`, then `preferences.json.migrated.*`, sorted).
2. **Per source:**
   1. Read the bytes and `sha = sha256(bytes)`.
   2. If receipt `preference-migration:<sha>` already exists, skip with zero writes.
   3. In one `BEGIN IMMEDIATE`, for each key:
      - skip it if its origin row exists;
      - skip it if `(key, canonical value)` is in the tombstone set — the union of every version's key/value for any artifact that has a `deleted=1` version with source `LEGACY_PREFERENCE_SOURCE`;
      - otherwise insert it through `_prepare_write`/`_insert_row`.
   4. Write the receipt (`kind="preference_migration"`, payload `{source, source_sha256, inserted, skipped_existing, skipped_tombstoned, artifact_ids}`) and commit.
   5. Verify every key has either an origin row or a tombstone. If not, raise `PreferenceError("E_MIGRATION_VERIFY")` and do not rename.
3. **Rename** (original file only), under `transactions._get_file_lock(path)`, after the `_before_backup_rename()` seam:
   - Re-hash the original. If it differs from the bytes read, do not rename (`source_changed`).
   - Otherwise the target is `.migrated` if absent, else `.migrated.<sha[:16]>` if absent, else leave the original in place.
   - The rename never overwrites. On Windows use `os.rename`. On POSIX, check the target is absent, then `os.rename`.
   - After the rename, hash the backup. If it does not match `sha`, run a migration pass over that backup in the same call.

## 4. Cross-task conflicts

1. **72-T01 (T004).** `evaluate_artifact_visibility` must accept the overlay access (owner `user_overlay_owner_scope`, operation `overlay_read`) against a store rooted at `dr/user`. It must not require `store.project_root` to equal the access `project_root` for that owner. If T01 lands with such a check, T031 stops; it does not edit `retrieval.py`.
2. **72-T06 (T009 and its cards).**
   - Operation counts become 23 after T05, so T06 moves them 23→25, renames the `test_phase70_t20` count test to `_is_25`, and adds `preference` to the parity sets.
   - T06's H6 correction on `subject="preference"` must also write the content-level `applicability`/`correction`. `PreferenceStore.correct` must be rerouted through T06's canonical transaction with an unchanged result shape. `insert_relation_tx` replaces T05's direct edge INSERT.
   - The `task_mismatch` check must treat preference content `scope=="task"` + `task_id` as the binding.
   - T06 already reuses T05's `task_id` naming.
3. **72-T02.** Writes go only through `_write_version`/`_insert_row`, so `payload_hash` applies. The RED author re-checks the signatures.
4. **72-T03.** T05's direct `supersedes` INSERT is within one store and one owner, under a write grant. A new T03 owner check on `add_relation` does not cover it until T06 replaces it.
5. **72-T04.** Maintenance corroboration can STATED-promote inferred preferences with count ≥2. H3 keeps those inferred.
6. **72-T07.** The CLI, TUI and dashboard preference views and correction call the `preference` operation. Under OD-1(b) the CLI leaf moves into T05.
7. **73-T02/BOOTSTRAP.** Preference delivery calls `PreferenceStore.resolve` and never reads the overlay directly.
8. **§8 / 73-T09.** Personal-scope export uses `PERSONAL_PREFERENCE_SOURCE` and the overlay owner.
9. **Phase 70.** `user/.rush/agent_memory.json` sits alongside the overlay `memory.db`. It is never read as preference data.

## 5. Test matrix (`tests/test_phase72_preferences.py`, new)

**Common setup for every test:**
- Import new symbols inside the test body.
- Patch `HOME`, `XDG_DATA_HOME` and `LOCALAPPDATA` to tmp paths.
- `dr = tmp_path/"user-data"` for library calls. MemoryTool tests use `dr = default_data_root()` after the patch.
- `register_project(root, data_root=dr)` comes before any grant.
- The project grant is: owner `legacy_owner_scope(root)` (unless stated otherwise), sources `[PROJECT_PREFERENCE_SOURCE, LEGACY_PREFERENCE_SOURCE]`, operations `["ask","list","expand","write","bootstrap"]`, at the current revision with `consent=True`.
- The overlay grant is: `user_overlay_owner_scope(data_root=dr)`, sources `[PERSONAL_PREFERENCE_SOURCE]`, operations `["overlay_read","write"]`.
- `_tree(p)` snapshots the sorted (path, size, mtime_ns, sha) of a directory tree.

**Expected RED failure:** `ImportError` for `PERSONAL_PREFERENCE_SOURCE`, `PreferenceError` or `resolve`, unless the row says otherwise.

| Test id | Fixture | Action | Assertion |
|---|---|---|---|
| `test_t05_scope_precedence_consent_and_migration` | Projects A, B, C. Overlay grant for A and B. Personal explicit `format=compact`; A explicit `wide`; B none; A task `task-a` explicit `plain`. C holds a legacy `{format: compact}` file | `resolve("format")` in A with `task-a`, in A, and in B; `end_task("task-a")`; migrate C twice | `plain` / `wide` / `compact`; after end_task, A with `task-a` gives `wide`; C migration returns 1 then 0 |
| `test_t05_inferred_is_advice_only` | Personal explicit `compact`, project inferred `wide`, task inferred `plain`; second project with explicit `compact` + inferred `wide` | resolve | `compact` both times; `advice` has exactly both inferred refs; never `selected` |
| `test_t05_corroborated_and_content_inferred_stay_advice` | Inferred row promoted with `user_stated=True`; explicit-content row promoted by corroboration (`candidate_sources` from 2 sources) | resolve | Both under `advice` with reasons `content_inferred`/`corroborated`; `status="advice_only"` |
| `test_t05_same_scope_explicit_conflict_unresolved` | Project explicit `wide` and `narrow` | resolve; `add_relation(supersedes)` between them; resolve; `correct(kind="supersede", value="narrow", user_stated=True)`; resolve | `unresolved` with both refs; still `unresolved` after the link; then `selected` `narrow`, original v3 `superseded`, edge new@2→orig@3 |
| `test_t05_reject_retained_and_query_matching` | Explicit `ui.panels=verbose` and `number.format="wide integer"`; a `contradicts` edge to `ui.panels` | `correct(reject, reason="Alice does not want verbose panel layouts", user_stated=True)`; `resolve(query="verbose panels")`; `resolve(query="wide integer")` | v4 STATED, rejected; `get_version_content(id,2)` is the original; `affected.relations` holds the edge; the first query returns the rejection; the second selects `wide integer` with `rejections == []` |
| `test_t05_overlay_requires_separate_grant` | Overlay row written under A's grant; B has a project grant only | resolve in B | `layers.personal.state == "disabled"`; no personal value; `_tree(dr)` and overlay DB sha unchanged |
| `test_t05_declined_consent_creates_nothing` | Project grant only | Overlay `grant_memory_scope(consent=False)`; resolve | `MemoryPolicyError` `E_CONSENT`; `disabled`; `dr/user/.rush/memory.db` absent |
| `test_t05_revoked_overlay_policy_revision` | Overlay granted at rev N, personal `compact` | resolve; revoke; resolve | Second result `layers.personal.state == "revoked"`, `policy_revision == N+1`, no `compact` |
| `test_t05_revoke_during_resolution_leaks_nothing` | As above | Monkeypatch `_before_delivery` to revoke on first call | Result has no personal value or ref |
| `test_t05_foreign_rows_and_host_identity_never_authorize` | A store has a `bob-secret` row owned by `agent:bob`, and a row with attribution host `codex`; B store has explicit `b-private` | resolve in A under two attributions | No `bob-secret`/`b-private`/B ids/B root in `json.dumps(result)`; identical `selected` both times |
| `test_t05_no_upward_migration_and_no_global_copy` | Overlay write granted | Record project + task explicit; resolve in A and B | Overlay DB absent; project DBs have 0 rows with source `PERSONAL_PREFERENCE_SOURCE` or content scope `personal` |
| `test_t05_personal_write_rules` | Overlay granted | Record personal inferred; record personal explicit without `user_stated`; correct an explicit record without `user_stated` | `E_INPUT` with exact reasons; overlay DB absent; versions unchanged |
| `test_t05_no_native_host_memory_import` | Patched HOME with `.claude/CLAUDE.md`, `.codex/AGENTS.md`, and `dr/user/.rush/agent_memory.json` all saying `format: verbose`; overlay granted but empty | resolve | `status="none"`; no `verbose`; overlay DB absent |
| `test_t05_task_binding_isolated` | Task `task-a` `plain`; task `task-c` with past `expires_at` | Resolve with `task-b`, none, `task-c`; `end_task("task-a")` | `wide` for all; ended row has a new version and its history is kept |
| `test_t05_tampered_explicit_falls_through` | Personal compact + project explicit `wide`, then project content altered by SQL | resolve | `compact` (T01 integrity excludes the row) |
| `test_t05_read_paths_create_nothing` | Unregistered dir; missing dir; registered project with policy | Constructor, `get`, `list_all`, `resolve` | No `.rush`, project root or `dr` created; registered `_tree` unchanged. RED fails on an AssertionError (the constructor creates `.rush`) |
| `test_t05_migration_single_transaction_and_receipt` | Legacy `{format, editor}` | Migrate; then a fresh copy with `_insert_row` patched to raise on the 2nd call | 2 inserted; receipt payload `source_sha256` and keys; failure leaves 0 new rows and identical `preferences.json` bytes, no backup |
| `test_t05_migration_never_overwrites_backup` | Legacy file | Migrate; `set` a new key; migrate | `.migrated` bytes unchanged; `.migrated.<sha16>` holds the new bytes. RED: AssertionError |
| `test_t05_migration_replay_no_resurrection` | Migrated `format` | Hard delete; replay; restore the original bytes and migrate; delete receipts by SQL and migrate | 0 each time; `read_origin` is None. RED: AssertionError (returns 1) |
| `test_t05_migration_source_changed_not_renamed` | Legacy file | Patch `migration._before_backup_rename` to `set` a new key | Original kept; rerun migrates the new key, then renames |
| `test_t05_concurrent_correction_exact_e_version` | Explicit v2 | Reject at 2 (OK); supersede at 2 | `PreferenceError.code == "E_VERSION"`; row count unchanged; v2 content intact |
| `test_t05_memory_tool_preference_operation` | `dr = default_data_root()`; grants | `MemoryTool().run(root, operation="preference", request={...})`: resolve; record with `apply` false; apply without `cache_write`; apply with permission | Envelope `OK` + `selected`; preview creates no files; `E_PERMISSION` (status fail/skipped per `_CODE_STATUS`); `OK` v2. `validate_and_normalize` rejects an unknown request key. `"preference" in memory_model_tags() == VALID_OPERATIONS == get_args(MemoryOperation)`. RED: AssertionError on "Unsupported memory operation" |
| `test_t05_same_project_agents_same_choice` | Two attributions and two `MemoryTool` instances | resolve | Identical `selected` ref and `why` |
| `test_t05_project_denied_never_reads_overlay` | Overlay granted; project grant revoked | resolve | `status="denied"`; no values; no personal ref |

**Platform markers:** none. Every case is platform-neutral, and the Windows rename branch is exercised by the same tests on Windows CI. No test is ever skipped.

## 6. Worker packages

Both packages are in the receipt below. RED is card T030; implement is card T031 (Opus, trust boundary).

---

## (B) Receipt

```json
{
  "goalbuddy_receipt_v1": {
    "result": "done",
    "task_id": "T008",
    "board_path": "/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/docs/goals/phase-72-memory-correctness/state.yaml",
    "decision": "approved",
    "full_outcome_complete": false,
    "rationale": "72-T05 is fully mapped at 07775f1. Probes confirm 5 defects: the constructor and get() create files, a second migration overwrites the backup, a hard-deleted key comes back on replay, there is no migration receipt, and migration is not one transaction. The design fixes the authority classification, precedence, the separate overlay grant, the policy-then-store writers, the corrections, and a CAS-safe migration that never overwrites a backup. Adding the preference operation needs request_models.py and the two count tests on top of the packet's files. T030 needs owner answers to OD-1 and OD-2 first.",
    "worker_package": {
      "red": {
        "objective": "Write tests/test_phase72_preferences.py with exactly the 24 tests in T008 note section 5. Import new symbols inside test bodies. Patch HOME/XDG_DATA_HOME/LOCALAPPDATA. Call register_project before every grant. Use tmp_path only. Prove that every test fails for the stated reason.",
        "allowed_files": ["tests/test_phase72_preferences.py"],
        "verify": [
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -c \"import subprocess,sys; r=subprocess.run([sys.executable,'-m','pytest','tests/test_phase72_preferences.py','-q','-p','no:cacheprovider'],capture_output=True,text=True); print(r.stdout[-4000:]); s=(r.stdout.strip().splitlines() or [''])[-1]; sys.exit(0 if r.returncode==1 and ' failed' in s and not any(w in s for w in (' passed',' skipped',' error',' xfail',' xpass')) else 1)\"",
          "rtk proxy uv run --python 3.12 --extra dev ruff check tests/test_phase72_preferences.py",
          "rtk proxy uv run --python 3.12 --extra dev ruff format --check tests/test_phase72_preferences.py"
        ],
        "stop_if": [
          "Any test passes, skips or errors at collection",
          "rush.memory.authorization or retrieval.evaluate_artifact_visibility is missing, or its signature or result keys differ from T003 section 3 / plan section 2.1 (report the drift)",
          "grant_memory_scope rejects operations ['overlay_read','write'] on user_overlay_owner_scope",
          "A test would need the real data root or a non-test file edit",
          "OD-1 or OD-2 is unanswered, or the answer is (b) and the PM has not amended the matrix",
          "Free disk below 8 GiB"
        ]
      },
      "implement": {
        "objective": "Implement 72-T05 exactly as T008 note section 3 (H1-H7) specifies, until every T030 test passes. Add the MemoryTool 'preference' operation (actions resolve/record/correct/end_task) and its strict request model. Update the operation counts 22 to 23 in tests/test_phase70_t6.py (MEMORY_OPERATIONS sample entry and request-keys parametrize) and tests/test_phase70_t20.py (rename the count test to _is_23). Dispatch on Opus. Do not edit RED tests or authorization.py.",
        "allowed_files": [
          "src/rush/memory/preference_store.py",
          "src/rush/memory/migration.py",
          "src/rush/memory/store.py",
          "src/rush/tools/memory.py",
          "src/rush/mcp_support/request_models.py",
          "tests/test_phase70_t6.py",
          "tests/test_phase70_t20.py"
        ],
        "verify": [
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_preferences.py tests/test_memory_compatibility_regressions.py -q -p no:cacheprovider",
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase61_migration.py tests/test_phase58_map_transactions.py tests/test_phase58_persistence.py tests/test_phase53_state_writers.py tests/test_phase41_memory_ship.py tests/test_cli_runtime_bindings.py tests/test_phase70_t6.py tests/test_phase70_t20.py tests/test_memory_versions.py tests/test_memory_authorization.py tests/test_phase72_memory_correctness.py tests/test_memory_public_contract.py tests/test_memory_relations.py -q -p no:cacheprovider",
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -c \"import subprocess,sys,re; r=subprocess.run([sys.executable,'-m','pytest','tests/','-q','-m','','-p','no:cacheprovider'],capture_output=True,text=True); out=r.stdout; print(out[-3000:]); fails=set(re.findall(r'^(?:FAILED|ERROR) (\\S+)',out,re.M)); base={'tests/test_phase70_t28f_review1.py::test_plus_minus_expand_and_collapse_detail_in_git_and_memory','tests/test_phase70_tui_usability_ef.py::test_t28e_tokens_git_artifacts'}; last=(out.strip().splitlines() or [''])[-1]; print('NEW FAILURES:',sorted(fails-base)); sys.exit(0 if fails<=base and 'skipped' not in last and ' error' not in last else 1)\"",
          "rtk proxy uv run --python 3.12 --extra dev ruff check src tests scripts",
          "rtk proxy uv run --python 3.12 --extra dev ruff format --check src tests scripts",
          "rtk proxy uv run --python 3.12 --extra dev mypy src/rush",
          "rtk git diff --check"
        ],
        "stop_if": [
          "Any file outside allowed_files would need to change: retrieval.py, cli.py, theme.py, the governance manifest, authorization.py, or another test file enumerating operations",
          "store.py would need more than narrow owner/version helper exposure",
          "T01's evaluate_artifact_visibility rejects overlay access against the dr/user store root",
          "A RED test appears wrong (report it; do not edit it)",
          "The full suite shows a new failure or any skip",
          "A third fix round would be needed (cap is 2)",
          "A read path creates any file, or a test touches the real data root",
          "Free disk below 8 GiB"
        ]
      }
    },
    "owner_decisions_needed": [
      "OD-1: What establishes explicit (user-approved) preference authority? (a) Plan-literal and the design default: STATED via user_stated promotion, plus apply, the cache_write permission and a policy write grant; reachable through MCP and in-process like the existing promote. (b) Explicit and personal writes, and corrections of explicit rules, go only through a CLI-only leaf. This adds cli.py, governance/public_operations.py, a regenerated governance/public-operations.toml, test_phase54 counts, theme.py and the T27 matrix to T05.",
      "OD-2: Legacy un-promoted preference values (migrated preferences.json values and rush context persona --set) in layered resolution: (a) advice until user-approved by promotion (design default), or (b) explicit project preferences. Legacy get/list_all behaviour is unchanged either way."
    ],
    "evidence": [
      "Probe (TemporaryDirectory, .venv python): 'ctor creates .rush: True', 'memory.db after get: True', 'ctor creates missing project root: True', 'backup overwritten: True'",
      "Probe: migrate=1, hard delete, then read_origin None; replay returned 1 and the row came back; mutation_receipts count (0,)",
      "migration.py:297-320 calls write_if_new per key (each commits separately); _rename_migrated :276 uses Path.rename",
      "graft callers: migrate_preference_store is called by tests only; get_preference_readonly and PreferenceStore are called in production only by cli.py:5562-5579",
      "trust.py:149-205: user_stated gives STATED with corroboration 0; corroboration >= 2 gives STATED. store.py:1435 edit demotes STATED to DERIVED; _find_stated_conflict evicts only when symbol_ref is set",
      "tests/test_phase70_t6.py:220-221,300,786 and test_phase70_t20.py:866-871 pin 22 operations; request_models.py:383/484/543/714 nested-action precedent (intent/recipe/handoff)",
      "T003 section 3: overlay grant uses user_overlay_owner_scope and overlay_read; resolve result keys; lock order policy then store. C01 contract L34-48",
      "Free disk 21 GiB at start"
    ],
    "summary": "T05 is approved with a corrected scope: 7 implementation files rather than 4, because the preference operation needs request_models.py and the two count tests. The design fixes precedence, the separate overlay grant and per-call recheck, the policy-then-store writers, the corrections, and a replay-safe migration that never overwrites a backup. The matrix has 24 RED tests. Two owner decisions (OD-1 confirmation channel, OD-2 legacy authority) gate T030. Required board updates go to the T01 gate (overlay visibility root) and the T06 gate/cards (counts 23 to 25, content-level applicability and task binding, rerouting corrections).",
    "note": "notes/T008-design-gate-72-t05.md",
    "required_board_updates": [
      "T004 (72-T01 gate): evaluate_artifact_visibility must accept overlay access (user_overlay_owner_scope, overlay_read) against a store rooted at default_data_root()/user",
      "T009 note and T06 cards: operation counts become 23 to 25 (t6 L220, t20 L870 plus test rename); T06's H6 correction on subject preference must write and honor content-level applicability/correction; reroute PreferenceStore.correct through the canonical transaction; the task_mismatch check must honor preference content scope=='task' with task_id; insert_relation_tx replaces T05's direct supersedes INSERT",
      "72-T07 gate: the preference user surfaces consume MemoryTool operation 'preference' (if OD-1 is (b), the CLI leaf moves into T05)",
      "73-T02/BOOTSTRAP: preference delivery calls PreferenceStore.resolve, never reading the overlay directly"
    ]
  }
}
```

Relevant paths, all under `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/`:
- `src/rush/memory/preference_store.py`
- `src/rush/memory/migration.py`
- `src/rush/memory/store.py`
- `src/rush/tools/memory.py`
- `src/rush/mcp_support/request_models.py`
- `tests/test_phase70_t6.py`
- `tests/test_phase70_t20.py`
- `docs/goals/phase-72-memory-correctness/notes/T003-design-gate-policy.md`
- `docs/goals/phase-72-memory-correctness/notes/T009-design-gate-72-t06.md`
