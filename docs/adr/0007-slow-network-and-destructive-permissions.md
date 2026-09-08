Current status: historical decision; Invocation-scoped permissions and containment remain required. Current fix dry-run, MCP ship cleanup, checkpoint, governance, and AI-evaluation paths violate parts of this contract; see [application review F01–F08](../reports/phase-64-66-application-review.md) and [Phase 64 safe execution](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md). Do not treat this decision as a current safety guarantee.

# ADR 0007: Slow, network, and destructive permissions

## Context
Some scans can mutate baselines, consume resources, or reach external systems.

## Decision
Local-safe defaults are mandatory. Slow, network-sensitive, destructive, baseline-mutating, or expensive operations require named explicit opt-in and path containment.

## Rejected alternatives
Implicit network access, default baseline updates, and broad project mutation were rejected.

## Consequences
Guarded quality tools remain skipped until a future adapter proves its explicit permission contract.

## Compatibility and operations
This protects source projects and is enforced by focused configuration/tool tests in the owning phase.
