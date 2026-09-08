Current status: historical decision; Optional engines are still discovered rather than installed implicitly. The Phase 59 isolated-environment amendment is a support/testing contract, not proof that every developer invocation ignores ambient PATH; [engine compatibility](../../ENGINE_COMPATIBILITY.md) describes discovery and compatibility limits.

# ADR-002: external engine discovery

**Status:** accepted

## Context

Bundling every language/runtime/scanner would make Rush large, unsafe, and hard to reproduce.

## Decision

Discover optional engine binaries at execution time. Never install implicitly. Return `skipped` with an install hint when absent.

## Consequences

Users choose engines and versions. CI provisions a bounded set. Documentation must distinguish a skipped check from a pass.
### Amendments (Phase 59)
External engine discovery is governed by `EngineSupportPolicy` and isolated with `FixedPathEnvironment` to prevent ambient developer PATH pollution.
