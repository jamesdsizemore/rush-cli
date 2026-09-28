# Phase 70 design gate: test-suite speed (TS)

Owner requirement: the full suite must not take 20+ minutes, and sharding is not a fix; the tests themselves must be fast. Baseline: 32m42s serial on the owner's machine (HEAD 3ffa374, 3,302 tests including T8's file).

The design-gate agent measured this on a scratch copy with all fixes applied. The table gives full-suite time on the same machine, with load averages of 30 to 99:

| Tree | Time | Failures |
|---|---|---|
| HEAD, run 1 | 47m53s | 16 |
| HEAD, run 2 | 51m46s | 14 |
| All fixes | 10m33s | 3, all pre-existing (§8) |

Estimated owner-machine time after every fix: about 7m25s–7m50s. Measured times were converted with the owner/scratch ratio of the same tests, 0.653; the whole-suite ratio, 0.639, agrees.

No assertion is weakened, and nothing is skipped, marked xfail, moved to `slow`, or given smaller data.

## 1. Root causes, ranked by cost

| # | Cause | Evidence | Before -> after (scratch machine) |
|---|---|---|---|
| R1 | Scan tests run the host's installed engines, including a local LLM | 74 tests = 1,654s = 59% of run 1 | git_artifacts 405->23s; dashboard_scan_actions 362->34s; full_project_scan 185->8.5s; project_journey 123->6.3s |
| R2 | 7 tests leave `serve_forever` threads spinning | 2,876s of background-thread CPU after the first leak (4s before it) | 44s background CPU in the whole fixed run |
| R3 | `_project_view` runs a full capability scan on every request | 759 samples at `capabilities.py:107`; `resolve_project` 136ms per call | covered by the dashboard numbers above |
| R4 | `expand_group` rebuilds the full graph for every page | 400 pages x a full 40k-node rebuild | 109.9s (owner) -> 1.5s |
| R5 | `recall_page`/`hybrid_page` retokenize the whole page for every candidate | 517–578 `_count_tokens` calls per page | scan-cap 10.5->0.6s; memory probe 15.4->3.4s |
| R6 | `build_operations_inventory` builds a second MCP server on every call | 0.8–1.2s per call | read-ops 26.2->0.3s |
| R7 | 11.4MB stale coverage manifest, 97.6% of it an untracked `research/` tree | 48,075 records; 11.2s to parse | 11.9->0.1s |
| R8 | `server.shutdown()` waits for the 0.5s `serve_forever` poll | 138 shutdowns x ~0.45s | about 60s |
| R9 | A 10s timeout is waited out twice | `test_native_startup_timeout_reaps_child[2]` | 20.2->4.6s |
| R10 | A 25-commit repo is built with 75 git spawns | | 23.4->0.9s |
| R11 | Heal child pytest processes autoload the venv's plugins | A/B test on the heal file | 161.5->125.0s |
| R1b | Lifecycle staging tests use the real catalog, and one is too weak to catch its bug | ollama takes 71s in one test; a mutation check still passes | 166s->0.3s; the test now proves its property |
| C1 | Waits that race admission release or publication | exposed once scans are fast | correctness prerequisite |
| C2 | The dashboard can reset the connection over its own 413/400 | 9/12 failures at HEAD when run alone | 16/16 pass |

## 2. Fixes

### R1 — engine resolution is hermetic for scan tests (tests only)
`tests/conftest.py` gets `_hermetic_engine_path(bin_dir)` plus the fixtures `hermetic_engine_path` (function scope) and `hermetic_engine_path_module` (module scope):
- PATH becomes a temp bin dir holding only a `git` symlink, plus `/usr/bin:/bin:/usr/sbin:/sbin`.
- On Windows it is Git's cmd dir plus `System32` and `SystemRoot`.
- `rush.runtime.binaries.clear_binary_cache()` runs before and after.
- The venv's pinned engines still resolve, because `resolve_binary` checks `sys.prefix/bin` first.

Where it applies:
- `pytestmark = pytest.mark.usefixtures("hermetic_engine_path")` in `test_dashboard_scan_actions.py`, `test_dashboard_missing_routes.py`, `test_dashboard_git_artifacts.py`, `test_full_project_scan.py`, `test_scan_rescan.py` and `test_scan_handoff.py`.
- The module-scoped journey fixtures `journey` (`test_project_journey.py:33`) and `ui_journey` (`test_dashboard_user_journey.py`).
- A per-test mark on the 28 `test_dashboard_map.py` tests that reach `execute_scan`, rescan, resume, check-suite or scan actions. The file has live node/tsc tests, so there is no module-wide mark. The full list of names is in the design-gate receipt: the test_a_completion..., rehydrate..., check_suite..., crash_after..., dashboard_owned..., hydration_racing..., initial_launch..., launch_populates..., legacy_attempt..., per_run_publication..., persisted_inventory..., present_but_empty..., publication_query..., reconcile_admissions (x2), recovery_required..., rescan_with_unchanged..., resume_pre_execution..., retained_candidates..., scan_bytes_a..., scan_resume_publishes..., and scan_start_with_live_dashboard... tests.

Deliberately left running live engines: `test_live_engine_execution.py`, the `*_reference.py` tests, the `needs_*` tests, `test_ai_eval::test_eval_live_local_provider`, `test_phase20_slop_tdd::test_cli_slop_clean_file`, and the `test_phase57_*` parity tests.

**This replaces T8's `monkeypatch.setattr("rush.engines.ENGINES", {})`** in `_isolate_data_roots` of `test_dashboard_map.py` and `test_dashboard_scan_actions.py`. Remove those lines. An empty `ENGINES` sends every engine row down the registry-mismatch branch (`project_run.py:713-721`) instead of the real engine route. It can't be applied to `test_full_project_scan.py`, which asserts "semgrep not on PATH", or to the git-guard tests. Hermetic PATH keeps the real route, the real catalog rows, and the later candidate boundaries the cancel tests rely on.

Update the comments at `test_dashboard_scan_actions.py:262-270` and `test_project_journey.py:105-109,124-125`. The assertions stay unchanged.

### R1b — lifecycle staging tests (`tests/test_project_run_lifecycle.py:1179,:1212`)
Add a `monkeypatch` parameter, then `monkeypatch.setattr(project_run, "ENGINE_SPECS", {})` and `monkeypatch.setattr(project_run, "ALL_TOOLS", [_InstantTool("quick-a")])`, the file's own documented technique. Test-depth fix: today, unavailable real-catalog candidates force `incomplete` by themselves, so a mutation that drops `staging_failures` in `_finalize_attempt` still passes. After the fix, it fails.

### R2 — the 7 tests that leave servers spinning (`tests/test_dashboard_http_contract.py`)
Add `server.shutdown()` before `server.server_close()` in the `finally:` block of the tests at `:3695`, `:3729`, `:3772`, `:3821`, `:3849`, `:3888` and `:3914`. Do NOT add it at `:277` or `:401`: those tests never serve, and `shutdown()` would block forever.

Recurrence guard in the autouse fixture at `tests/conftest.py:16-24`: record the `(serve_forever)` threads before the test; after `stop_all_dashboard_contexts()`, join any new ones (1s) and fail if any is still alive, with "test left an HTTP server serving: call server.shutdown() before server.server_close()".

### R3 — `_project_view` (production, `src/rush/workflows/projects.py:52,253-256`)
Replace `inspect_capabilities(root)["languages"]` with `load_config(start=root)` (kept so an invalid `rush.toml` still fails the view closed) followed by `languages = detect_project_languages(root)`. This is exact: `inspect_capabilities` computes languages the same way (`capabilities.py:68`).

### R4 — `expand_group` rebuilds per page (production)
1. `project_map.py`: a single-entry memo `_MEMBERSHIP_CACHE` under `_MEMBERSHIP_LOCK`.
   - Key: the snapshot object's identity, `_snapshot_guard(snapshot)` (sequence, source_identity, and the id and length of files/findings/memories/agents), and the filter hash.
   - Value: the filtered node list plus a per-group member cache.
   - `expand_group` replaces lines 829-843 with `_group_members(...)` and returns `[dict(node) for node in members[offset:offset+page_size]]`.
   - Add a comment saying this relies on M01 (published snapshots are replaced, never mutated in place).
2. The server path:
   - `state.py`: add `get_published(project_id)`, which returns the stored record itself, read-only. It is used by `_hydrate_published_scan` (`:1431`), by `_sync_current_map` (`:1477`), and by `_handle_snapshot` when `section == "map"`; `:4621` becomes `get_published(...) or record`. Every other section keeps `get()`.
   - `_historical_map_snapshot(...)` keeps its signature, because tests call it, and wraps `_build_historical_map_snapshot(...) -> (snapshot|None, reusable)`, where `reusable = "file_inventory" not in manifest or bool(manifest["file_inventory"])`.
   - The map route uses `_historical_map_snapshot_reused(ctx, root, project_id, record, run_id, attempt_id)`, with a single-entry `ctx.historical_map_memo` set to `None` in `DashboardContext.__init__`. Its key is `(project_id, run_id, attempt_id, manifest st_mtime_ns, st_size, record.snapshot.get("root"))`, computed after the build.

### R5 — token counting (production, `src/rush/memory/retrieval.py:412-445,:937-946`)
Add the shared helpers `_contains_special_token(text, encoding)` and `_trial_page_bytes(items, items_bytes, item, *, max_bytes, max_tokens, encoding)`:
- They keep a running byte total of the compact JSON.
- They fully tokenize only when the running bytes exceed `max_tokens` or the item contains a special token. This preserves tiktoken's `ValueError`.
- `recall_page` starts from `items_bytes = floor_bytes`; `hybrid_page` starts from `_measure_page([], None, True, encoding)`.

It is exact because the tokenizer is byte-level: a page can never have more tokens than bytes. The design gate checked equivalence by hashing results: 480 recall scenarios and 108 hybrid scenarios were identical.

### R6 — `build_operations_inventory` (production, `src/rush/governance/public_operations.py:15,63-66`)
Use the module-level `rush.mcp.mcp_server` instead of calling `build_server()` again.

### R7 — coverage manifest (`src/rush/governance/coverage_manifest.py:28-48`, `governance/first-party-coverage.toml`)
Add `".scratch"` to `EXCLUDED_DIRS`. Regenerate LAST, from the phase worktree, with `python scripts/build_remediation_manifests.py --coverage`. The expected result is about 1,452 records, which parse in about 0.03s.

### R8 — `serve_forever` poll interval
Pass `kwargs={"poll_interval": 0.05}` at all 13 `threading.Thread(target=<x>.serve_forever, ...)` starts:
- `test_dashboard_scan_actions.py:46`, `test_dashboard_git_artifacts.py:62`, `test_dashboard.py:66,165`, `test_ai_eval.py:208`, `test_dashboard_http_contract.py:232`, `test_dashboard_map.py:140`, `test_dashboard_memory_tokens.py:62`, `test_dashboard_projects.py:42`, `test_executed_modes.py:1021,1077,1520`;
- `scripts/benchmarks/run.py:931`.

### R9 — native startup timeout (`tests/test_phase61_transport.py:141`)
Before `dispatch`, monkeypatch `multiprocessing.connection.Connection.poll`: poll in 50ms steps, and report the deadline expired as soon as the peer's pidfile shows it has reached `stage`. All assertions stay, including `< 14`. Re-derive the patch point against T8's forkserver version of `_send_native`.

### R10 — 25-commit repo (`tests/test_dashboard_git_artifacts.py:699-712`)
Build the chain with one `git fast-import`, via a new `_commit_files(root, commits)` helper: same author, subjects and files, then `git reset --hard HEAD`. The later `_commit_file(root, "late.txt", ...)` stays.

### R11 — heal children (`tests/test_phase47_heal_apidiff.py`)
Add a module autouse fixture that sets `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`. The perturbation plugin is loaded explicitly with `-p`.

### C1 — waits that race admission release or publication
- `test_dashboard_scan_actions.py`: add `_wait_operation_terminal(base_url, project_id, cookie, operation_id)`, which waits until the `/operations/{id}` status is `terminal`. Call it after the existing run-visible wait in:
  - `_seed_baseline_and_rescan` (before rescan);
  - `test_handoff_preview_hash_changes_when_evidence_artifact_version_changes`;
  - `test_baseline_attempt_id_differs_from_executing_attempt_id_for_resume`;
  - `test_fresh_execution_after_release_receives_a_new_attempt_id` (the first resume);
  - `test_scan_cancel_on_terminal_target_returns_stored_result_not_a_fresh_cancel`;
  - `test_cancel_retains_partial_results`, before the `active_run_id is None` assert.
- `test_dashboard_missing_routes.py`: `_seed_one_run` waits for its operation to reach `terminal` (30s timeout). `test_events_route_surfaces_real_candidate_progress_events` additionally waits for `ctx.projects.get(pid).sequence > published_before`.

### C2 — lingering close for rejected bodies (production, `src/rush/dashboard/server.py:4021-4050`)
T8 already added `_linger_discard` for the 413 path. It must cover all four early rejections: the Transfer-Encoding 400 `(None)`, the invalid Content-Length 400 `(None)`, the negative Content-Length 400 `(None)`, and `length > MAX_BODY_BYTES` 413 `(length)`. Bounds: `_MAX_DISCARD_BYTES = 4 * MAX_BODY_BYTES` and a 2s timeout; set `close_connection = True`. Draining only the 413 case still failed 2/12, on the chunked 400. Trust-boundary work: Opus.

## 3. Test matrix (written first by a separate test author; each case must fail before the fix unless it is marked keep-green)
- **R3:** with `inspect_capabilities` and `shutil.which` monkeypatched to raise, `resolve_project`/`list_projects` still succeed, and `languages == detect_project_languages(root)`. An invalid `rush.toml` still raises `RushConfigError`.
- **R4 memo:**
  - two snapshot dicts with the same project, source and sequence each page their own members;
  - appending to `snapshot["files"]` invalidates the memo;
  - mutating a returned member does not change later pages;
  - a different filter gives different membership.
- **R4 server:**
  - paging a 250-member group over HTTP calls `_build_full_graph` once per published record (spy);
  - the stored snapshot deep-equals a pre-paging copy;
  - a second historical request reuses the view;
  - rewriting the manifest invalidates it;
  - an empty persisted `file_inventory` is never reused.
- **R5:**
  - with 1e6 budgets and 512 items, `_count_tokens` is called 3 times or fewer (today about 514);
  - results equal an inline copy of the old loop across budgets, including `<|endoftext|>` content (same `ValueError`).
- **R6:** `build_operations_inventory()` works while `rush.mcp.build_server` is monkeypatched to raise.
- **R7:**
  - `build_manifest(<repo>)` succeeds;
  - every record path in the checked-in manifest exists in the tree.
- **R1 fixture:**
  - inside it, a fake executable on the original PATH does not resolve, while `git` and the venv's `ruff` do;
  - after teardown, PATH and resolution are restored.
- **R2 guard:** a pytester meta-test where a `_serve` that only calls `server_close()` errors at teardown, and one that also calls `shutdown()` passes.
- **R1b:** the mutation check (drop `staging_failures`) makes `test_staging_failure_never_falls_back...` fail.
- **C2:**
  - the 257KB oversized POST and the chunked POST get 413/400 in 50 of 50 runs;
  - a client that declares a 100MB `Content-Length` and trickles data is cut off within 2s + 1s and after at most `_MAX_DISCARD_BYTES`.
- **C1:** each affected test passes 20 of 20 runs.
- **Suite-time acceptance:** the serial full suite (`-m "not slow"`), measured on the owner's machine, is far under 20 minutes. The target is about 7m30s, with 0 failed and 0 skipped. The existing environment skips are resolved separately (§5).

## 4. Kept as-is, with evidence
- **Heal, about 75s after R11:** one process per observation is the diagnosis's isolation property.
- **Live tests:** `test_all_tools_execute_live_on_polyglot_repo` (33s), `test_eval_live_local_provider` (13.4s), and the stdio MCP tests (11–12.5s, a real server).
- **Tests whose cost is their property:** events retention (2,001 commits, 2.1s), `test_no_undocumented_persistence_or_lock_seams` (parses 465 files, 3.6s), and tests that call `build_server()` directly.

## 5. Pre-existing skips (owner rule: zero skipped tests)
Found at HEAD, and every one must be made to run:
- the Windows-only ACL test at `test_dashboard_http_contract.py:1557`, which needs a Windows CI lane;
- 5 `test_executed_modes` "real … acceptance disabled" skips, which need the `RUSH_REQUIRE_REAL_ENGINES` lanes;
- 2 "no native archive" skips at `test_phase52_installed_artifacts.py:193` and `test_release_asset_contract.py:157`, which need a PyInstaller archive built in the suite.

Owner: TS, as part of making the suite complete.

## 6. Order
TS runs after T8 commits. It is built on the phase branch after the task branches (T18, T15, T14, T3, T24) are merged, because `server.py` and `projects.py` overlap with them. R7 is regenerated as its last step.
