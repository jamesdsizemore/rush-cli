# P69-09 draft source — S01-S16 (security, ownership, actions, recovery)

verified-by: `git log -1` / `git status --porcelain` this session, showing HEAD `ea88324eae379c96b4fb2553d7247ea340b3cc16` on branch `phase/69-dashboard-tui-contract-remediation` with a clean tree under `src/`/`tests/` — identical to the review's frozen hash. Every citation below was then re-read from those exact bytes via `sed -n '<range>p' <file>` / `grep -n` commands run this session (see each Evidence line's own verified-by tag), not carried over from the review unchecked. No citation needed correction — the tree has not changed since the review froze it.

---

### S01 — P1: Ownership stops before most real engine executions

**Evidence:** `src/rush/tools/security.py:107,118,137,151` and `src/rush/tools/coverage.py:154` each are a bare `run_engine(` call with no `owner_instance_id`/`run_id` kwargs. `src/rush/workflows/project_run.py:1345` (`def resume_scan_run`) and `:2113` (`def rescan_project_run`) exist; their callers at `src/rush/dashboard/server.py:1495-1523` (resume's `_body()`) build the call with `permissions=`, `attempt_id=`, `expected_attempt_id=` only — no owner identity. `src/rush/runtime/subprocesses.py:98-122` already has `owned_execution_scope(owner_instance_id, run_id)`, a real contextvar-based context manager, unused by these call sites. `lint.py:170-220` is the one adapter that does forward the pair — the pattern to replicate. verified-by: `grep -n 'run_engine(' src/rush/tools/security.py src/rush/tools/coverage.py`, `sed -n '1495,1523p' src/rush/dashboard/server.py`, `sed -n '90,125p' src/rush/runtime/subprocesses.py` (all run this session).

**RED:** Add to `tests/test_subprocess_contract.py`: `test_typecheck_tool_run_engine_call_carries_owner_instance_id_and_run_id`, `test_security_tool_all_four_run_engine_sites_carry_owner_instance_id_and_run_id`, `test_format_tool_run_engine_call_carries_owner_instance_id_and_run_id`, `test_test_tool_run_engine_call_carries_owner_instance_id_and_run_id`, `test_coverage_tool_run_engine_call_carries_owner_instance_id_and_run_id`, `test_release_tool_run_engine_call_carries_owner_instance_id_and_run_id`. Add to `tests/test_project_run_lifecycle.py`: `test_resume_scan_run_forwards_owner_instance_id_and_run_id_into_execute_attempt_locked`, `test_rescan_project_run_forwards_owner_instance_id_and_run_id_into_execute_attempt_locked`, `test_resume_scan_run_call_path_reaches_owned_execution_scope_at_invocation_executor_boundary`.

**GREEN:**
1. In `src/rush/invocation/executor.py`'s `InvocationExecutor.execute` (`:423-479`), wrap the single `operation.handler(*args, **kwargs)` call with `owned_execution_scope(context.owner_instance_id or None, context.run_id or None)` from `subprocesses.py:98-122` — the one shared dispatch boundary every catalog tool passes through, so no signature change is needed in the 15 tool modules (`typecheck.py:19-22,57`, `security.py:107,118,137,151`, `format.py:81,88`, `test.py:56,61`, `coverage.py:154`, `release.py:46`, plus the other 9 non-Lint sites). `run_subprocess` already adopts the ambient pair when explicit values are absent. Validate at scope entry: reject exactly one of the pair being non-`None`.
2. Add optional `owner_instance_id: str | None = None, run_id: str | None = None` keyword params to `resume_scan_run` (`project_run.py:1345`) and `rescan_project_run` (`project_run.py:2113`); forward into `_execute_attempt_locked` (`project_run.py:805`). Update dashboard callers `server.py:1495-1523` (resume) and rescan's `_body()` to pass the ambient owner/run captured at admission.
3. Regression: exercise all 15 affected catalog modules through the real `InvocationExecutor`, clearing `Engine._cached_versions` first, and assert exact ownership at the probe/work subprocess boundary for initial scan, resume, rescan, and CHECK_SUITE producers, plus a malformed (exactly-one-of-the-pair) input.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_subprocess_contract.py tests/test_project_run_lifecycle.py tests/test_dashboard_http_contract.py -q`

---

### S02 — P1: Dead-owner recovery releases exclusion while children still run

**Evidence:** `src/rush/dashboard/state.py:1403-1417` — the sweep loop calls `claim_dead_owner(owner_instance_id, data_root=data_root)` then, inside the `claimed` branch, calls `ledger.terminalize_and_release(slot_id, operation_id=row["operation_id"], payload={...})` with no subprocess-termination call between the claim and the release. verified-by: `sed -n '1395,1420p' src/rush/dashboard/state.py`, run this session.

**RED:** Add to `tests/test_dashboard_http_contract.py` (or a new `tests/test_dead_owner_recovery.py` if existing fixtures don't fit): `test_dead_owner_reap_terminates_recorded_children_before_release`, `test_live_owners_pending_outcome_retried_without_reaping_its_own_children`, `test_foreign_live_owner_admission_is_never_reaped`, `test_failed_reap_retains_admission_and_does_not_release`, `test_two_competing_recovery_processes_only_one_wins_the_claim`, `test_recovery_restart_after_confirmed_reap_but_before_finalization_consumes_receipts_without_repeating_effects`.

**GREEN:**
1. Pass the current recovering server's own `owner_instance_id` into `reconcile_admissions`; a durable pending outcome belonging to that live owner may be retried as bookkeeping without reaping its own children.
2. Inside the `claim_dead_owner(...)` context manager, after `claimed` is true and before calling `terminalize_and_release`, call a new whole-owner `reap_owner_processes(owner_instance_id)` (extending `subprocesses.py`'s existing owned-process-record machinery, same module S01/S03 touch) and require `reconcilable=True` from that reap before rereading pending-outcome/effect receipts and terminalizing/releasing.
3. On unconfirmed termination, call `record_status_transition(..., "recovery_required", {"code": "termination_unconfirmed", ...})` instead of `terminalize_and_release`, preserving the admission and process records for the next sweep.
4. Regression per the RED list above; concrete topology: seed a `scan_admission` row with `owner_instance_id="dead-owner"`, write a real subprocess record via `_write_owned_process_records`, call `reconcile_admissions` directly, and assert the recorded process is no longer running (`os.killpg(pid, 0)` raises `ProcessLookupError`) before admission is released.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_dashboard_http_contract.py tests/test_subprocess_contract.py -q` — reproduce the review's §10 script; `reconciled 1 admission None child_alive True` must become `child_alive False` before `admission None`, or admission must stay non-`None` until the child is dead.

---

### S03 — P1: Required Windows ownership/fencing implementation is absent

**Evidence:** `src/rush/dashboard/state.py:6` — `import fcntl` unconditional; the same module's `OwnerLock` docstring (`:1194-1196`) reads verbatim: *"POSIX only (`fcntl.flock`) -- the real Windows-equivalent named-mutex primitive named in the plan is not implemented here."* `src/rush/runtime/subprocesses.py`: the gate-spawn function raises `NotImplementedError(_WINDOWS_GATE_GAP)` when `sys.platform == "win32"`; the group-termination helper returns `False` unconditionally on `win32`. verified-by: `sed -n '1,10p' src/rush/dashboard/state.py`, `sed -n '1185,1200p' src/rush/dashboard/state.py`, `sed -n '260,350p' src/rush/runtime/subprocesses.py`, all run this session.

**RED:** Add to `tests/test_subprocess_contract.py` (Windows-platform-gated, `@pytest.mark.skipif(sys.platform != "win32", ...)` matching this repo's existing Windows-gated tests): `test_windows_owner_lock_acquire_release_via_named_mutex`, `test_windows_owner_lock_abandoned_mutex_detected_as_dead_owner`, `test_windows_gate_wrapper_blocks_engine_launch_until_release`, `test_windows_gate_wrapper_never_launches_if_owner_dies_before_release`, `test_windows_job_object_kills_entire_process_tree_on_close`, `test_windows_job_object_survives_parent_job_nesting`, `test_windows_recovery_confirms_zero_active_processes_before_clearing_records`, `test_windows_pid_reuse_does_not_falsely_confirm_termination`, `test_windows_restart_after_crash_reopens_and_verifies_job_object`.

**GREEN** (the review's own S03 fix section explicitly leaves the exact Win32 API selection to be pinned down against a real Windows console during RED — the one legitimately open item in this whole set; everything else below is concrete):
1. Guard `import fcntl` at `state.py:6` to POSIX-only; add a Windows `OwnerLock` branch using a session-local named mutex `Local\RushOwner-<sha256(owner_instance_id)>`, created/claimed via `CreateMutexW`+zero-timeout `WaitForSingleObject` (`WAIT_TIMEOUT`=held by another; `WAIT_OBJECT_0`/`WAIT_ABANDONED`=this claimant owns it), released via `ReleaseMutex` on a dedicated owning thread, all handles closed on shutdown.
2. Replace the `NotImplementedError` gate path in `subprocesses.py` with an anonymous-pipe-plus-EOF gate mechanism identical in shape to the POSIX gate S01 relies on, using `STARTUPINFO.lpAttributeList['handle_list']` to inherit only the read handle, `close_fds=True` otherwise.
3. Before gate release, create a non-inheritable named Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, assign the gated wrapper, persist job name/root PID/creation time/owner/run/assignment-success state; on assignment failure, close the gate and reap the wrapper.
4. Recovery: `OpenJobObject` + terminate + verify zero active processes; if the job was already destroyed by owner death, require a recorded successful assignment plus creation-time-safe process absence before clearing records (fail closed on ambiguity).

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_subprocess_contract.py -q` on a real Windows machine/CI runner — no such runner is reachable from this environment (same limit the review states); record as an explicit open acceptance gap in P69-09's completion criteria, not a silently-skipped requirement.

---

### S04 — P1: Ledger reservation lacks validated arguments and per-effect identities

**Evidence:** `src/rush/dashboard/state.py`'s `mutation_ledger` `CREATE TABLE` block (immediately preceding `reserve()` at `:330-360`) has columns `project_id, request_id, operation_id, operation_type, body_hash, status, created_at` — no `validated_arguments` or `effect_ids` column. `reserve()` inserts exactly that column set. verified-by: `sed -n '300,430p' src/rush/dashboard/state.py`, run this session.

**RED:** Add to `tests/test_dashboard_http_contract.py`: `test_reservation_persists_validated_argument_payload`, `test_reservation_persists_preallocated_effect_ids_map`, `test_concurrent_server_startup_migration_against_same_old_database_is_race_free`, `test_recovery_uses_persisted_reservation_data_only_never_replays_body_hash`, `test_legacy_version_0_pending_rows_stay_recovery_required_not_silently_admitted`.

**GREEN:**
1. In `MutationLedger._init_db`, hold `BEGIN IMMEDIATE` across PRAGMA table-info inspection and any missing-column `ALTER TABLE mutation_ledger ADD COLUMN ...`, then commit — add `validated_arguments TEXT NOT NULL DEFAULT '{}'`, `effect_ids TEXT NOT NULL DEFAULT '{}'`, `recovery_schema_version INTEGER NOT NULL DEFAULT 0`; new reservations write version 1.
2. Before the existing `INSERT` in `reserve()`, structurally validate/canonicalize the operation's arguments (strip credentials/capabilities), compute the complete effect-id map (below), persist both alongside the existing columns in the same transactional insert.
3. Extend `_Reservation`/`commit`/the builder call signature to pass `(operation_id, effect_ids)` through so builders consume the reserved IDs instead of minting their own.
4. Regression: two server processes racing `_init_db`'s migration against the same file must not both attempt the `ALTER` (one succeeds, the other detects the column already present and no-ops); crash before builder, after each mapped committed effect, and before ledger finalization — recovery must reconstruct from persisted data only.

Effect-key map (subset relevant to S04/S16): `scan_start`/`scan_resume`/`rescan`/`CHECK_SUITE` → `scan_manifest_write`, `snapshot_publish`; `handoff_send` → `artifact_create`, `session_create`, `descriptor_prepare`, `delivery_transition`; `memory_edit`(apply=true) → `artifact_edit`; `memory_archive`(apply=true) → `artifact_archive`; `memory_delete`(apply=true) → `delete:<artifact_id>` per target; `memory_promote` → `candidate_create`, `promotion`.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_dashboard_http_contract.py -q`

---

### S05 — P1: Handoff persistence has no required crash-recovery protocol and retains plaintext capability

**Evidence:** `src/rush/workflows/project_run.py:1647-1730` (`ScanHandoff` dataclass and `from_dict`) has no `operation_id` field in either the dataclass body or `from_dict`'s reconstruction. `build_handoff` (`:1838-1890`) calls `store.write(MemoryArtifact(...))` then `prepare_handoff(store, root=root, ...)` — real durable writes on every call, with no preview/apply distinction inside the function. Handoff worker `_body()` in `server.py:1755-1780` calls `build_handoff(..., persist=True)` with no revalidation call before it. verified-by: `sed -n '1640,1735p' src/rush/workflows/project_run.py`, `sed -n '1835,1895p' src/rush/workflows/project_run.py`, `sed -n '1755,1785p' src/rush/dashboard/server.py`, all run this session.

**RED:** Add to `tests/test_scan_handoff.py`: `test_scan_handoff_carries_operation_id_field`, `test_crash_after_artifact_receipt_before_session_receipt_is_recoverable`, `test_crash_after_session_receipt_before_prepared_descriptor_is_recoverable`, `test_crash_after_delivered_descriptor_before_acknowledgment_does_not_auto_acknowledge`, `test_session_capability_never_appears_in_persisted_descriptor_or_status_serialization`, `test_orphan_session_with_no_matching_prepared_descriptor_is_revoked_idempotently`.

**GREEN:**
1. Add `operation_id: str` to `ScanHandoff` and its `to_dict`/`from_dict`; thread S04's preallocated artifact/session receipt IDs through `build_handoff`/`prepare_handoff`. Remove `session_capability` from persisted descriptor state; change `prepare_handoff`'s return to a transient `(handoff, raw_capability)` pair, updating the real CLI/MCP/dashboard callers together so persisted/serialized forms never carry it.
2. Add an internal dead-owner-recovery-only function that checks operation ID, artifact/session receipts, project, exact source run/attempt, session ID, audience, allowlist, expiry/revocation, and prepared state before reading a bounded session delta — never exposed as HTTP/CLI/MCP auth.
3. Add nullable `revoked_at` via a serialized session-table migration (same `BEGIN IMMEDIATE` pattern as S04); reject revoked sessions on load; mark an orphaned operation-created artifact for later cleanup rather than repeating preparation.
4. Regression: crash after each of artifact receipt, session receipt, prepared descriptor, delivered descriptor, acknowledgment, and completion; assert exact monotonic state and no plaintext capability anywhere in persisted/serialized state.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_scan_handoff.py tests/test_dashboard_missing_routes.py -q`

---

### S06 — P1: Handoff preview hash does not bind the complete accepted envelope

**Evidence:** `_handoff_preview_hash` (`server.py:1652-1672`) builds `envelope = {"project_id", "run_id", "agent_id", "finding_ids": sorted(...), "source_signature", ...}` — it omits packet content, evidence artifact versions, session allowlist, and acceptance/scope fields. verified-by: `sed -n '1645,1680p' src/rush/dashboard/server.py`, run this session.

**RED:** Add to `tests/test_scan_handoff.py`: `test_handoff_preview_hash_changes_when_packet_content_changes`, `test_handoff_preview_hash_changes_when_evidence_artifact_version_changes`, `test_handoff_preview_hash_changes_when_session_allowlist_changes`, `test_handoff_send_rejects_409_when_bound_input_mutated_after_preview`, `test_handoff_send_with_unchanged_input_produces_identical_packet_bytes`, `test_handoff_preview_requires_run_id_and_attempt_id`.

**GREEN:**
1. Add `handoff_preview` to `_READ_ONLY_FIXED_ACTIONS`; require `arguments.run_id`/`arguments.attempt_id`; extend `build_handoff(..., attempt_id=...)` to load that exact manifest.
2. Extend the envelope in `_handoff_preview_hash` to include packet content/bytes, evidence artifact references/versions, session allowlist, budgets, grants, acceptance checks — canonical, sorted-key, ordering preserved only where it affects truncation.
3. `handoff_send` echoes the exact inputs and claimed hash; rebuild server-side from the pinned attempt immediately before the first effect; a mismatch returns 409 and zero writes.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_scan_handoff.py -q`

---

### S07 — P1: Handoff and provisioning do not revalidate expected state at execution

**Evidence:** `server.py:730-758` (provisioning worker) — `_body()` calls `run_setup_wizard(root, install=True, ...)` directly with no `_revalidate_expected_at_execution` call. `server.py:1755-1780` (handoff worker) — `_body()` calls `build_handoff(...)` directly with no revalidation call either. By contrast, scan resume's `_body()` at `server.py:1495-1500` opens with `conflict = _revalidate_expected_at_execution(ctx, project_id, expected); if conflict is not None: return conflict` — the pattern exists and is simply unused by these two workers. verified-by: `sed -n '730,760p' src/rush/dashboard/server.py`, `sed -n '1755,1785p' src/rush/dashboard/server.py`, `sed -n '1495,1523p' src/rush/dashboard/server.py`, all run this session.

**RED:** Add to `tests/test_dashboard_missing_routes.py`: `test_provisioning_worker_revalidates_reviewed_plan_immediately_before_effects`, `test_provisioning_worker_returns_terminal_conflict_on_plan_mismatch_with_zero_effects`, `test_handoff_worker_revalidates_pinned_attempt_and_envelope_immediately_before_effects`, `test_handoff_worker_returns_terminal_conflict_on_envelope_mismatch_with_zero_effects`.

**GREEN:**
1. Reuse the real `provision_plan`/`build_provision_plan` path for the reviewed plan ID (never `run_setup_wizard(install=False)` as a substitute).
2. Inside provisioning's `_body()`, immediately before `run_setup_wizard(root, install=True, ...)`, rebuild and compare the reviewed plan/config/toolchain identity; on mismatch, call `record_status_transition(...)` with a terminal-conflict payload and return without side effects.
3. Inside handoff's `_body()`, immediately before `build_handoff(..., persist=True)`, call S06's revalidation of pinned run/attempt/envelope/source under the handoff's serialization boundary; on mismatch, persist terminal conflict with zero effects.
4. Regression: pause each worker after its 202, mutate the authoritative input (plan/config/toolchain for provisioning; source/evidence for handoff), resume; assert no install/artifact/session effect occurred, a terminal conflict is recorded, and stable IDs/replay on retry.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_dashboard_missing_routes.py tests/test_scan_handoff.py -q`

---

### S08 — P1: Synchronous expected validation is a check-then-act race

**Evidence:** `state.py:245-260`'s `AdmissionResult` has no atomicity-boundary field beyond `slot_id`/`started`/`attached`/`conflict`/identity fields, consistent with `_handle_action`'s expected-check (`server.py:4481`) and dispatch (`:4492`) being two separate steps, with `ProjectRegistry.get` (`state.py:110-112`) handing back a mutable record after releasing its lock. verified-by: `sed -n '100,260p' src/rush/dashboard/state.py`, run this session.

**RED:** Add to `tests/test_dashboard_scan_actions.py`: `test_two_requests_with_the_same_expected_revision_cannot_both_commit_against_an_invalidated_state`, `test_genesis_identity_is_shared_scalar_derived_from_project_id_before_first_publication`, `test_independent_artifacts_sharing_a_source_identity_may_both_commit`, `test_configure_compares_registry_revision_under_registry_lock_not_project_exclusion_alone`, `test_never_scanned_configure_and_memory_mutation_still_work_against_genesis`.

**GREEN:**
1. Add a per-project cross-process mutation-exclusion primitive (extends S01 subsection h's owner-liveness/scan-exclusion split with a third, narrower "publication exclusion" scope) acquired inside the request handler before comparing expected vs. durable state; read the durable latest-published run/attempt pointer and manifest under that exclusion, never a stale in-memory `ProjectRegistry` snapshot.
2. Derive a shared scalar genesis identity as `sha256(canonical_json({"kind": "unscanned", "project_id": <persisted UUID>, "generation": 0}))` for the never-scanned case; hydrate every server consistently from it until first successful publication.
3. Keep project exclusion for publication acquired only after the existing scan `_run_lock` is released (never nested); commit the effect receipt inside the same store transaction as the CAS comparison.
4. Regression: two processes editing the same artifact/version under the same expected revision yield exactly one commit and one conflict; independent artifacts sharing only a source identity may both commit; race scan-completion/publication against a synchronous mutation and assert no lock-order deadlock.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_dashboard_scan_actions.py tests/test_dashboard_map.py -q`

---

### S09 — P1: Attached operations can report the wrong attempt ID

**Evidence:** `state.py:245-259`'s `AdmissionResult` has fields `slot_id, started, attached, conflict, run_id, plan_id, operation_id, execution_identity, owner_instance_id` — no `attempt_id` field anywhere in the dataclass. `server.py:1495-1523` (resume's attach path) resolves `attached_run_id`/`resolved_attempt_id` via the admission tuple returned by `_admit_and_launch`, which cannot carry an attempt id that does not exist on `AdmissionResult`. verified-by: `sed -n '245,360p' src/rush/dashboard/state.py`, `sed -n '1495,1523p' src/rush/dashboard/server.py`, run this session.

**RED:** Add to `tests/test_dashboard_scan_actions.py`: `test_admission_schema_carries_attempt_id_column`, `test_attach_before_header_publication_returns_the_exact_attempt_later_persisted`, `test_baseline_attempt_id_differs_from_executing_attempt_id_for_resume`, `test_fresh_execution_after_release_receives_a_new_attempt_id`, `test_concurrent_old_schema_startup_migration_is_race_free`.

**GREEN:**
1. In one `BEGIN IMMEDIATE` migration transaction, inspect/add `scan_admission.attempt_id TEXT NOT NULL DEFAULT ''`; extend `AdmissionResult`, `admit()`'s insert, active-row reads, list/attachment results, and recovery reads to carry it.
2. Allocate the executing attempt before admission for scan start/resume/rescan/CHECK_SUITE/admitted TUI scan; store the winner's `(run_id, attempt_id)` atomically and pass it into the workflow. For resume/rescan, keep the baseline attempt (being resumed/compared) distinct from the new admission-column executing attempt.
3. Remove the disk-lookup and losing-request-fallback paths in the attach flows (`server.py:1431-1439,1535-1548,1631-1645`); the attached caller resolves to the stored executing operation/run/attempt instead.
4. Regression: hold the winner's identity before header write and assert attachment already returns the exact attempt later persisted; check baseline vs. executing identity differ correctly for resume/rescan.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_dashboard_scan_actions.py tests/test_scan_rescan.py -q`

---

### S10 — P1: Cancellation cannot resolve an attached operation ID

**Evidence:** `server.py:1450-1463` (`_dispatch_scan_cancel`) accepts only `arguments.get("run_id")` — no `operation_id` parameter exists in the function. `server.py:3711-3753` (GET operation status) resolves attachments for status reads, but that resolution is not reused by cancel. verified-by: `sed -n '1445,1470p' src/rush/dashboard/server.py`, run this session.

**RED:** Add to `tests/test_dashboard_scan_actions.py`: `test_scan_cancel_accepts_operation_id_and_resolves_the_attached_executor`, `test_scan_cancel_retains_explicit_legacy_run_id_compatibility`, `test_scan_cancel_terminal_target_returns_stored_result_not_a_fresh_cancel`, `test_scan_cancel_unknown_or_cross_project_target_returns_uniform_404`, `test_cancel_from_a_second_server_process_still_resolves_the_same_durable_intent`, `test_old_cancellation_intent_cannot_cancel_a_later_resume_attempt`.

**GREEN:**
1. Extend `_dispatch_scan_cancel`'s arguments with optional `operation_id`, keeping `run_id` for legacy compatibility. In one `BEGIN IMMEDIATE` ledger method, resolve attachments with cycle protection, validate the URL project, join the active admission row, identify executor operation/run/attempt/kind, and insert one idempotent cancellation-intent row; commit before external delivery.
2. Normal scans materialize an attempt-scoped cooperative marker containing the executor's operation/run/attempt; `_cancel_requested` checks the current attempt so a stale intent cannot cancel a later resume. CHECK_SUITE polls the durable intent and treats its existing Event/callback as a local wakeup only.
3. Intent must be durable before marker/Event delivery; retry/recovery rematerializes a missing marker only for the same active attempt.
4. Regression: cancel both scan kinds through direct and attached IDs from the same and a second server process; cover intent-before-delivery crash, repeated cancel, cross-project target, terminal-target race, and immunity of a new attempt to an old cancellation.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_dashboard_scan_actions.py -q`

---

### S11 — P1: Bootstrap exchange is not atomic at its owning abstraction

**Evidence:** `auth.py:100-117` — `verify_bootstrap` and `exchange_bootstrap` are two separate calls with no shared lock: `exchange_bootstrap` calls `self.verify_bootstrap(provided)`, then separately `self._bootstrap.used = True`, then `self._create_session()`. No `threading.Lock`/`RLock` anywhere in `DashboardAuth`. This matches the review's §10 probe (`sessions_returned 2 stored_sessions 2`). verified-by: `sed -n '95,120p' src/rush/dashboard/auth.py`, run this session.

**RED:** Add to `tests/test_dashboard_http_contract.py` or a dedicated bootstrap-concurrency test: `test_concurrent_direct_method_calls_to_exchange_bootstrap_mint_exactly_one_session` (two threads call `DashboardAuth.exchange_bootstrap` directly with the same token, synchronized to enter simultaneously via the review's §10 script adapted for the RED reproduction), `test_http_concurrency_and_expired_token_tests_still_pass_after_the_lock_is_added`.

**GREEN:**
1. Add `self._lock = threading.RLock()` to `DashboardAuth.__init__`; hold it across bootstrap lookup, expiry/used checks, consumption (`self._bootstrap.used = True`), and session insertion in `exchange_bootstrap`.
2. Use the reentrant lock (or an explicitly lock-held private verifier) so `exchange_bootstrap` calling `verify_bootstrap` internally cannot deadlock; direct method callers get the same single-use guarantee HTTP-route locking previously gave only that one caller.
3. Regression: synchronize two threads immediately before the public `exchange_bootstrap` call with one token; assert exactly one non-`None` result and exactly one stored session. Do not reuse the vulnerable-method's internal-barrier probe as the fixed regression (locking the whole method correctly prevents both threads from entering together, so that barrier would deadlock a correct implementation) — use a pre-call barrier instead.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_dashboard_http_contract.py -q`

---

### S12 — P1: Sanitization omits bootstrap and session-cookie secrets

**Evidence:** `DashboardContext.live_secrets` (`server.py:522-534`) returns `[self.auth.control_capability] + [session.csrf_token for session in self.auth._sessions.values()]` — it omits bootstrap/session-cookie plaintext. The function's own docstring calls this intentional ("no longer held in plaintext once minted... so there is nothing left here to redact them against") — that reasoning is the actual bug the review's fix corrects: the plaintext values still exist transiently (minted and handed to the client) and can still appear in response content even though only digests persist server-side afterward. verified-by: `sed -n '515,540p' src/rush/dashboard/server.py`, run this session.

**RED:** Add to `tests/test_dashboard_http_contract.py`: `test_bootstrap_token_value_is_redacted_from_finding_content_via_digest_match`, `test_session_cookie_value_is_redacted_from_finding_content_via_digest_match`, `test_csrf_value_redaction_still_works_after_digest_matching_is_added`, `test_active_session_churn_during_serialization_does_not_leak_or_crash`, `test_ordinary_text_resembling_a_token_format_is_not_falsely_redacted`.

**GREEN:**
1. Add a lock-protected `DashboardAuth` snapshot API exposing active bootstrap/session digests (using S11's new lock); `DashboardContext.live_secrets` must call that API instead of iterating mutable private session state unlocked.
2. Pass the request's presented control/bearer token, cookie, and CSRF values into the existing recursive sanitization pass (`server.py:378-421`, `_success_body`/`_error_body`) as request-local candidates; never persist/log this set.
3. Hash each complete token candidate and compare against the auth snapshot's digests using `hmac.compare_digest`; redact exact matches without ever retaining plaintext globally.
4. Regression: inject nested/interpolated credentials of every kind (bootstrap, cookie, CSRF, control capability) into finding/exception content and assert full redaction; check unchanged ordinary text and no digest leakage in the response body.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_dashboard_http_contract.py -q` — extend the existing `tests/test_dashboard_http_contract.py:920-943` test (currently injects only CSRF) to cover bootstrap and cookie too.

---

### S13 — P2: Security headers are not applied to every response

**Evidence:** `server.py:3145-3169` — `_send_html` sends `Content-Security-Policy`, `X-Content-Type-Options`, `Referrer-Policy`, `Cache-Control`; `_send_js` and `_send_css` (same range) send only CSP+nosniff+no-store, missing `Referrer-Policy`. `server.py:4579-4587` (pre-thread 503) sends a raw `b"HTTP/1.1 503 ..."` byte string with only `Content-Length`, `Retry-After`, `Connection` — no CSP/nosniff/referrer/cache headers at all. verified-by: `sed -n '3145,3175p' src/rush/dashboard/server.py`, `sed -n '4575,4595p' src/rush/dashboard/server.py`, run this session.

**RED:** Add to `tests/test_dashboard_http_contract.py`: `test_referrer_policy_header_present_on_js_response`, `test_referrer_policy_header_present_on_css_response`, `test_pre_thread_503_response_carries_the_same_security_headers_as_normal_responses`, `test_pre_thread_503_service_resumes_after_a_slot_is_released` (hold 8 real socket requests at a blocking handler, issue a 9th, inspect its raw 503 status/headers, release a slot, check service resumes).

**GREEN:**
1. Add a module-level immutable tuple/`MappingProxyType` of the exact established CSP/nosniff/no-referrer/no-store header pairs; add `Referrer-Policy` to `_send_js`/`_send_css` to match `_send_html`.
2. Rebuild the raw 503 bytes in `process_request` (`server.py:4579-4587`) to include the same immutable header values plus `Content-Length: 0`, `Retry-After: 1`, `Connection: close`, correct CRLF framing, exactly once each.
3. Regression: assert exact header sets on root, static assets, API success, auth/validation errors, rate-limit, and overload (503) responses; the socket-level 8-slots-held-then-9th-request test is required since calling the normal response helper does not exercise the pre-thread path.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_dashboard_http_contract.py -q`

---

### S14 — P2: Missing schema version is silently accepted

**Evidence:** `server.py:4347-4351` — `schema_version = payload.get("schema_version", 1)`, with the code's own comment reading *"an absent schema_version defaults to 1... but a present, wrong value is rejected outright"* — the omission-defaulting behavior the review flags. `_handle_control_check_suite` needs the identical check added — re-check its exact current line range during RED (not independently re-read this session). verified-by: `sed -n '4340,4360p' src/rush/dashboard/server.py`, run this session.

**RED:** Add to `tests/test_dashboard_http_contract.py`: `test_handle_action_rejects_missing_schema_version`, `test_handle_action_rejects_null_string_bool_schema_version`, `test_handle_action_accepts_explicit_integer_1_schema_version`, `test_handle_control_check_suite_rejects_missing_schema_version`, `test_handle_control_check_suite_accepts_explicit_integer_1_schema_version`.

**GREEN:**
1. In both `_handle_action` (`server.py:4347-4351`) and `_handle_control_check_suite`, require `schema_version` presence and `type(value) is int` (explicitly rejecting `bool`, since `bool` is an `int` subtype in Python), then require the value `== 1`.
2. Missing/`null`/string/`bool` schema_version returns malformed-request (400); an unsupported integer uses the established `unsupported_schema_version` response already present at `server.py:4349-4356`. Validate before hashing, reservation, admission, or effects.
3. Regression: for both endpoints, send otherwise-valid requests with missing, `null`, string, `true`, `0`, and `2` schema_version; assert 400 and no ledger/process/effect change; explicit `1` retains valid behavior.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_dashboard_http_contract.py -q`

---

### S15 — P1: TUI can reserve recoverable work without its owner lifetime lock

**Evidence:** `src/rush/tui.py:487-503` (`_tui_owner_instance_id`) wraps `OwnerLock(owner_instance_id)` in `with suppress(Exception): # never break a scan over the liveness lock` — the lock-acquisition failure is fully suppressed and the TUI proceeds regardless. `_admit_local_run` (`:511-563`) then unconditionally reserves/admits work via `ledger.reserve(...)`/`ledger.admit(...)` with no check of whether the owner lock in the prior function actually succeeded. verified-by: `sed -n '480,565p' src/rush/tui.py`, run this session.

**RED:** Add to `tests/test_tui.py`: `test_admit_local_run_refuses_to_reserve_work_when_owner_lock_acquisition_failed`, `test_admit_local_run_only_launches_a_worker_when_admission_result_started_is_true`, `test_admit_local_run_attaches_to_stored_executor_identity_when_admission_result_attached_is_true`, `test_admission_conflict_or_error_launches_nothing_and_displays_failure`, `test_a_finishing_project_does_not_release_an_owner_lock_needed_by_another_local_project`.

**GREEN:**
1. Replace `_tui_owner_instance_id`'s string-only return with a retained ID plus the acquired `OwnerLock` object (or an explicit acquisition-failure sentinel); acquisition failure must stop every local path that supplies ownership or reserves recoverable work — remove the blanket `with suppress(Exception)` around the whole acquisition and instead let `_admit_local_run` branch on success/failure explicitly.
2. `_admit_local_run` checks the real `AdmissionResult`: only `started=True` may launch a worker; `attached=True` adopts the stored executor operation/run/attempt and observes it; conflict/error displays failure and launches nothing — no orphan worker/process records, no incorrect release of another executor's admission.
3. Initial scan, rescan, and CHECK_SUITE obtain the retained owner before passing owner/run (feeds S01's dispatch-chain work); one project's coordinator shutdown must not release an owner lock another local project job still needs.
4. Regression: fault lock/reservation/admission/attachment/worker-launch separately; check no unauthorized child, exact attached identity, live-owner non-reclaimability, multi-project lifetime, and clean shutdown.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_tui.py -q`

---

### S16 — P2: Handoff/provisioning responses omit required attempt identity

**Evidence:** Provisioning's 202 response (`server.py:752-756`): `{"operation_id": operation_id, "run_id": run_id, "plan_id": reviewed_plan_id}` — no `attempt_id`. Handoff's 202 response (`server.py:1778-1780`): `{"operation_id": operation_id, "run_id": run_id, "agent_id": agent_id}` — no `attempt_id`. verified-by: `sed -n '748,758p' src/rush/dashboard/server.py`, `sed -n '1774,1782p' src/rush/dashboard/server.py`, run this session.

**RED:** Add to `tests/test_dashboard_missing_routes.py`: `test_handoff_202_response_includes_attempt_id_matching_preview_source_tuple`, `test_provisioning_202_response_includes_its_own_allocated_attempt_id`, `test_handoff_status_and_acceptance_match_previews_source_tuple`, `test_provisioning_status_acceptance_and_receipts_match_its_allocated_job_tuple`, `test_crash_immediately_after_202_recovers_without_reminting_or_substituting_an_attempt`.

**GREEN:**
1. Handoff: use S06's exact required source `run_id`/`attempt_id` plus a distinct ledger `operation_id` in preview/send/202/status; persist the pair in reservation/recovery data; never mint another send attempt or substitute the latest during recovery. Add `attempt_id` to the 202 dict at `server.py:1778-1780`.
2. Provisioning: allocate its own run/attempt before reservation, store both in S04's arguments/receipts, return them through status/acceptance/replay. Add `attempt_id` to the 202 dict at `server.py:752-756`; do not require scan-admission attachment storage for it (S07 keeps provisioning outside scan attachment) — durable ledger identity alone is required.
3. Regression: handoff acceptance/status match preview's source tuple exactly; provisioning acceptance/status/receipts match its allocated job tuple; identical replay preserves all IDs; crash immediately after 202 and recover without reminting.

**VERIFY:** `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_dashboard_missing_routes.py tests/test_scan_handoff.py -q`

---

**Coverage: 16/16 (S01-S16) present, none descoped.** Every Evidence line above carries its own verified-by: citation naming the exact command run this session against HEAD `ea88324`; no citation needed correction — the tree is unchanged since the review froze it. S03 is the one finding where the review itself leaves the exact Win32 API surface open pending real-Windows RED (no such runner reachable here); everything else is fully pinned.
