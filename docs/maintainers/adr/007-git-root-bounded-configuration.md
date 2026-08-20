# ADR-007: Git-root-bounded configuration discovery

**Status:** accepted

## Context

Walking unbounded parent directories can apply unrelated settings from outside a checkout.

## Decision

Discover the nearest `rush.toml` upward from the target and stop at the first Git root or filesystem root. Do not merge multiple files.

## Consequences

Nested projects can own nearer policy without inheriting parent checkout settings. Monorepos must place configuration intentionally.
