# Connecting Rush capabilities through memory for vibecoders

Assessment against `997b56e`, extending [the memory capability assessment](recommendations.md). These are proposed integrations, not implemented capabilities or an approved implementation plan. No runtime changes made.

**The strongest opportunity: let an agent remember what the user wanted, which approaches failed, which project patterns worked, and what evidence would justify its next action.** The vibecoder should need fewer repeated explanations and fewer rounds of “you broke it again.”

Comparison criteria: user effort removed, change in the agent's next decision, reuse of demonstrated Rush components, strength of verification, and integration cost. Merely saving more logs or renaming a test runner adds little value.

## Five useful combinations

### 1. Preserve the promise behind a feature

Illustrative experience: the user asks, “Clean up checkout.” The agent remembers an earlier explicit requirement: customers can buy without creating an account. A proposed change breaks the guest-checkout test, so the agent repairs that regression before presenting the result.

**Connect:** preference/decision memory, traceability links, codegraph, API diff, contract tests and configured E2E tests.

**New behavior:** store the user's confirmed intent beside the relevant behavior check and implementation references. When an edit touches those references, recall the promise and run its check. Store the new result against the exact revision. An intentional new user instruction can supersede the old requirement; inferred preferences remain candidates.

**Distinctive benefit:** continuity of product intent across coding sessions and providers. A generic test suite cannot explain why a behavior matters or distinguish an obsolete requirement from an active one.

**Proof:** after a provider handoff, detect an injected guest-checkout regression while allowing an explicitly authorized requirement change. Current [TraceScanner](/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-61-62-review-fixes/src/rush/tools/trace.py:14) only matches requirement tags in docs/code/tests. Its `VERIFIED` label is not execution evidence; this integration needs real test results. Current [semantic-drift](/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-61-62-review-fixes/src/rush/tools/semantic_drift.py:116) invokes configured Playwright tests tagged `@drift`; it does not infer arbitrary product behavior.

### 2. Stop repeating failed repairs

Illustrative experience: “Fix the upload error.” Before retrying a timeout increase, the agent recalls that it failed under the same dependency version and identifies the experiment that exposed a request-size limit. It checks whether those conditions still hold before choosing a repair.

**Connect:** FailureLedger, flight recorder, MistakeMiner, typed failure memory, patch sandbox, PatchVerifier and fix attribution.

**New behavior:** link symptom → conditions → attempted change → observed result → successful repair → regression test. Retrieve a compact relevant episode before the next attempt. A different environment or new evidence permits a fresh trial. Similarity alone must not block a repair.

**Distinctive benefit:** the next attempt tests a different explanation instead of spending another prompt and tool cycle rediscovering the same failure.

**Proof:** fewer repeated unsuccessful attempts on held-out repair tasks, with equal or better final correctness and lower total tokens. Existing [FailureLedger](/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-61-62-review-fixes/src/rush/memory/failure_ledger.py:35) recognizes exact patch hashes; semantic and condition-aware matching would be new work. Existing [MistakeMiner](/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-61-62-review-fixes/src/rush/memory/mistake_miner.py:18) reads revert messages; a revert alone does not prove a technical defect. [Fix attribution](/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-61-62-review-fixes/src/rush/tools/provenance_ai.py:85) supplies links, not causal proof.

### 3. Build new features from the project's tested patterns

Illustrative experience: “Add CSV export for invoices.” The agent retrieves the project's existing export implementation, authorization convention, error handling and relevant tests. It adapts that pattern instead of introducing a second export library or inventing a parallel architecture.

**Connect:** codegraph/call paths, context packing, dependency discovery, skill/pattern memory, type checks and patch verification.

**New behavior:** remember a reusable recipe as source references, applicability conditions and validating tests. Resolve the current source when the recipe is reused; invalidate references after relevant changes. Record whether the adapted feature passed its required checks. Retain known exceptions alongside the recipe.

**Distinctive benefit:** the agent becomes more consistent with this particular project as it works, without requiring the vibecoder to maintain a long instruction file or understand every architectural convention.

**Proof:** complete a new feature using an appropriate existing implementation, avoid an unnecessary dependency, and reject a stale recipe after an API change. [CallGraphTraverser](/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-61-62-review-fixes/src/rush/codegraph/traverser.py:17) and [ContextPacker](/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-61-62-review-fixes/src/rush/codegraph/context_packer.py:30) provide retrieval primitives. Passing once, being frequently copied, or remaining in Git does not establish universal correctness.

### 4. Choose checks from what this project has actually broken

Illustrative experience: “Rename this field.” Prior failures connect that field to an API payload, database fixture and checkout flow. The agent prioritizes those checks and reports their results in ordinary language, without asking the user to choose among Rush's engines.

**Connect:** codegraph/blast radius, coverage and mutation results, contract/E2E tests, security/dependency findings and failure memory.

**New behavior:** record which checks caught real regressions and which changes they covered. Use those relationships to prioritize early feedback for the next relevant edit. A passing check supports only its measured behavior; required broader gates still run. Missing engines remain explicitly skipped.

**Distinctive benefit:** project experience helps allocate verification effort. This can shorten the feedback cycle while exposing gaps that a generic “tests passed” summary hides.

**Proof:** earlier detection of seeded regressions at comparable total quality, with measured time/token costs. Current [BlastRadiusAnalyzer](/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-61-62-review-fixes/src/rush/tools/blast_radius.py:32) uses reverse imports and path-name heuristics. It is a candidate selector, not proof of complete impact coverage. Dynamic calls and external consumers require additional evidence.

### 5. Explain what changed since the last successful run

Illustrative experience: “It worked yesterday.” The agent finds the last successful run of the same behavior, compares relevant code/configuration/dependency fingerprints, and narrows the investigation. It verifies a suspected cause in isolation before explaining it or proposing a repair.

**Connect:** checkpoints, flight recorder, verifier receipts, Git history, dependency/security results, API diff and memory freshness checks.

**New behavior:** maintain a last-successful reference per behavior and environment, rather than one global “good project” flag. Link later failures to the differences from that reference. Reproduce a suspected cause when feasible; otherwise report it as a candidate. Carry this state through provider handoffs.

**Distinctive benefit:** makes the project's recent history usable for diagnosis and resuming work. The user gets a specific change and supporting observation instead of a fresh debugging interview.

**Proof:** distinguish an introduced code regression from a changed dependency or unavailable engine, including after a handoff. Existing [PatchContract](/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-61-62-review-fixes/src/rush/patch/contracts.py:31) binds code, patch, configuration and required commands; [PatchVerifier](/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-61-62-review-fixes/src/rush/patch/verifier.py:46) records execution outcomes. Additional environment identity and comparison logic are still needed. A checkpoint or successful delivery is not itself proof that the application worked.

## Where the rest of Rush contributes

| Capability family | Useful memory | Effect on a future agent decision |
|---|---|---|
| Tests, contracts, snapshots, E2E, mutation | Behavior exercised, input/fixture, outcome and revision | Select a meaningful reproduction; preserve previously requested behavior |
| Codegraph, API diff, coverage | Source relationships and measured execution links | Retrieve the right implementation and check affected consumers |
| Security, dependency and license checks | Exact finding, relevant package/configuration version and resolution evidence | Revisit a decision when its conditions change, rather than repeat stale advice |
| Sandbox, patch verification, provenance | Attempt, required checks, results and attributed repair | Choose the next experiment and distinguish an attempted fix from a verified one |
| Continuity, checkpoints, token utilities | Active intent, unresolved hypotheses, compact evidence references and expansion costs | Resume useful work with bounded context across providers |

## What makes this more than ordinary automation

The important loop is **observe → retrieve relevant experience → choose an action → execute within granted permissions → verify → update memory**. Memory must alter the next decision. Merely appending every ToolResult to a database does not establish that loop.

The individual ideas are not claimed as world-first inventions. [Reflexion](https://arxiv.org/abs/2303.11366) studies feedback retained as episodic memory to improve later attempts. [Voyager](https://voyager.minedojo.org/) combines reusable executable skills with environment feedback. These support investigating the mechanisms; their experimental gains do not establish gains for Rush or vibecoders. Rush's potential distinction is combining project intent with its existing code, quality, isolation and continuity evidence.

## Boundaries that preserve useful memory

Keep records tied to the repository, source revision, relevant environment and permitted audience. Preserve the difference between what the user requested, what an agent inferred and what a tool observed. Summaries should point to redacted evidence, with full details expanded only when useful.

Do not treat current [line-survival statistics](/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-61-62-review-fixes/src/rush/tools/provenance_ai.py:107) as a probability that a repair is correct: the implementation measures ages of surviving lines and returns default ratios when no lines are measured. Likewise, frequency, model agreement and a green status label must not automatically promote a claim to trusted memory.

Use existing CLI/MCP tasks and explicit execution permissions. These proposals do not require a new Rush UI, automatically installed hooks, a background daemon, or automatic commits/rollbacks. Tool observations may inform an agent; they do not grant it new authority.

## Recommended starting point

**Start with failed-repair recall plus verified repair outcomes.** It has a clear vibecoder problem, existing failure/patch primitives, and a direct comparison against current behavior. Then add remembered product promises as the more ambitious user-facing capability.

Compare the current agent workflow, workflow with raw retrieved history, and workflow with scoped repair episodes. Measure repeated failed attempts, final behavioral correctness, user corrections, total tokens and elapsed time on the same tasks. The existing [PromptEvalTool](/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-61-62-review-fixes/src/rush/tools/prompt_eval.py:101) can assess supplied run records; it does not launch agents or prove those records came from real executions. No evaluation runner or implementation was created for this assessment.
