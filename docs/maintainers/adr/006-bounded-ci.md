Current status: historical decision; The bounded CI policy remains required; its Phase 59 amendment is not proof that the current pipeline has enforced every listed gate. [Application review F27–F29](../../reports/phase-64-66-application-review.md) and [Phase 64](../../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md) record CI, artifact, and portability acceptance work.

# ADR-006: bounded CI

**Status:** accepted

## Context

An all-language CI image is expensive and fragile.

## Decision

Run core Python quality/package gates plus a small representative engine set; cover the broad adapter matrix with fixtures.

## Consequences

Promotion requires fixture evidence and at least appropriate representative contracts, not universal executable provisioning.

### Amendments (Phase 59)
Bounded CI incorporates provisioned success, failure, and malformed jobs for supported engines and enforces the non-skipped mypy release gate.
