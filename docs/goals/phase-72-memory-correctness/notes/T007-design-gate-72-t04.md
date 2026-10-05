# T007: Design gate for 72-T04 (goal-judge report, recorded verbatim)

The text below the line is the goal-judge's T007 report, copied unchanged.

## PM re-checks (run on 07775f1)

1. **Cross-owner promotion reproduces.**
   - Setup: a TemporaryDirectory git repo with `pkg/mod.py` and two anchored rows with the same payload, a1 (alice, source-a) and b1 (bob, source-b).
   - Action: `run_maintenance_cycle("promotion_sweep", project_root=root, owner_scope=alice)`.
   - Result: processed 1, changed 1, and a1 became `STATED`.
2. **Importing `rush.dashboard.state` loads `rush.tools.memory` and `rush.memory.maintenance`.** This supports the gate's import-cycle hazard and its lazy-import rule.

verified-by:
- probe 1 printed `1 1` and then `STATED`;
- probe 2 printed `True True True` for the `sys.modules` membership checks.

**PM reconciliation with T003:**
- T003's `hold_policy_lock` is the exported policy OS-lock helper this gate needs.
- `resolve_memory_scope` returns `approved_sources`.
- Grant ops include `write` and `list`.

The gate's stop_if items on these three points are answered by the T003 design.

**Flags the PM routes to the owner:**
- Maintain is denied without a policy grant until a consent path exists. This is the same root issue as T011's D-T07-1.
- The PluginTrustStore repo-local ledger risk is untracked.
- Phase 70 fixture grant seeding needs to be coordinated.

**Not re-run by the PM:** the rest of the report. The T027 RED author re-checks the code map at HEAD (stop_if).

---

# T007 design gate: 72-T04 (maintenance import and owner-isolated corroboration)

**Verdict: approved.** The package is buildable from the code at `07775f1` with no owner decision open. Two things still have to be re-checked when the RED author starts: the exact helper names that 73-T02/POLICY and 72-T01 ship (the stop_if items below), and the PM handling the cross-phase fixture items.

This message is the note body for `notes/T007-design-gate-72-t04.md`. I made no edits.

## (A) Note body

### 1. Testable behavior

- **Fresh import.** `from rush.memory.maintenance import run_maintenance_cycle; print(run_maintenance_cycle.__name__)` prints exactly `run_maintenance_cycle` and exits 0. Today it does (I ran it). Fresh `import rush.dashboard.state` and fresh `import rush.tools.memory` both still exit 0, and so does importing `rush.memory.authorization` before maintenance.
- **Cross-owner (bug reproduced; verified-by: PM probe printed 1 1 then STATED).** At 07775f1, Alice row `a1` (source-a) plus Bob row `b1` (source-b, same symbol and payload) gives an Alice `promotion_sweep` of `processed=1 changed=1`, with `a1` promoted to STATED and `corroboration_count=2`. After T04, Bob's row adds nothing.
  - Plan acceptance "processed1 changed0" holds on a settled baseline. The first sweep of Alice alone records `corroboration_count` 0→1 (changed1, an existing bookkeeping write). Bob is then added, and the second Alice sweep gives `processed1 changed0` with `a1` still DERIVED and its version unchanged.
- **Who corroborates.** A row counts only if all of these hold:
  - same owner `(kind, id)`; legacy NULL owner resolves to `legacy_owner_scope(root)`;
  - same subject, `symbol_ref` and parsed payload;
  - non-STATED, not stale, not archived, not expired, not orphaned, valid JSON;
  - its `source` is in the effective allowlist, which is the grant's approved sources narrowed by the caller's requested sources;
  - it is grounded (anchored rows only): T01's freshness is `current`, meaning a contained symbol and a source hash that matches. Unknown or stale freshness never counts.
- **Independence.** Independence key = distinct approved `source`. Duplicate copies with the same source count once. Labels the grant has not approved count zero.
- **What does not count.** Owner-name equality (`agent:alice` vs `user:alice`), Bob's rows, denied sources, ungrounded or stale anchored peers, and corrupt peers all add zero.
- **Promotion threshold.** The candidate itself must pass the same predicate, otherwise the count is 0. Two independent grounded allowed sources (`a1` source-a, `a2` source-b) promote exactly one row: `a1` becomes STATED with count 2, and `a2` gets a bookkeeping write to count 1.
- **Authorization.**
  - Apply needs `resolve_memory_scope(operation="write")`; preview needs `operation="list"`.
  - Missing policy, revoked grant, missing operation, or a requested source outside the grant is refused with `E_PERMISSION` (status `fail`). The refusal happens before any lock, DB, `.rush` or data-root file is created, and it lists no candidate IDs.
  - A missing execution permission still returns `skipped` first. That existing test is kept.
- **Lock order.** Policy OS lock, then mesh lease, then SQLite transaction. The policy lock is held through the last row commit, so a concurrent `revoke_memory_scope` blocks until the sweep finishes, and the next sweep is denied.
- **Lease loss.** The lease is checked before every row. On loss, no later row commits. The result reports `lock_lost=True` and `unprocessed=(ids…)`; rows already committed keep accurate counts and receipts. The lease is not released (existing behavior). MemoryTool status becomes `warn`.
- **Corrupt row.** It goes into `errors` by exact ID, counts as processed, never acts as a corroborator, and the other rows keep truthful counts. Status is `warn` when `errors` is non-empty.
- **Preview.** Uses the same owner, source and active predicates as apply. With a valid grant and a missing DB it returns `[]` and creates no `.rush`. With a drifted `expected_revisions` value, apply refuses the row and changes 0.
- **Legacy `candidate_sources` promote path** (store, CLI, dashboard, MCP). Labels are only a filter over peers resolved from the DB, never evidence on their own. The `candidate_refs` path uses the same shared predicate (an expired ref peer now gives `E_VERSION`) and counts only grounded refs.
- **`skill_admission_check`.** Uses the same scoped corroboration.

### 2. Code and caller map (07775f1)

**`src/rush/memory/maintenance.py`**
- `MaintenanceTask` :36, `_OWNER_CLAUSE` :48, `_SELECT_SQL` :56, `_PREVIEW_COLUMNS` :80, `_select_rows` :88, `preview_maintenance_candidates` :115.
- `MaintenanceRunResult` :190, `_revision_conflicts` :201, `run_maintenance_cycle` :240, the renew-every-50 loop at :349.
- `_mutate_row` :369, `_artifact_from_row` :385, `_candidate_sources` :403 (cross-owner: no owner, archive, expiry, source or payload filter).
- `_mutate_promotion_sweep` :414: computes sources *outside* `BEGIN IMMEDIATE` (a time-of-check/time-of-use gap) and does the bookkeeping write at :440-456.
- `_mutate_skill_admission_check` :501.
- Module-level `from rush.plugins.trust_store import PluginTrustStore` :34. Keep it; it imports cleanly today.

**`src/rush/memory/store.py`**
- `OwnerScope` :249, `legacy_owner_scope` :290, `owner_scope_for_row` :309.
- `promote` :2553-2640: the `candidate_refs` same-owner check is at :2586-2617, and the legacy label path takes `candidate_sources` unchecked.
- `promote_stored_artifact` :2771, recall hash freshness inline at :2735-2747.

**`src/rush/memory/trust.py`**: `count_corroboration` :130 (distinct labels), `evaluate_promotion` :149, `resolve_symbol_ref` :108 (T01 hardens).

**`src/rush/memory/expiry.py`** (missing from packet): `expired_candidate_rows` :62, `sweep_reviewed_expired` :145.

**`src/rush/tools/memory.py`**
- `_MAINTAIN_REQUEST_KEYS` :292, maintain dispatch lambda :592 (does not pass `session_allowlist`).
- `_run_promote` :1566, with a duplicate inline peer predicate at :1673-1716.
- `_run_maintain` :1791-1935 (status `warn` only on `refused`).

**Callers (graft `--depth all`)**
- `run_maintenance_cycle` ← `_run_maintain` ← `run`/`__call__`.
- Dynamic adapters: `cli.py` `memory_maintain_cmd` :3693, `dashboard/server.py` `_dispatch_memory_maintain` :3158, `tui.py` `_memory_maintain_preview` :4057 / `_apply` :4114, `mcp_support/request_models.py` :565 (maintain model has no allowlist), `scripts/benchmarks/memory.py` `_probe_stale_record` :94.
- `promote_stored_artifact` ← maintenance ×2 and `store.promote` ← `_run_promote`.
- `sweep_reviewed_expired` ← `run_maintenance_cycle`, `sweep_expired`.

**Files missing from the packet** (each found, by reading, to exercise the changed paths)
- Production: `src/rush/memory/expiry.py`.
- Tests needing fixture-only updates (seed real grants or grounded same-owner evidence; never weaken an assertion):
  - `tests/test_memory_core_regressions.py` (:164-198 promotion relies on an ungrounded "second" row; :334/:342/:421 CLI maintain)
  - `tests/test_phase61_memory_tool.py:60`
  - `tests/test_phase70_t28d.py` (:966-1043, TUI maintenance)
  - `tests/test_phase70_t28d_backend.py` (:102-141: different-payload, unanchored, ungrounded "corroboration")
  - `tests/test_phase70_t28d_review1.py` (:317, :454, :480)
  - `tests/test_windows_import_safety.py` (:1139 sweep, :1483-1541)
  - `tests/test_dashboard_missing_routes.py:859`
  - `tests/test_dashboard_memory_tokens.py:503-537` (promotion from fabricated labels)
  - `tests/test_phase70_t27.py` with `tests/fixtures/phase70/cli-outcomes.json` `memory.maintain` (expects `ok`)
  - `scripts/benchmarks/memory.py:94`

**Symbols earlier units will change (RED author re-checks)**
- 73-T02/POLICY: new `authorization.py`.
- 72-T01: `resolve_symbol_ref` containment, the retrieval "freshness helper", `MemoryTool.run` policy threading and grant fixture helper, `store.edit`/`update_content`, and it creates `tests/test_phase72_memory_correctness.py`.
- 72-T02: `retrieval.py` cursors.
- 72-T03: `relations.py`, `consolidation.py`. No overlap.

### 3. Design of the hard parts

**D1. One shared predicate in `store.py`, and only this.**
- `corroboration_peer_matches(candidate: MemoryArtifact, peer: MemoryArtifact) -> bool`: same `owner_scope`, subject, `symbol_ref` and content; `trust_tier != "STATED"`; not stale; `archived_at is None`; not `expired`.
- `corroborating_sources(conn, candidate_id: str, *, project_root: Path, allowed_sources: Collection[str], peer_ids: Collection[str] | None = None) -> list[str]`:
  - Runs `SELECT * … WHERE subject=:s AND symbol_ref IS :r AND trust_tier!='STATED' AND stale=0 AND archived_at IS NULL AND expired_at IS NULL AND orphaned_at IS NULL AND json_valid(content) AND COALESCE(owner_scope_kind,:lk)=:ok AND COALESCE(owner_scope_id,:li)=:oi AND source IN (SELECT value FROM json_each(:sources))`, plus `id IN peer_ids` when given.
  - Filters each row with the predicate. Anchored rows also need T01's access-free freshness helper (lazy import inside the function) to return `current`. Unanchored rows need no freshness.
  - Returns `[]` unless the candidate is in the kept set. Otherwise returns the sorted distinct sources, including the candidate's own.
- `store.promote`:
  - The refs path keeps the version/source check and swaps its inline test for `corroboration_peer_matches`; a failure raises `VersionConflictError` as today. It then calls `corroborating_sources(..., allowed_sources={ref sources}, peer_ids={ref ids})`.
  - The legacy path (`candidate_sources` given, no refs) calls `corroborating_sources(..., allowed_sources=candidate_sources)`.
  - `promote_stored_artifact`, `evaluate_promotion` and `count_corroboration` are unchanged.
- `_run_promote` :1689-1705 uses `corroboration_peer_matches`. That gives one predicate in store; `tui.py` keeps its advisory pre-filter (T07).

**D2. `maintenance.py`**
- Signatures:
  - `run_maintenance_cycle(task, *, batch_size=500, project_root=None, owner_scope: OwnerScope, sources: Collection[str], candidate_ids=None, expected_revisions=None, data_root: Path | None = None)`.
  - `preview_maintenance_candidates(task, *, batch_size=500, project_root=None, owner_scope, sources, candidate_ids=None, data_root=None)`.
  - `sources` is required; empty means the grant's approved sources, which is 73-T02's `requested_sources` meaning.
- New `class MaintenanceAccessDenied(Exception)` with a `.reason` attribute.
- Apply sequence:
  1. Read-only `resolve_memory_scope(project_root=root, operation="write", owner_scope=owner_scope, requested_sources=tuple(sources), data_root=data_root)`. If denied, raise with no effects.
  2. Take 73-T02's exported policy OS lock and re-resolve under it. If denied, raise.
  3. `effective = approved sources ∩ requested`.
  4. Mesh `acquire`, then rows, then release the mesh lease, then release the policy lock.
- Preview resolves read-only with `operation="list"`, takes no lock, and adds `archived_at`, `orphaned_at` and `stale` to `_PREVIEW_COLUMNS`.
- Imports of `rush.memory.authorization` and `retrieval` are function-local. This is required: I simulated `rush.dashboard.state` being imported before `MaintenanceTask` is defined and got `ImportError: cannot import name 'MaintenanceTask' from partially initialized module` (chain: `dashboard.state` → tools → `tools.memory` → maintenance).
- `_SELECT_SQL` (all three tasks) gets `AND source IN (SELECT value FROM json_each(:sources)) AND archived_at IS NULL AND expired_at IS NULL AND orphaned_at IS NULL`. `expired_candidate_rows` and `sweep_reviewed_expired` gain `sources: Collection[str] | None = None` (None keeps legacy `sweep_expired`).
- `_mutate_row(..., *, allowed_sources)`. In the promotion and skill paths, compute `corroborating_sources` **after** `BEGIN IMMEDIATE` and `_refuse_unless_reviewed`. The bookkeeping count is `len(sources)`, and the bookkeeping semantics are kept.
- Remove `_RENEW_EVERY`. Before each row: `if not lock_manager.renew(_LOCK_PATH, capability, ttl_s=60.0)` → set `lock_lost`, set `unprocessed` to this row's ID and all remaining IDs, then break.
- `MaintenanceRunResult` adds `lock_lost: bool = False` and `unprocessed: tuple[str, ...] = ()`.

**D3. `_run_maintain`**
- Dispatch passes `session_allowlist`. Order: permission check (`skipped`) → owner → `sources=tuple(session_allowlist or ())`.
- `MaintenanceAccessDenied` maps to `fail` with raw `{"code": "E_PERMISSION", "reason": ...}` and no IDs.
- Status is `warn` if `refused`, `errors` or `lock_lost`. The summary names the error and unprocessed IDs.

**D4. Choices I settled from the plan text** (none is owner-level)
- Unanchored rows corroborate through ≥2 distinct grant-approved sources. Requiring an anchor would make `skill_admission_check`, which has unanchored payloads, unable to admit anything, which would be unstated descoping.
- Maintenance has no legacy "allowlist without policy" path, because maintain never took an allowlist. C01 says missing policy means denied.
- Independence key = approved `source`. The ceiling is the C01 statement that there is no isolation against same-OS-user hostile processes.

### 4. Cross-task conflicts

- **73-T02/POLICY**
  - Must export the policy OS-lock helper (or the policy path plus lock identity) for Phase 72 mutators.
  - The operation vocabulary must include `write` and `list`.
  - `resolve_memory_scope` must return the approved-sources key.
  - Its top-level import of `dashboard.state` creates the cycle risk above; T04 avoids it with lazy imports.
- **72-T01**
  - Needs an access-free freshness helper.
  - Its `expired` and `E_PERMISSION` conventions, grant fixture helper and `data_root` threading must match.
  - It hits the same t27 catalog, benchmark and native fixture grant seeding first; T04 reuses that harness.
- **72-T06**
  - Strict v2 maintain `sources` must map to `requested_sources`. It must use the same lock helper.
  - Plan §8 import must extend the independence key in `corroborating_sources` so imported duplicate copies (same foreign origin) collapse to one source. That obligation lives in the real plan §8 "Atomic import seam" and needs a line on the T06 card.
  - The bookkeeping write advances `artifact_version` without a content change; T06 should rule on that under its generation rules.
- **72-T07**: the TUI pre-filter at `tui.py:3683-3698` is a fourth copy of the predicate; switch it to the shared one. The TUI must render `E_PERMISSION`, lease loss and unprocessed IDs.
- **Phase 70/71**
  - Retained acceptance fixtures need real grants: the `cli-outcomes` `memory.maintain` route, the native lane in `test_windows_import_safety`, and the t28d tests.
  - The dashboard maintain route returns `E_PERMISSION` until consent exists.
  - Reconcile with the integration owner under C09.
- **Phase 73**: only BOOTSTRAP adds an end-user consent path, and it is not in this board's sequence. Until then, maintain is unusable from CLI, TUI and dashboard without a grant made through the Python API.
- **Phase 75**: the benchmark maintain probe must seed a grant.

### 5. Test matrix

All tests go in `tests/test_phase72_memory_correctness.py`.

**Common fixture**
- `pkg/mod.py` containing `def target(): return 1`; `symbol_ref="pkg/mod.py::target"`; `content_hash` = sha256 of that file's text.
- Payload `P={"title":"target returns one","claim":"target() returns 1"}`, written as DERIVED through `TypedArtifactStore.write`.
- `ALICE=user:alice`, `BOB=user:bob`.
- Grants through the real `grant_memory_scope` (`approved_sources=["source-a","source-b"]`, `ops=["write","list"]`, `consent=True`).
- Calls go through `MemoryTool().run(root, operation="maintain", …, permissions=cache_write)` unless a row says otherwise.

| test id | fixture | action | assertion | expected RED failure |
|---|---|---|---|---|
| test_t04_fresh_import_and_scoped_promotion | subprocess with PYTHONPATH cleared; Alice `a1` | fresh import; Alice sweep; add Bob `b1`; Alice sweep | stdout == "run_maintenance_cycle\n", rc 0; sweep 2 processed1 changed0; a1 DERIVED, same version, count 1 | sweep 2 promotes a1 (changed1, STATED) |
| test_t04_name_equality_never_corroborates | a1 Alice; x1 `agent:alice` source-b; y1 Bob source-b | Alice sweep | a1 DERIVED, count 1 | promoted with count 2 |
| test_t04_ungrounded_or_stale_peer_adds_no_corroboration | a1 grounded; a2 source-b with hash None; a3 source-b with hash "0"*64 | Alice sweep | a1 DERIVED | promoted |
| test_t04_denied_source_adds_no_corroboration | a1 source-a; c1 source-c grounded; separately a2 source-b with `session_allowlist=["source-a"]`; unanchored variant with source-c | sweeps | a1 never promoted | promoted |
| test_t04_requested_source_outside_grant_refused_with_zero_effects | grant a,b; `session_allowlist=["source-a","source-z"]` | apply | status fail, code E_PERMISSION; DB/WAL bytes unchanged; no new lock dir | status ok |
| test_t04_missing_policy_refuses_apply_and_preview_without_files | no policy | apply; preview (`request={"apply":False}`) | both E_PERMISSION; no `candidate_ids`; no root `.rush`; data root empty | ok, with IDs |
| test_t04_grant_without_write_refuses_apply | ops ["list"]; Alice and Bob rows | apply; preview | apply E_PERMISSION; preview lists only Alice IDs | apply ok |
| test_t04_legacy_owner_rows_isolated | a1 Alice; L1/L2 NULL owner, sources a,b; grant for `legacy_owner_scope` | Alice sweep; legacy sweep | a1 DERIVED; exactly L1 STATED; a1 untouched | a1 promoted |
| test_t04_corrupt_row_isolated_and_not_corroborating | a1 source-a; c1 source-b, content set to `'{"bad'` by SQL | Alice sweep | errors ("c1",); processed 2; changed 1; a1 DERIVED; status warn | a1 promoted / status ok |
| test_t04_lease_loss_commits_no_later_row_and_reports_unprocessed | r1-r3 anchored with stale hash; staleness_sweep; wrap `maintenance._mutate_row` so that after call 1 the lease is expired and reclaimed (agent "memory-maintenance") | apply | processed1 changed1; lock_lost; unprocessed ("r2","r3"); r2/r3 unchanged; thief still holds lock; status warn | r2/r3 committed; AttributeError on `unprocessed` |
| test_t04_policy_lock_serializes_revoke_against_apply | `_mutate_row` pauses on an Event | thread A apply; thread B `revoke_memory_scope` | B alive after join(0.5); after release both finish; next apply E_PERMISSION | revoke finishes at once |
| test_t04_lock_order_policy_then_mesh | spies on the 73-T02 lock helper and `MeshLockManager.acquire`/`release` | apply | order: policy-enter, mesh-acquire, mesh-release, policy-exit | no policy event |
| test_t04_preview_scoped_like_apply | a1 source-a, a2 source-c, b1 Bob | preview | candidate_ids == ["a1"] | includes a2 |
| test_t04_legacy_candidate_sources_cannot_promote_from_labels | `store.promote` on a1 with `candidate_sources=["source-a","source-b"]`; then with Bob b1; then with Alice a2 source-b | promote ×3 | False, False, True | first call promotes |
| test_t04_candidate_refs_shared_predicate | refs path; peer `expired_at` stamped; another peer anchored with hash None | `MemoryTool` promote with refs | expired gives E_VERSION; ungrounded gives promoted False, `insufficient_corroboration` | promoted |
| test_t04_skill_admission_scoped_corroboration | trusted plugin in a repo-local ledger; s1 Alice source-a; s2 Bob source-b, same payload | skill_admission_check (Alice) | s1 DERIVED | promoted |

**Guards: must pass at RED and at GREEN; do not include them in the RED selection.**
- `test_t04_duplicate_source_copies_do_not_corroborate`: a1/a2 both source-a; sweep 1 processed2 changed2; sweep 2 changed0.
- `test_t04_two_independent_grounded_allowed_sources_promote_once`: processed2 changed2; exactly a1 STATED, count 2.
- `test_t04_unanchored_two_approved_sources_promote`.
- `test_t04_apply_expected_version_drift_changes_nothing`.
- `test_t04_fresh_import_orders`: four subprocess variants, all rc 0.
- `test_t04_preview_missing_db_stays_absent`.
- Guards must go through MemoryTool so the new keyword arguments cannot make them fail at RED.

### 6. Worker packages

See the receipt.

## (B) Receipt

```json
{"goalbuddy_receipt_v1":{"result":"done","task_id":"T007","board_path":"/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/docs/goals/phase-72-memory-correctness/state.yaml","decision":"approved","full_outcome_complete":false,"rationale":"Cross-owner promotion reproduced at 07775f1 (Alice promoted by Bob's row, count 2). Design: one shared store predicate (corroboration_peer_matches/corroborating_sources) used by maintenance, both store.promote paths and _run_promote; policy-lock -> mesh -> SQLite with grant-scoped sources; per-row lease check reporting unprocessed IDs; lazy authorization imports (an import-cycle hazard was found by simulation). The packet's file list is extended to expiry.py plus fixture-only test files that the grant and grounding rules break. Plan-text choices settled in D4. The matrix has 16 RED tests and 6 guards.","worker_package":{"red":{"objective":"Append the 16 RED tests and 6 guards from the T007 matrix to tests/test_phase72_memory_correctness.py; import new symbols inside test bodies; prove every RED-selected test fails and every guard passes.","allowed_files":["tests/test_phase72_memory_correctness.py"],"verify":["cd /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72 && rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -c \"import subprocess,sys; r=subprocess.run([sys.executable,'-m','pytest','tests/test_phase72_memory_correctness.py::test_t04_fresh_import_and_scoped_promotion','tests/test_phase72_memory_correctness.py::test_t04_name_equality_never_corroborates','tests/test_phase72_memory_correctness.py::test_t04_ungrounded_or_stale_peer_adds_no_corroboration','tests/test_phase72_memory_correctness.py::test_t04_denied_source_adds_no_corroboration','tests/test_phase72_memory_correctness.py::test_t04_requested_source_outside_grant_refused_with_zero_effects','tests/test_phase72_memory_correctness.py::test_t04_missing_policy_refuses_apply_and_preview_without_files','tests/test_phase72_memory_correctness.py::test_t04_grant_without_write_refuses_apply','tests/test_phase72_memory_correctness.py::test_t04_legacy_owner_rows_isolated','tests/test_phase72_memory_correctness.py::test_t04_corrupt_row_isolated_and_not_corroborating','tests/test_phase72_memory_correctness.py::test_t04_lease_loss_commits_no_later_row_and_reports_unprocessed','tests/test_phase72_memory_correctness.py::test_t04_policy_lock_serializes_revoke_against_apply','tests/test_phase72_memory_correctness.py::test_t04_lock_order_policy_then_mesh','tests/test_phase72_memory_correctness.py::test_t04_preview_scoped_like_apply','tests/test_phase72_memory_correctness.py::test_t04_legacy_candidate_sources_cannot_promote_from_labels','tests/test_phase72_memory_correctness.py::test_t04_candidate_refs_shared_predicate','tests/test_phase72_memory_correctness.py::test_t04_skill_admission_scoped_corroboration','-q','-p','no:cacheprovider'],capture_output=True,text=True); print(r.stdout[-4000:]); s=(r.stdout.strip().splitlines() or [''])[-1]; sys.exit(0 if r.returncode==1 and ' failed' in s and not any(w in s for w in (' passed',' skipped',' error',' xfail',' xpass')) else 1)\"","cd /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72 && rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_memory_correctness.py::test_t04_duplicate_source_copies_do_not_corroborate tests/test_phase72_memory_correctness.py::test_t04_two_independent_grounded_allowed_sources_promote_once tests/test_phase72_memory_correctness.py::test_t04_unanchored_two_approved_sources_promote tests/test_phase72_memory_correctness.py::test_t04_apply_expected_version_drift_changes_nothing tests/test_phase72_memory_correctness.py::test_t04_fresh_import_orders tests/test_phase72_memory_correctness.py::test_t04_preview_missing_db_stays_absent -q -p no:cacheprovider","cd /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72 && rtk proxy uv run --python 3.12 --extra dev ruff check tests/test_phase72_memory_correctness.py","cd /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72 && rtk proxy uv run --python 3.12 --extra dev ruff format --check tests/test_phase72_memory_correctness.py"],"stop_if":["Re-checking the code map at current HEAD shows that an earlier unit changed maintenance.py, store.promote, _run_promote, _run_maintain or expiry candidate functions differently from this note","src/rush/memory/authorization.py does not export a policy OS-lock helper (or policy path + lock identity) for mutators, or its operation vocabulary lacks write/list, or resolve_memory_scope does not return approved sources","T01 did not ship an access-free freshness helper or a grant fixture helper","Any RED test errors at collection, passes or skips; any guard fails","A test needs a production edit to be writable"]},"implement":{"objective":"Implement 72-T04 per T007 D1-D4 on Opus (trust boundary) until all T04 RED tests and guards pass with full-suite, ruff, format and mypy green; adjust existing fixtures only by seeding real grants or grounded same-owner evidence.","allowed_files":["src/rush/memory/maintenance.py","src/rush/tools/memory.py","src/rush/memory/store.py","tests/test_phase72_memory_correctness.py","tests/test_phase62_maintenance.py","src/rush/memory/expiry.py","tests/test_memory_core_regressions.py","tests/test_phase61_memory_tool.py","tests/test_phase70_t28d.py","tests/test_phase70_t28d_backend.py","tests/test_phase70_t28d_review1.py","tests/test_windows_import_safety.py","tests/test_dashboard_missing_routes.py","tests/test_dashboard_memory_tokens.py","tests/test_phase70_t27.py","tests/fixtures/phase70/cli-outcomes.json","scripts/benchmarks/memory.py"],"verify":["cd /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72 && rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -c 'from rush.memory.maintenance import run_maintenance_cycle; print(run_maintenance_cycle.__name__)'","cd /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72 && rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_memory_correctness.py -k t04 -q -p no:cacheprovider","cd /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72 && rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase62_maintenance.py tests/test_phase62_expiry.py tests/test_phase61_trust.py tests/test_memory_versions.py tests/test_memory_core_regressions.py tests/test_phase61_memory_tool.py tests/test_phase70_t28d.py tests/test_phase70_t28d_backend.py tests/test_phase70_t28d_review1.py tests/test_windows_import_safety.py tests/test_dashboard_missing_routes.py tests/test_dashboard_memory_tokens.py tests/test_dashboard.py tests/test_phase70_t27.py tests/test_benchmark_memory.py tests/test_memory_authorization.py -q -p no:cacheprovider","cd /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72 && rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/ -q -m '' -p no:cacheprovider","cd /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72 && rtk proxy uv run --python 3.12 --extra dev ruff check src tests scripts","cd /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72 && rtk proxy uv run --python 3.12 --extra dev ruff format --check src tests scripts","cd /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72 && rtk proxy uv run --python 3.12 --extra dev mypy src/rush","cd /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72 && rtk proxy git diff --check","rush_check on changed files"],"stop_if":["A store.py change beyond corroboration_peer_matches, corroborating_sources and routing store.promote's two corroboration branches through them","Any top-level import of rush.memory.authorization or retrieval added to maintenance.py, or of retrieval to store.py","Fixing a broken existing test would need a weakened assertion or changed expected status, rather than seeding a real grant or grounded evidence","Editing authorization.py, tui.py, cli.py, dashboard/server.py or request_models.py would be needed","Fix round 3 would be needed (hard cap of two rounds)","Free disk below 8 GiB"]}},"evidence":["HEAD 07775f1; maintenance.py 530 lines read in full","Fresh `from rush.memory.maintenance import run_maintenance_cycle` printed run_maintenance_cycle, exit 0","Repro: Alice a1 + Bob b1 -> Alice sweep processed1 changed1, a1 STATED, count 2","Repro: Alice alone -> changed1 (bookkeeping 0->1); duplicate same-source -> processed2 changed1","Import-cycle simulation: importing rush.dashboard.state before MaintenanceTask -> ImportError partially initialized module","rush.dashboard.state import pulls rush.tools.memory and rush.memory.maintenance (sys.modules probe)","store.promote refs check store.py:2586-2617; legacy candidate_sources unchecked; _run_promote duplicate check tools/memory.py:1673-1716","test_dashboard_memory_tokens.py:503-537 promotes from fabricated labels source-a/source-b","Disk 20 GiB free"],"subgoal_contract":null,"parallel_safety":null,"blocked_tasks":[],"missing_evidence":["authorization.py and the T01 freshness/grant helpers do not exist at 07775f1; their exact names must be re-checked by T027"],"required_board_updates":["Copy the RED and implement worker_packages onto T027 and T028","Add to the T06 card: plan §8 import must extend corroborating_sources' independence key for foreign-origin copies; rule on whether the bookkeeping write should advance artifact_version","Add to the T07 card: replace tui.py:3683-3698 peer pre-filter with corroboration_peer_matches; render E_PERMISSION, lock_lost and unprocessed","Coordinate with the Phase 70 integration owner (C09) on grant seeding in retained-acceptance fixtures (cli-outcomes memory.maintain, windows native lane, t28d)","Record the usability gap: maintain is denied from CLI/TUI/dashboard until a consent path exists (73-T02/BOOTSTRAP is not in this board's sequence)","File a tracked item (none exists): PluginTrustStore uses a repo-writable ledger when the repo path contains pytest/temp/tmp (plugins/trust_store.py:85-93), and skill_admission_check trusts it"]},"owner_decisions_needed":[],"summary":"T04 gate approved. Cross-owner promotion reproduced at 07775f1 (verified-by: PM probe printed 1 1 then STATED). One shared store predicate closes the maintenance, legacy candidate_sources and refs paths. Grant-scoped sources sit under a policy-lock -> mesh -> SQLite order with lazy imports (cycle hazard proven). Per-row lease check reports unprocessed IDs. 16 RED tests and 6 guards. The packet's file list grows to expiry.py plus fixture-only test files. No owner decisions; Phase 70 fixture coordination and an untracked plugin-trust risk go to the PM.","note":"notes/T007-design-gate-72-t04.md"}}
```

Three things the PM should act on:

1. **Phase 70 fixtures.** These retained Phase 70 tests will fail until they seed real consent grants, because maintenance is now denied when no policy exists:
   - the `cli-outcomes` `memory.maintain` route (expects `ok`);
   - the native lane in `test_windows_import_safety`;
   - the t28d tests.

   C09 says to coordinate this with the Phase 70 integration owner.
2. **Usability gap.** From CLI, TUI or dashboard, maintenance stays denied until a consent path exists, and 73-T02/BOOTSTRAP is not in this board's sequence.
3. **Untracked security item.** Nothing tracks this yet, so it needs a filed item. `PluginTrustStore` uses a ledger inside the repo whenever the repo path contains `pytest`, `temp` or `tmp` (`plugins/trust_store.py:85-93`), and `skill_admission_check` relies on that ledger.

Relevant paths:
- `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/src/rush/memory/maintenance.py`
- `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/src/rush/memory/store.py`
- `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/src/rush/memory/expiry.py`
- `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/src/rush/tools/memory.py`
- `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/docs/goals/phase-72-memory-correctness/state.yaml`

Graft saved about 486,000 tokens this turn.