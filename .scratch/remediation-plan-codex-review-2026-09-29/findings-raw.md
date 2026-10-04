**NOT_READY.** Review stayed read-only; disposable fixtures deleted. Plan SHA256 unchanged: `539955cf9a183d05800771fbb9e40e885a300879ccde6cfbd5baab890f815a62`.

Paths below: `plan` = document under review; `skill` = `~/.claude/skills/orchestrator`; `wt` = `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70`; `x` = supplied scratchpad directory.

## Finding 1 [critical]
Section: 4.D2, 4.J21, 8.X9  
Defect: Automatic disk cleanup deletes directories without establishing ownership or inactivity, including protected evidence.  
Failure scenario: Running process keeps writing inside an old `tmp*/keep/` directory → cleanup deletes its files because parent-directory mtime remains old.  
Evidence: `plan:1820-1824` checks only name, age and size. Disposable fixture containing recently updated `tmp-active/keep/evidence.txt` was deleted. No `keep/` exclusion exists.  
Suggested change: Replace this cleanup specification with deletion of explicitly registered, completed run-owned directories only; require inactive ownership evidence, exclude `keep/` descendants, and add `-mindepth 1`. Acceptance must retain active directories and evidence, not merely fresh directories.

## Finding 2 [critical]
Section: 4.T5, 8.X11  
Defect: Global pytest basetemp is protected by a worktree-local lock.  
Failure scenario: Two worktrees run their gates → both acquire separate locks → second pytest deletes `/tmp/rush-gate-bt` while first suite uses it.  
Evidence: `plan:1991` fixes basetemp globally; `plan:2005-2012` places lock under each run. Installed pytest `_pytest/tmpdir.py:149-153` removes an existing explicit basetemp before using it.  
Suggested change: Specify one shared suite lock across participating worktrees and a unique gate-owned basetemp per invocation. Verify two different run directories cannot enter their suites concurrently.

## Finding 3 [major]
Section: 4.A4, 8.X4, 8.X10  
Defect: Budget removal leaves executable references and callers behind.  
Failure scenario: Updated generator without `--budget` → `budget: unbound variable`; existing documented commands → `unknown argument: --budget`.  
Evidence: Live `skill/scripts/dispatch-prompt.sh:123` evaluates `handoff=$((budget * 9 / 10))`. Disposable patch reproduced both failures. Remaining callers include `SKILL.md:89`, `references/dispatch.md:15,26,38,69,80,94,168`, and `tests/test-dispatch-prompt.sh`.  
Suggested change: Make budget removal one atomic patch covering arithmetic, all invocations, generated sections, tests and persisted `agents.active` schema. Replace removed-budget assertions with turn-limit assertions.

## Finding 4 [major]
Section: 4.B1, 4.H11, 8.X10  
Defect: Retained dispatch instructions do not satisfy model-guard rule 7.  
Failure scenario: Send generator output unchanged as instructed → guard rejects it because prompt does not reference a saved, signed prompt file.  
Evidence: `skill/SKILL.md:91` requires unchanged output. `~/.claude/hooks/orchestrator-model-guard.js:85-99` searches referenced files and hashes their contents. Replay of generated scout output returned `permissionDecision: deny`.  
Suggested change: Replace dispatch instructions with an exact save-and-reference procedure: save unchanged generator output under `$WT/.orchestrator/`, then reference that absolute file in Agent input. Add an integration fixture invoking actual rule 7.

## Finding 5 [major]
Section: 4.B4, 8.X10  
Defect: Packet factory assigns file creation to a read-only scout.  
Failure scenario: Scout receives instruction to write `.orchestrator/maps/...` → its definition forbids writes and lacks Write/Edit.  
Evidence: `plan:1930-1933`; `~/.claude/agents/orch-scout.md:4,34`. X5 adds search tools but no writing capability. Generator also clears scout write targets at `dispatch-prompt.sh:118-120`.  
Suggested change: Choose one explicit contract: scout returns map content for orchestrator to persist, or scout gains narrowly scoped map-writing permission. Update definition, generator and acceptance probe together. Exempt seed scout dispatches from any scout-produced-map prerequisite.

## Finding 6 [major]
Section: 4.F2, 8.X10  
Defect: Tests-first dispatch still requires a RED log before tests exist.  
Failure scenario: Dispatch implementer to author initial test matrix → generator requires `--red-log` produced by those unwritten tests.  
Evidence: `skill/SKILL.md:242-244`; `skill/scripts/dispatch-prompt.sh:96-112`. Proposed edits retain unconditional RED-log requirement for implementers.  
Suggested change: Define separate test-authoring mode with test-only write targets and no prior RED-log requirement. Implementation mode must require successful acceptance of that mode’s RED results.

## Finding 7 [major]
Section: 4.B4, 4.B6, 8.X4  
Defect: Exact generator edits omit promised `scout:` and `done:` enforcement.  
Failure scenario: Map lacks both fields → proposed generator still emits a dispatch without provenance or completion checklist.  
Evidence: B4 requires rejection at `plan:725`; B6 requires parsing, rejection, checklist and receipt at `plan:741-743`. None appears in X4’s six edits or X11’s additional generator check.  
Suggested change: Add exact parser, validation and rendering changes for both fields, plus missing-field fixtures. Define bootstrap exemptions explicitly rather than making scouts recursively require scouts.

## Finding 8 [major]
Section: 4.I1, 4.I3  
Defect: Replacing multiple task-loop steps with committing `task-gate.sh` changes lifecycle ordering and makes repeated steps fail.  
Failure scenario: Step 2 commits before review; step 3 invokes gate again → `no changes in the worktree`; later docs edits occur after initial commit.  
Evidence: `plan:348` replaces steps 2, 3, 7 and 8. Script commits at `plan:383` and rejects clean trees at `367`. Existing review and docs occur at `skill/SKILL.md:256-266`.  
Suggested change: Keep one committing invocation at final task-loop step 8, after review and docs. Earlier verification must not commit. Amend I3 to merge only after this final invocation.

## Finding 9 [major]
Section: 4.D2, 4.F2, 8.X9, 8.X11  
Defect: Shared-environment proposal conflicts with commands requiring a worktree-local environment.  
Failure scenario: `worktree-add.sh` creates no `.venv` → F2’s `$WT/.venv/bin/python` is missing; gate’s `uv run` can create the environment the proposal forbids.  
Evidence: `plan:1834-1845`, `909-910`, `1991`; retained generator instruction at `skill/scripts/dispatch-prompt.sh:201`.  
Suggested change: Resolve and record one absolute interpreter path at run start. Use that interpreter consistently for task tests, acceptance and gates, with imports explicitly targeting each worktree. Replace every `$WT/.venv` instruction.

## Finding 10 [major]
Section: 4.F1, 4.I3, 8.X11  
Defect: Task completion requires remote CI for a commit the workflow forbids pushing.  
Failure scenario: Local task commit or `--no-ff` merge produces new SHA → no remote CI exists → `task merged` refuses → dependent nodes remain blocked.  
Evidence: `plan:405` says “Never push”; `plan:2121-2124` requires CI success for current HEAD.  
Suggested change: Separate local integration state from remote CI state, or specify an explicitly authorized push route before the CI-dependent transition. Define which SHA and required workflow set each transition validates.

## Finding 11 [major]
Section: 4.T4, 4.T8, 8.X8, 8.X11  
Defect: CI changes omit both locked dependency integration and authorization for large collections.  
Failure scenario: CI uses frozen lock without xdist → `-n` unavailable; after installing xdist, large collection exits 4 because `RUSH_GATE` remains unset.  
Evidence: `wt/uv.lock` contains no `pytest-xdist`; `.github/workflows/ci.yml:31` uses `uv sync --all-extras --frozen`; primary pytest step at `:91` has no `RUSH_GATE`. X8 introduces collection refusal.  
Suggested change: Include `uv.lock` and exact CI changes in file map. Specify how CI obtains suite authorization independently of a local user-installed skill. Test frozen installation and CI collection together.

## Finding 12 [major]
Section: 4.C1, 4.D1, 8.X1, 8.X11  
Defect: Proposed task graph cannot represent prescribed split and parked workflows consistently.  
Failure scenario: Add `T28.a`/`T28.b` → startup’s row-count equality fails; retain parent T28 → dependents have no specified aggregate completion transition; park a grant → command unsupported.  
Evidence: `plan:777,831,2106-2108`; live `skill/scripts/run-state.sh:103-125` supports only `add`, `start`, `merged`.  
Suggested change: Define parent/child completion semantics and implement `parked` transition. Validate required parent IDs rather than total row count. Update readiness and monitor consumers to the same schema.

## Finding 13 [major]
Section: 4.H1, 4.C1, 8.X1, 8.X10  
Defect: Loading the plan overwrites existing progress with `pending`.  
Failure scenario: Resume existing Phase 70 run → loader truncates `tasks.tsv` and resets completed/running nodes → completed work is redispatched.  
Evidence: `plan:1146-1148` opens output with `"w"` and assigns every node `pending`; X10 invokes loader at intake. Existing `wt/.orchestrator/run.json` remains present.  
Suggested change: Separate initial graph creation from resume reconciliation. Preserve verified task states; reject destructive reloads of existing state. Specify migration of current Phase 70 state before restarting dispatch.

## Finding 14 [major]
Section: 4.H1, 4.C3, 8.X10  
Defect: Mandatory parallel dispatch preserves a shared-file policy contradicting the actual Phase 70 plan.  
Failure scenario: Two ready chain heads touch shared CLI/catalog files → skill permits concurrent writers in separate worktrees despite plan’s explicit prohibition.  
Evidence: `skill/SKILL.md:230`: “Shared files are no reason to serialize across worktrees.” Phase 70 plan `:112` requires one writer for named shared files and forbids parallel shared-file edits.  
Suggested change: Replace that sentence with the approved ownership constraint. Readiness must include file reservations, not dependency status alone; release reservations only after integration.

## Finding 15 [major]
Section: 4.A2, 5.D1, 8.X4, 8.X5, 8.X10  
Defect: Model/effort policy has contradictory matrices and no binding between checked map and actual dispatch.  
Failure scenario: D1 calls for Sonnet/medium scout; X5 installs Haiku without effort; design gate requests medium/80 turns but adversarial definition applies high/240.  
Evidence: `plan:1013`, `1387-1394`, `1455-1462`, `1917-1923`. Model guard validates allowed models, not correspondence with `model-reason:`.  
Suggested change: Select one canonical matrix after D1 resolution and derive every table/config from it. Specify separate design-gate configuration or supported per-dispatch overrides. Bind selected model and justification to actual Agent input.

## Finding 16 [major]
Section: 4.T2, 8.X8  
Defect: Five-second throttle suppresses process-listing failures after first teardown.  
Failure scenario: First test succeeds; process probe breaks during second test inside cooldown → suite reports success.  
Evidence: Disposable execution using actual conftest: original produced `2 passed, 1 error`; X8 produced `2 passed`. Existing contract is pinned by `wt/tests/test_real_home_guard.py:723-794`.  
Suggested change: Remove claim that behavior remains unchanged. Add the two-test regression before choosing an optimization; preserve explicit probe-failure reporting or obtain an explicit contract change.

## Finding 17 [major]
Section: 4.T5, 5.D7, 8.X11  
Defect: Retention setting does not delete the explicitly configured gate basetemp.  
Failure scenario: Passing gate with `--basetemp=... -o tmp_path_retention_count=0` → factory directories remain.  
Evidence: Installed `_pytest/tmpdir.py:304-317` excludes explicit basetemps from passing-session cleanup. Fixture passed while `explicit/engine0/evidence` remained.  
Suggested change: Add explicit cleanup of the uniquely owned gate basetemp after preserving required logs; implement D7’s chosen failure-retention policy there. Verify filesystem state after both pass and failure.

## Finding 18 [major]
Section: 4.T4  
Defect: npm cache is incorrectly presented as caching all expensive session fixtures across workers.  
Failure scenario: `loadfile` assigns archive consumers to different workers → each invokes its own PyInstaller build despite T3.  
Evidence: `wt/tests/conftest.py:859` creates fresh `pyinstaller` and release directories. Consumers exist in `test_release_asset_contract.py`, `test_phase70_ts.py`, and `test_phase52_installed_artifacts.py`. T3 changes only npm cache.  
Suggested change: Correct claim at `plan:960`; specify worker count consistently (`4` versus `auto`) and validate expensive fixture multiplicity. If sharing builds is required, define artifact production and ownership explicitly.

## Finding 19 [major]
Section: 4.A5, 4.H14, 8.X11  
Defect: Agent probe can pass missing results and does not exercise installed agents under real controls.  
Failure scenario: First agent emits no statuses; second emits three `ok` lines → parser credits both and writes `"ok": true`.  
Evidence: Exact proposed parser reproduced that result. `plan:2287-2288` constructs replacement probe agents; `2300` disables hooks; effort, `maxTurns`, `omitClaudeMd` and real agent bodies are omitted.  
Suggested change: Bound parsing to each agent’s record and fail on missing results. Probe actual installed definitions with effective hooks and settings; associate observed model/tool calls with each agent separately.

## Finding 20 [major]
Section: 4.D1, 8.X7  
Defect: Ask guard still permits blocking questions and treats failed decision lookup as a miss.  
Failure scenario: Question begins `decision-search: zzznomatch` → approved; missing `decisions.sh` also → approved.  
Evidence: `plan:1662-1668` ignores subprocess status and approves empty output. Disposable missing-script fixture returned `{"decision":"approve"}`.  
Suggested change: Enforce the stated rule directly: active-run questions require explicit user unlock. Treat lookup errors as errors, not absent decisions. Specify handoff handling for parked grants.

## Finding 21 [major]
Section: 8.X7, 8.X11  
Defect: New hooks apply to unrelated sessions whenever global active-run marker exists.  
Failure scenario: Phase 70 active elsewhere; unrelated session asks a legitimate question → hooks block it.  
Evidence: `plan:1624-1627` reads global marker; hook bodies test only its existence, without matching session, cwd or valid run state.  
Suggested change: Bind marker to run and session identity; validate `run.json` and scope before enforcing. Add unrelated-session and stale-marker fixtures.

## Finding 22 [major]
Section: 5.D4, 8.X7, 8.X11  
Defect: Unlock reader mistakes hook feedback for the latest human message.  
Failure scenario: User sends `ask`; another Stop hook emits feedback → proposed question hook no longer recognizes unlock.  
Evidence: `plan:1628-1636` accepts ordinary `type:"user"` text except four XML prefixes. Replay of `ask` followed by `Stop hook feedback: ...` remained blocked.  
Suggested change: Use one verified human-message classifier across hooks, excluding hook feedback and synthetic messages. Make exact-token versus “contains word” unlock semantics consistent throughout sections 4, 5 and 8.

## Finding 23 [major]
Section: 4.C4, 8.X7  
Defect: Resume guard blocks ordinary communication to every agent type, not repeated implementer continuations.  
Failure scenario: Reviewer receives clarification, then user corrects scope → second correction is denied.  
Evidence: `plan:1691-1701` counts all `SendMessage` calls by recipient; no role, purpose or completion check. Reviewer-correction fixture was blocked.  
Suggested change: Enforce continuation limit on completed implementers using recorded lifecycle state. Exempt required scope corrections and coordination messages; count completed sends rather than ambiguous transcript occurrences.

## Finding 24 [major]
Section: 4.C5, 4.H6, 4.E4, 8.X11  
Defect: TaskStop hook disagrees with monitor’s completion definition and permits stopping running shell suites.  
Failure scenario: Completed agent ends with `end_turn` → blocked; running suite has shell-task ID without agent transcript → approved.  
Evidence: `plan:2202-2205`; both outcomes reproduced. E4 explicitly defines completion through `end_turn`, while hook requires `SubagentStop`.  
Suggested change: Share one completion classifier between monitor and hook. Resolve shell-task lifecycle before allowing stops; missing agent transcript must not constitute proof that a test may be terminated.

## Finding 25 [major]
Section: 4.E4, 8.X6, 8.X11  
Defect: Monitor remains one-shot on alerts, permanently suppresses recurring conditions, and allocates exit code 10 twice.  
Failure scenario: First idle alert exits monitor; after restart, a later low-capacity or slow-suite event with same key is suppressed forever.  
Evidence: `skill/scripts/monitor.py:291-293,343-345,367-372`; E4 assigns `DONE:10`, X6 assigns `READY-LOW:10`. Neither changes loop or recurrence semantics.  
Suggested change: Define one alert registry, continuous monitoring lifecycle, and episode-based reset/rearming. Add a fixture covering trigger → recovery → second trigger, plus production-mode exit behavior.

## Finding 26 [major]
Section: 4.H3, 4.E1, 4.E4  
Defect: Expanded raw-read detector flags the read/Edit workflow the plan mandates.  
Failure scenario: Agent performs ten bounded `rtk read ... --max-lines 20` followed by Edit → TOOLSTACK warning despite compliance.  
Evidence: Exact `monitor-copy.py` fixture returned `TOOLSTACK required: 10 raw reads vs 0 graft/ctx/repowise calls`. Proposed regex ignores read limits and following Edit.  
Suggested change: Exclude bounded edit-preparation reads from raw-read violations. Test compliant read/Edit pairs separately from whole-file exploration.

## Finding 27 [major]
Section: 4.F2  
Defect: Assertion-prefix classification neither verifies the stated RED reason nor accepts every legitimate assertion mechanism.  
Failure scenario: `assert 1 == 2` unrelated to feature passes; missing expected exception under `pytest.raises(ValueError)` is rejected as an error.  
Evidence: Replayed `test-acceptance-copy.py`: assertion-only case returned `ok`; missing-exception case returned `errored (not an assertion failure)`. Existing AST check accepts `pytest.raises` at `test-acceptance.py:42-44`.  
Suggested change: Map each required RED result to its expected failure signature/location, including supported `pytest.raises` failures. Add wrong-reason assertions and missing-exception fixtures.

## Finding 28 [major]
Section: 4.E3, 4.H17, 8.X3  
Defect: Status implementation does not deliver promised live, changed-only status.  
Failure scenario: Finished agents remain registered → report labels them “running”; documented `status --report` invokes old status branch instead.  
Evidence: X3 adds `report)` at `plan:1361`, counts lines at `1365`, and never reads agent transcripts. Live `run-state.sh:128-136` ignores `--report` and prints full state/log.  
Suggested change: Standardize one command interface, distinguish registered/running/finished agents using live evidence, and implement the claimed changed-only behavior. Remove claims for fields the command does not produce.

## Finding 29 [major]
Section: 4.A6, 4.T6, 8.X2, 8.X11  
Defect: Usage and performance reporting remain disconnected from execution.  
Failure scenario: Commit completes → no usage report or COST alert; suite timing row lacks phase totals and ten heaviest items.  
Evidence: X2 prints reports but never writes `usage.tsv`; X3/X11 do not change `log)` to invoke it. X11 records only five columns at `plan:2029`; monitor has no COST integration.  
Suggested change: Add exact call sites and output schemas for commit-time usage, current-day threshold evaluation and suite details. Verify a real fixture commit appends expected records and triggers the threshold path.

## Finding 30 [major]
Section: 4.J2, 4.J5, 4.J7, 4.J9  
Defect: Document checker treats backticks as proof of a concrete fix and passes nonexistent input.  
Failure scenario: `**Fix.** Think about \`does-not-exist.sh\`.` → PASS; missing document → PASS.  
Evidence: Replayed checker produced `DOC-DONE-CHECK PASS 1 entries` and `DOC-DONE-CHECK PASS  entries`. `x/doc-done-check.sh:13` checks only for a backtick; pipelines do not propagate read failure.  
Suggested change: Require readable input and propagate command failures. Relabel existing checker as structural lint; add substantive artifact/verification review before allowing completion claims.

## Finding 31 [major]
Section: 4.J22  
Defect: Coverage checker equates mentioning a filename with opening and reviewing it.  
Failure scenario: Document names `monitor.py` without inspection → checker marks NAMED and procedure skips opening it.  
Evidence: `x/skill-coverage.sh:12-13` performs basename substring matching; user-level and repo-level copies share basenames.  
Suggested change: Replace NAMED/UNNAMED as review coverage with exact-path, source-hash and reviewed-span records. Keep filename inventory only as inventory.

## Finding 32 [major]
Section: 4.H5, 4.H13, 4.H16, 4.J1, 4.J6, 4.J14, 4.J15, 4.G2  
Defect: Several behavior fixes remain reminders without the promised execution check.  
Failure scenario: Assistant omits requirement row, writes unrequested memory, repeats analysis, or supplies unchecked estimate → proposed mechanisms do not reject action.  
Evidence: These entries prescribe procedures; `skill-lint.py` at `plan:1872-1874` checks only whether a tagged path exists. A tag cannot establish that artifact enforces the associated rule.  
Suggested change: Give each named entry an exact enforcement point, input/state contract and negative fixture. Where semantic review is required, specify it explicitly and stop claiming file-existence lint supplies enforcement.

## Finding 33 [major]
Section: 4.J4, 4.J8, 4.J10, 4.J12, 4.J16, 4.J18, 4.J19, 4.J22; 5.D4  
Defect: Eight proposed behavior hooks lack an installation/activation path in decisions and exact edits.  
Failure scenario: Apply all X7/X11 registrations → none of these J-series hooks runs.  
Evidence: D4 lists four hooks; X11 registers only those four. J-series hooks are absent from current hook directory and have no registration additions. Five supporting behavior scripts exist only in supplied scratchpad.  
Suggested change: Add explicit install destinations, registrations, approval status and acceptance fixtures for J-series mechanisms. Preserve these as proposed work; do not treat applying D4 as completing them.

## Finding 34 [major]
Section: 4.J4, 4.J10, 4.J12, 4.J22  
Defect: Proposed keyword triggers confuse prohibitions, successful status and genuine unfinished work.  
Failure scenario: “Do not remove anything” unlocks shrink guard; “remaining: 0” blocks completion; “I have not opened unrelated Codex sessions” blocks correct scope observance.  
Evidence: Trigger/unlock specifications at `plan:451,499,515,595` contain no negation, target, quantity or scope handling.  
Suggested change: Replace bare keyword unlocks with explicit action-and-target authorization. Base incomplete-work detection on unresolved ledger state; include these exact counterexamples in negative fixtures.

## Finding 35 [major]
Section: 4.B7  
Defect: Reviewer replacement weakens caller review to changes that a call trace itself reveals.  
Failure scenario: Function keeps same signature but changes return semantics → unchanged call edge provides no trigger to inspect affected callers.  
Evidence: `plan:761` opens callers only when trace shows changed signature or contract; current `~/.claude/agents/orch-reviewer.md:27-28` requires reviewing callers for correctness.  
Suggested change: Replace sentence with: “Trace every changed symbol; inspect affected caller spans whenever its behavior or contract changes, including unchanged signatures.” Preserve semantic caller review while bounding source reads.

## Finding 36 [major]
Section: 4.T7  
Defect: Proposed remedy risks removing user-visible assertions instead of fixing path-dependent behavior.  
Failure scenario: Recorded target remains absent from rendered outcome details, but test passes by checking stored target identity.  
Evidence: `plan:979` proposes identity assertions instead of rendered text. `wt/tests/test_phase70_t28c_review2.py:207-215` explicitly verifies rendered details do not hide recorded targets.  
Suggested change: Retain rendered-target acceptance. Add bounded root-cause investigation for short `/tmp` and long paths, then specify exact production/test patches preserving visible behavior. Current evidence does not justify replacing that contract.

## Finding 37 [major]
Section: 4.A4, 4.B4–B5, 4.E1, 4.I1–I3, 4.T2; 8.X3–X6, 8.X8, 8.X10–X11  
Defect: Overlapping edits have no single canonical application order, and some are alternative implementations.  
Failure scenario: Apply section 4 literally, then section 8 → anchors disappear, conflicting cleanup executes twice, or later whole-block replacement erases earlier additions.  
Evidence: A4/X4 replace same budget block; B5/E1/X4 replace same Edits clause; B4 replaces `SKILL.md:75-94` while X10 replaces `76-80`; T2 teardown deletion conflicts with X8 delayed deletion; X3 replaces entire `stop)` that X11 augments.  
Suggested change: Replace duplicates with references to one canonical patch per file. Required ordering: X3 stop replacement before X11 additions; I1 final lifecycle rewrite before I3 merge clause; X10 heading rename before insertion at renamed heading; X5 frontmatter plus B7 body edits before final probe. Reconcile T2/X8 and E4/X6 alternatives rather than applying both.

## Finding 38 [minor]
Section: 4.C6, 8.X3, 8.X11  
Defect: Exact stop implementation omits promised worktree archival and merged-branch cleanup.  
Failure scenario: Apply proposed `stop)` → state disappears, but merged branches/worktrees remain.  
Evidence: `plan:817` promises deletion after archive; X3 stop body at `1342-1354` only compares hashes and removes state/marker; X11 adds monitor termination only.  
Suggested change: Add explicit archival/cleanup operations before state removal, selecting branches from recorded run ownership and verified merge state. Include dirty-worktree preservation and cleanup-failure behavior.

Automatic tool review rejected the read-only worktree `git -C … rev-parse HEAD` check as outside document contract; no alternate execution route used.

Graft saved approximately 2,834 tokens this turn, 1 call.

Sections reviewed: sections 0–8; 81/81 section-4 entries, including H 17/17, I 4/4, J 22/22; 11/11 exact-edit sections; 7/7 user-level and 7/7 repo-level agent definitions; all named live scripts/configuration surfaces; 4/4 requested available fixture scripts exercised, with checker scratch output relocated into disposable directory.

Not reviewed: Codex sessions and `stall-notify.sh`, explicitly excluded; historical arithmetic, intentionally not recounted; full-suite performance, remote CI and headless model probes not rerun because this review exercised bounded local fixtures without production writes. Unimplemented J-series hooks received specification review, not runtime certification.


