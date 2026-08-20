# ADR-014: Composite Workflow Suites and Real-Time File Watcher

## Status
Accepted

## Context
Running individual tools for every development stage creates CLI invocation friction.

## Decision
1. Provide composite workflow commands: `rush check`, `rush audit`, `rush gate`, `rush doctor`.
2. Provide `rush watch` for automatic background re-execution upon file modifications.

## Consequences
- Streamlined developer CLI ergonomics.
