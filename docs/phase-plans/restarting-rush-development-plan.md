# Restarting Rush development

**Owner acceptance approval (2026-10-04):** The owner explicitly approved the reviewed temporary Claude Code/Codex Rush configuration conversion, native plugin/guidance installation, scoped fixture hook acceptance and cleanup/restoration, plus exactly five existing CI gate conditionals so mypy, documentation parity, dependency audit, whitespace and Windows data-directory ACL checks run after test failures unless cancelled. This supersedes the earlier no-CI-edit restriction for those five steps in addition to the approved macOS artifact job. Existing failures remain visible; no new runner/job or UI waiver is approved. Consent authorizes execution, not an acceptance result.

**Owner CI approval (2026-10-04):** The owner approved extending Phase 70's existing artifact-probes CI job with native `macos-15` arm64 build and downloadable checksum/source-commit-bound candidate. This supersedes the prior no-CI-edit/local-macOS-build decision only for G5/G6 artifact production. Build runs on CI, without release publication or version changes. Acceptance still requires the exact run, current artifact checks and separately consented real Claude Code/Codex adoption. All UI acceptance remains Phase 71.

**Owner scope correction (2026-10-04):** All UI implementation and acceptance belongs to Phase 71, superseding the earlier Phase 70 UI/TUI allocation and all-T1–T29/G0–G8 transition wording below. Preserve the complete UI contracts, existing changes and evidence; no transferred check is waived or accepted. Finish Phase 70 non-UI engines, permissions, identity, memory, setup, CLI/MCP and Claude Code/Codex integration first. Phase 71 retains its entire prototype/dashboard plan and additionally owns transferred TUI and terminal/browser acceptance. Existing protected planning files and unrelated work remain preserved.

Verified: 2026-10-03. Audience: owner and next implementation agent. Status: restart plan, not product acceptance or authorization to merge, publish, change host configuration, or discard existing work.

## 1. Restart decision

**Continue development in `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70`, branch `phase/70-agent-adoption-and-usability`, HEAD `66c6c799eaa5b6017776d659e9e0de2b4a8878a5`. First finish Phase 70's current failing acceptance and CI portability work. Do not start Phase 70 over.**

The primary checkout, `/Users/jamesdsizemore/Developer/rush-cli`, is on `codex/codex-cli-mcp-commands-review` at `c78e445ba1e575ca373e35840142cd627b055d6a`. It contains the recent uncommitted command plans, audit, remediation reports and instruction changes. It does **not** contain the subsequent Phase 70 implementation. The phase branch is 234 commits ahead of this primary HEAD, with no primary-only commits. Its committed delta spans 360 files, including 119 source files and 130 test files. These counts establish divergence, not correctness.

Three separate states explain the confusion:

1. Existing application: real CLI, stdio MCP, interactive TUI, HTTP dashboard, provisioning and memory implementations.
2. Later development: substantial Phase 70 code on its separate branch, with unresolved acceptance and platform failures.
3. Future contracts: dashboard prototype integration, memory/activation/graph/token work and command remediation plans. Their existence does not implement their requirements.

Phase 70's current handoff explicitly says **not complete**. Its final commit adds handoff documentation, not runtime repairs. Its implementation-evidence report describes older revisions and leaves the CI-runs section without actual run conclusions. Current verification below independently reproduces additional T29 failures.

## 2. Evidence boundary and current checks

Source discovery used Graft and Repowise, followed by live source/AST, Git identity, file existence and actual execution. Repowise identifies primary `c78e445` as its indexed revision; it is not evidence of Phase 70 runtime acceptance. All observations below belong to the stated checkout. Historical report claims remain historical.

Both checkout environments execute Python **3.12.12** with `uv run --frozen --python 3.12 --extra dev` and inherited `PYTHONPATH` cleared. Their lock files differ; never copy primary's environment or test verdict onto Phase 70.

| Subject / check executed on 2026-10-03 | Observed result | Meaning |
|---|---|---|
| Phase 70 Git status | Clean tracked and untracked state before this document | Existing implementation checkout is preserved and usable for bounded development. |
| Phase 70 `ruff check src tests scripts` | PASS | Lint only. |
| Phase 70 `ruff format --check src tests scripts` | PASS; 938 files already formatted | Formatting only. |
| Phase 70 `mypy src/rush` | PASS; 474 source files | Configured production type gate only, not `mypy .`. |
| Phase 70 `python scripts/sync_docs.py --check` | PASS: `Documentation coverage and runtime contracts match.` | Documentation contract check, not application usability. |
| Phase 70 `git diff --check` | PASS | Whitespace only. |
| Phase 70 G1–G4 files plus `test_phase70_tui_usability.py` | **2 failed, 663 passed**, 72.44 seconds | Current T29 acceptance fails. This is not the full Phase 70 regression suite. |
| Second, bounded T29 reproduction with `-vv --showlocals --tb=long` | Same granted-scan failure; full child results retained | Failure diagnosis below comes from actual returned results, not inference from aggregate status. |
| Primary lint | FAIL: 8 errors | Unused test locals, dictionary style/value iteration and two import-order defects. |
| Primary formatting | FAIL: 9 test files | Older checkout fails baseline formatting. |
| Primary default pytest characterization | Interrupted after **1 failed, 1418 passed, 6 skipped, 1 deselected, 9 warnings**, 481.60 seconds | Partial run only. Stopped once actual continuation root was established; never a full-suite PASS. |

Primary's reproduced behavioral failure is `tests/test_dashboard_missing_routes.py::test_events_route_surfaces_real_candidate_progress_events`: `/events` contained no candidate progress events. This belongs to the old primary snapshot; reproduce against Phase 70 before treating it as remaining product work. Primary formatting failures are in dashboard HTTP/map/memory/missing-route/scan tests, diff-cover, full-scan, project-journey and project-run-lifecycle tests. Do not polish this obsolete snapshot instead of continuing the phase branch.

### Current T29 failure: verified dependency-scope contamination

Both failing tests are in Phase 70 `tests/test_phase70_onboarding.py`:

- `test_t29_allowed_and_denied_scans_parity_cli_mcp_tui`, assertion at line 1539.
- `test_t29_user_outcome_parity`, assertion at line 1582.

They expect granted CLI/MCP/TUI checks to return `ok`. All three actually return `fail`. The second reproduction shows all other child checks `ok`; the `slop` child returns `fail`, summary **`aislop: 2 anti-pattern finding(s)`**, engine version `0.16.1`, executable `/opt/homebrew/bin/npx`, fixture cwd. The findings name `pyjwt` and `urllib3`, rule `aislop/security/security/vulnerable-dependency`, provenance `slop/aislop`, and a fixture-root `requirements.txt` path. Retained fixture has no such file. Pytest's child reports `no tests ran in 0.00s` and `ok`; empty collection is not this failure's cause.

Verified upstream cause: the retained test HOME's actual `aislop/dist/cli.js:17515–17527` invokes `pip-audit --format=json` without `-r` or `--project`, then hardcodes `requirements.txt` as finding path. At `17879–17899`, any Python manifest, including this dependency-free fixture's `pyproject.toml`, triggers that audit. It audits ambient interpreter dependencies, not declared fixture dependencies. Rush `src/rush/engines/aislop.py:226–230` prefixes relative engine paths with target root. No requirements file was generated. Error findings correctly become `fail` at `302–305`; aggregate parity remains intact.

Actual inspected artifact: `/var/folders/j5/lj1y2c4j5dxgrzs4x2j2n1bc0000gn/T/pytest-of-jamesdsizemore/pytest-1909/t29-home0/.npm/_npx/344dbbdbf7b2aa5c/node_modules/aislop/dist/cli.js`. Its `security.audit` boolean and `.aislop/config.yml` loader are verified at `3157–3159,3371–3373,3489–3511`. Do not weaken aggregate assertions or hide legitimate security findings. A scoped fixture config can isolate this deliberately dependency-free parity scenario; production default dependency attribution needs its own bounded correction.

Diagnostic log: `/Users/jamesdsizemore/Developer/rush-cli/.git/rush-restart-recovery/2026-10-03/t29-current-reproduction.log`. Contains the complete child metadata from the second executed reproduction. No third unchanged reproduction is needed.

## 3. What is actually developed

Paths in this section refer to the Phase 70 checkout unless explicitly marked primary. Source implementation and exercised acceptance are different columns.

| Surface | Actual implementation | Remaining boundary |
|---|---|---|
| CLI and MCP | Click CLI; shared `src/rush/tools/` implementations; stdio server; root-bound invocation; core/full profiles; compact delivery. `mcp.py:91–133,320–388` defines and validates the exact core set: `rush_status`, `rush_check`, `rush_lint`, `rush_review`, `rush_security`, `rush_test`, `rush_memory`. | Installed/native host calls and complete CLI outcome acceptance still require final-revision evidence. Core profile is absent from primary. Catalog counts are not total command counts. |
| TUI | Actual keyboard-driven application, background work, project selection, Overview/Map/Scans/Memory/Tokens/Git/Artifacts/Setup sections, paging/detail/export, cancellation and terminal lifecycle. `tui.py`, `dashboard/terminal_input.py`, `dashboard/keymaps.py`, T28 tests. | Historical walkthrough covered presentation and exit; registered-project setup→scan→agent→rescan and complete mutation/recovery/platform matrix remain required. Passing headless selectors cannot close G8. |
| Dashboard | Real authenticated HTTP server, project/action API, asynchronous provisioning/scans, result/map/memory views. `dashboard/server.py`, `application.js`, `panels.js`; existing dashboard contract tests. | Phase 71's complete prototype shell/assets/navigation/motion/section integration and installed browser acceptance are separate uncompleted work. Existing backend is reusable, not absent. |
| Provisioning and first use | Allowlisted engine catalog, reviewed setup, resolved package identities, grants, manifests, environment selection, install/bootstrap and readiness projections. `setup/provision.py`, `tools/install.py`, `tools/setup_wizard.py`, `tools/status.py`. | A top-level install result cannot prove every child engine ready. Final frozen install route, actual selected-host login/reload/tool invocation and failure recovery remain acceptance requirements. |
| Agent adoption | Native assets, managed host registrations, instructions, ownership/CAS disconnect and opt-in post-edit feedback. `integrations/agents.py`, new `agent_hooks.py`, request models and native package assets. These later files are missing in primary. | Registered configuration is not initialized transport or model use. `agents.py` readiness still uses registration for `any_connected`; report each stage honestly. Historical Codex calls were denied before reaching Rush. |
| Memory and continuity | Typed SQLite store; gated queries/writes, administration, checkpoint/handoff, read-only projections, attribution and context packing. `tools/memory.py`, `memory/store.py`, `continuity/context.py`. | Automatic authorized host activation, evidence application, cross-session continuation, correction semantics and measured quality are not established by storage/receipt presence. Phases 72–75 own explicit remaining guarantees. |
| Internal code graph | SQLite graph store/traverser and Python symbol-node indexing exist. | Inspected production Python indexer builds nodes; exhaustive indexed `insert_edge` search found store method and manually seeded tests, not production call-edge population. External Graft is a different engine. `codegraph/index.py` and `tests/test_phase74_graph.py` are absent; 74-T01 owns qualified multi-language graph population. |
| Local review and requested baseline additions | `tools/offline_runner.py:165–380` executes discovered Ollama/llama-cli using selected model/GGUF. Existing bounded review samples first 20 code files and first 1000 characters each. | This does not establish connected specialist-model orchestration. Source-corpus search established no voice/3D runtime implementation. Selectable voice/live speech, connected specialists and 3D companion remain requested baseline capabilities, not newly invented enhancements. |

No runtime sources were changed by this restart audit. No assertion here closes all T1–T29 requirements. The handoff's statement that their code landed is reconciled with actual files and current checks; its completion verdict remains **not complete**.

## 4. Open-plan reconciliation

This reconciles plan families with development, not every historical checkbox. Coverage includes developer phases 20–50 and their program plans, phase-plan sequence 41–75 including 50a/b/c and 69 remediation, MC00–MC15, CI/runtime/benchmark programs, both command batches and their governing audit/reports. Primary inventory contains 43 plan-named developer artifacts, 68 plan/MC-named phase artifacts and another 12 Q01–Q10 Markdown artifacts; filename counts are coverage inventory only.

| Existing authority | Disposition at restart | How it controls forward work |
|---|---|---|
| `docs/developer/repository-remediation-plan.md`; older developer/master/toolkit plans; phases 41–60 | Historical remediation completion claims and retained safety/release obligations. | Reuse developed contracts. Current failing prerequisite overrides an older PASS. No wholesale restart of old phases and no retirement of release/containment/redaction guarantees. |
| Phases 61/62; Phase 63; `MC00`–`MC15`; benchmark plan/review and evidence | Memory foundations exist. Phase index still labels 63 planned while MC15 claims historical integrated acceptance. Those statements have different revisions/coverage. | Use actual store/services. Recheck inherited seam in next owned packet; MC15 does not close automatic native activation, all benchmarks or future memory work. Superseded unified-memory original/ag y plans remain historical, not competing implementation authorities. |
| Phases 64/65/66 and evidence | Runtime/provisioning/interfaces exist despite stale planned labels. Phase 66 interface gaps led to Phase 69 remediation. | Preserve runtime correctness, provisioning, full interface and installed artifact contracts. Phase 70/71 consume them; do not implement parallel backends. |
| Phase 67 capability validation | Native cross-agent capability acceptance remains distinct from registrations and fixtures. | Reconcile each host scenario with Phase 70 G6 and Phase 73 host matrix; retain any unmet scenario. |
| Phase 68 onboarding/bootstrap | P68-01–07 still listed planned. Phase 70 implements parts of install/setup, not every 68 requirement. | Explicit reconciliation required for one elevated prompt, persistent boot/autostart, real reboot-before-login, animated display, rerun and uninstall. Keep outstanding platform behavior owned; do not silently replace it with `rush setup`. |
| Phase 69 and `docs/reports/69-dashboard-tui-codex-implementation-review.md`; remediation board | Historical independent review found 51 findings (S01–S16, M01–M21, U01–U11, D01–D03). Later fixes exist. | Map every finding to current source, regression and Phase 70/71 owner; neither repeat all legacy work nor close the board from an old count. |
| Phase 70 plan, amended worktree plan, handoff and implementation evidence | Active developed branch; CI and final acceptance incomplete. | Finish sequence in §5. Worktree amendments/owner decisions govern developed code; primary plan is older. |
| Phase 71 prototype integration plan | Proposed P01–P14 integration; primary file is untracked and not copied into the phase branch automatically. | Start only after every Phase 70 T1–T29 and G0–G8 requirement has final evidence. Integrate complete live dashboard, including all prototype sections/assets; sample data remains requirements evidence. |
| `memory-program-contract.md`, Phases 72–75 and PAS additions | Future shared authority/activation/graph/token contracts; several required modules absent. | Follow task-level DAG in §6 and one owner for shared files. No whole-phase parallel writing or invented completion. |
| Q01–Q10: `command-tdd-2026-10-01/00-shared-foundation.md`, ten command plans and README; remediation report | Planning artifacts based on an older source snapshot, with Phase 70 prerequisite and unapproved D1–D12 defaults. | Preserve files; reconcile each finding against Phase 70 before implementation. Implement remaining defects, requested extensions and new proposals as separate categories. Foundation then shared Ruff target work; follow actual dependency graph, not command numbering alone. |
| Q11–Q20: `command-remediation-batch-02/` | Ten files exist; no implementation or full readiness established by their presence. | Reconcile shared P0 isolation/P0A MCP-input contracts with Q01 foundation under one integration owner. Continue batch approval boundaries; do not generate remaining command batches as part of restarting development. |
| 79-command audit; command/session/orchestrator remediation reports; CI/runtime/benchmark plans and terminal roadmap | Findings, protected evidence and future product requirements, not implemented features or runtime acceptance. | Preserve individual command assessments. Carry unresolved audit corrections into their command owners. No external orchestrator/skill edits authorized by this document. |

Concrete absent future outputs in both inspected roots: `memory/authorization.py`, `memory/learning_context.py`, `token_economy/context_policy.py`, `continuity/context_query.py`, `token_economy/compression_worker.py`. Their proposed behavior is not supplied by similarly named existing modules.

## 5. Finish current development before product expansion

### Step 1 — Stabilize current Phase 70 test inputs and portability

**Owner:** one implementation writer for the bounded test/engine contract being changed. **Input:** current `66c6c799` and preserved diagnostic log. **Output:** actual reproduced failure, minimum justified patch, exact passing result and affected regressions. No product downscoping.

1. Repair current T29's dependency-free fixture with the exact proposed config below in `tests/test_phase70_onboarding.py::t29_world`. Keep actual Aislop anti-pattern subprocess and exact six-step/permission assertions. Then address production `AislopEngine` dependency scope: its ambient audit currently produces target-project findings from unrelated interpreter packages. Inspect existing project-environment and `pip-audit` input helpers before implementing one shared correction. Required behavior: findings bind to reviewed project dependency inputs or are explicitly identified as external-environment findings; never invent a project file. Exact production patch is not yet established because supported Aislop invocation overrides and shared environment/input integration still require bounded investigation. Acceptance fixture must have different project and ambient dependencies and assert only authorized project attribution, while preserving real project vulnerability findings. This is a genuine remaining behavior defect, separate from making T29's parity fixture clean.
2. Repair Windows test-helper import. Saved CI log establishes that `tests/_process_children.py` imports `pty` at module level; Windows `spawn_child` users fail collection through `pty → tty → termios`. Move that import into `spawn_pty_child`, immediately before `pty.openpty()`. `spawn_child` uses `subprocess.Popen` and does not need POSIX PTY. Production `dashboard/terminal_input.py` already imports POSIX terminal modules behind platform separation.
3. Reproduce the three saved Linux failures under an owned `/tmp` test directory: offline-review engine result, recorded-target lookup and truncated Git diff disclosure. Trace actual producer/reader/environment before fixing. Saved log identifies two occurrences of the same multi-threaded `fork()` warning in `test_t03_concurrent_connects_yield_one_lock_winner_and_consistent_ledger`; the old handoff's unidentified-second-warning statement is resolved by that log.

**Proposed T29 fixture patch, not applied by this audit:** insert after `t29_world` writes its empty-dependency `pyproject.toml`:

```python
    # Keep real anti-pattern scan; exclude ambient interpreter dependency audit.
    (root / ".aislop").mkdir()
    (root / ".aislop" / "config.yml").write_text(
        "version: 1\nsecurity:\n  audit: false\n",
        encoding="utf-8",
    )
```

This configuration narrows this test fixture only. It does not repair production dependency attribution or authorize disabling project security auditing.

**Proposed Windows patch, not applied by this audit:**

```diff
--- a/tests/_process_children.py
+++ b/tests/_process_children.py
@@
-import pty
@@
 def spawn_pty_child(
@@
+    import pty
+
     master_fd, slave_fd = pty.openpty()
```

Run existing checks after the justified changes, from the Phase 70 root:

```sh
rtk proxy env -u PYTHONPATH uv run --frozen --python 3.12 --extra dev python -m pytest tests/test_phase70_onboarding.py -k t29 -q
rtk proxy env -u PYTHONPATH uv run --frozen --python 3.12 --extra dev python -m pytest 'tests/test_phase70_t27.py::test_t27_catalog_semantics_and_human_output[offline-review]' tests/test_phase70_t28c_review2.py::test_outcome_detail_shows_recorded_targets tests/test_phase70_tui_usability_ef.py::test_t28e_tokens_git_artifacts --basetemp /tmp/rush-phase70-restart-owned -q
rtk proxy env -u PYTHONPATH uv run --frozen --python 3.12 --extra dev python -m pytest tests/test_tui_terminal.py tests/test_dashboard_http_contract.py -q
```

`--basetemp` removes its selected directory: use a new owned test-only path, never a project/recovery directory. Linux expectations: offline-review exact `ok`, recorded target values displayed and truncated diff explicitly says more remains. Native Windows must import `spawn_child`, execute a child successfully, then pass dashboard ACL/guard/frozen-entry steps previously blocked by collection. These proposed post-fix checks were not executed by this audit.

### Step 2 — Run complete Phase 70 acceptance on final frozen bytes

Resolve defects first; freeze final source/lock/binary identities. Run all Phase 70 task and T28-A–F checks, existing regressions, full G7 including slow tests, mypy source gate, documentation parity, dependency audit and installed wheel/sdist/native probes. Default local pytest excludes `slow`; explicitly include it. Current 665-test selection cannot replace this gate.

```sh
rtk proxy env -u PYTHONPATH uv run --frozen --python 3.12 --extra dev python -m pytest tests/ -q -m ""
rtk proxy env -u PYTHONPATH uv run --frozen --python 3.12 --extra dev ruff check src tests scripts
rtk proxy env -u PYTHONPATH uv run --frozen --python 3.12 --extra dev ruff format --check src tests scripts
rtk proxy env -u PYTHONPATH uv run --frozen --python 3.12 --extra dev mypy src/rush
rtk proxy env -u PYTHONPATH uv run --frozen --python 3.12 --extra dev python scripts/sync_docs.py --check
rtk git diff --check
```

Use existing CI/release build commands for artifacts; do not add a new runner or publish a release. Saved CI run `36465316792` concerns `e7c29b1`, not this audit's current source verification. Re-run Linux/Windows required lanes after fixes under separately authorized push/CI activity. No current remote CI verdict is asserted here.

### Step 3 — Re-run final installed T29/G5/G6/G8 journeys

Rebuild frozen executable from final passing source. Record commit, executable origin/version/digest, installed assets and arbitrary-cwd behavior. Repeat native host calls using actual host trace and domain output; distinguish registration, authenticated/connected, model-requested call, context delivered, evidence applied and continuation verified.

Historical evidence is incomplete: fresh-HOME setup left login/probe pending; Codex denied tool calls under policy `never`; unregistered-project TUI walkthrough did not complete repair cycle. Finish registered-project setup→scan→agent→rescan, full memory actions, tokens, Git diff, known/unknown artifacts, grants/cancel/recovery, resize/paste/NO_COLOR/reduced motion and idle Ctrl-C. Required terminal sizes/platforms are those in T28/G8, including native Windows. Missing native platform/host evidence stays an exact unmet lane.

Owner-approved real-host procedures recorded in the phase plan require preview/consent and backup/readback/byte restoration. Existing user-owned Rush registrations must not be treated as disposable managed entries. This restart audit does not modify them. Keep installed bootstrap checks in isolated prefix/HOME. Fill final implementation evidence with actual CI URLs/conclusions and the correct revision coverage receipt.

### Step 4 — Review, hand off, then integrate

Perform independent phase-end review against Requirement Ledger, actual file writes, runtime behavior, permissions, failures/recovery, assets and native acceptance. Reconcile all T1–T29, G0–G8 and inherited Phase 69 findings before final handoff. Any edit invalidates frozen verdict. Preserve current evidence while correcting only real defects.

Stage/commit/push only with explicit authorization applicable to that run. Merge into `main` remains a separate owner decision. Primary's uncommitted plans/instructions cannot be discarded or silently overwritten during integration. Phase 71's protected untracked plan and command artifacts must be transferred byte-for-byte or intentionally reconciled into the implementation branch before their dependent task starts; preview conflicts and preserve both versions.

## 6. Work after Phase 70: preserve complete scope

| Stream | Start condition / ordered work | Concrete output and acceptance |
|---|---|---|
| Phase 71 P01–P14 | All Phase 70 T1–T29/G0–G8 accepted. Then shell/assets and session/navigation foundations, live graph/map, Overview/scans/memory/tokens/Git/artifacts/setup, accessibility/motion, installed packaging, full browser acceptance, documentation/handoff. | Complete `dashboard/` integration using shared backends. Real live data and installed assets; no sample-only substitution. Keep all prototype surfaces from §5 ledger. |
| Phase 72 + Phase 73 foundation | `memory-program-contract.md` C01–C09 reconciled with current APIs. 72-T01 defensive read predicates can start independently; 73-T01 host diagnostics can overlap. 73-T02 owns shared authorization producer; consuming mutation/activation waits for that authority. | One `memory/authorization.py` and policy format; safe read/scope/version/paging/correction/relations/admin; native activation and ownership without parallel grants/stores. |
| Phase 73 continuation / PAS | Build on 72 safe reads and 73 authorization. Complete actual native activation, task state/capture, handoff receiver/uptake, worktree deltas, host matrix and portable capsule/PAS interoperability. | 73-T09 verified import/bridge/reread/continuation, explicit project mapping, honest offline snapshot state. Final app acceptance consumes Phase 70 T28-D and live Phase 71 surfaces. |
| Phase 74 | After shared contract, narrow 74-T01 graph and 74-T06 workflow foundations can start; dependent advice/invalidation waits for real qualified graph/freshness. | Production Python/TS/TSX/Rust graph population, versioned identities/edges/coverage, change invalidation, grounded learning/recipe/workflow/skill behavior and actual improvement evaluation. New `codegraph/index.py` and named graph tests are outputs, not existing helpers. |
| Phase 75 | Contract reconciled; independent 75-T01 receipts, T02 evaluation and T05 compact-view fixtures can start. Whole-packet budget/code/log work follows the budget/receipt contract; graph-supported completion additionally requires 74-T01. Memory selection/recovery requires 72-T01/T02; result query/deltas depend on canonical authority/retention; owned-provider compression remains opt-in. | Attributable actual usage, whole-packet budgets, selective cache/CCR, recoverable compact delivery/local query/deltas, real-agent quality benchmarks and supported provider behavior. No fabricated savings or fixture-only adoption claim. |
| Command remediation | Phase 70 gate and batch-specific owner decisions first. Rebase findings onto developed source; unify foundation/isolation/raw-MCP contracts before shared-engine packets. Keep next batch approval boundary. | Every command retains concrete current defect/RED/minimum patch/check, separate requested extension and genuinely new proposal assessment. Do not apply already-fixed historical patches or implement unapproved defaults. |
| Remaining baseline product capabilities | Reconcile Phase 67/68 and user-requested scanner provisioning, connected specialists, selectable voice/live speech and 3D companion into exact existing owning contracts. | Keep separate implementation and real acceptance rows. No assistant-created exclusion, innovation relabeling, or deferred stub closes a requested outcome. Missing ownership requires a bounded approved amendment, not silent deletion. |

This is task-level concurrency, not approval to execute all phases together. One integration writer owns `memory/store.py`, `tools/memory.py`, `cli.py`, `mcp.py`, shared dashboard/TUI adapters/tests, `pyproject.toml` and `uv.lock`. Separate worktrees do not remove these contract/package conflicts. Finish current Phase 70 correction before discretionary downstream implementation.

## 7. Worktree cleanup and development readiness

### Preserved and verified

Before authoring this document, primary had one tracked edit (`AGENTS.md`, +51/−8) and 115 untracked files: 86 scratch artifacts, 2 agent documents, 23 phase-plan files and 4 reports. All 116 files were backed up and each archived byte stream verified by SHA-256. No existing tracked/untracked file was removed, rewritten or staged.

Recovery directory: `/Users/jamesdsizemore/Developer/rush-cli/.git/rush-restart-recovery/2026-10-03/`:

- `primary-uncommitted.zip`, SHA-256 `9863d820ebf7ca8e5e3f2cb2f4d8bf4d4a63003713e26936a33188a2d86711cd`.
- `primary-inventory.json`, exact original path/size/digest inventory; separate working/index binary patches.
- `command-tdd-generated.zip`, SHA-256 `c84cfb827e75da1812946216bb91a8443d08e350c640afaf573370c4ecd865e2`, and its inventory: four generated Graft files totaling 35,589,438 bytes.
- `phase70-source-baseline.json`: 1024 source/test/script/package/lock files; combined digest `dabb0391cd358ac737cf33a0ac3b0182f85269946b91b4076a2ca4d70182fed8`. This records subject identity; it does not prove behavior.

AGENTS restoration uses saved current bytes/patch, not `git restore`. Original untracked documents restore to their exact relative paths from the archive; compare inventory digest before overwriting. Generated Graft files restore from their separate archive.

### Checkout disposition

| Checkout | Verified state | Action |
|---|---|---|
| Primary `rush-cli` | Old source; user-owned instructions/research/plans; active primary processes observed. | Preserve. This requested document belongs here alongside existing plans. Do not broad-clean runtime state or move user documents out of requested repository. |
| `rush-cli-worktrees/phase-70` | Unique developed branch; clean tracked/untracked state; valid locked Python environment; lint/format/mypy/docs pass. | Keep as development checkout. Preserve `.orchestrator/` gate/design/archive history and `.rush` state. Current tests prevent an acceptance-ready claim. |
| `.codex/worktrees/command-tdd/rush-cli` | Detached `c78e445`; no edits or unique commits; four generated ignored Graft files backed up. No process cwd was observed there. | Redundant checkout removal is prepared, pending explicit destructive-cleanup confirmation. Current-chat artifacts list is empty; that does not prove another chat has no attachment. Never force removal. |

Prepared cleanup command, not executed without requested confirmation:

```sh
rtk git worktree remove /Users/jamesdsizemore/.codex/worktrees/command-tdd/rush-cli
```

Recovery after approved removal:

```sh
rtk git worktree add --detach /Users/jamesdsizemore/.codex/worktrees/command-tdd/rush-cli c78e445ba1e575ca373e35840142cd627b055d6a
```

Then restore its four generated files from the verified archive if exact cache state is needed. A regenerated graph is not byte-identical recovery evidence.

### Remaining readiness constraints

Observed disk free space: **7.1 GiB**, below the existing handoff's **8 GiB** test prerequisite. Removing the small redundant checkout alone cannot establish that threshold. Primary `.rush` contains about 2.51 GB including actual memory/session/run/configuration state. `p64-promptfoo` accounts for about 2.18 GB of its cache; availability in cache is not proof it is safe to delete during active use. No indiscriminate cache deletion, `git clean`, reset, history rewrite or instruction removal is performed here. Inventory and approve an exact inactive cache/build removal before a disk-heavy full gate; otherwise free at least the measured shortfall elsewhere under separately authorized scope.

Primary remains intentionally dirty with preserved user artifacts plus this document. Clean Phase 70 is the implementation continuation root. Making primary both up-to-date and clean requires a separately reviewed integration plus explicit commit authorization for its existing artifacts; hiding them with stash or deleting plans would not satisfy recovery.

**Ready now:** correct checkout/branch identified; locked interpreter works; source gates pass; existing edits recoverable; current failing behavioral packet and cleanup candidate are concrete. **Not accepted:** full current regression/native/CI gates, disk headroom prerequisite, final Phase 70 evidence/review, Phase 71 and remaining product requirements. No product-ready or release-ready verdict.

## 8. Stop conditions and completion ledger

| Requested outcome | Delivered evidence / section | Remaining action |
|---|---|---|
| Understand developed app and restart location | §§1–3; two exact revisions; live source and current execution | Continue Phase 70, not old primary source or plan authoring. |
| Valid forward plan considering open plans | §§4–6; family reconciliation, exact task gates, ownership and full baseline obligations | Execute bounded correction, then required acceptance and existing dependency DAG. |
| Preserve and clean worktrees | §7; exact inventory, verified archives, safe removal/restoration commands | Redundant checkout deletion awaits explicit confirmation; primary integration/commits remain controlled. |
| Ready for development | §§2,5,7; passing source/environment checks and reproducible first defect | Resolve actual T29/CI failures; meet disk prerequisite before heavy gates. |

Stop writes if subject bytes drift during verification, source attribution is unresolved, shared contracts diverge, required side effects lack consent, or state provenance is uncertain before deletion. Record exact unmet native lane instead of accepting simulation. Two identical checks on unchanged bytes maximum; do not grow another runner/audit framework.

Next bounded development action: apply the scoped T29 fixture configuration in Phase 70 `t29_world`, then run its two exact failing selectors. Keep production Aislop dependency-scope correction as an explicit required packet; a passing fixture does not close it.

## 9. Primary evidence references

- Phase 70 checkout `docs/phase-plans/phase-70-agent-adoption-and-usability-handoff.md:3–54,75–107`: exact branch, saved CI, remaining acceptance and disk prerequisite.
- Phase 70 checkout `docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md:395–465`: T28-A–F, T29 and G0–G8, including required native evidence and owner decisions.
- Phase 70 checkout `docs/reports/phase-70-implementation-evidence.md:5–97`: older runtime identity, incomplete fresh-host/TUI outcomes, actual granted/denied traces and unfilled CI section.
- Primary `docs/phase-plans/README.md:31–87`, Phase 71 `§§3,5–8`, Phases 72–75 dependency/ownership sections and `memory-program-contract.md`: historical state versus future contracts.
- Primary command-batch README/foundation, command remediation report and 79-command audit: protected planning inputs, unresolved decisions and command-specific requirements; not production changes.

All source/test locations and logs refer to this audit's frozen checkout subjects. Historical CI/native evidence has not been presented as a new executed result. The proposed Windows patch and future verification commands remain unapplied/unexecuted.
