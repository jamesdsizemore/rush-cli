Current status: historical decision; Invocation-scoped permissions and containment remain required. Current fix dry-run, MCP ship cleanup, checkpoint, governance, and AI-evaluation paths violate parts of this contract; see [application review F01–F08](../../reports/phase-64-66-application-review.md) and [Phase 64 safe execution](../../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md). Do not treat this decision as a current safety guarantee.

# ADR-004: explicit safety gates

**Status:** accepted

## Context

Browser, slow, network, fuzz, baseline, artifact, Git, and publication actions can create external or irreversible effects.

## Decision

Default to skip/refuse/dry-run. Require invocation-scoped, implemented consent plus target/output controls before execution.

## Consequences

A catalog command may remain a guarded placeholder. Mentioning a flag in prose is insufficient; CLI and MCP schemas must expose and test it before capability is documented as usable.
