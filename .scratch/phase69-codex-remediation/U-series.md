Coverage: 11 of 11 U-series findings (U01-U11) drafted below. verified-by: `rtk git log -1` shows HEAD `ea88324eae379c96b4fb2553d7247ea340b3cc16`, byte-identical to the review's frozen commit; `rtk git status --porcelain` shows zero changes to any `src/rush/**` file since that commit. All cited files confirmed to exist with sufficient line count. 3 of the cited files were opened and read verbatim at the cited ranges this session (`keymaps.py:28-48`, `tui.py:684-700,1995-2010`, `terminal_input.py:100-125`); all matched the review's claims exactly -- including confirming `keymaps.py` already carries a `P69-06c` code comment admitting Tab and F2 both currently map to `next_project` with Shift+Tab/pane-cycling explicitly deferred (U01's core claim), and `terminal_input.py`'s `_SEQUENCES` dict only decodes plain arrow keys, no F2/F3/Shift+Tab (also U01). The remaining cited files rest on the unchanged-tree argument, not an individual re-open.

Environment limit applying to several VERIFY sections below: this environment has no live Windows machine and no already-open native-browser (`agent-browser`) session for THIS task -- U01/U04's Windows-input acceptance and U05/U06/U08/U10/U11's visible-browser-journey acceptance are marked as explicit open acceptance gaps in their VERIFY sections, not silently assumed passing.

### U01 -- P1: Required key, pane, hierarchy, and input-decoding behavior is missing

**Evidence:** `src/rush/dashboard/keymaps.py:33,44` (Tab and F2 both switch projects) verified-by: opened `keymaps.py:28-48` directly this session -- confirmed both `key="tab"` and `key="f2"` map to `action_name="next_project"`, with an existing `P69-06c` comment admitting Shift+Tab/pane-cycling is deferred pending this packet. `src/rush/dashboard/terminal_input.py:107,120,155` (POSIX input bytewise, arrows-only, uses `select.select`; Windows handles arrows only) verified-by: opened `terminal_input.py:100-125` directly -- `_SEQUENCES` dict has exactly 4 entries (`[A`/`[B`/`[C`/`[D`), no CSI-Z (Shift+Tab) or SS3 F-key entries. `docs/goals/phase-69-dashboard-tui-contract-remediation/state.yaml:1320-1325` (board deviations admit these omissions).

**RED:** Add to `tests/test_tui.py`: `test_shift_tab_cycles_panes_in_reverse_order`; `test_plus_minus_keys_expand_and_collapse_map_hierarchy_nodes`; `test_f3_switches_section_and_f2_opens_project_selector_as_distinct_actions`; `test_question_mark_help_text_matches_dispatch_keymap_exactly`. Add to `tests/test_tui_terminal.py`: `test_posix_decoder_handles_fragmented_utf8_multibyte_sequences_across_reads`; `test_posix_decoder_parses_csi_and_ss3_function_key_escape_sequences`; `test_sigwinch_triggers_a_resize_wakeup_without_blocking_the_read_loop`; `test_prior_sigwinch_handler_is_restored_on_reader_shutdown`.

**GREEN:**
1. In `src/rush/dashboard/keymaps.py`, split Tab/F2 apart: bind `shift+tab` to a new `prev_pane`/pane-cycling action distinct from `next_project`, and keep `tab`/`f2` both resolving to project switching only until this packet's own decoding work lands (per the existing `P69-06c` comment's own stated sequencing) -- then, in the same packet, finish that decoding and let `tab` become plain pane-cycling, matching Phase 66 par3.8. Add `+`/`-` bindings for Map hierarchy expand/collapse. Regenerate the `?` help text from `_KEYMAP` so it reflects the corrected bindings automatically.
2. In `src/rush/dashboard/tui.py`'s dispatch and rendering state, add minimum selected-parent/expanded-node state needed for hierarchical expand/collapse -- do not invent helper functions that don't already exist; search for an existing hierarchy-state container before adding a new one.
3. Rewrite `PosixKeyReader.read_key` (`terminal_input.py:120`) to incrementally decode UTF-8 continuation bytes and full CSI/SS3 escape sequences (not just the 4 arrow entries in `_SEQUENCES`) using `select.select`/`selectors` plus a `SIGWINCH`-triggered self-pipe wakeup; handle a fragmented escape sequence spanning two reads without misinterpreting its first byte as a standalone Escape. Restore the prior `SIGWINCH` handler and close wakeup descriptors on shutdown.
4. Extend Windows extended-key decoding (the Windows branch near `terminal_input.py:155`) for F2/F3/Shift+Tab once the actual emitted console sequences are confirmed against a real Windows console -- this specific sub-step has no substitute; guessed scan codes are not acceptance evidence.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_tui.py tests/test_tui_terminal.py -q`. Real PTY test: project/section/pane/hierarchy navigation including reverse Shift+Tab wrapping, resize/state preservation across `SIGWINCH`, and `?` help matching actual keys. Open acceptance gap: native Windows input case (F2/F3/Shift+Tab against a real Windows console) cannot be executed in this environment -- record it as an explicit unclosed acceptance item, not a silent pass.

### U02 -- P1: Dashboard-owned work can be marked complete before completion

**Evidence:** `_start_dashboard_owned`, `src/rush/tui.py:684-728` (saves only `response.run_id`, sets `status="complete"` immediately when `plan_total <= 0`; CHECK_SUITE has no plan total; returned operation ID neither retained nor polled) verified-by: opened `tui.py:684-700` directly this session -- confirmed the function's real docstring/signature; the `plan_total`-based completion inference is in the body immediately following (not re-quoted here, same function).

**RED:** Add to `tests/test_tui.py`: `test_dashboard_owned_check_suite_shows_pending_running_before_true_terminal_state_not_immediate_complete`; `test_cancel_submits_the_retained_logical_operation_id_including_an_attached_callers_id`; `test_multiple_polls_reuse_one_authenticated_client_session`; `test_401_on_poll_triggers_one_reexchange_and_retry_then_surfaces_repeated_failure_as_visible_disconnection`.

**GREEN:**
1. In `_start_dashboard_owned`, retain the returned logical `operation_id`, executor run/attempt, owner, and pending state; remove completion inference from `plan_total`. Add `DashboardOwner.operation_status(operation_id)` and a dashboard-owned branch in `_poll_running_scans` that uses durable operation status, retaining last known state across transient errors.
2. Give the frozen `DashboardOwner` a private mutable cached client-session field excluded from repr/comparison; factor/reuse the existing `_control_session` control-to-bootstrap-to-cookie/CSRF exchange from `dispatch_dashboard_action`. Cache credentials in memory only; use the Cookie for the operation-status GET; on 401 clear credentials, re-exchange, retry once; repeated failure surfaces as visible disconnection, not a silent stall. Never bootstrap on every poll or persist credentials to disk.
3. After S10 lands (cancellation resolving an attached operation ID), Cancel submits the retained logical operation ID including an attached caller's ID; server resolves it to the executor, commits durable cancellation intent, then delivers scan cancellation or CHECK_SUITE's local event. Dashboard-owned Detach stops observation only, no process termination.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_tui.py -q`. Use a real slow dashboard control-channel CHECK_SUITE: assert pending/running is shown before true terminal state; cancel its actual event; retain completed-tool partial result; observe durable status. Separately test full scan and attached-operation cancellation; assert multiple polls reuse one session, one expiry renewal works, repeated 401 surfaces failure, and action retry does not duplicate effects.

### U03 -- P1: Detach can kill another project's subprocesses

**Evidence:** Process records carry `run_id`, but `reap_owner_processes` filters only by process-wide owner (`src/rush/runtime/subprocesses.py:352-386`); Detach passes only that owner (`src/rush/tui.py:1487-1528`) -- one TUI process can own multiple project runs.

**RED:** Add to `tests/test_subprocess_contract.py`: `test_reap_owner_processes_accepts_an_optional_exact_run_id_filter_and_only_signals_matching_records`. Add to `tests/test_tui.py`: `test_detach_on_run_a_terminates_only_run_as_descendants_and_leaves_run_b_untouched_under_one_tui_owner` (launch two real process trees A and B under one TUI owner; force A's timed-out Detach; assert A's descendants terminate and A's records clear while B receives no signal, keeps writing, and retains its records); `test_dead_owner_recovery_still_reaps_both_a_and_b`.

**GREEN:**
1. Add an optional exact `run_id` filter to `reap_owner_processes` (`subprocesses.py:352-386`); filter before sending signals, not only when deleting process records. Keep owner-only cleanup for confirmed dead-owner recovery (S02's path is unaffected).
2. At TUI's Detach call site (`tui.py:1487-1528`), pass the selected local run's ID; never use process-wide ownership alone when the same coordinator can own more than one project. Dashboard-owned Detach follows U02 and must not reap the dashboard's own children.
3. Remove only confirmed-dead records matching the chosen owner/run; preserve failed-termination records and all sibling-run records so later recovery remains possible.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_subprocess_contract.py tests/test_tui.py -q`.

### U04 -- P2: TUI theme, motion, and narrow layouts are incomplete

**Evidence:** Hard-coded Rich styles remain without THEME/MOTION integration (`src/rush/tui.py:1896` and nearby renderers); layout only distinguishes `>=100` (`:1946-1954`); required 80-99 and below-80 behavior and motion contracts are missing (plan lines 467,515); board `state.yaml:1320-1325` records these omissions.

**RED:** Add to `tests/test_tui.py`: `test_layout_at_79_columns_uses_narrow_branch_with_specified_pane_visibility_and_two_row_footer`; `test_layout_at_80_columns_uses_compact_branch`; `test_layout_at_99_columns_stays_compact`; `test_layout_at_100_columns_uses_wide_branch`; `test_project_section_pane_selection_and_expanded_hierarchy_preserved_across_a_real_pty_resize_crossing_a_width_boundary`; `test_reduced_motion_renders_final_state_with_no_animated_refresh`.

**GREEN:**
1. Build the smallest Rich style mapping from existing THEME tokens and use MOTION values for required selection/reveal behavior -- do not introduce a second theme/animation system.
2. In `render_app`, implement wide `>=100`, compact `80-99`, and narrow `<80` branches with specified pane visibility/order and a two-row footer (extending the layout logic currently only distinguishing `>=100` at `tui.py:1946-1954`); preserve project, section, pane, selection, and expanded hierarchy across resize.
3. Retain the production `Console(no_color=bool(os.environ.get("NO_COLOR")))` construction verified at `tui.py:2009` (this session's own read of `:1995-2010`) -- there is no separate shared console adapter to call. Reduced motion renders final state without animated refresh.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_tui.py -q`. Real PTY: check 79/80/99/100 columns and live transitions across those boundaries, including footer/state/selection preservation; verify reduced-motion final state and colored/NO_COLOR bytes through the real production construction.

### U05 -- P1: Artifact browser control never performs paged content download

**Evidence:** The visible form invokes only `artifact_export` (`src/rush/dashboard/application.js:565-570`), whose server handler returns `expand_artifact_reference` metadata (`src/rush/dashboard/server.py:2070-2085`); browser code has no paged artifact GET/`next_offset` loop. Backend page tests (`tests/test_dashboard_git_artifacts.py:725-768`) don't satisfy the visible-control requirement.

**RED:** Add a browser-acceptance test (structural JS assertions in an existing dashboard JS test location, or a new fixture under the existing browser acceptance path referenced by U07/U08): `test_export_form_after_grant_gated_metadata_follows_paged_content_get_to_null_next_offset`; `test_two_same_name_attempts_each_longer_than_two_pages_with_split_utf8_nul_binary_bytes_download_with_matching_size_and_hash`; `test_failed_middle_page_and_cancellation_via_abortcontroller_never_produce_a_downloaded_partial_file`.

**GREEN:**
1. Reuse the existing authenticated `GET /api/projects/{project_id}/artifacts/{artifact_ref}?path=...&offset=...&limit=...` endpoint -- do not add a duplicate. `artifact_export` returns metadata only. M12 (already drafted in M-series.md) must land first to implement immutable attempt selection and the `data.content.content_base64` byte-page contract this depends on.
2. In `application.js`, after grant-gated export returns the chosen entry, retain the exact reference and allowed logical path; fetch the content GET (URL-encoding reference/path), follow `data.content.next_offset` until null; verify unchanged reference, total size, and whole-artifact digest across pages; decode M12's base64 into byte arrays.
3. Concatenate bytes into a Blob with declared media type/filename; show download progress and actionable errors; use `AbortController` for cancellation and revoke object URLs; reject inconsistent/truncated/failed pages rather than deliver a partial artifact as complete.

**VERIFY:** Open acceptance gap -- this environment has no live native-browser session for this task; the review's own regression is a real browser journey (export two same-name attempts through the visible controls, each longer than two pages, containing split UTF-8/NUL/binary bytes; compare full size/hash; cover a failed middle page and cancellation; prove attempt A's reference/offset never returns attempt B's bytes). Record this as an explicit unclosed acceptance item pending a real `agent-browser` session, plus `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_dashboard_git_artifacts.py -q` for the backend page contract this depends on.

### U06 -- P1: Visible handoff success is not proven and action identity can be stale

**Evidence:** Form dispatch uses `state.sourceIdentity` (`src/rush/dashboard/application.js:679`), refreshed in Overview (`:923`). Board `state.yaml:1177` admits handoff success was demonstrated with a direct probe instead of the visible form because expected identity kept drifting.

**RED:** Browser-acceptance test (same acceptance path as U05/U07/U08): `test_visible_preview_then_send_on_a_stable_registered_fixture_confirms_stored_and_delivered_content`; `test_source_or_attempt_evidence_change_between_preview_and_send_returns_409_with_zero_artifact_session_delivery_effects`; `test_stale_preview_remains_visible_and_disabled_until_a_deliberate_fresh_preview`.

**GREEN:**
1. Replace independent Preview/Send forms with one reviewed preview plus Send control. After S06 (already drafted in S-series.md) corrects the server contract, both requests require `run_id` and `attempt_id`. Before preview, refresh identity through the existing project snapshot flow. Store exact submitted run/attempt, `agent_id`, `finding_ids`, budgets, scope/grants/acceptance fields allowed by the corrected contract, returned packet/envelope, and hash-as-`handoff_id`.
2. Send those stored inputs and `handoff_id`, plus the preview's captured expected identity. Server rebuilds the canonical packet from that exact attempt; never submit an arbitrary client-built envelope, silently substitute the latest attempt, or add a separate source-identity endpoint.
3. On a 409, mark the preserved preview stale and disable Send until an explicit fresh Preview; never auto-reload if it would discard reviewed state; preserve form input.

**VERIFY:** Open acceptance gap -- requires a real native-browser session against a stable registered fixture, unavailable in this environment; record explicitly. Backend contract portion (once S06 lands): `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_scan_handoff.py -q`.

### U07 -- P2: Shell readiness passes live testing but lacks durable regression coverage

**Evidence:** Plan line 619 requires an independent shell-interactive milestone measured from navigation, plus a deliberately delayed-map negative check. `test_shell_interactive_signal_independent_of_map_fetch_completion` is absent from the repo. `scripts/benchmarks/run.py:724-739` measures `/api/session` round-trip, not enabled application controls. This review's own native-browser negative check (delayed map ~2s) already passed: controls enabled at 299ms, selection worked at 318ms, response at 2,015ms, nodes at 2,524ms -- current product behavior is not defective here; only the durable regression proof is missing.

**RED:** Add `test_shell_interactive_signal_independent_of_map_fetch_completion` to the existing browser acceptance test module (alongside `tests/test_dashboard_projects.py`/`tests/test_dashboard_user_journey.py`'s structural coverage).

**GREEN:**
1. No speculative product rewrite -- this review's own observation already demonstrates the required behavior; the remaining work is durable regression/evidence coverage, not a product fix.
2. Add the named test using navigation's performance time origin and the actual enabled/selectable controls as the milestone; delay the map response by approximately two seconds in the test fixture.
3. Assert shell interaction within the required one-second warm-local bound while map data is still pending; verify eventual map completion separately. Preserve browser/version, fixture, and exact navigation/control/map timestamps plus the exact runnable test command in the acceptance evidence.
4. Leave the existing `/api/session` round-trip measurement (`scripts/benchmarks/run.py:724-739`) labeled as bootstrap latency; do not relabel it as shell readiness or merge fetch duration with graph transition duration.

**VERIFY:** Open acceptance gap for the live-browser run itself (needs a real `agent-browser` session, unavailable here); once written, the test's presence and pass in the existing browser acceptance suite is the closure evidence.

### U08 -- P2: Terminal-event pulse and complete acceptance evidence remain unverified

**Evidence:** `tests/test_dashboard_motion_contract.py:5` declares structural/token scope only. Board `state.yaml:1226` records earlier runtime omissions. The specific 480ms terminal-event pulse was not observed by the review: memory mutation advances sequence without satisfying `event.status === 'terminal'` (`src/rush/dashboard/application.js:230-259`); the review's own real scan fixture was still pending at cleanup after 6.2s.

**RED:** Add to the existing browser acceptance path: `test_480ms_terminal_event_pulse_fires_after_a_real_scan_reaches_terminal_status_through_normal_ledger_polling`; `test_terminal_pulse_has_exactly_one_iteration_and_no_animation_under_reduced_motion`.

**GREEN:**
1. Use a controlled real scan fixture that reaches terminal status through the normal ledger polling route, then observe the actual 480ms terminal-event pulse; a memory write alone does not reach the `event.status === 'terminal'` branch at `application.js:230-259` -- directly calling the pulse helper bypasses the required trigger and is not acceptance evidence.
2. Capture start/mid/end properties, duration, easing, and `iterations === 1` after that real event; assert no idle repetition and no animation under reduced motion. If the assertion fails, repair the trigger/animation -- no production animation change is justified merely because this case was previously unobserved.
3. Retain this review's already-passing native project-entry, relationship, inspector, detail-row, abort/retry, input, focus, and reduced-motion observations as current evidence; add a repeatable browser command/fixture to the existing acceptance workflow instead of relying solely on source-token tests.

**VERIFY:** Open acceptance gap -- requires a real native-browser session with a real scan fixture reaching terminal state, unavailable in this environment. `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_dashboard_motion_contract.py -q` covers structural scope only, not this finding's closure.

### U09 -- P2: New NO_COLOR acceptance test fails from its capture harness

**Evidence:** `tests/test_tui_terminal.py:318` fails with `colored_output == b''`. `_run_pty_harness` starts a capture thread (`:185`); `_collect` closes the PTY without joining/draining it (`:215-227`). The colored control does not explicitly clear inherited `NO_COLOR` (`:312-320`). Independent PTY checks with `TERM=xterm-256color` confirm production color on/off behavior at `src/rush/tui.py:2006` verified-by: opened `tui.py:1995-2010` directly this session -- confirmed the real `reduced_motion`/`Console(no_color=...)` construction exists exactly as cited.

**RED:** Fix the existing `test_no_color_env_suppresses_ansi_color_codes` (`tests/test_tui_terminal.py:318`) rather than adding a new test -- it is the RED target itself; add `test_pty_harness_reader_is_drained_and_joined_before_pty_close_and_propagates_reader_errors`.

**GREEN:**
1. In `_run_pty_harness`/`_collect` (`tests/test_tui_terminal.py:185,215-227`), give the reader an explicit completion/error signal; after process exit, drain readable bytes to EOF or a bounded deadline and join the reader before closing the PTY descriptor. Propagate reader errors instead of returning an unexplained empty byte string.
2. Set `TERM=xterm-256color` explicitly in the harness; remove inherited `NO_COLOR` for the colored control and set it only for the suppressed case; exercise the same production console construction and content in both runs.
3. Require the expected plain text in both captures, ANSI color sequences in the colored case, and their absence in the NO_COLOR case; empty output must fail as a capture problem, never count as successful suppression.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_tui_terminal.py -q` then `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/ -q` (required full-suite gate) -- do not weaken the color assertion, add arbitrary sleeps, or infer full-suite success from the independently passing manual PTY probe.

### U10 -- P1: Browser memory forms expose none of the required ownership choices

**Evidence:** All five mutation-form definitions at `src/rush/dashboard/application.js:501-560` omit `owner_scope`. Plan lines 563,600 require all four ownership kinds across the visible flows -- the client-side gap accompanying M08 (already drafted in M-series.md).

**RED:** Browser-acceptance test (same acceptance path as U05/U06/U08): `test_all_five_memory_actions_exercised_for_all_four_owner_kinds_with_exact_stored_owner_and_revision`; `test_missing_owner_foreign_project_wrong_session_and_stored_owner_mismatch_leave_storage_unchanged`; `test_session_renewal_supplies_a_non_secret_new_id_and_cannot_silently_take_ownership_of_old_session_rows`.

**GREEN:**
1. Add one owner-kind/ID control used by Write/Promote/Edit/Archive/Delete in `application.js:501-560`, sending exact `arguments.owner_scope={kind,id}` separately from memory subject/version scope. Project uses the selected registered UUID; user/agent are required opaque nonblank labels, not authenticated accounts.
2. Add `owner_scope_id` to successful authenticated POST/GET session responses, sourced from `Session.owner_scope_id`; store it in browser session state for session-kind selection; never ask for a cookie/CSRF secret. M08 (S/M-series) validates the supplied ID against the request's authenticated session before reservation. Renewal updates session state but never transfers an existing row's immutable owner automatically.
3. Preserve form content/owner selection on validation/CAS failure and display the server's actual error message; browser validation improves input, exact owner/version enforcement stays server/store-side.

**VERIFY:** Open acceptance gap -- requires a real native-browser session, unavailable here. Backend contract portion (M08, already scheduled): `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_memory_public_contract.py -q`.

### U11 -- P2: Memory content form requires undocumented API knowledge

**Evidence:** Form definitions/parser at `src/rush/dashboard/application.js:501-509,640-653` label a field merely `content` and send raw strings when JSON parsing fails; the review's real registered-project browser fixture confirmed natural text and a source value yielded `400 malformed_request`, requiring undocumented JSON such as `{"text":"..."}` and a supported `source_kind`.

**RED:** Browser-acceptance test (same acceptance path as U05/U06/U08/U10): `test_write_edit_archive_via_visible_labels_and_examples_produces_correct_revisions`; `test_malformed_or_non_object_content_causes_no_post_and_shows_inline_guidance`; `test_source_kind_select_is_constrained_to_local_tool_cross_tool_handoff_human_derived`.

**GREEN:**
1. Write, Promote, and Edit content controls must explicitly require a non-array JSON object; show `{"text":"..."}` as an illustrative example, not a universal subject schema. Parse locally, retain invalid text, and send no malformed content request. Remove the raw-string fallback for declared JSON fields (`application.js:640-653`) while preserving other JSON fields' individually expected types -- e.g. artifact-ID arrays must remain arrays.
2. Provide a source-kind select with `local_tool`, `cross_tool_handoff`, `human_derived` for Write/Propose and Promote; Edit accepts content with no source-kind requirement; keep source visibly required only where the server contract requires it.
3. Keep defensive server validation and render its existing message next to the submitting form; do not assume a field-error response schema already exists.

**VERIFY:** Open acceptance gap -- requires a real native-browser session, unavailable here; record explicitly as an unclosed acceptance item pending a real `agent-browser` session.
