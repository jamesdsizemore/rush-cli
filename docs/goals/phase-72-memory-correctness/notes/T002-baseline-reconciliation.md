# T002: Baseline probe and plan reconciliation at 07775f1

Worktree: `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72`, HEAD `07775f1`. Plan: `docs/phase-plans/phase-72-memory-correctness-and-user-control-plan.md` (475 lines). The plan was reviewed at commit `66c6c799`, plus uncommitted changes in the phase-70 worktree.

## PM verification of this scout report (overrides the scout text below)

The PM re-checked the scout's drift claims and its open questions directly:

- **Wrong:** "`DEFAULT_MAX_TOKENS` and `DEFAULT_MAX_BYTES` not located." Both exist: `src/rush/memory/retrieval.py:66` has `DEFAULT_MAX_TOKENS = 2048` and `src/rush/memory/retrieval.py:67` has `DEFAULT_MAX_BYTES = 8192`. The plan's §2.1 item 3 claim holds. The separate `delivery/compact.py:38` `DEFAULT_MAX_BYTES = 32_768` is unrelated. Item 8 in section 5 is void.
- **Wrong:** "`_MemoryRunSpy` not found." It exists in test code at `tests/test_phase70_t28d.py:94`.
- **Checked:** `tests/test_memory_handoff.py` has no test named `test_t02_receiver_digest_reconstruction`. The 72-T02 gate (T005) must treat it as a new deliverable.
- **Checked:** `candidate_refs` does not appear anywhere under `src` at `66c6c799`. At `07775f1`, `store.py:2559` defines `promote(..., candidate_refs=...)` and `store.py:2586-2591` iterates the refs.
- **Checked:** `MemoryOperation` is defined at `tools/memory.py:72`.
- **Checked:** the TUI cycles subjects: key `S` in `tui.py:4507-4512` steps through `get_args(MemorySubject)`.

**Not PM-verified:** sections 1 through 5 below rest on the scout's report alone. That covers the §2.2 probe output, the §2 claims, the §3 file:line list and the §4 drift summaries, apart from the six items checked above. Each design gate (T003 to T014) is instructed to verify against 07775f1 every claim it consumes. Treat these rows as unverified until a gate receipt confirms them.

verified-by: `grep -c test_t02_receiver_digest_reconstruction tests/test_memory_handoff.py` printed 0; `git grep -c candidate_refs 66c6c799 -- src` printed nothing; `grep -n candidate_refs src/rush/memory/store.py` showed 2559/2586/2591; `grep -n "MemoryOperation = " src/rush/tools/memory.py` showed 72; `sed -n 4505,4515p src/rush/tui.py` showed the cycle; `grep -rn DEFAULT_MAX_ src` showed retrieval.py:66-67.

## 1. §2.2 probe

- **Command:** the plan heredoc, verbatim: `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python - <<'PY' ... PY`, run from the worktree root.
- **Isolation:** `TypedArtifactStore(root)` writes `root/.rush/memory.db` (`store.py:956`). Here `root` sits inside the probe's `TemporaryDirectory`. A `find -newermt` over `~/.rush` and `~/Library/Application Support/Rush` showed no writes.
- **Output:**

```
{"archive_hidden": false, "expansion_denied": false, "outside_denied": false, "paging": false}
AssertionError: {'paging': False, 'archive_hidden': False, 'expansion_denied': False, 'outside_denied': False}
```

- **Exit code:** 1. This matches the plan's pre-fix baseline. Every probe call binds with no signature drift.

## 2. §2 claims at 07775f1

Unchanged between `66c6c799` and `07775f1`: retrieval, trust, relations, consolidation, maintenance, preference_store, migration, api_diff and request_models. Each claim below holds unless the note says otherwise.

- `search_candidates` filters only `expired_at IS NULL` and has no archive predicate (`store.py:1175`). The legacy `search` does check archive (`store.py:2668`, `store.py:2681`).
- In `recall_page`, `limit=2` can mark a page complete (`retrieval.py:399`). The probe reproduced this: `paging` was false.
- Expansion returns base64 slices (`retrieval.py:593`, `retrieval.py:715`, `retrieval.py:765`).
- `add_relation` checks versions, existence and cycles. It does not check the owner (`relations.py:89`).
- `summary_is_current` compares versions only (`consolidation.py:140`).
- The maintenance fresh-import cycle is already fixed (`maintenance.py:240`). Importing it exits 0.
- Maintenance corroboration still crosses owners (`_candidate_sources`, `maintenance.py:403`). The public promote route now enforces same-owner corroboration; see section 4.
- `resolve_symbol_ref` accepts paths outside the project root (`trust.py:108`). The probe reproduced this.
- `diff_symbol` can return `unknown` (`api_diff.py:80`, `api_diff.py:105`).
- `PreferenceStore` uses `.rush/preferences.json` (`preference_store.py:18`, `preference_store.py:25`). `migrate_preference_store` is at `migration.py:297`. `default_data_root` is at `provision.py:124`.
- `authorization.py` does not exist.
- Locations: `MemoryTool.run` at `tools/memory.py:401`; `_build_memory_section` at `server.py:3749`; `renderMemorySection` at `application.js:1230`.
- **Stale:** plan L23 says `TuiState.memory_subject` is fixed. Its default is `domain_knowledge` (`tui.py:926`), but the TUI cycles subjects (`tui.py:4507-4512`).
- `edit` spans `store.py:1435-1527`. `open_readonly_view` is at `store.py:1844`. `_query` is at `tools/memory.py:844` and `_compact_query` at `tools/memory.py:885`.
- `test_t28d_memory_workflows` (`tests/test_phase70_tui_usability.py:64`) did not exist at `66c6c799`. It is committed now in a changed form and was not re-run in T002. The T001 full suite covers it.

## 3. §5 and §8 symbols and files

A mechanical check covered all 249 backtick tokens in L126-475. Every existing symbol is present at `07775f1`:

- **retrieval:** `recall_page` (399), `expand_artifact` (612), `hybrid_page` (923), `hybrid_candidates` (790), `defended_recall` (114), `_encode_cursor` (248), `_decode_cursor` (255).
- **store:** `search_candidates` (1175), `scope_artifacts` (1230), `_write_version` (630), `edit` (1435), `archive` (1529), `promote` (2553), `recall` (2697), `update_content` (2515), `delete` (2642), `open_readonly_view` (1844).
- **trust and diff:** `trust.resolve_symbol_ref` (108) and `ApiDiffer.diff_symbol` (`api_diff.py:80`).
- **cache gate:** `memory_cache_gate.check_memory_before_pack` (`token_economy/memory_cache_gate.py:64`).
- **MemoryTool:** `run` (401), `_query` (844), `_compact_query` (885), `_run_maintain` (1791), `_run_promote` (1566).
- **relations and consolidation:** `add_relation` (89), `related_artifacts` (160), `summary_is_current` (140).
- **maintenance:** `run_maintenance_cycle` (240), `MaintenanceTask` (36), `_SELECT_SQL` (56), `_mutate_row` (369), `_candidate_sources` (403), `_mutate_skill_admission_check` (501).
- **trust store:** `PluginTrustStore` (`plugins/trust_store.py:62`).
- **request models:** `_memory_tag` (668), `_memory_spec` (677), `memory_request_model_keys` (718).
- **TUI:** `TuiState` (911), `_memory_refresh` (3173), `_handle_memory_key` (4426), `_render_memory_admin` (7532).
- **dashboard server:** `_dispatch_memory_query` (2976) and `_build_memory_section` (3749).
- **dashboard client:** `renderMemorySection` (1230) and `switchSection` (1337).
- **existing tests:** `test_memory_public_contract.py`, `test_memory_relations.py`, `test_memory_consolidation.py`, `test_phase62_maintenance.py` and `test_dashboard_memory_tokens.py`.

These do not exist yet and are proposed by the plan:

- `TypedArtifactStore.apply_import_records`, `VisibilityDecision`, `evaluate_artifact_visibility`.
- `authorization.load_policy_readonly` and `authorization.resolve_memory_scope`.
- `preview_import` and `preview_binding`.
- All 7 test names in §8.

**Create targets** are all absent, which is correct:

- `src/rush/memory/authorization.py`, `src/rush/memory/capsule.py`, `src/rush/dashboard/panels.js`.
- `tests/fixtures/phase75/task_manifest.json`, `docs/reports/phase-72-memory-acceptance.md`.
- All `tests/test_phase72_*.py` files and `tests/test_phase71_dashboard_integration.py`.

`scripts/benchmarks/run.py` has no `--decision-mode`, `--decision-route` or `--task-manifest` flag.

## 4. Drift between 66c6c799 and 07775f1

There are 18 commits. All are Phase 70 acceptance, native and Codex work.

- **`store.py` (+62):**
  - Adds a new reader, `TypedArtifactStore.read_artifact_receipts_readonly` (about line 1146).
  - `promote` gains `candidate_refs` (2553-2617). Each corroborating peer must match the candidate's version, source, subject, symbol_ref, content and owner_scope. The peer must also be non-STATED, not stale and not archived. Otherwise `promote` raises `VersionConflictError`.
- **`tools/memory.py` (+113):**
  - Adds the write keys `source_id`, `expected_version` and `candidate_refs` (287).
  - Promote validates `candidate_refs` through `open_readonly_view`. If a candidate changed, it fails with "promotion candidates changed since review". It maps `VersionConflictError` to `E_VERSION` (1637-1773).
- **`tui.py` (+454):**
  - `_memory_expand_selected` (3488) uses `_memory_sources_and_state` (3147) and `open_readonly_view`. It refuses a foreign owner, keeps a page cache with previous and next, calls `related` and loads mutation and expansion receipts. The expansion receipts come from `telemetry.read_artifact_expansion_receipts_readonly`, `telemetry.py:358`.
  - `_memory_promote_selected` (3639) uses real same-owner corroboration.
- **`dashboard/server.py`:** tokens use `read_summary_readonly` and `read_memory_event_totals_readonly`. Artifacts gain a `captured` bucket. `_build_setup_section` now takes `(ctx, project_id)`. Provision review was refactored. The memory functions moved lines only.
- **`application.js` (+97):**
  - `downloadArtifactContentPages` gains `{expectedSha256}`.
  - Artifact export controls and `ACTION_FORMS` changed.
- **`cli.py` (+15):** `agent_connect_cmd` only. **`scripts/benchmarks/run.py` (+15):** `run_dashboard_user_journey` only.
- **Tests:**
  - `test_phase70_tui_usability.py` (+118) now commits `test_t28d_memory_workflows`.
  - `test_dashboard_memory_tokens.py` (+271).

## 5. Plan claims each gate must handle

1. **T04, T01 and T06 (L19 cross-owner corroboration).** The gap is still true in `maintenance.py`. It is closed on the public promote route when the caller passes `candidate_refs`. Gates must extend that route rather than duplicate it, and must close the legacy `candidate_sources` path, which still runs when `candidate_refs` is omitted.
2. **T06.** The strict v2 request and its legacy-adapter mapping must cover the new keys `source_id`, `expected_version` and `candidate_refs` (`tools/memory.py:287`).
3. **T07.** The TUI expand, related, receipts, paging and promote handlers already exist (`tui.py:3488`, `tui.py:3639`). T07 extends them. The L23 claim that the subject is fixed is stale.
4. **T02.** The TUI expansion allowlist comes from `_memory_sources_and_state` (`tui.py:3147`).
5. **T06 and T07.** `read_artifact_receipts_readonly` and `telemetry.read_artifact_expansion_receipts_readonly` are reuse points.
6. **T02 and T07.** The client-side `expectedSha256` in `downloadArtifactContentPages` must be reconciled with the proposed `payload_hash`.
7. **L28.** The `test_t28d_memory_workflows` evidence was re-established by the T001 full suite, not by the plan's original run.
8. Void; see the PM verification at the top.
9. **§2.1 item 3.** `MemoryOperation` is at `tools/memory.py:72`, not in request_models.
10. **T02 (L180).** `test_t02_receiver_digest_reconstruction` does not exist. It is a new T02 deliverable.
11. Everything else in §2 is unchanged and still true.
