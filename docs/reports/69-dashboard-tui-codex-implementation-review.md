# Phase 69 — Codex adversarial implementation review

**Verdict: NOT COMPLETE / NO-SHIP.** Phase 69 contains substantial implementation, but its completion claim is not supported by the shipped behavior or acceptance evidence. Required ownership, recovery, provenance, history, event, TUI, browser, and documentation contracts remain incomplete. Passing tests often exercise narrower behavior than the plan requires.

**Findings: 51 — 35 P1, 16 P2.** Every finding below includes a fix and regression/acceptance check. Separate observations identify pre-existing formatting, timing-sensitive tests, and unverified threshold-approval provenance without counting them as additional deterministic runtime defects.

## 1. Review subject and method

- Date: 2026-09-18. Branch: `phase/69-dashboard-tui-contract-remediation`.
- Frozen implementation: `ea88324eae379c96b4fb2553d7247ea340b3cc16`; implementation commits `b7966af` and `ea88324`, following planning head `8a15f4e`.
- Contract: `docs/phase-plans/phase-69-dashboard-tui-contract-remediation-plan.md`, SHA-256 `5b8600a6d209f736431165cebf241f7c9503c207fbf0cd62b8bdeab98fcd77eb`, plus the referenced Phase 66 contract and its 24-row reconciliation.
- Method: plan/file-write comparison first; source, callers, AST, assertions, and recorded deviations second; current tests and isolated behavioral probes third. The `orchestrate` skill coordinated GPT-5.6 Sol security/mutation and map/memory reviewers, GPT-5.6 Terra browser/TUI review, and coordinator documentation/integration review.
- Scope: all eight packets, all 39 board tasks, required documentation, failure/recovery paths, concurrency, persisted identity, interface behavior, verification quality, and completion semantics. Existing modified `AGENTS.md` and pre-existing untracked files were preserved. No implementation fixes, commits, or screenshots were made for this review.

References below use repository-relative `path:line` locations at the frozen head. A passing unit test is not treated as browser, Windows, crash-recovery, or historical RED evidence. An absent exact test name alone is not counted as a defect where equivalent assertions exist. Fix sections below specify proposed implementation changes, not APIs or migrations already present. New fields/helpers are proposals for the existing modules; reuse an equivalent existing mechanism where available. Numbered steps state the implementation boundary, failure behavior, and closure evidence.

Severity: **P1** blocks Phase 69 acceptance or breaks a material runtime/security contract; **P2** is a required correctness, documentation, or verification repair. No finding relies on an assumed universal P0 outage.

## 2. Current verification

Commands used Python **3.12.12**, with inherited `PYTHONPATH` cleared. Coordinator commands used `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev ...`.

| Check | Observed result | Interpretation |
| --- | --- | --- |
| `python -m pytest tests/ -q` | **1 failed, 2566 passed, 6 skipped, 15 warnings in 804.98s** | Required full-suite gate fails. Failure: `tests/test_tui_terminal.py::test_no_color_env_suppresses_ansi_color_codes`, line 318; colored control capture was `b''`. **This is the original session's point-in-time observation; a 2026-09-18 independent re-run of this exact command on unchanged source (§12) got `2567 passed, 6 skipped, 0 failed` — see §12/U09 for the full 9-attempt non-reproduction record and why the underlying race-condition fix still stands regardless.** |
| `ruff check src tests scripts` | Exit 0, all checks passed | Lint only; does not establish contractual completion. |
| `ruff format --check src tests scripts` | Exit 1; `src/rush/dashboard/terminal_input.py:86` would be reformatted; 864 other files formatted | Pre-existing formatting defect: file unchanged across Phase 69; last modifying commit `48687df`. Keep separate from introduced regressions. |
| `python scripts/sync_docs.py --check` before adding this report | Exit 1, exactly 20 missing-coverage entries | Three named Phase 66/69 plan/index hash checks are clean. Remaining entries match the plan's permitted historical exception set; this does not validate prose accuracy. |
| Map/memory focused suite: `test_dashboard_map.py`, `test_dashboard_memory_tokens.py`, `test_memory_versions.py`, `test_dashboard_git_artifacts.py`, `test_dashboard_missing_routes.py` | **173 passed, 2 warnings** | Probes below still demonstrate real defects that these tests miss. |
| P69-01 official target (`test_dashboard_http_contract.py`, `test_dashboard.py`, `test_subprocess_contract.py`) | **118 passed, 1 skipped, 5 warnings** | Windows ACL skip; green result misses independently reproduced failures. |
| P69-02 official eight-file target | **3 failed, 203 passed, 1 skipped, 2 warnings** in the independent lane | Timeout-sensitive resume/rescan/artifact tests; first timeout passed isolated. Coordinator's later full suite passed these three. Treat as variable verification evidence, not three additional deterministic product defects. |
| Browser structural suite: `test_dashboard_projects.py`, `test_dashboard_motion_contract.py` | **40 passed** | Primarily structural/source assertions, not complete interaction acceptance. |
| TUI/security focused suite: `test_tui.py`, `test_tui_terminal.py`, `test_dashboard_http_contract.py`, `test_subprocess_contract.py` | **119 passed, 1 failed, 1 skipped** | Same `NO_COLOR` capture failure as coordinator's independent full suite. |
| Direct auth race, independently rerun by coordinator | `sessions_returned 2 stored_sessions 2` | One bootstrap token can create two sessions through concurrent direct calls. |
| Dead-owner recovery, independently rerun by coordinator | `reconciled 1 admission None child_alive True` | Recovery releases admission before terminating recorded child. |
| Native browser / real PTY | Registered-project navigation, real memory revisions, input, preferences, four animation families, abort/backoff, and delayed-map shell readiness observed; PTY color on/off controls pass | Current positive behavior is detailed below. Terminal-event pulse, several complete visible journeys, and historical acceptance evidence remain unclosed. |
| Protected Phase 66 sections 1–5 | Byte-identical to planning baseline `e74995d` | SHA-256 of section 1 onward: `40b286a432e918426e23883f1ab839ca3a9559c1b5c6da0a23a6362ea304cc2a`. Required preservation holds. |

The six skips were Windows data-directory ACL execution and five opt-in real-engine acceptance tests. The 15 warnings concern `fork`/`forkpty` from a multithreaded process in recovery/PTY tests; no deadlock was observed. These warnings are test-isolation concerns, not proof of a production failure. No green Windows result is claimed. The three timing-sensitive P69-02 tests were `test_scan_resume_202_response_attempt_id_matches_the_attempt_resume_scan_run_actually_uses`, `test_rescan_202_response_attempt_id_matches_the_attempt_rescan_project_run_actually_uses`, and `test_artifact_route_and_artifact_export_action_return_real_content_not_404`; preserve their command/environment evidence and investigate isolation before accepting a future variable gate.

### Native browser acceptance observed during this review

The browser lane used a real CLI-registered temporary project and native browser APIs through `agent-browser`; WAAPI, fetch interception, and performance timing were available. Earlier restricted-evaluator limitations were overcome and are not a remaining browser blocker. Temporary fixtures and servers were cleaned up.

| Runtime lane | Observed evidence | Boundary |
| --- | --- | --- |
| Navigation and mutations | Visible Map → Overview → Scans → Memory → Tokens → Git → Artifacts → Setup; grant-denied scan without grants; visible Write/Edit/Archive produced actual revisions 1 → 2 → 3 | Does not prove visible handoff, successful configure/provision, agent connect, multi-project restore, or artifact download. |
| Interaction and accessibility | SVG/list node counts equal; keyboard +/Enter/ArrowRight changed scale to 1.1 and preserved focus; tooltip; drag panned 60/40; 360/1280 viewport focus containment; high-contrast persistence | Native dispatched WheelEvent prevented default and changed scale to 1.1. The automation wheel adapter was inconclusive; no product wheel defect is claimed. |
| Project entry and relationships | Entry group/halo duration 520 ms with `cubic-bezier(.22,1,.36,1)`; samples around 66/516/520 ms. Relationships 360 ms with 24 ms stagger | These current measurements replace the prior source-only characterization of these cases. |
| Inspector and detail rows | Inspector transformed from `perspective(1200px) translateX(24px) rotateY(-6deg)` to final state over 300 ms; 100 detail rows used 180 ms and capped delays 0/32/64/96/128 ms | Real WAAPI inspection; historical RED and reference-video comparison were not reconstructed. |
| Recovery and preferences | Superseded request aborted; successor returned 200. Retry gaps 1.002/2.003/4.004/8.004 seconds. Reduced-motion preference persisted after reload with zero active animations | Real network/animation behavior, not a source-token assertion. |
| Independent shell timing | With map delayed about two seconds, navigation enabled at 299 ms and selection at 318 ms; response at 2,015 ms, nodes at 2,524 ms | Warm-local one-second shell behavior passes. Add durable named regression under U07. |
| Terminal-event pulse | Real scan remained pending at fixture cleanup after 6.2 seconds; memory-write events did not meet the terminal trigger | The 480 ms pulse is specifically unverified; no failure of pulse or scan completion is inferred from fixture duration. |

## 3. Security, ownership, actions, and recovery findings

### S01 — P1: Ownership stops before most real engine executions

**Evidence:** P69-01.2j, plan lines 89–111, requires the owner/run pair through every relevant catalog tool. Engine adapters gained parameters, but 20 of 22 tool-layer `run_engine` sites in 15 files omit them: examples `src/rush/tools/typecheck.py:19–22,57`, `security.py:107,118,137,151`, `format.py:81,88`, `test.py:56,61`, `coverage.py:154`, and `release.py:46`. Only the two LintTool sites forward them (`lint.py:176–216`). `resume_scan_run` and `rescan_project_run` also lack ownership parameters/forwarding (`src/rush/workflows/project_run.py:1345–1433,2113–2198`; callers `src/rush/dashboard/server.py:1500–1507,1600`).

**Impact:** Owned scans, resumes, and rescans can spawn unowned children that recovery and Detach cannot fence. Updating leaf adapters does not close the real call path. The shared dispatch boundary is `InvocationExecutor.execute` (`src/rush/invocation/executor.py:423–479`); reuse the existing `owned_execution_scope` in `src/rush/runtime/subprocesses.py:98–122` rather than changing 15 tool signatures.

**Fix / acceptance — concrete implementation:**

1. **Shared ownership boundary:** Reuse `owned_execution_scope` in `runtime/subprocesses.py:98–122`. In `InvocationExecutor.execute`, wrap the single `operation.handler(*args, **kwargs)` call with that scope using `context.owner_instance_id or None` and `context.run_id or None`. `run_subprocess` already adopts the ambient pair when explicit values are absent. Validate the pair at scope entry so exactly one nonempty value fails instead of becoming unowned. Keep explicit Lint forwarding; do not add redundant parameters across 15 tool modules.
2. **Workflow callers:** Add optional owner identity to `resume_scan_run`/`rescan_project_run`, forward it with the actual executing run into `_execute_attempt_locked`, and update dashboard/TUI callers. Initial scan and CHECK_SUITE already construct ownership-bearing invocation contexts; preserve them. The current 20 affected call paths do not create intervening worker threads, so the context scope reaches version probes and main subprocess calls.
3. **Regression:** Exercise all 15 affected catalog modules through real `InvocationExecutor`, clear version cache, and assert exact ownership at probe/work process boundaries. Test initial, resume, rescan, and CHECK_SUITE producers plus malformed owner/run pair. If a future tool introduces another thread, explicitly propagate context there; do not assume ContextVars cross threads.

### S02 — P1: Dead-owner recovery releases exclusion while children still run

**Evidence:** `src/rush/dashboard/state.py:1403–1417` claims the dead owner and calls `terminalize_and_release` without `reap_owner_processes`. A real recorded process group remained alive after the admission row disappeared: `reconciled 1 admission None child_alive True`. P69-01.2i requires termination before reconciliation/release. This dead-owner path is distinct from the same live owner's pending-outcome bookkeeping; the repair must not reap that live owner.

**Impact:** A new executor can enter while the dead owner's subprocess still changes files.

**Fix / acceptance — concrete implementation:**

1. **Live versus dead owners:** Pass the current recovering server's owner identity into `reconcile_admissions`. A durable pending outcome belonging to this live owner may be retried as bookkeeping without reaping its children. Never treat another instance's pending outcome alone as permission to release admission.
2. **Dead-owner claim:** Acquire `claim_dead_owner` atomically, then call whole-owner `reap_owner_processes` while holding the claim. Only `reconcilable=True` permits rereading pending outcome/effect receipts and terminalizing/releasing. A competing recovery process that fails the claim skips the row; it does not reinterpret the claimant's held lock as proof the original executor is alive.
3. **Unconfirmed termination:** Reuse `record_status_transition(..., "recovery_required", {"code":"termination_unconfirmed", ...})`, preserving admission and process records for later retry. No new recovery-status abstraction is needed. This repair uses existing owner/run identity and is independent of S09's attempt-column change.
4. **Regression:** Cover same-live-owner pending-outcome retry, foreign live-owner exclusion, dead owner with pending outcome and live descendant, failed reap retaining admission, and two competing recovery processes. Kill recovery after confirmed reap but before finalization; restart must consume receipts without repeating effects.

### S03 — P1: Required Windows ownership/fencing implementation is absent

**Evidence:** `src/rush/dashboard/state.py:6` imports POSIX-only `fcntl` unconditionally; `OwnerLock` at `1194–1196` acknowledges missing Windows mutex support. Owned gate execution raises `NotImplementedError` at `src/rush/runtime/subprocesses.py:271–272`; cross-process termination returns `False` at `343–344`.

**Impact:** Windows cannot import this dashboard state module, and its required ownership/fencing paths are unimplemented. The plan's Windows-console acceptance exception does not waive these implementation requirements.

**Fix / acceptance — concrete implementation:**

1. **Lifetime mutex:** Import `fcntl` only on POSIX. On Windows use a session-local named mutex `Local\RushOwner-<sha256(owner_instance_id)>`, owned by a dedicated coordinator thread. Atomically create/open/claim through `CreateMutexW` and zero-time `WaitForSingleObject`; `OpenMutex` alone races object absence. `WAIT_TIMEOUT` means another owner holds it; `WAIT_OBJECT_0`/`WAIT_ABANDONED` gives the claimant ownership. Signal that owning thread to release and join on close. Close every handle. See [Mutex Objects](https://learn.microsoft.com/en-us/windows/win32/sync/mutex-objects) and [ReleaseMutex](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-releasemutex).
2. **Closed gate and inheritance:** Use an anonymous pipe to the gated wrapper; inherit only its read handle through `STARTUPINFO.lpAttributeList['handle_list']` with `close_fds=True`. Never inherit the write end or job handles. EOF exits without executing. The parent persists ownership/process records before writing the release byte. See [Python subprocess handle lists](https://docs.python.org/3/library/subprocess.html) and [Pipe Handle Inheritance](https://learn.microsoft.com/en-us/windows/win32/ipc/pipe-handle-inheritance).
3. **Job fencing:** Before gate release, create a non-inheritable named Job Object, set `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, assign the gated wrapper, and persist job name, root PID, creation time, owner, run, and successful-assignment state. Assignment failure closes the gate and reaps the wrapper. Prohibit breakaway; account for nested/parent job constraints. See [Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects) and [AssignProcessToJobObject](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject).
4. **Recovery and native proof:** If `OpenJobObject` succeeds, terminate and verify zero active processes. If owner death already destroyed a kill-on-close job, inability to reopen alone is insufficient: require recorded successful assignment and creation-time-safe process absence before clearing records. Fail closed on uncertainty. Native Windows tests must cover import, abandonment, inherited-handle leaks, parent-job assignment, death before/after release, descendants, PID reuse, and restart. These official API constraints were researched; no native Windows execution was available in this review.

### S04 — P1: Ledger reservation lacks validated arguments and per-effect identities

**Evidence:** `src/rush/dashboard/state.py:330–344,396–425` persists operation type, operation ID, and body hash, but not the validated argument payload or preallocated effect identities required by plan line 54.

**Impact:** A body hash cannot reconstruct which effects to inspect or compensate after a crash. The multi-stage handoff failure in S05 is one concrete consequence.

**Fix / acceptance — concrete implementation:**

1. **Serialized additive migration:** In `MutationLedger._init_db`, hold `BEGIN IMMEDIATE` across PRAGMA inspection and individual missing-column ALTERs, then commit. Add `validated_arguments TEXT NOT NULL DEFAULT '{}'`, `effect_ids TEXT NOT NULL DEFAULT '{}'`, and `recovery_schema_version INTEGER NOT NULL DEFAULT 0`. New reservations write version 1. Serializing the inspection prevents two server startups racing the same ALTER.
2. **Reservation contract:** Before insert, structurally validate/canonicalize arguments and remove credentials/capabilities. Persist compact sorted-key JSON, complete effect-ID map, and domain identifiers in the reservation transaction. Extend `_Reservation`/`commit` and builder to pass `(operation_id, effect_ids)`; builders consume these IDs rather than remint after reservation.
3. **Per-kind effects:** Use the complete proposed effect-key map below. Generate receipt IDs before reservation; persist domain/object identifiers separately where they are not receipt keys. Builders consume those exact IDs. A read-only preview or no-effect rejection creates no domain receipt. Legacy version-0 pending rows lacking reconstruction data stay recovery-required and admitted where admission exists; never replay a body hash. For maintenance/delete, persist the selected population or deterministic selection boundary rather than rediscovering a changed population during recovery.
4. **Regression:** Test simultaneous process startup migration against the same old database. Crash before builder, after every mapped committed effect, and before ledger finalization. Recovery uses persisted data only, preserves IDs, neither duplicates nor invents effects, and stores no plaintext credential.

#### S04 proposed effect-key map

These are proposed stable keys inside `effect_ids`, not claims that every current effect API already accepts them. Extend the existing effect boundary to consume the reserved ID and record the committed outcome; do not add a second effect implementation. One operation's keys and target IDs must survive retries unchanged.

| Mutating action | Required reserved effect keys / separately persisted identities |
| --- | --- |
| `noop` | Ledger-only result; no domain effect. |
| `provision_apply` | `cursor_key_ensure`, `install:<engine_id>` for every validated plan entry, `toolchain_manifest`; provisioning run/attempt separately. |
| `scan_start`, `scan_resume`, `rescan`, private `CHECK_SUITE` | `scan_manifest_write`, `snapshot_publish`; exact executing run/attempt separately. Run/attempt are domain identities, not receipt IDs. |
| `scan_cancel` | `cancellation_intent`; marker/Event delivery derives idempotently from that durable intent (S10). |
| `handoff_send` | `artifact_create`, `session_create`, `descriptor_prepare`, `delivery_transition`; source run/attempt, artifact/session/handoff IDs separately. |
| `configure` with `apply=true` | `config_write`. |
| `memory_propose` | `artifact_create`; this is the browser Write action's underlying store write. |
| `memory_edit` with `apply=true` | `artifact_edit`. |
| `memory_archive` with `apply=true` | `artifact_archive`. |
| `memory_delete` with `apply=true` | `delete:<artifact_id>` for each validated, sorted target. |
| `memory_promote` | `candidate_create`, `promotion`; candidate artifact identity separately. |
| `memory_maintain` | `maintenance_run` plus `<task>:<artifact_id>` subkeys for each committed mutation; persist selected targets or a deterministic cursor/boundary. |

No domain effect keys for `provision_plan`, `handoff_status`, `memory_query`, `memory_expand`, `data_export`, `artifact_export`, `handoff_preview`, or `configure`/`memory_edit`/`memory_archive`/`memory_delete` with `apply=false`. Add the missing `handoff_preview` classification to `_READ_ONLY_FIXED_ACTIONS` (S06). Direct CLI/MCP reads do not acquire dashboard-ledger effects.

### S05 — P1: Handoff persistence has no required crash-recovery protocol and retains plaintext capability

**Evidence:** `ScanHandoff` lacks `operation_id` (`src/rush/workflows/project_run.py:1647–1730`); `build_handoff` writes artifact/session/descriptor without effect receipt IDs (`1838–1890`). The descriptor stores `session_capability` (`1691,1750,1883`). Required prepared/delivered/acknowledged/complete recovery and orphan-session compensation are absent.

**Impact:** A crash can leave a prepared session or artifact without a reconcilable ledger outcome, repeat preparation, or claim the wrong delivery outcome. Durable plaintext capability also violates the planned hash-only persistence contract.

**Fix / acceptance — concrete implementation:**

1. **Preparation/correlation:** Add operation/effect correlation to persisted handoff state and pass S04's artifact/session receipt IDs through existing effect APIs. Remove persisted `session_capability`. Change preparation to return a transient pair such as `(handoff, raw_capability)`; update real CLI/MCP/dashboard callers together. Authorized standalone prepare may return capability once, and live dashboard send uses it immediately; status and descriptor serialization never include it.
2. **Internal prepared recovery:** Under dead-owner recovery claim, verify operation ID, artifact/session receipts, project, exact source run/attempt, session ID, audience, allowlist, expiry/revocation, and prepared state. Only this internal function may read the bounded verified stored session delta without raw capability; it is not exposed as HTTP/CLI/MCP auth bypass. Never call public receive/authentication with empty or fabricated capability.
3. **Idempotent delivery and monotonic projection:** Share one internal delivery helper between initial send and claimed recovery. Initial send preallocates/persists the delivery nonce. After the checks above, select the exact bounded delta and commit a unique `effect_ids['delivery_transition']` receipt in the store transaction, binding operation, descriptor/session, source attempt, delta artifact/version digest, nonce, and sanitized delivery result. An identical existing receipt returns its stored result; conflicting bindings remain recovery-required. Treat the receipt as authoritative, then atomically project `prepared → delivered` into the file descriptor. A file replacement and SQLite commit are not one transaction: death between them must repair the descriptor from the matching receipt without redispatch. Reuse nonce/session/artifact IDs; never regenerate capability. Preserve existing delivered, acknowledged, or agent-reported-complete stages. Never call `acknowledge_readback`, advance acknowledged versions, or mark complete during delivery recovery.
4. **Orphans/revocation:** Add nullable `revoked_at` through serialized session-table migration and reject revoked sessions on load. A committed session receipt with no matching prepared descriptor is unrecoverable: revoke idempotently and record recovery failure. Mark operation-created artifact orphaned for safe later cleanup; never repeat preparation to replace lost plaintext capability.
5. **Regression:** Crash after artifact receipt, session receipt, prepared descriptor, delivered descriptor, acknowledgment, and completion. Assert exact monotonic state, stable replay/IDs, no duplicated effects or plaintext capability, and no automatic acknowledgment/completion.

### S06 — P1: Handoff preview hash does not bind the complete accepted envelope

**Evidence:** `_handoff_preview_hash`, `src/rush/dashboard/server.py:1652–1672`, hashes selected IDs/source/budgets but omits packet content, exact evidence artifact versions, session allowlist, and the full scope/acceptance envelope. HTTP dispatch does not pass acceptance checks/granted actions, leaving those hashed collections empty. P69-02's preview-to-send contract at plan lines 138–151 requires the whole envelope.

**Impact:** The hash does not prove that the subsequently sent packet and authorization/evidence envelope are the preview the user approved.

**Fix / acceptance — concrete implementation:**

1. **Read-only preview and exact attempt input:** Add `handoff_preview` to `_READ_ONLY_FIXED_ACTIONS`; it must require no mutation grant/reservation/effect. Require `arguments.run_id` and `arguments.attempt_id` for dashboard preview/send. Extend `build_handoff(..., attempt_id=...)` to load that exact manifest. Omitted attempt is malformed for schema-v1 dashboard actions; keep any documented legacy CLI/MCP omission behavior separate.
2. **Canonical server envelope:** From that manifest construct project/source tuple and provenance identity, audience, ordered selected finding records, packet content/bytes, evidence references/versions, session allowlist, budgets, grants, acceptance checks, and accepted constraints. Preserve ordering that affects packet truncation and sort only semantic sets. Exclude generated handoff/session/effect IDs, capability, nonce, and timestamps. Extend the actual argument allowlists/dispatch for these named fields; do not accept a generic client-submitted envelope.
3. **Preview/send parity:** Preview returns the server-rendered packet, source run/attempt, and envelope hash in `handoff_id`. Send echoes exact inputs and claimed hash. Under project/handoff serialization rebuild from the pinned attempt and current authoritative inputs immediately before the first effect; missing attempt/stale envelope gives 409 and zero writes. Preserve S07's async terminal-conflict semantics if invalidation happens after 202.
4. **Regression:** Mutate each bound input independently and assert rejection/no effects. Unchanged input yields identical packet bytes. A newer latest attempt must not alter or substitute for the accepted attempt; concurrent source/evidence mutation at send execution must be detected.

### S07 — P1: Handoff and provisioning do not revalidate expected state at execution

**Evidence:** Scan paths call `_revalidate_expected_at_execution`; provisioning's worker (`src/rush/dashboard/server.py:738–746`) and handoff's worker (`1762–1774`) do not. P69-02.2c requires acceptance-time and execution-time validation.

**Impact:** Accepted work can mutate a changed project after waiting in a background thread.

**Fix / acceptance — concrete implementation:**

1. **Read-only provisioning plan:** Reuse the real `provision_plan` / `build_provision_plan` path to obtain the reviewed plan ID. `run_setup_wizard(install=False)` does not produce that ID and is not an equivalent replacement. Do not rely on install=True plus absent grants as a read-only planning contract.
2. **Durable async supervision:** Reserve sanitized expected values, domain IDs, and complete effect IDs through S04 before launch. Reuse the existing supervisor's durable-outcome mechanics where appropriate; do not automatically apply scan attachment semantics to distinct handoff/provisioning mutations. Each distinct accepted mutation retains its operation identity.
3. **Last effect check:** Handoff revalidates pinned run/attempt/envelope/source under its serialization boundary. Provisioning rebuilds and compares reviewed plan/config/toolchain identity immediately before effects, retaining exclusion across Rush-controlled multi-effect application. On mismatch persist terminal conflict through polling with zero effects; already-sent 202 and replay identity remain unchanged.
4. **Regression:** Pause each worker after 202, change each authoritative input, and resume. Assert no install/download/artifact/session effect, terminal conflict, correct release of any exclusion, stable IDs/replay, and recovery from a committed partial effect using receipts.

### S08 — P1: Synchronous expected validation is a check-then-act race

**Evidence:** `_handle_action` checks a mutable record at `src/rush/dashboard/server.py:4481`, dispatches at `4492`, and finalizes the ledger later. `ProjectRegistry.get` returns the mutable record after releasing its lock (`src/rush/dashboard/state.py:110–112`). There is no common expected-check/effect transaction. P69-02.2b requires a real compare-and-swap boundary.

**Impact:** Two distinct requests can both pass the same expected revision and execute against a state one of them has invalidated. This is a source-established atomicity gap; no claim is made that ordinary sequential tests reproduce the race.

**Fix / acceptance — concrete implementation:**

1. **Canonical shared identity:** Replay identical completed requests first. New requests reserve, then acquire per-project cross-process mutation exclusion. Inside it read the durable latest-published run/attempt pointer and manifest, not another server's stale `ProjectRegistry`. Before any completed scan, derive a shared scalar genesis identity as SHA-256 of canonical JSON `{kind:'unscanned',project_id:<persisted UUID>,generation:0}`; initialize durable generation state, leave published pointer absent, and hydrate every server consistently. Genesis remains until first successful publication, even if an attempt counter was allocated. It does not claim source bytes were scanned.
2. **No project/run nesting:** Preserve existing release of scan `_run_lock` before publication. Acquire project exclusion for publication only after run exclusion ends; never hold both. No caller waits for either lock while a ledger/store transaction is open. Configure takes project exclusion before the existing registry-file lock. Document/assert these actual acquisition rules instead of a generic nested hierarchy.
3. **Effect-specific CAS:** Keep project exclusion across authoritative source comparison and memory owner/version CAS plus receipt in one store transaction. Configure also compares its registry revision/config plan and atomically replaces under registry lock. Commit effect receipt before ledger completion; cross-database work is reconciled rather than described as one transaction. Source identity, artifact version, and config revision are distinct comparisons.
4. **Regression:** Two processes editing the same artifact/version yield one commit and one version conflict; same expected configure revision/plan yields one commit and one conflict. Independent artifacts sharing a source identity may both commit. Verify never-scanned configure/memory still work, first publication replaces genesis, duplicate request replay adds no effect, and death after effect receipt recovers. Race scan completion/publication against synchronous mutations to prove no lock-order deadlock.

### S09 — P1: Attached operations can report the wrong attempt ID

**Evidence:** Admission schema/result omit `attempt_id` (`src/rush/dashboard/state.py:245–259,347–357`). Attach responses use best-effort disk lookup or the losing request's minted attempt (`src/rush/dashboard/server.py:1431–1439,1535–1548,1631–1645`). Plan lines 170–172 and 265–267 require the admitted executor's exact preallocated attempt.

**Impact:** An attachment before attempt-header publication can return a previous or nonexistent attempt, breaking identity and later historical selection.

**Fix / acceptance — concrete implementation:**

1. **Serialized migration:** In one BEGIN IMMEDIATE migration transaction inspect/add `scan_admission.attempt_id TEXT NOT NULL DEFAULT ''`. Extend `AdmissionResult`, inserts, active reads, list/attachment results, and recovery reads.
2. **Executing versus baseline attempt:** Allocate executing attempt before admission for scan start/resume/rescan/CHECK_SUITE/admitted TUI scan. Store winner run/attempt atomically and pass it to the workflow. For resume/rescan, execution identity still captures the baseline attempt being resumed/compared; the admission column contains the new executing attempt. Do not conflate them.
3. **Attachment/legacy:** The attached caller retains its own operation ID but resolves to the stored executing operation/run/attempt. Remove disk lookup and losing-request fallbacks. Empty-attempt legacy active rows remain recovery-required. S02 whole-owner reaping remains usable without this new column.
4. **Regression:** Hold winner before header write: attachment already returns the exact attempt later persisted. Verify baseline identity differs appropriately from executing identity and a fresh execution after release receives a new attempt. Include concurrent old-schema startup migration.

### S10 — P1: Cancellation cannot resolve an attached operation ID

**Evidence:** GET operation status resolves attachments (`src/rush/dashboard/server.py:3711–3753`), but `scan_cancel` accepts only `run_id` (`1450–1463`), and no operation-cancellation route resolves the attached ID. This misses P69-02.2e.

**Impact:** A caller holding its own accepted/attached operation ID cannot use the promised cancellation contract for the real underlying executor.

**Fix / acceptance — concrete implementation:**

1. **Durable cancellation selection:** Extend existing scan_cancel arguments with operation_id, retaining explicit legacy run_id compatibility. In one BEGIN IMMEDIATE ledger method resolve attachments with cycle protection, validate URL project, join active admission, identify executor operation/run/attempt/kind, and insert one idempotent cancellation-intent row. Commit before external delivery. Terminal targets return their stored result; unknown/cross-project targets return uniform 404.
2. **Executor-specific delivery:** Normal scans materialize an attempt-scoped cooperative marker containing executor operation/run/attempt; `_cancel_requested` validates current attempt so old intent cannot cancel a later resume. CHECK_SUITE polls durable intent and uses its existing Event/registered callback only as a fast local wakeup. A process-local Event alone cannot support cancellation from another dashboard process.
3. **Recovery/no nested transaction:** Intent is durable before marker/Event delivery. Retry/recovery rematerializes a missing marker only for the same active attempt; live CHECK_SUITE observes the durable row. Dead-owner recovery terminalizes without re-execution. Never invoke ledger methods that open another SQLite connection while the resolver holds its write transaction.
4. **Regression:** Cancel both scan kinds through direct/attached IDs from the same and second server processes. Cover intent-before-delivery crash, repeated cancel, cycle, wrong project, terminal target/release race, and a new attempt immune to old cancellation.

### S11 — P1: Bootstrap exchange is not atomic at its owning abstraction

**Evidence:** `DashboardAuth.exchange_bootstrap`, `src/rush/dashboard/auth.py:108–117`, separates verification and consumption. HTTP locking masks this for that one route. A direct-call barrier probe creates two sessions from one token; the named test exercises HTTP rather than the required concurrent method calls.

**Fix / acceptance — concrete implementation:**

1. **Owning lock:** Create an internal `threading.RLock` in `DashboardAuth`. Hold it across bootstrap lookup, expiry/used checks, consumption, and insertion of the newly issued session. Guard related token/session mutation and expiry cleanup with the same lock.
2. **Avoid split locking:** Use the reentrant lock or an explicitly lock-held private verifier so calling verification inside exchange cannot deadlock. Remove any reliance on a route-only lock for correctness; direct method callers must have the same single-use guarantee.
3. **Regression:** Synchronize two threads immediately before the public `exchange_bootstrap` call with one token; use a controlled bounded delay after successful verification to widen the old race. Assert exactly one non-null result and exactly one stored session. Never put a two-party barrier inside the now-locked method, which would deadlock a correct implementation. Keep HTTP concurrency and expired-token tests.
4. **Probe distinction:** The vulnerable-method demonstration in section 10 deliberately blocks inside verification to expose the old race. Do not reuse that internal barrier as the fixed regression: locking the entire method correctly prevents both threads from entering it together.

### S12 — P1: Sanitization omits bootstrap and session-cookie secrets

**Evidence:** `DashboardContext.live_secrets`, `src/rush/dashboard/server.py:523–534`, includes control capability and CSRF but omits bootstrap/session-cookie plaintext because only their digests are retained. Response helpers (`378–421`) therefore leak those values if included in finding/exception content. Probe: `bootstrap_leaked True cookie_leaked True csrf_leaked False`. Existing test `tests/test_dashboard_http_contract.py:920–943` injects only CSRF, unlike the plan's broader requirement.

**Impact:** Secret-bearing response content is not universally redacted. Exploitability depends on a secret reaching such content; this review does not claim an unauthenticated credential-read endpoint.

**Fix / acceptance — concrete implementation:**

1. **Thread-safe verifier snapshot:** Add a lock-protected `DashboardAuth` snapshot of active bootstrap/session digests. After S11, `DashboardContext.live_secrets` must use that API rather than iterate mutable private session state without the auth lock.
2. **Request-local credentials:** Pass presented control/bearer token, cookie, and CSRF values into recursive success/error/finding/detail/exception sanitization. Never persist/log this set. Match exact known values and complete token-format candidates; do not blanket-replace arbitrary substrings.
3. **Hash-only matching and issuance:** Hash complete token candidates and compare to verifier snapshots with constant-time equality. Redact matches without retaining plaintext globally or emitting digests. Preserve only intentional Set-Cookie/bootstrap/CSRF issuance fields on authorized routes; exemptions must not expose unrelated body fields.
4. **Regression:** Test nested standalone/interpolated credentials of every kind, active-session churn during serialization, unchanged ordinary text, no digest leakage, and usable authorized issuance. Include expired/consumed request credentials through the request-local set.

### S13 — P2: Security headers are not applied to every response

**Evidence:** JS/CSS responses omit `Referrer-Policy` (`src/rush/dashboard/server.py:3152–3169`); the pre-thread admission 503 omits CSP, nosniff, referrer, and cache headers (`4583–4587`). Existing coverage checks root and health only.

**Fix / acceptance — concrete implementation:**

1. **One header source:** Add a module-level immutable tuple of header pairs or `MappingProxyType` with the exact established CSP, nosniff, no-referrer, and no-store values. A handler helper emits it after `send_response` for JSON, HTML, JS, CSS, and errors. The pre-thread gate cannot use that handler; its raw 503 serializer must iterate the same immutable values.
2. **Early overload path:** Construct the pre-thread 503 from the same values before a handler is allocated. Include `Content-Length: 0`, `Retry-After: 1`, and `Connection: close`; ensure correct CRLF framing and exactly one occurrence of each security header.
3. **Regression:** Assert exact values on root, static assets, API success, authentication/validation errors, rate-limit, and overload responses. Hold eight real socket requests at a controlled blocking handler, issue the ninth socket request, inspect its raw 503 status/headers, release a slot, and verify service resumes. Merely calling the normal response helper does not exercise the pre-thread rejection.

### S14 — P2: Missing schema version is silently accepted

**Evidence:** `_handle_action`, `src/rush/dashboard/server.py:4347–4351`, defaults an omitted `schema_version` to 1. The control-channel `_handle_control_check_suite` path (`src/rush/dashboard/server.py:3528–3657`) has the same missing-field acceptance and must be corrected too. P69-02.2a requires the version field.

**Fix / acceptance — concrete implementation:**

1. **Both action boundaries:** Require schema_version presence and `type(value) is int`, then supported value 1, in `_handle_action` and `_handle_control_check_suite`. Both currently default omission; fix the shared validation rule rather than only the browser action route.
2. **Error ordering:** Missing/null/string/bool returns malformed-request; unsupported integers use established unsupported-version response. Validate before hashing, reservation, admission, or effects; booleans must not pass Python's integer subtype check.
3. **Regression:** For both endpoints send otherwise valid requests with missing, null, string, true, 0, and 2, asserting 400 and no ledger/process/effect change. Explicit integer 1 retains valid behavior.

### S15 — P1: TUI can reserve recoverable work without its owner lifetime lock

**Evidence:** `src/rush/tui.py:487–503,531–563` suppresses owner-lock/admission failures and continues. P69-01.2h, plan line 68, requires successful lifetime-lock acquisition before reserving recoverable work.

**Impact:** Recovery may classify a still-running TUI executor as dead; a missing lock is not equivalent to permission to proceed.

**Fix / acceptance — concrete implementation:**

1. **Retain successful ownership:** Replace string-only TUI owner state with retained ID/acquired OwnerLock object. Acquisition failure stops every local path that supplies ownership or reserves recoverable work. Idempotent close occurs only after local workers have joined/reaped during coordinator shutdown, not per project.
2. **Honor admission result:** `_admit_local_run` returns/checks AdmissionResult. Only started=True may launch a worker; attached=True adopts stored executor operation/run/attempt and observes it. Conflict/error displays failure and launches nothing. Handle reservation/admission/thread-start failures without orphan worker/process records or incorrectly releasing another executor's admission.
3. **All local producers:** Initial scan, rescan, and CHECK_SUITE obtain that retained owner before passing owner/run; resume/rescan forwarding uses S01. Preserve separate dashboard ownership. One project finishing must not release an owner lock needed by another local job.
4. **Regression:** Fault lock, reservation, admission, attachment, and worker launch separately. Verify no unauthorized child, exact attached identity, live-owner non-reclaimability, multi-project lifetime, clean shutdown, and native Windows owner behavior.

### S16 — P2: Handoff/provisioning responses omit required attempt identity

**Evidence:** Provisioning's 202 response (`src/rush/dashboard/server.py:752–756`) and handoff's (`1776–1780`) omit `attempt_id`, despite P69-02.2d at plan line 170 requiring operation/run/attempt identities.

**Fix / acceptance — concrete implementation:**

1. **Handoff source tuple:** Preview/send/202/status use S06's exact required source run_id/attempt_id plus a distinct ledger operation_id. Persist the pair in reservation/recovery data. Never mint another send attempt or choose latest during recovery.
2. **Provisioning job tuple:** Allocate provisioning's own run/attempt before reservation and store both in S04 arguments/receipts. Return them through status, acceptance, and replay. Do not require scan-admission attachment storage if S07's corrected launcher keeps provisioning outside scan attachment; durable ledger identity is required.
3. **Regression:** Handoff acceptance/status match preview's source tuple; provisioning acceptance/status/receipts match its allocated job tuple. Identical replay preserves all IDs. Crash immediately after 202 and recover without reminting or substituting an attempt.

## 4. Map, provenance, memory, telemetry, and artifact findings

### M01 — P1: Published records mutate after readers obtain them

**Evidence:** `src/rush/dashboard/state.py:80–93,110–112,158–240` returns live `ProjectRecord` objects and mutates their snapshot, source identity, and sequence in place. Plan lines 342–344 require immutable publication and one atomic swap.

**Fix / acceptance — concrete implementation:**

1. **Immutable values:** Make `ProjectRecord` a frozen dataclass while keeping snapshots JSON-compatible. Deep-copy input in `ProjectRegistry.__init__`, `register`, `refresh_memories`, and `publish_scan_result`; return detached records from `get`, `register`, and `list_page`. Never expose stored nested dictionaries to caller mutation.
2. **Atomic, disjoint-field merge:** `_publish_scan_snapshot` passes only scan-owned fields and generation into `ProjectRegistry.publish_scan_result`; it must not assemble a whole snapshot from an earlier `record.snapshot`. Under `_lock`, merge those fields into the lock-current record's memories/agents and replace one frozen record. `refresh_memories` merges memories into the lock-current scan fields. Keep `ProjectRecord.sequence`/`source_identity` authoritative and derive any compatibility snapshot fields from them during serialization.
3. **Required callers:** Hydration remains on `publish_scan_result`. Remove pre-lock memory reads in scan adaptation and direct assignments to records returned by `get`. All publication/generation checks and the final pointer swap occur inside the same lock; a detached snapshot alone does not prevent lost updates.
4. **Regression:** Pause scan publication after result adaptation, commit/publish newer memories, then resume scan publication. Both updates must survive. Hold old reader references throughout and verify their nested data stays unchanged; stale generations must not overwrite a newer record.

### M02 — P1: Map publication discards actual consumed-source identity

**Evidence:** Normal terminal manifests build consumption identity (`src/rush/workflows/project_run.py:673–713,995–1018,1563–1573`), but publication substitutes live `_source_signature(root)` (`src/rush/dashboard/server.py:964–1006`, specifically 998). Hydration repeats that substitution (`1041–1085`). CHECK_SUITE's manifest (`1185–1253`) lacks required content identity, inventory, generation, and Git provenance and bypasses equivalent staging.

**Fix / acceptance — concrete implementation:**

1. **Scalar identity versus provenance:** Keep `ProjectRecord.source_identity`, snapshot `source_identity`, cursors, and `expected.source_identity` as strings containing the manifest's deterministic aggregate digest. Store the complete provenance object separately, proposed as `scan_provenance`; never assign the whole dictionary into a scalar identity field. Remove live `_source_signature(root)` fallback for completed attempts.
2. **Producer parity:** Persist `file_inventory`, `scan_generation`, consumed path digests, repository-state evidence, Git link, and aggregate identity in `_build_manifest` and CHECK_SUITE's writer. `_snapshot_from_scan_result` accepts these persisted values rather than recomputing them. CHECK_SUITE must stage/capture before `run_workflow_suite`.
3. **Publication order:** Allocate generation; capture inventory/Git state; stage and execute; atomically write terminal manifest; call `ProjectRegistry.publish_scan_result`; record publication outcome; update `MutationLedger.record_published_scan` only if registry publication won. Version new required persisted fields explicitly. Legacy manifests expose unavailable provenance and never substitute current-tree state.
4. **Regression:** For initial scan, resume, rescan, and CHECK_SUITE, scan bytes A, change the live tree to B, and hydrate through a second server and restart. The selected attempt must retain A's identity, inventory, generation, and Git evidence.

### M03 — P2: File inventory is not persisted and hydration rewalks current files

**Evidence:** `_build_manifest` at `src/rush/workflows/project_run.py:673–713` lacks inventory; hydration falls back to current files at `src/rush/dashboard/server.py:1069–1082`. Inventory walkers at `server.py:898–915` and `project_run.py:1501–1522` duplicate `SKIP_DIRS`/dot-directory filtering. Plan line 289 requires persisted inventory using the existing repository convention. Follow-up checked `src/rush/review/collection.py:76–94` and `src/rush/tools/routing.py:52–89`: these establish skip-directory behavior, not an existing `.gitignore`/`.rushignore` parser. The finding is frozen-inventory loss; a missing ignore-file parser is not independently established as a defect.

**Fix / acceptance — concrete implementation:**

1. **Reuse the verified convention:** Base the shared inventory collector on the current `SKIP_DIRS` and dot-directory convention used by `tools/routing.collect_files`, preserving relevant declared scan scope. The reviewed `_collect_reviewable_files` and `collect_files` do not demonstrate a `.gitignore`/`.rushignore` parser; do not introduce one and call it existing behavior. Any claimed additional supported exclusion requires evidence from its actual helper.
2. **One capture:** Replace the duplicate inventory walks in `dashboard/server.py` and `workflows/project_run.py` with one captured, sorted project-relative inventory at attempt start. Include covered-but-engine-skipped files; inventory is broader than a candidate's consumed paths.
3. **Persist and hydrate:** Write that exact inventory into the attempt header and terminal manifest and make hydration read it. A legacy attempt without inventory must expose missing provenance, not silently substitute files present now. Keep this distinct from the per-engine scope correction in M16.
4. **Regression:** Include skipped directories, dot directories, a clean file, and a file whose engine is unavailable. Add/remove files after the attempt, restart, and assert the original inventory is unchanged and all currently supported exclusions match the canonical collector.

### M04 — P1: Event API omits real candidate events and retains the wrong unit

**Evidence:** Real candidate progress writes attempt `events.json` (`src/rush/workflows/project_run.py:823,889–943,1023,1226–1261`). Dashboard ledger receives status transitions only (`src/rush/dashboard/state.py:529–592`); retention prunes by project (`278,543,585–590`), not 2,000 per run. Route `src/rush/dashboard/server.py:3755–3803` serves that narrower stream. Tests at `tests/test_dashboard_missing_routes.py:1075–1164` manufacture ledger transitions instead of real candidate events.

**Fix / acceptance — concrete implementation:**

1. **Durable event identity:** Extend `dashboard_events` with run, attempt, attempt-local sequence, event kind, candidate, outcome, payload, and stream classification; retain project-global `sequence` as API cursor. Candidate-log replay dedupes on `(project_id, run_id, attempt_id, attempt_sequence)`. Scan lifecycle transitions carry the admitted run/attempt explicitly and use a separate `(project_id, operation_id, transition_ordinal)` dedupe key, so correlation survives admission release. Non-scan operation events are explicitly classified and do not consume a scan run's 2,000-row allowance.
2. **Real producer connection:** Thread the existing event sink through workflow execution and `_append_event`. Once an event is durable in the attempt event log, ingest it into the dashboard stream. On restart replay un-ingested events idempotently; an ingestion failure must be recoverable and visible rather than replaced by fabricated status events.
3. **Retention and cursors:** Prune independently by `(project_id, run_id)` to 2,000 rows. Since `/events` is project-wide, persist a project cursor floor equal to the greatest global sequence deleted by any run. Reject `after < floor` with 409; never compare a project cursor to an arbitrary run's floor. Return at most 100 rows ordered by global sequence.
4. **Regression:** Run actual candidates that emit progress/outcomes, interrupt between log write and ingestion, and restart. Assert exact candidate events without duplicates. Produce more than 2,000 events in each of two runs and verify independent retention, paging, and expired-cursor behavior.

### M05 — P1: Grouping drops relationships without reachable expansion

**Evidence:** `src/rush/dashboard/project_map.py:499–510` drops edges whose endpoints collapse into the same group. At `547–583`, summary slicing/overflow self-loop cursors can also lose reachability; expansion at `769–863` cannot resolve ordinary relationships through that overflow shape. A 101-file/101-finding fixture produced `map_total_edges=202`, `rendered_edges=2`, and `rendered_reports=0`: all 101 report relationships vanished.

**Fix / acceptance — concrete implementation:**

1. **Preserve internal relationships:** In `project_map.py`, bucket every source edge by rendered source, rendered target, and relationship type. When both endpoints collapse into one group, emit an expandable counted self-summary rather than dropping the relationship.
2. **Budget before rendering:** Reserve one summary for every nonempty `(resolved_source, resolved_target, relation)` bucket before optional detail edges. If summaries exceed the budget, emit relation-level overflow summaries whose selector covers every relationship omitted by overflow.
3. **Exact, compact expansion:** Encode selector, offset, and frozen-view tuple in cursors, not entire edge-ID arrays. Ordinary selectors contain relation/resolved-source/resolved-target; overflow selectors identify the omitted relation bucket explicitly. `expand_group_edge` rebuilds the frozen graph, selects matching edges, sorts IDs, and pages them. Add explicit self-group/overflow branches; current source/target matching cannot resolve project self-loop overflow.
4. **Regression:** Use the 101-file/101-finding reproduction plus multiple relationship types and a forced overflow budget. Expand every summary across every page; the union must equal the full source edge set, including all 101 report edges, while the rendered map stays within budget.

### M06 — P1: Historical views can select latest attempt and expand live data

**Evidence:** `src/rush/dashboard/server.py:3832–3853` accepts historical `run_id` without `attempt_id`; `_historical_map_snapshot:1108–1163` then allows latest-attempt resolution. Base map uses the historical snapshot, while group/edge expansion passes `record.snapshot` at `3887–3905`. Probe: historical first member `old-0`; expansion using the server's live argument returned `new-0` (201 members).

**Fix / acceptance — concrete implementation:**

1. **Exact selector:** Reject a historical map request unless both `run_id` and `attempt_id` are supplied and resolve together. Remove latest-attempt resolution for historical views; current-view convenience must not change historical URLs.
2. **One resolved view:** Return selected snapshot plus `view_id=("run", run_id, attempt_id)` from `_historical_map_snapshot`. Add a `view_id` keyword to `expand_group` / `expand_group_edge`; `_handle_snapshot` passes that same snapshot/view ID to base construction and both expansion paths. Never default historical expansion to `("current",)` or `record.snapshot`.
3. **Cursor binding:** Include `view_id` in the existing `_cursor_tuple` alongside project, scalar source identity, sequence, and filter hash. Reuse against another attempt/current view raises `CursorRejected`, serialized as HTTP 409. Missing legacy identity remains unavailable rather than a live-data fallback.
4. **Regression:** Create two attempts under one run with disjoint grouped node/edge IDs. Mutate the live tree and resume the run; every old expansion page must remain old, and old cursors used with the other attempt must conflict.

### M07 — P1: Edit/archive/delete/promote do not refresh published memory data

**Evidence:** Dispatch paths `src/rush/dashboard/server.py:1820–1972,2031–2046` do not call `_refresh_project_memories`; only propose/maintain do so at `2239–2316`. This misses plan lines 361 and 559–567.

**Fix / acceptance — concrete implementation:**

1. **Shared dispatch:** Make `_dispatch_memory_edit`, `_dispatch_memory_archive`, `_dispatch_memory_delete`, and `_dispatch_memory_promote` accept `DashboardContext`; update `_dispatch_scan_action` callers. Put these and propose/maintain on the existing shared post-commit refresh path.
2. **Detect actual commits:** Read the pre-operation memory generation using the existing read-only store-opening path; a nonexistent store has no prior generation. Do not construct a writable store just to inspect a preview. Execute the action, then read `snapshot_memories()` from the resulting existing store and publish only a newer generation. Promotion can write a candidate artifact before later trust promotion is denied; refresh that real commit even if the final action reports denial.
3. **Publish once:** Pass the atomic `(memories, generation)` pair once to `ProjectRegistry.refresh_memories`. The generation guard rejects stale concurrent refreshes. Remove duplicate route-specific refreshes. Preview, validation/owner/CAS failure without a commit, and unchanged maintenance cause no fabricated sequence bump.
4. **Regression:** For every mutation, verify immediate map content and exact generation/sequence changes. Include promotion that creates a candidate but denies the later promotion, as well as genuine zero-write failures, preview on nonexistent/legacy stores, and out-of-order refreshes. Preview must leave filesystem/database bytes unchanged.

### M08 — P1: Dashboard owner scope is optional and not bound to the URL project

**Evidence:** Allowlists/dispatch accept omission (`src/rush/dashboard/server.py:262–314,1957–1969,2267–2277`). `_parse_owner_scope` accepts no scope and arbitrary nonabsolute project IDs (`src/rush/tools/memory.py:1040–1062`); legacy fallback lives at `src/rush/memory/store.py:137–148,613`. A temp-root write with an unrelated UUID owner returned `status=ok`. The dashboard adds no URL-project equality check.

**Fix / acceptance — concrete implementation:**

1. **Validate before reservation:** Add a narrow `_validate_memory_owner_scope` helper called in `_handle_action` after argument/boolean validation but before `body_hash` and `MutationLedger.commit`. Pass the exact authenticated `session.owner_scope_id` already returned to that handler, selected URL project ID, and requested owner. Write its normalized owner back into `arguments`; every five-form memory mutation plus owner-scoped maintenance uses it. Validation inside the later builder is too late to satisfy zero-reservation failures.
2. **Identity rules:** Project ID equals the registered URL project; session ID equals this request's authenticated `Session.owner_scope_id`; user/agent IDs are opaque caller-supplied nonblank strings, structurally validated only. Never choose an arbitrary session from `ctx.auth`, authenticate opaque labels, or use cookie/CSRF values or digests as owner IDs. Expose only `owner_scope_id` in the authenticated session response for U10's browser control. Dashboard-backed TUI actions already exchange a real session through `_control_session`; standalone TUI memory retains its own invocation owner ID.
3. **Compatibility:** Keep legacy project-path fallback only in explicitly supported direct CLI/MCP entry points. Dashboard adapters must always pass the normalized owner object to the existing owner-aware store methods; no new database schema is required.
4. **Regression:** Exercise write/edit/promote/archive/delete with all four owner kinds. Omitted/incomplete owner, foreign project UUID, wrong session, empty user/agent ID, and mismatch with an existing row's owner must fail before any row/version/receipt changes. Arbitrary nonempty user/agent labels must be accepted structurally, persist unchanged, and remain subject to exact owner/version checks.

### M09 — P1: TUI and maintenance disagree with registered-project ownership

**Evidence:** TUI defaults project ownership to the raw path (`src/rush/tui.py:1100–1117`); `ProjectState:329–348` has no project ID. Maintenance/sweep owner remains optional (`src/rush/memory/maintenance.py:81–97`, `expiry.py:59–75`), MemoryTool maintain drops it (`src/rush/tools/memory.py:441–459,1188–1211`), dashboard maintain omits it (`server.py:311`), and CLI maintain has no owner flags/registered-ID lookup (`src/rush/cli.py:2762–2797`). `tests/test_memory_versions.py:759–780` codifies the incorrect registered-path assumption.

**Fix / acceptance — concrete implementation:**

1. **TUI identity:** Add optional canonical `project_id` to `ProjectState` and resolve it through the existing project registry when loading the root. Fall back to the root path only for an explicit project-not-found result; registry failures must not silently change ownership.
2. **Transport and caller migration:** Carry normalized owner through CLI maintenance, `MemoryTool.__call__`/`run`/`_run_maintain`, dashboard maintain, TUI maintenance, `run_maintenance_cycle`, and `sweep_expired`. Add CLI owner flags with registered UUID defaults and unregistered-path fallback. In the same change update every direct call and spy assertion in `tests/test_phase62_maintenance.py`, `tests/test_phase62_expiry.py`, and `tests/test_memory_core_regressions.py`; run these focused modules rather than discovering required-signature failures only in the full suite.
3. **Scoped transaction:** Make owner mandatory in `MemoryTool._run_maintain`, `run_maintenance_cycle`, and `sweep_expired`. Apply `owner_scope_kind=? AND owner_scope_id=?` to selection and mutation in one transaction. Include NULL-owner legacy rows only when requested owner equals `legacy_owner_scope(root)`; `owner_scope_for_row` maps these to path ownership, not a registered UUID. Preview/read-only paths must not backfill ownership.
4. **Regression:** Seed project-, user-, agent-, and session-owned rows for one subject/root. TUI edit and CLI/dashboard maintenance must reach the registered project's UUID-owned row and leave every other owner's version, trust, and expiry unchanged. Correct the test that currently expects a registered path owner; retain a separate unregistered-root test.

### M10 — P1: Token filters leave displayed totals unfiltered

**Evidence:** `_build_tokens_section`, `src/rush/dashboard/server.py:2909–2976`, requests project-wide telemetry/memory totals; run/agent filters affect only handoff rows and session filtering is absent. `TelemetryStore.get_memory_event_total` already supports filters (`src/rush/token_economy/telemetry.py:185–220`), while `get_summary:252–280` does not. Existing tests assert handoff rows rather than totals.

**Fix / acceptance — concrete implementation:**

1. **Query API:** Add optional project/run/agent/session filters to `TelemetryStore.get_summary`, using the same clause builder as `get_memory_event_total`. Filter token-event count/raw/compressed aggregates there. In `_build_tokens_section`, separately pass identical filters to each `get_memory_event_total(kind=...)`; `get_summary` does not own memory-event by-kind groups.
2. **One selection:** Parse the route's selection once in `_build_tokens_section` and pass it to token totals, memory-event totals, and handoff rows. Use the registered canonical project ID. Add indexes only if the existing query shape needs them; do not introduce another telemetry store.
3. **Legacy semantics:** Exclude genuinely unscoped legacy rows from a narrower identity selection and retain the existing explicit unavailable/provider-usage semantics. A missing attribution must not be guessed into the chosen run.
4. **Regression:** Seed two runs, agents, and sessions with intentionally different counts/token values. Assert exact overall, individually filtered, combined-filter, and by-kind totals for every displayed field, including empty results.

### M11 — P1: Real telemetry calls lack complete invocation/attribution propagation

**Evidence:** `MemoryTool.run` has no reusable invocation argument (`src/rush/tools/memory.py:280–470`) and constructs content-derived request IDs at `663,679,762`. Retrieval mints UUIDs lower down but records path project identity without run/agent/session (`src/rush/memory/retrieval.py:454–463,594–604,641–650`). Continuity's boundary UUID additions (`src/rush/tools/continuity.py:146–178,455–489`) do not complete all attribution paths.

**Fix / acceptance — concrete implementation:**

1. **Public invocation boundary:** Add optional invocation ID and project/run/agent/session attribution to `MemoryTool.__call__` / `run` and continuity public boundaries. Mint invocation once when absent and thread through compact query, hybrid, recall, expand, context retrieval, and fallbacks. Keep content-derived `request_id` only as descriptive attribution, not invocation identity. Lower retrieval currently mints UUIDs, so distinct identical calls already avoid collision; the defect is inability to reuse one invocation across retries and branches.
2. **Attribution:** Resolve canonical project identity at that boundary and carry project/run/agent/session throughout retrieval and telemetry writes. Use the defined explicit unscoped sentinel only when a dimension truly is unavailable; do not substitute a path for a known registered UUID.
3. **Retry semantics:** Reuse the invocation ID for retry of the same logical call and enforce existing telemetry deduplication on that ID plus the relevant event identity. Separate user calls with identical content must receive different IDs.
4. **Regression:** Execute real hybrid, recall, expand, and context-retrieve routes rather than inserting telemetry directly. Assert two identical distinct calls count twice, one retry counts once, and persisted attribution columns match the public invocation on every success/fallback branch.

### M12 — P1: Historical artifacts serve current bytes and paging corrupts content

**Evidence:** References include attempt identity (`src/rush/workflows/projects.py:1093–1122`), but download resolves `paths[0]` under the current project (`src/rush/dashboard/server.py:4158–4204`, `_read_artifact_page:2485–2514`). A helper-level probe, independently repeated by the coordinator, read `attempt-A`, overwrote the same logical path, then read `attempt-B`. Combined with the route's current-path selection, this demonstrates the missing immutable boundary; it was not an end-to-end HTTP request using two persisted attempts. Test `tests/test_dashboard_git_artifacts.py:771–809` checks distinct labels, not distinct bytes. A separate byte-paging probe used original hex `41e282ac4200ff` and page sizes 2/2/3: decoding each byte slice with UTF-8 replacement produced `A�`, `��`, and `B\u0000�`; re-encoding yielded `41efbfbdefbfbdefbfbd4200efbfbd`, not the original bytes. Thus text spanning a page boundary and binary artifacts are also corrupted by `_read_artifact_page`.

**Fix / acceptance — concrete implementation:**

1. **Capture before overwrite:** Add a separate `CandidateResult.artifact_snapshots` collection. Immediately after each `_execute_candidate` returns and before `_persist_candidate_evidence` or another candidate runs, copy declared artifact bytes into the current attempt's contained artifact directory, keyed by candidate and path. Use temporary write, fsync, and atomic rename. Each entry records logical path, immutable relative path, byte size, SHA-256, and media type. Preserve canonical `ToolResult.artifacts: list[str]`; aggregate consumers cannot accept object elements.
2. **All producer/resume paths:** Serialize snapshots in candidate evidence, reload them in `_load_completed_candidates`, and assemble already-captured entries in `_finalize_attempt`. CHECK_SUITE uses the existing `run_workflow_suite(on_tool_complete=...)` seam to capture each child before the next tool, with a stable child ordinal/tool key and atomic incremental sidecar. Compose this into dashboard `_dispatch_check_suite` and CLI `_run_initial_scan`, then pass entries into `publish_check_suite_scan`. Missing, unreadable, or out-of-root output produces explicit incomplete/capture-error evidence, never a live-file fallback.
3. **Exact content contract:** Keep the existing authenticated artifact GET and outer success envelope. Within `data.content`, return `path`, byte `offset`, whole-artifact byte `size`, `content_base64`, byte `next_offset` (null at completion), whole-artifact `sha256`, and `media_type`. Resolve only the selected run/attempt's snapshot entry, validate containment and immutable metadata, and base64-encode raw bytes without per-page text decoding. Listing preserves logical `paths` compatibility while preferring snapshot metadata. Legacy path-only references report immutable-content-unavailable.
4. **Regression:** Two candidates within one attempt must retain different original bytes even when both write the same logical filename; two attempts and resumed completed candidates must also retain their own copies after restart. Cover CHECK_SUITE per-child capture and recovery of its sidecar. Download more than two pages containing split UTF-8, NUL, and `0xff`; concatenated bytes/size/hash must match. A reference and offset for A can never select B. Update browser, route tests, and documentation together for the new lossless wire fields.

### M13 — P2: Repository-state evidence becomes an impossible Git path

**Evidence:** `src/rush/workflows/project_run.py:917–927` inserts a synthetic `candidate_id:kind` digest; `_build_manifest:684–691` copies it into `git_link.path_digests`. `src/rush/workflows/projects.py:1031–1070` interprets every key as a real repository path for `git show commit:path`.

**Fix / acceptance — concrete implementation:**

1. **Separate evidence types:** Replace `CandidateResult.source_digests` with proposed `consumed_path_digests` and `repository_state_evidence`. Update `to_dict`, `_persist_candidate_evidence`, `_load_completed_candidates`, resume carry-forward, `_finalize_attempt`, and manifest serialization together. Legacy evidence is path-verifiable only when its keys are provably actual paths; mixed synthetic/path dictionaries are Git-unverifiable rather than guessed apart.
2. **Identity aggregation:** Hash both structures with explicit domain tags and deterministic serialization so changing either still changes consumed-source identity. Only actual project-relative paths populate `git_link.path_digests`.
3. **Git lookup:** Make path-based matching and `_git_show` consume only the path-digest collection. Treat old manifests that cannot distinguish synthetic evidence as unverifiable; do not guess a path/evidence split from punctuation in a filename.
4. **Regression:** Execute GitGuard, DiffCover, and Undercover through the real scan route. Assert no synthetic key reaches `git show commit:path`, a clean matching commit links correctly, and changed source or repository-state evidence prevents a false match.

### M14 — P2: Memory browsing silently truncates at 10,240 rows per subject

**Evidence:** `src/rush/dashboard/server.py:2713–2719,2796–2850` reads at most 20 batches of 512 and derives page totals from that truncated collection, contrary to plan line 596.

**Fix / acceptance — concrete implementation:**

1. **Preserve both read contracts:** For empty-query browse, add `TypedArtifactStore.page_artifacts` with existing subject/source/trust/persisted-expiry/archive predicates before COUNT/LIMIT. Do not add a new owner filter under this finding. For text query, extend the existing MemoryTool/retrieval path, which performs dynamic freshness revalidation, rather than replacing it with direct SQL. When text search requests freshness filtering, compute the eligible total after that same revalidation; an unfiltered SQL candidate count is not the final total.
2. **Consistent paging:** Read browse total/page in one store read transaction with deterministic ordering. Preserve query mode's dynamic-freshness semantics and `dynamic_freshness_checked` indication. Both continuations bind normalized filters and memory generation; reject a changed generation rather than mix pages. Eliminate the 20-by-512 materialization ceiling in both paths.
3. **Route response:** Return the true filtered total and next cursor directly. Do not infer totals from a capped in-memory sample, and do not hide archived rows merely after page slicing.
4. **Regression:** Seed more than 10,240 rows with mixed archive/source/trust/expiry values. Traverse browse and query results to the end with exact totals and unique IDs. Include a record whose live source becomes stale: query-mode freshness must still exclude/mark it as before. Mutate memory generation and verify cursor rejection.

### M15 — P1: In-process tool reads bypass staged bytes

**Evidence:** `_execute_candidate` passes the live project root into tools (`src/rush/workflows/project_run.py:586–670`); only nested `run_engine` invocations redirect to staging. Direct readers include slop, offline-review, dead-asset, license-matrix, and other applicable tool implementations. With staged `x.js='// clean'`, changing live content to `'// generated by ai'` made `SlopTool` report `rush-ai-marker` and leave `source_digests={}` (`src/rush/tools/slop.py:21–60`). Plan lines 295–313 require actual immutable consumed-byte identity.

**Fix / acceptance — concrete implementation:**

1. **Invocation boundary:** Obtain `staging = active_staging()`. For source-reading staged candidates, pass both request path and `InvocationContext.workspace_root` as `staging.staged_root` through `resolve_invocation`; a staged target under the live workspace root fails containment or gets reconstructed incorrectly. Keep canonical live project identity separately only through explicit metadata accepted by the consuming tool. Ordinary unstaged invocations retain their current behavior.
2. **Reads and results:** Record successful source reads through active staging in slop, offline runner, dead-asset, license-matrix, and other applicable direct readers. Do this at the actual read boundary, including clean files. After `InvocationExecutor.execute` and before finding IDs/evidence are created, apply structural staged-to-logical path remapping to direct-tool finding/artifact/raw path fields; do not rewrite literal messages or fix text.
3. **Explicit exceptions:** Keep repository-state engines on their declared repository-state path with separate evidence. Preserve mutation permissions and semantics: a command that intentionally writes live source cannot be represented as an immutable read-only scan by silently pointing it at a disposable tree. Resolve its scan role through the existing planner contract.
4. **Regression:** Stage clean source, alter the live source to introduce a marker/failure, and run the real tool candidate. Results and digests must reflect the staged bytes. Cover a clean file that yields no finding, all affected direct-reader routes, and CHECK_SUITE parity.

### M16 — P1: Per-engine coverage claims every staged file despite explicit targets

**Evidence:** `_staged_invocation` records the whole `run_path` (`src/rush/runtime/subprocesses.py:667–669`); recording the project root includes every inventory file (`src/rush/engines/staging.py:216–232`). Lint/format/typecheck pass the root plus explicit file arguments. Probe with target `a.py` recorded both `a.py` and unrelated `b.js` as consumed. Plan lines 289,295–305 distinguish inventory from per-engine consumption.

**Fix / acceptance — concrete implementation:**

1. **Declared scope:** Add proposed `consumed_paths` to `run_engine` / `_staged_invocation`. Adapters with explicit targets pass original logical paths. Resolve relative targets against original root, validate/substitute them, and record only the staged targets. Do not record whole `run_path` when explicit targets exist.
2. **Root/support semantics:** Omitted explicit paths means root-scoped only when the command actually receives root as its scan target. An explicitly passed configuration file belongs in declared consumption. Do not claim symlinked dependency trees solely because the engine could access them; report observable evidence without asserting exact unseen dependency reads.
3. **Call sites:** Update lint/format/typecheck and every adapter passing root plus file arguments. Ensure the source identity is aggregated at candidate boundaries so one engine cannot inherit unrelated consumption from another candidate.
4. **Regression:** With inventory `a.py` and `b.js`, an explicit `a.py` candidate must not claim `b.js`; cover relative and absolute targets. A true root-scoped scan records its full staged source scope. An explicitly passed/read configuration affects provenance. Do not demand changes for unobserved symlinked dependency reads: Rush must not claim evidence it did not capture.

### M17 — P1: Required repository-state engines are unreachable through actual scan routing

**Evidence:** `_execute_candidate` immediately returns `ENGINE_ROUTE_MISSING` for engine-kind candidates (`src/rush/workflows/project_run.py:586–610`). GitGuard and DiffCover have no owning tool route; Undercover is available only through the explicit coverage tool. Inventory: 121 registered engines, 32 actual tool-owned names, 89 unowned planner rows (not a claim that all 89 are installed/applicable). Probe of the GitGuard candidate returned `outcome=unavailable`, `status=skipped`, `summary='skipped: ENGINE_ROUTE_MISSING'` before binary lookup. Plan lines 327–334 require real repository-state provenance.

**Fix / acceptance — concrete implementation:**

1. **Canonical engine route:** Resolve `candidate.candidate_id` through `rush.engines.ENGINES` and obtain binary/routing metadata from `rush.catalog.ENGINE_SPECS`, then invoke shared `run_engine`. `EngineSpec` has no permission field. Read-only candidates use empty `required_permissions`; privileged engines require an explicit existing/planner permission mapping or remain requires-input/unsupported, never invented grants or dummy owning tools.
2. **Execution context:** Pass owner/run identity, candidate arguments, staging or repository-state mode, and attribution through canonical `run_engine`. Preserve existing candidate-boundary cancellation. `run_engine` and `Engine.run` have no `cancel_check` parameter; this routing repair must not silently promise a new mid-engine cancellation API.
3. **Honest failures:** A missing registry entry remains `ENGINE_ROUTE_MISSING`; a registered engine whose binary is absent uses `run_engine`'s structured skipped result; denied explicit permission remains `permission_blocked`. Preserve these distinctions in `CandidateResult`.
4. **Regression:** Execute an applicable GitGuard/repository-state candidate through `execute_scan` with a real installed engine or a controlled executable fixture. Assert actual subprocess execution and persisted evidence. Separately test absent binary, denied grant, and unknown engine.

### M18 — P1: Rejected escaping symlink can still be sent live to the engine

**Evidence:** `stage_inventory` flags/skips an escaping symlink (`src/rush/engines/staging.py:276–300`), but argument substitution returns the original argument when it resolves outside root (`201–213`). Tools discover arguments from the live tree. Probe reported `staging.symlink_escapes_root` while the outgoing engine argument still resolved outside root and had no digest. Plan line 336 explicitly forbids following it.

**Fix / acceptance — concrete implementation:**

1. **Track rejection:** Extend the existing staging context to retain rejected project paths and their structured failure reasons. Classify lexical project inputs before resolving symlinks so an escaping project symlink is distinguishable from an explicitly allowed external configuration/dependency.
2. **Fail before spawn:** Add proposed `StagingInputError` in `engines/staging.py`; it is not an existing exception. `substitute_arg` classifies lexical project membership before resolution, rejects paths recorded as broken/escaping, and never returns their live value. `_staged_invocation` converts this to structured candidate failure before `engine.run` or subprocess spawn. External configuration is allowed only through a separately declared adapter input.
3. **Containment:** Copy permitted internal symlink targets under the staged tree and record their evidence. Preserve separately declared support/configuration exceptions without allowing them to become arbitrary source-read escape routes.
4. **Regression:** Invoke a real tool adapter with an escaping symlink; assert no outgoing engine argument reaches external source and no result depends on those bytes. Also test an internal symlink and an explicitly supported external configuration to avoid overblocking legitimate inputs.

### M19 — P1: DiffCover drops coverage identity, leaks staging, and can reuse an old report

**Evidence:** `src/rush/engines/diff_cover.py:80–89` creates a `mkdtemp` directory without cleanup; `104–111` reads a live fixed `diff-cover.json` that may predate the invocation. Provenance includes `coverage_digest`, but `_run_candidates` folds only top-level `digest` (`src/rush/workflows/project_run.py:917–927`). Probe confirmed the coverage digest existed, the folded identity was diff-only, and the temp directory survived return.

**Fix / acceptance — concrete implementation:**

1. **Scoped temporary directory:** Replace `mkdtemp` in `DiffCoverEngine` with `TemporaryDirectory` around copy, execution, report parsing, and provenance capture. Ensure timeout, subprocess error, malformed output, and cancellation leave no temporary directory.
2. **Fresh, non-overridable report:** Before constructing argv, reject caller args that add another coverage positional input or override `--compare-branch`/`--json-report`, including equivalent `--option=value` spellings. Pass exactly the staged coverage input, pinned comparison SHA, and invocation-unique contained absolute report path. Require that invocation to produce a valid report; never consume a live fixed `diff-cover.json`.
3. **Complete identity:** Combine diff bytes and coverage input bytes using a tagged canonical evidence object. Fold both into the candidate's repository-state evidence/source identity using M13's separate evidence channel, not `git_link.path_digests`.
4. **Regression:** Seed a stale live report and make the executable omit fresh output: fail honestly. Reject conflicting positional/options and prove the binary is not launched. Verify valid fresh output, cleanup on success/error/timeout/cancellation, and changed provenance when only coverage bytes change.

### M20 — P2: Decoded raw results retain temporary staged paths

**Evidence:** `_PATH_KEYS`, `src/rush/engines/staging.py:91–104`, omits Stylelint `source` and Trivy `Target`. Canonical finding paths remap after normalization, but decoded `ToolResult.raw` retains temp paths (`src/rush/engines/stylelint.py:41–48,61–91`; `trivy.py:39–48,69–95`). A helper probe confirmed mapped canonical paths alongside unmapped decoded raw fields.

**Fix / acceptance — concrete implementation:**

1. **Schema-aware remap:** Extend decoded-result remapping for Stylelint's top-level file `source` fields and Trivy's `Results[].Target` paths before normalization/serialization. Prefer adapter-specific structural handling; globally treating every key named source/Target as a path can corrupt unrelated data.
2. **Preserve text:** Keep generic path-key remapping for its existing fields, but do not replace staged-path substrings in messages, snippets, fixes, or replacement content. Map only fields whose engine schema says they are paths.
3. **Regression:** Feed each real decoder JSON containing staged path fields plus identical-looking literal text in a message/fix. Canonical findings and decoded raw path fields must use logical project paths; literal content must remain byte-for-byte unchanged.

### M21 — P2: Staging input/configuration failures are silently skipped

**Evidence:** `src/rush/engines/staging.py:279–282,303–307,325–329` silently continues after broken-symlink resolution, copy/hash errors, and dependency/config symlink creation errors. The attempt can continue without explicit incomplete provenance. Plan lines 289,313 require honest partial/failure publication.

**Fix / acceptance — concrete implementation:**

1. **Structured failures:** Replace silent skips in `stage_inventory` with records naming logical path, operation, error code, and sanitized message. Include broken/escaping symlink resolution, a captured inventory path disappearing or becoming non-file, copy, hash, and required support/configuration staging.
2. **Execution policy:** A required source that cannot be staged prevents the affected candidate from executing. If a support failure's affected consumers cannot be identified safely, fail the attempt conservatively. Never read the live source as a fallback or publish a clean complete result.
3. **Persist failed staging:** Pass failures into `_finalize_attempt`; fatal staging failure forces incomplete/failed state before its current empty-schedule-completed branch. Add a structured staging child result and retain failure details in the terminal manifest so hydration/restart cannot present a clean result. Temporary resources remain scoped and cleaned on every exit.
4. **Regression:** Inject each failure separately, including a disappeared inventory file with zero scheduled candidates. Assert the exact failure, no affected engine execution, non-clean terminal state/provenance, no live fallback, and complete cleanup.

## 5. Browser and terminal findings

### U01 — P1: Required key, pane, hierarchy, and input-decoding behavior is missing

**Evidence:** Tab and F2 both switch projects (`src/rush/dashboard/keymaps.py:33,44`); required Shift+Tab/pane cycling and hierarchical expand/collapse are absent. POSIX input remains bytewise, arrows-only, and uses `select.select` (`src/rush/dashboard/terminal_input.py:107,124,132`, verified-by: `ctx_execute_file` read of the current file this session — the two `select.select(...)` calls are at lines 124 and 132; corrected 2026-09-18 from the originally cited line 120, which is not a `select.select` call site); Windows handles arrows only (`155`). Plan lines 461–465 require function keys, UTF-8, selectors/SIGWINCH, and the specified Windows keys. Board deviations admit omissions at `docs/goals/phase-69-dashboard-tui-contract-remediation/state.yaml:1320–1325`.

**Fix / acceptance — concrete implementation:**

1. **Real bindings and state:** Update `DEFAULT_KEYBINDINGS` and `_dispatch_key`: F2 project selection, F3 section switching, Tab/Shift+Tab pane cycling, and +/- Map hierarchy. Generate `?` help from `_KEYMAP`. Inspect existing bindings before resolving the current `h` collision, as the plan requires. Add the minimum selected-parent/expanded-node state; do not claim helper functions already exist.
2. **POSIX decoder:** Implement incremental UTF-8 plus CSI/SS3 parsing in `terminal_input.py` with selectors and SIGWINCH wakeup/cleanup. Handle fragmented escape sequences without treating their first byte as standalone Escape; restore prior signal handler and close wakeup descriptors on shutdown.
3. **Windows input:** Extend native extended-key decoding for F2/F3/Shift+Tab after confirming actual emitted sequences in the target Windows console. Preserve identical logical actions across platforms; guessed scan codes or POSIX-only mocks are insufficient acceptance.
4. **Regression:** Test fragmented UTF-8/escapes, real PTY project/section/pane/hierarchy navigation, reverse wrapping, resize/state preservation, and help matching actual keys. Run the native Windows input cases; leave that acceptance explicitly open if the required environment is unavailable.

### U02 — P1: Dashboard-owned work can be marked complete before completion

**Evidence:** `_start_dashboard_owned`, `src/rush/tui.py:684–728`, saves only `response.run_id` and sets `status="complete"` immediately when `plan_total <= 0`. CHECK_SUITE has no plan total. The returned operation ID is neither retained nor polled, contrary to plan lines 471,482,522.

**Fix / acceptance — concrete implementation:**

1. **Acceptance and polling state:** In `_start_dashboard_owned`, retain returned logical `operation_id`, executor run/attempt, owner, and pending state. Remove completion inference from `plan_total`. Add `DashboardOwner.operation_status(operation_id)` and a dashboard-owned branch in `_poll_running_scans` that uses durable operation status, retaining last state during transient errors.
2. **Reuse authenticated client session:** `DashboardOwner` is frozen; give it a private mutable cached client-session field excluded from repr/comparison. Factor/reuse existing `_control_session` control→bootstrap→cookie/CSRF exchange from `dispatch_dashboard_action`. Cache credentials in memory only and use Cookie for existing operation-status GET. On 401 clear credentials, re-exchange, and retry GET once; repeated failure is visible disconnection. Reuse this session for actions; any authentication retry preserves the mutation request ID. Never bootstrap on every poll, persist credentials, or add an unauthenticated/control-bypassing status endpoint.
3. **Cancellation and detach:** After S10, Cancel submits the retained logical operation ID, including an attached caller's ID. Server resolves it to the executor, commits durable cancellation intent, then delivers normal scan cancellation or CHECK_SUITE's local event. CHECK_SUITE also polls durable intent, so cancellation works through another server and survives requester restart. Run ID is display/legacy input, not authoritative selection. Dashboard-owned Detach stops observation only.
4. **Regression:** Use a real slow dashboard control-channel CHECK_SUITE: show pending/running before true terminal state, cancel its actual event, retain completed-tool partial result, and observe durable status. Separately test full scan and attached operation cancellation. Assert multiple polls reuse one session, one expiry renewal works, repeated 401 surfaces failure, and action retry does not duplicate effects.

### U03 — P1: Detach can kill another project's subprocesses

**Evidence:** Process records carry `run_id`, but `reap_owner_processes` filters only by process-wide owner (`src/rush/runtime/subprocesses.py:352–386`). Detach passes only that owner (`src/rush/tui.py:1487–1528`). One TUI process can own multiple project runs; plan line 502 requires cleanup of this run's records.

**Fix / acceptance — concrete implementation:**

1. **Filter at the shared helper:** Add an optional exact `run_id` filter to `reap_owner_processes`; keep owner-only cleanup for confirmed dead-owner recovery. Filter before sending signals, not only when deleting process records.
2. **Detach call site:** Pass the selected local run from TUI's Detach flow. Never use process-wide ownership alone when the same coordinator can own more than one project. Dashboard-owned Detach follows U02 and must not reap the dashboard's children.
3. **Record lifecycle:** Remove only confirmed-dead records matching the chosen owner/run. Preserve failed-termination records and all sibling-run records so later recovery remains possible.
4. **Regression:** Launch two real process trees A and B under one TUI owner. Force A's timed-out Detach; assert A's descendants terminate and records clear while B receives no signal, keeps writing, and retains its records. Separately verify dead-owner recovery still reaps both.

### U04 — P2: TUI theme, motion, and narrow layouts are incomplete

**Evidence:** Hard-coded Rich styles remain without THEME/MOTION integration (`src/rush/tui.py:1896` and nearby renderers); layout only distinguishes `>=100` (`1946–1954`). Required 80–99 and below-80 behavior and motion contracts are missing (plan lines 467,515); board `state.yaml:1320–1325` records these omissions.

**Fix / acceptance — concrete implementation:**

1. **Local token mapping:** Build the smallest Rich style mapping from existing THEME tokens and use MOTION values for required selection/reveal behavior. Do not introduce another theme/animation system.
2. **Width contract:** In `render_app`, implement wide >=100, compact 80–99, and narrow <80 branches with specified pane visibility/order and two-row footer. Preserve project, section, pane, selection, and expanded hierarchy across resize.
3. **Existing color constructor:** Retain production `Console(no_color=bool(os.environ.get("NO_COLOR")))` semantics; there is no separate shared console adapter to call. Reduced motion renders final state without animated refresh.
4. **Regression:** Check 79/80/99/100 columns and live PTY transitions across boundaries, including footer/state/selection preservation. Verify reduced-motion final state and colored/NO_COLOR bytes through production construction.

### U05 — P1: Artifact browser control never performs paged content download

**Evidence:** The visible form invokes only `artifact_export` (`src/rush/dashboard/application.js:565–570`), whose server handler returns `expand_artifact_reference` metadata (`src/rush/dashboard/server.py:2070–2085`). Browser code has no paged artifact GET/`next_offset` loop. Backend page tests (`tests/test_dashboard_git_artifacts.py:725–768`) do not satisfy the visible-control requirement at plan line 602.

**Fix / acceptance — concrete implementation:**

1. **Existing endpoint and dependency:** Reuse authenticated `GET /api/projects/{project_id}/artifacts/{artifact_ref}?path=...&offset=...&limit=...`; do not add a duplicate endpoint. `artifact_export` returns metadata only. M12 must first implement immutable attempt selection and its explicit `data.content.content_base64` byte-page contract.
2. **Visible download loop:** After grant-gated export returns the chosen entry, retain exact reference and allowed logical path. Fetch existing content GET, URL-encoding reference/path, and follow `data.content.next_offset` until null. Verify unchanged reference, total size, and whole-artifact digest across pages; decode M12's base64 into byte arrays.
3. **Download lifecycle:** Concatenate bytes into a Blob with declared media type/filename. Show progress and actionable errors; use AbortController for cancellation and revoke object URLs. Reject inconsistent/truncated/failed pages rather than download a partial artifact as complete.
4. **Browser regression:** Export two same-name attempts through visible controls, each longer than two pages and containing split UTF-8/NUL/binary bytes. Compare full size/hash, cover failed middle page and cancellation, and prove A's reference/offset never returns B's bytes.

### U06 — P1: Visible handoff success is not proven and action identity can be stale

**Evidence:** Form dispatch uses `state.sourceIdentity` (`src/rush/dashboard/application.js:679`), refreshed in Overview (`923`). Board `state.yaml:1177` admits handoff success was demonstrated with a direct probe instead of the visible form because expected identity kept drifting. Plan line 439 expressly requires visible preview/send.

**Fix / acceptance — concrete implementation:**

1. **One preview-bound flow:** Replace independent Preview/Send forms with a reviewed preview plus Send control. After S06's server contract repair, both requests require run_id and attempt_id. Before preview refresh identity through the existing project snapshot flow. Store exact submitted run/attempt, agent_id, finding_ids, budgets, scope/grants/acceptance fields allowed by the corrected contract, returned packet/envelope, and hash-as-handoff_id.
2. **Exact send inputs:** Send those stored inputs and handoff_id, plus the preview's captured expected identity. Server rebuilds the canonical packet from that exact attempt; do not submit an arbitrary client-built envelope, silently substitute latest attempt, or add a separate source-identity endpoint. S05–S07/S16 own server persistence, hashing, execution validation, and identity.
3. **Conflict recovery:** A 409 marks the preserved preview stale and disables Send until explicit Preview. Bypass generic automatic reload if it discards reviewed state. Preserve form input and never auto-refresh expected identity merely to retry delivery.
4. **Browser regression:** Complete visible Preview → inspect → Send on a stable registered fixture and confirm stored/delivered content. Change source or attempt/evidence between preview/send: require 409 and zero artifact/session/delivery effects. Verify the stale preview remains visible and a deliberate fresh preview is required.

### U07 — P2: Shell readiness passes live testing but lacks durable regression coverage

**Evidence:** Plan line 619 requires an independent shell-interactive milestone, measured from navigation, plus a deliberately delayed-map negative check. The named `test_shell_interactive_signal_independent_of_map_fetch_completion` is absent and no equivalent repository regression was found. `scripts/benchmarks/run.py:724–739` measures `/api/session` round-trip, not enabled application controls. A native-browser negative check during this review delayed map fetch by approximately two seconds: controls enabled at 299 ms and selection worked at 318 ms, before the response at 2,015 ms and rendered nodes at 2,524 ms. Current behavior passed; the remaining issue is repeatable acceptance coverage and its documented metric.

**Fix / acceptance — concrete implementation:**

1. **No speculative product rewrite:** Native browser testing during this review already demonstrated shell readiness while map loading was delayed: navigation enabled at 299 ms, selection completed at 318 ms, delayed response arrived at 2,015 ms, and nodes appeared at 2,524 ms. The remaining repair is durable regression/evidence coverage, not a proven interactivity defect.
2. **Named regression:** Add `test_shell_interactive_signal_independent_of_map_fetch_completion` to the existing browser acceptance path. Use navigation's performance time origin and the actual enabled/selectable controls as the milestone; delay the map response for approximately two seconds.
3. **Assertions and receipt:** Assert shell interaction within the required one-second warm-local bound while map data is still pending, then verify eventual map completion separately. Preserve browser/version, fixture, navigation/control/map timestamps, and the exact runnable test command in the acceptance evidence.
4. **Metric separation:** Leave the existing `/api/session` round-trip measurement labeled as bootstrap latency. Do not relabel it as shell readiness or merge fetch duration with graph transition duration.

### U08 — P2: Terminal-event pulse and complete acceptance evidence remain unverified

**Evidence:** `tests/test_dashboard_motion_contract.py:5` declares structural/token scope. Board `state.yaml:1226` records earlier runtime omissions, but current native-browser execution now verifies project entry, relationships, inspector/detail animation, abort/retry, and accessibility/input behaviors listed in section 2. The specific 480 ms terminal-event pulse was not observed: memory mutation advances sequence without satisfying `event.status === 'terminal'` (`src/rush/dashboard/application.js:230–259`), and the real scan fixture was still pending at cleanup after 6.2 seconds. This is an unverified acceptance case, not proof of a pulse or scan runtime failure. The prescribed reference comparison and historical before/after evidence also remain unestablished.

**Fix / acceptance — concrete implementation:**

1. **Remaining runtime case:** Use a controlled real scan fixture that reaches terminal status through the normal ledger polling route, then observe the actual 480 ms terminal-event pulse. A memory write alone does not reach the `event.status === 'terminal'` branch in `application.js:230–259`; directly calling the pulse helper would bypass the required trigger.
2. **Exact assertion:** Capture start/mid/end properties, duration, easing, and `iterations === 1` after that real event. Assert no idle repetition and no animation under reduced motion. If the assertion fails, repair the trigger/animation; no production animation change is justified merely because this case remains unobserved.
3. **Preserve completed proof:** Retain this review's native project-entry, relationship, inspector, detail-row, abort/retry, input, focus, and reduced-motion observations as current evidence. Add a repeatable browser command/fixture to the existing acceptance workflow instead of relying solely on source-token tests.
4. **Reference comparison and historical limits:** Use `research/dashboard-prototype/reference-verification.md:9–31` to locate the exact [Control AI reference shot](https://dribbble.com/shots/27388009-AI-Dashboard-Design-for-Control-AI-Policy-Platform) and its [21.066667-second clip](https://cdn.dribbble.com/userupload/47771395/file/2176ba1ef89e12c95fdfcf99e615f302.mp4). Compare root reveal (0–3 s), full network (4.896 s), camera/neighborhood motion (8–11 s), relationship exploration (11–17 s), and angled inspector (17–21 s) against the implemented Rush interaction beats. Those timestamps locate reference scenes; they do not replace Rush's ≤800 ms settling contract. Record observed differences and dated/hash-bound acceptance evidence. The reference ledger reports an earlier author's playback; this fix-design audit did not independently replay the clip or certify visual equivalence. Do not manufacture historical RED or claim a current passing run establishes an earlier before/after process.

### U09 — P2: New NO_COLOR acceptance test fails from its capture harness

**Evidence:** Coordinator full suite and Terra's focused suite both fail `tests/test_tui_terminal.py:318` because `colored_output == b''`. `_run_pty_harness` starts a capture thread (`185`), while `_collect` closes the PTY without joining/draining it (`215–227`). The colored control also does not explicitly clear inherited `NO_COLOR` (`312–320`). Independent PTY checks with `TERM=xterm-256color` confirm production color on/off behavior at `src/rush/tui.py:2006`.

**Fix / acceptance — concrete implementation:**

1. **Capture lifecycle:** In `_run_pty_harness` / `_collect`, give the reader an explicit completion/error signal. After process exit, drain readable bytes to EOF or a bounded deadline and join the reader before closing the PTY descriptor. Propagate reader errors instead of returning an unexplained empty byte string.
2. **Controlled environment:** Set `TERM=xterm-256color` explicitly. Remove inherited `NO_COLOR` for the colored control and set it only for the suppressed case. Exercise the same production console construction and content in both runs.
3. **Meaningful assertions:** Require the expected plain text in both captures, ANSI color sequences in the colored case, and their absence in the NO_COLOR case. Empty output must fail as a capture problem rather than count as successful suppression.
4. **Verification:** Run the focused terminal test/suite on corrected frozen bytes, then the required full suite once. Do not weaken the color assertion, add arbitrary sleeps, or infer full-suite success from the independently passing manual PTY probe.

### U10 — P1: Browser memory forms expose none of the required ownership choices

**Evidence:** All five mutation-form definitions at `src/rush/dashboard/application.js:501–560` omit `owner_scope`. Real visible Write/Edit/Archive succeeded by relying on server defaults, but user/session/agent ownership cannot be selected. Plan lines 563,600 require all four kinds across the visible flows. This is the client-side gap accompanying M08's missing server validation.

**Fix / acceptance — concrete implementation:**

1. **Shared control:** Add one owner-kind/ID control used by Write/Promote/Edit/Archive/Delete, sending exact `arguments.owner_scope={kind,id}` separately from memory subject/version scope. Project uses selected registered UUID; user/agent are required opaque nonblank labels, not authenticated accounts.
2. **Non-secret session contract:** Add `owner_scope_id` to successful authenticated POST/GET session responses, sourced from that exact `Session.owner_scope_id`. Store it in browser session state and use it for session-kind selection; never ask for a cookie/CSRF secret. M08 validates the supplied ID against the request's authenticated session before reservation. Renewal updates session state but never transfers an existing row's immutable owner automatically.
3. **Error behavior:** Preserve form content/owner selection on validation/CAS failure and display the server's actual error message. Browser validation improves input; exact owner/version enforcement remains in the server/store.
4. **Browser regression:** Exercise all five actions for all four owner kinds, checking exact stored owner/revision. Missing owner, foreign project, wrong session, and stored-owner mismatch leave storage unchanged. Verify session renewal supplies a non-secret new ID and cannot silently take ownership of old-session rows.

### U11 — P2: Memory content form requires undocumented API knowledge

**Evidence:** Form definitions/parser at `src/rush/dashboard/application.js:501–509,640–653` label a field merely `content` and send raw strings when JSON parsing fails. In the real registered-project browser fixture, natural text and a source value yielded `400 malformed_request`; valid input required JSON such as `{"text":"..."}` and a supported `source_kind` such as `local_tool`, without a sufficient visible contract.

**Fix / acceptance — concrete implementation:**

1. **Content JSON:** Write, Promote, and Edit content controls must explicitly require a non-array JSON object. Show `{"text":"..."}` as an illustrative example, not a universal subject schema. Parse locally, retain invalid text, and send no malformed content request. Remove raw-string fallback for declared JSON fields while preserving their individual expected types—other JSON fields such as artifact-ID arrays must remain arrays.
2. **Operation-specific source inputs:** Provide source-kind select with `local_tool`, `cross_tool_handoff`, and `human_derived` for Write/Propose and Promote. Edit accepts content but has no source-kind requirement. Keep source visibly required only where the server contract requires it.
3. **Errors:** Keep defensive server validation and render its existing message next to the submitting form. Do not assume a field-error response schema already exists.
4. **Browser regression:** Following visible labels/examples, perform Write → Edit → Archive and verify revisions. Include valid Promote input and normal promotion-screen refusal. Malformed/non-object content causes no POST; source choices are constrained; malformed direct requests remain server-rejected.

## 6. Documentation and evidence findings

### D01 — P2: User-facing documentation still describes obsolete interfaces

**Evidence:** `docs/USER_GUIDE.md:102,108` says UI synchronously prints once and browser findings are unreliable because client/server auth disagrees. `docs/CLI_COOKBOOK.md:220–226` repeats this; `docs/BUNDLE_DIAGRAMS.md:268–271` labels UI one-shot. Current-status notes in `docs/adr/0016-local-web-dashboard-and-rich-interactive-tui.md:1` and `docs/maintainers/adr/013-local-web-dashboard-and-tui.md:1` also describe obsolete current behavior. Additional affected current claims appear in `docs/reference/cli-reference.md:122–123`, `docs/user-guide/everyday-workflow.md:85`, `docs/SECURITY.md:23`, `docs/safety/security-model.md:36`, and the current-status paragraph at `docs/BUNDLE_DIAGRAMS.md:7`. `docs/README.md:105` and `docs/workflows/gain_tui_and_telemetry.md:4` describe stale gain behavior.

**Fix / acceptance — exact documentation edits:**

1. **Persistent UI documentation:** Correct `docs/USER_GUIDE.md:102`, `docs/CLI_COOKBOOK.md:218–223`, and `docs/reference/cli-reference.md:122–123`. A TTY starts persistent Rich UI and background checks; `--json` runs checks, emits JSON, and exits; redirected stdout without `--json` emits text summaries and exits. Both CLI references must say `ui [PATH ...]`. Describe real quit choices and ownership effects after U01–U04 repair; do not advertise unfinished bindings.
2. **Current browser/security claims:** Replace obsolete blanket browser/API mismatch claims in `docs/USER_GUIDE.md:108`, `docs/CLI_COOKBOOK.md:220`, `docs/reference/cli-reference.md:123`, `docs/user-guide/everyday-workflow.md:85`, `docs/SECURITY.md:23`, and `docs/safety/security-model.md:36`. Document the observed loopback server, per-server context, single-use bootstrap URL, session/CSRF boundary, reconnect, and explicit mutation grants. Link current S findings for unresolved defects; neither preserve the obsolete shared-class-state story nor declare all security work complete.
3. **Gain aliases:** Update `docs/README.md:105` and `docs/workflows/gain_tui_and_telemetry.md:4` to describe the shared continuously updating HUD and Ctrl+C exit. Both `rush gain` and `rush context gain` invoke `_run_gain_live_panel` (`src/rush/cli.py:4127–4166`); the latter is a live compatibility alias, not a one-shot command. Keep measured provider usage distinct from local token/cost estimates.
4. **Diagrams and historical ADRs:** Correct both the current-status paragraph at `docs/BUNDLE_DIAGRAMS.md:7` and UI node at line 271. In the two cited ADRs, edit only the leading `Current status:` paragraph; retain the rest byte-for-byte. `historical_body_digest` excludes precisely that leading paragraph, so never reset its stored immutable-body hash to bless a changed historical body.
5. **Acceptance:** Use an isolated project to verify TTY, redirected text, `--json`, gain aliases, browser navigation, quit, and reconnect against the final copy. Update only supported current claims; retain recorded historical claims as historical. Refresh every touched file's coverage entry via D02's exact helper procedure after behavior and text agree.

### D02 — P2: Public references omit Phase 69's new contracts

**Evidence:** `docs/CLI_REFERENCE.md:148` omits `ui --json`/non-TTY behavior and has no `rush gain` entry, although both help commands expose them. Memory examples at `258–273` and `docs/MCP_REFERENCE.md:23–27` omit owner scope and do not explain legacy defaults versus required dashboard/TUI ownership. `docs/ARCHITECTURE.md:61–64` describes Phase 66 but lacks Phase 69's durable admission/recovery, generation/provenance, and attempt-history architecture. Both `rush gain` and `rush context gain` dispatch to the same live `_run_gain_live_panel` (`src/rush/cli.py:4127–4166`); the proposed documentation fix must not relabel the compatibility alias as one-shot.

**Fix / acceptance — exact reference additions:**

1. **CLI routes:** Add `ui --json` and non-TTY behavior to both CLI references, including plural paths. Add top-level `rush gain` and identify `rush context gain` as its live alias; do not describe either as a one-shot summary. Check individual help plus shared live-loop dispatch. The review's isolated Click probe invoked both commands with only `_run_gain_live_panel` intercepted and confirmed one call from each.
2. **Ownership examples:** Add `owner_scope: {"kind":"project","id":"<registered-project-id>"}` to the existing edit/archive/delete request examples while preserving subject `scope` and revision CAS fields. Explain opaque nonempty user/agent labels, registered project UUIDs, non-secret session IDs and their lifetimes, immutable owner assignment, and exact mismatch/version behavior. Distinguish legacy direct-call defaults from mandatory dashboard/TUI ownership. Add maintenance flags only with M09, showing both registered and unregistered roots.
3. **Architecture/API truth:** Extend `docs/ARCHITECTURE.md:61–64` with shared dispatch, durable reservation/effect receipts, owner fencing before admission release, and immutable source/artifact provenance. Distinguish operation/run/attempt and handoff source identity from provisioning job identity. Document the revised artifact byte-page fields/offset semantics near the technical artifact flow and link M12/U05; never describe base64 pages as current until the route and callers implement them.
4. **Exact coverage procedure:** `scripts/sync_docs.py` has only a read-only `--check` CLI. Import its `read_coverage_receipt`, `build_document_inventory`, and `collect_runtime_contracts` helpers to compute current values. Update only touched `documents[]` entries and changed registered-command contracts inside the existing `rush-doc-coverage-v1` JSON block in `docs/reports/phase-64-66-documentation-coverage.md`; supply truthful audience/authority/evidence fields, preserve unrelated entries, and preserve historical immutable-body hashes. Do not invent a regenerate/write flag or run the broad `update_phase_docs.py` appender.
5. **Verification:** Execute the examples, including wrong owner, stale CAS, denied grant, async polling, and two-attempt download. Run `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python scripts/sync_docs.py --check`. Compare output with P69-08.3's explicit allowed baseline; no new changed-file, contract, link, or historical-body failure is acceptable. A nonzero exit containing only allowed historical exceptions is not a prose-correctness pass or an unqualified clean-docs result.

### D03 — P2: Completion documents contradict one another and overstate evidence

**Evidence:** Phase 69 plan line 3 still says “planned, not implemented”; phase index line 49 says implemented with final audit pending; board T038 (`state.yaml:1903–1913`) says fully complete. `docs/phase-plans/phase-66-implementation-evidence.md:242,249` still says NO_COLOR has no test, while index lines 46/49 say T036 closed it. T002/T008/T009/T015 still literally show blocked, with later receipts claiming resolution; T999 remains not_complete while T038 claims complete. The board's browser deviations at 1177/1226 and the defects in this report are incompatible with blanket closure. Fourteen referenced `tNNN*.txt` receipt log basenames had no repository-local artifact; summaries do not supply independently replayable RED evidence.

**Fix / acceptance — reconciliation sequence:**

1. **Consistent current status:** Update Phase 69 plan's opening status, `docs/phase-plans/README.md` Phase 66/69 rows, and current-status paragraphs in `docs/phase-plans/phase-66-implementation-evidence.md` to implemented with unresolved acceptance findings, linking this review and frozen hash. Replace the inaccurate 'no NO_COLOR test' claim with the recorded failing capture test and independently passing production PTY behavior. Preserve Phase 66 sections 1–5 byte-for-byte; update only its allowed §0 reconciliation if required.
2. **Historical task evidence:** Preserve T999/T038 and earlier task receipts as dated historical claims. Add a superseding current-review statement using the existing evidence format, mapping reopened findings. For T002/T008/T009/T015, explicitly link any historical resolving task and retain current unresolved related findings. Do not edit old failure receipts into successes or invoke the former orchestration system.
3. **Acceptance evidence and decisions:** Record exact commands, environment, source hash, exit/results, and durable logs for corrective verification. Browser records identify real visible actions, timing origin, properties, and limits. Missing historical RED remains missing; create new genuine failing regressions instead. For row 18's threshold decision, locate an attributable product-owner approval receipt or obtain that decision before ratification; do not infer it from the plan author's own 'sign-off' label.
4. **Final reconciliation:** Freeze corrected code, run the required packet/full gates, update only genuinely passing acceptance rows, and apply D02's helper-based coverage updates last. Run the actual global `--check` command and assess its named allowed exceptions; there is no scoped checker flag. Preserve the Windows-console exception separately from mandatory Windows ownership implementation. New review reports need their own truthful coverage entry when integrated; they are post-baseline artifacts, not retroactive code defects.

## 7. Packet and task reconciliation

### Packet coverage

| Packet | Audited requirement lanes | Current result / findings |
| --- | --- | --- |
| P69-01 | HTTP/security; auth; reservation/receipts; locks/gates; ownership propagation; retention; previews; exception validation; generations; CLI reconnect | **Incomplete:** S01–S05, S11–S13,S15. Durable ledger/locks/admission code exists, but end-to-end ownership and recovery are broken. |
| P69-02 | Schema; synchronous/async expected; operation/run/attempt identity; attachment/status/cancel; admission/release; generation/locks; handoff; routes; refresh | **Incomplete:** S04–S10,S14/S16; U06. Implemented routes and tests do not establish the missing CAS, recovery, or attachment contracts. |
| P69-03 | All GREEN a–v; four producers; inventory/staging/identity; atomic publication; generation/rehydration; real events; grouping; historical cursors; full adapter inventory | **Incomplete:** M01–M06,M13,M15–M21. Central staging exists, but real tool inputs, reachable producers, immutable publication, event provenance, and historical expansion fail. |
| P69-04 | Structural RED; shell/forms/navigation; shared dispatch/error handling; restore; real visible action journey | **Incomplete:** U05–U07,U11. Visible handoff/download remain incomplete; shell readiness now passes live but lacks durable regression coverage. |
| P69-05 | Structural and runtime RED; motion/fit/filter/input; preferences; polling/retry; responsive/accessibility; complete browser VERIFY | **Incomplete acceptance:** U08. Four animation families and network recovery pass current native checks; terminal-event pulse/reference/historical evidence remain unclosed. |
| P69-06 | GREEN a–i; startup; gain; keys/input; ownership/control; cancel/checkpoint; quit; cleanup/recovery; theme/layout | **Incomplete:** U01–U04,U09; S01–S03. Background startup, gain, quit menu and some checkpoint paths exist, but required user flows still fail. |
| P69-07 | Ownership a–i; GREEN a–g; all transport adapters; memory mutation/maintenance; telemetry attribution/filtering; Git; artifact/browse paging | **Incomplete:** M07–M14,U05/U10. Store CAS/owner primitives exist; public boundaries and current/history data disagree. |
| P69-08 | F38/F41 mapping; NO_COLOR/browser/shell proof; timing decision; full suite; docs/index/coverage reconciliation | **Incomplete:** U07–U09,D01–D03 and approval evidence below. Full suite fails; protected Phase 66 bytes and the narrow historical hash gate pass. |

P69-01 lettered coverage: a fail, b admission bound present, c fail, d durable project/request uniqueness present, e fail, f partial memory receipts, g atomic write present, h/i partial POSIX implementation, j fail, k terminal-only retention present, l preview classification present, m structured boundary/allowlists present, n primitives present but publication invariant fails M01, o strict grant booleans present, p operation-aware admission present. CONNECT fails at auth atomicity/Windows; VERIFY's passing subset does not close those defects.

P69-02 lettered coverage: a/b fail, c partial scan-only revalidation, d fail, e partial status but no attached cancellation, f durable admission transaction present, g partial terminal handling, h recovery sweep present but unsafe/incomplete, i transactional attachment/retry present, j operation-prefixed keys present, k persisted generation/selector present, l locked resume present, m pinned rescan comparison present, n partial routes/handoff, o memory-refresh calls present for that packet's specified actions, p shared payload/benchmark migration present. Genuine read-only preview split exists. Complete preview hash and handoff recovery do not.

P69-03 lettered coverage after the complete adapter pass: a partial, b fail, c partial, d fail, e fail, f partial/fail, g partial, h/i fail, j partial, k partial/fail, l fail, m partial, n fail, o partial, p/q/r fail, s partial, t present for cursor binding, u present, v partial. Inventory checked all 121 registered adapters and sole direct `engine.run` call at `src/rush/runtime/subprocesses.py:790`: generic remapping applies to engines reaching that path; defects lie in upstream routing/read paths, central scope/remap/failure behavior, and bespoke repository-state handling.

P69-07 ownership a–g/i primitives are present at the examined store/tool layer; h maintenance fails. Its GREEN a fails at boundary/refresh, b partial, c fails content identity, d/e partial attribution, f correctly reports provider usage unavailable, g partial browse. “Present” means no independent defect found in that bounded lane, not whole-packet acceptance.

### Every board task

`docs/goals/phase-69-dashboard-tui-contract-remediation/state.yaml` contains 39 tasks. Historical checkpoint decisions cannot certify this final hash by themselves.

| Task | Board status | Current reconciliation |
| --- | --- | --- |
| T001 | done | Historical prerequisite review; later complete claim invalidated by S01–S14. |
| T002 | blocked | Later T006 claims resolution; HTTP/header/redaction gaps remain S12/S13. |
| T003 | done | Durable storage implemented; reservation/recovery inputs incomplete S04/S05. |
| T004 | done | POSIX liveness exists; Windows/recovery/TUI acquisition gaps S02/S03/S15. |
| T005 | done | Gate/adapters implemented, but real propagation/recovery incomplete S01/S02/S03. |
| T006 | done | Partial retention/validation/auth primitives; S11/S12 and M01 prevent closure. |
| T007 | done | Historical checkpoint did not establish final P69-01 contract. |
| T008 | blocked | Later T012 claims resolution; S07/S08/S14 still open. |
| T009 | blocked | Later T011 claims resolution; S09/S10/S16 still open. |
| T010 | done | Durable admission exists; safe dead-owner release incomplete S02. |
| T011 | done | Generation/lock work exists; exact attachment attempt and ownership gaps S01/S09. |
| T012 | done | Routes exist; handoff/recovery/refresh incomplete S05/S06/M07. |
| T013 | done | Historical checkpoint; P69-02 remains incomplete. |
| T014 | done | Adapter/publication exists; inventory/identity/immutability gaps M01–M03. |
| T015 | blocked | Follow-ups supplied staging work; real input/staging/provenance failures remain M02/M03/M15–M21. |
| T031 | done | Repo-state helpers exist; reachability/coverage identity/Git-link defects M13/M17/M19. |
| T016 | done | Publication/generation additions do not fix M01/M02/M07. |
| T032 | done | Durable counter exists; hydration lacks frozen manifest inputs M02/M03. |
| T033 | done | Complexity cleanup present; current ruff check passes. No separate defect found. |
| T017 | done | Event volume/group completeness contract fails M04/M05. |
| T018 | done | Historical base exists; identity/expansion and immutable content fail M06/M12. |
| T019 | done | Browser availability confirmed; availability is not full browser acceptance. |
| T020 | done | Real shell/forms exist; U05/U06/U07/U11 remain open. |
| T021 | done | Current native checks close several earlier omissions; pulse/reference/historical acceptance remains unverified U08. |
| T022 | done | Historical checkpoint accepted named browser omissions outside full completion contract. |
| T023 | done | Startup/gain exist; keys/layout/theme omitted U01/U04. |
| T024 | done | Control/checkpoint code exists; dashboard-owned TUI observation fails U02. |
| T034 | done | Gain governance entry repaired; no current independent defect found. |
| T025 | done | Quit/recovery paths exist; sibling cleanup and test gate fail U03/U09. |
| T026 | done | Store ownership work present; public ownership/maintenance incomplete M08/M09/U10. |
| T027 | done | Attempt labels exist; immutable download/Git provenance fail M12/M13. |
| T028 | done | Schema additions exist; real attribution/filtering/browse gaps M10/M11/M14. |
| T029 | done | Historical checkpoint did not establish final transport/telemetry acceptance. |
| T035 | done | Backend paging/Git predicate exists; historical bytes and visible download fail M12/M13/U05. |
| T030 | done | Shell behavior now passes; visible handoff, durable regression, pulse/reference evidence, and docs gaps remain U06–U08,D01–D03. |
| T036 | done | NO_COLOR test and timing clause added; new test currently fails U09. |
| T037 | done | Three named hash entries are currently clean; prose accuracy unaffected D01–D03. |
| T038 | done/complete | **Completion verdict rejected** by current tests and findings. |
| T999 | done/not_complete | Superseded by T038 historically; current review independently remains not complete. |

### Phase 66 reconciliation rows

Rows 1/11/12 remain affected by S01–S03,S11–S13; rows 2/3/6/14 by S04–S10,S14; row 4 by U05–U07; rows 5/9/10 by M01–M06; rows 7/8 by U01–U04; row 13 by U06–U09; row 15/24 by U08; rows 16/17/23 by M07–M14,U05; row 20's ownership mapping exists but its claimed closure is not supported. Row 19 remains historically pre-closed. Rows 21/22 are contract clarifications rather than proof that every security implementation is correct.

Row 18 now has a 1.0-second superseding clause (Phase 69 plan line 31), preserving the original Phase 66 text. However plan line 621 explicitly requires product sign-off. The stored text documents local measurements and a decision but does not identify an attributable user/product-owner approval receipt. **Approval provenance is unverified, not proven absent.** Fix: attach the actual approval reference, or obtain it before treating the relaxed threshold as ratified; do not invent approval from passing local timings.

## 8. Required documentation work

| Surface | Current state | Required repair |
| --- | --- | --- |
| Phase 69 plan; `docs/phase-plans/README.md`; Phase 66 evidence; Phase 69 task state | Mutually inconsistent current status and overly broad closure | Reconcile corrected behavior and unresolved acceptance, preserve historical receipts and protected Phase 66 sections, link final immutable evidence. |
| `docs/USER_GUIDE.md`, `docs/CLI_COOKBOOK.md`, `docs/reference/cli-reference.md`, `docs/user-guide/everyday-workflow.md`, `docs/BUNDLE_DIAGRAMS.md` | Obsolete one-shot/broken-dashboard descriptions | Correct persistent TUI, redirected text, JSON exit, browser routes, current-status paragraph, and diagram label after matching executable behavior. |
| `docs/README.md`, `docs/workflows/gain_tui_and_telemetry.md`; `docs/SECURITY.md`, `docs/safety/security-model.md`; both UI ADR status prefaces | Stale gain and browser/auth facts | Describe both live gain aliases and actual per-server/session boundary; preserve ADR bodies and retain unresolved security findings explicitly. |
| `docs/CLI_REFERENCE.md`, `docs/MCP_REFERENCE.md`, `docs/ARCHITECTURE.md` | CLI, ownership, recovery, and history additions incompletely documented | Add executable contracts after repair, including plural UI paths, owner/default distinctions, operation/run/attempt identity, and lossless artifact byte pages. |
| `docs/reports/phase-64-66-documentation-coverage.md` | Three targeted plan/index hashes pass; 20 allowed historical missing receipts remain | Use D02's actual read helpers to update touched receipt entries and changed contracts. The checker has no write/regenerate flag. Add this post-baseline review's truthful entry when integrating documentation. |

The initial coverage output contains five Phase 69 goal/board assets and `phase-69-plan-remediation-plan.md` among its 20 exceptions, alongside other goals, Phase 67/68 plans, CI plan, and retrospective. P69-08 explicitly grandfathered these categories. Thus the **narrow planned gate passes** while “every Phase 69 document has coverage” would be false. This newly requested review report is a post-freeze artifact, not evidence of a pre-existing implementation defect. This fix-design audit changes only this report; the table specifies future documentation work, not completed edits.

## 9. Coding-agent handoff and closure criteria

Treat each numbered finding as a repair ticket. Its **Evidence** identifies the existing implementation location; **Fix / acceptance** specifies the required change and observable closure test. This report is sufficient task context; the conversation is not an additional specification. Reopen the cited source at the implementation checkout before editing because line numbers refer to the frozen reviewed hash.

1. Reproduce the stated defect with the smallest regression in the relevant existing test module. For an evidence-only finding such as U07, preserve the already-passing product behavior and add the missing repeatable acceptance proof.
2. Implement the shared correction once and update every named caller. Proposed schema/API additions are explicit design instructions, not claims that those names already exist. Preserve legacy behavior only where the finding explicitly permits it.
3. Close the finding only after its exact acceptance assertions pass. Record changed files, command, exit/result, platform, and new source hash. A missing native-platform or visible-browser run remains an explicit acceptance gap.

Use these existing test modules as starting points; extend their real call-path coverage rather than introducing a second framework:

| Findings / repair boundary | Existing regression locations |
| --- | --- |
| S01–S03,S15; U03 — child ownership, admission, recovery, Detach | `tests/test_subprocess_contract.py`, `tests/test_dashboard_http_contract.py`, `tests/test_project_run_lifecycle.py`, `tests/test_tui.py` |
| S04–S10,S16; U02/U06 — ledger, handoff, expected state, operation/attempt identity | `tests/test_dashboard_scan_actions.py`, `tests/test_dashboard_missing_routes.py`, `tests/test_scan_handoff.py`, `tests/test_scan_rescan.py`, `tests/test_tui.py` |
| S11–S14 — authentication and HTTP boundary | `tests/test_dashboard_http_contract.py` |
| M01–M06,M13,M15–M21 — publication, events, staging, provenance/history | `tests/test_dashboard_map.py`, `tests/test_staged_scan_bytes.py`, `tests/test_project_run_lifecycle.py`, `tests/test_dashboard_missing_routes.py`, `tests/test_dashboard_git_artifacts.py` |
| M07–M11,M14; U10/U11 — ownership, memory, telemetry, forms | `tests/test_memory_versions.py`, `tests/test_memory_public_contract.py`, `tests/test_memory_retrieval.py`, `tests/test_dashboard_memory_tokens.py`, plus `tests/test_phase62_maintenance.py`, `tests/test_phase62_expiry.py`, and `tests/test_memory_core_regressions.py` for M09 caller/signature migration; real browser form acceptance remains required |
| M12; U05 — historical byte storage and visible download | `tests/test_dashboard_git_artifacts.py`; real visible browser download plus byte-hash comparison |
| U01/U04/U09 — terminal behavior | `tests/test_tui.py`, `tests/test_tui_terminal.py`; native Windows input acceptance where specified |
| U07/U08 and remaining visible journeys — browser acceptance | `tests/test_dashboard_projects.py`, `tests/test_dashboard_motion_contract.py`, `tests/test_dashboard_user_journey.py` for existing structural/backend coverage; retain a runnable native-browser acceptance procedure for properties those tests cannot exercise |
| D01–D03 — documentation truth | Exact documents listed in section 8; execute their examples and run `scripts/sync_docs.py --check` after updating affected receipts |

Run a targeted module with `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest <test-file> -q`. Existing source-string tests are not substitutes for the real-process/browser tests specified above.

**Dependencies:** S04 supplies persisted effect inputs for S05/S16. S02's dead-owner fencing is independently repairable; it does not require S09's later attempt-schema work. S03 supplies the native Windows owner primitive. S09 supplies exact scan attachment identity; S10 supplies durable cancellation for U02, including CHECK_SUITE and cross-server delivery. S08/M01/M02 must agree on shared publication and never-scanned genesis identity without nesting project/run locks. M01 supports M07; M02/M03/M13/M15–M21 share one provenance contract. M12 precedes U05's lossless downloader. M08 supplies authenticated session-owner exposure for U10, while M09 extends maintenance callers. S04/S05/S06/S07/S16 precede complete U06 handoff: exact source attempt, stable envelope, effects, and async recovery must agree. Provisioning uses its own durable job identity; S07/S16 do not force it into scan-attachment admission. Shared corrections receive one implementation and every affected acceptance case.

### Repair sequence

1. Repair execution safety: S01–S05, S07–S10,S15/S16, U02/U03, then auth/redaction/header/schema gaps. Verify real child lifetime, effects, identities, crash seams, attachment, and supported-platform behavior.
2. Repair immutable provenance/history and ownership: M01–M09,M12/M13,M15–M21; include all four producers and all user transports. Then repair telemetry and paging M10/M11/M14.
3. Complete the user routes: U01/U04–U08,U10/U11, including browser content downloads, visible handoff, independent shell timing, and runtime motion/recovery/accessibility proof.
4. Repair U09's test harness; run required packet commands and one complete frozen-byte regression. Keep any target-OS or external acceptance limit explicit; do not convert missing evidence into a pass.
5. Update/reconcile the named documentation and coverage entries, establish the timing approval receipt, and perform a new independent read-only review of the corrective frozen hash. Only then reconsider completion.

Every finding above supplies a specific fix and regression/acceptance check. These are proposed repairs, not changes made by this review. Do not lower the contract, remove inconvenient assertions, or substitute API probes for specified visible-control journeys.

## 10. Independently reproducible security probes

Run these against the reviewed checkout with `rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH uv run --python 3.12 --extra dev python`. They touch temporary data and their own process only.

### Single-use bootstrap race

```python
import threading
from rush.dashboard.auth import DashboardAuth

auth = DashboardAuth()
token = auth.issue_bootstrap()
original = auth.verify_bootstrap
barrier = threading.Barrier(2)
results = []

def verify(value):
    valid = original(value)
    barrier.wait(timeout=5)
    return valid

auth.verify_bootstrap = verify
threads = [threading.Thread(target=lambda: results.append(
    auth.exchange_bootstrap(token))) for _ in range(2)]
for thread in threads:
    thread.start()
for thread in threads:
    thread.join(timeout=6)
print("sessions_returned", sum(x is not None for x in results),
      "stored_sessions", len(auth._sessions))
```

Observed: `sessions_returned 2 stored_sessions 2`. The correct fixed regression produces one session with a barrier placed before `exchange_bootstrap`, as S11 specifies. This vulnerable-method probe intentionally places its barrier inside verification; do not reuse that internal barrier after adding the method-wide lock.

### Admission released before owned child termination

```python
import os
import signal
import subprocess
import tempfile
from pathlib import Path
from rush.dashboard.state import MutationLedger, reconcile_admissions
from rush.runtime.subprocesses import _write_owned_process_records

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    ledger = MutationLedger(db_path=root / "ledger.db")
    reservation = ledger.reserve("p", "r", "h", operation_type="scan_start")
    ledger.admit("p", execution_identity="scan_start:plan",
                 slot_id=reservation.operation_id,
                 operation_id=reservation.operation_id,
                 run_id="run", plan_id="plan", owner_instance_id="dead-owner")
    child = subprocess.Popen(["/bin/sh", "-c", "sleep 60"],
                             start_new_session=True)
    try:
        _write_owned_process_records("dead-owner", [{
            "owner_instance_id": "dead-owner", "run_id": "run",
            "pgid": child.pid}], data_root=root)
        count = reconcile_admissions(ledger, data_root=root)
        alive = True
        try:
            os.killpg(child.pid, 0)
        except ProcessLookupError:
            alive = False
        print("reconciled", count, "admission",
              ledger.admission_for_project("p"), "child_alive", alive)
    finally:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait()
```

Observed: `reconciled 1 admission None child_alive True`. Correct behavior cannot release admission while this recorded child is alive.

## 11. Fix-design verification and handoff limits

All **51 proposed fixes** received a second, independent source/caller/contract review against implementation `ea88324eae379c96b4fb2553d7247ea340b3cc16`. Input review SHA-256 was `dc1efa87086bd8a237f9af3e80da98997a226d9b3629892abff90700b4e58202`. This pass corrected or strengthened **38 fix blocks** and retained **13** after checking their implementation boundaries and acceptance requirements. Finding count/severity remains 51 (35 P1, 16 P2); changes here repair the remediation instructions, not the product.

| Review lane | Reviewer | Fix instructions corrected or strengthened | Instructions retained after review |
| --- | --- | --- | --- |
| Security, execution, recovery | GPT-5.6 Sol | S01, S02, S03, S04, S05, S06, S07, S08, S09, S10, S11, S12, S13, S14, S15, S16 | None |
| Map, provenance, memory, artifacts | GPT-5.6 Sol | M01, M04, M08, M09, M12, M14, M15, M16, M17, M19, M21 | M02, M03, M05, M06, M07, M10, M11, M13, M18, M20 |
| Browser and TUI | GPT-5.6 Terra | U01, U02, U04, U05, U06, U08, U10, U11 | U03, U07, U09 |
| Documentation and integration | Coordinator | D01, D02, D03 | None |

The design checks traced existing helpers and caller signatures, lock/transaction boundaries, operation versus run/attempt identity, capture timing, authentication lifetimes, wire formats, test entry points, and document/receipt tooling. In particular, corrections remove redundant tool-signature fanout (S01), unsafe recovery release/automatic acknowledgement (S02/S05), nested project/run exclusion (S08), cancellation delivery inside a write transaction (S10), finalization-time artifact capture after overwrite (M12), repeated TUI session creation (U02), and an invented documentation regeneration command (D02).

1. **New behavioral evidence in this pass:** An isolated Click invocation intercepted only `_run_gain_live_panel`; both `gain` and `context gain` exited 0 and invoked that shared loop once. This validates alias dispatch, not terminal rendering. Remaining checks in this pass were read-only source/contract/API research.
2. **External API evidence:** S03 cites official Microsoft and Python documentation for mutex ownership, inheritance, job assignment, and subprocess handle lists. Those sources constrain the proposed Windows implementation. They do not establish native Windows acceptance; that work remains required.
3. **Preserved verification boundary:** Section 2's existing tests/probes and earlier native-browser observations remain evidence for the frozen implementation. The unchanged full suite was not rerun for a documentation-only pass. No corrected fix has runtime proof because no fix was implemented. Every numbered regression/acceptance instruction is work for the implementing agent.
4. **Artifact scope:** Only this review report was revised. Production code, tests, other documentation, coverage receipts, task state, source hash, and protected plan/evidence bytes were preserved. Sections 8–9 identify subsequent code/docs/acceptance work; none is implicitly completed by this review.

## 12. Named regression tests — implementation-readiness pass (2026-09-18)

Independent re-verification of this report against real current source at HEAD `ea88324eae379c96b4fb2553d7247ea340b3cc16` (unchanged since this report froze on it — verified-by: `git log -1` and `git status` run this session, showing that exact HEAD and a clean tree). 51 of 51 findings' own Evidence citations (S01-S16, M01-M21, U01-U11, D01-D03) were individually re-checked against live source this pass and matched, with exactly one correction (U01's `terminal_input.py` line numbers, corrected in section 5 above). Section 10's two runnable probes were executed directly this pass, not merely read: the S11 bootstrap-race probe returned `sessions_returned 2 stored_sessions 2`, and the S02 dead-owner-recovery probe returned `reconciled 1 admission None child_alive True` — both match this report's own claimed output exactly.

This section closes the one remaining implementation-readiness gap found in that pass: most findings' Regression/RED text names test *scenarios* in prose rather than literal test-function identifiers a coding agent can create directly. The names below are additive — they name the exact scenarios each finding's own Regression paragraph already specifies, in this repository's real `test_snake_case` naming convention, so a handoff coding agent has literal names to create rather than inventing its own. They do not change any finding's Evidence, Impact, or Fix content above; §1-11 remain the authoritative technical specification.

**S-series (extends P69-01/P69-02/P69-06 test files, primarily `tests/test_dashboard_http_contract.py`, `tests/test_subprocess_contract.py`, `tests/test_scan_handoff.py`, `tests/test_dashboard_scan_actions.py`, `tests/test_tui.py`):**

- **S01:** `test_typecheck_tool_run_engine_call_carries_owner_instance_id_and_run_id`, `test_security_tool_all_four_run_engine_sites_carry_owner_instance_id_and_run_id`, `test_format_tool_run_engine_call_carries_owner_instance_id_and_run_id`, `test_test_tool_run_engine_call_carries_owner_instance_id_and_run_id`, `test_coverage_tool_run_engine_call_carries_owner_instance_id_and_run_id`, `test_release_tool_run_engine_call_carries_owner_instance_id_and_run_id`, `test_resume_scan_run_forwards_owner_instance_id_and_run_id_into_execute_attempt_locked`, `test_rescan_project_run_forwards_owner_instance_id_and_run_id_into_execute_attempt_locked`, `test_resume_scan_run_call_path_reaches_owned_execution_scope_at_invocation_executor_boundary`.
- **S02:** `test_dead_owner_reap_terminates_recorded_children_before_release`, `test_live_owners_pending_outcome_retried_without_reaping_its_own_children`, `test_foreign_live_owner_admission_is_never_reaped`, `test_failed_reap_retains_admission_and_does_not_release`, `test_two_competing_recovery_processes_only_one_wins_the_claim`, `test_recovery_restart_after_confirmed_reap_but_before_finalization_consumes_receipts_without_repeating_effects`.
- **S03:** `test_windows_owner_lock_acquire_release_via_named_mutex`, `test_windows_owner_lock_abandoned_mutex_detected_as_dead_owner`, `test_windows_gate_wrapper_blocks_engine_launch_until_release`, `test_windows_gate_wrapper_never_launches_if_owner_dies_before_release`, `test_windows_job_object_kills_entire_process_tree_on_close`, `test_windows_job_object_survives_parent_job_nesting`, `test_windows_recovery_confirms_zero_active_processes_before_clearing_records`, `test_windows_pid_reuse_does_not_falsely_confirm_termination`, `test_windows_restart_after_crash_reopens_and_verifies_job_object` (all platform-gated; no Windows runner reachable in this environment to execute them — named for a future Windows session, per this finding's own stated limit).
- **S04:** `test_reservation_persists_validated_argument_payload`, `test_reservation_persists_preallocated_effect_ids_map`, `test_concurrent_server_startup_migration_against_same_old_database_is_race_free`, `test_recovery_uses_persisted_reservation_data_only_never_replays_body_hash`, `test_legacy_version_0_pending_rows_stay_recovery_required_not_silently_admitted`.
- **S05:** `test_scan_handoff_carries_operation_id_field`, `test_crash_after_artifact_receipt_before_session_receipt_is_recoverable`, `test_crash_after_session_receipt_before_prepared_descriptor_is_recoverable`, `test_crash_after_delivered_descriptor_before_acknowledgment_does_not_auto_acknowledge`, `test_session_capability_never_appears_in_persisted_descriptor_or_status_serialization`, `test_orphan_session_with_no_matching_prepared_descriptor_is_revoked_idempotently`.
- **S06:** `test_handoff_preview_hash_changes_when_packet_content_changes`, `test_handoff_preview_hash_changes_when_evidence_artifact_version_changes`, `test_handoff_preview_hash_changes_when_session_allowlist_changes`, `test_handoff_send_rejects_409_when_bound_input_mutated_after_preview`, `test_handoff_send_with_unchanged_input_produces_identical_packet_bytes`, `test_handoff_preview_requires_run_id_and_attempt_id`.
- **S07:** `test_provisioning_worker_revalidates_reviewed_plan_immediately_before_effects`, `test_provisioning_worker_returns_terminal_conflict_on_plan_mismatch_with_zero_effects`, `test_handoff_worker_revalidates_pinned_attempt_and_envelope_immediately_before_effects`, `test_handoff_worker_returns_terminal_conflict_on_envelope_mismatch_with_zero_effects`.
- **S08:** `test_two_requests_with_the_same_expected_revision_cannot_both_commit_against_an_invalidated_state`, `test_genesis_identity_is_shared_scalar_derived_from_project_id_before_first_publication`, `test_independent_artifacts_sharing_a_source_identity_may_both_commit`, `test_configure_compares_registry_revision_under_registry_lock_not_project_exclusion_alone`, `test_never_scanned_configure_and_memory_mutation_still_work_against_genesis`.
- **S09:** `test_admission_schema_carries_attempt_id_column`, `test_attach_before_header_publication_returns_the_exact_attempt_later_persisted`, `test_baseline_attempt_id_differs_from_executing_attempt_id_for_resume`, `test_fresh_execution_after_release_receives_a_new_attempt_id`, `test_concurrent_old_schema_startup_migration_is_race_free`.
- **S10:** `test_scan_cancel_accepts_operation_id_and_resolves_the_attached_executor`, `test_scan_cancel_retains_explicit_legacy_run_id_compatibility`, `test_scan_cancel_terminal_target_returns_stored_result_not_a_fresh_cancel`, `test_scan_cancel_unknown_or_cross_project_target_returns_uniform_404`, `test_cancel_from_a_second_server_process_still_resolves_the_same_durable_intent`, `test_old_cancellation_intent_cannot_cancel_a_later_resume_attempt`.
- **S11:** `test_concurrent_direct_method_calls_to_exchange_bootstrap_mint_exactly_one_session`, `test_http_concurrency_and_expired_token_tests_still_pass_after_the_lock_is_added`.
- **S12:** `test_bootstrap_token_value_is_redacted_from_finding_content_via_digest_match`, `test_session_cookie_value_is_redacted_from_finding_content_via_digest_match`, `test_csrf_value_redaction_still_works_after_digest_matching_is_added`, `test_active_session_churn_during_serialization_does_not_leak_or_crash`, `test_ordinary_text_resembling_a_token_format_is_not_falsely_redacted`.
- **S13:** `test_referrer_policy_header_present_on_js_response`, `test_referrer_policy_header_present_on_css_response`, `test_pre_thread_503_response_carries_the_same_security_headers_as_normal_responses`, `test_pre_thread_503_service_resumes_after_a_slot_is_released`.
- **S14:** `test_handle_action_rejects_missing_schema_version`, `test_handle_action_rejects_null_string_bool_schema_version`, `test_handle_action_accepts_explicit_integer_1_schema_version`, `test_handle_control_check_suite_rejects_missing_schema_version`, `test_handle_control_check_suite_accepts_explicit_integer_1_schema_version`.
- **S15:** `test_admit_local_run_refuses_to_reserve_work_when_owner_lock_acquisition_failed`, `test_admit_local_run_only_launches_a_worker_when_admission_result_started_is_true`, `test_admit_local_run_attaches_to_stored_executor_identity_when_admission_result_attached_is_true`, `test_admission_conflict_or_error_launches_nothing_and_displays_failure`, `test_a_finishing_project_does_not_release_an_owner_lock_needed_by_another_local_project`.
- **S16:** `test_handoff_202_response_includes_attempt_id_matching_preview_source_tuple`, `test_provisioning_202_response_includes_its_own_allocated_attempt_id`, `test_handoff_status_and_acceptance_match_previews_source_tuple`, `test_provisioning_status_acceptance_and_receipts_match_its_allocated_job_tuple`, `test_crash_immediately_after_202_recovers_without_reminting_or_substituting_an_attempt`.

**M-series (extends P69-03/P69-07 test files, primarily `tests/test_dashboard_map.py`, `tests/test_project_run_lifecycle.py`, `tests/test_dashboard_missing_routes.py`, `tests/test_staged_scan_bytes.py`, `tests/test_dashboard_git_artifacts.py`, `tests/test_dashboard_memory_tokens.py`, `tests/test_memory_public_contract.py`, `tests/test_memory_retrieval.py`, `tests/test_memory_versions.py`):**

- **M01:** `test_get_returns_a_detached_record_not_the_live_stored_object`, `test_paused_scan_publication_and_concurrent_memory_refresh_both_survive`.
- **M02:** `test_scan_bytes_a_changed_to_b_then_hydrate_still_reports_a`, `test_check_suite_manifest_carries_content_identity_inventory_generation_and_git_link`.
- **M03:** `test_persisted_inventory_survives_restart_and_file_changes`, `test_legacy_attempt_without_inventory_reports_missing_provenance_not_current_files`.
- **M04:** `test_events_route_serves_real_candidate_progress_events_not_synthetic_status_transitions`, `test_run_scoped_retention_prunes_independently_to_2000_rows_per_run`, `test_events_after_cursor_below_project_floor_returns_409`.
- **M05:** `test_101_file_101_finding_fixture_preserves_all_report_relationships_through_expansion`.
- **M06:** `test_historical_map_request_without_attempt_id_is_rejected`, `test_historical_expansion_uses_the_pinned_attempts_snapshot_not_live_record`, `test_cursor_reused_against_a_different_view_id_raises_cursor_rejected_409`.
- **M07:** `test_memory_edit_immediately_updates_map_content_and_generation`, `test_memory_archive_delete_promote_each_publish_a_new_generation`, `test_promotion_denial_after_candidate_write_still_refreshes_the_real_candidate_commit`, `test_preview_and_zero_write_failure_publish_no_fabricated_sequence_bump`.
- **M08:** `test_write_edit_promote_archive_delete_reject_omitted_or_incomplete_owner_before_any_row_change`, `test_foreign_project_uuid_owner_rejected_before_reservation`, `test_wrong_session_id_owner_rejected`, `test_arbitrary_nonempty_user_agent_labels_accepted_structurally_and_persist_unchanged`.
- **M09:** update the existing `tests/test_memory_versions.py:759-780` (currently codifies the wrong registered-path assumption) plus add `test_tui_and_cli_maintenance_reach_the_registered_projects_uuid_owned_row_not_path_owner`; migrate the existing direct-call/spy assertions in `tests/test_phase62_maintenance.py`, `tests/test_phase62_expiry.py`, `tests/test_memory_core_regressions.py` for the new required-owner signature.
- **M10:** `test_tokens_section_totals_respect_run_agent_session_filters_not_just_handoff_rows`.
- **M11:** `test_two_identical_distinct_calls_are_counted_twice_and_one_retry_is_counted_once`, `test_persisted_attribution_columns_match_the_public_invocation_id_on_every_success_and_fallback_branch`.
- **M12:** `test_two_candidates_in_one_attempt_writing_the_same_logical_filename_retain_different_original_bytes`, `test_two_attempts_and_a_resumed_completed_candidate_retain_their_own_artifact_copies_after_restart`, `test_download_more_than_two_pages_containing_split_utf8_nul_and_0xff_bytes_reassembles_exactly`, `test_a_reference_and_offset_for_attempt_a_never_selects_attempt_bs_bytes`.
- **M13:** `test_no_synthetic_evidence_key_reaches_git_show_commit_path`, `test_clean_matching_commit_links_correctly_through_gitguard_diffcover_undercover`, `test_changed_repository_state_evidence_prevents_a_false_git_match`.
- **M14:** `test_browse_and_query_traverse_more_than_10240_rows_with_exact_totals_and_unique_ids`, `test_record_becoming_stale_is_excluded_by_query_mode_freshness_revalidation_at_any_page`, `test_memory_generation_mutation_mid_traversal_rejects_the_cursor`.
- **M15:** `test_slop_tool_reads_staged_bytes_not_live_source_when_live_content_diverges`, `test_offline_review_dead_asset_license_matrix_all_read_staged_bytes`, `test_a_clean_staged_file_with_marked_live_content_yields_no_finding`.
- **M16:** `test_explicit_target_a_py_does_not_claim_unrelated_b_js_as_consumed`, `test_root_scoped_scan_records_its_full_staged_source_scope`, `test_explicit_configuration_file_target_is_recorded_as_declared_consumption`.
- **M17:** `test_gitguard_candidate_executes_through_execute_scan_with_a_real_or_fixture_engine_binary_and_persists_evidence`, `test_unregistered_engine_stays_engine_route_missing`, `test_registered_engine_with_absent_binary_returns_structured_skipped_result`, `test_denied_explicit_permission_returns_permission_blocked`.
- **M18:** `test_escaping_symlink_argument_never_reaches_the_real_engine_argv`, `test_internal_symlink_and_explicitly_supported_external_configuration_are_not_overblocked`.
- **M19:** `test_stale_live_report_with_no_fresh_output_fails_honestly_rather_than_reusing_old_bytes`, `test_conflicting_positional_or_option_args_are_rejected_and_the_binary_is_not_launched`, `test_temp_directory_is_cleaned_up_on_success_error_timeout_and_cancellation`, `test_changed_coverage_bytes_alone_change_the_folded_provenance_identity`.
- **M20:** `test_stylelint_decoded_raw_source_field_uses_logical_path_not_staged_temp_path`, `test_trivy_decoded_raw_results_target_field_uses_logical_path`, `test_literal_message_or_fix_text_containing_a_path_like_substring_is_never_rewritten`.
- **M21:** `test_disappeared_inventory_file_during_staging_forces_incomplete_attempt_state_with_zero_scheduled_candidates`, `test_copy_or_hash_error_during_staging_prevents_the_affected_candidate_from_executing`, `test_staging_failure_never_falls_back_to_a_live_read_and_never_publishes_a_clean_result`.

**U-series (extends P69-04/P69-05/P69-06 test files, primarily `tests/test_tui_terminal.py`, `tests/test_tui.py`, `tests/test_subprocess_contract.py`, browser-acceptance coverage via `browser-qa-agent`/`e2e-runner`/`mcp__claude-in-chrome__*` where noted — those findings are not pytest-provable, per each one's own VERIFY section above):**

- **U01:** `test_f2_opens_project_selector`, `test_f3_switches_section`, `test_tab_cycles_panes_not_projects`, `test_shift_tab_cycles_panes_reverse`, `test_map_hierarchical_navigation_expand_collapse`, `test_question_mark_shows_real_current_bindings`, `test_function_key_escape_sequences_decoded_not_just_arrows`, `test_utf8_multibyte_input_decoded_correctly`, `test_posix_selectors_and_sigwinch_handling` (POSIX-gated), `test_windows_f2_f3_shift_tab_decode_to_named_actions_not_escape` (Windows-gated, no runner reachable here).
- **U02:** `test_dashboard_owned_check_suite_does_not_report_complete_before_terminal_status`, `test_dashboard_owned_scan_retains_operation_id_and_polls_it`, `test_poll_running_scans_uses_durable_operation_status_for_dashboard_owned_branch`, `test_control_session_reuses_one_authenticated_client_session_across_polls`, `test_401_during_poll_triggers_one_reexchange_and_retry_then_visible_disconnection_on_repeated_failure`, `test_cancel_submits_retained_operation_id_including_attached_callers_id`.
- **U03:** `test_reap_owner_processes_accepts_optional_run_id_filter_and_only_signals_matching_records`, `test_reap_owner_processes_with_no_run_id_filter_keeps_existing_owner_wide_behavior_for_dead_owner_recovery`, `test_detach_reaps_only_the_selected_local_runs_process_tree_not_a_sibling_projects`, `test_detach_preserves_failed_termination_records_and_sibling_run_records`.
- **U04:** `test_tui_styling_uses_theme_and_motion_tokens`, `test_layout_79_columns_uses_narrow_branch`, `test_layout_80_columns_uses_compact_branch`, `test_layout_99_columns_uses_compact_branch`, `test_layout_100_columns_uses_wide_branch`, `test_footer_is_two_rows_at_every_width`, `test_selection_and_expanded_hierarchy_preserved_across_resize`, `test_reduced_motion_renders_final_state_with_no_animated_refresh`, `test_no_color_and_reduced_motion_are_independent_settings`.
- **U05 (browser-acceptance):** `test_artifact_export_control_follows_next_offset_until_null_and_assembles_full_byte_content`, `test_artifact_export_control_rejects_a_truncated_or_inconsistent_page_sequence`, `test_artifact_export_control_supports_cancellation_via_abortcontroller`.
- **U06 (browser-acceptance):** `test_visible_handoff_preview_then_send_completes_using_stored_preview_inputs`, `test_source_or_attempt_change_between_preview_and_send_yields_409_and_zero_effects`, `test_stale_preview_disables_send_until_explicit_fresh_preview`, `test_handoff_preview_and_send_both_require_run_id_and_attempt_id_per_s06`.
- **U07 (browser-acceptance):** `test_shell_interactive_signal_independent_of_map_fetch_completion` (verified-by: `rtk grep -rn` across `tests/` this session confirms this exact name does not exist yet — real gap, matching this finding's own claim).
- **U08 (browser-acceptance):** `test_terminal_event_pulse_plays_once_480ms_on_real_scan_completion_via_normal_ledger_polling`, `test_terminal_pulse_has_exactly_one_iteration_and_no_animation_under_reduced_motion`.
- **U09:** the fix target is the existing `tests/test_tui_terminal.py::test_no_color_env_suppresses_ansi_color_codes` (line 318) — add `test_pty_harness_capture_never_returns_empty_bytes_on_a_successful_run` as the new harness-level regression guard. **Re-execution this session could not reproduce the claimed failure, across 9 separate attempts**, verified-by (all run this session against the unchanged frozen HEAD): the named test alone, 5 consecutive runs, all passed; the whole `test_tui_terminal.py` module, 1 run, `9 passed`; the reviewer's own combined focused suite — `test_tui.py`+`test_tui_terminal.py`+`test_dashboard_http_contract.py`+`test_subprocess_contract.py` — 1 run, `120 passed, 1 skipped`; and the full required-gate command this report's own §2 table cites, `pytest tests/ -q`, 1 run, `2567 passed, 6 skipped, 16 warnings in 408.35s` — zero failures, one more pass than this report's originally recorded `2566 passed` figure, consistent with the named test passing where the original run recorded it failing. This does not retract the finding: the harness defect described (`_collect` not draining/joining the reader thread before PTY close) is itself real (verified-by: direct read of `tests/test_tui_terminal.py:215` this session, matching the finding's own citation), and is a genuine race condition by construction — a race that fires 0 times in 9 attempts here is not proof it cannot fire elsewhere (different hardware, load, OS scheduler). But §2's original table entry for this run (`1 failed, 2566 passed... Failure: ...test_no_color_env_suppresses_ansi_color_codes`) is a point-in-time observation from the original review session that this session's own independent re-run, under matching command and unchanged source, could not reproduce even once — record both facts (original observation, and this session's 9-for-9 non-reproduction) rather than treating either alone as the settled state. The fix (draining/joining the reader thread) remains the correct closure regardless of reproduction rate, since it removes a real race by construction rather than papering over an observed symptom.
- **U10 (browser-acceptance):** `test_all_five_memory_actions_expose_owner_kind_and_id_control`, `test_project_owner_uses_selected_registered_uuid`, `test_user_agent_owner_accepts_opaque_nonblank_label`, `test_session_owner_uses_non_secret_owner_scope_id_from_session_state`, `test_missing_or_foreign_or_mismatched_owner_leaves_storage_unchanged`, `test_session_renewal_supplies_new_non_secret_id_without_transferring_old_rows_ownership`.
- **U11 (browser-acceptance):** `test_content_field_shows_json_object_example_and_rejects_non_object_input_client_side`, `test_malformed_or_non_object_content_sends_no_post_request`, `test_source_kind_select_offers_exactly_local_tool_cross_tool_handoff_human_derived_for_write_and_promote`, `test_edit_does_not_require_source_kind`, `test_valid_write_edit_archive_sequence_produces_correct_revisions`.

**D-series:** no named tests apply — D01/D02 are prose-documentation findings whose own RED step (a manual isolated-project walkthrough comparing claimed vs. observed behavior) is already the correct, implementation-ready acceptance method for a documentation change; D03 is a plan/evidence-reconciliation finding with no test surface. Neither needs augmentation.
