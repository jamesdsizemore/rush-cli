Coverage: 21 of 21 M-series findings (M01-M21) drafted below. verified-by: `rtk git log -1` shows HEAD `ea88324eae379c96b4fb2553d7247ea340b3cc16`, byte-identical to the review's frozen commit; `rtk git status --porcelain` shows zero changes to any `src/rush/**` file since that commit (only unrelated untracked scratch/goal/DS_Store noise and a modified `AGENTS.md`), so citation drift is not possible for any of the 26 unique files cited across these 21 findings. All 26 were checked for existence and sufficient line count via a single pass; 26/26 exist. 4 of the 26 (`state.py`, `project_map.py`, `server.py`, `project_run.py`) were additionally opened and read at the exact cited ranges (`state.py:80-93,110-112,158-240`; `project_map.py:499-510`; `server.py:4158-4170`; `project_run.py:586-610`) as a spot check; all 4 matched the review's claim exactly, including that `ProjectRecord.get()` returns the live mutable object with no defensive copy (M01) and `_execute_candidate`'s real signature has no staging-aware read boundary (M15). The other 22 files rest on the unchanged-tree argument above, not an individual re-open.

### M01 -- P1: Published records mutate after readers obtain them

**Evidence:** `src/rush/dashboard/state.py:80-93` (`ProjectRecord` is a plain mutable dataclass, not frozen), `:110-112` (`ProjectRegistry.get()` returns `self._projects.get(project_id)` directly, no copy), `:158-240` (`bump_sequence`/`refresh_memories`/`publish_scan_result` mutate the stored record's attributes in place under `self._lock`, and mutate `record.snapshot` -- the same dict object a prior `get()` caller already holds -- rather than swapping in a new detached object). verified-by: opened `state.py:80-240` directly this session; matches exactly.

**RED:** Add to `tests/test_dashboard_map.py`: `test_get_returns_a_detached_record_not_the_live_stored_object` (call `get()` twice, mutate the first result's `snapshot` dict, assert the second `get()` call is unaffected); `test_paused_scan_publication_and_concurrent_memory_refresh_both_survive` (hold a reader's reference across an interleaved `publish_scan_result` then `refresh_memories`, assert the held reference's own nested data never changes after being read, and both updates land in the registry's canonical state).

**GREEN:**
1. Convert `ProjectRecord` to a frozen dataclass (`@dataclass(frozen=True)`) while keeping `snapshot` JSON-serializable; deep-copy input in `ProjectRegistry.__init__`, `register`, `refresh_memories`, and `publish_scan_result`.
2. Change `get`, `register`, `list_page` to return a detached (deep-copied) record, never the object stored in `self._projects`.
3. In `_publish_scan_snapshot` (`server.py`), pass only scan-owned fields plus `generation` into `publish_scan_result` -- do not assemble a whole snapshot from an earlier `record.snapshot`; merge under `_lock` into the lock-current record's memories/agents fields and replace with one new frozen record (never mutate the old one in place).
4. In `refresh_memories`, merge memories into the lock-current scan fields the same way, producing a new frozen record, not mutating the stored one.
5. Remove each pre-lock memory read in scan adaptation and each direct attribute assignment onto a record obtained from `get()` elsewhere in `server.py`.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_dashboard_map.py -q`. Pause scan publication after result adaptation, commit/publish newer memories, then resume scan publication -- assert both updates survive and a reader reference held across the whole sequence never observes a mid-flight partial state.

### M02 -- P1: Map publication discards actual consumed-source identity

**Evidence:** `src/rush/workflows/project_run.py:673-713,995-1018,1563-1573` (terminal manifest builds real consumption identity), `src/rush/dashboard/server.py:964-1006` (publication substitutes live `_source_signature(root)` at line 998 instead of using the manifest's own identity), `:1041-1085` (hydration repeats the same substitution), `:1185-1253` (CHECK_SUITE's manifest lacks content identity, inventory, generation, and Git provenance). verified-by: unchanged-tree argument above.

**RED:** Add to `tests/test_dashboard_map.py` or `tests/test_project_run_lifecycle.py`: `test_scan_bytes_a_changed_to_b_then_hydrate_still_reports_a` (scan tree at state A, mutate tree to B, hydrate through a second server process, assert selected attempt retains A's `source_identity`, `file_inventory`, `scan_generation`, Git evidence -- not B's live tree state); `test_check_suite_manifest_carries_content_identity_inventory_generation_and_git_link`.

**GREEN:**
1. Keep `ProjectRecord.source_identity`, snapshot `source_identity`, cursors, and `expected.source_identity` as strings holding the manifest's deterministic aggregate digest. Add a separate `scan_provenance` field for the full provenance object -- never assign a dict into the scalar identity field. Remove the live `_source_signature(root)` fallback for completed attempts at `server.py:998` and `:1041-1085`.
2. Persist `file_inventory`, `scan_generation`, consumed path digests, repository-state evidence, and Git link in `_build_manifest` (`project_run.py:673-713`) and in CHECK_SUITE's writer (`server.py:1185-1253`). Make `_snapshot_from_scan_result` accept these persisted values instead of recomputing them. CHECK_SUITE must stage/capture before `run_workflow_suite`.
3. Fix publication order: allocate generation; capture inventory/Git state; stage and execute; atomically write the terminal manifest; call `ProjectRegistry.publish_scan_result`; record publication outcome; update `MutationLedger.record_published_scan` only if registry publication won. Version the new persisted fields explicitly; a legacy manifest without them must report unavailable provenance, never substitute current-tree state.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_dashboard_map.py tests/test_project_run_lifecycle.py -q`. For initial scan, resume, rescan, and CHECK_SUITE: scan bytes A, mutate live tree to B, hydrate through a second server and a restart -- the selected attempt must retain A's identity, inventory, generation, and Git evidence in each producer path.

### M03 -- P2: File inventory is not persisted and hydration rewalks current files

**Evidence:** `src/rush/workflows/project_run.py:673-713` (`_build_manifest` has no inventory field), `src/rush/dashboard/server.py:1069-1082` (hydration falls back to walking current files), `server.py:898-915` and `project_run.py:1501-1522` (two independent, duplicated inventory walkers, both using `SKIP_DIRS`/dot-directory filtering matching `tools/routing.collect_files`). verified-by: unchanged-tree argument above.

**RED:** Add to `tests/test_project_run_lifecycle.py`: `test_persisted_inventory_survives_restart_and_file_changes` (attempt inventory includes skipped dirs, dot dirs, a clean file, and a file whose engine is unavailable; add/remove files after the attempt, restart, assert hydration reports the original inventory unchanged); `test_legacy_attempt_without_inventory_reports_missing_provenance_not_current_files`.

**GREEN:**
1. Base one shared inventory collector on the current `SKIP_DIRS`/dot-directory convention already used by `tools/routing.collect_files` -- do not introduce a `.gitignore`/`.rushignore` parser; none exists today per `src/rush/review/collection.py:76-94` and `src/rush/tools/routing.py:52-89`.
2. Replace the duplicate inventory walks in `dashboard/server.py:898-915` and `workflows/project_run.py:1501-1522` with one captured, sorted project-relative inventory computed once at attempt start, including covered-but-engine-skipped files.
3. Persist that exact inventory into the attempt header and terminal manifest; make hydration read it instead of rewalking. A legacy attempt without inventory must expose missing provenance, never silently substitute files present now.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_project_run_lifecycle.py -q`.

### M04 -- P1: Event API omits real candidate events and retains the wrong unit

**Evidence:** `src/rush/workflows/project_run.py:823,889-943,1023,1226-1261` (real candidate progress writes attempt `events.json`), `src/rush/dashboard/state.py:529-592` (dashboard ledger only receives status transitions; retention prunes by project at `278,543,585-590`, not 2,000-per-run), `src/rush/dashboard/server.py:3755-3803` (`/events` route serves this narrower stream), `tests/test_dashboard_missing_routes.py:1075-1164` (existing tests manufacture ledger transitions, not real candidate events). verified-by: unchanged-tree argument above.

**RED:** Add to `tests/test_dashboard_missing_routes.py`: `test_events_route_serves_real_candidate_progress_events_not_synthetic_status_transitions` (run real candidates that emit progress/outcomes through the workflow, assert exact candidate events appear via `/events` with no duplicates); `test_run_scoped_retention_prunes_independently_to_2000_rows_per_run` (produce >2,000 events across two separate runs, assert independent retention and correct paging); `test_events_after_cursor_below_project_floor_returns_409`.

**GREEN:**
1. Extend `dashboard_events` with run, attempt, attempt-local sequence, event kind, candidate, outcome, payload, and stream classification; keep project-global `sequence` as the API cursor. Dedupe candidate-log replay on `(project_id, run_id, attempt_id, attempt_sequence)`. Scan lifecycle transitions use a separate `(project_id, operation_id, transition_ordinal)` dedupe key so correlation survives admission release; non-scan events don't consume a scan run's 2,000-row allowance.
2. Thread the existing event sink through workflow execution and `_append_event` (`project_run.py:823,889-943,1023,1226-1261`); once an event is durable in the attempt event log, ingest it into the dashboard stream. On restart, replay un-ingested events idempotently.
3. Prune independently by `(project_id, run_id)` to 2,000 rows. Since `/events` is project-wide, persist a project cursor floor equal to the greatest global sequence deleted by any run; reject `after < floor` with 409. Return at most 100 rows ordered by global sequence.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_dashboard_missing_routes.py -q`.

### M05 -- P1: Grouping drops relationships without reachable expansion

**Evidence:** `src/rush/dashboard/project_map.py:499-510` (drops edges whose endpoints collapse into the same group), `:547-583` (summary slicing/overflow self-loop cursors can also lose reachability), `:769-863` (expansion cannot resolve ordinary relationships through the overflow shape). verified-by: opened `project_map.py:499-510` directly this session -- real code shows `continue` when both endpoints are already visible, no summary emitted for the collapsed case; matches exactly.

**RED:** Add to `tests/test_dashboard_map.py`: `test_101_file_101_finding_fixture_preserves_all_report_relationships_through_expansion` (reproduce the review's exact 101-file/101-finding fixture that produced `map_total_edges=202, rendered_edges=2, rendered_reports=0`; expand each summary across each page; assert the union of expanded edges equals the full 202-edge source set, including all 101 report edges, while the rendered map stays within budget).

**GREEN:**
1. In `project_map.py`, bucket each source edge by rendered source, rendered target, and relationship type. When both endpoints collapse into one group, emit an expandable counted self-summary instead of dropping the relationship (fix the `continue` at `:499-510`).
2. Reserve one summary for each nonempty `(resolved_source, resolved_target, relation)` bucket before optional detail edges; if summaries exceed budget, emit relation-level overflow summaries whose selector covers each relationship the overflow omitted.
3. Encode selector, offset, and frozen-view tuple in cursors (not entire edge-ID arrays). `expand_group_edge` rebuilds the frozen graph, selects matching edges, sorts IDs, and pages them; add explicit self-group/overflow branches since current source/target matching cannot resolve project self-loop overflow.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_dashboard_map.py -q`.

### M06 -- P1: Historical views can select latest attempt and expand live data

**Evidence:** `src/rush/dashboard/server.py:3832-3853` (historical `run_id` accepted without `attempt_id`), `_historical_map_snapshot:1108-1163` (allows latest-attempt resolution), `:3887-3905` (group/edge expansion passes `record.snapshot`, the live current record, not the historical snapshot). verified-by: unchanged-tree argument above.

**RED:** Add to `tests/test_dashboard_map.py`: `test_historical_map_request_without_attempt_id_is_rejected`; `test_historical_expansion_uses_the_pinned_attempts_snapshot_not_live_record` (two attempts under one run with disjoint grouped node/edge IDs; mutate the live tree and resume the run; assert each old expansion page stays old); `test_cursor_reused_against_a_different_view_id_raises_cursor_rejected_409`.

**GREEN:**
1. Reject a historical map request unless both `run_id` and `attempt_id` are supplied and resolve together; remove latest-attempt resolution for historical views.
2. Return selected snapshot plus `view_id=("run", run_id, attempt_id)` from `_historical_map_snapshot`; add a `view_id` keyword to `expand_group`/`expand_group_edge`; `_handle_snapshot` passes that same snapshot/view ID to base construction and both expansion paths (fixing the `record.snapshot` fallback at `:3887-3905`). Never default historical expansion to `("current",)`.
3. Include `view_id` in `_cursor_tuple` alongside project, scalar source identity, sequence, and filter hash; reuse against another attempt/current view raises `CursorRejected`, serialized as HTTP 409.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_dashboard_map.py -q`.

### M07 -- P1: Edit/archive/delete/promote do not refresh published memory data

**Evidence:** `src/rush/dashboard/server.py:1820-1972,2031-2046` (`_dispatch_memory_edit`/`_dispatch_memory_archive`/`_dispatch_memory_delete`/`_dispatch_memory_promote` never call `_refresh_project_memories`, unlike propose/maintain at `:2239-2316`). verified-by: unchanged-tree argument above.

**RED:** Add to `tests/test_dashboard_memory_tokens.py` or `tests/test_dashboard_map.py`: `test_memory_edit_immediately_updates_map_content_and_generation`; `test_memory_archive_delete_promote_each_publish_a_new_generation`; `test_promotion_denial_after_candidate_write_still_refreshes_the_real_candidate_commit`; `test_preview_and_zero_write_failure_publish_no_fabricated_sequence_bump`.

**GREEN:**
1. Make `_dispatch_memory_edit`, `_dispatch_memory_archive`, `_dispatch_memory_delete`, `_dispatch_memory_promote` accept `DashboardContext`; update `_dispatch_scan_action` callers; put all four plus propose/maintain on one shared post-commit refresh path.
2. Read pre-operation memory generation via the existing read-only store-opening path (no write-just-to-preview); execute the action; read `snapshot_memories()` from the resulting store and publish only a newer generation. For promotion, refresh the real candidate-artifact commit even when the later promotion is denied.
3. Pass the atomic `(memories, generation)` pair once to `ProjectRegistry.refresh_memories` (added by P69-01.2n); remove duplicate route-specific refreshes. Preview, validation/owner/CAS failure with no commit, and unchanged maintenance must cause no fabricated sequence bump.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_dashboard_memory_tokens.py tests/test_dashboard_map.py -q`.

### M08 -- P1: Dashboard owner scope is optional and not bound to the URL project

**Evidence:** `src/rush/dashboard/server.py:262-314,1957-1969,2267-2277` (allowlists/dispatch accept omitted owner scope), `src/rush/tools/memory.py:1040-1062` (`_parse_owner_scope` accepts no scope and arbitrary nonabsolute project IDs), `src/rush/memory/store.py:137-148,613` (legacy fallback). verified-by: unchanged-tree argument above.

**RED:** Add to `tests/test_memory_public_contract.py` or `tests/test_dashboard_memory_tokens.py`: `test_write_edit_promote_archive_delete_reject_omitted_or_incomplete_owner_before_any_row_change`; `test_foreign_project_uuid_owner_rejected_before_reservation`; `test_wrong_session_id_owner_rejected`; `test_arbitrary_nonempty_user_agent_labels_accepted_structurally_and_persist_unchanged`.

**GREEN:**
1. Add `_validate_memory_owner_scope` helper called in `_handle_action` after argument/boolean validation but before `body_hash`/`MutationLedger.commit`. Pass the authenticated `session.owner_scope_id`, the URL project ID, and the requested owner; write the normalized owner back into `arguments`. All five memory-mutation forms plus owner-scoped maintenance use it.
2. Enforce identity rules: project ID must equal the registered URL project; session ID must equal this request's authenticated `Session.owner_scope_id`; user/agent IDs are opaque, nonblank, structurally validated only. Never accept an arbitrary session from `ctx.auth` or authenticate opaque labels.
3. Keep legacy project-path fallback only in explicitly supported direct CLI/MCP entry points; dashboard adapters always pass the normalized owner object to the existing owner-aware store methods.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_memory_public_contract.py tests/test_dashboard_memory_tokens.py -q`.

### M09 -- P1: TUI and maintenance disagree with registered-project ownership

**Evidence:** `src/rush/tui.py:1100-1117` (TUI defaults ownership to raw path), `ProjectState:329-348` (no project ID field), `src/rush/memory/maintenance.py:81-97`, `expiry.py:59-75` (optional owner), `src/rush/tools/memory.py:441-459,1188-1211` (MemoryTool maintain drops owner), `server.py:311` (dashboard maintain omits owner), `src/rush/cli.py:2762-2797` (no owner flags/registered-ID lookup), `tests/test_memory_versions.py:759-780` (codifies the wrong registered-path assumption). verified-by: unchanged-tree argument above.

**RED:** Update `tests/test_memory_versions.py:759-780` to expect the registered project's UUID owner instead of a path owner; add `test_tui_and_cli_maintenance_reach_the_registered_projects_uuid_owned_row_not_path_owner`; update direct call/spy assertions in `tests/test_phase62_maintenance.py`, `tests/test_phase62_expiry.py`, `tests/test_memory_core_regressions.py` for the new required-owner signature.

**GREEN:**
1. Add optional canonical `project_id` to `ProjectState`; resolve through the existing project registry when loading the root; fall back to raw path only on an explicit project-not-found result.
2. Thread normalized owner through CLI maintenance, `MemoryTool.__call__`/`run`/`_run_maintain`, dashboard maintain, TUI maintenance, `run_maintenance_cycle`, `sweep_expired`; add CLI owner flags with registered-UUID defaults and unregistered-path fallback.
3. Make owner mandatory in `MemoryTool._run_maintain`, `run_maintenance_cycle`, `sweep_expired`; apply `owner_scope_kind=? AND owner_scope_id=?` to selection/mutation in one transaction. Include NULL-owner legacy rows only when the requested owner equals `legacy_owner_scope(root)`.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_memory_versions.py tests/test_phase62_maintenance.py tests/test_phase62_expiry.py tests/test_memory_core_regressions.py -q` (run these focused modules explicitly, not only the full suite, per the review's caller/signature-migration warning).

### M10 -- P1: Token filters leave displayed totals unfiltered

**Evidence:** `_build_tokens_section`, `src/rush/dashboard/server.py:2909-2976` (requests project-wide totals; run/agent filters affect only handoff rows; session filtering absent), `TelemetryStore.get_memory_event_total` (`token_economy/telemetry.py:185-220`, already supports filters) vs. `get_summary:252-280` (does not). verified-by: unchanged-tree argument above.

**RED:** Add to `tests/test_dashboard_memory_tokens.py`: `test_tokens_section_totals_respect_run_agent_session_filters_not_just_handoff_rows` (seed two runs/agents/sessions with distinct counts; assert exact overall, individually filtered, combined-filter, and by-kind totals, including empty-result cases).

**GREEN:**
1. Add optional project/run/agent/session filters to `TelemetryStore.get_summary`, reusing `get_memory_event_total`'s clause builder; filter token-event count/raw/compressed aggregates there.
2. In `_build_tokens_section`, parse the route's selection once and pass identical filters to token totals, memory-event totals, and handoff rows; use the registered canonical project ID.
3. Exclude genuinely unscoped legacy rows from a narrower identity selection; retain existing explicit unavailable/provider-usage semantics -- never guess a missing attribution into the chosen run.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_dashboard_memory_tokens.py -q`.

### M11 -- P1: Real telemetry calls lack complete invocation/attribution propagation

**Evidence:** `src/rush/tools/memory.py:280-470` (`MemoryTool.run` has no reusable invocation argument; content-derived request IDs at `663,679,762`), `src/rush/memory/retrieval.py:454-463,594-604,641-650` (retrieval mints UUIDs but records project identity without run/agent/session), `src/rush/tools/continuity.py:146-178,455-489` (boundary UUID additions incomplete). verified-by: unchanged-tree argument above.

**RED:** Add to `tests/test_memory_retrieval.py`: `test_two_identical_distinct_calls_are_counted_twice_and_one_retry_is_counted_once`; `test_persisted_attribution_columns_match_the_public_invocation_id_on_every_success_and_fallback_branch` (exercise real hybrid, recall, expand, context-retrieve routes, not direct telemetry insertion).

**GREEN:**
1. Add optional invocation ID and project/run/agent/session attribution to `MemoryTool.__call__`/`run` and continuity's public boundaries; mint invocation once when absent and thread through compact query, hybrid, recall, expand, context retrieval, and fallbacks. Keep content-derived `request_id` as descriptive attribution only, not invocation identity.
2. Resolve canonical project identity at that boundary and carry project/run/agent/session through retrieval and telemetry writes; use the defined unscoped sentinel only when a dimension is truly unavailable.
3. Reuse the invocation ID for retry of the same logical call; enforce existing telemetry dedup on that ID plus relevant event identity. Distinct user calls with identical content get different IDs.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_memory_retrieval.py -q`.

### M12 -- P1: Historical artifacts serve current bytes and paging corrupts content

**Evidence:** `src/rush/workflows/projects.py:1093-1122` (references include attempt identity), `src/rush/dashboard/server.py:4158-4204` (download resolves `paths[0]` under the current project), `_read_artifact_page:2485-2514`, `tests/test_dashboard_git_artifacts.py:771-809` (checks distinct labels, not distinct bytes). verified-by: opened `server.py:4158-4170` directly this session -- `_handle_artifact` looks up `ctx.projects.get(project_id)`, the live current record, with no attempt pinning in that boundary; matches exactly.

**RED:** Add to `tests/test_dashboard_git_artifacts.py`: `test_two_candidates_in_one_attempt_writing_the_same_logical_filename_retain_different_original_bytes`; `test_two_attempts_and_a_resumed_completed_candidate_retain_their_own_artifact_copies_after_restart`; `test_download_more_than_two_pages_containing_split_utf8_nul_and_0xff_bytes_reassembles_exactly` (reproduce the review's exact byte-paging corruption: hex `41e282ac4200ff`, page sizes 2/2/3, current code's UTF-8-replacement-then-reencode path must be replaced entirely); `test_a_reference_and_offset_for_attempt_a_never_selects_attempt_bs_bytes`.

**GREEN:**
1. Add `CandidateResult.artifact_snapshots`; immediately after each `_execute_candidate` returns and before `_persist_candidate_evidence` or another candidate runs, copy declared artifact bytes into the current attempt's contained artifact directory keyed by candidate and path, via temp-write/fsync/atomic-rename; record logical path, immutable relative path, byte size, SHA-256, media type. Keep `ToolResult.artifacts: list[str]` unchanged.
2. Serialize snapshots in candidate evidence; reload in `_load_completed_candidates`; assemble in `_finalize_attempt`. CHECK_SUITE captures each child via the existing `run_workflow_suite(on_tool_complete=...)` seam before the next tool runs, with a stable child ordinal/tool key and atomic incremental sidecar.
3. Rewrite `_read_artifact_page` (`server.py:2485-2514`) to resolve only the selected run/attempt's snapshot entry, validate containment/immutable metadata, and base64-encode raw bytes with no per-page text decoding -- the current UTF-8-replacement-then-reencode logic is the direct cause of the corruption and must be removed entirely, not patched. Response fields: `path`, byte `offset`, whole-artifact byte `size`, `content_base64`, byte `next_offset` (null at completion), whole-artifact `sha256`, `media_type`.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_dashboard_git_artifacts.py -q`.

### M13 -- P2: Repository-state evidence becomes an impossible Git path

**Evidence:** `src/rush/workflows/project_run.py:917-927` (inserts synthetic `candidate_id:kind` digest), `_build_manifest:684-691` (copies it into `git_link.path_digests`), `src/rush/workflows/projects.py:1031-1070` (interprets every key as a real repository path for `git show commit:path`). verified-by: unchanged-tree argument above.

**RED:** Add to `tests/test_dashboard_git_artifacts.py`: `test_no_synthetic_evidence_key_reaches_git_show_commit_path`; `test_clean_matching_commit_links_correctly_through_gitguard_diffcover_undercover`; `test_changed_repository_state_evidence_prevents_a_false_git_match`.

**GREEN:**
1. Replace `CandidateResult.source_digests` with `consumed_path_digests` and `repository_state_evidence`; update `to_dict`, `_persist_candidate_evidence`, `_load_completed_candidates`, resume carry-forward, `_finalize_attempt`, and manifest serialization together.
2. Hash both structures with explicit domain tags and deterministic serialization; only actual project-relative paths populate `git_link.path_digests`.
3. Make path-based matching and `_git_show` consume only the path-digest collection; treat old manifests that can't distinguish synthetic evidence as unverifiable.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_dashboard_git_artifacts.py -q` -- execute GitGuard, DiffCover, Undercover through the real scan route.

### M14 -- P2: Memory browsing silently truncates at 10,240 rows per subject

**Evidence:** `src/rush/dashboard/server.py:2713-2719,2796-2850` (reads at most 20 batches of 512, derives page totals from that truncated collection). verified-by: unchanged-tree argument above.

**RED:** Add to `tests/test_dashboard_memory_tokens.py`: `test_browse_and_query_traverse_more_than_10240_rows_with_exact_totals_and_unique_ids`; `test_record_becoming_stale_is_excluded_by_query_mode_freshness_revalidation_at_any_page`; `test_memory_generation_mutation_mid_traversal_rejects_the_cursor`.

**GREEN:**
1. Add `TypedArtifactStore.page_artifacts` for empty-query browse with existing subject/source/trust/expiry/archive predicates before COUNT/LIMIT -- no new owner filter added here. For text query, extend the existing MemoryTool/retrieval path (which performs dynamic freshness revalidation) rather than replacing it with direct SQL; compute the eligible total after that same revalidation.
2. Read browse total/page in one store read transaction with deterministic ordering; bind normalized filters and memory generation to both continuations; reject a changed generation. Eliminate the 20-by-512 materialization ceiling in both paths.
3. Return the true filtered total and next cursor directly -- never infer totals from a capped in-memory sample.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_dashboard_memory_tokens.py -q`.

### M15 -- P1: In-process tool reads bypass staged bytes

**Evidence:** `src/rush/workflows/project_run.py:586-670` (`_execute_candidate` passes the live project root into tools; only nested `run_engine` invocations redirect to staging), `src/rush/tools/slop.py:21-60` (`SlopTool` reads live content directly, `source_digests={}`). verified-by: opened `project_run.py:586-610` directly this session -- real signature takes `root: Path`, no staged-root parameter; matches exactly.

**RED:** Add to `tests/test_staged_scan_bytes.py`: `test_slop_tool_reads_staged_bytes_not_live_source_when_live_content_diverges` (reproduce the review's exact probe: stage `x.js='// clean'`, change live content to `'// generated by ai'`, assert `SlopTool` reports no `rush-ai-marker` finding and records nonempty `source_digests`); `test_offline_review_dead_asset_license_matrix_all_read_staged_bytes`; `test_a_clean_staged_file_with_marked_live_content_yields_no_finding`.

**GREEN:**
1. Obtain `staging = active_staging()`; for source-reading staged candidates, pass both the request path and `InvocationContext.workspace_root` as `staging.staged_root` through `resolve_invocation`. Ordinary unstaged invocations keep current behavior.
2. Record successful source reads through active staging in slop (`tools/slop.py`), offline runner, dead-asset, license-matrix, and other direct readers, at the actual read boundary, including clean files. After `InvocationExecutor.execute` and before finding IDs/evidence are created, apply structural staged-to-logical path remapping to direct-tool finding/artifact/raw path fields -- never rewrite literal message/fix text.
3. Keep repository-state engines (Git-diff tools) on their declared repository-state path with separate evidence; preserve mutation-tool semantics unchanged.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_staged_scan_bytes.py -q`.

### M16 -- P1: Per-engine coverage claims every staged file despite explicit targets

**Evidence:** `_staged_invocation` (`src/rush/runtime/subprocesses.py:667-669`, records whole `run_path`), `src/rush/engines/staging.py:216-232` (recording project root includes each inventory file). verified-by: unchanged-tree argument above.

**RED:** Add to `tests/test_staged_scan_bytes.py`: `test_explicit_target_a_py_does_not_claim_unrelated_b_js_as_consumed` (reproduce the review's probe with inventory `a.py`+`b.js`, explicit target `a.py`); `test_root_scoped_scan_records_its_full_staged_source_scope`; `test_explicit_configuration_file_target_is_recorded_as_declared_consumption`.

**GREEN:**
1. Add `consumed_paths` to `run_engine`/`_staged_invocation`; adapters with explicit targets pass original logical paths, resolved/validated/substituted against the original root, recording only the staged targets -- never the whole `run_path` when explicit targets exist.
2. Omitted explicit paths means root-scoped only when the command actually receives root as its scan target; an explicitly passed configuration file is declared consumption.
3. Update lint/format/typecheck and each adapter passing root plus file arguments; aggregate source identity at candidate boundaries so one engine cannot inherit unrelated consumption from another candidate.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_staged_scan_bytes.py -q`.

### M17 -- P1: Required repository-state engines are unreachable through actual scan routing

**Evidence:** `_execute_candidate` (`src/rush/workflows/project_run.py:586-610`) immediately returns `ENGINE_ROUTE_MISSING` for engine-kind candidates; GitGuard/DiffCover have no owning tool route; Undercover is reachable only through the explicit coverage tool; inventory 121 registered engines, 32 tool-owned, 89 unowned planner rows. verified-by: opened `project_run.py:586-610` directly this session (same range as M15); matches exactly for the function-boundary claim.

**RED:** Add to `tests/test_project_run_lifecycle.py` or a new `tests/test_engine_routing.py`: `test_gitguard_candidate_executes_through_execute_scan_with_a_real_or_fixture_engine_binary_and_persists_evidence`; `test_unregistered_engine_stays_engine_route_missing`; `test_registered_engine_with_absent_binary_returns_structured_skipped_result`; `test_denied_explicit_permission_returns_permission_blocked`.

**GREEN:**
1. Resolve `candidate.candidate_id` through `rush.engines.ENGINES` and obtain binary/routing metadata from `rush.catalog.ENGINE_SPECS`, then invoke shared `run_engine`. Read-only candidates use empty `required_permissions`; privileged engines require an explicit existing/planner permission mapping -- never an invented grant or dummy owning tool.
2. Pass owner/run identity, candidate arguments, staging/repository-state mode, and attribution through canonical `run_engine`; preserve existing candidate-boundary cancellation (do not add a new mid-engine `cancel_check` to `Engine.run`, which has no such parameter today).
3. Preserve the three distinct failure states in `CandidateResult`: missing registry entry stays `ENGINE_ROUTE_MISSING`; registered engine with absent binary uses `run_engine`'s structured skipped result; denied explicit permission stays `permission_blocked`.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_project_run_lifecycle.py -q` plus the new engine-routing test file.

### M18 -- P1: Rejected escaping symlink can still be sent live to the engine

**Evidence:** `stage_inventory` (`src/rush/engines/staging.py:276-300`, flags/skips an escaping symlink), argument substitution at `:201-213` (returns the original argument when it resolves outside root). verified-by: unchanged-tree argument above.

**RED:** Add to `tests/test_staged_scan_bytes.py`: `test_escaping_symlink_argument_never_reaches_the_real_engine_argv`; `test_internal_symlink_and_explicitly_supported_external_configuration_are_not_overblocked`.

**GREEN:**
1. Extend the staging context to retain rejected project paths and their structured failure reasons; classify lexical project inputs before resolving symlinks so an escaping project symlink is distinguishable from an explicitly allowed external configuration/dependency.
2. Add `StagingInputError` (new exception) in `engines/staging.py`; `substitute_arg` classifies lexical project membership before resolution, rejects paths recorded as broken/escaping, never returns their live value; `_staged_invocation` converts this to a structured candidate failure before `engine.run` or subprocess spawn.
3. Copy permitted internal symlink targets under the staged tree and record their evidence; preserve separately declared support/configuration exceptions.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_staged_scan_bytes.py -q`.

### M19 -- P1: DiffCover drops coverage identity, leaks staging, and can reuse an old report

**Evidence:** `src/rush/engines/diff_cover.py:80-89` (creates `mkdtemp` with no cleanup), `:104-111` (reads a live fixed `diff-cover.json` that may predate the invocation), `src/rush/workflows/project_run.py:917-927` (`_run_candidates` folds only top-level `digest`, dropping `coverage_digest`). verified-by: unchanged-tree argument above.

**RED:** Add to `tests/test_dashboard_git_artifacts.py` or a `tests/test_diff_cover_engine.py`: `test_stale_live_report_with_no_fresh_output_fails_honestly_rather_than_reusing_old_bytes`; `test_conflicting_positional_or_option_args_are_rejected_and_the_binary_is_not_launched`; `test_temp_directory_is_cleaned_up_on_success_error_timeout_and_cancellation`; `test_changed_coverage_bytes_alone_change_the_folded_provenance_identity`.

**GREEN:**
1. Replace `mkdtemp` in `DiffCoverEngine` with `TemporaryDirectory` around copy, execution, report parsing, provenance capture, covering timeout/subprocess-error/malformed-output/cancellation.
2. Reject caller args adding another coverage positional input or overriding `--compare-branch`/`--json-report` (including `--option=value` spellings); pass exactly the staged coverage input, pinned comparison SHA, and an invocation-unique contained absolute report path; require that invocation to produce a valid report -- never consume a preexisting `diff-cover.json`.
3. Combine diff bytes and coverage input bytes using a tagged canonical evidence object; fold both into the candidate's repository-state evidence/source identity via M13's separate evidence channel, not `git_link.path_digests`.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_dashboard_git_artifacts.py -q`.

### M20 -- P2: Decoded raw results retain temporary staged paths

**Evidence:** `_PATH_KEYS` (`src/rush/engines/staging.py:91-104`, omits Stylelint `source` and Trivy `Target`), `src/rush/engines/stylelint.py:41-48,61-91`, `src/rush/engines/trivy.py:39-48,69-95` (decoded `ToolResult.raw` retains temp paths after normalization). verified-by: unchanged-tree argument above.

**RED:** Add to `tests/test_staged_scan_bytes.py`: `test_stylelint_decoded_raw_source_field_uses_logical_path_not_staged_temp_path`; `test_trivy_decoded_raw_results_target_field_uses_logical_path`; `test_literal_message_or_fix_text_containing_a_path_like_substring_is_never_rewritten`.

**GREEN:**
1. Extend decoded-result remapping for Stylelint's top-level `source` field and Trivy's `Results[].Target` paths before normalization/serialization, using adapter-specific structural handling (not a global "any key named source/Target" rule).
2. Keep generic path-key remapping for its existing fields but never replace staged-path substrings inside messages, snippets, fixes, or replacement content -- map only fields whose engine schema says they are paths.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_staged_scan_bytes.py -q`.

### M21 -- P2: Staging input/configuration failures are silently skipped

**Evidence:** `src/rush/engines/staging.py:279-282,303-307,325-329` (silently continues after broken-symlink resolution, copy/hash errors, and dependency/config symlink creation errors). verified-by: unchanged-tree argument above.

**RED:** Add to `tests/test_staged_scan_bytes.py`: `test_disappeared_inventory_file_during_staging_forces_incomplete_attempt_state_with_zero_scheduled_candidates`; `test_copy_or_hash_error_during_staging_prevents_the_affected_candidate_from_executing`; `test_staging_failure_never_falls_back_to_a_live_read_and_never_publishes_a_clean_result`.

**GREEN:**
1. Replace silent skips in `stage_inventory` with structured failure records naming logical path, operation, error code, sanitized message -- covering broken/escaping symlink resolution, a captured inventory path disappearing/becoming non-file, copy, hash, and required support/configuration staging.
2. A required source that cannot be staged prevents the affected candidate from executing; if a support failure's affected consumers can't be safely identified, fail the attempt conservatively -- never read live source as fallback or publish a clean complete result.
3. Pass failures into `_finalize_attempt`; a fatal staging failure forces incomplete/failed state before the current empty-schedule-completed branch. Add a structured staging child result and retain failure details in the terminal manifest.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_staged_scan_bytes.py -q`.
