# Reusable prompt: ten CLI-command remediation development plans

Copy the prompt below into the planning task. Change the batch IDs and output directory when using it for a later batch. This is a planning instruction, not approval to implement or publish changes.

---

Create **exactly ten individual TDD-based CLI/MCP remediation development plans that are ready for development**, using the authorized command batch below. Use subagents with bounded file ownership and appropriate models/reasoning. Complete the documents; do not substitute research receipts, an index or status messages.

## Inputs and authority

- Repository/delivery root: `/Users/jamesdsizemore/Developer/rush-cli`.
- Current development target: Phase 70, presently discoverable at `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70`, branch `phase/70-agent-adoption-and-usability`. Verify live checkout/branch/HEAD; do not reuse a historical hash as “current.”
- Authoritative command audit: `/Users/jamesdsizemore/Developer/rush-cli/docs/reports/cli-mcp-command-audit-2026-09-26.md`.
- Binding phase contract: `docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md` **in the current development checkout**, including relevant design-gate briefs identified by its task-to-brief map. Read the fuller packet/brief requirements together.
- Required task schema: `docs/templates/task-block-template.md`.
- Authorized batch for next use: **Q11–Q20**, after the standing user review/approval boundary is satisfied or explicitly superseded. Supplying this prompt does not prove an earlier batch was approved.
- Absolute output directory: `/Users/jamesdsizemore/Developer/rush-cli/docs/phase-plans/command-remediation-batch-02/`.
- Historical failure reference: `docs/reports/cli-command-plan-batch-01-session-review-2026-10-01.md`. Use its lessons; do not repeat its research or alter Batch 1.

Verify the ten audit IDs and actual CLI/MCP names from the audit and current catalog. Expected audit entries for this batch:

| IDs | Commands |
|---|---|
| Q11–Q13 | `rush_actions`, `rush_yaml`, `rush_sql` |
| Q14–Q16 | `rush_templates`, `rush_containerfile`, `rush_iac` |
| Q17–Q18 | `rush_secrets`, `rush_sbom` |
| Q19–Q20 | `rush_coverage`, `rush_codeql` |

Use verified CLI spellings in filenames and examples. For another batch, replace this manifest from the authoritative audit; never infer ten names from memory.

Read applicable AGENTS.md instructions first. User scope and corrections control. The audit is a finding/proposal source, not proof that its code still matches current development or that every assistant-originated proposal was approved.

## 1. Establish one authoritative baseline before drafting

Identify the current Phase 70 source checkout and status. Record branch, HEAD, relevant dirty-file hashes, phase-plan/brief identities and audit hash **inside every command plan**. Distinguish source checkout, delivery directory and future implementation worktree.

Check Git status/diff before writes. Existing changes are user-owned. Inspect attached/registered worktrees and reuse a suitable authorized worktree; do not create another casually. Any future implementation worktree must start from the verified Phase 70 baseline, not default/main merely because it is convenient. Do not switch or reset the active Phase 70 checkout.

Use Graft/CodeGraph first for indexed code, then inspect exact missing spans when necessary. Use context tools for large/multiple sources; return derived findings, not raw documents, broad tool catalogs or repeated source dumps. A graph hit must be checked for the requested checkout and staleness.

For every command, trace current implementation and callers: shared tool, engine adapters, routing/target identity, config, permissions, invocation, catalog, CLI and stdio MCP registration, existing tests and documentation. Distinguish defining modules from re-exports.

Reconcile every audit requirement against current Phase 70: already implemented and verified; implemented but regressed; remaining repair; approved ordinary extension/user baseline; distinct proposal with its authorization status. Record evidence and exact planned change for each. Do not duplicate existing work or erase required behavior to fit present code.

## 2. Delegate complete documents with equal acceptance

Check active slots first. Assign each author exact owned Markdown files, current baseline, required sections, complete audit rows, restrictions and the same acceptance gates. Each author returns a finished document plus a compact receipt; grounding notes alone are not the requested output.

Choose model/effort by task difficulty and binding Phase 70 allocation. Narrow read-only scouts use low effort; routine bounded authoring uses medium; conflicting contracts, permissions, isolation, supply-chain trust and final synthesis use high. Honor Phase 70's stronger model requirements where applicable. Record actual model/effort and responsibility; do not increase cost to compensate for an unclear assignment.

Parallelize independent research and command documents. Resolve shared contracts before parallel authors use them. One owner controls each shared production/test/doc path in the proposed execution order. Tell agents they are not alone and must preserve others' work.

Coordinator remains responsible for substantive integration of all ten. Different command difficulty may justify different effort; it never justifies missing sections, generic acceptance or skipped review of any command.

## 3. Write ten standalone development packets

Save only the ten command-specific Markdown plans in the absolute output directory. No PRD, README, batch index, wrapper, issue-tracker files, extra framework, or replacement deliverable. Shared implementation contracts must be included concretely in each consuming plan; do not invent another document to supply missing behavior.

Use the local task-block schema and a comparable current Phase 70 packet. Every plan must contain:

1. **Goal, scope and requirement ledger.** Map every applicable audit finding, approved extension, requested baseline and expansion assessment to source evidence, exact behavior/change, task/test and acceptance. Keep categories distinct. Provisioning, connected specialist local models, voice/live speech and 3D companion are user baseline requirements where applicable, not claimed inventions. No quota of unique inventions.
2. **Required behavior and concrete design.** Exact input names/types/defaults, CLI flags/MCP schema, canonical ToolResult fields, state transitions, permission effects, limits, errors, compatibility and before/after example. Name verified helpers; define proposed helpers completely enough for implementation. No undefined pseudo-APIs, signature-only sketches or comment-only behavior.
3. **Deliverables and dependency order.** Literal production files/symbols, tests/fixtures, documentation claims, config/registry updates, prerequisite contracts and one owner per shared file. Identify exact first task and subsequent ordered tasks. No conditional file map, unnamed graph/evidence provider or implementer-decided schema.
4. **Ordered TDD packets.** Runnable RED bodies with defined fixtures/helpers and exact assertions; minimum GREEN changes tied to each failure; named regression and refactor checks. Include recovery/cleanup and stop conditions.
5. **Constraints, checks and completion.** Exact environment/engine prerequisites, executable commands, expected output/state, failure handling, full scope reconciliation and development-readiness verdict.

A dependency need not already be implemented. It must be either a verified existing capability or a fully specified ordered prerequisite packet included in the consuming plan. Name its files, interface, permissions, tests, owner, entry/exit criteria and integration checks. Cross-plan references may establish ordering; they cannot delegate missing behavior or require the implementer to design it.

Future command-focused PR scope belongs in each plan: shared prerequisites first, exact command changes next, literal files and acceptance. Do not create, commit, push or publish PRs during planning.

## 4. Make the first RED meaningful on current source

For a bug repair, reproduce through a **verified current callable boundary** before changing interfaces. Supply real input/fixture and assert exact incorrect-versus-required behavior. Establish that the failure reaches the intended assertion rather than crashing because of an invented keyword, invalid mock, missing project marker, wrong Python or unavailable engine.

Separate new-interface/new-capability acceptance tests. A proposed API may legitimately be absent today; label its expected initial failure precisely as interface/feature absence and order implementation accordingly. A TypeError does not reproduce a different behavioral bug. Existing correct behavior needs a preservation regression, not a fabricated RED.

Define every fixture, helper, import, config, project manifest and controlled engine return in the shown module. Mock availability consistently per engine. Mock only the layer being tested; an engine double cannot prove real parsing, transport, persistence, isolation or algorithm execution.

State observed reproduction results when safely executed. Label unexecuted expected failures as proposed. Plans do not need their future GREEN tests to pass today, but code/examples must be syntactically coherent, have exact prerequisites and provide a complete executable route.

Required checks use the repository's Python 3.12/uv environment, with inherited PYTHONPATH cleared:

```text
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python --version
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest <literal-existing-or-proposed-test-paths-and-node-ids> -q
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev ruff check src tests scripts
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev ruff format --check src tests scripts
```

Replace test placeholders with literal paths/node IDs in every delivered plan. Python version check must report 3.12. Derive additional real-engine commands/version bounds from current source and authoritative engine evidence when needed. No implicit dependency installation, network access or fake skipped-success evidence.

Include actual CLI execution and initialized stdio MCP request tests that reach shared implementation. Compare deterministic domain fields and exact expected results; exclude timings/run IDs from equality. Assert grants/denial and effects. stdout remains JSON-RPC during MCP serving; logs remain stderr.

Cover applicable adversarial cases: missing/incompatible engine, malformed output, crash/timeout, empty versus invalid input, mixed assessed/skipped coverage, target/config containment, stale identities, partial writes/recovery and permission-denied zero effects. Real execution/isolation claims require the genuine runtime and an explicit acceptance test; worktree copies, launcher mocks and fabricated receipts do not prove isolation.

## 5. Review frozen bytes before readiness

Freeze source/plan identities after drafting. Review every command against the controlling requirement ledger and literal file map before looking at green tests. Reconcile Phase 70 packets and briefs with actual source/tests; a phase specification is not implementation proof.

For each audit row, verify requested outcome, concrete design, current API/helper, exact writes, coherent first RED, minimum GREEN, regressions/refactor, dependencies/ownership, transport, adversarial behavior and recovery. Read corrected substance; file count, headings, word count, snippet syntax and agent PASS messages prove only their narrow checks.

Any edit invalidates affected verdicts. Review corrected bytes again; do not run identical unchanged-byte verification more than the allowed limit or introduce a new runner/framework.

**Development-ready** means an implementer can begin the first packet without deciding scope, contract, file, data source, ownership or prerequisite design. It does not mean production changes already exist or future tests already pass. Explicitly unimplemented but fully specified prerequisites are ordered work, not grounds for automatic downscoping.

If evidence/design remains unresolved, perform the exact bounded investigation and resolve it before handoff. If a genuine external blocker prevents resolution, name it precisely and mark that plan not ready; do not call the ten-plan batch finished. Never make a packet ready by changing a label, deleting required scope or turning a missing capability into simulated output.

## 6. Keep execution and communication within scope

Respect real tool enforcement. Do not disable/bypass guards, edit hooks/settings, create another chat or change global instructions as a workaround. Distinguish obsolete task-skill scope from actual current enforcement. Preserve prepared work and one concrete checkpoint; do not repeat blocked attempts or make the user repeat approval already supplied.

A correction stops the disputed action; an explicit task switch/cancellation stops affected work. Preserve valid edits and re-anchor assignments immediately. Never interpret frustration about context dumping as authorization for a different artifact or an automatic cancellation of independently authorized work.

No production edits, new harnesses, unsolicited cleanup, commits, pushes, release changes, hook installation or next-batch planning in this task. Use existing tools/helpers and the minimum complete design.

Final verification: exactly the authorized ten standalone files exist in the requested absolute directory; every command/requirement and readiness check was substantively reviewed; final hashes match reviewed bytes; unrelated source and user changes remain untouched.

Return only actual file links, concise per-batch readiness status and precise blockers if any. Stop after ten for user review/approval. No unrequested wrapper or additional deliverable.

---

