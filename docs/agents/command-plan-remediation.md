# Command-plan remediation: one plan, complete correction

Audience: Rush maintainers and coordinating/subagents. Applies to corrective
editing of Plans 02–10 in `docs/phase-plans/command-tdd-2026-10-01/` after James
explicitly authorizes the next plan. Creating or invoking this guide does not
authorize that next plan, production implementation, commits, or publication.

Use this guide with [orchestrate](/Users/jamesdsizemore/.agents/skills/orchestrate/SKILL.md)
and [task-block-template.md](../templates/task-block-template.md). Keep the
existing plan's valid content and schema. The [batch creation prompt](cli-command-remediation-plan-batch-prompt.md)
serves a different authorized task; its ten-plan scope never replaces the
current one-plan remediation boundary.

## What Plan 01 taught us

Evidence snapshot: [Plan 01](../phase-plans/command-tdd-2026-10-01/01-rush-review.md)
at SHA256 `42be071461fda7353aaf25cc813030ba6606e577dfc9da0d96220a9fd17b2828`;
the controlling [Claude remediation report](../reports/command-tdd-2026-10-01-plan-remediation.md),
especially its final **Cross-section conflicts and binding resolutions**.
These identities describe the reviewed snapshot. Reverify current bytes for
each new task; they are not permanent source or readiness assertions.

| Failed decision / concrete trap | Replacement decision before editing |
| --- | --- |
| Completion was claimed before complete helpers, tests, and dependencies had been established. | Cover every applicable finding before delivery. Inspect actual proposed bodies, interfaces, fixtures, ownership, and implementation entry conditions. Headers, counts, hashes, syntax, and agent PASS cannot establish development readiness. |
| Later review found a C-11 whole-call denial mismatch after substantial proposal work. | Extract applicable final C resolutions before drafting. Write one input/state/result/effect matrix; derive proposed code and exact assertions from it. Preserve explicit per-command exceptions; do not copy Plan 01's result semantics into other commands. |
| Tests initially patched the wrong provider module, used inconsistent predicate fixtures, or omitted branch/state assertions. Transport also retained credentials in an import-time `ENV` copy. | Trace the actual callable/import boundary and subprocess environment once. Define helpers/fixtures completely. Assert exact status, summary, metadata, preserved findings/scope, provider/launch counts, and state mutations where applicable. |
| Before/after source hashes did not prove which bytes a container imported. Receipt field presence did not prove receipt validity. | Specify the complete data flow and identity bindings before authoring isolation tests. Q01-13/16/24 contain proposed captured/executed-byte binding, invocation-bound receipt validation, and an unexecuted real OCI transient-swap test. Mocks establish only their tested branch. |
| Shared documentation inventory rejected prerequisite copies; a reviewer also proposed an unsupported caller-known ownership API. | Reconcile the entire prerequisite/transport/docs chain early. Q01-M1 specifies exactly 14 prerequisite files and a proposed hash-verified transfer/registration gate. Require a literal binding/source citation for reviewer objections; withdraw unsupported objections instead of expanding scope. |

James's corrections also prohibit destructive restarts: preserve usable agent
work and valid plan content. A defect in one entry authorizes correcting that
entry, not replacing/deleting surrounding work or restarting the series.

## 1. Freeze scope and evidence before delegation

Record the following in the existing plan's reconciliation section or working
context. Do not create another report, recovery system, or runner.

1. **Authorization:** exact plan path, requested operation, literal non-goals,
   user corrections, approved model/effort constraints, and next-plan boundary.
2. **Baseline:** delivery root, actual Phase 70 source root/branch/HEAD,
   relevant dirty-file hashes, target-plan hash, audit/report hashes, and known
   preserved changes. Check Git status/diff before writing. Git state is not
   Phase 70 acceptance.
3. **Coverage:** every command-specific finding and missed issue, plus every
   applicable shared X/M, Foundation, final C resolution, Phase 70 packet/brief,
   and documentation/transport dependency. Explain excluded items individually.
4. **Authority:** user requirements/corrections control; apply the report's
   explicit final binding resolutions over superseded conflicting proposals.
   Live source establishes current behavior, not permission to remove required
   behavior. Audit source, approved decisions, and assistant proposals remain
   distinct. Record unresolved user-owned choices without silently selecting a
   report default.
5. **First packet:** identify what an implementer would do first, its current
   callable boundary, dependencies, and exact acceptance. Resolve missing design
   before editing dependent snippets. Investigate an unknown with one bounded
   question, not another broad audit.

Use Graft/CodeGraph first for indexed code; verify checkout/index provenance and
read only necessary missing spans. Use context-mode for large report sections
and multi-source analysis. Extract the selected plan's findings and applicable
final resolutions once; retain retrieval handles. Prefix shell commands `rtk`.
Do not read the full report into conversation or re-scan other plans.

Working coverage row, one per applicable finding; retain substantive detail:

| Finding + controlling clause | Literal requirement/category | Current source/test evidence | Exact plan section + proposed change | Concrete check/input/expected state | Disposition + remaining gap |
| --- | --- | --- | --- | --- | --- |
| Fill each applicable ID | Repair / ordinary extension / user baseline / new proposal | Checkout, file:line, API; existing / proposed | Surgical patch, defined helper, or exact contract | Label executed observation vs proposed acceptance | Confirmed, already satisfied, contradicted/withdrawn, or external blocker; rationale |

A row count closes inventory only. Empty cells, generic fixes, unexplained
exclusions, missing body/fixture/dependency design, and unresolved user corrections
block completion. Do not let a shared proposal ID replace each finding's analysis.

## 2. Assign subagents by task, model, and reasoning

For this series, James approved **GPT 6.1 Sol High + GPT 6 Luna High**. Use these
for difficult remediation and adversarial review. Honor any later explicit
model/effort direction. Never silently substitute a missing model.

| Lane | Model / reasoning | Bounded responsibility and output |
| --- | --- | --- |
| Coordinator | Current main agent | Scope/coverage, source identity, ownership, binding conflicts, integration, frozen hashes, completion. No redundant scout by default. |
| Plan author | GPT 6.1 Sol / High | Difficult shared-contract, permission, identity, isolation, or design synthesis. One authorized plan; exact owned sections/IDs. Return integrated concrete corrections and compact evidence/change receipt. |
| Independent reviewer | GPT 6 Luna / High | Requirement-versus-plan review, source/API truth, realistic test routes, adversarial branches, and readiness. Read-only. Return finding ID, literal controlling clause, exact location, concrete defect/correction, and evidentiary limit. |
| Optional narrow scout | GPT 6 Luna / Low, only when current effort instructions permit | One unresolved locator/API question with exact spans and a compact answer. No writing, design decisions, delegation, or full-plan review. Coordinator normally performs this work without spawning another agent. |
| Routine bounded correction | GPT 6.1 Sol / Medium, only when current effort instructions permit | Mechanical edits after contract/design is settled. Do not downgrade a lane expressly assigned High; do not upgrade because its assignment is unclear. |

For full multi-issue plan remediation, coordinator + author + reviewer usually
provides distinct coverage. Select only needed lanes: coordinator can author a
routine bounded correction without a separate author agent. Add an independent
reviewer for material risk or added coverage; permission, isolation, transport,
identity, or shared-contract changes require that review. Do not spawn a separate
reviewer for an already-proven literal formatting correction. Full requested
review coverage remains required regardless of agent count. Check live slots and
reuse completed agents with retained relevant evidence. Keep optional scouts out unless
an independent unresolved question materially saves work. No leaf delegation.
Use fresh compact context for new agents; full-history forks are unnecessary.

Reviewer starts with the same controlling requirements and rejection history as
author. Before edits, independently check high-risk binding/dependency decisions
against the frozen existing plan while author prepares correction specifications.
Coordinator resolves disagreements before those decisions enter dependent bodies.
Do not accept a speculative concern as a binding requirement.

**One writer per section; normally one author owns all plan edits.** Coordinator
does not concurrently rewrite the author's sections. Explicitly transfer ownership
before another writer takes over; preserve the completed patch and receipt.
Independent read-only review can run concurrently on unchanged sections whose
hashes are frozen. Final integrated review uses the final frozen plan.

Reusable assignment template; fill all fields before dispatch:

```text
Task: remediate/review <finding IDs> in <one absolute plan path>.
Model/reasoning: <actual model and effort; why task needs it>.
Mode: <sole plan writer / read-only reviewer / read-only scout>.
Owned sections: <literal headings and IDs>; all other bytes preserved.
Frozen subject: <whole-plan or owned-section SHA256>.
Source: <actual checkout, HEAD, relevant dirty hashes, exact retrieved spans>.
Bindings: <literal requirements, final C overrides, applicable Foundation/Phase70 contracts>.
User corrections: plan edits only; preserve valid work; no rewrites/restarts;
no production/test/config writes; no next plan; no commit/push/release.
Output: <concrete integrated corrections or specific review findings>, plus
IDs covered, evidence, hashes, exact checks/results, and any genuine blocker.
Acceptance: same full coverage/concreteness/readiness rules as coordinator;
syntax is not behavior; no invented existing API or implicit approval.
You are not alone. Preserve others' changes. No delegation or extra artifacts.
Stop on byte drift, overlapping ownership, instruction conflict, or user stop;
preserve completed work and report exact state.
```

## 3. Correct substance once, preserving the plan

Author applies surgical hunks to the authorized Markdown only. Retain useful
sections, requirement IDs, approved scope, prior tests, and valid agent work.
Do not append a workaround while leaving contradictory original content active.
Do not reformat unrelated sections, reorder the entire plan, or replace a whole
document to repair one entry. Before a disputed deletion/rewrite/move, provide
the required no-write recovery inventory with proven original/restoration source.

Each correction must supply the actual proposed diff/body/config/schema change,
literal target file/symbol, all necessary imports/helpers, exact input/output,
and a runnable check with concrete fixture and expected result. Label future code
and behavior checks proposed. Source/test/config files remain untouched.

Check the complete chain before final review:

1. **Current defect:** reproduction reaches the intended assertion through an
   existing callable. A future-keyword TypeError is interface absence, not proof
   of an unrelated behavioral defect. Already-correct behavior gets a regression.
2. **Proposed design:** every helper is verified existing or completely specified;
   every dependency has owner, files, interface, permissions, ordered entry/exit
   criteria, concrete implementation packet, and integration acceptance. A
   cross-plan link orders work but cannot hide missing prerequisite design.
3. **State and effects:** state table, code, tests, CLI exits, MCP carriers, scope,
   summaries, permissions, and docs agree. Include invalid/empty input, denial,
   unavailable provider/engine/runtime, malformed output/receipt, stale identity,
   budget/timeout/crash, cleanup/recovery, and success branches where applicable.
4. **Tests and transports:** imports patch the defining boundary; fixture math and
   engine controls match assertions; subprocess environment copies are controlled;
   CLI and initialized stdio use shared helpers/implementations. Actual transport,
   persistence, isolation, or algorithms need relevant future real-path tests.
5. **Shared integration:** one Foundation owner for shared writes; frozen binary
   packaging, runtime/image provisioning, marker/CI behavior, documentation inventory,
   historical ADR rules, exact prerequisites, and transfer identities all reconcile.

Do not invent new capabilities, APIs, or ownership machinery to satisfy an
unsupported reviewer objection. Verify the cited binding; record withdrawal and
retain valid content. An unimplemented, fully specified prerequisite is ordered
work; an undefined prerequisite or unapproved design choice blocks readiness.

## 4. Freeze, review, and verify only what changed

Complete applicable corrections before final verification. Freeze whole-plan
SHA256, or exact section hashes for proven independent lanes. Reviewer stays
read-only. Review full requested coverage; do not stop at first blockers or
replace semantic review with syntax, headings, or test-name inventory.

After review findings, make only substantiated corrections. Re-freeze affected
bytes; re-review affected claims and dependencies. Reuse accepted unchanged
sections only with hash evidence. A formatting-only change can retain semantic
evidence when exact diff and AST equivalence demonstrate unchanged code; it
still needs an affected format check. No blanket reuse after substantive drift.

Plan-only validation uses existing tooling, not an installed/new validator or
recovery framework. Check code-fence syntax, embedded-source syntax where
applicable, relevant formatting, concrete check commands/fixtures, literal file
map, working coverage, and preservation boundary. Ruff stdin formatting must
receive the source's terminating newline. An extraction/tool failure is a check
failure; correct that extraction, not unrelated plan content.

Scope/hash checks available from the delivery root:

```sh
rtk git status --short
rtk git diff --stat
rtk proxy shasum -a 256 docs/phase-plans/command-tdd-2026-10-01/*.md
```

Capture hashes before writing and compare afterward. Untracked plan changes do
not appear in `git diff`; unchanged Git stats alone cannot establish preservation.
For proposed test commands use Python 3.12/uv with inherited `PYTHONPATH` cleared;
identify real runtime/engine/image prerequisites and exact expected results.
Do not execute future behavior tests or implement their prerequisites under
plan-only authorization. Static PASS never becomes behavior PASS.

Resource rules:

- Research each needed surface once; retain exact spans, hashes, and decisions.
  Reviewer re-derives critical claims independently, not the entire corpus.
- Use parameterized cases/shared existing helpers when they preserve exact
  domain assertions. No generic permissive assertion or fabricated receipt as
  real-runtime evidence. Return compact receipts, not full source dumps.
- No identical verification more than twice on unchanged bytes. Resume only
  unchecked/affected checks after drift. Never rerun to recover omitted output;
  expand the retained output or query its index.
- At repository execution/mutation or time ceilings, perform its required
  internal read-only recenter: task, completed evidence, exact blocker, shortest
  remaining route. Do not evade ceilings through another agent/tool/batch.
- Preserve prepared patches across corrections and compaction. No broad restart,
  new runner, extra chat, unsolicited skill/global-rule edit, or downstream plan.
  Communicate useful state at least every 60 seconds; status questions do not
  require stopping work, while corrections stop the disputed tactic immediately.

## 5. Completion gate and handoff template

Before handoff, reconcile **every** coverage row with the actual corrected
substance. Full review includes task logic, source/API truth, dependencies,
ordering, assets, scope, tests, transports, adversarial behavior, failure/recovery,
semantic drift, and readiness/ratification. Final hashes must match reviewed bytes.

Use three separate claims:

1. **Plan remediation complete:** every applicable finding disposition is justified,
   required concrete corrections integrated, no unresolved in-scope design/review
   gap, final bytes reviewed, and preservation checked.
2. **Development-ready:** implementer can begin the first ordered packet without
   choosing scope, API, data source, schema, ownership, prerequisite design, or an
   unapproved user-owned behavior. Fully specified future dependencies have an
   executable ordered route. Record genuine external/user-decision blockers
   precisely; do not declare ready or simulate closure while they remain.
3. **Implementation accepted:** requires separately authorized production changes
   and relevant real behavior gates. Plan hashes, syntax, proposed test bodies,
   mocks, clean worktree, or Phase70 commit identity cannot establish it.

Finish resolvable in-scope work before returning. A real external blocker needs
its exact missing decision/evidence/environment, affected packets, and smallest
required next action. Do not hand back ordinary unfinished authoring/review work,
ask James to diagnose it, or silently downscope to make a completion label fit.

Place compact reconciliation/receipt in the existing plan; no companion report.
Fill this template with facts, not placeholders in the delivered plan:

```text
Authorization/output: <one absolute plan path; plan-only>.
Final SHA256/source baseline: <reviewed bytes; live checkout/HEAD/dirty hashes>.
Coverage: <finding IDs + controlling overrides + exact corrected sections;
justified already-satisfied/withdrawn items; no unexplained gaps>.
Checks: <exact commands, subjects, results and evidentiary limits>.
Preservation: <unchanged other-plan/source/test/config/user-change evidence>.
Readiness: <plan remediation status; separate development-ready verdict>.
External prerequisites/decisions: <literal blocker and affected packet, or none>.
Implementation evidence: <none during plan-only remediation>.
Next boundary: James reviews this plan; another plan needs explicit authorization.
```

Final chat: exact plan link, concise status/precise blockers, one review action.
No unsupported “implementation-ready” claim. Stop at James's review boundary.

## Kickoff prompt for the next authorized plan

```text
Remediate only <absolute authorized plan path> against the Claude findings and
final binding resolutions in docs/reports/command-tdd-2026-10-01-plan-remediation.md,
the binding command audit, and current Phase70 source/contract/design briefs.
Apply docs/agents/command-plan-remediation.md and the local task-block template.
Preserve valid existing plan content and prior agent work. Edit Markdown only;
no production/test/config edits, implementation, other plans, commit, or push.
Use GPT6.1 Sol High for difficult concrete corrections and GPT6 Luna High for
independent bounded review. Coordinator owns scope/integration; assign literal
section ownership and the same acceptance criteria; no leaf delegation.
Freeze baseline and full applicable finding/override coverage before drafting.
Resolve shared-contract and test-route questions early, then integrate surgical
corrections. Independently review frozen bytes; validate only changed/unchecked
subjects and preservation. Do not restart the series or create extra artifacts.
Finish all resolvable plan gaps. Report readiness separately from implementation
acceptance and name any genuine external decision/evidence blocker precisely.
Return the corrected plan link and concise status; stop for James's review.
```
