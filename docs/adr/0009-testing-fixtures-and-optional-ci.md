# ADR 0009: Fixture-first tests and optional CI

## Context
Host-installed scanners make tests non-deterministic.

## Decision
Every adapter is proven with deterministic fake executable/output fixtures before optional installed-engine smoke coverage. CI must distinguish fixture and optional-engine lanes.

## Rejected alternatives
CI auto-installs, accidental PATH execution, and fixtureless parser claims were rejected.

## Consequences
Adapter tests cover clean, findings, malformed output, missing binary, version failure, command failure, timeout/cancellation, and redaction.

## Compatibility and operations
Optional engine absence is a structured skip, never a failing dependency of Rush itself.
