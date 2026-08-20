# ADR-005: fixture-first adapter tests

**Status:** accepted

## Context

CI cannot safely install every runtime and scanner, while parsers must handle real native reports.

## Decision

Own sanitized native fixtures and fake-process invocation tests for clean, findings, malformed, and inconsistent cases. Add bounded installed-engine contracts separately.

## Consequences

Adapters can be tested deterministically and offline. Reference fixture freshness and engine compatibility require maintenance.
