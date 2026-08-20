# ADR 0010: Review and remediation gates

## Context
Broad scanner work can drift from contracts while still passing a narrow test.

## Decision
Each slice uses RED→GREEN tests, targeted lint/format, self review, spec/security review, logged remediation, and scoped Git inspection before commit.

## Rejected alternatives
Unreviewed bulk changes, hidden global refactors, and staging unrelated research or documentation were rejected.

## Consequences
The Phase 00–02 ledger records evidence, errors, recovery, backlog, and phase gates.

## Compatibility and operations
No commit, push, tag, release, or history rewrite is implied by passing these gates.
