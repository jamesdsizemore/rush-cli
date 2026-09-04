---
name: adversarial-plan-review
description: Run a Sol-orchestrated, multi-Terra red-team review that falsifies a plan's claims, issues plan-only corrections, and verifies the revised plan without implementing it.
---

# Adversarial Plan Review

Use this skill to test whether a plan is executable, evidence-backed, safe, and
complete. This is not a polite checklist review and not an implementation
workflow.

Use it with the `orchestrator` skill. The parent orchestrator runs as
`gpt-5.6-sol`; review subagents run as `gpt-5.6-terra` with `high` reasoning.

## Scope boundary

First identify the plan being reviewed and the exact review artifacts the user
authorizes. Unless the user explicitly expands scope, reviewers may inspect
repository evidence but may edit only:

- the plan under review; and
- the dedicated adversarial-review artifact.

Never implement the plan, change production code, add tests, alter
dependencies/configuration, or make release/Git-history changes during a plan
review.

## Sol's protocol

1. Read the plan completely and turn its material assertions into a claim
   ledger. Include evidence claims, root causes, impacts, priorities, proposed
   fixes, dependencies, phase ordering, file references, tests, release gates,
   and definitions of done.
2. Freeze the plan during the first attack round.
3. Dispatch multiple independent Terra attackers. Use all available parallel
   capacity; if capacity is limited, run additional attack roles in a second
   wave rather than dropping them.
4. Require evidence-backed attack packets, cross-examination, and an explicit
   Sol adjudication for every material finding.
5. Permit one designated Terra remediator to revise the plan only after
   adjudication.
6. Run a second attack round against all revised material.
7. Independently verify every P0/P1 closure before final handoff.

Sol is a referee, not the plan's advocate. A claim survives only when evidence
and an executable remediation path support it.

## Terra attack roles

Assign non-overlapping roles as capacity permits:

- **Finding falsifier:** attempts to disprove the plan's cited facts, impact,
  severity, and root-cause claims from source and test evidence.
- **Remediation breaker:** finds bypasses, regression paths, and weak tests
  that let a proposed fix appear complete while the underlying defect remains.
- **Execution saboteur:** simulates a literal coding agent executing each
  phase; identifies missing prerequisites, hidden work, unsafe ordering,
  ambiguous tasks, and unverifiable exit criteria.
- **Security and trust attacker:** attacks secret handling, credentials,
  plugins, logging, persistence, network permissions, provenance, and trust
  boundaries.
- **Contract attacker:** attacks public APIs, CLI/MCP parity, schemas,
  transports, result contracts, configuration, and compatibility claims.
- **Release-gate attacker:** attempts to make the plan's release gates pass
  while the claimed defect still exists; attacks test isolation, package
  installation, dependencies, and definitions of done.

Terra reviewers are attackers, not summarizers. They must try to falsify the
plan, construct a concrete failure path, and show why a proposed repair does
not yet close it.

## Evidence and finding standard

For repository work, use the repository's required context and source tools
before broad search or reads. Ground each finding in exact source, test,
configuration, call-path, or primary external evidence.

Each finding must contain:

- stable finding ID and severity: P0, P1, P2, or P3;
- attacked claim ID or exact plan section;
- attack thesis and evidence;
- counterexample, bypass, or failure narrative;
- consequence if the plan is executed unchanged;
- minimum plan-only correction;
- affected plan sections and required revised acceptance criteria;
- required evidence for closure.

Reject generic feedback such as “add tests,” “clarify,” or “consider
security.” If there is no concrete attack, do not create a finding.

## Cross-examination and adjudication

For every P0, P1, and disputed P2 finding, assign a different Terra agent to
try to disprove the attack. The cross-examiner must use evidence, not intent or
plausibility.

Sol records one verdict:

- sustained;
- narrowed;
- disproved; or
- unresolved evidence, requiring an explicit plan gate or blocker.

Only sustained findings receive fixes. A finding may be dismissed only with
specific contrary evidence.

## Plan-only remediation

For every sustained finding, issue a fix order with:

- linked finding ID;
- exact plan text or section to revise;
- required correction to scope, sequence, evidence, task, dependency, test,
  acceptance criterion, release gate, or definition of done;
- closure evidence;
- explicit non-goals.

One Terra remediator applies all accepted fix orders to the plan. The
remediator must make the plan more executable and accurate, not merely longer.
It must preserve uncertainty as an explicit gate or blocker rather than
pretending it is resolved.

## Second attack and final decision

Re-attack every revised section and every closed P0/P1 finding. A finding is
not closed because prose was added; it closes only when the revised plan now
contains an evidence-backed, executable correction that survives renewed
attack.

Sol may return only:

- Accepted;
- Accepted with explicit non-blocking follow-ups;
- Revise and re-review; or
- Blocked pending evidence or a user decision.

Sol must not accept while a P0/P1 finding remains open, a material claim lacks
evidence, a release/acceptance gate can pass without proving its claim, or the
plan still requires a reviewer to invent missing implementation details.
