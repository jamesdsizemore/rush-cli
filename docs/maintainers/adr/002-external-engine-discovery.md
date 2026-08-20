# ADR-002: external engine discovery

**Status:** accepted

## Context

Bundling every language/runtime/scanner would make Rush large, unsafe, and hard to reproduce.

## Decision

Discover optional engine binaries at execution time. Never install implicitly. Return `skipped` with an install hint when absent.

## Consequences

Users choose engines and versions. CI provisions a bounded set. Documentation must distinguish a skipped check from a pass.
