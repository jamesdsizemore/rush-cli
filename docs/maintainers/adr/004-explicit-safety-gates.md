# ADR-004: explicit safety gates

**Status:** accepted

## Context

Browser, slow, network, fuzz, baseline, artifact, Git, and publication actions can create external or irreversible effects.

## Decision

Default to skip/refuse/dry-run. Require invocation-scoped, implemented consent plus target/output controls before execution.

## Consequences

A catalog command may remain a guarded placeholder. Mentioning a flag in prose is insufficient; CLI and MCP schemas must expose and test it before capability is documented as usable.
