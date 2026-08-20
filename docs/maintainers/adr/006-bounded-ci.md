# ADR-006: bounded CI

**Status:** accepted

## Context

An all-language CI image is expensive and fragile.

## Decision

Run core Python quality/package gates plus a small representative engine set; cover the broad adapter matrix with fixtures.

## Consequences

Promotion requires fixture evidence and at least appropriate representative contracts, not universal executable provisioning.
