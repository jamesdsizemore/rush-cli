# Phase 70 restart execution checklist

Status: in progress, 2026-10-04. No phase acceptance or final handoff claimed.

Latest checkpoint: run `37231951857`, head `7e4028c`, passes all five
retained backend gates and compiled rollback on Linux/Windows/macOS. Overall
CI retains Phase 71 UI failures. Actual Claude loads installed Rush skill,
seven core tools, denied-build result and fixture F401. Granted test revealed
TestTool widening the explicit fixture path to its ancestor; minimal shared
dispatch fix and mocked RED/GREEN regression are frozen-reviewed. Native
rebuild and successful host/edit/hook/timeout acceptance remain required.
Temporary user/project registrations, plugins, resources, guidance and hooks
were removed without conflicts; original manual Rush entries and modes were
CAS-restored. Current evidence report supplies exact receipts and supersedes
older checkpoints below.

CI-trigger checkpoint: pushed scope fix `3f8bf5a` could not start CI while
PR 2 conflicted with newer upstream documentation. Branch merge retains the
newer Phase 73 plan exactly; runtime fix hashes are unchanged. Imported docs
coverage and links are reconciled, including a corrected GitHub underscore
anchor validator. Remaining sequence: commit/push reviewed merge, consume
fresh native artifact, complete both host journeys and cleanup, reconcile
final native/CI receipts and perform frozen final review.

Current checkpoint (2026-10-04): CI run `37226805311`, source `ae69282`,
completed failure: six of eight jobs passed. Linux Quality reported 6470 passed,
three Phase 71 UI failures and 26 deselected in 1251.15 seconds; Windows
reported 57 passed and three Phase 71 UI failures. The prior macOS warmup
regression is absent from the current full-suite failure list. macOS npm
warmup/build/probe/upload, downloaded native origin/import/MCP probe and
current Linux/Windows wheel/sdist probes passed. Windows native checksum,
origin/version/MCP assertions passed before its UI asset assertion failed;
Linux native artifact checks and existing installation rollback selectors passed
under the verified full-suite selection. The new compiled-candidate
checksum/probe rollback cases both passed on macOS against downloaded
`ae69282` bytes. Both selectors are included by existing Linux/Windows CI
selections; their new CI execution remains pending.
Windows ACL, mypy, docs parity/links, dependency audit and whitespace gates
were all skipped. The G6 fixture now has one real greeting assertion, verified
by direct Python 3.12 invocation. Real-host G6 execution, provisioned
native timeout route, actual host/hook/timeout/model acceptance, retained
end-to-end journeys and final frozen review remain open. The current
evidence-report checkpoint supersedes older dated
execution states below; transferred UI remains Phase 71. Production attribution
repair is implemented with focused regression and review evidence; final CI
acceptance is still required.

Owner execution approval (2026-10-04): temporary real Claude Code/Codex
configuration conversion, native plugins/guidance, scoped fixture hooks and
cleanup/restoration are approved. Exactly five existing backend CI gate
conditionals are approved, applied and frozen-reviewed; their actual next-run
results remain required. Run `37230144466`, head `4e1aab6`, reports Windows
59 passed and the same three Phase 71 UI failures, with no skips. Existing
selection includes both new compiled rollback cases; the two-pass increase
and exhaustive unchanged failure list establish their native Windows PASS.
Linux's new cases were still running at this checkpoint. Approval closes the
permission gate, not G6 or Phase 70 acceptance.

Current priority (owner correction, 2026-10-03): finish existing Phase 70 CI
blockers and full gates. Linux/Windows testing uses existing CI lanes; no
separate native machines requested. Separate production Aislop attribution
work is stopped pending completion of this priority; its requirement remains
unresolved, not removed.

Authority: primary checkout `docs/phase-plans/restarting-rush-development-plan.md`
§5, this checkout's amended `phase-70-agent-adoption-and-usability-plan.md`,
Requirement Ledger and G0–G8. Implementation checkout:
`/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70`, branch
`phase/70-agent-adoption-and-usability`, starting HEAD
`66c6c799eaa5b6017776d659e9e0de2b4a8878a5`.

All downstream contracts remain required at their existing dependency gates.
This checklist executes Phase 70 first; it does not revise product scope.
Claude Code and Codex are required hosts under the recorded owner amendment
in §3.3; Cursor requirements are superseded by that amendment.

## 1. T29 fixture and production dependency attribution

Required behavior: dependency-free T29 fixture exercises actual anti-pattern
subprocess and unchanged CLI/MCP/TUI permission and six-step assertions.
Production findings bind to reviewed target dependency inputs or disclose an
external environment; real target vulnerabilities remain visible.

- [x] Read current fixture, exact failing assertions and restart diagnosis.
- [x] Apply specified `.aislop/config.yml` only inside `t29_world`.
- [ ] Resolve production `AislopEngine` invocation/input attribution using existing helpers.
- [x] Run exact two previously failing T29 selectors: 2 passed in 18.24 seconds.
- [x] Run complete T29 selection: 8 passed, 38 deselected in 18.06 seconds.
- [ ] Freeze production packet bytes; run dependency attribution regression.
- [ ] Independent review, corrections, affected regressions and final read-only review.

Checks: `rtk proxy env -u PYTHONPATH uv run --frozen --python 3.12 --extra dev python -m pytest tests/test_phase70_onboarding.py -k t29 -q`;
production check must exercise different project/ambient inventories and
preserve actual project vulnerabilities. Fixture PASS alone cannot close this packet.

## 2. CI portability

Required behavior: Windows imports `spawn_child` without POSIX PTY modules;
actual child executes. Linux offline review executes its required engine;
recorded targets display; truncated diff discloses remaining output.
Concurrency check uses actual independent processes without threaded fork.

- [x] Trace saved CI failures and current producers/readers before edits.
- [x] Apply minimum justified corrections; preserve exact domain assertions.
- [x] Freeze packet; run three saved Linux selectors, T03 concurrency and unavailable-runner check: 5 passed.
- [x] Run terminal/dashboard/fork-free-helper regressions: 128 passed, 1 Windows-only deselected.
- [x] Independent frozen CI-packet review; correct selected Git detail/disclosure at 80×24, 120×40 and 60×20 and retest.
- [ ] Record final Linux/Windows CI run URLs, revisions and conclusions separately; local simulation is not native acceptance.

Independent review rejected the initial Git fix as sufficient at ordinary
terminal sizes: moving the notice before the diff still left selected detail
below history/dirty rows. Corrected selected detail precedes history/dirty rows;
actual `render_app` checks cover 80×24, 120×40 and 60×20, history paging,
collapse and preserved commit metadata. Final G7/CI still requires the final
subject; earlier packet hashes are not a final acceptance verdict.

Checks: restart §5 exact selectors; Windows ACL, process guard and frozen
entry checks run through existing Windows CI. Local import simulation is
diagnostic evidence only.

## 3. Complete frozen acceptance and documentation

- [ ] Resolve packet defects; reconcile T1–T29, T28-A–F and inherited Phase 69 findings.
- [x] Record every inherited S01–S16/M01–M21/U01–U11/D01–D03 requirement, code path, existing behavioral selector and empirical gap in current Phase 70 evidence.
- [x] Finish M10 canonical-project filtering for handoff rows; actual 3-failure RED, 93-pass/1-deselected GREEN and independent final frozen packet review recorded.
- [x] U05 corrected actual shared captured-artifact metadata and production JS preview/export boundaries; prior lane passed 228 cases with 1 deselected in 78.95s. Subsequent real EOF race failed one case in 0.40s; same-stream bounded reader correction passed 195 affected cases in 61.67s and independent frozen review.
- [x] Correct older same-run attempt metadata through shared `workflows/projects.py::list_project_artifacts`; preserve reviewed attempt identity, canonical paths and binary bytes. Latest U05 independent frozen review passed; native browser acceptance remains required.
- [ ] Complete U05 native browser two-attempt size/hash/failure/cancel acceptance; Node DOM tests do not close it.
- [ ] Execute all nine native Windows ownership scenarios and console/recovery requirements through existing Windows CI; local S03 104-pass result does not close native cases.
- [x] Extend existing Windows contracts command to select `tests/test_windows_import_safety.py` and `tests/test_dashboard_http_contract.py::test_windows_owner_mutex_wait_results_fail_closed`; same job/runner/triggers/build steps.
- [x] Implement T24 full immutable shared setup review/apply; exact approved version remains frozen after upstream changes; final scan-actions selection: 42 passed in 25.22 seconds.
- [x] Independent T24 frozen review passed on recorded four-file packet; M10/U05 and durable 202/replay/effect reservations retained. Stale-worker fixture lacks an explicit disk-bytes assertion; native/full gates remain required.
- [x] Correct S03 identity-query uncertainty; failed queries retain durable records. Actual 4-failure/3-pass RED, 40-pass subprocess/owned-data GREEN and independent runtime review recorded. Native denial/zero-process cases remain required in existing Windows CI.
- [x] Reproduce public native-plugin hook-disable defect and correct shared path; 2-case RED/GREEN and 87 affected regression passes recorded.
- [x] Correct hook-disable P1 and obtain independent frozen review: explicit shared guidance callback and nonnative interactive prompt retained, native disable-only CLI avoids duplicate registration. Final focused 6 passed; prior affected lane 99 passed before final added nonnative test. Actual host acceptance remains required.
- [x] Correct native hook-only ENABLE/DISABLE public routes: actual four-failure RED, 139 affected passes in 47.96s and independent frozen local review. Broader native connect source correction now has 256 affected passes in 42.55s and independent frozen review; real host cache/G6 acceptance remains required.
- [ ] Freeze source, tests, lock, assets and binary identity before verification.
- [ ] Run full pytest including slow, lint, format, `mypy src/rush`, docs parity, whitespace and dependency audit.
- [ ] Build/probe wheel, sdist and frozen executable using existing release routes.
- [ ] Update every pertinent `docs/` contract, guide, reference, index and evidence claim; rerun affected gates after edits.

Full pytest: `rtk proxy env -u PYTHONPATH TERM=xterm-256color uv run --frozen --python 3.12 --extra dev env -u NO_COLOR python -m pytest tests/ -q -m ""`.
Other exact gates remain restart §5 and amended phase §7. Two identical runs
on unchanged bytes maximum. Source edits invalidate earlier final verdicts.

## 4. Installed and native journeys

- [ ] Rebuild final frozen executable; record version, digest, assets and arbitrary-cwd behavior.
- [ ] Complete isolated install/setup and registered-project setup→scan→agent→rescan.
- [ ] Complete native Claude Code/Codex consent, backup/readback/restoration and model feedback/continuation.
- [ ] Complete local macOS terminal/action/recovery matrix; execute Linux/Windows contract lanes in CI under current owner direction.
- [ ] Run existing Linux/Windows CI on final revision; fill actual URLs, conclusions and revision coverage under applicable authorization.

Native host configuration changes require the documented preview/consent
procedure. No merge, push, release, host mutation, destructive cleanup or commit
is authorized by this checklist itself. Missing native evidence remains unmet.

### G8 installed-terminal acceptance mini-checklist

Implementation uses existing `tests/test_tui_terminal.py` (POSIX),
`tests/test_windows_import_safety.py` (Windows), and existing build-job selections
in `.github/workflows/ci.yml` (coordinator-owned). No new runner, framework,
script or release. Source PTY/reader checks remain separate from added installed
binary journeys. Latest POSIX source lane passed 29 cases in 17.59s; real
orphaned-descendant cleanup regression passed in 0.35s. Native case remains
unexecuted. Extended native case defines distinct
Overview body evidence, explicit platform/TERM/cwd/HOME and actual key receipts,
real pytest scan grant/decline/cancel, config failure/recovery, Unicode/control
paste, independent NO_COLOR/reduced-motion observations and native idle Ctrl-C.
Checksummed extraction, three sizes/eight sections, project/focus switch, Git,
resize, normal quit and terminal/process-group cleanup remain covered by its
assertions. Those new native actions are unexecuted until final rebuilt binary.
Latest POSIX frozen review verified absolute scan gates, SIGINT handling before
native spawn, exact cancellation acknowledgment before gate release and natural
process-group absence before forced cleanup. Paired header-only focus assertions
remain blocked; coordinator is adding a real actions-focus observation. Windows
review verified corrected narrow headers, unique selected root/file and actual
scan/cancel/Job assertions; intermediate focus, explicit CTRL_C_EVENT, typed
CloseHandle and cursor/alternate-buffer proof remain under correction. No Windows
or full native matrix acceptance claimed.
Menu-only smoke cannot close G8.

- [ ] Build final `dist/rush`/`dist/rush.exe` through existing release route;
  launch exact artifact from arbitrary cwd without checkout imports. Record
  executable/version/digest, OS, terminal and isolated fixture identity.
- [ ] Drive real keys and record actual screen/state observations for all eight
  TUI sections and full T28-A–F section/action/state matrix at 80×24, 120×40
  and 60×20. Preserve complete G8 T26 command-count/native CLI, T27 public-route
  and T29 cross-interface journey requirements; section labels do not prove
  their actions, permissions or results.
- [ ] Exercise resize, permitted action/grant/cancel, failure/recovery and quit
  against final binary; verify terminal restoration and durable outcome rather
  than only mocked dispatch or input-reader decoding.
- [ ] Run macOS locally and Linux/Windows via existing CI build jobs; record
  revision, run URL, platform-specific inputs/results and exact blockers.
- [ ] Review frozen installed evidence independently; rerun affected static
  gates after added tests/workflow selection and final full G7 before acceptance.

Native G6 preparation observed authenticated Claude Code 2.1.285 and Codex
0.159.0 plus pre-existing user-owned manual Rush MCP registrations without a
Rush ownership ledger. No host mutation/model call performed by preparation.
Preview exact conversion/instruction/hooks diff and obtain required packet
consent before writes; preserve backups and reviewed-hash CAS restoration,
then verify readback/reload/disconnect. No sensitive identities recorded here.

## 5. Final review and integration boundary

- [ ] Read-only independent review of frozen ledger, file writes, behavior, permissions, recovery, assets and native evidence.
- [ ] Correct every real finding; retest and review changed subject again.
- [ ] Reconcile all completion claims against exact observed evidence.
- [ ] Replace historical handoff only after complete acceptance; preserve historical receipts.
- [ ] Integrate only with explicit applicable authorization; preserve primary user-owned bytes and downstream plans.

## Execution observations

2026-10-03: Phase 70 began clean. Primary has existing user-owned tracked and
untracked documents; preserved. Disk initially 3.6 GiB free; later independent
read and coordinator `df -k` showed 17,143,344 KiB available (16.35 GiB), above
8 GiB prerequisite. This execution performed no disk cleanup.

Targeted CI checks passed in 1.79 seconds; terminal/dashboard/helper lane passed
in 33.93 seconds with `TERM=xterm-256color` and inherited `NO_COLOR` cleared
after `uv run`. Initial PTY failures came from `TERM=dumb` and `NO_COLOR=1`,
not a terminal implementation defect. ANSI-regex suspicion disproved with an
actual ESC sample; `tests/test_tui_terminal.py` unchanged.

Scope correction from frozen acceptance review: historical evidence's assignment
of shared dashboard frozen provisioning to Phase 71 was not owner approval.
Amended Phase 70 plan §8.1 retains shared setup/readiness contracts. Keep T24
reviewed version/digest binding in Phase 70; Phase 71 owns prototype integration.

Current gate checkpoint: full frozen G7 baseline recorded 6,345 passed,
4 failed, 2 deselected in 1,503.64s with 1,482 subject hashes unchanged.
The four failed selectors now pass in 9.89s after Git loading visibility and
lock corrections; this is targeted verification, not full G7 PASS. Dependency
audit passed after PyJWT 2.15/urllib3 2.8 update and reuse-expiry/options check
passed. Final source/lock/docs edits require final frozen full gates.

M10 latest correction has 93 passes/1 deselected in 27.11s after actual
3-failure RED; canonical handoff UUID filtering now independently reviewed.
S03 earlier correction had 104 local passes with one Windows ACL case
deselected; subsequent mutex observer access-mask correction passed five local
cases in 0.34s and independent frozen review. Nine native ownership
cases remain unmet. T24 actual frozen-review HTTP assertion reproduced
`resolved_at_apply` failure; correction passed 42 scan-actions cases in 25.22s
and independent four-file frozen review. Full acceptance remains unmet.

Subsequent S03 observer-rights frozen packet passed independent read-only
review at state SHA-256 `e87c314dfdd95fab6bd8588e3f301ae918deecfb7035206112fd2d9926eae1c0`.
Prepared native module locally passed two import checks; eleven Windows-only cases
were deselected. Existing Windows lane now selects the native module and
mutex wait-results selector; actual native execution remains required.

CI-selection reconciliation now complete: one existing Windows-command line
includes `tests/test_windows_import_safety.py` and exact mutex wait-results
selector above. Actual execution on new CI head remains pending. Final owned
documentation check is bounded to this checkpoint; final source acceptance remains open.
U05 actual production-JS RED was 12 failed/4 passed; GREEN was 16 focused
passes and full module 48 passes. Native browser acceptance remains unmet.

G5 macOS artifact probes passed on older lock; preserved artifacts:
`/tmp/rush-phase70-g5.AVQbMy`. Lock upgrade invalidates final provenance;
rebuild wheel, sdist and frozen executable before final installed probes.
Root corrected USER_GUIDE, CLI_REFERENCE and CLI_COOKBOOK non-TTY behavior,
ARCHITECTURE historical M12/current U05 status, and phase-index evidence claim.
Targeted receipt refreshed for all 13 changed documents; current documentation
checker and owned-path whitespace check passed. Later source/docs edits require
final documentation gate again; no final G7 or phase acceptance claimed.

Required static G7 subset passed once on 1,485 frozen files, Python 3.12.12:
Ruff check; Ruff format (938 files); mypy (474 source files); docs/runtime
parity; whitespace. Manifest `/tmp/phase70-g7-static-frozen.json`, SHA-256
`bfb6964df69f271c66216f37fee57eae46f497ae7c58db0088046cb8bc0227b7`;
before/after path sets and hashes unchanged. Commands used `--frozen --no-sync`
and cleared `PYTHONPATH`. This is static evidence, not full G7/native PASS.
This documentation update and upcoming installed-terminal test/workflow
corrections invalidate affected gates; refreeze and rerun before final verdict.

Two later full G7 attempts stopped on stale test fixtures, so final full G7
remains open: first used `-q -m ""`; root sent SIGINT after the observed old-CI-
command failure (exit 2; 739 passed, one failed, 14 deselected; 120.72s), then
four focused cases and frozen peer review passed. Second used `-x` and stopped
naturally at the journey-telemetry failure (exit 1; 952 passed, one failed,
14 deselected; 183.29s): telemetry lacked the registered project ID. Corrected real journey now
passes 15 focused cases and asserts scoped HTTP totals of 100 raw, 40 sent,
60 saved, one event, excluding foreign/unscoped rows. Production telemetry
and dashboard project scoping remain unchanged. Rerun final integrated G7.

## Next required packets

1. Carry corrected hook packet into final integrated acceptance: explicit shared
   callback, native disable-only public CLI and nonnative interactive prompt
   passed focused checks and frozen review; actual Claude Code/Codex behavior
   still requires final artifact and consent. Native hook-only ENABLE/DISABLE
   correction passed 139 affected cases in 47.96s and independent local review.
   Broader native connect profile/guidance/memory duplication is a separate
   required shared correction; this result does not close G6.
2. Finish corrected Windows installed-console packet review and existing
   Windows CI execution. Identity-query
   correction reproduced 4 failures/3 passes, then passed 40 subprocess/owned-data
   cases in 8.45s and independent frozen runtime review. Native module includes
   real DACL denial and zero-process query; local 2 passes/11 deselections do
   not prove Windows behavior or close nine ownership/U01 console scenarios.
3. Freeze final integrated source/tests/lock/assets; rerun full G7 and docs,
   rebuild G5 artifacts, then record existing Linux/Windows CI revision/URLs.
4. Complete Claude Code/Codex preview/consent, real-model hook and continuation
   journeys against final artifact; verify backups, readback and restoration.
   G6/G8 and production Aislop attribution remain unresolved.

## Integrated packet checkpoint — 2026-10-03

Compact header correction reproduced 16 failures in 1.25s, then passed all
16 cases in 0.90s and the full EF/TUI lane: 72 passed in 25.27s. Independent
frozen review passed at source `e1d7c91ff0e82f00121261809b4ff48a7c68282005fad56c22763c0752486f55`
and test `6022e667f5367266d2a04e01d60904808459a4308eece85a80ed49d7f258b556`.
At 60×20 section/size and project index precede long names; wider header text
and literal-text safety remain unchanged. This is source-render evidence.

POSIX source lane latest passed 29 cases in 17.59s with `TERM=xterm-256color` and
`NO_COLOR` cleared after `uv run`. Reviewed native/helper test frozen hash:
`e2da1b0dfb23ad9bbccadd700afcdc8391ccdc9b67bd5c314300d14725b6ddd7`.
Independent review verified corrected cancellation/signal/cleanup assertions,
but paired focus observations remain blocked. Native assertions are unexecuted.
Old G5 archive debugging exposed the missing 60×20 section label; it predates
final lock/header fixes and cannot establish final native acceptance.

Existing CI jobs now pass archive/checksum/receipt environment variables to
native tests and require valid `posix-installed-tui.json` or
`windows-installed-tui.json`. Independent frozen workflow review passed at
`66097aae80bf25f051c954c094711478dc443f3caada47f669d554d449547761`;
Linux sets TERM and clears PYTHONPATH/NO_COLOR after uv, retains receipt-directory
creation; PowerShell preserves pytest exit code. Both log parsed receipt JSON.
No new job, build, trigger or runner. Review was static, without a YAML parser;
actual CI remains pending and no receipt artifact upload is configured.

U05 latest implementation freezes preview identity/content, decodes encoded
artifact references once, verifies response digest with WebCrypto, preserves
`grant_denied`, and guards concurrent submit/cancel. Latest 228-pass lane and
3-pass naming check are prior local evidence. Subsequent actual EOF-race RED
failed one case in 0.40s; captured bytes now use one stream's retained bounded
page plus digest, with explicit EOF/short-read/size/digest guards. Latest 195
affected cases passed in 61.67s, mypy 474 files and Ruff check/format passed;
independent final frozen review passed. Native browser acceptance remains open.

Earlier 2–4-hour estimate is superseded. No defensible ETA while source
corrections and native acceptance remain unresolved. Observed full-suite
runtime of approximately 25 minutes measures that run only. Final G5/G6/G7/G8,
full action/state matrix, actual CI and production Aislop attribution remain
open. Refreeze after documentation changes before final integrated gates.

### Native shared-connect checkpoint — 2026-10-03

Shared native connect now selects owned plugin evidence before manual
registration; ordinary/guidance/resources/memory/ack/profile requests preserve
host configuration. Missing, mutated or ambiguous evidence conflicts. Profile
migration retains preview/consent/CAS, projected root digests and journaled
compensation; omitted profile preserves full/extras. Memory rollback uses own
serialized write digest, retaining concurrent edits. Native guidance CAS races
and unowned resources produced four RED failures in 0.39s, then four GREEN
passes in 0.24s with rollback and no host refresh. Eight affected modules passed
256 tests in 42.55s; Ruff, format, whitespace and agents-module mypy passed.
Independent frozen review passed on all four unchanged subjects. Actual same-version host cache adoption,
host/model continuation and G6 remain unexecuted.

Historical POSIX `b198…` / Windows `c0f24…` independent read-only review passed
the five identified focus/signal/WinAPI/restoration corrections as source
evidence only. New local Memory/artifact native cases are being added; these
edits invalidate final-candidate verdicts and require new frozen review and
final installed-binary execution.

### T28-D local Memory acceptance mini-checklist

- [x] Locally render selected record's real decoded content and page through it;
  verify selected ID/version and bounded pages, including related-record
  traversal, rather than a JSON excerpt or menu label.
- [x] Locally verify read-only access leaves database/files unchanged and exposes
  actual per-record write/use receipts through existing shared readers.
- [x] Locally exercise preview, exact grants, decline/apply and stale-version failure
  through shared memory mutation routes; preserve original/concurrent bytes
  and truthful recovery outcomes.
- [x] Locally promote genuinely corroborated selected evidence through canonical
  promotion gate; positive, single-source denial and stale-source checks pass.
- [ ] Freeze corrected source/tests, obtain independent review, then execute
  final installed-native Memory/artifact journeys. These local lanes do not
  depend on G6; full Phase 70 matrix and later phases remain required.

### Current installed acceptance mini-checklist — 2026-10-04

- [x] Repair and independently review actual native refresh/cancellation,
  Memory pagination, literal checkbox and stale owner-status defects.
- [x] Rebuild native dashboard data; verify clean artifact probes and exact
  HTTP asset bytes. This does not close the native/browser journeys.
- [ ] Repair mobile inspector scrolling; verify actual accessible export
  controls and downloaded immutable bytes for both attempts.
- [ ] Pass strict final native journeys at all three terminal sizes, then
  freeze integrated documentation/source and execute full G7/current CI.
- [ ] Complete remaining host, browser and dependency acceptance; reconcile
  all required gates before proceeding to later restart-plan phases.

Latest installed native run failed at owner-scope acknowledgment after
35.29 seconds. Its source correction passed 94 focused/adjacent cases and
independent review; rebuilt native acceptance remains required. Browser
export still lacks downloaded-byte proof. Earlier 2–4-hour estimate remains
withdrawn; no supported completion date exists while these gates are open.

Next native archive passed the owner acknowledgment step, then failed at
Memory expansion after 39.06 seconds: frozen `tiktoken` discovers no encoding
plugin. Correct existing package collection before another native attempt.
Mobile scrolling is now exercised successfully; export UI reports complete
byte count, but downloaded-file digest remains unverified. Full native,
browser, G7 and current CI gates remain open.

Tokenizer is now collected into the rebuilt native executable; actual
Memory expansion passed with the real verified existing encoding cache.
The next native failure is held-ID refresh after a genuine external edit
and correctly rejected stale write: active search excludes the new content.
Repair refresh without changing owner checks, typed draft or CAS re-review.

Current bounded checklist (2026-10-04):

- [x] Fix held-ID conflict refresh; native edit/re-review/archive/create exercised.
- [x] Fix actual terminal-page end without changing continuation control;
  native exact final-page bytes, markers and cached navigation exercised.
- [x] Rebuild final-page archive once; existing G5 and exact HTTP asset probes pass.
- [ ] Wait for actual maintenance apply completion, retain exact persisted
  stale/expired checks and finish all three native terminal sizes.
- [ ] Verify actual saved browser exports, then finish remaining browser,
  host, G7/current CI and documentation gates. Later phases remain required.

Archive SHA-256: `993a5a1a137f2373d8f5bb427666da66a7ce401d50f50df92f30914e0ae114e8`.
Latest native run passed exact paged content but its maintenance check ran
before async apply finished; no full native pass is asserted. Chrome shows
the complete captured export byte count; saved-file hash remains unverified.

### Current bounded acceptance step — 2026-10-04

- [x] Actual maintenance completion and source-change assertions corrected.
- [x] Compact Artifacts details and narrow footer corrected; focused tests and frozen review passed.
- [x] Current installed native journeys passed at 80×24 and 120×40.
- [ ] Finish 60×20 using exact selected-record identity for the clipped skill ID; freeze documents and run full G7/current CI.
- [ ] Apply the evidence report's real-home G6 packet only after its required consent; complete browser hashes, remaining hosts and every open release gate before later phases.

Current archive SHA-256:
`10947f5b5d11d4adf4dd2f7e734d590d72aea38721c3e96e4e45a5043812c36b`.
Latest strict run: 79.80 seconds; no all-three-size PASS is claimed.

### Superseding current task — owner correction 2026-10-04

- [x] Check exact Phase 71 plan; preserve all UI work/requirements and stop UI execution.
- [x] Record additive ownership amendments in Phase 70, Phase 71 and restart plans.
- [x] Pass frozen-source Ruff check/format and mypy; preserve interrupted G7 evidence without claiming PASS.
- [x] Correct production attribution; frozen review and regression passed. Candidate `8341cd8` passed five engine/artifact CI jobs; full CI failed on recorded Windows prerequisite and transferred UI checks.
- [ ] Windows denial correction cleared in current CI's 57 passes; finish skipped backend gates and remaining CI conclusions; no local full suite/build.
- [ ] Current macOS artifact passed CI and local native probe with matching source/checksum; refreshed real-host packet still requires consent and actual acceptance.
- [ ] Close retained Phase 70 gates before Phase 71; transferred UI checks remain required there.

This section supersedes earlier checklist sequencing that kept UI acceptance
in Phase 70. It does not claim either phase complete.

### Superseding native/backend checklist — 2026-10-04

- [x] Complete approved macOS CI extension and actual checksum-bound native origin/MCP probe at `8fd5f99`; all five backend gates executed and passed in CI `37235554376`.
- [x] Exercise actual Claude native skill/seven core schemas, denied/granted fixture test, native fault edit, received F401 hook feedback and repair; receipt does not close the full host journey.
- [ ] Freeze reviewed hook-startup deadline and setup-probe engine-scope repairs; run fresh CI and rebuilt cold-native timeout acceptance. Existing focused source regressions passed.
- [ ] Finish actual Codex MCP pickup and both hosts' status/timeout/disable/restoration observations; approved real-home consent remains valid, with no repeated consent gate.
- [ ] Reconcile all retained Phase 70 evidence and pertinent documentation, complete final frozen review and authorized commit/push. Phase 71 UI failures remain required in Phase 71.

This checkpoint supersedes earlier pending-consent/CI statements without
closing unexecuted native acceptance or claiming Phase 70 completion.
